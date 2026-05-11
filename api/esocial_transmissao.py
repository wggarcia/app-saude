"""
eSocial REST transmission engine.

The Brazilian government eSocial platform (since 2023) accepts events via REST API.
Authentication uses a company's digital certificate (PKCS#12 / .pfx) for mTLS + OAuth2.

Flow:
  1. Load empresa's certificate from encrypted storage
  2. Obtain OAuth2 Bearer token from Serpro IDP using the certificate
  3. POST the event XML as JSON payload to the eSocial gateway
  4. Parse the response to extract the protocol number
  5. Update eSocialEventoSST with status + protocol

Government endpoints:
  Homologação: https://h-autenticacao.esocial.gov.br/
  Produção:    https://autenticacao.esocial.gov.br/

Reference: Manual de Orientação do eSocial v2.5 — Capítulo 4 (Transmissão REST)
"""
import base64
import json
import logging
import os
import tempfile
from datetime import datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Environment ──────────────────────────────────────────────────────────────

_ESOCIAL_AMBIENTE = getattr(settings, "ESOCIAL_AMBIENTE", "homologacao")

_URLS = {
    "homologacao": {
        "token":  "https://h-autenticacao.esocial.gov.br/api/login",
        "enviar": "https://h-gateway.esocial.gov.br/services/v1/lotes/eventos/enviar",
        "tpAmb": "2",
    },
    "producao": {
        "token":  "https://autenticacao.esocial.gov.br/api/login",
        "enviar": "https://gateway.esocial.gov.br/services/v1/lotes/eventos/enviar",
        "tpAmb": "1",
    },
}


def _cfg_urls():
    return _URLS.get(_ESOCIAL_AMBIENTE, _URLS["homologacao"])


# ── Certificate loading ───────────────────────────────────────────────────────

def _carregar_certificado(cfg_esocial):
    """
    Returns (cert_path_pem, key_path_pem) tuple for use with requests.
    Writes temp PEM files from the stored PKCS#12 data and returns their paths.
    Caller must delete temp files after use.
    """
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise RuntimeError(
            "Instale 'cryptography' para transmissão eSocial: pip install cryptography"
        )

    pfx_b64 = cfg_esocial.certificado_pfx_b64
    senha = cfg_esocial.certificado_senha

    if not pfx_b64:
        raise ValueError("Certificado digital não configurado para esta empresa.")

    pfx_bytes = base64.b64decode(pfx_b64)
    senha_bytes = senha.encode() if senha else b""

    private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
        pfx_bytes, senha_bytes, backend=default_backend()
    )

    # Write PEM files to temp dir
    cert_file = tempfile.NamedTemporaryFile(suffix=".crt", delete=False)
    key_file = tempfile.NamedTemporaryFile(suffix=".key", delete=False)

    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    cert_file.write(cert_pem)
    cert_file.close()
    key_file.write(key_pem)
    key_file.close()

    return cert_file.name, key_file.name


def _limpar_cert_files(*paths):
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


# ── Token acquisition ─────────────────────────────────────────────────────────

def _obter_token(cert_path, key_path):
    """
    Authenticates with eSocial IDP using client certificate and returns Bearer token.
    Uses mTLS (mutual TLS) — the certificate proves the company's identity.
    """
    import requests as req

    urls = _cfg_urls()
    try:
        resp = req.post(
            urls["token"],
            cert=(cert_path, key_path),
            json={"grant_type": "client_credentials"},
            timeout=30,
            verify=True,
        )
        resp.raise_for_status()
        return resp.json().get("access_token") or resp.json().get("token")
    except req.exceptions.SSLError as e:
        raise RuntimeError(f"Erro de certificado: {e}")
    except req.exceptions.ConnectionError:
        raise RuntimeError("Não foi possível conectar ao servidor eSocial. Verifique a conexão.")
    except Exception as e:
        raise RuntimeError(f"Falha na autenticação eSocial: {e}")


# ── Event transmission ────────────────────────────────────────────────────────

def _montar_lote(evento, xml_str, cnpj_empresa):
    """Wraps a single event XML into the eSocial batch envelope."""
    return {
        "grupo": {
            "ideEmpregador": {
                "tpInsc": "1",
                "nrInsc": cnpj_empresa,
            },
            "ideTransmissor": {
                "tpInsc": "1",
                "nrInsc": cnpj_empresa,
            },
            "eventos": [
                {
                    "evento": {
                        "Id": evento.evento_id or f"ID_{evento.tipo_evento.replace('-','')}_{evento.pk}",
                        "dados": xml_str,
                    }
                }
            ],
        }
    }


