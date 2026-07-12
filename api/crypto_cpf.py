"""
Criptografia determinística de CPF usando AES-SIV (RFC 5297).

AES-SIV é determinístico: mesmo CPF + mesma chave → mesmo ciphertext.
Isso permite que filter(cpf='12345678901') continue funcionando nas views
sem nenhuma alteração — Django chama get_prep_value() no valor de busca,
que criptografa antes da query SQL, e o resultado bate com o valor no banco.

Usado exclusivamente via EncryptedCPFField — não chamar encrypt/decrypt
diretamente nas views.
"""
import base64
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from django.db import models

_DEV_KEY = "dev-cpf-nao-usar-em-producao-altere-via-CPF_ENCRYPTION_KEY"


def _get_key() -> bytes:
    """Deriva chave AES-SIV-512 (64 bytes) a partir de settings.CPF_ENCRYPTION_KEY."""
    from django.conf import settings
    raw = getattr(settings, "CPF_ENCRYPTION_KEY", _DEV_KEY) or _DEV_KEY
    return hashlib.sha512(raw.encode()).digest()  # 64 bytes → AES-256-SIV


def _is_encrypted(value: str) -> bool:
    # Texto puro: CPF tem no máximo 14 chars ("000.000.000-00").
    # Ciphertext AES-SIV de 11 bytes + 16 bytes tag = 27 bytes → base64 = 36 chars.
    return len(value) > 20


def encrypt_cpf(value: str) -> str:
    """Criptografa CPF. Idempotente — não re-criptografa valor já criptografado."""
    if not value:
        return value
    if _is_encrypted(value):
        return value
    aessiv = AESSIV(_get_key())
    ct = aessiv.encrypt(value.encode(), [])
    return base64.urlsafe_b64encode(ct).decode()


def decrypt_cpf(value: str) -> str:
    """Descriptografa CPF. Dados legados em texto puro são devolvidos sem modificação."""
    if not value:
        return value
    if not _is_encrypted(value):
        return value  # dado legado ainda em plaintext — retorna como está
    try:
        padding = (4 - len(value) % 4) % 4
        ct = base64.urlsafe_b64decode(value + "=" * padding)
        aessiv = AESSIV(_get_key())
        return aessiv.decrypt(ct, []).decode()
    except Exception:
        return value  # fallback seguro


class EncryptedCPFField(models.TextField):
    """
    Campo Django que armazena CPF cifrado com AES-SIV.
    Transparente nas views: leitura, escrita e filter() recebem/entregam
    texto puro. A criptografia acontece automaticamente na camada do ORM.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_cpf(value)

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            return value
        return str(value)

    def get_prep_value(self, value):
        """Chamado pelo ORM ao salvar E ao fazer filter() — criptografa o valor de busca."""
        if not value:
            return value
        return encrypt_cpf(value)
