"""
WhatsApp Integration — API views.

GET  /api/gestao/whatsapp/           → retorna configuração
POST /api/gestao/whatsapp/           → salva configuração
POST /api/gestao/whatsapp/testar/    → testa conexão com provedor
POST /api/gestao/whatsapp/enviar/    → envia mensagem manual de teste
GET  /api/gestao/whatsapp/logs/      → histórico de envios
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.access_control import api_requer_gerencia
from api.models import IntegracaoWhatsApp, LogWhatsApp
from api.whatsapp_service import WhatsAppService


@csrf_exempt
@api_requer_gerencia
def api_whatsapp(request):
    """GET retorna configuração; POST salva configuração."""
    empresa = request.empresa

    if request.method == "GET":
        return _get_whatsapp(empresa)

    if request.method == "POST":
        return _post_whatsapp(request, empresa)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


def _get_whatsapp(empresa):
    try:
        cfg = empresa.integracao_whatsapp
    except IntegracaoWhatsApp.DoesNotExist:
        return JsonResponse({
            "provider": "z-api",
            "instance_id": "",
            "token": "",
            "numero_remetente": "",
            "ativo": False,
            "notif_aso": True,
            "notif_treinamento": True,
            "notif_epi": True,
            "notif_cat": True,
            "notif_psicossocial": True,
        })

    return JsonResponse({
        "provider": cfg.provider,
        "instance_id": cfg.instance_id,
        # Não retornamos o token completo por segurança — apenas máscara
        "token": ("*" * max(0, len(cfg.token) - 4) + cfg.token[-4:]) if cfg.token else "",
        "token_configurado": bool(cfg.token),
        "numero_remetente": cfg.numero_remetente,
        "ativo": cfg.ativo,
        "notif_aso": cfg.notif_aso,
        "notif_treinamento": cfg.notif_treinamento,
        "notif_epi": cfg.notif_epi,
        "notif_cat": cfg.notif_cat,
        "notif_psicossocial": cfg.notif_psicossocial,
    })


def _post_whatsapp(request, empresa):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cfg, _ = IntegracaoWhatsApp.objects.get_or_create(empresa=empresa)

    cfg.provider = body.get("provider", cfg.provider)
    cfg.instance_id = (body.get("instance_id") or "").strip()
    cfg.numero_remetente = (body.get("numero_remetente") or "").strip()
    cfg.ativo = bool(body.get("ativo", cfg.ativo))
    cfg.notif_aso = bool(body.get("notif_aso", True))
    cfg.notif_treinamento = bool(body.get("notif_treinamento", True))
    cfg.notif_epi = bool(body.get("notif_epi", True))
    cfg.notif_cat = bool(body.get("notif_cat", True))
    cfg.notif_psicossocial = bool(body.get("notif_psicossocial", True))

    # Token: só atualiza se enviado e não for máscara
    novo_token = (body.get("token") or "").strip()
    if novo_token and not novo_token.startswith("*"):
        cfg.token = novo_token

    cfg.save()
    return JsonResponse({"status": "ok", "mensagem": "Configuração WhatsApp salva com sucesso."})


@csrf_exempt
@api_requer_gerencia
def api_whatsapp_testar(request):
    """POST — testa a conexão com o provedor configurado."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = request.empresa
    try:
        cfg = empresa.integracao_whatsapp
    except IntegracaoWhatsApp.DoesNotExist:
        return JsonResponse({"erro": "Nenhuma integração configurada ainda."}, status=400)

    if not cfg.instance_id or not cfg.token:
        return JsonResponse({"erro": "Preencha Instance ID e Token antes de testar."}, status=400)

    svc = WhatsAppService(cfg)
    ok, msg = svc.testar_conexao()
    if ok:
        return JsonResponse({"status": "ok", "mensagem": msg or "Conexão estabelecida com sucesso!"})
    return JsonResponse({"erro": msg or "Falha ao conectar com o provedor."}, status=400)


@csrf_exempt
@api_requer_gerencia
def api_whatsapp_enviar(request):
    """POST — envia mensagem de teste manual para um número."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = request.empresa
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    numero = (body.get("numero") or "").strip()
    mensagem = (body.get("mensagem") or "").strip()

    if not numero:
        return JsonResponse({"erro": "Informe o número de destino."}, status=400)
    if not mensagem:
        mensagem = f"✅ Teste de integração WhatsApp — SolusCRT · {empresa.nome}"

    try:
        cfg = empresa.integracao_whatsapp
    except IntegracaoWhatsApp.DoesNotExist:
        return JsonResponse({"erro": "Nenhuma integração configurada."}, status=400)

    svc = WhatsAppService(cfg)
    ok, erro = svc.enviar(numero, mensagem)

    status_log = LogWhatsApp.STATUS_OK if ok else LogWhatsApp.STATUS_ERRO
    LogWhatsApp.objects.create(
        empresa=empresa,
        numero_destino=numero,
        mensagem=mensagem,
        evento="manual_teste",
        status=status_log,
        resposta_api={"erro": erro} if erro else {},
    )

    if ok:
        return JsonResponse({"status": "ok", "mensagem": f"Mensagem enviada para {numero}."})
    return JsonResponse({"erro": erro or "Falha ao enviar mensagem."}, status=400)


@csrf_exempt
@api_requer_gerencia
def api_whatsapp_logs(request):
    """GET — retorna últimos 50 logs de envio."""
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = request.empresa
    logs = (
        LogWhatsApp.objects
        .filter(empresa=empresa)
        .order_by("-enviado_em")[:50]
    )

    return JsonResponse({
        "logs": [
            {
                "id": log.id,
                "numero_destino": log.numero_destino,
                "mensagem": log.mensagem[:120] + ("…" if len(log.mensagem) > 120 else ""),
                "evento": log.evento,
                "status": log.status,
                "enviado_em": log.enviado_em.strftime("%d/%m/%Y %H:%M"),
            }
            for log in logs
        ]
    })
