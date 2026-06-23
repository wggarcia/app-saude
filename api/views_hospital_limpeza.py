"""
Hospital — Limpeza/Liberação de Leito e Rouparia
  • Controle de higienização do leito (giro de leito)
  • Registro de entrega/coleta de roupa hospitalar
"""
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_feature
from .models import LeitoHospitalar, RegistroLimpezaLeito, RegistroRouparia
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


def _limpeza_to_dict(r):
    return {
        "id": r.id,
        "leito_id": r.leito_id,
        "leito_numero": r.leito.numero,
        "status": r.status,
        "tipo_limpeza": r.tipo_limpeza,
        "responsavel": r.responsavel,
        "iniciada_em": r.iniciada_em.strftime("%d/%m/%Y %H:%M"),
        "concluida_em": r.concluida_em.strftime("%d/%m/%Y %H:%M") if r.concluida_em else None,
        "observacoes": r.observacoes,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.limpeza")
def api_limpeza_leito(request, leito_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    leito = LeitoHospitalar.objects.filter(pk=leito_id, empresa=empresa).first()
    if not leito:
        return JsonResponse({"erro": "Leito não encontrado"}, status=404)

    if request.method == "GET":
        qs = leito.registros_limpeza.all()[:50]
        return JsonResponse({"registros": [_limpeza_to_dict(r) for r in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    registro = RegistroLimpezaLeito.objects.create(
        leito=leito,
        status=data.get("status", "sujo"),
        tipo_limpeza=data.get("tipo_limpeza", "concorrente"),
        responsavel=(data.get("responsavel") or "").strip(),
        observacoes=(data.get("observacoes") or "").strip(),
    )
    return JsonResponse({"ok": True, "registro": _limpeza_to_dict(registro)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_feature("hospital.limpeza")
def api_limpeza_status(request, registro_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    registro = RegistroLimpezaLeito.objects.select_related("leito").filter(
        pk=registro_id, leito__empresa=empresa,
    ).first()
    if not registro:
        return JsonResponse({"erro": "Registro não encontrado"}, status=404)

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    novo_status = data.get("status")
    if novo_status not in dict(RegistroLimpezaLeito.STATUS_CHOICES):
        return JsonResponse({"erro": "status inválido"}, status=400)

    registro.status = novo_status
    if novo_status in ("limpo", "interditado"):
        registro.concluida_em = timezone.now()
    registro.save()

    return JsonResponse({"ok": True, "registro": _limpeza_to_dict(registro)})


def _rouparia_to_dict(r):
    return {
        "id": r.id,
        "leito_id": r.leito_id,
        "leito_numero": r.leito.numero if r.leito else "",
        "setor": r.setor,
        "tipo": r.tipo,
        "quantidade_pecas": r.quantidade_pecas,
        "responsavel": r.responsavel,
        "registrado_em": r.registrado_em.strftime("%d/%m/%Y %H:%M"),
        "observacoes": r.observacoes,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.limpeza")
def api_rouparia(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    if request.method == "GET":
        qs = RegistroRouparia.objects.filter(empresa=empresa).select_related("leito")[:200]
        return JsonResponse({"registros": [_rouparia_to_dict(r) for r in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    leito = None
    if data.get("leito_id"):
        leito = LeitoHospitalar.objects.filter(pk=data["leito_id"], empresa=empresa).first()

    registro = RegistroRouparia.objects.create(
        empresa=empresa,
        leito=leito,
        setor=(data.get("setor") or "").strip(),
        tipo=data.get("tipo", "entrega_limpa"),
        quantidade_pecas=data.get("quantidade_pecas", 0),
        responsavel=(data.get("responsavel") or "").strip(),
        observacoes=(data.get("observacoes") or "").strip(),
    )
    return JsonResponse({"ok": True, "registro": _rouparia_to_dict(registro)}, status=201)
