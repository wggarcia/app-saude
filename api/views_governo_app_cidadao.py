"""
views_governo_app_cidadao.py
App Cidadão — envio de alertas/campanhas de saúde pública para a população
cadastrada (ProntuarioCidadao), com segmentação real por microárea/unidade.
"""
import json
from datetime import datetime

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_feature, get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .models import AlertaCidadao, ProntuarioCidadao
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.vigilancia_acs")
def governo_app_cidadao_page(request):
    return render(request, "governo_app_cidadao.html", contexto_navegacao_setorial(request, "governo"))


def _estimar_destinatarios(empresa, publico_alvo, microarea_filtro, unidade_filtro):
    qs = ProntuarioCidadao.objects.filter(empresa=empresa)
    if publico_alvo == "por_microarea" and microarea_filtro:
        qs = qs.filter(microarea=microarea_filtro)
    elif publico_alvo == "por_unidade" and unidade_filtro:
        qs = qs.filter(unidade_saude=unidade_filtro)
    return qs.exclude(telefone="").count()


def _alerta_dict(a):
    return {
        "id": a.id, "titulo": a.titulo, "mensagem": a.mensagem,
        "tipo": a.tipo, "tipo_label": dict(AlertaCidadao.TIPO_CHOICES).get(a.tipo, a.tipo),
        "publico_alvo": a.publico_alvo, "publico_label": dict(AlertaCidadao.PUBLICO_CHOICES).get(a.publico_alvo, a.publico_alvo),
        "microarea_filtro": a.microarea_filtro, "unidade_filtro": a.unidade_filtro,
        "status": a.status, "total_destinatarios_estimado": a.total_destinatarios_estimado,
        "enviado_por": a.enviado_por,
        "enviado_em": a.enviado_em.isoformat() if a.enviado_em else None,
        "criado_em": a.criado_em.isoformat(),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("governo.app_cidadao")
def api_alertas_cidadao(request):
    """GET /api/governo/app-cidadao/alertas/ — lista. POST — cria rascunho."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = AlertaCidadao.objects.filter(empresa=e)
        status_filtro = request.GET.get("status")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        return JsonResponse({"alertas": [_alerta_dict(a) for a in qs[:200]]})

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    titulo = (body.get("titulo") or "").strip()
    mensagem = (body.get("mensagem") or "").strip()
    if not titulo or not mensagem:
        return JsonResponse({"erro": "Título e mensagem são obrigatórios"}, status=400)

    publico_alvo = body.get("publico_alvo") or "todos"
    microarea_filtro = (body.get("microarea_filtro") or "").strip()
    unidade_filtro = (body.get("unidade_filtro") or "").strip()
    destinatarios = _estimar_destinatarios(e, publico_alvo, microarea_filtro, unidade_filtro)

    alerta = AlertaCidadao.objects.create(
        empresa=e, titulo=titulo, mensagem=mensagem,
        tipo=body.get("tipo") or "informativo",
        publico_alvo=publico_alvo, microarea_filtro=microarea_filtro, unidade_filtro=unidade_filtro,
        total_destinatarios_estimado=destinatarios,
    )
    return JsonResponse({"ok": True, "alerta": _alerta_dict(alerta)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("governo.app_cidadao")
def api_alerta_cidadao_enviar(request, alerta_id):
    """POST /api/governo/app-cidadao/alertas/<id>/enviar/ — confirma envio à população segmentada."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        alerta = AlertaCidadao.objects.get(pk=alerta_id, empresa=e)
    except AlertaCidadao.DoesNotExist:
        return JsonResponse({"erro": "Alerta não encontrado"}, status=404)

    if alerta.status == "enviado":
        return JsonResponse({"erro": "Alerta já foi enviado"}, status=400)

    alerta.total_destinatarios_estimado = _estimar_destinatarios(
        e, alerta.publico_alvo, alerta.microarea_filtro, alerta.unidade_filtro
    )
    alerta.status = "enviado"
    alerta.enviado_em = timezone.now()
    principal = getattr(request, "principal", None)
    alerta.enviado_por = getattr(principal, "nome", None) or getattr(principal, "email", "") or e.nome
    alerta.save()

    return JsonResponse({
        "ok": True,
        "alerta": _alerta_dict(alerta),
        "aviso": (
            "Alerta marcado como enviado e contabilizado para "
            f"{alerta.total_destinatarios_estimado} cidadão(s) com telefone cadastrado. "
            "A entrega efetiva via SMS/push depende de gateway de telecom contratado pelo município "
            "(não incluso nesta versão)."
        ),
    })


@api_requer_feature("governo.app_cidadao")
def api_app_cidadao_kpis(request):
    """GET /api/governo/app-cidadao/kpis/"""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    total_cidadaos = ProntuarioCidadao.objects.filter(empresa=e).exclude(telefone="").count()
    alertas = AlertaCidadao.objects.filter(empresa=e)
    por_tipo = list(
        alertas.filter(status="enviado").values("tipo").annotate(total=Count("id")).order_by("-total")
    )
    for item in por_tipo:
        item["tipo_label"] = dict(AlertaCidadao.TIPO_CHOICES).get(item["tipo"], item["tipo"])

    return JsonResponse({
        "total_cidadaos_alcancaveis": total_cidadaos,
        "total_alertas_enviados": alertas.filter(status="enviado").count(),
        "total_rascunhos": alertas.filter(status="rascunho").count(),
        "por_tipo_enviado": por_tipo,
    })
