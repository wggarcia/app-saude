"""
Motor de interpretação de espirometria ocupacional — SoloCRT SST.

Classifica o distúrbio ventilatório (normal, obstrutivo, restritivo, misto) e o
grau, a partir de CVF, VEF1 e do índice VEF1/CVF (Tiffeneau) e dos percentuais
do previsto. Função pura e determinística — auditável e testável.

Critérios (referência espirometria ocupacional / diretrizes SBPT):
  - VEF1/CVF < 0,70 → padrão obstrutivo
  - CVF < 80% do previsto com VEF1/CVF normal → padrão restritivo (sugestivo)
  - ambos reduzidos → padrão misto
  - grau pelo VEF1 (% do previsto)
"""
from __future__ import annotations

LIMITE_TIFFENEAU = 0.70          # VEF1/CVF abaixo disto = obstrução
LIMITE_CVF_PREV = 80.0           # CVF abaixo de 80% do previsto = redução de volume


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _grau_por_vef1(vef1_prev: float | None) -> str:
    """Grau do distúrbio pelo VEF1 em % do previsto (escala tipo GOLD)."""
    if vef1_prev is None:
        return "indeterminado"
    if vef1_prev >= 80:
        return "leve"
    if vef1_prev >= 60:
        return "moderado"
    if vef1_prev >= 50:
        return "moderadamente_grave"
    if vef1_prev >= 35:
        return "grave"
    return "muito_grave"


def interpretar(dados: dict) -> dict:
    """
    dados: {
      "cvf": litros, "vef1": litros, "vef1_cvf": fração (0-1) ou %,
      "cvf_prev": % do previsto, "vef1_prev": % do previsto
    }
    Aceita vef1_cvf como fração (0,72) ou percentual (72). Retorna padrão + grau.
    """
    cvf = _num(dados.get("cvf"))
    vef1 = _num(dados.get("vef1"))
    tiff = _num(dados.get("vef1_cvf"))
    cvf_prev = _num(dados.get("cvf_prev"))
    vef1_prev = _num(dados.get("vef1_prev"))

    # normaliza índice para fração
    if tiff is None and cvf and vef1 and cvf > 0:
        tiff = vef1 / cvf
    if tiff is not None and tiff > 1.5:  # veio em percentual
        tiff = tiff / 100.0

    obstrucao = tiff is not None and tiff < LIMITE_TIFFENEAU
    reducao_volume = cvf_prev is not None and cvf_prev < LIMITE_CVF_PREV

    if obstrucao and reducao_volume:
        padrao = "misto"
        resumo = ("Distúrbio ventilatório misto (obstrutivo + restritivo). "
                  "Encaminhar para avaliação pneumológica.")
    elif obstrucao:
        padrao = "obstrutivo"
        resumo = ("Distúrbio ventilatório obstrutivo (VEF1/CVF < 0,70). "
                  "Correlacionar com tabagismo e exposição ocupacional a poeiras/gases.")
    elif reducao_volume:
        padrao = "restritivo"
        resumo = ("Padrão sugestivo de distúrbio restritivo (CVF < 80% do previsto "
                  "com relação VEF1/CVF preservada). Confirmar com pletismografia.")
    elif tiff is None and cvf_prev is None and vef1_prev is None:
        padrao = "indeterminado"
        resumo = "Dados insuficientes para interpretação."
    else:
        padrao = "normal"
        resumo = "Espirometria dentro dos limites da normalidade."

    grau = _grau_por_vef1(vef1_prev) if padrao not in ("normal", "indeterminado") else padrao

    return {
        "padrao": padrao,
        "grau": grau,
        "vef1_cvf": round(tiff, 2) if tiff is not None else None,
        "obstrucao": obstrucao,
        "reducao_volume": reducao_volume,
        "alterada": padrao not in ("normal", "indeterminado"),
        "resumo": resumo,
    }


def comparar_sequencial(atual: dict, anterior: dict | None) -> dict:
    """Compara VEF1 (% do previsto) com exame anterior. Queda >= 10 pontos
    percentuais indica declínio funcional acelerado (reteste/investigação)."""
    if not anterior:
        return {"classificacao_sequencial": "referencia", "declinio_indicado": False,
                "delta_vef1": None, "detalhe": "Exame de referência."}
    a = _num(atual.get("vef1_prev"))
    b = _num(anterior.get("vef1_prev"))
    if a is None or b is None:
        return {"classificacao_sequencial": "estavel", "declinio_indicado": False,
                "delta_vef1": None, "detalhe": "Sem dados comparáveis de VEF1 previsto."}
    delta = round(a - b, 1)  # negativo = piorou
    if delta <= -10:
        return {"classificacao_sequencial": "declinio", "declinio_indicado": True,
                "delta_vef1": delta, "detalhe": "Queda >= 10 pontos no VEF1 (% previsto) — investigar."}
    if delta >= 10:
        return {"classificacao_sequencial": "melhora", "declinio_indicado": False,
                "delta_vef1": delta, "detalhe": "Melhora >= 10 pontos no VEF1 (% previsto)."}
    return {"classificacao_sequencial": "estavel", "declinio_indicado": False,
            "delta_vef1": delta, "detalhe": "Estável (variação < 10 pontos)."}
