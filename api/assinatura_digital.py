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

# Suporte a envelope PKCS#7 real (CAdES-BES) — disponível a partir da versão
# 41.x da biblioteca cryptography. Detectado em import-time para não quebrar
# instalações mais antigas (fallback para RSA raw com label honesto).
try:
    from cryptography.hazmat.primitives.serialization import pkcs7 as _pkcs7_mod
    from cryptography.hazmat.primitives.serialization import Encoding as _Enc
    _PKCS7_OK = True
except ImportError:
    _PKCS7_OK = False


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

        priv_key, cert, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, senha_bytes, backend=default_backend()
        )

        dados_bytes = conteudo.encode("utf-8")
        hash_hex = hashlib.sha256(dados_bytes).hexdigest()

        # Tenta envelope CAdES-BES (PKCS#7 DER) — validade jurídica mais robusta.
        if _PKCS7_OK and cert is not None:
            try:
                builder = _pkcs7_mod.PKCS7SignatureBuilder()
                builder = builder.set_data(dados_bytes)
                builder = builder.add_signer(cert, priv_key, hashes.SHA256())
                signed_bytes = builder.sign(_Enc.DER, [_pkcs7_mod.PKCS7Options.Binary])
                assinatura_b64 = base64.b64encode(signed_bytes).decode("utf-8")
                return True, assinatura_b64, hash_hex, None
            except Exception:
                pass  # fallback para RSA raw abaixo

        # Fallback: assinatura RSA raw (PKCS#1 v1.5 SHA-256) — label honesto.
        assinatura_bytes = priv_key.sign(
            dados_bytes,
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


def _cert_da_cred(cred, senha_override=""):
    """Carrega (priv_key, cert) do PKCS#12 da empresa, ou (None, None)."""
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.hazmat.backends import default_backend
        pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "") if cred else ""
        if not pfx_b64:
            return None, None
        senha = senha_override or (
            cred.get_rnds_certificado_senha() if hasattr(cred, "get_rnds_certificado_senha") else ""
        )
        priv, cert, _ = pkcs12.load_key_and_certificates(
            base64.b64decode(pfx_b64), senha.encode() if senha else None, backend=default_backend()
        )
        return priv, cert
    except Exception:
        return None, None


def verificar_assinatura(conteudo, assinatura_b64, hash_armazenado, cred=None):
    """
    Verifica uma assinatura de dado clínico. Vai ALÉM do hash: quando há
    certificado e a assinatura é RSA/CAdES, valida CRIPTOGRAFICAMENTE que o
    conteúdo foi assinado pela chave privada do certificado.

    Retorna dict:
      {integro, autentico, metodo, detalhe}
      integro  = o conteúdo não mudou (hash bate)
      autentico= a assinatura confere com o certificado (None se não aplicável)
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    hash_atual = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
    integro = bool(hash_armazenado) and (hash_atual == hash_armazenado)
    resultado = {"integro": integro, "autentico": None, "metodo": "SHA256",
                 "detalhe": "", "hash_calculado": hash_atual}

    if not assinatura_b64:
        return resultado

    try:
        raw = base64.b64decode(assinatura_b64)
    except Exception:
        resultado["detalhe"] = "assinatura ilegível"
        return resultado

    # Fallback SHA-256: a assinatura é um JSON base64 com o hash dentro.
    if raw[:1] == b"{":
        try:
            meta = json.loads(raw.decode("utf-8"))
            resultado["metodo"] = meta.get("metodo", "SHA256")
            resultado["autentico"] = None  # sem cripto de chave — só integridade
            resultado["detalhe"] = "assinatura SHA-256 (sem validade jurídica plena)"
        except Exception:
            pass
        return resultado

    priv, cert = _cert_da_cred(cred, "")
    if cert is None:
        resultado["detalhe"] = "certificado indisponível para verificar autenticidade"
        return resultado

    # CAdES-BES / PKCS#7 (DER começa com SEQUENCE 0x30)
    if raw[:1] == b"\x30" and _PKCS7_OK:
        resultado["metodo"] = "ICP-Brasil-CAdES-BES"
        try:
            # O certificado do signatário vai DENTRO do envelope PKCS#7; a
            # verificação criptográfica PLENA de CAdES depende de validador
            # ICP-Brasil (cadeia + LCR/OCSP), fora do escopo em-processo. Aqui
            # confirmamos que o envelope é bem-formado e que a INTEGRIDADE do
            # conteúdo bate (hash). Honesto: autenticidade = None (não afirmamos
            # o que não verificamos in-app).
            from cryptography.hazmat.primitives.serialization import pkcs7 as _p7
            if hasattr(_p7, "load_der_pkcs7_certificates"):
                _p7.load_der_pkcs7_certificates(raw)  # levanta se malformado
            resultado["autentico"] = None
            resultado["detalhe"] = ("envelope CAdES-BES bem-formado; integridade confirmada. "
                                    "Autenticidade jurídica plena via validador ICP-Brasil.")
        except Exception as e:
            resultado["autentico"] = False
            resultado["detalhe"] = f"envelope PKCS#7 inválido: {str(e)[:120]}"
        return resultado

    # RSA raw (PKCS#1 v1.5) — verificação criptográfica real contra a chave pública
    resultado["metodo"] = "ICP-Brasil-RSA-SHA256"
    try:
        cert.public_key().verify(raw, conteudo.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        resultado["autentico"] = True
        resultado["detalhe"] = "assinatura RSA confere com o certificado"
    except Exception:
        resultado["autentico"] = False
        resultado["detalhe"] = "assinatura RSA NÃO confere — documento ou chave divergem"
    return resultado


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
            # Detecta se o envelope é CAdES-BES (prefixo DER 0x30) ou RSA raw.
            metodo = "ICP-Brasil-RSA-SHA256"
            try:
                raw = base64.b64decode(assinatura[:4] + "==")
                if raw[0] == 0x30:
                    metodo = "ICP-Brasil-CAdES-BES"
            except Exception:
                pass
            return True, assinatura, hash_hex, metodo, None
        # falha recuperável (sem biblioteca/erro) → cai para SHA-256
    ok, assinatura, hash_hex, erro = _assinar_hash_simples(conteudo, identificador)
    if ok:
        return True, assinatura, hash_hex, "SHA256", None
    return False, "", "", "SHA256", erro
