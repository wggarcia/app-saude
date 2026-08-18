"""
brevo_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Envio de emails comerciais via Brevo (antigo Sendinblue) API v3.

Por quê Brevo e não SendGrid: SendGrid só é grátis por 60 dias (depois
US$19,95/mês mínimo). Brevo é grátis de verdade, sem prazo — 300
emails/dia (~9.000/mês), suficiente pro volume de prospecção + nutrição
de trial deste agente.

Configuração necessária no .env:
  BREVO_API_KEY=xkeysib-xxxx
  EMAIL_COMERCIAL_FROM=comercial@solocrt.com
  EMAIL_COMERCIAL_NOME=Wagner Garcia - SoloCRT Saúde

Webhook de eventos (abertura/clique/bounce) configurado no painel Brevo
apontando pra /api/comercial/webhook/eventos/.

Resposta de lead (Inbound Parse) exige domínio dedicado com MX apontando
pro Brevo (inbound1.sendinblue.com / inbound2.sendinblue.com) — configurar
depois, não bloqueia o envio funcionar.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.utils import timezone as dj_tz

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

_TAG_PREFIXO = "leadprospeccao_email_"


def _get_config() -> dict:
    return {
        "api_key": getattr(settings, "BREVO_API_KEY", ""),
        "from_email": getattr(settings, "EMAIL_COMERCIAL_FROM", "comercial@solocrt.com"),
        "from_name": getattr(settings, "EMAIL_COMERCIAL_NOME", "Wagner Garcia — SoloCRT Saúde"),
    }


def enviar_email(email_comercial) -> bool:
    """
    Envia o EmailProspeccao via Brevo.

    Atualiza email_comercial.status, enviado_em, provedor_message_id.
    Retorna True se enviado com sucesso, False caso contrário.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        email_comercial.status = "erro"
        email_comercial.erro = "BREVO_API_KEY não configurado. Configure no painel Render/VPS."
        email_comercial.save(update_fields=["status", "erro"])
        logger.error("brevo: API key ausente para lead %s", email_comercial.lead.email)
        return False

    lead = email_comercial.lead

    payload = {
        "sender": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "to": [{"email": lead.email, "name": lead.nome}],
        "replyTo": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "subject": email_comercial.assunto,
        "htmlContent": _wrap_html(email_comercial.corpo_html, lead.nome),
        "textContent": email_comercial.corpo_texto or _html_to_plain(email_comercial.corpo_html),
        "tags": [f"{_TAG_PREFIXO}{email_comercial.id}"],
    }

    try:
        resp = requests.post(
            BREVO_API_URL,
            headers={
                "api-key": cfg["api_key"],
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=json.dumps(payload),
            timeout=30,
        )

        if resp.status_code in (200, 201, 202):
            message_id = resp.json().get("messageId", "")
            email_comercial.status = "enviado"
            email_comercial.enviado_em = dj_tz.now()
            email_comercial.provedor_message_id = message_id
            email_comercial.erro = ""
            email_comercial.save(update_fields=["status", "enviado_em", "provedor_message_id", "erro"])
            logger.info("brevo: enviado seq=%s lead=%s msg_id=%s",
                        email_comercial.numero_sequencia, lead.email, message_id)
            return True
        else:
            erro = f"HTTP {resp.status_code}: {resp.text[:500]}"
            email_comercial.status = "erro"
            email_comercial.erro = erro
            email_comercial.save(update_fields=["status", "erro"])
            logger.error("brevo: erro ao enviar lead=%s: %s", lead.email, erro)
            return False

    except Exception as exc:
        email_comercial.status = "erro"
        email_comercial.erro = str(exc)[:500]
        email_comercial.save(update_fields=["status", "erro"])
        logger.error("brevo: exceção lead=%s: %s", lead.email, exc)
        return False


def enviar_email_transacional(to_email: str, to_nome: str, assunto: str, corpo_html: str) -> bool:
    """
    Envia um email avulso via Brevo, sem depender de um LeadProspeccao/
    EmailProspeccao — usado para nutrição de trial (clientes reais em
    período de avaliação, não leads frios de prospecção).

    Retorna True se enviado com sucesso, False caso contrário. Não lança.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        logger.error("brevo: API key ausente para envio transacional a %s", to_email)
        return False

    payload = {
        "sender": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "to": [{"email": to_email, "name": to_nome}],
        "replyTo": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "subject": assunto,
        "htmlContent": _wrap_html(corpo_html, to_nome, rodape=_RODAPE_CLIENTE),
        "textContent": _html_to_plain(corpo_html),
        "tags": ["nutricao_trial"],
    }

    try:
        resp = requests.post(
            BREVO_API_URL,
            headers={
                "api-key": cfg["api_key"],
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=json.dumps(payload),
            timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            logger.info("brevo: transacional enviado para %s", to_email)
            return True
        logger.error("brevo: erro transacional para %s: HTTP %s %s", to_email, resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        logger.error("brevo: exceção transacional para %s: %s", to_email, exc)
        return False


def processar_evento_webhook(payload: list) -> int:
    """
    Processa eventos do Brevo (opened, click, hard_bounce, spam, unsubscribed).

    Brevo manda 1 objeto por evento (não um array); o chamador
    (views_comercial.api_brevo_webhook) já normaliza payload único em
    lista de 1, então aqui sempre recebemos uma lista.

    Retorna número de eventos processados.
    """
    from .models import EmailProspeccao, LeadProspeccao

    processados = 0
    for evento in payload:
        tags = evento.get("tags", []) or []
        email_id = None
        for tag in tags:
            if tag.startswith(_TAG_PREFIXO):
                email_id = tag[len(_TAG_PREFIXO):]
                break
        if not email_id:
            continue

        try:
            em = EmailProspeccao.objects.select_related("lead").get(pk=int(email_id))
        except (EmailProspeccao.DoesNotExist, ValueError):
            continue

        tipo = evento.get("event", "")
        ts = evento.get("ts_event") or evento.get("ts")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else dj_tz.now()

        if tipo == "opened" and em.status not in ("clicado", "respondeu"):
            em.status = "aberto"
            em.aberto_em = dt
            em.save(update_fields=["status", "aberto_em"])

        elif tipo == "click":
            em.status = "clicado"
            em.clicou_em = dt
            if not em.aberto_em:
                em.aberto_em = dt
            em.save(update_fields=["status", "clicou_em", "aberto_em"])

        elif tipo in ("hard_bounce", "soft_bounce", "blocked", "invalid_email"):
            em.status = "bounce"
            em.save(update_fields=["status"])
            em.lead.status = "bounce"
            em.lead.save(update_fields=["status"])

        elif tipo in ("spam", "unsubscribed"):
            em.status = "spam" if tipo == "spam" else "enviado"
            em.save(update_fields=["status"])
            em.lead.status = "unsubscribe"
            em.lead.save(update_fields=["status"])

        processados += 1

    return processados


_RODAPE_PROSPECCAO = (
    '<p>Você está recebendo este email porque seu contato está em nossa base de prospecção.</p>'
    '<p>SoloCRT Saúde | solocrt.com.br | comercial@solocrt.com</p>'
)
_RODAPE_CLIENTE = (
    '<p>Você está recebendo este email porque sua empresa tem uma conta no SoloCRT Saúde.</p>'
    '<p>SoloCRT Saúde | solocrt.com.br | comercial@solocrt.com</p>'
)


def _wrap_html(corpo: str, nome_lead: str, rodape: str = _RODAPE_PROSPECCAO) -> str:
    """Envolve o corpo em template HTML básico de email."""
    if "<html" in corpo.lower():
        return corpo
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 15px; color: #222; line-height: 1.6; margin: 0; padding: 0; background: #f5f5f5; }}
    .container {{ max-width: 600px; margin: 20px auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
    .header {{ background: #1a56db; padding: 20px 30px; }}
    .header h1 {{ color: #fff; margin: 0; font-size: 20px; font-weight: 600; }}
    .header p {{ color: #b3c9ff; margin: 4px 0 0; font-size: 13px; }}
    .body {{ padding: 28px 30px; }}
    .footer {{ background: #f9f9f9; padding: 16px 30px; border-top: 1px solid #eee; font-size: 12px; color: #888; }}
    .footer a {{ color: #1a56db; text-decoration: none; }}
    ul {{ padding-left: 20px; }}
    li {{ margin-bottom: 6px; }}
    strong {{ color: #111; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>SoloCRT Saúde</h1>
      <p>solocrt.com.br — Gestão inteligente para saúde</p>
    </div>
    <div class="body">
      {corpo}
    </div>
    <div class="footer">
      {rodape}
    </div>
  </div>
</body>
</html>"""


def _html_to_plain(html: str) -> str:
    """Converte HTML simples para texto puro."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<li>", "• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|h[1-6]|ul|ol)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
