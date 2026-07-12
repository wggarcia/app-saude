"""
Migração 0134 — Criptografia AES-SIV do campo CPF em FuncionarioSST.

1. Altera o campo de CharField(max_length=14) para TextField (o ciphertext
   tem ~36 chars, maior que o limite anterior).
2. Criptografa todos os CPFs existentes no banco usando a mesma lógica
   de api.crypto_cpf — idempotente, não re-criptografa valores já cifrados.
"""
import base64
import hashlib

from django.db import migrations, models


def _derive_key():
    import os
    from django.conf import settings
    raw = getattr(settings, "CPF_ENCRYPTION_KEY", "") or os.environ.get("CPF_ENCRYPTION_KEY", "")
    if not raw:
        raw = "dev-cpf-nao-usar-em-producao-altere-via-CPF_ENCRYPTION_KEY"
    return hashlib.sha512(raw.encode()).digest()


def encrypt_existing_cpfs(apps, schema_editor):
    from cryptography.hazmat.primitives.ciphers.aead import AESSIV

    FuncionarioSST = apps.get_model("api", "FuncionarioSST")
    key = _derive_key()
    aessiv = AESSIV(key)

    to_update = []
    for func in FuncionarioSST.objects.exclude(cpf="").only("id", "cpf"):
        if len(func.cpf) > 20:
            continue  # já criptografado
        ct = aessiv.encrypt(func.cpf.encode(), [])
        func.cpf = base64.urlsafe_b64encode(ct).decode()
        to_update.append(func)

    if to_update:
        FuncionarioSST.objects.bulk_update(to_update, ["cpf"], batch_size=500)


def decrypt_existing_cpfs(apps, schema_editor):
    """Reverse: descriptografa CPFs de volta para texto puro."""
    from cryptography.hazmat.primitives.ciphers.aead import AESSIV

    FuncionarioSST = apps.get_model("api", "FuncionarioSST")
    key = _derive_key()
    aessiv = AESSIV(key)

    to_update = []
    for func in FuncionarioSST.objects.exclude(cpf="").only("id", "cpf"):
        if len(func.cpf) <= 20:
            continue  # já é texto puro
        try:
            padding = (4 - len(func.cpf) % 4) % 4
            ct = base64.urlsafe_b64decode(func.cpf + "=" * padding)
            func.cpf = aessiv.decrypt(ct, []).decode()
            to_update.append(func)
        except Exception:
            pass

    if to_update:
        FuncionarioSST.objects.bulk_update(to_update, ["cpf"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0133_biometria_consentimento_lgpd"),
    ]

    operations = [
        # 1. Schema: expande coluna para TEXT via SQL direto (AlterField falha quando
        #    o modelo não está registrado no estado de migrações do Django).
        migrations.RunSQL(
            sql="ALTER TABLE api_funcionariosst ALTER COLUMN cpf TYPE TEXT",
            reverse_sql="ALTER TABLE api_funcionariosst ALTER COLUMN cpf TYPE varchar(14)",
        ),
        # 2. Dados: criptografa todos os CPFs existentes
        migrations.RunPython(
            encrypt_existing_cpfs,
            reverse_code=decrypt_existing_cpfs,
        ),
    ]
