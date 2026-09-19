"""
Motor de interpretação de audiometria ocupacional — SoloCRT SST.

Implementa os critérios da NR-07 (Portaria SEPRT 6.734/2020, ex-Quadro II da NR-7):
classificação de grau, detecção de padrão sugestivo de PAIR (Perda Auditiva
Induzida por Ruído) e comparação sequencial entre exames (desencadeamento,
agravamento, estabilidade, melhora).

Tudo aqui é função pura e determinística — sem I/O, sem IA, sem banco. Isso
torna a interpretação auditável e testável, diferente de caixas-pretas do
mercado. Os limiares chegam em dB (NA) por frequência.

Frequências avaliadas na via aérea: 500, 1000, 2000, 3000, 4000, 6000, 8000 Hz.
"""
from __future__ import annotations

# Frequências padrão (Hz) — via aérea ocupacional
FREQUENCIAS = [500, 1000, 2000, 3000, 4000, 6000, 8000]

# Grupos usados nos cálculos (NR-07)
_FREQ_FALA = [500, 1000, 2000]          # frequências da fala
_FREQ_ALTAS = [3000, 4000, 6000]        # frequências altas (região da "gota acústica")

# Limiar de normalidade (dB) — acima disto há comprometimento
LIMIAR_NORMAL = 25
# Variação mínima (dB) na média das altas para caracterizar piora/melhora sequencial
DELTA_SEQUENCIAL = 10


def _media(limiares: dict, freqs: list[int]) -> float | None:
    """Média aritmética dos limiares nas frequências dadas. None se faltar dado."""
    vals = []
    for f in freqs:
        v = limiares.get(str(f), limiares.get(f))
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def _grau_perda(media_fala: float | None) -> str:
    """Classifica o grau da perda pela média das frequências da fala (500-2000 Hz)."""
    if media_fala is None:
        return "indeterminado"
    if media_fala <= 25:
        return "normal"
    if media_fala <= 40:
        return "leve"
    if media_fala <= 55:
        return "moderada"
    if media_fala <= 70:
        return "moderadamente_severa"
    if media_fala <= 90:
        return "severa"
    return "profunda"


def _sugestivo_pair(limiares: dict) -> bool:
    """
    Detecta o padrão sugestivo de PAIR (NR-07): limiares em 3000, 4000 e/ou
    6000 Hz maiores que nas demais frequências (entalhe / gota acústica),
    apresentando-se em geral com nível igual ou superior a 25 dB.
    """
    piores_altas = None
    for f in _FREQ_ALTAS:
        v = limiares.get(str(f), limiares.get(f))
        if v is None:
            continue
        v = float(v)
        if piores_altas is None or v > piores_altas:
            piores_altas = v
    if piores_altas is None or piores_altas < LIMIAR_NORMAL:
        return False

    # a "gota" exige recuperação em 8000 Hz (vizinha), característica do entalhe
    v8000 = limiares.get("8000", limiares.get(8000))
    v6000 = limiares.get("6000", limiares.get(6000))
    entalhe_8k = True
    if v8000 is not None and v6000 is not None:
        entalhe_8k = float(v8000) < float(v6000)

    # e as altas precisam estar piores que a média da fala
    media_fala = _media(limiares, _FREQ_FALA)
    pior_que_fala = media_fala is None or piores_altas > media_fala
    return entalhe_8k and pior_que_fala


def classificar_orelha(limiares: dict) -> dict:
    """
    Classifica uma orelha a partir dos limiares (dict freq->dB).
    Retorna grau, médias e flag de padrão sugestivo de PAIR.
    """
    media_fala = _media(limiares, _FREQ_FALA)
    media_altas = _media(limiares, _FREQ_ALTAS)
    return {
        "media_fala": media_fala,
        "media_altas": media_altas,
        "grau": _grau_perda(media_fala),
        "sugestivo_pair": _sugestivo_pair(limiares),
        "alterada": (media_fala is not None and media_fala > LIMIAR_NORMAL) or _sugestivo_pair(limiares),
    }


