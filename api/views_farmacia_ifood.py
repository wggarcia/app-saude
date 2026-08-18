"""
Integração iFood (Merchant API) — pedidos de delivery por farmácia.

Cada farmácia conecta seu próprio estabelecimento (merchantId) com
credenciais próprias. O webhook é público (validado por assinatura por
tenant, igual ao padrão usado no webhook do Asaas) e cria/atualiza
PedidoDelivery automaticamente conforme o pedido avança no iFood.
"""
import hmac
import json
import time as _time
from decimal import Decimal, InvalidOperation

import requests

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import IntegracaoIfood, PedidoDelivery, ItemPedidoDelivery, MedicamentoFarmacia
from .views_farmacia_ecommerce import baixar_estoque_pedido, STATUS_CONFIRMA_BAIXA
from .access_control import api_requer_gerencia, api_requer_feature


# ─── iFood OAuth 2.0 — token cache em memória ─────────────────────────────────

_IFOOD_TOKEN_CACHE: dict = {}  # {config_pk: {"token": str, "expires_at": float}}


def _ifood_get_token(config):
    """Obtém token OAuth2 do iFood Merchant API, com cache em memória."""
    cache = _IFOOD_TOKEN_CACHE.get(config.pk)
    if cache and cache["expires_at"] > _time.time() + 30:
        return cache["token"]
    try:
        resp = requests.post(
            "https://merchant-api.ifood.com.br/authentication/v1.0/oauth/token",
            data={
                "grantType": "client_credentials",
                "clientId": config.client_id,
                "clientSecret": config.client_secret,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            _IFOOD_TOKEN_CACHE[config.pk] = {
                "token": data.get("accessToken", ""),
                "expires_at": _time.time() + data.get("expiresIn", 3600),
            }
            return data.get("accessToken", "")
    except Exception:
        pass
    return None


def _ifood_ack_events(config, event_ids):
    """Confirma recebimento de eventos ao iFood (acknowledgment)."""
    if not event_ids:
        return
    try:
        token = _ifood_get_token(config)
        if not token:
            return
        requests.post(
            "https://merchant-api.ifood.com.br/order/v1.0/events/acknowledgment",
            json=[{"id": eid} for eid in event_ids],
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
    except Exception:
        pass  # Não-fatal: iFood reenvia o evento caso não receba ack


def _ifood_confirm_order(config, order_id):
    """Envia confirmação de aceite do pedido ao iFood."""
    try:
        token = _ifood_get_token(config)
        if not token:
            return
        requests.post(
            f"https://merchant-api.ifood.com.br/order/v1.0/orders/{order_id}/statuses/confirm",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception:
        pass


# ─── Helpers gerais ───────────────────────────────────────────────────────────

def _decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default

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

    # Coleta o ID deste evento para acknowledgment ao final
    event_id = str(data.get("id") or "").strip()

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

    # Sincroniza os itens uma única vez (na primeira vez que o payload traz a
    # lista). Cada item é casado com o catálogo MedicamentoFarmacia da farmácia
    # por EAN (código de barras); itens sem correspondência ficam registrados
    # mas não baixam estoque.
    itens_payload = pedido_payload.get("items") or []
    if isinstance(itens_payload, list) and itens_payload and not pedido.itens.exists():
        for it in itens_payload:
            ean = str(it.get("ean") or it.get("externalCode") or "").strip()
            med = None
            if ean:
                med = MedicamentoFarmacia.objects.filter(
                    empresa=config.empresa, codigo_barras=ean, ativo=True,
                ).first()
            quantidade = _decimal(it.get("quantity") or 1)
            preco_unitario = _decimal(it.get("unitPrice") or it.get("price") or 0)
            ItemPedidoDelivery.objects.create(
                pedido=pedido,
                empresa=config.empresa,
                medicamento=med,
                descricao=(it.get("name") or "").strip(),
                codigo_barras=ean,
                quantidade=quantidade,
                preco_unitario=preco_unitario,
                total_item=quantidade * preco_unitario,
            )

    # Baixa de estoque quando o pedido é confirmado no iFood (uma única vez).
    if novo_status in STATUS_CONFIRMA_BAIXA and not pedido.estoque_baixado:
        baixar_estoque_pedido(pedido)
        pedido.refresh_from_db()

    # ── iFood outbound: acknowledgment e confirmação de pedido ────────────────
    # Acknowledgment informa ao iFood que o evento foi recebido com sucesso.
    processed_event_ids = [event_id] if event_id else []
    _ifood_ack_events(config, processed_event_ids)

    # Confirmação de aceite enviada quando o evento resulta em CONFIRMED ou
    # quando o pedido é recém-criado via PLACED (iFood aguarda nosso aceite).
    if evento == "CONFIRMED" or (criado and evento == "PLACED"):
        _ifood_confirm_order(config, order_id)

    return JsonResponse({"ok": True, "pedido_id": pedido.id, "criado": criado})
