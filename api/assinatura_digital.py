"""
assinatura_digital.py
Assinatura digital de documentos clínicos (genérica, reutilizável).

Dois modos:
  - ICP-Brasil (PKCS#12): assinatura RSA-SHA256 com o certificado A1/A3 da
    empresa, armazenado Fernet-encrypted em CredenciaisIntegracoes
    (rnds_certificado_pfx_b64). Validade jurídica plena — CFM Res. 2.299/2021.
  - SHA-256 (fallback): quando não há certificado configurado. Garante
    integridade (qualquer alteração invalida o hash) mas sem validade jurídica
    plena.

Uso:
    ok, assinatura_b64, hash_hex, metodo, erro = assinar_conteudo(
        conteudo_canonical, cred, identificador="CRM/PR 12345")

Este módulo é independente do módulo de assinatura hospitalar — não altera
aquele fluxo. Serve o PEC (governo) e qualquer outro que precise assinar texto.
"""
import base64
import hashlib
import json
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def _assinar_hash_simples(conteudo, identificador):
    """Assinatura funcional SHA-256. Retorna (ok, assinatura_b64, hash_hex, erro)."""
    try:
        hash_hex = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
        meta = json.dumps({
            "hash": hash_hex,
            "identificador": identificador,
            "timestamp": timezone.now().isoformat(),
            "metodo": "SHA256",
        })
        assinatura = base64.b64encode(meta.encode("utf-8")).decode("utf-8")
        return True, assinatura, hash_hex, None
    except Exception as e:  # pragma: no cover - defensivo
        logger.exception("Falha na assinatura SHA-256")
        return False, "", "", str(e)[:300]


def _assinar_icp_brasil(conteudo, cred, senha_override=""):
    """
    Assinatura RSA-SHA256 (PKCS#1 v1.5) com certificado ICP-Brasil.
    Retorna (ok, assinatura_b64, hash_hex, erro).
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend

        pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "") if cred else ""
        if not pfx_b64:
            return False, "", "", "sem_certificado"

        pfx_bytes = base64.b64decode(pfx_b64)
        senha = senha_override or (
            cred.get_rnds_certificado_senha() if hasattr(cred, "get_rnds_certificado_senha") else ""
        )
        senha_bytes = senha.encode() if senha else None

        priv_key, _cert, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, senha_bytes, backend=default_backend()
        )

        hash_hex = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
        assinatura_bytes = priv_key.sign(
            conteudo.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        assinatura_b64 = base64.b64encode(assinatura_bytes).decode("utf-8")
        return True, assinatura_b64, hash_hex, None

    except ImportError:
        logger.warning("Biblioteca 'cryptography' ausente — usando SHA-256 simples.")
        return False, "", "", "sem_biblioteca"
    except Exception as e:
        logger.exception("Erro ao assinar com ICP-Brasil")
        return False, "", "", str(e)[:300]


def assinar_conteudo(conteudo, cred, identificador="", senha_override=""):
    """
    Assina o conteúdo canônico. Tenta ICP-Brasil; se não houver certificado ou
    biblioteca, aplica SHA-256 funcional.

    Retorna: (ok, assinatura_b64, hash_hex, metodo, erro)
      metodo ∈ {"ICP-Brasil-PKCS7", "SHA256"}
    """
    pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "") if cred else ""
    if pfx_b64:
        ok, assinatura, hash_hex, erro = _assinar_icp_brasil(conteudo, cred, senha_override)
        if ok:
            return True, assinatura, hash_hex, "ICP-Brasil-PKCS7", None
        # falha recuperável (sem biblioteca/erro) → cai para SHA-256
    ok, assinatura, hash_hex, erro = _assinar_hash_simples(conteudo, identificador)
    if ok:
        return True, assinatura, hash_hex, "SHA256", None
    return False, "", "", "SHA256", erro
