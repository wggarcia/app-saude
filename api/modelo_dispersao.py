"""
Modelo de dispersão epidemiológica — o 9º sistema de IA da SoloCRT.

Responde à pergunta que o Detector de Surto (api/epidemiologia_ml.py, IA #5)
NÃO responde: **para onde o surto vai**. O #5 diz "onde a doença está agora";
este diz "em quais municípios ela provavelmente chega em 7, 14 e 30 dias, e por
qual rota".

Método: SEIR metapopulacional com acoplamento de mobilidade (padrão em
epidemiologia — ex.: GLEAM, modelos de metapopulação de Colizza/Vespignani).
Cada município é um compartimento SEIR; a mobilidade (matriz de voos de
api/pipeline_mobilidade.py) redistribui a força de infecção entre eles. A
probabilidade de chegada num município ainda não afetado sai do número
esperado de introduções importadas (processo de Poisson):

        P_chegada_i(T) = 1 − exp(−m_i(T))

onde m_i(T) é o nº esperado acumulado de infecções importadas até T.

Sem scipy (não está nas dependências): integração por Euler em numpy puro.
O nº de compartimentos é pequeno (municípios com aeroporto + focos ativos),
então roda em milissegundos.

Este módulo é MATEMÁTICA PURA e testável offline: recebe seeds, populações e a
matriz de mobilidade já prontos, e devolve projeções. Ele nunca inventa dado —
quem chama (o management command) resolve seeds reais de SurtoEpidemiologico e
a matriz real de MatrizMobilidade. Onde falta população, usa um default
explícito e o registra nos metadados, para a projeção nunca mentir sobre sua
própria base.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


# ── Parâmetros por doença ────────────────────────────────────────────────────
# sigma = 1/período de incubação (dias⁻¹); gamma = 1/período infeccioso;
# beta  = taxa de transmissão = R0 * gamma. Valores de faixa central da
# literatura para a fase de dispersão — ajustáveis por doença. Não são
# "verdade absoluta": são premissas transparentes, guardadas nos metadados
# da projeção para quem for auditar.
@dataclass(frozen=True)
class ParametrosDoenca:
    nome: str
    r0: float
    incubacao_dias: float
    infeccioso_dias: float
    # acoplamento de mobilidade: fração da força de infecção que vem de fora
    # (via viajantes), vs. transmissão puramente local. 0 = ilhas isoladas.
    rho_mobilidade: float = 0.15

    @property
    def sigma(self) -> float:
        return 1.0 / self.incubacao_dias

    @property
    def gamma(self) -> float:
        return 1.0 / self.infeccioso_dias

    @property
    def beta(self) -> float:
        return self.r0 * self.gamma


# Faixas centrais de literatura. Chave em minúsculo sem acento resolvida por
# parametros_para_doenca(); doença desconhecida cai num default genérico.
PARAMS_POR_DOENCA = {
    "dengue":       ParametrosDoenca("Dengue", r0=2.5, incubacao_dias=5.5, infeccioso_dias=5.0),
    "zika":         ParametrosDoenca("Zika", r0=2.0, incubacao_dias=6.0, infeccioso_dias=5.0),
    "chikungunya":  ParametrosDoenca("Chikungunya", r0=2.8, incubacao_dias=4.0, infeccioso_dias=6.0),
    "febre amarela": ParametrosDoenca("Febre Amarela", r0=2.0, incubacao_dias=4.5, infeccioso_dias=4.0),
    "sarampo":      ParametrosDoenca("Sarampo", r0=13.0, incubacao_dias=11.0, infeccioso_dias=8.0, rho_mobilidade=0.25),
    "covid-19":     ParametrosDoenca("COVID-19", r0=2.8, incubacao_dias=5.0, infeccioso_dias=7.0, rho_mobilidade=0.25),
    "gripe":        ParametrosDoenca("Gripe", r0=1.4, incubacao_dias=2.0, infeccioso_dias=4.0, rho_mobilidade=0.2),
    "influenza":    ParametrosDoenca("Gripe", r0=1.4, incubacao_dias=2.0, infeccioso_dias=4.0, rho_mobilidade=0.2),
    "mpox":         ParametrosDoenca("Mpox", r0=1.6, incubacao_dias=8.0, infeccioso_dias=14.0),
    "meningite":    ParametrosDoenca("Meningite", r0=1.3, incubacao_dias=4.0, infeccioso_dias=7.0),
}
PARAMS_DEFAULT = ParametrosDoenca("Genérica", r0=2.0, incubacao_dias=5.0, infeccioso_dias=5.0)

HORIZONTES_PADRAO = (7, 14, 30)
POPULACAO_DEFAULT = 100_000  # usado só quando o município não tem população conhecida


def _normalizar_nome(doenca: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (doenca or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def parametros_para_doenca(doenca: str) -> ParametrosDoenca:
    alvo = _normalizar_nome(doenca)
    for chave, params in PARAMS_POR_DOENCA.items():
        if _normalizar_nome(chave) == alvo:
            return params
    return PARAMS_DEFAULT


# ── Núcleo: SEIR metapopulacional ────────────────────────────────────────────
def projetar_dispersao(
    seeds: dict,
    populacoes: dict,
    matriz_norm: dict,
    params: ParametrosDoenca,
    *,
    horizontes=HORIZONTES_PADRAO,
    populacao_default: int = POPULACAO_DEFAULT,
    dt: float = 0.5,
) -> dict:
    """Projeta a dispersão de uma doença a partir de focos ativos.

    Args:
        seeds:        {ibge: casos_ativos} — focos atuais (I inicial por município).
        populacoes:   {ibge: habitantes} — população; ausência vira populacao_default.
        matriz_norm:  {origem_ibge: {destino_ibge: peso∈(0,1]}} — mobilidade
                      normalizada por origem (de matriz_para_pesos_normalizados()).
        params:       ParametrosDoenca (beta/sigma/gamma/rho).
        horizontes:   dias a projetar (default 7/14/30).

    Returns:
        {horizonte_dias: [
            {ibge, probabilidade, casos_projetados, origem_provavel_ibge, semente},
            ...ordenado por probabilidade desc, só municípios NÃO-semente...
        ]}
        Municípios-semente são marcados 'semente': True e reportados à parte.
    """
    seeds = {str(k): float(v) for k, v in (seeds or {}).items() if v and float(v) > 0}
    if not seeds:
        return {h: [] for h in horizontes}

    # Universo de compartimentos: focos + toda origem/destino alcançável na matriz.
    patches: set = set(seeds.keys())
    for o, destinos in (matriz_norm or {}).items():
        patches.add(str(o))
        for d in destinos:
            patches.add(str(d))
    patches = sorted(patches)
    idx = {ibge: i for i, ibge in enumerate(patches)}
    n = len(patches)

    N = np.array([float(populacoes.get(p, populacao_default) or populacao_default) for p in patches])
    N = np.maximum(N, 1.0)

    # Matriz de importação W[i, j] = fração de viajantes de j que chegam em i.
    # (linha = destino, coluna = origem). Multiplicada pela prevalência de j,
    # dá a pressão infecciosa importada em i.
    W = np.zeros((n, n))
    for o, destinos in (matriz_norm or {}).items():
        j = idx.get(str(o))
        if j is None:
            continue
        for d, peso in destinos.items():
            i = idx.get(str(d))
            if i is not None:
                W[i, j] += float(peso)

    # Estado inicial
    I = np.zeros(n)
    for p, casos in seeds.items():
        I[idx[p]] = min(casos, N[idx[p]])
    E = np.zeros(n)
    R = np.zeros(n)
    S = np.maximum(N - I - E - R, 0.0)

    beta, sigma, gamma, rho = params.beta, params.sigma, params.gamma, params.rho_mobilidade
    era_semente = np.array([p in seeds for p in patches])

    # Acumuladores para probabilidade de chegada (Poisson) e origem provável.
    m_importado = np.zeros(n)                 # nº esperado acumulado de infecções importadas
    contrib_origem = np.zeros((n, n))         # soma da contribuição de j para importação em i

    horizontes = sorted(set(int(h) for h in horizontes))
    t_max = max(horizontes)
    passos = int(round(t_max / dt))
    resultado_por_h: dict = {}
    proximo_h = {h: int(round(h / dt)) for h in horizontes}

    for passo in range(1, passos + 1):
        prev = I / N                                   # prevalência por município
        importada = W @ prev                           # pressão importada (por destino)
        # força de infecção: local + importada (ponderada por rho)
        forca = (1 - rho) * prev + rho * importada
        novas = beta * S * forca * dt
        novas = np.minimum(novas, S)                   # não infecta mais que os suscetíveis

        # componente importada das novas infecções → alimenta a chance de chegada
        comp_import = beta * S * rho * importada * dt
        m_importado += comp_import
        # contribuição de cada origem j (para descobrir a rota provável)
        contrib_origem += (beta * S * rho * dt)[:, None] * (W * prev[None, :])

        dE = novas - sigma * E * dt
        dI = sigma * E * dt - gamma * I * dt
        dR = gamma * I * dt

        S = np.maximum(S - novas, 0.0)
        E = np.maximum(E + dE, 0.0)
        I = np.maximum(I + dI, 0.0)
        R = np.maximum(R + dR, 0.0)

        for h, passo_alvo in proximo_h.items():
            if passo == passo_alvo:
                prob = 1.0 - np.exp(-m_importado)      # P(≥1 introdução) por Poisson
                casos_acumulados = N - S               # já infectados (E+I+R + saídos)
                origem_idx = contrib_origem.argmax(axis=1)
                linhas = []
                for i, p in enumerate(patches):
                    semente = bool(era_semente[i])
                    oi = int(origem_idx[i])
                    origem_prov = patches[oi] if (contrib_origem[i, oi] > 0 and oi != i) else ""
                    linhas.append({
                        "ibge": p,
                        "semente": semente,
                        "probabilidade": 1.0 if semente else round(float(prob[i]), 4),
                        "casos_projetados": round(float(casos_acumulados[i]), 1),
                        "origem_provavel_ibge": origem_prov,
                    })
                resultado_por_h[h] = linhas

    # Ordena cada horizonte: não-sementes por probabilidade desc
    saida = {}
    for h, linhas in resultado_por_h.items():
        nao_sementes = sorted(
            (l for l in linhas if not l["semente"]),
            key=lambda l: l["probabilidade"], reverse=True,
        )
        saida[h] = nao_sementes
    return saida
