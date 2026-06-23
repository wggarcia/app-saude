"""
Hospital — Controle de Visitantes
  • Check-in / check-out de visitantes por paciente internado
  • Alerta (não bloqueante) quando já há 2+ visitantes simultâneos no leito
"""
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_feature
from .models import PacienteInternado, VisitanteHospitalar
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base

LIMITE_VISITANTES_SIMULTANEOS = 2


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    setor = get_setor(empresa)
    if setor != "hospital":
        return JsonResponse(
            {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
            status=403,
        )
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência hospitalar."}, status=403)
    return empresa


def _pac_or_404(empresa, pac_id):
    try:
        return PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
    except PacienteInternado.DoesNotExist:
        return None


def _visitante_to_dict(v):
    return {
        "id": v.id,
        "nome": v.nome,
        "documento": v.documento,
        "parentesco": v.parentesco,
        "telefone": v.telefone,
        "entrada": v.entrada.strftime("%d/%m/%Y %H:%M"),
        "saida": v.saida.strftime("%d/%m/%Y %H:%M") if v.saida else None,
        "status": v.status,
        "registrado_por": v.registrado_por,
        "observacoes": v.observacoes,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.visitantes")
def api_visitantes_paciente(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        qs = pac.visitantes.all()[:100]
        return JsonResponse({"visitantes": [_visitante_to_dict(v) for v in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = (data.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"erro": "nome é obrigatório"}, status=400)

    visitante = VisitanteHospitalar.objects.create(
        paciente=pac,
        nome=nome,
        documento=(data.get("documento") or "").strip(),
        parentesco=(data.get("parentesco") or "").strip(),
        telefone=(data.get("telefone") or "").strip(),
        registrado_por=(data.get("registrado_por") or "").strip(),
        observacoes=(data.get("observacoes") or "").strip(),
    )

    dentro_agora = pac.visitantes.filter(status="dentro").count()
    alerta = (
        f"Atenção: já há {dentro_agora} visitantes simultâneos neste leito "
        f"(limite recomendado: {LIMITE_VISITANTES_SIMULTANEOS})."
        if dentro_agora > LIMITE_VISITANTES_SIMULTANEOS else None
    )

    return JsonResponse(
        {"ok": True, "visitante": _visitante_to_dict(visitante), "alerta": alerta},
        status=201,
    )


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_feature("hospital.visitantes")
def api_visitante_saida(request, visitante_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        visitante = VisitanteHospitalar.objects.select_related("paciente").get(
            pk=visitante_id, paciente__empresa=empresa,
        )
    except VisitanteHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Visitante não encontrado"}, status=404)

    if visitante.status == "saiu":
        return JsonResponse({"erro": "Visitante já registrou saída"}, status=400)

    visitante.saida = timezone.now()
    visitante.status = "saiu"
    visitante.save()
    return JsonResponse({"ok": True, "visitante": _visitante_to_dict(visitante)})
