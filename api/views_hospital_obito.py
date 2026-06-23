"""
Hospital — Declaração de Óbito (DO)
  • Registro estruturado de óbito vinculado a PacienteInternado, com os campos
    exigidos para o SIM (Sistema de Informação sobre Mortalidade): causas CID
    (imediata/intermediária/básica), tipo de morte, necropsia, SVO/IML.
  • Ao emitir a DO, o status do paciente é automaticamente marcado como "obito".
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_feature
from .models import PacienteInternado, DeclaracaoObito
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


def _do_to_dict(d):
    return {
        "id": d.id,
        "numero_do": d.numero_do,
        "data_obito": d.data_obito.strftime("%d/%m/%Y %H:%M"),
        "local_obito": d.local_obito,
        "tipo_morte": d.tipo_morte,
        "causa_imediata_cid": d.causa_imediata_cid,
        "causa_imediata_descricao": d.causa_imediata_descricao,
        "causa_intermediaria_cid": d.causa_intermediaria_cid,
        "causa_intermediaria_descricao": d.causa_intermediaria_descricao,
        "causa_basica_cid": d.causa_basica_cid,
        "causa_basica_descricao": d.causa_basica_descricao,
        "causas_contribuintes": d.causas_contribuintes,
        "necropsia_realizada": d.necropsia_realizada,
        "removido_svo_iml": d.removido_svo_iml,
        "medico_atestante": d.medico_atestante,
        "medico_crm": d.medico_crm,
        "status": d.status,
        "observacoes": d.observacoes,
        "emitida_em": d.emitida_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.obito")
def api_declaracoes_obito(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        qs = pac.declaracoes_obito.all()[:50]
        return JsonResponse({"declaracoes": [_do_to_dict(d) for d in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    data_obito_str = data.get("data_obito", "")
    if not data_obito_str:
        return JsonResponse({"erro": "data_obito é obrigatória"}, status=400)

    from datetime import datetime
    try:
        data_obito = datetime.fromisoformat(data_obito_str)
    except ValueError:
        return JsonResponse({"erro": "data_obito inválida (use ISO 8601)"}, status=400)

    declaracao = DeclaracaoObito.objects.create(
        paciente=pac,
        numero_do=(data.get("numero_do") or "").strip(),
        data_obito=data_obito,
        local_obito=(data.get("local_obito") or "").strip(),
        tipo_morte=data.get("tipo_morte", "natural"),
        causa_imediata_cid=(data.get("causa_imediata_cid") or "").strip(),
        causa_imediata_descricao=(data.get("causa_imediata_descricao") or "").strip(),
        causa_intermediaria_cid=(data.get("causa_intermediaria_cid") or "").strip(),
        causa_intermediaria_descricao=(data.get("causa_intermediaria_descricao") or "").strip(),
        causa_basica_cid=(data.get("causa_basica_cid") or "").strip(),
        causa_basica_descricao=(data.get("causa_basica_descricao") or "").strip(),
        causas_contribuintes=(data.get("causas_contribuintes") or "").strip(),
        necropsia_realizada=bool(data.get("necropsia_realizada", False)),
        removido_svo_iml=bool(data.get("removido_svo_iml", False)),
        medico_atestante=(data.get("medico_atestante") or "").strip(),
        medico_crm=(data.get("medico_crm") or "").strip(),
        observacoes=(data.get("observacoes") or "").strip(),
    )

    pac.status = "obito"
    pac.save(update_fields=["status"])

    return JsonResponse({"ok": True, "declaracao": _do_to_dict(declaracao)}, status=201)
