"""
views_governo_regulacao.py
Regulação Assistencial — fila SISREG-like.
"""
import json
from datetime import date

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import RegulacaoAssistencial
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import (
    requer_setor, requer_operacao_page,
    requer_permissao_modulo, api_requer_permissao_modulo,
)


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
@requer_permissao_modulo("governo.regulacao_urgencia")
def governo_regulacao_page(request):
    return render(request, "governo_regulacao.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.regulacao_urgencia")
@require_http_methods(["GET"])
def api_regulacao_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    qs = RegulacaoAssistencial.objects.filter(empresa=e)
    aguardando = qs.filter(status="aguardando").count()
    agendados = qs.filter(status="agendado").count()
    realizados_mes = qs.filter(status="realizado", data_agendamento__gte=inicio_mes).count()
    urgentes = qs.filter(status="aguardando", prioridade__in=["urgente", "emergen"]).count()
    return JsonResponse({
        "aguardando": aguardando,
        "agendados": agendados,
        "realizados_mes": realizados_mes,
        "urgentes": urgentes,
    })


# ── Lista ─────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.regulacao_urgencia")
@require_http_methods(["GET"])
def api_regulacao_lista(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = RegulacaoAssistencial.objects.filter(empresa=e)
    status = request.GET.get("status")
    tipo = request.GET.get("tipo")
    unidade = request.GET.get("unidade_origem")
    if status:
        qs = qs.filter(status=status)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if unidade:
        qs = qs.filter(unidade_origem__icontains=unidade)
    return JsonResponse({"regulacoes": [_reg_dict(r) for r in qs[:200]]})


# ── Nova solicitação ──────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.regulacao_urgencia")
@require_http_methods(["POST"])
def api_regulacao_nova(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    r = RegulacaoAssistencial.objects.create(
        empresa=e,
        paciente_nome=data.get("paciente_nome", ""),
        cns=data.get("cns", ""),
        tipo=data.get("tipo", "consulta_esp"),
        especialidade=data.get("especialidade", ""),
        procedimento=data.get("procedimento", ""),
        cid10=data.get("cid10", ""),
        unidade_origem=data.get("unidade_origem", ""),
        unidade_destino=data.get("unidade_destino", ""),
        prioridade=data.get("prioridade", "normal"),
        status="aguardando",
    )
    return JsonResponse({"id": r.id}, status=201)


# ── Atualizar ─────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.regulacao_urgencia")
@require_http_methods(["POST"])
def api_regulacao_atualizar(request, reg_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        r = RegulacaoAssistencial.objects.get(pk=reg_id, empresa=e)
    except RegulacaoAssistencial.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    if "status" in data:
        r.status = data["status"]
    if "data_agendamento" in data:
        r.data_agendamento = data["data_agendamento"] or None
    if "unidade_destino" in data:
        r.unidade_destino = data["unidade_destino"]
    r.save()
    return JsonResponse({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reg_dict(r):
    return {
        "id": r.id,
        "paciente_nome": r.paciente_nome,
        "cns": r.cns,
        "tipo": r.tipo,
        "tipo_label": r.get_tipo_display(),
        "especialidade": r.especialidade,
        "procedimento": r.procedimento,
        "cid10": r.cid10,
        "unidade_origem": r.unidade_origem,
        "unidade_destino": r.unidade_destino,
        "status": r.status,
        "status_label": r.get_status_display(),
        "data_solicitacao": str(r.data_solicitacao),
        "data_agendamento": str(r.data_agendamento) if r.data_agendamento else "",
        "prioridade": r.prioridade,
        "prioridade_label": r.get_prioridade_display(),
    }
