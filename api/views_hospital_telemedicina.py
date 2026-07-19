"""
Telemedicina Hospitalar — reutiliza TeleconsultaGoverno filtrada por empresa hospital.
"""
import json
from datetime import date
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo

try:
    from .models import TeleconsultaGoverno
except ImportError:
    TeleconsultaGoverno = None


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _consulta_to_dict(c):
    return {
        "id": c.id,
        "paciente_nome": c.paciente_nome,
        "especialidade": c.especialidade,
        "data_hora": c.data_hora.isoformat() if c.data_hora else None,
        "medico": c.profissional,
        "link_sala": c.link_sala,
        "observacoes": c.resumo,
        "status": c.status,
        "criado_em": c.criado_em.isoformat() if c.criado_em else None,
    }


# ─── Page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.telemedicina", "Telemedicina")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_telemedicina_page(request):
    return render(request, "hospital_telemedicina.html")


# ─── Consultas ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_hosp_telemedicina_consultas(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if TeleconsultaGoverno is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    if request.method == "GET":
        qs = TeleconsultaGoverno.objects.filter(empresa=emp).order_by("-data_hora")[:200]
        data = [_consulta_to_dict(c) for c in qs]
        return JsonResponse({"consultas": data, "total": len(data)})

    body = json.loads(request.body or "{}")

    # Monta data_hora a partir de data_consulta + horario ou data_hora direta
    from django.utils.dateparse import parse_datetime
    data_hora_str = body.get("data_hora")
    if not data_hora_str:
        data_consulta = body.get("data_consulta", "")
        horario = body.get("horario", "00:00")
        data_hora_str = f"{data_consulta}T{horario}:00" if data_consulta else None

    data_hora = parse_datetime(data_hora_str) if data_hora_str else timezone.now()

    consulta = TeleconsultaGoverno.objects.create(
        empresa=emp,
        paciente_nome=body.get("paciente_nome", ""),
        especialidade=body.get("especialidade", ""),
        data_hora=data_hora,
        profissional=body.get("medico", body.get("profissional", "")),
        link_sala=body.get("link_sala", ""),
        resumo=body.get("observacoes", body.get("resumo", "")),
        status="agendada",
    )
    return JsonResponse({"id": consulta.id, "mensagem": "Consulta agendada"}, status=201)


# ─── Detalhe / Atualização ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "PATCH", "PUT"])
def api_hosp_telemedicina_consulta_detalhe(request, pk):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if TeleconsultaGoverno is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        consulta = TeleconsultaGoverno.objects.get(pk=pk, empresa=emp)
    except TeleconsultaGoverno.DoesNotExist:
        return JsonResponse({"erro": "Consulta não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_consulta_to_dict(consulta))

    body = json.loads(request.body or "{}")
    if "paciente_nome" in body:
        consulta.paciente_nome = body["paciente_nome"]
    if "especialidade" in body:
        consulta.especialidade = body["especialidade"]
    if "medico" in body:
        consulta.profissional = body["medico"]
    if "profissional" in body:
        consulta.profissional = body["profissional"]
    if "link_sala" in body:
        consulta.link_sala = body["link_sala"]
    if "observacoes" in body:
        consulta.resumo = body["observacoes"]
    if "resumo" in body:
        consulta.resumo = body["resumo"]
    if "status" in body:
        consulta.status = body["status"]
    if "data_hora" in body:
        from django.utils.dateparse import parse_datetime
        dh = parse_datetime(body["data_hora"])
        if dh:
            consulta.data_hora = dh
    consulta.save()
    return JsonResponse({"mensagem": "Consulta atualizada", **_consulta_to_dict(consulta)})


# ─── Iniciar ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_hosp_telemedicina_iniciar(request, pk):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if TeleconsultaGoverno is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        consulta = TeleconsultaGoverno.objects.get(pk=pk, empresa=emp)
    except TeleconsultaGoverno.DoesNotExist:
        return JsonResponse({"erro": "Consulta não encontrada"}, status=404)

    consulta.status = "em_curso"
    consulta.save()
    return JsonResponse({"mensagem": "Consulta iniciada", "status": consulta.status, "link_sala": consulta.link_sala})


# ─── Encerrar ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_hosp_telemedicina_encerrar(request, pk):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if TeleconsultaGoverno is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        consulta = TeleconsultaGoverno.objects.get(pk=pk, empresa=emp)
    except TeleconsultaGoverno.DoesNotExist:
        return JsonResponse({"erro": "Consulta não encontrada"}, status=404)

    consulta.status = "concluida"
    consulta.encerrado_em = timezone.now()
    consulta.save()
    return JsonResponse({"mensagem": "Consulta encerrada", "status": consulta.status})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_hosp_telemedicina_kpis(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    agendadas = 0
    realizadas_mes = 0
    canceladas = 0
    comp = timezone.now().strftime("%Y-%m")

    if TeleconsultaGoverno:
        agendadas = TeleconsultaGoverno.objects.filter(
            empresa=emp, status="agendada"
        ).count()
        canceladas = TeleconsultaGoverno.objects.filter(
            empresa=emp, status="cancelada"
        ).count()
        realizadas_mes = TeleconsultaGoverno.objects.filter(
            empresa=emp,
            status="concluida",
            data_hora__year=timezone.now().year,
            data_hora__month=timezone.now().month,
        ).count()

    return JsonResponse({
        "agendadas": agendadas,
        "realizadas_mes": realizadas_mes,
        "canceladas": canceladas,
        "competencia": comp,
    })
