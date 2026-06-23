"""
Hospital — Farmácia: Dispensação de Dose Unitária por Leito
  • Ciclo da farmácia (preparo → conferência → dispensação ao leito),
    separado do registro de administração feito pela enfermagem.
"""
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_feature
from .models import PacienteInternado, PrescricaoHospitalar, DispensacaoDoseUnitaria
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


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


def _dose_to_dict(d):
    return {
        "id": d.id,
        "prescricao_id": d.prescricao_id,
        "nome_medicamento": d.nome_medicamento,
        "dose": d.dose,
        "leito_numero": d.leito_numero,
        "horario_previsto": d.horario_previsto.strftime("%H:%M") if d.horario_previsto else None,
        "status": d.status,
        "farmaceutico_responsavel": d.farmaceutico_responsavel,
        "crf": d.crf,
        "preparada_em": d.preparada_em.strftime("%d/%m/%Y %H:%M") if d.preparada_em else None,
        "dispensada_em": d.dispensada_em.strftime("%d/%m/%Y %H:%M") if d.dispensada_em else None,
        "observacoes": d.observacoes,
        "criado_em": d.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.dose_unitaria")
def api_dose_unitaria_paciente(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        qs = pac.dispensacoes_dose_unitaria.all()[:100]
        return JsonResponse({"dispensacoes": [_dose_to_dict(d) for d in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    presc_id = data.get("prescricao_id")
    nome_med = (data.get("nome_medicamento") or "").strip()
    if not presc_id or not nome_med:
        return JsonResponse({"erro": "prescricao_id e nome_medicamento são obrigatórios"}, status=400)

    presc = PrescricaoHospitalar.objects.filter(pk=presc_id, empresa=empresa, paciente=pac).first()
    if not presc:
        return JsonResponse({"erro": "Prescrição não encontrada para este paciente"}, status=404)

    horario = None
    if data.get("horario_previsto"):
        from datetime import time as dtime
        try:
            horario = dtime.fromisoformat(data["horario_previsto"])
        except ValueError:
            return JsonResponse({"erro": "horario_previsto inválido (HH:MM)"}, status=400)

    dose = DispensacaoDoseUnitaria.objects.create(
        prescricao=presc,
        paciente=pac,
        nome_medicamento=nome_med,
        dose=(data.get("dose") or "").strip(),
        leito_numero=pac.leito.numero if pac.leito else "",
        horario_previsto=horario,
        farmaceutico_responsavel=(data.get("farmaceutico_responsavel") or "").strip(),
        crf=(data.get("crf") or "").strip(),
        observacoes=(data.get("observacoes") or "").strip(),
    )
    return JsonResponse({"ok": True, "dispensacao": _dose_to_dict(dose)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_feature("hospital.dose_unitaria")
def api_dose_unitaria_status(request, dose_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    dose = DispensacaoDoseUnitaria.objects.select_related("paciente").filter(
        pk=dose_id, paciente__empresa=empresa,
    ).first()
    if not dose:
        return JsonResponse({"erro": "Dispensação não encontrada"}, status=404)

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    novo_status = data.get("status")
    if novo_status not in dict(DispensacaoDoseUnitaria.STATUS_CHOICES):
        return JsonResponse({"erro": "status inválido"}, status=400)

    dose.status = novo_status
    agora = timezone.now()
    if novo_status == "preparada":
        dose.preparada_em = agora
    elif novo_status == "dispensada_leito":
        dose.dispensada_em = agora
    dose.save()

    return JsonResponse({"ok": True, "dispensacao": _dose_to_dict(dose)})
