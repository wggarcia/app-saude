"""
WhatsApp notification service for SolusCRT.

Supports:
  - Z-API  (https://developer.z-api.io/)
  - Evolution API (self-hosted / cloud)

Usage:
    from api.whatsapp_service import WhatsAppService
    svc = WhatsAppService(integracao)
    ok, erro = svc.enviar("5511999999999", "Texto da mensagem")
"""

import logging
from typing import Tuple, Optional

import requests

logger = logging.getLogger(__name__)

# Timeout para chamadas HTTP ao provedor
_HTTP_TIMEOUT = 10


class WhatsAppService:
    """Abstraction layer over Z-API / Evolution API."""

    def __init__(self, integracao):
        """
        :param integracao: IntegracaoWhatsApp model instance
        """
        self.integracao = integracao

    # ── Public interface ──────────────────────────────────────────────────────

    def enviar(self, numero: str, mensagem: str) -> Tuple[bool, Optional[str]]:
        """
        Envia uma mensagem de texto simples para *numero* (formato: 5511999999999).
        Retorna (True, None) em caso de sucesso ou (False, "motivo do erro").
        """
        numero = self._normalizar_numero(numero)
        if not numero:
            return False, "Número inválido"

        if not self.integracao.ativo:
            return False, "Integração WhatsApp inativa"

        provider = self.integracao.provider
        try:
            if provider == "z-api":
                return self._enviar_zapi(numero, mensagem)
            elif provider == "evolution":
                return self._enviar_evolution(numero, mensagem)
            else:
                return False, f"Provedor desconhecido: {provider}"
        except requests.exceptions.Timeout:
            return False, "Timeout ao conectar com o provedor WhatsApp"
        except requests.exceptions.ConnectionError as exc:
            return False, f"Erro de conexão: {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro inesperado ao enviar WhatsApp")
            return False, str(exc)

    def testar_conexao(self) -> Tuple[bool, str]:
        """Verifica se as credenciais estão corretas enviando uma requisição de status."""
        provider = self.integracao.provider
        try:
            if provider == "z-api":
                return self._status_zapi()
            elif provider == "evolution":
                return self._status_evolution()
            else:
                return False, f"Provedor desconhecido: {provider}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ── Z-API ─────────────────────────────────────────────────────────────────

    def _enviar_zapi(self, numero: str, mensagem: str) -> Tuple[bool, Optional[str]]:
        url = (
            f"https://api.z-api.io/instances/{self.integracao.instance_id}"
            f"/token/{self.integracao.token}/send-text"
        )
        payload = {"phone": numero, "message": mensagem}
        r = requests.post(url, json=payload, timeout=_HTTP_TIMEOUT)
        if r.status_code in (200, 201):
            data = r.json()
            if data.get("zaapId") or data.get("messageId"):
                return True, None
            return False, data.get("error", "Resposta inesperada da Z-API")
        return False, f"Z-API HTTP {r.status_code}: {r.text[:200]}"

    def _status_zapi(self) -> Tuple[bool, str]:
        url = (
            f"https://api.z-api.io/instances/{self.integracao.instance_id}"
            f"/token/{self.integracao.token}/status"
        )
        r = requests.get(url, timeout=_HTTP_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            connected = data.get("connected", False)
            smartphoneConnected = data.get("smartphoneConnected", False)
            if connected and smartphoneConnected:
                return True, "Conectado ✓"
            return False, "Instância desconectada — verifique o QR Code no Z-API"
        return False, f"Z-API HTTP {r.status_code}"

    # ── Evolution API ─────────────────────────────────────────────────────────

    def _enviar_evolution(self, numero: str, mensagem: str) -> Tuple[bool, Optional[str]]:
        base = (self.integracao.instance_id or "").rstrip("/")
        if not base.startswith("http"):
            return False, "Evolution API: instance_id deve ser a URL base (ex: https://seu-servidor.com)"
        url = f"{base}/message/sendText/{self.integracao.token}"
        payload = {
            "number": numero,
            "options": {"delay": 1200, "presence": "composing"},
            "textMessage": {"text": mensagem},
        }
        headers = {"apikey": self.integracao.token}
        r = requests.post(url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT)
        if r.status_code in (200, 201):
            return True, None
        return False, f"Evolution HTTP {r.status_code}: {r.text[:200]}"

    def _status_evolution(self) -> Tuple[bool, str]:
        base = (self.integracao.instance_id or "").rstrip("/")
        if not base.startswith("http"):
            return False, "Evolution API: instance_id deve ser a URL base"
        instance_name = self.integracao.numero_remetente or "SolusCRT"
        url = f"{base}/instance/connectionState/{instance_name}"
        headers = {"apikey": self.integracao.token}
        r = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            state = data.get("instance", {}).get("state", "unknown")
            if state == "open":
                return True, "Conectado ✓"
            return False, f"Evolution API estado: {state}"
        return False, f"Evolution API HTTP {r.status_code}"

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_numero(numero: str) -> str:
        """Remove caracteres não numéricos; garante DDI 55 para BR."""
        digits = "".join(c for c in (numero or "") if c.isdigit())
        if not digits:
            return ""
        # Adiciona DDI Brasil se ausente
        if len(digits) in (10, 11):
            digits = "55" + digits
        return digits


# ── Mensagens pré-formatadas ──────────────────────────────────────────────────

def msg_aso_vencendo(nome_func: str, dias: int, empresa: str) -> str:
    return (
        f"⚠️ *{empresa}* — SolusCRT SST\n\n"
        f"O ASO do(a) funcionário(a) *{nome_func}* vence em *{dias} dia(s)*.\n"
        "Agende o exame periódico com antecedência para manter a conformidade.\n\n"
        "_Mensagem automática — SolusCRT_"
    )


def msg_treinamento_vencendo(nome_func: str, treinamento: str, dias: int, empresa: str) -> str:
    return (
        f"📋 *{empresa}* — SolusCRT SST\n\n"
        f"O treinamento *{treinamento}* do(a) funcionário(a) *{nome_func}* "
        f"vence em *{dias} dia(s)*.\n"
        "Providencie a renovação para conformidade com as NRs.\n\n"
        "_Mensagem automática — SolusCRT_"
    )


def msg_epi_pendente(nome_func: str, epi: str, empresa: str) -> str:
    return (
        f"🦺 *{empresa}* — SolusCRT SST\n\n"
        f"O(a) funcionário(a) *{nome_func}* possui entrega de EPI pendente: *{epi}*.\n"
        "Regularize a entrega e obtenha a assinatura digital.\n\n"
        "_Mensagem automática — SolusCRT_"
    )


def msg_cat_registrada(nome_func: str, data_acidente: str, empresa: str) -> str:
    return (
        f"🚨 *{empresa}* — SolusCRT SST\n\n"
        f"CAT registrada para *{nome_func}* — acidente em *{data_acidente}*.\n"
        "Verifique o módulo CAT/Acidentes para acompanhamento e envio ao eSocial.\n\n"
        "_Mensagem automática — SolusCRT_"
    )


def msg_psicossocial_disponivel(avaliacao_titulo: str, empresa: str) -> str:
    return (
        f"🧠 *{empresa}* — SolusCRT SST\n\n"
        f"A avaliação psicossocial *{avaliacao_titulo}* está disponível para resposta.\n"
        "Incentive os colaboradores a participarem — prazo limitado.\n\n"
        "_Mensagem automática — SolusCRT_"
    )