def interpretar(limiares: dict) -> dict:
    """
    Interpreta um exame completo. `limiares` no formato:
      {"od_aerea": {"500": 10, ...}, "oe_aerea": {...}}
    Retorna classificação por orelha + laudo-resumo automático.
    """
    od = classificar_orelha(limiares.get("od_aerea", {}) or {})
    oe = classificar_orelha(limiares.get("oe_aerea", {}) or {})

    sugestivo = od["sugestivo_pair"] or oe["sugestivo_pair"]
    alterada = od["alterada"] or oe["alterada"]

    if not alterada:
        resumo = "Audiometria dentro dos limites da normalidade em ambas as orelhas."
        classificacao = "normal"
    elif sugestivo:
        resumo = ("Audiometria com padrão sugestivo de PAIR (entalhe em frequências "
                  "altas). Correlacionar com histórico de exposição a ruído e vincular ao PCA.")
        classificacao = "sugestivo_pair"
    else:
        resumo = ("Audiometria alterada sem padrão típico de PAIR. Recomenda-se "
                  "avaliação otorrinolaringológica para diagnóstico diferencial.")
        classificacao = "alterada_nao_pair"

    return {
        "od": od,
        "oe": oe,
        "classificacao": classificacao,
        "sugestivo_pair": sugestivo,
        "alterada": alterada,
        "resumo": resumo,
    }


def comparar_sequencial(atual: dict, anterior: dict | None) -> dict:
    """
    Compara o exame atual com o anterior (referência) segundo a NR-07.

    Piora significativa (desencadeamento/agravamento) quando a média dos limiares
    em 3000-4000-6000 Hz piora >= 10 dB em relação ao exame de referência, em
    qualquer orelha. Melhora quando reduz >= 10 dB. Caso contrário, estável.

    Retorna classificação sequencial e se há indicação de reteste imediato.
    """
    if not anterior:
        interp = interpretar(atual)
        return {
            "classificacao_sequencial": "referencia",
            "reteste_indicado": False,
            "delta_od": None,
            "delta_oe": None,
            "detalhe": "Exame de referência (base) — sem exame anterior para comparação.",
            "novo_caso": interp["alterada"],
        }

    def _delta(orelha_key):
        a = _media((atual.get(orelha_key) or {}), _FREQ_ALTAS)
        b = _media((anterior.get(orelha_key) or {}), _FREQ_ALTAS)
        if a is None or b is None:
            return None
        return round(a - b, 1)  # positivo = piorou

    delta_od = _delta("od_aerea")
    delta_oe = _delta("oe_aerea")
    deltas = [d for d in (delta_od, delta_oe) if d is not None]

    piora = any(d >= DELTA_SEQUENCIAL for d in deltas)
    melhora = deltas and all(d <= -DELTA_SEQUENCIAL for d in deltas)

    interp_atual = interpretar(atual)
    interp_ant = interpretar(anterior)

    if piora:
        # desencadeamento = primeira vez que cruza para alterada; senão agravamento
        if interp_atual["alterada"] and not interp_ant["alterada"]:
            classificacao = "desencadeamento"
            detalhe = "Desencadeamento: exame cruzou para alterado com piora >= 10 dB nas altas frequências."
        else:
            classificacao = "agravamento"
            detalhe = "Agravamento: piora >= 10 dB na média das frequências altas (3-4-6 kHz)."
        reteste = True
    elif melhora:
        classificacao = "melhora"
        detalhe = "Melhora >= 10 dB na média das frequências altas em relação à referência."
        reteste = False
    else:
        classificacao = "estavel"
        detalhe = "Estável: sem variação significativa (< 10 dB) em relação à referência."
        reteste = False

    return {
        "classificacao_sequencial": classificacao,
        "reteste_indicado": reteste,
        "delta_od": delta_od,
        "delta_oe": delta_oe,
        "detalhe": detalhe,
        "novo_caso": interp_atual["alterada"] and not interp_ant["alterada"],
    }
