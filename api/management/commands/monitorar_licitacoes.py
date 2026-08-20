"""
monitorar_licitacoes.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monitor de licitações públicas (PNCP — Portal Nacional de Contratações
Públicas, oficial da Lei 14.133/2021). Varre os editais publicados nos
últimos dias, filtra os que casam com o produto SoloCRT (SOFTWARE/SISTEMA
para SAÚDE ou ASSISTÊNCIA SOCIAL/SUAS) e salva como LicitacaoOportunidade.

É o canal certo de venda pro setor público — que compra por licitação, não
por email frio. Roda 1x/dia via cron.

Filtro = cruza DOMÍNIO (saúde/SUAS) com TECNOLOGIA (sistema/software/etc),
pra não pegar comprinha de oxigênio/comida/limpeza.

  cd /opt/soluscrt && set -a && . ./.env && set +a && \
    venv/bin/python -u manage.py monitorar_licitacoes >> /var/log/soluscrt/licitacoes.log 2>&1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import re
import time
from datetime import datetime, date, timedelta

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone as djtz

from api.models import LicitacaoOportunidade

PNCP_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"

# Modalidades eletrônicas onde software/serviço aparece (código PNCP):
# 6=Pregão Eletrônico, 4=Concorrência Eletrônica, 8=Dispensa
_MODALIDADES = [6, 4, 8]

_DOMINIO_SAUDE = [
    "saúde", "saude", "hospital", "prontuário", "prontuario", "ubs", "atenção básica",
    "atencao basica", "e-sus", "esus", "vigilância", "vigilancia", "epidemiol",
    "regulação", "regulacao", "samu", "farmácia", "farmacia", "ambulatorial",
    "atenção primária", "atencao primaria", "sus",
]
_DOMINIO_ASSIST = [
    "assistência social", "assistencia social", "suas", "cras", "creas",
    "socioassistencial", "bolsa família", "bolsa familia", "cadúnico", "cadunico",
    "acolhimento", "proteção social", "protecao social",
]
_TECH = [
    "software", "prontuário eletrônico", "prontuario eletronico", "aplicativo",
    "plataforma digital", "tecnologia da informação", "tecnologia da informacao",
    "informatiz", "digitaliz", "pec", "licenciamento de software", "licença de uso",
    "licenca de uso", "sistema de gestão", "sistema de gestao", "sistema de informação",
    "sistema de informacao", "sistema informatizado", "sistema de prontuário",
    "sistema de prontuario", "sistema de regulação", "sistema de regulacao",
    "sistema de gerenciamento", "gestão informatiz", "gestao informatiz",
    "solução de software", "solucao de software", "erp", "sistema web",
]

# Frases-armadilha: contêm "sistema"/"saúde" mas são DOMÍNIO, não tecnologia.
# Removidas do texto antes de checar TECH pra não dar falso positivo.
_ARMADILHAS = [
    "sistema único de saúde", "sistema unico de saude", "por meio do sistema",
    "sistema de saúde", "sistema de saude", "sistema prisional", "sistema viário",
    "sistema viario", "sistema de abastecimento", "sistema de esgoto",
]

# Se qualquer um destes aparecer, é compra de commodity/serviço não-software: veta.
_EXCLUSAO = [
    "buffet", "refeiç", "refeic", "coffee", "gênero aliment", "genero aliment",
    "gêneros aliment", "generos aliment", "merenda", "alimentíc", "alimentic",
    "oxigên", "oxigen", "medicament", "material de limpeza", "material de consumo",
    "material hospitalar", "materiais hospitalar", "combustív", "combustiv",
    "veículo", "veiculo", "pavimenta", "obra ", "reforma", "construção de",
    "construcao de", "uniforme", "mobiliár", "mobiliar", "insumo", "reagente",
    "órtese", "ortese", "prótese", "protese", "registrador eletrônico",
    "registradores eletrôn", "ponto eletrôn", "ponto eletron", "material médico",
    "material medico", "locação de veícul", "locacao de veicul", "gases medicinais",
    # Hardware/equipamento (mesmo quando cita 'sistema'/TI) — não é software:
    "ar condicionado", "ultrassonogr", "ultrassom", "multissensorial",
    "materiais de tecnologia", "material de tecnologia", "aparelho de ar",
    "raio-x", "raio x", "tomógrafo", "tomografo", "mamógrafo", "mamografo",
    "equipamentos de informática", "equipamentos de informatica",
]


# Siglas curtas: precisam casar como PALAVRA INTEIRA (senão 'sus' bate dentro de
# 'sustentável', 'ubs' dentro de outra palavra, etc.).
_ACRONIMOS = {"sus", "ubs", "cras", "creas", "samu", "suas", "esus", "e-sus",
              "pec", "erp", "sgs"}


def _m(kw: str, texto: str) -> bool:
    """Casa keyword no texto respeitando limite de palavra no INÍCIO. Para siglas
    curtas exige palavra inteira (início e fim); para o resto basta o início, o
    que deixa radicais funcionarem ('epidemiol' → 'epidemiologia', 'informatiz'
    → 'informatização') sem casar no meio de outra palavra."""
    if kw in _ACRONIMOS:
        return re.search(r"\b" + re.escape(kw) + r"\b", texto) is not None
    return re.search(r"\b" + re.escape(kw), texto) is not None


def _classificar(obj_lower: str):
    """Retorna (casa?, area, termos) — cruza domínio (saúde/SUAS) com tecnologia
    (software de verdade), vetando commodities e frases-armadilha."""
    if any(x in obj_lower for x in _EXCLUSAO):
        return False, None, ""
    dom_saude = [k for k in _DOMINIO_SAUDE if _m(k, obj_lower)]
    dom_assist = [k for k in _DOMINIO_ASSIST if _m(k, obj_lower)]
    if not (dom_saude or dom_assist):
        return False, None, ""
    # remove frases-armadilha antes de procurar tecnologia
    obj_tech = obj_lower
    for arm in _ARMADILHAS:
        obj_tech = obj_tech.replace(arm, " ")
    tech = [k for k in _TECH if _m(k, obj_tech)]
    if not tech:
        return False, None, ""
    if dom_saude and dom_assist:
        area = "ambos"
    elif dom_assist:
        area = "assistencia"
    else:
        area = "saude"
    termos = (dom_saude + dom_assist + tech)[:6]
    return True, area, ", ".join(termos)


def _parse_data(valor):
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = djtz.make_aware(dt)
    return dt


class Command(BaseCommand):
    help = "Varre o PNCP e salva licitações de software para saúde/assistência social."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=3,
                            help="Quantos dias pra trás varrer (default 3, sobrepõe pro cron diário)")
        parser.add_argument("--paginas-max", type=int, default=40,
                            help="Máx. de páginas por modalidade (trava de segurança)")
        parser.add_argument("--pausa", type=float, default=1.2,
                            help="Segundos entre chamadas (PNCP tem rate limit; 1.2 evita 429)")

    def handle(self, *args, **options):
        dias = options["dias"]
        pag_max = options["paginas_max"]
        pausa = options["pausa"]

        hoje = date.today()
        inicio = hoje - timedelta(days=dias)
        di, df = inicio.strftime("%Y%m%d"), hoje.strftime("%Y%m%d")

        analisados = matches = novos = 0
        por_area = {"saude": 0, "assistencia": 0, "ambos": 0}

        for modalidade in _MODALIDADES:
            for pagina in range(1, pag_max + 1):
                # tenta a página com backoff em caso de 429 (rate limit do PNCP)
                payload = None
                for tentativa in range(5):
                    try:
                        resp = requests.get(PNCP_URL, params={
                            "dataInicial": di, "dataFinal": df,
                            "codigoModalidadeContratacao": modalidade,
                            "pagina": pagina, "tamanhoPagina": 50,
                        }, headers={"Accept": "application/json"}, timeout=30)
                        if resp.status_code == 204:
                            payload = {"data": []}
                            break
                        if resp.status_code == 429:
                            espera = 5 * (tentativa + 1)
                            self.stdout.write(f"  429 (rate limit) modalidade={modalidade} pag={pagina} — aguardando {espera}s")
                            time.sleep(espera)
                            continue
                        resp.raise_for_status()
                        payload = resp.json()
                        break
                    except Exception as exc:
                        self.stdout.write(f"  erro modalidade={modalidade} pag={pagina}: {exc}")
                        time.sleep(3)
                if payload is None:
                    self.stdout.write(f"  desistindo de modalidade={modalidade} na pag={pagina}")
                    break

                itens = payload.get("data") or []
                if not itens:
                    break

                for it in itens:
                    analisados += 1
                    obj = it.get("objetoCompra") or ""
                    casa, area, termos = _classificar(obj.lower())
                    if not casa:
                        continue
                    matches += 1

                    ncp = it.get("numeroControlePNCP") or ""
                    if not ncp:
                        continue

                    unidade = it.get("unidadeOrgao") or {}
                    orgao_ent = it.get("orgaoEntidade") or {}
                    dt_abertura = _parse_data(it.get("dataAberturaProposta"))
                    dt_pub = _parse_data(it.get("dataPublicacaoPncp") or it.get("dataInclusao"))

                    _, criado = LicitacaoOportunidade.objects.get_or_create(
                        numero_controle_pncp=ncp,
                        defaults={
                            "objeto": obj[:5000],
                            "orgao": (orgao_ent.get("razaoSocial") or "")[:300],
                            "municipio": (unidade.get("municipioNome") or "")[:150],
                            "uf": (unidade.get("ufSigla") or "")[:2],
                            "modalidade": (it.get("modalidadeNome") or "")[:80],
                            "valor_estimado": it.get("valorTotalEstimado") or None,
                            "data_publicacao": dt_pub.date() if dt_pub else None,
                            "data_abertura": dt_abertura,
                            "link_origem": (it.get("linkSistemaOrigem") or "")[:600],
                            "area": area,
                            "palavras_match": termos[:300],
                            "dados_adicionais": {
                                "numeroCompra": it.get("numeroCompra"),
                                "anoCompra": it.get("anoCompra"),
                                "modalidadeId": modalidade,
                            },
                        },
                    )
                    if criado:
                        novos += 1
                        por_area[area] = por_area.get(area, 0) + 1
                        self.stdout.write(f"  NOVA [{area}] {unidade.get('ufSigla','')} "
                                          f"{(orgao_ent.get('razaoSocial') or '')[:35]} :: {obj[:80]}")

                time.sleep(pausa)

        self.stdout.write("\n=== RESUMO ===")
        self.stdout.write(f"Período: {di} a {df} | itens analisados: {analisados}")
        self.stdout.write(f"Casaram com o filtro: {matches} | Novos salvos: {novos}")
        self.stdout.write(f"Novos por área — saúde: {por_area['saude']} | "
                          f"assistência: {por_area['assistencia']} | ambos: {por_area['ambos']}")
        total = LicitacaoOportunidade.objects.count()
        abertas = LicitacaoOportunidade.objects.filter(status="nova").count()
        self.stdout.write(f"Total no banco: {total} | aguardando análise (nova): {abertas}")
