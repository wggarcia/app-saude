"""
rnds_fhir.py — Helper compartilhado para transmissão FHIR R4 ao RNDS
(Rede Nacional de Dados em Saúde — DATASUS/MS)

Autenticação: certificado ICP-Brasil A1/A3 (PKCS#12) por empresa/tenant,
armazenado em CredenciaisIntegracoes.rnds_certificado_pfx_b64 (base64)
com senha criptografada por Fernet.

Endpoints RNDS:
  Homologação: https://ehr-hmg.saude.gov.br/api/fhir/r4
  Produção:    https://ehr.saude.gov.br/api/fhir/r4

Referência:
  https://rnds-guia.saude.gov.br/
  https://simplifier.net/redenacionaldedadosemsaude
"""
import base64
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# Endpoints RNDS oficiais (Portaria GM/MS 1.434/2020 e atualizações)
RNDS_FHIR_URLS = {
    "homologacao": "https://ehr-hmg.saude.gov.br/api/fhir/r4",
    "producao":    "https://ehr.saude.gov.br/api/fhir/r4",
}


def transmitir_bundle(bundle: dict, cred) -> tuple[bool, str, str]:
    """
    Envia Bundle FHIR R4 ao RNDS via mTLS (PKCS#12 ICP-Brasil).

    Parâmetros:
        bundle: dicionário FHIR Bundle (type=batch ou transaction)
        cred:   instância de CredenciaisIntegracoes com cert PFX carregado

    Retorna:
        (ok: bool, protocolo: str, erro: str)
    """
    try:
        import requests as req
        from cryptography.hazmat.primitives.serialization import (
            pkcs12, Encoding, PrivateFormat, NoEncryption,
        )

        ambiente  = getattr(cred, "rnds_ambiente", "homologacao") or "homologacao"
        base_url  = RNDS_FHIR_URLS.get(ambiente, RNDS_FHIR_URLS["homologacao"])

        pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "") or ""
        if not pfx_b64:
            return False, "", "Certificado RNDS não carregado. Configure em Integrações → RNDS."

        pfx_bytes   = base64.b64decode(pfx_b64)
        senha       = cred.get_rnds_certificado_senha() if hasattr(cred, "get_rnds_certificado_senha") else ""
        senha_bytes = senha.encode() if senha else None

        priv_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, senha_bytes)
        pem_cert = cert.public_bytes(Encoding.PEM)
        pem_key  = priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

        cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
        key_fd,  key_path  = tempfile.mkstemp(suffix=".pem")
        try:
            with os.fdopen(cert_fd, "wb") as fc:
                fc.write(pem_cert)
            with os.fdopen(key_fd, "wb") as fk:
                fk.write(pem_key)

            resp = req.post(
                f"{base_url}/Bundle",
                json=bundle,
                cert=(cert_path, key_path),
                headers={
                    "Content-Type": "application/fhir+json",
                    "Accept":       "application/fhir+json",
                },
                timeout=30,
            )
        finally:
            for p in (cert_path, key_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

        if resp.status_code in (200, 201):
            data      = resp.json()
            protocolo = (
                data.get("id")
                or resp.headers.get("Location", "").rsplit("/", 1)[-1]
                or f"RNDS-{bundle.get('timestamp', '')}"
            )
            return True, protocolo, ""

        return False, "", f"HTTP {resp.status_code}: {resp.text[:400]}"

    except ImportError as e:
        return False, "", f"Dependência ausente: {e}. Execute: pip install cryptography requests"
    except Exception as e:
        logger.exception("Erro transmissão RNDS: %s", e)
        return False, "", str(e)[:500]


def get_cred(empresa):
    """Retorna CredenciaisIntegracoes da empresa (cria se não existir)."""
    try:
        from api.models import CredenciaisIntegracoes
        cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
        return cred
    except Exception:
        return None
