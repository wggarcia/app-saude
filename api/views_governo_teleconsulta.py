"""
views_governo_teleconsulta.py
Teleconsulta cidadão — agendamento e gestão de salas.
"""
import json
import uuid
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import TeleconsultaGoverno
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import requer_setor, requer_operacao_page, requer_permissao_modulo


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
def governo_teleconsulta_page(request):
    return render(request, "governo_teleconsulta.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    qs = TeleconsultaGoverno.objects.filter(empresa=e)
    agendadas_hoje = qs.filter(data_hora__date=hoje, status="agendada").count()
    concluidas_mes = qs.filter(status="concluida", data_hora__date__gte=inicio_mes).count()
    em_curso = qs.filter(status="em_curso").count()
    total = qs.count()
    return JsonResponse({
        "agendadas_hoje": agendadas_hoje,
        "concluidas_mes": concluidas_mes,
        "em_curso": em_curso,
        "total": total,
    })


# ── Lista ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_lista(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = TeleconsultaGoverno.objects.filter(empresa=e)
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    return JsonResponse({"teleconsultas": [_tc_dict(t) for t in qs[:200]]})


# ── Agendar ───────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_teleconsulta_agendar(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    sala_id = uuid.uuid4().hex[:12]
    link_sala = f"https://teleconsulta.sus.gov.br/sala/{sala_id}"
    tc = TeleconsultaGoverno.objects.create(
        empresa=e,
        paciente_nome=data.get("paciente_nome", ""),
        cns=data.get("cns", ""),
        profissional=data.get("profissional", ""),
        especialidade=data.get("especialidade", ""),
        data_hora=data.get("data_hora"),
        status="agendada",
        link_sala=link_sala,
        resumo="",
    )
    return JsonResponse({"id": tc.id, "link_sala": link_sala}, status=201)


# ── Atualizar ─────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_teleconsulta_atualizar(request, tc_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        tc = TeleconsultaGoverno.objects.get(pk=tc_id, empresa=e)
    except TeleconsultaGoverno.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    if "status" in data:
        tc.status = data["status"]
    if "resumo" in data:
        tc.resumo = data["resumo"]
    tc.save()
    return JsonResponse({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tc_dict(t):
    return {
        "id": t.id,
        "paciente_nome": t.paciente_nome,
        "cns": t.cns,
        "profissional": t.profissional,
        "especialidade": t.especialidade,
        "data_hora": t.data_hora.isoformat(),
        "status": t.status,
        "status_label": t.get_status_display(),
        "link_sala": t.link_sala,
        "resumo": t.resumo,
        "criado_em": t.criado_em.isoformat(),
    }
