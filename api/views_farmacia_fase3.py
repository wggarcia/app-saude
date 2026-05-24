"""
Farmácia — Fase 3: IA & Analytics
  • CMM (Consumo Médio Mensal) calculado de movimentos reais
  • Ponto de reposição e lote econômico (Wilson / EOQ)
  • Curva ABC automática por valor de consumo
  • Score de ruptura (probabilidade de stockout em 30 dias)
  • Detecção de interações medicamentosas na dispensação
  • Previsão de demanda (trend linear simples)
"""
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import EstoqueMovimento, MedicamentoFarmacia, Dispensacao
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    setor = get_setor(empresa)
    if setor != "farmacia":
        return JsonResponse(
            {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
            status=403,
        )
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência da farmácia."}, status=403)
    return empresa


# ─── Interações medicamentosas (base estática ANVISA + literatura) ────────────
# Pares de princípios ativos com risco de interação clínica relevante
_INTERACOES = [
    {"a": "varfarina",      "b": "aspirina",       "risco": "alto",   "efeito": "Risco aumentado de hemorragia"},
    {"a": "varfarina",      "b": "ibuprofeno",     "risco": "alto",   "efeito": "Risco aumentado de hemorragia"},
    {"a": "varfarina",      "b": "diclofenaco",    "risco": "alto",   "efeito": "Risco aumentado de hemorragia"},
    {"a": "varfarina",      "b": "naproxeno",      "risco": "alto",   "efeito": "Risco aumentado de hemorragia"},
    {"a": "metformina",     "b": "contraste iodado","risco": "alto",  "efeito": "Risco de acidose lática"},
    {"a": "digoxina",       "b": "amiodarona",     "risco": "alto",   "efeito": "Toxicidade digitálica — aumenta nível sérico"},
    {"a": "digoxina",       "b": "claritromicina", "risco": "alto",   "efeito": "Toxicidade digitálica"},
    {"a": "atorvastatina",  "b": "claritromicina", "risco": "alto",   "efeito": "Risco de miopatia / rabdomiólise"},
    {"a": "sinvastatina",   "b": "amiodarona",     "risco": "alto",   "efeito": "Risco de miopatia"},
    {"a": "sildenafila",    "b": "nitrato",        "risco": "alto",   "efeito": "Hipotensão grave — contraindicação absoluta"},
    {"a": "sildenafila",    "b": "isossorbida",    "risco": "alto",   "efeito": "Hipotensão grave"},
    {"a": "clopidogrel",    "b": "omeprazol",      "risco": "medio",  "efeito": "Redução do efeito antiagregante"},
    {"a": "clopidogrel",    "b": "ibuprofeno",     "risco": "alto",   "efeito": "Risco aumentado de hemorragia"},
    {"a": "metronidazol",   "b": "alcool",         "risco": "alto",   "efeito": "Reação tipo dissulfiram (náuseas, vômito, taquicardia)"},
    {"a": "ciprofloxacino", "b": "teofilina",      "risco": "alto",   "efeito": "Toxicidade por teofilina"},
    {"a": "captopril",      "b": "espironolactona","risco": "medio",  "efeito": "Hipercalemia"},
    {"a": "lisinopril",     "b": "amilorida",      "risco": "medio",  "efeito": "Hipercalemia"},
    {"a": "tramadol",       "b": "sertralina",     "risco": "alto",   "efeito": "Síndrome serotoninérgica"},
    {"a": "tramadol",       "b": "fluoxetina",     "risco": "alto",   "efeito": "Síndrome serotoninérgica"},
    {"a": "fluoxetina",     "b": "tramadol",       "risco": "alto",   "efeito": "Síndrome serotoninérgica"},
    {"a": "lítio",          "b": "ibuprofeno",     "risco": "alto",   "efeito": "Toxicidade por lítio"},
    {"a": "lítio",          "b": "diclofenaco",    "risco": "alto",   "efeito": "Toxicidade por lítio"},
    {"a": "aminofilina",    "b": "ciprofloxacino", "risco": "alto",   "efeito": "Convulsões / toxicidade"},
    {"a": "fenitoína",      "b": "fluconazol",     "risco": "alto",   "efeito": "Toxicidade por fenitoína"},
    {"a": "carbamazepina",  "b": "eritromicina",   "risco": "alto",   "efeito": "Toxicidade por carbamazepina"},
    {"a": "tacrolimus",     "b": "fluconazol",     "risco": "alto",   "efeito": "Nefrotoxicidade / imunossupressão excessiva"},
    {"a": "ciclosporina",   "b": "sinvastatina",   "risco": "alto",   "efeito": "Risco de miopatia / rabdomiólise"},
    {"a": "metotexato",     "b": "ibuprofeno",     "risco": "alto",   "efeito": "Toxicidade por metotrexato"},
    {"a": "rivaroxabana",   "b": "aspirina",       "risco": "medio",  "efeito": "Risco aumentado de hemorragia"},
    {"a": "alopurinol",     "b": "azatioprina",    "risco": "alto",   "efeito": "Toxicidade por azatioprina — inibição do metabolismo"},
]


def _normalizar(texto):
    """Lowercase + remover acentos simples para match de princípios ativos."""
    import unicodedata
    texto = texto.lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def verificar_interacoes(principios_ativos: list[str]) -> list[dict]:
    """Retorna lista de interações encontradas entre os princípios ativos informados."""
    normalizados = [_normalizar(p) for p in principios_ativos if p]
    alertas = []
    vistos = set()

    for inter in _INTERACOES:
        a = _normalizar(inter["a"])
        b = _normalizar(inter["b"])
        for pa in normalizados:
            if a in pa or pa in a:
                for pb in normalizados:
                    if pb == pa:
                        continue
                    if b in pb or pb in b:
                        chave = tuple(sorted([a, b]))
                        if chave not in vistos:
                            vistos.add(chave)
                            alertas.append({
                                "medicamento_a": inter["a"],
                                "medicamento_b": inter["b"],
                                "risco": inter["risco"],
                                "efeito": inter["efeito"],
                            })
    return alertas


@csrf_exempt
@require_http_methods(["POST"])
def api_verificar_interacoes(request):
    """Verifica interações entre princípios ativos de uma lista de medicamentos."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    import json
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    # Aceita lista de medicamento_ids OU lista de principios_ativos
    med_ids = data.get("medicamento_ids", [])
    principios = data.get("principios_ativos", [])

    if med_ids:
        meds = MedicamentoFarmacia.objects.filter(pk__in=med_ids, empresa=empresa)
        principios = [m.principio_ativo for m in meds if m.principio_ativo]

    alertas = verificar_interacoes(principios)

    return JsonResponse({
        "principios_verificados": principios,
        "total_interacoes": len(alertas),
        "interacoes": alertas,
    })


# ─── CMM & Previsão de Demanda ────────────────────────────────────────────────

def _calcular_cmm(empresa, medicamento_id, meses=3):
    """Consumo Médio Mensal baseado em saídas reais dos últimos N meses."""
    desde = date.today() - timedelta(days=30 * meses)
    total = EstoqueMovimento.objects.filter(
        empresa=empresa,
        medicamento_id=medicamento_id,
        tipo__in=["saida", "descarte"],
        criado_em__date__gte=desde,
    ).aggregate(total=Sum("quantidade"))["total"] or Decimal("0")

    return float(total) / meses if meses > 0 else 0.0


def _calcular_eoq(cmm_mensal, preco_custo, custo_pedido=50.0, taxa_manutencao=0.20):
    """
    Wilson / EOQ:
      Q* = sqrt(2 * D * S / H)
      D = demanda anual, S = custo por pedido, H = custo de manutenção por unidade/ano
    """
    D = cmm_mensal * 12
    S = custo_pedido
    H = float(preco_custo) * taxa_manutencao if preco_custo and float(preco_custo) > 0 else 1.0
    if D <= 0 or H <= 0:
        return 0.0
    return round(math.sqrt(2 * D * S / H), 2)


def _score_ruptura(qtd_atual, cmm_mensal, lead_time_dias=7):
    """
    Score 0-100 de probabilidade de ruptura nos próximos 30 dias.
    Considera: cobertura atual vs lead time de reposição.
    """
    if cmm_mensal <= 0:
        return 0
    cmm_diario = cmm_mensal / 30
    dias_cobertura = float(qtd_atual) / cmm_diario if cmm_diario > 0 else 999
    # Se cobertura < lead_time → ruptura quase certa
    # 30 dias de janela de análise
    if dias_cobertura <= lead_time_dias:
        return 100
    if dias_cobertura >= 60:
        return 0
    # Interpolação linear
    return round(max(0, min(100, (60 - dias_cobertura) / (60 - lead_time_dias) * 100)), 1)


def _tendencia_linear(valores: list[float]) -> float:
    """
    Retorna a inclinação da tendência linear (regressão simples).
    Positivo = crescendo, negativo = caindo.
    """
    n = len(valores)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(valores) / n
    num = sum((i - x_mean) * (valores[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return round(num / den, 4) if den != 0 else 0.0


@require_http_methods(["GET"])
def api_farmacia_previsao_demanda(request):
    """CMM + EOQ + score de ruptura + tendência para todos os medicamentos."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    meses = int(request.GET.get("meses", 3))
    meses = max(1, min(meses, 12))

    meds = MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True)
    resultado = []

    for med in meds:
        cmm = _calcular_cmm(empresa, med.id, meses)
        eoq = _calcular_eoq(cmm, med.preco_custo)
        score = _score_ruptura(med.quantidade_atual, cmm)
        dias_cobertura = round(float(med.quantidade_atual) / (cmm / 30), 1) if cmm > 0 else None

        # Tendência: consumo dos últimos N meses individualmente
        consumo_por_mes = []
        for i in range(meses, 0, -1):
            inicio = date.today() - timedelta(days=30 * i)
            fim = date.today() - timedelta(days=30 * (i - 1))
            total_mes = EstoqueMovimento.objects.filter(
                empresa=empresa, medicamento_id=med.id,
                tipo__in=["saida", "descarte"],
                criado_em__date__gte=inicio,
                criado_em__date__lt=fim,
            ).aggregate(t=Sum("quantidade"))["t"] or Decimal("0")
            consumo_por_mes.append(float(total_mes))

        tendencia = _tendencia_linear(consumo_por_mes)
        ponto_reposicao = round(cmm / 30 * 7 + float(med.quantidade_minima), 2)  # lead 7 dias + estoque min

        resultado.append({
            "id": med.id,
            "nome": med.nome,
            "principio_ativo": med.principio_ativo,
            "forma": med.forma_farmaceutica,
            "quantidade_atual": float(med.quantidade_atual),
            "quantidade_minima": float(med.quantidade_minima),
            "preco_custo": float(med.preco_custo),
            "cmm": round(cmm, 2),
            "eoq": eoq,
            "ponto_reposicao": ponto_reposicao,
            "score_ruptura": score,
            "dias_cobertura": dias_cobertura,
            "tendencia_mensal": tendencia,
            "consumo_por_mes": consumo_por_mes,
            "status_estoque": med.status_estoque,
            "controlado": med.controlado,
        })

    # Ordenar por score de ruptura decrescente
    resultado.sort(key=lambda x: x["score_ruptura"], reverse=True)
    return JsonResponse({"medicamentos": resultado, "meses_analise": meses})


