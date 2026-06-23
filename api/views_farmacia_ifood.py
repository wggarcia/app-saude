"""
Integração iFood (Merchant API) — pedidos de delivery por farmácia.

Cada farmácia conecta seu próprio estabelecimento (merchantId) com
credenciais próprias. O webhook é público (validado por assinatura por
tenant, igual ao padrão usado no webhook do Asaas) e cria/atualiza
PedidoDelivery automaticamente conforme o pedido avança no iFood.
"""
import hmac
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import IntegracaoIfood, PedidoDelivery
from .access_control import api_requer_gerencia, api_requer_feature

STATUS_MAP_IFOOD = {
    "PLACED": "aguardando",
    "CONFIRMED": "confirmado",
    "PREPARATION_STARTED": "em_preparo",
    "READY_TO_PICKUP": "em_preparo",
    "DISPATCHED": "saiu",
    "CONCLUDED": "entregue",
    "CANCELLED": "cancelado",
}


def _config_to_dict(c):
    return {
        "merchant_id": c.merchant_id,
        "client_id": c.client_id,
        "ativo": c.ativo,
        "conectado_em": c.conectado_em.isoformat() if c.conectado_em else None,
    }


@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.delivery")
def api_ifood_config(request):
    """GET/POST — configura a integração iFood da farmácia (merchantId, credenciais)."""
    empresa = request.empresa

    if request.method == "GET":
        config = IntegracaoIfood.objects.filter(empresa=empresa).first()
        return JsonResponse({"ok": True, "config": _config_to_dict(config) if config else None})

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    config, _criado = IntegracaoIfood.objects.get_or_create(empresa=empresa)
    if "merchant_id" in data:
        config.merchant_id = (data.get("merchant_id") or "").strip()
    if "client_id" in data:
        config.client_id = (data.get("client_id") or "").strip()
    if data.get("client_secret"):
        config.client_secret = data["client_secret"].strip()
    if data.get("webhook_signature_key"):
        config.webhook_signature_key = data["webhook_signature_key"].strip()

    config.ativo = bool(config.merchant_id and config.client_id and config.webhook_signature_key)
    config.conectado_em = timezone.now() if config.ativo and not config.conectado_em else config.conectado_em
    config.save()

    return JsonResponse({"ok": True, "config": _config_to_dict(config)})


@csrf_exempt
def api_ifood_webhook(request):
    """POST — webhook público do iFood. Identifica a farmácia pelo merchantId
    e valida a assinatura com a chave configurada por aquela farmácia."""
    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    merchant_id = str(data.get("merchantId") or "").strip()
    if not merchant_id:
        return JsonResponse({"erro": "merchantId ausente"}, status=400)

    config = IntegracaoIfood.objects.filter(merchant_id=merchant_id, ativo=True).select_related("empresa").first()
    if not config:
        return JsonResponse({"erro": "Estabelecimento não configurado"}, status=404)

    assinatura_esperada = (config.webhook_signature_key or "").strip()
    assinatura_recebida = (request.headers.get("x-ifood-signature") or "").strip()
    if not assinatura_esperada or not hmac.compare_digest(assinatura_esperada, assinatura_recebida):
        return JsonResponse({"erro": "Assinatura inválida"}, status=403)

    order_id = str(data.get("orderId") or "").strip()
    if not order_id:
        return JsonResponse({"erro": "orderId ausente"}, status=400)

    evento = str(data.get("code") or data.get("event") or "PLACED").strip().upper()
    novo_status = STATUS_MAP_IFOOD.get(evento, "aguardando")

    pedido_payload = data.get("order") or {}
    cliente = pedido_payload.get("customer") or {}
    endereco = pedido_payload.get("deliveryAddress") or {}

    pedido, criado = PedidoDelivery.objects.update_or_create(
        empresa=config.empresa,
        id_externo=order_id,
        defaults={
            "numero_pedido": pedido_payload.get("displayId") or order_id,
            "cliente_nome": cliente.get("name") or "Cliente iFood",
            "cliente_telefone": cliente.get("phone") or "",
            "cliente_endereco": endereco.get("formattedAddress") or "",
            "status": novo_status,
            "origem": "ifood",
            "total": pedido_payload.get("totalPrice") or 0,
        },
    )
    return JsonResponse({"ok": True, "pedido_id": pedido.id, "criado": criado})
