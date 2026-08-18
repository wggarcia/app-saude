"""
notificacao_comercial.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Notifica o dono do negócio quando um lead responde ou pede demo.

Canal: WhatsApp via CallMeBot (grátis, sem servidor próprio).
Cadastro em: https://www.callmebot.com/blog/free-api-whatsapp-messages/

Configuração no .env:
  WHATSAPP_NOTIFY_PHONE=5511999999999   (com DDI, só dígitos)
  WHATSAPP_CALLMEBOT_APIKEY=123456

Se não configurado, apenas registra em log — nunca quebra o fluxo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def notificar_resposta(lead, contexto: str = "respondeu") -> bool:
    """
    Envia notificação WhatsApp avisando que um lead avançou no funil.

    `contexto` é um texto curto: 'respondeu', 'pediu demo', etc.
    Retorna True se a mensagem foi despachada, False caso contrário.
    Nunca lança — falha de notificação não pode derrubar o webhook/endpoint.
    """
    mensagem = (
        f"🔔 SoloCRT — Lead {contexto}!\n\n"
        f"👤 {lead.nome}\n"
        f"🏢 {lead.empresa}\n"
        f"📧 {lead.email}\n"
        f"📱 {lead.telefone or 'sem telefone'}\n"
        f"📍 {lead.cidade}/{lead.estado}\n"
        f"🏷️ {lead.get_segmento_display()} — {lead.get_tipo_display()}\n\n"
        f"➡️ Abra o painel: /comercial/"
    )
    return _enviar_whatsapp(mensagem)


def _enviar_whatsapp(mensagem: str) -> bool:
    phone = getattr(settings, "WHATSAPP_NOTIFY_PHONE", "")
    apikey = getattr(settings, "WHATSAPP_CALLMEBOT_APIKEY", "")

    if not phone or not apikey:
        logger.info("notificacao_comercial: WhatsApp não configurado — pulando (mensagem: %s)",
                    mensagem.split(chr(10))[0])
        return False

    try:
        resp = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": phone, "text": mensagem, "apikey": apikey},
            timeout=15,
        )
        ok = resp.status_code == 200
        if ok:
            logger.info("notificacao_comercial: WhatsApp enviado para %s", phone)
        else:
            logger.warning("notificacao_comercial: CallMeBot HTTP %s: %s",
                           resp.status_code, resp.text[:200])
        return ok
    except Exception as exc:
        logger.error("notificacao_comercial: erro ao enviar WhatsApp: %s", exc)
        return False
