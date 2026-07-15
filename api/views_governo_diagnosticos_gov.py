"""
views_governo_diagnosticos_gov.py
Panorama epidemiológico — Camada 2 (diagnósticos CID-10 confirmados por médico).
Exclusivo do gestor governo. Nunca exposto no app cidadão.
"""
import logging
from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncWeek
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor,
    principal_pode_operacao_setorial,
    requer_operacao_page,
    requer_permissao_modulo,
    requer_setor,
    contexto_navegacao_setorial,
)
from .models import DiagnosticoConfirmadoGov
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base

logger = logging.getLogger(__name__)


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def governo_diagnosticos_panorama_page(request):
    return render(request, "governo_diagnosticos_panorama.html", contexto_navegacao_setorial(request, "governo"))


# ── API ───────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_diagnosticos_confirmados(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        dias = int(request.GET.get("dias", 30))
    except (ValueError, TypeError):
        dias = 30
    dias = max(7, min(dias, 365))

    desde = date.today() - timedelta(days=dias)
    qs = DiagnosticoConfirmadoGov.objects.filter(empresa=e, data_registro__gte=desde)

    total = qs.count()

    # Top CID-10
    por_cid10 = list(
        qs.values("cid10").annotate(total=Count("id")).order_by("-total")[:20]
    )
    for item in por_cid10:
        item["label"] = _label_cid10(item["cid10"])

    # Por município
    por_municipio = list(
        qs.values("cidade", "estado")
        .annotate(total=Count("id"))
        .order_by("-total")[:30]
    )
    for m in por_municipio:
        top = (
            qs.filter(cidade=m["cidade"], estado=m["estado"])
            .values("cid10")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        m["top_cid10"] = top["cid10"] if top else ""
        m["top_cid10_label"] = _label_cid10(m["top_cid10"]) if m["top_cid10"] else ""

    # Tendência semanal
    tendencia = list(
        qs.annotate(semana=TruncWeek("data_registro"))
        .values("semana")
        .annotate(total=Count("id"))
        .order_by("semana")
    )
    for t in tendencia:
        t["semana"] = t["semana"].isoformat() if t["semana"] else ""

    crescendo = False
    if len(tendencia) >= 2:
        crescendo = tendencia[-1]["total"] > tendencia[-2]["total"]

    # Mês corrente vs mês anterior (comparação)
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_mes_ant = (inicio_mes - timedelta(days=1)).replace(day=1)
    mes_atual = DiagnosticoConfirmadoGov.objects.filter(empresa=e, data_registro__gte=inicio_mes).count()
    mes_anterior = DiagnosticoConfirmadoGov.objects.filter(
        empresa=e, data_registro__gte=inicio_mes_ant, data_registro__lt=inicio_mes
    ).count()
    variacao_mensal = round(((mes_atual - mes_anterior) / mes_anterior * 100), 1) if mes_anterior else None

    municipios_cobertos = qs.filter(cidade__gt="").values("cidade").distinct().count()

    return JsonResponse({
        "periodo_dias": dias,
        "total": total,
        "mes_atual": mes_atual,
        "mes_anterior": mes_anterior,
        "variacao_mensal_pct": variacao_mensal,
        "municipios_cobertos": municipios_cobertos,
        "crescendo": crescendo,
        "por_cid10": por_cid10,
        "por_municipio": por_municipio,
        "tendencia_semanal": tendencia,
    })


# ── CID-10 labels (top códigos na APS brasileira) ─────────────────────────────

_CID10_LABELS = {
    # Respiratório
    "J06": "IVAS", "J06.9": "IVAS", "J00": "Resfriado comum",
    "J02": "Faringotonsilite", "J02.9": "Faringotonsilite",
    "J03": "Amigdalite", "J03.9": "Amigdalite",
    "J06.0": "Laringofaringite", "J11": "Gripe / Influenza",
    "J18": "Pneumonia", "J18.9": "Pneumonia NE", "J20": "Bronquite aguda",
    "J44": "DPOC", "J45": "Asma",
    # Cardiovascular
    "I10": "Hipertensão arterial", "I11": "Hipertensão cardíaca",
    "I25": "Doença arterial coronariana", "I50": "Insuficiência cardíaca",
    # Metabólico / endócrino
    "E11": "Diabetes tipo 2", "E10": "Diabetes tipo 1",
    "E14": "Diabetes NE", "E03": "Hipotireoidismo",
    "E66": "Obesidade",
    # Digestivo
    "K21": "DRGE", "K29": "Gastrite", "K59": "Intestino irritável",
    "A09": "Diarreia infecciosa",
    # Infecções
    "A90": "Dengue", "A92": "Arbovirose", "B34": "Infecção viral NE",
    "N39": "ITU", "N39.0": "ITU",
    # Mental
    "F32": "Depressão", "F41": "Ansiedade", "F41.1": "Transtorno ansioso",
    # Neurológico
    "G43": "Enxaqueca", "R51": "Cefaleia",
    # Musculoesquelético
    "M54": "Dorsalgia", "M54.5": "Lombalgia",
    # Dermatológico
    "L20": "Dermatite atópica", "L30": "Dermatite NE",
    # Outros
    "Z00": "Check-up / Consulta rotina", "Z71": "Aconselhamento",
}


def _label_cid10(code):
    if not code:
        return code
    c = code.strip().upper()
    return _CID10_LABELS.get(c, _CID10_LABELS.get(c.split(".")[0], c))
