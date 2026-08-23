"""
biometria_token.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Selo biométrico de rede (VITA OS — Fase 2b)

Prova portátil e SEM PII de que um paciente foi reconhecido por biometria
facial num hospital SoloCRT. Viaja junto da guia TISS até a operadora, que
valida a assinatura e marca a guia como "verificada por biometria".

- Assinado com HMAC-SHA256 (segredo de rede) → operadora confia sem cruzar
  banco com o hospital (respeita isolamento de segmento / LGPD).
- Não carrega CPF em claro: apenas um hash truncado, suficiente para conferir
  que o token corresponde ao beneficiário da guia, sem expor o documento.
- Tem validade (expira), evitando reuso de tokens antigos.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from django.conf import settings

_VALIDADE_SEGUNDOS = 60 * 60 * 24 * 2   # token vale 48h (janela de envio da guia)


def _segredo() -> bytes:
    """Segredo de rede — dedicado se definido, senão deriva do SECRET_KEY."""
    base = getattr(settings, "VITA_NETWORK_SECRET", "") or settings.SECRET_KEY
    return hashlib.sha256(("vita-biometria::" + base).encode("utf-8")).digest()


def hash_cpf(cpf: str) -> str:
    """Hash truncado do CPF (sem expor o documento no token)."""
    cpf_limpo = "".join(c for c in (cpf or "") if c.isdigit())
    if not cpf_limpo:
        return ""
    dig = hashlib.sha256((cpf_limpo + "::" + _segredo().hex()).encode("utf-8")).hexdigest()
    return dig[:16]


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def gerar_token(checkin_id: int, empresa_id: int, cpf: str, score: float, agora: float | None = None) -> str:
    """
    Gera o token biométrico assinado para um check-in verificado.
    Formato: <payload_b64>.<assinatura_b64>
    """
    payload = {
        "cid":  checkin_id,
        "eid":  empresa_id,          # hospital de origem
        "cpfh": hash_cpf(cpf),
        "sc":   round(float(score or 0), 3),
        "ts":   int(agora if agora is not None else time.time()),
        "v":    1,
    }
    corpo = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    assinatura = hmac.new(_segredo(), corpo.encode("ascii"), hashlib.sha256).digest()
    return f"{corpo}.{_b64e(assinatura)}"


def validar_token(token: str, cpf_esperado: str | None = None, agora: float | None = None) -> dict | None:
    """
    Valida o token: assinatura correta, não expirado e (opcional) CPF confere.
    Retorna o payload (dict) se válido, senão None. Nunca lança.
    """
    try:
        corpo, assinatura = token.strip().split(".", 1)
        esperada = hmac.new(_segredo(), corpo.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(assinatura), esperada):
            return None
        payload = json.loads(_b64d(corpo).decode("utf-8"))
        agora = agora if agora is not None else time.time()
        if agora - payload.get("ts", 0) > _VALIDADE_SEGUNDOS:
            return None  # expirado
        if cpf_esperado is not None and payload.get("cpfh") != hash_cpf(cpf_esperado):
            return None  # token não corresponde a este beneficiário
        return payload
    except Exception:
        return None
