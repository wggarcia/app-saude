"""
TOTP (RFC 6238) em biblioteca padrão — sem dependência externa (pyotp/qrcode).

Compatível com Google Authenticator, Authy, Microsoft Authenticator e 1Password:
todos implementam o mesmo padrão HMAC-SHA1, passo de 30s, 6 dígitos.

Não geramos imagem de QR aqui (evita dependência). Entregamos a URI
`otpauth://` (que o app lê via QR renderizado no cliente) e o segredo em base32
para digitação manual — todo app autenticador aceita entrada manual.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def gerar_secret() -> str:
    """Segredo base32 de 160 bits (padrão recomendado pela RFC)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _codigo_no_tempo(secret_b32: str, momento: float, passo: int = 30, digitos: int = 6) -> str:
    # base32 sem padding precisa ser recompletado para múltiplo de 8
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    chave = base64.b32decode(secret_b32.upper() + pad, casefold=True)
    contador = int(momento // passo)
    msg = struct.pack(">Q", contador)
    h = hmac.new(chave, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    trecho = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(trecho % (10 ** digitos)).zfill(digitos)


def verificar(secret_b32: str, codigo: str, janela: int = 1) -> bool:
    """Valida um código TOTP com tolerância de ±`janela` passos (clock skew).
    Comparação em tempo constante contra timing attack."""
    codigo = (codigo or "").strip().replace(" ", "")
    if not codigo.isdigit() or not secret_b32:
        return False
    agora = time.time()
    for w in range(-janela, janela + 1):
        esperado = _codigo_no_tempo(secret_b32, agora + w * 30)
        if hmac.compare_digest(esperado, codigo):
            return True
    return False


def uri_otpauth(secret_b32: str, conta: str, emissor: str = "SoloCRT") -> str:
    """URI otpauth:// que o app autenticador consome (via QR ou manual)."""
    label = quote(f"{emissor}:{conta}")
    params = f"secret={secret_b32}&issuer={quote(emissor)}&algorithm=SHA1&digits=6&period=30"
    return f"otpauth://totp/{label}?{params}"


# ── Backup codes (recuperação quando o usuário perde o autenticador) ──────────

def gerar_backup_codes(qtd: int = 8) -> list[str]:
    """Códigos de uso único, formato legível (ex.: 'a1b2-c3d4')."""
    codes = []
    for _ in range(qtd):
        bruto = secrets.token_hex(4)  # 8 hex
        codes.append(f"{bruto[:4]}-{bruto[4:]}")
    return codes


def hash_backup(code: str) -> str:
    return hashlib.sha256((code or "").strip().lower().encode()).hexdigest()
