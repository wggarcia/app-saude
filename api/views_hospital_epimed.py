"""
Integração com Epimed Monitor (estatística UTI).
"""
import json
import csv
import io
from datetime import date
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo

try:
    from .models import TransmissaoEpimed, PacienteInternado, LeitoHospitalar
except ImportError:
    TransmissaoEpimed = PacienteInternado = LeitoHospitalar = None


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.uti", "Epimed")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_epimed_page(request):
    return render(request, "hospital_epimed.html")


# ─── Status ──────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_epimed_status(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    credencial_ok = False
    ultima_transmissao = None
    total_transmissoes = 0

    try:
        from .models import CredenciaisIntegracoes
        cred = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="epimed").first()
        credencial_ok = bool(cred)
    except Exception:
        pass

    if TransmissaoEpimed:
        total_transmissoes = TransmissaoEpimed.objects.filter(empresa=emp).count()
        ultimo = TransmissaoEpimed.objects.filter(
            empresa=emp, status="enviado"
        ).order_by("-data_envio").first()
        if ultimo and ultimo.data_envio:
            ultima_transmissao = ultimo.data_envio.isoformat()

    return JsonResponse({
        "credencial_configurada": credencial_ok,
        "ultima_transmissao": ultima_transmissao,
        "total_transmissoes": total_transmissoes,
    })


# ─── Gerar CSV Epimed ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_epimed_gerar(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if PacienteInternado is None or TransmissaoEpimed is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    body = json.loads(request.body or "{}")
    competencia = body.get("competencia", timezone.now().strftime("%Y-%m"))

    # Buscar pacientes de UTI/CTI
    qs_pacientes = PacienteInternado.objects.filter(empresa=emp)
    if LeitoHospitalar:
        leitos_uti_ids = LeitoHospitalar.objects.filter(
            empresa=emp, tipo__in=["uti", "cti", "UTI", "CTI"]
        ).values_list("id", flat=True)
        qs_pacientes = qs_pacientes.filter(leito_id__in=leitos_uti_ids)

    # Gera CSV no formato Epimed
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id_paciente", "data_admissao", "data_alta", "idade",
        "diagnostico_cid", "apache2", "saps3", "procedimentos",
    ])

    for p in qs_pacientes.select_related("leito")[:5000]:
        writer.writerow([
            p.id,
            p.data_internacao.strftime("%Y-%m-%d") if getattr(p, "data_internacao", None) else "",
            p.data_alta.strftime("%Y-%m-%d") if getattr(p, "data_alta", None) else "",
            getattr(p, "idade", ""),
            getattr(p, "diagnostico_principal", ""),
            "",  # apache2 — campo calculado externamente
            "",  # saps3 — campo calculado externamente
            "",  # procedimentos
        ])

    csv_string = output.getvalue()
    total_registros = qs_pacientes.count()

    transmissao = TransmissaoEpimed.objects.create(
        empresa=emp,
        competencia=competencia,
        total_registros=total_registros,
        arquivo_gerado=csv_string,
        status="pendente",
    )

    return JsonResponse({
        "transmissao_id": transmissao.id,
        "competencia": competencia,
        "total_registros": total_registros,
        "status": "pendente",
        "mensagem": "CSV gerado. Use /transmitir/<id> para enviar.",
    }, status=201)


# ─── Transmitir ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_epimed_transmitir(request, id):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if TransmissaoEpimed is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        transmissao = TransmissaoEpimed.objects.get(pk=id, empresa=emp)
    except TransmissaoEpimed.DoesNotExist:
        return JsonResponse({"erro": "Transmissão não encontrada"}, status=404)

    # Verifica credenciais
    credencial = None
    try:
        from .models import CredenciaisIntegracoes
        credencial = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="epimed").first()
    except Exception:
        pass

    if not credencial:
        # Sem credencial — retorna CSV para download
        response = HttpResponse(transmissao.arquivo_gerado, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="epimed_{transmissao.competencia}.csv"'
        )
        return response

    # Com credencial — envio real (placeholder)
    transmissao.status = "enviado"
    transmissao.data_envio = timezone.now()
    transmissao.save()
    return JsonResponse({"status": "enviado", "transmissao_id": transmissao.id})


# ─── Histórico ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_epimed_historico(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if TransmissaoEpimed is None:
        return JsonResponse({"transmissoes": [], "total": 0})

    qs = TransmissaoEpimed.objects.filter(empresa=emp).order_by("-criado_em")[:100]
    data = [
        {
            "id": t.id,
            "competencia": t.competencia,
            "status": t.status,
            "total_registros": t.total_registros,
            "data_envio": t.data_envio.isoformat() if t.data_envio else None,
            "erro_msg": t.erro_msg,
        }
        for t in qs
    ]
    return JsonResponse({"transmissoes": data, "total": len(data)})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_epimed_kpis(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    pendentes = 0
    ultima_competencia = None
    registros_uti_mes = 0
    comp = timezone.now().strftime("%Y-%m")

    if TransmissaoEpimed:
        pendentes = TransmissaoEpimed.objects.filter(empresa=emp, status="pendente").count()
        ultimo = TransmissaoEpimed.objects.filter(empresa=emp).order_by("-competencia").first()
        if ultimo:
            ultima_competencia = ultimo.competencia
        t_mes = TransmissaoEpimed.objects.filter(empresa=emp, competencia=comp).first()
        if t_mes:
            registros_uti_mes = t_mes.total_registros

    return JsonResponse({
        "pendentes": pendentes,
        "ultima_competencia": ultima_competencia,
        "registros_uti_mes": registros_uti_mes,
        "competencia_atual": comp,
    })
