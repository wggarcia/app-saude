"""
views_governo_faturamento.py
Faturamento SUS — BPA / APAC / AIH.
"""
import json
from datetime import date

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import FaturamentoSUSLote
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import requer_setor, requer_operacao_page


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
def governo_faturamento_sus_page(request):
    return render(request, "governo_faturamento_sus.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_faturamento_sus_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    competencia_atual = hoje.strftime("%Y%m")
    qs = FaturamentoSUSLote.objects.filter(empresa=e, competencia=competencia_atual)
    total_registros = qs.aggregate(t=Sum("total_registros"))["t"] or 0
    total_aprovado = qs.aggregate(t=Sum("total_aprovado"))["t"] or 0
    total_lotes = qs.count()
    enviados = qs.filter(enviado_cnes=True).count()
    return JsonResponse({
        "competencia_atual": competencia_atual,
        "total_lotes": total_lotes,
        "total_registros": total_registros,
        "total_aprovado": str(total_aprovado),
        "lotes_enviados": enviados,
        "lotes_pendentes": total_lotes - enviados,
    })


# ── Lotes ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_faturamento_sus_lotes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        competencia = request.GET.get("competencia", "")
        qs = FaturamentoSUSLote.objects.filter(empresa=e)
        if competencia:
            qs = qs.filter(competencia=competencia)
        return JsonResponse({"lotes": [_lote_dict(l) for l in qs[:200]]})
    data = json.loads(request.body or "{}")
    lote = FaturamentoSUSLote.objects.create(
        empresa=e,
        competencia=data.get("competencia", ""),
        tipo=data.get("tipo", "bpa"),
        estabelecimento_cnes=data.get("estabelecimento_cnes", ""),
        total_registros=int(data.get("total_registros", 0)),
        total_aprovado=data.get("total_aprovado", 0) or 0,
        enviado_cnes=False,
    )
    return JsonResponse({"id": lote.id}, status=201)


# ── Transmitir ────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_faturamento_sus_transmitir(request, lote_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        lote = FaturamentoSUSLote.objects.get(pk=lote_id, empresa=e)
    except FaturamentoSUSLote.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if lote.enviado_cnes:
        return JsonResponse({"erro": "Lote já transmitido"}, status=400)
    lote.enviado_cnes = True
    lote.save(update_fields=["enviado_cnes"])
    return JsonResponse({"ok": True, "lote_id": lote.id})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lote_dict(l):
    return {
        "id": l.id,
        "competencia": l.competencia,
        "tipo": l.tipo,
        "tipo_label": l.get_tipo_display(),
        "estabelecimento_cnes": l.estabelecimento_cnes,
        "total_registros": l.total_registros,
        "total_aprovado": str(l.total_aprovado),
        "enviado_cnes": l.enviado_cnes,
        "criado_em": l.criado_em.isoformat(),
    }