def transmitir_evento(evento):
    """
    Sends a single eSocial event to the government.
    Updates evento.status, evento.protocolo, evento.mensagem_erro, evento.data_envio.

    Returns (success: bool, message: str).
    """
    from .models import ConfiguracaoSST

    empresa = evento.empresa

    # Load empresa config
    try:
        cfg_sst = empresa.configuracao_sst
    except ConfiguracaoSST.DoesNotExist:
        cfg_sst = None

    if not cfg_sst or not getattr(cfg_sst, "certificado_pfx_b64", None):
        evento.status = "erro"
        evento.mensagem_erro = "Certificado digital não configurado. Acesse Configurações > eSocial para enviar o certificado."
        evento.save(update_fields=["status", "mensagem_erro"])
        return False, evento.mensagem_erro

    if not evento.xml_gerado:
        evento.status = "erro"
        evento.mensagem_erro = "XML não gerado. Gere o XML antes de transmitir."
        evento.save(update_fields=["status", "mensagem_erro"])
        return False, evento.mensagem_erro

    cert_path = key_path = None
    try:
        import requests as req

        cert_path, key_path = _carregar_certificado(cfg_sst)
        token = _obter_token(cert_path, key_path)

        cnpj = "".join(c for c in (cfg_sst.cnpj or "") if c.isdigit())[:14]
        payload = _montar_lote(evento, evento.xml_gerado, cnpj)

        urls = _cfg_urls()
        resp = req.post(
            urls["enviar"],
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            cert=(cert_path, key_path),
            timeout=60,
            verify=True,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            protocolo = (
                data.get("protocolo")
                or data.get("nrRec")
                or data.get("data", {}).get("protocolo", "")
            )
            evento.status = "transmitido"
            evento.protocolo = str(protocolo or "")
            evento.mensagem_erro = ""
            evento.data_envio = timezone.now()
            evento.save(update_fields=["status", "protocolo", "mensagem_erro", "data_envio"])

            # Sync status back to origin records
            _sincronizar_status(evento, "transmitido", evento.protocolo)

            logger.info(
                "eSocial evento %s transmitido — protocolo %s",
                evento.pk, evento.protocolo,
            )
            return True, f"Transmitido com sucesso. Protocolo: {evento.protocolo}"

        else:
            erro = resp.text[:500]
            evento.status = "erro"
            evento.mensagem_erro = f"HTTP {resp.status_code}: {erro}"
            evento.data_envio = timezone.now()
            evento.save(update_fields=["status", "mensagem_erro", "data_envio"])
            return False, evento.mensagem_erro

    except Exception as e:
        msg = str(e)[:500]
        evento.status = "erro"
        evento.mensagem_erro = msg
        evento.data_envio = timezone.now()
        evento.save(update_fields=["status", "mensagem_erro", "data_envio"])
        logger.exception("Erro ao transmitir evento eSocial %s", evento.pk)
        return False, msg

    finally:
        if cert_path or key_path:
            _limpar_cert_files(cert_path, key_path)


def _sincronizar_status(evento, status, protocolo):
    """Updates the source record (CAT, ASO, etc.) with the transmission status."""
    from .models import CATOcupacional, ASOOcupacional, AfastamentoSST

    try:
        ref = int(evento.referencia) if evento.referencia and evento.referencia.isdigit() else None
        if ref is None:
            return
        if evento.tipo_evento == "S-2210":
            CATOcupacional.objects.filter(pk=ref, empresa=evento.empresa).update(
                status_esocial=status, protocolo_esocial=protocolo
            )
        elif evento.tipo_evento == "S-2220":
            ASOOcupacional.objects.filter(pk=ref, empresa=evento.empresa).update(
                status_esocial=status, protocolo_esocial=protocolo
            )
        elif evento.tipo_evento == "S-2230":
            AfastamentoSST.objects.filter(pk=ref, empresa=evento.empresa).update(
                status_esocial=status
            )
    except Exception:
        pass


# ── Batch transmission ────────────────────────────────────────────────────────

def transmitir_pendentes(empresa, limite=50):
    """
    Transmits all pending events for an empresa, up to `limite`.
    Returns list of (evento_id, success, message).
    """
    from .models import eSocialEventoSST

    eventos = eSocialEventoSST.objects.filter(
        empresa=empresa,
        status="pendente",
        xml_gerado__isnull=False,
    ).exclude(xml_gerado="")[:limite]

    resultados = []
    for ev in eventos:
        ok, msg = transmitir_evento(ev)
        resultados.append({"evento_id": ev.pk, "tipo": ev.tipo_evento, "ok": ok, "mensagem": msg})

    return resultados