# ─── Curva ABC ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_curva_abc(request):
    """Classifica medicamentos como A/B/C por valor de consumo real."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    meses = int(request.GET.get("meses", 3))
    meses = max(1, min(meses, 12))
    desde = date.today() - timedelta(days=30 * meses)

    meds = MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True)

    dados = []
    for med in meds:
        consumo = EstoqueMovimento.objects.filter(
            empresa=empresa, medicamento_id=med.id,
            tipo__in=["saida", "descarte"],
            criado_em__date__gte=desde,
        ).aggregate(t=Sum("quantidade"))["t"] or Decimal("0")
        valor_consumo = float(consumo) * float(med.preco_custo)
        dados.append({
            "id": med.id,
            "nome": med.nome,
            "principio_ativo": med.principio_ativo,
            "forma": med.forma_farmaceutica,
            "quantidade_consumida": float(consumo),
            "preco_custo": float(med.preco_custo),
            "valor_consumo": round(valor_consumo, 2),
            "quantidade_atual": float(med.quantidade_atual),
            "status_estoque": med.status_estoque,
        })

    # Ordenar por valor de consumo descendente
    dados.sort(key=lambda x: x["valor_consumo"], reverse=True)

    total_valor = sum(d["valor_consumo"] for d in dados)
    acumulado = 0.0

    for i, d in enumerate(dados):
        acumulado += d["valor_consumo"]
        pct_acum = (acumulado / total_valor * 100) if total_valor > 0 else 0
        # Regra 80/15/5: A≤80%, B≤95%, C>95%
        if pct_acum <= 80:
            d["classe"] = "A"
        elif pct_acum <= 95:
            d["classe"] = "B"
        else:
            d["classe"] = "C"
        d["pct_valor_acumulado"] = round(pct_acum, 1)
        d["posicao"] = i + 1

    totais = {
        "A": {"itens": 0, "valor": 0, "pct_itens": 0, "pct_valor": 0},
        "B": {"itens": 0, "valor": 0, "pct_itens": 0, "pct_valor": 0},
        "C": {"itens": 0, "valor": 0, "pct_itens": 0, "pct_valor": 0},
    }
    for d in dados:
        totais[d["classe"]]["itens"] += 1
        totais[d["classe"]]["valor"] += d["valor_consumo"]

    n = len(dados)
    for cls in totais:
        totais[cls]["pct_itens"] = round(totais[cls]["itens"] / n * 100, 1) if n else 0
        totais[cls]["pct_valor"] = round(totais[cls]["valor"] / total_valor * 100, 1) if total_valor else 0
        totais[cls]["valor"] = round(totais[cls]["valor"], 2)

    return JsonResponse({
        "total_itens": n,
        "total_valor_consumo": round(total_valor, 2),
        "meses_analise": meses,
        "resumo": totais,
        "medicamentos": dados,
    })


# ─── Dashboard de IA ─────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_ia_dashboard(request):
    """Resumo executivo de IA: top riscos, recomendações de compra, alertas."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    meds = MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True)
    alertas_ruptura = []
    recomendacoes_compra = []

    for med in meds:
        cmm = _calcular_cmm(empresa, med.id, 3)
        score = _score_ruptura(med.quantidade_atual, cmm)
        eoq = _calcular_eoq(cmm, med.preco_custo)

        if score >= 70:
            alertas_ruptura.append({
                "id": med.id,
                "nome": med.nome,
                "score_ruptura": score,
                "quantidade_atual": float(med.quantidade_atual),
                "cmm": round(cmm, 2),
                "criticidade": "urgente" if score >= 90 else "alto",
            })

        if eoq > 0 and float(med.quantidade_atual) < eoq * 0.5:
            recomendacoes_compra.append({
                "id": med.id,
                "nome": med.nome,
                "eoq": eoq,
                "quantidade_atual": float(med.quantidade_atual),
                "quantidade_sugerida": round(eoq - float(med.quantidade_atual), 2),
                "preco_custo": float(med.preco_custo),
                "valor_estimado": round((eoq - float(med.quantidade_atual)) * float(med.preco_custo), 2),
            })

    alertas_ruptura.sort(key=lambda x: x["score_ruptura"], reverse=True)
    recomendacoes_compra.sort(key=lambda x: x["valor_estimado"], reverse=True)

    return JsonResponse({
        "total_medicamentos": meds.count(),
        "alertas_ruptura": alertas_ruptura[:10],
        "recomendacoes_compra": recomendacoes_compra[:10],
        "total_alertas_ruptura": len(alertas_ruptura),
        "total_valor_reposicao": round(sum(r["valor_estimado"] for r in recomendacoes_compra), 2),
    })
