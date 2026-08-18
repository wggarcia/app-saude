"""
sendgrid_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Envio de emails comerciais via SendGrid v3 API.

Não usa a biblioteca sendgrid — usa requests diretamente
para evitar nova dependência.

Configuração necessária no .env:
  SENDGRID_API_KEY=SG.xxxx
  EMAIL_COMERCIAL_FROM=comercial@solocrt.com
  EMAIL_COMERCIAL_NOME=Wagner Garcia - SoloCRT Saúde
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.utils import timezone as dj_tz

logger = logging.getLogger(__name__)

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def _get_config() -> dict:
    return {
        "api_key": getattr(settings, "SENDGRID_API_KEY", ""),
        "from_email": getattr(settings, "EMAIL_COMERCIAL_FROM", "comercial@solocrt.com"),
        "from_name": getattr(settings, "EMAIL_COMERCIAL_NOME", "Wagner Garcia — SoloCRT Saúde"),
    }


def enviar_email(email_comercial) -> bool:
    """
    Envia o EmailProspeccao via SendGrid.

    Atualiza email_comercial.status, enviado_em, sendgrid_message_id.
    Retorna True se enviado com sucesso, False caso contrário.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        email_comercial.status = "erro"
        email_comercial.erro = "SENDGRID_API_KEY não configurado. Configure no painel Render/VPS."
        email_comercial.save(update_fields=["status", "erro"])
        logger.error("sendgrid: API key ausente para lead %s", email_comercial.lead.email)
        return False

    lead = email_comercial.lead

    # Montar payload SendGrid v3
    payload = {
        "personalizations": [{
            "to": [{"email": lead.email, "name": lead.nome}],
            "subject": email_comercial.assunto,
        }],
        "from": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "reply_to": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "content": [
            {"type": "text/plain", "value": email_comercial.corpo_texto or _html_to_plain(email_comercial.corpo_html)},
            {"type": "text/html",  "value": _wrap_html(email_comercial.corpo_html, lead.nome)},
        ],
        "tracking_settings": {
            "click_tracking":  {"enable": True},
            "open_tracking":   {"enable": True},
        },
        "custom_args": {
            "email_comercial_id": str(email_comercial.id),
            "lead_id":            str(lead.id),
            "numero_sequencia":   str(email_comercial.numero_sequencia),
        },
    }

    try:
        resp = requests.post(
            SENDGRID_API_URL,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type":  "application/json",
            },
            data=json.dumps(payload),
            timeout=30,
        )

        if resp.status_code in (200, 202):
            message_id = resp.headers.get("X-Message-Id", "")
            email_comercial.status = "enviado"
            email_comercial.enviado_em = dj_tz.now()
            email_comercial.sendgrid_message_id = message_id
            email_comercial.erro = ""
            email_comercial.save(update_fields=["status", "enviado_em", "sendgrid_message_id", "erro"])
            logger.info("sendgrid: enviado seq=%s lead=%s msg_id=%s",
                        email_comercial.numero_sequencia, lead.email, message_id)
            return True
        else:
            erro = f"HTTP {resp.status_code}: {resp.text[:500]}"
            email_comercial.status = "erro"
            email_comercial.erro = erro
            email_comercial.save(update_fields=["status", "erro"])
            logger.error("sendgrid: erro ao enviar lead=%s: %s", lead.email, erro)
            return False

    except Exception as exc:
        email_comercial.status = "erro"
        email_comercial.erro = str(exc)[:500]
        email_comercial.save(update_fields=["status", "erro"])
        logger.error("sendgrid: exceção lead=%s: %s", lead.email, exc)
        return False


def enviar_email_transacional(to_email: str, to_nome: str, assunto: str, corpo_html: str) -> bool:
    """
    Envia um email avulso via SendGrid, sem depender de um LeadProspeccao/
    EmailProspeccao — usado para nutrição de trial (clientes reais em
    período de avaliação, não leads frios de prospecção).

    Retorna True se enviado com sucesso, False caso contrário. Não lança.
    """
    cfg = _get_config()
    if not cfg["api_key"]:
        logger.error("sendgrid: API key ausente para envio transacional a %s", to_email)
        return False

    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_nome}], "subject": assunto}],
        "from": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "reply_to": {"email": cfg["from_email"], "name": cfg["from_name"]},
        "content": [
            {"type": "text/plain", "value": _html_to_plain(corpo_html)},
            {"type": "text/html", "value": _wrap_html(corpo_html, to_nome, rodape=_RODAPE_CLIENTE)},
        ],
        "tracking_settings": {"click_tracking": {"enable": True}, "open_tracking": {"enable": True}},
    }

    try:
        resp = requests.post(
            SENDGRID_API_URL,
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
        if resp.status_code in (200, 202):
            logger.info("sendgrid: transacional enviado para %s", to_email)
            return True
        logger.error("sendgrid: erro transacional para %s: HTTP %s %s", to_email, resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        logger.error("sendgrid: exceção transacional para %s: %s", to_email, exc)
        return False


def processar_evento_webhook(payload: list) -> int:
    """
    Processa eventos do SendGrid (open, click, bounce, spam, unsubscribe).

    Retorna número de eventos processados.
    """
    from .models import EmailProspeccao, LeadProspeccao

    processados = 0
    for evento in payload:
        email_id = evento.get("email_comercial_id")
        if not email_id:
            continue

        try:
            em = EmailProspeccao.objects.select_related("lead").get(pk=int(email_id))
        except (EmailProspeccao.DoesNotExist, ValueError):
            continue

        tipo = evento.get("event", "")
        ts = evento.get("timestamp")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else dj_tz.now()

        if tipo == "open" and em.status not in ("clicado", "respondeu"):
            em.status = "aberto"
            em.aberto_em = dt
            em.save(update_fields=["status", "aberto_em"])
            if em.lead.status == "email_enviado":
                em.lead.status = "email_enviado"  # mantém; só marca respondeu quando há reply
                em.lead.save(update_fields=["status"])

        elif tipo == "click":
            em.status = "clicado"
            em.clicou_em = dt
            if not em.aberto_em:
                em.aberto_em = dt
            em.save(update_fields=["status", "clicou_em", "aberto_em"])

        elif tipo in ("bounce", "dropped"):
            em.status = "bounce"
            em.save(update_fields=["status"])
            em.lead.status = "bounce"
            em.lead.save(update_fields=["status"])

        elif tipo in ("spamreport", "unsubscribe"):
            em.status = "spam" if tipo == "spamreport" else "enviado"
            em.save(update_fields=["status"])
            em.lead.status = "unsubscribe"
            em.lead.save(update_fields=["status"])

        processados += 1

    return processados


_RODAPE_PROSPECCAO = (
    '<p>Você está recebendo este email porque seu contato está em nossa base de prospecção.</p>'
    '<p>Para não receber mais emails: <a href="{{unsubscribe}}">descadastrar</a></p>'
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
    import re
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<li>", "• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|h[1-6]|ul|ol)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
