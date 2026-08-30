"""
Campo de texto cifrado em repouso (Fernet) — para blobs sensíveis que NUNCA
são consultados por valor: certificados ICP-Brasil (PKCS#12), chaves privadas,
tokens longos.

Diferente do EncryptedCPFField (AES-SIV determinístico, para permitir filter=):
aqui usamos Fernet (não-determinístico, com HMAC + timestamp) porque não há
necessidade de busca — só de sigilo em repouso.

Transparente na camada ORM: as views continuam lendo/gravando o base64 em
texto puro; a cifra acontece em get_prep_value/from_db_value.

Retrocompatível: valores legados ainda em texto puro (não-Fernet) são devolvidos
como estão na leitura e re-cifrados no próximo save (a migration de dados força
esse re-save para não deixar nada em claro).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.db import models


def _fernet() -> Fernet:
    """Fernet derivado do SECRET_KEY — mesma raiz já usada para as senhas de
    integração em CredenciaisIntegracoes._fernet(), para consistência de chave."""
    from django.conf import settings
    chave = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def encrypt_text(value: str) -> str:
    """Cifra texto. Idempotente: valor já cifrado (Fernet válido) não é re-cifrado."""
    if not value:
        return value
    if _is_encrypted(value):
        return value
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(value: str) -> str:
    """Decifra. Valor legado em texto puro é devolvido sem modificação."""
    if not value:
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return value  # legado em claro (ou não-Fernet) — devolve como está


def _is_encrypted(value: str) -> bool:
    """True se `value` é um token Fernet válido para a nossa chave."""
    if not value or not isinstance(value, str):
        return False
    try:
        _fernet().decrypt(value.encode())
        return True
    except (InvalidToken, ValueError, TypeError):
        return False


class EncryptedTextField(models.TextField):
    """TextField cifrado em repouso com Fernet. Transparente para as views."""

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_text(value)

    def to_python(self, value):
        if value is None or not isinstance(value, str):
            return value
        # to_python pode receber valor do banco (cifrado) ou já em claro
        return decrypt_text(value)

    def get_prep_value(self, value):
        if not value:
            return value
        return encrypt_text(value)
