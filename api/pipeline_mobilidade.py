"""
Pipeline de mobilidade aérea (OpenSky Network) — alimenta o modelo de
dispersão epidemiológica (api/modelo_dispersao.py).

Mesma filosofia do pipeline_oficial.py: coleta um sinal público e agrega em
tabela compartilhada, SEM dado individual e SEM vínculo com empresa/tenant.
O que este módulo produz é uma matriz origem→destino de fluxo de voos entre
municípios brasileiros — puramente agregada, é dado de mobilidade, não de
pessoa. Isso responde a "para onde o surto vai", não "onde está".

Fonte: OpenSky Network (https://opensky-network.org/), REST API pública.
Desde 2025 a OpenSky migrou o acesso autenticado para OAuth2 (client
credentials). Este módulo:
  • usa OAuth2 se OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET estiverem no ambiente
    (padrão do projeto: credencial em env var, como ANTHROPIC_API_KEY);
  • cai para acesso anônimo (rate limit menor) quando não há credencial —
    suficiente para MVP e para a demo do estande.
Nunca inventa dado: se a API não responder, retorna vazio e quem chama decide
o fallback (o modelo de dispersão sabe operar com matriz esparsa).

FlightAware (comercial, ~R$ 2.500/mês) NÃO é necessário: OpenSky cobre o
espaço aéreo brasileiro para o propósito de estimar fluxo entre municípios.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ── OpenSky endpoints ────────────────────────────────────────────────────────
OPENSKY_BASE = "https://opensky-network.org/api"
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/"
    "protocol/openid-connect/token"
)
# A janela máxima aceita por consulta de partidas/chegadas é 7 dias (limite
# documentado da OpenSky). Consultas maiores são quebradas em blocos.
JANELA_MAX_SEG = 7 * 24 * 3600

_token_cache: dict = {"access_token": None, "expira_em": 0.0}


# ── Aeroportos brasileiros × município (IBGE) ────────────────────────────────
# ICAO → (IATA, código IBGE do município do aeroporto, nome, UF).
# Os códigos IBGE são VALIDADOS contra api/base_municipios.json em
# validar_aeroportos() (roda nos testes) — não confie neles sem essa checagem.
# Cobre os ~45 aeroportos de maior movimento, que concentram a grande maioria
# do tráfego doméstico. Ampliar a tabela é só acrescentar linhas aqui.
AEROPORTOS_BR = {
    "SBGR": ("GRU", 3518800, "Guarulhos", "SP"),
    "SBSP": ("CGH", 3550308, "São Paulo", "SP"),
    "SBKP": ("VCP", 3509502, "Campinas", "SP"),
    "SBRJ": ("SDU", 3304557, "Rio de Janeiro", "RJ"),
    "SBGL": ("GIG", 3304557, "Rio de Janeiro", "RJ"),
    "SBBR": ("BSB", 5300108, "Brasília", "DF"),
    "SBCF": ("CNF", 3117876, "Confins", "MG"),
    "SBBH": ("PLU", 3106200, "Belo Horizonte", "MG"),
    "SBPA": ("POA", 4314902, "Porto Alegre", "RS"),
    "SBCT": ("CWB", 4125506, "São José dos Pinhais", "PR"),
    "SBSV": ("SSA", 2927408, "Salvador", "BA"),
    "SBRF": ("REC", 2611606, "Recife", "PE"),
    "SBFZ": ("FOR", 2304400, "Fortaleza", "CE"),
    "SBEG": ("MAO", 1302603, "Manaus", "AM"),
    "SBBE": ("BEL", 1501402, "Belém", "PA"),
    "SBPS": ("BPS", 2925303, "Porto Seguro", "BA"),
    "SBFL": ("FLN", 4205407, "Florianópolis", "SC"),
    "SBGO": ("GYN", 5208707, "Goiânia", "GO"),
    "SBSG": ("NAT", 2412005, "São Gonçalo do Amarante", "RN"),
    "SBMO": ("MCZ", 2704302, "Maceió", "AL"),
    "SBVT": ("VIX", 3205309, "Vitória", "ES"),
    "SBCY": ("CGB", 5108402, "Várzea Grande", "MT"),
    "SBSL": ("SLZ", 2111300, "São Luís", "MA"),
    "SBJP": ("JPA", 2507507, "João Pessoa", "PB"),
    "SBTE": ("THE", 2211001, "Teresina", "PI"),
    "SBAR": ("AJU", 2800308, "Aracaju", "SE"),
    "SBPL": ("PNZ", 2611101, "Petrolina", "PE"),
    "SBUL": ("UDI", 3170206, "Uberlândia", "MG"),
    "SBLO": ("LDB", 4113700, "Londrina", "PR"),
    "SBMG": ("MGF", 4115200, "Maringá", "PR"),
    "SBFI": ("IGU", 4108304, "Foz do Iguaçu", "PR"),
    "SBNF": ("NVT", 4211306, "Navegantes", "SC"),
    "SBJV": ("JOI", 4209102, "Joinville", "SC"),
    "SBPV": ("PVH", 1100205, "Porto Velho", "RO"),
    "SBRB": ("RBR", 1200401, "Rio Branco", "AC"),
    "SBBV": ("BVB", 1400100, "Boa Vista", "RR"),
    "SBMQ": ("MCP", 1600303, "Macapá", "AP"),
    "SBPJ": ("PMW", 1721000, "Palmas", "TO"),
    "SBCG": ("CGR", 5002704, "Campo Grande", "MS"),
    "SBIL": ("IOS", 2913606, "Ilhéus", "BA"),
    "SBJU": ("JDO", 2307304, "Juazeiro do Norte", "CE"),
    "SBKG": ("CPV", 2504009, "Campina Grande", "PB"),
    "SBSJ": ("SJK", 3549904, "São José dos Campos", "SP"),
    "SBDN": ("PPB", 3541406, "Presidente Prudente", "SP"),
}


def icao_para_ibge(icao: str):
    """Retorna o código IBGE do município do aeroporto, ou None se desconhecido."""
    reg = AEROPORTOS_BR.get((icao or "").upper())
    return reg[1] if reg else None


# ── Base de municípios (para validação e geo) ────────────────────────────────
_MUNICIPIOS_CACHE: dict | None = None


def _carregar_municipios() -> dict:
    """codigo_ibge (int) → registro do município. Lido de api/base_municipios.json."""
    global _MUNICIPIOS_CACHE
    if _MUNICIPIOS_CACHE is None:
        caminho = Path(__file__).with_name("base_municipios.json")
        # o arquivo tem BOM UTF-8 — utf-8-sig lida com os dois casos
        with open(caminho, encoding="utf-8-sig") as fh:
            dados = json.load(fh)
        _MUNICIPIOS_CACHE = {int(m["codigo_ibge"]): m for m in dados}
    return _MUNICIPIOS_CACHE


_UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}

_NOME_UF_INDEX: dict | None = None


def _norm(txt: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (txt or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def geo_municipio(ibge) -> dict | None:
    """Registro geográfico do município (nome, uf, lat, lon) por código IBGE."""
    m = _carregar_municipios().get(int(ibge)) if str(ibge).isdigit() else None
    if not m:
        return None
    return {
        "ibge": str(m["codigo_ibge"]),
        "nome": m["nome"],
        "uf": _UF_POR_CODIGO.get(m["codigo_uf"], ""),
        "latitude": m["latitude"],
        "longitude": m["longitude"],
    }


def resolver_ibge(nome: str, uf: str | None = None):
    """Resolve (nome do município, UF) → código IBGE (str). None se não achar.

    Usado para converter SurtoEpidemiologico.municipio (texto) em código IBGE.
    Casa por nome normalizado + UF; sem UF, só aceita se o nome for único no país.
    """
    global _NOME_UF_INDEX
    if _NOME_UF_INDEX is None:
        _NOME_UF_INDEX = {}
        por_nome: dict = {}
        for m in _carregar_municipios().values():
            uf_m = _UF_POR_CODIGO.get(m["codigo_uf"], "")
            chave = (_norm(m["nome"]), uf_m)
            _NOME_UF_INDEX[chave] = str(m["codigo_ibge"])
            por_nome.setdefault(_norm(m["nome"]), []).append(str(m["codigo_ibge"]))
        _NOME_UF_INDEX["__por_nome__"] = por_nome

    nome_n = _norm(nome)
    if uf:
        return _NOME_UF_INDEX.get((nome_n, uf.strip().upper()))
    candidatos = _NOME_UF_INDEX["__por_nome__"].get(nome_n, [])
    return candidatos[0] if len(candidatos) == 1 else None


def validar_aeroportos() -> list[str]:
    """Confere que todo IBGE de AEROPORTOS_BR existe na base real.

    Retorna lista de problemas (vazia = tudo certo). Usada nos testes para
    travar a build se algum código IBGE de aeroporto for digitado errado.
    """
    municipios = _carregar_municipios()
    problemas: list[str] = []
    for icao, (iata, ibge, nome, uf) in AEROPORTOS_BR.items():
        m = municipios.get(ibge)
        if m is None:
            problemas.append(f"{icao}/{iata}: IBGE {ibge} ({nome}/{uf}) não existe na base")
    return problemas


# ── OpenSky: autenticação e coleta ───────────────────────────────────────────
def _obter_token() -> str | None:
    """Token OAuth2 (client credentials). None se não houver credencial."""
    client_id = getattr(settings, "OPENSKY_CLIENT_ID", None) or ""
    client_secret = getattr(settings, "OPENSKY_CLIENT_SECRET", None) or ""
    if not client_id or not client_secret:
        return None

    agora = time.time()
    if _token_cache["access_token"] and _token_cache["expira_em"] > agora + 30:
        return _token_cache["access_token"]

    try:
        r = requests.post(
            OPENSKY_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OpenSky: falha ao obter token OAuth2: %s", exc)
        return None

    token = payload.get("access_token")
    _token_cache["access_token"] = token
    _token_cache["expira_em"] = agora + float(payload.get("expires_in", 1800))
    return token


def _opensky_get(path: str, params: dict, *, tentativas: int = 3, backoff: float = 2.0):
    """GET na OpenSky com retry; usa OAuth2 se disponível, senão anônimo.

    Retorna o JSON decodificado (lista de voos) ou None em falha definitiva.
    Não levanta exceção: a mobilidade é um sinal auxiliar, nunca deve
    derrubar quem chama.
    """
    token = _obter_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"{OPENSKY_BASE}{path}"

    for tentativa in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 404:
                # OpenSky devolve 404 quando não há voo na janela — não é erro
                return []
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if tentativa < tentativas - 1:
                espera = backoff ** tentativa
                logger.warning(
                    "OpenSky GET %s falhou (%d/%d): %s — aguardando %.0fs",
                    path, tentativa + 1, tentativas, exc, espera,
                )
                time.sleep(espera)
            else:
                logger.warning("OpenSky GET %s falhou definitivamente: %s", path, exc)
    return None


def _blocos_janela(inicio: int, fim: int):
    """Quebra [inicio, fim] em blocos de no máximo JANELA_MAX_SEG segundos."""
    if fim <= inicio:
        return
    atual = inicio
    while atual < fim:
        prox = min(atual + JANELA_MAX_SEG, fim)
        yield atual, prox
        atual = prox


def coletar_partidas(icao: str, inicio: int, fim: int) -> list[dict]:
    """Voos que partiram de `icao` em [inicio, fim] (epoch UTC).

    Retorna lista de dicts crus da OpenSky (chaves estAirport /
    estDepartureAirport / estArrivalAirport etc.). Lista vazia = sem dado.
    """
    voos: list[dict] = []
    for a, b in _blocos_janela(inicio, fim):
        dados = _opensky_get("/flights/departure", {"airport": icao, "begin": a, "end": b})
        if dados:
            voos.extend(dados)
    return voos


def coletar_chegadas(icao: str, inicio: int, fim: int) -> list[dict]:
    """Voos que chegaram em `icao` em [inicio, fim] (epoch UTC)."""
    voos: list[dict] = []
    for a, b in _blocos_janela(inicio, fim):
        dados = _opensky_get("/flights/arrival", {"airport": icao, "begin": a, "end": b})
        if dados:
            voos.extend(dados)
    return voos


# ── Construção da matriz de fluxo origem→destino ─────────────────────────────
def construir_matriz_fluxo(voos: list[dict]) -> dict:
    """Agrega voos crus da OpenSky numa matriz (origem_ibge, destino_ibge)→nº voos.

    Só conta voos cujos AEROPORTOS de origem E destino estão em AEROPORTOS_BR
    (voo doméstico entre municípios que sabemos mapear). Voo internacional ou
    para aeroporto fora da tabela é ignorado — não inventa destino.

    A chave do dict é a tupla (origem_ibge, destino_ibge); voos dentro do mesmo
    município (origem == destino) são descartados (não há dispersão).
    """
    matriz: dict = defaultdict(int)
    for v in voos:
        dep = (v.get("estDepartureAirport") or "").upper()
        arr = (v.get("estArrivalAirport") or "").upper()
        if not dep or not arr:
            continue
        o = icao_para_ibge(dep)
        d = icao_para_ibge(arr)
        if o is None or d is None or o == d:
            continue
        matriz[(o, d)] += 1
    return dict(matriz)


def matriz_para_pesos_normalizados(matriz: dict) -> dict:
    """Normaliza a matriz por origem: peso[o][d] = fração dos voos de o que vão a d.

    Saída: {origem_ibge: {destino_ibge: peso∈(0,1]}}. Usada como acoplamento de
    mobilidade no SEIR metapopulacional (api/modelo_dispersao.py).
    """
    por_origem: dict = defaultdict(dict)
    total_por_origem: dict = defaultdict(int)
    for (o, d), n in matriz.items():
        por_origem[o][d] = n
        total_por_origem[o] += n

    normalizada: dict = {}
    for o, destinos in por_origem.items():
        total = total_por_origem[o] or 1
        normalizada[o] = {d: n / total for d, n in destinos.items()}
    return normalizada


def coletar_matriz_nacional(inicio: int, fim: int) -> dict:
    """Coleta partidas de TODOS os aeroportos BR e monta a matriz nacional.

    Este é o ponto de entrada usado pelo management command. Faz uma consulta
    de partidas por aeroporto (as chegadas já são cobertas por serem partidas
    de outro aeroporto BR), então agrega tudo numa matriz só.
    """
    todos_voos: list[dict] = []
    for icao in AEROPORTOS_BR:
        todos_voos.extend(coletar_partidas(icao, inicio, fim))
    return construir_matriz_fluxo(todos_voos)


def epoch_utc(dt: datetime) -> int:
    """datetime → epoch UTC (int). Aceita naive (assume UTC) ou aware."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())
