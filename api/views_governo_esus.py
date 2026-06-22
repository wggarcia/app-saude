"""
views_governo_esus.py
e-SUS / RNDS — envio de fichas ao ecossistema nacional de saúde digital.

Integração real com RNDS (Rede Nacional de Dados em Saúde) via:
  • Certificado ICP-Brasil A1/A3 emitido em nome da prefeitura/secretaria
  • OAuth2 mTLS → token Bearer → POST FHIR R4 ao endpoint RNDS
  • Fichas: fichaAtendimentoIndividual, fichaVacinacao, fichaAtividadeColetiva

Quando o certificado RNDS está configurado em CredenciaisIntegracoes:
  → transmissão real ao RNDS
Quando não está configurado:
  → modo registro local (dados salvos, aguardando credenciais)

Referência:
  https://rnds-guia.saude.gov.br/
  https://simplifier.net/redenacionaldedadosemsaude
"""
import base64
import hashlib
import json
import logging
import os
import tempfile
from datetime import date, datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import AtendimentoUBS, CredenciaisIntegracoes, LogESUS
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import requer_setor, requer_operacao_page, requer_permissao_modulo

logger = logging.getLogger(__name__)

# ── Endpoints RNDS ────────────────────────────────────────────────────────────
_RNDS_AUTH_PROD = "https://ehr.saude.gov.br/api/fhir/r4"
_RNDS_AUTH_HML  = "https://ehr-hmg.saude.gov.br/api/fhir/r4"
_RNDS_TOKEN_PROD = "https://ehr.saude.gov.br/api/token"
_RNDS_TOKEN_HML  = "https://ehr-hmg.saude.gov.br/api/token"


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def governo_esus_page(request):
    return render(request, "governo_esus.html", contexto_navegacao_setorial(request, "governo"))


# ── Status ────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_esus_status(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    pendentes = AtendimentoUBS.objects.filter(empresa=e, enviado_esus=False).count()
    enviados_hoje = LogESUS.objects.filter(empresa=e, enviado_em__date=hoje, status="enviado").count()
    erros = LogESUS.objects.filter(empresa=e, status="erro").count()

    # Verifica se credenciais RNDS estão configuradas
    cred = CredenciaisIntegracoes.objects.filter(empresa=e).first()
    rnds_ok = cred.rnds_configurado() if cred else False

    return JsonResponse({
        "pendentes": pendentes,
        "enviados_hoje": enviados_hoje,
        "erros": erros,
        "rnds_configurado": rnds_ok,
        "modo": "rnds_real" if rnds_ok else "registro_local",
        "instrucao_configuracao": (
            None if rnds_ok else
            "Configure o certificado ICP-Brasil em POST /api/integracoes/credenciais/rnds/"
        ),
    })


# ── Logs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_esus_logs(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = LogESUS.objects.filter(empresa=e).order_by("-enviado_em")[:50]
    return JsonResponse({"logs": [_log_dict(l) for l in qs]})


# ── Enviar fichas ─────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_esus_enviar_fichas(request):
    """
    Envia fichas de atendimento ao RNDS.

    Com credenciais configuradas: transmissão real via OAuth2 mTLS + FHIR R4.
    Sem credenciais: registra localmente e orienta configuração.

    POST /api/governo/esus/enviar/
    """
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    pendentes_qs = AtendimentoUBS.objects.filter(empresa=e, enviado_esus=False)
    total = pendentes_qs.count()

    if total == 0:
        return JsonResponse({"enviados": 0, "mensagem": "Nenhuma ficha pendente."})

    # Verifica se RNDS está configurado
    cred = CredenciaisIntegracoes.objects.filter(empresa=e).first()
    if cred and cred.rnds_configurado():
        return _enviar_fichas_rnds_real(e, pendentes_qs, total, cred)
    else:
        return _enviar_fichas_registro_local(e, pendentes_qs, total)


def _enviar_fichas_rnds_real(empresa, pendentes_qs, total, cred):
    """Transmissão real ao RNDS via certificado ICP-Brasil + OAuth2 + FHIR R4."""
    cert_path = key_path = None
    try:
        import requests as req
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
        from cryptography.hazmat.backends import default_backend

        # Carrega certificado ICP-Brasil
        pfx_bytes = base64.b64decode(cred.rnds_certificado_pfx_b64)
        senha_bytes = cred.get_rnds_certificado_senha().encode() or b""
        private_key, cert, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, senha_bytes, backend=default_backend()
        )

        cert_file = tempfile.NamedTemporaryFile(suffix=".crt", delete=False)
        key_file = tempfile.NamedTemporaryFile(suffix=".key", delete=False)
        cert_file.write(cert.public_bytes(Encoding.PEM))
        cert_file.close()
        key_file.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        key_file.close()
        cert_path, key_path = cert_file.name, key_file.name

        ambiente = cred.rnds_ambiente
        token_url = _RNDS_TOKEN_PROD if ambiente == "producao" else _RNDS_TOKEN_HML
        fhir_base = _RNDS_AUTH_PROD if ambiente == "producao" else _RNDS_AUTH_HML

        # OAuth2 mTLS — obtém token Bearer
        token_resp = req.post(
            token_url,
            cert=(cert_path, key_path),
            data={"grant_type": "client_credentials", "scope": "write"},
            timeout=30,
            verify=True,
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("access_token", "")
        if not token:
            raise RuntimeError("Token RNDS não obtido.")

        # Serializa fichas em Bundle FHIR R4
        atendimentos = list(pendentes_qs.select_related("prontuario")[:200])
        bundle = _montar_bundle_fhir(atendimentos, cred)
        bundle_json = json.dumps(bundle, ensure_ascii=False)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/fhir+json; charset=utf-8",
            "X-Authorization-Server": f"Bearer {token}",
        }

        resp = req.post(
            f"{fhir_base}/Bundle",
            data=bundle_json.encode("utf-8"),
            headers=headers,
            cert=(cert_path, key_path),
            timeout=120,
            verify=True,
        )

        if resp.status_code in (200, 201):
            pendentes_qs.update(enviado_esus=True)
            log = LogESUS.objects.create(
                empresa=empresa,
                ficha_tipo="fichaAtendimentoIndividual",
                registros_enviados=total,
                status="enviado",
                resposta_rnds=resp.json() if resp.text else {"ok": True},
            )
            # Atualiza metadados de transmissão
            cred.rnds_ultima_transmissao = timezone.now()
            cred.save(update_fields=["rnds_ultima_transmissao"])
            return JsonResponse({
                "ok": True,
                "enviados": total,
                "log_id": log.id,
                "modo": "rnds_real",
                "ambiente": ambiente,
                "mensagem": f"{total} ficha(s) transmitida(s) ao RNDS com sucesso.",
            })
        else:
            erro_msg = f"RNDS retornou HTTP {resp.status_code}: {resp.text[:500]}"
            log = LogESUS.objects.create(
                empresa=empresa,
                ficha_tipo="fichaAtendimentoIndividual",
                registros_enviados=total,
                status="erro",
                resposta_rnds={"status_http": resp.status_code, "erro": resp.text[:2000]},
            )
            return JsonResponse({"ok": False, "erro": erro_msg, "log_id": log.id}, status=502)

    except Exception as ex:
        msg = str(ex)[:500]
        logger.exception("Erro ao transmitir fichas RNDS: %s", msg)
        LogESUS.objects.create(
            empresa=empresa,
            ficha_tipo="fichaAtendimentoIndividual",
            registros_enviados=total,
            status="erro",
            resposta_rnds={"erro": msg},
        )
        return JsonResponse({"ok": False, "erro": msg}, status=500)
    finally:
        for p in [cert_path, key_path]:
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass


def _montar_bundle_fhir(atendimentos, cred):
    """
    Serializa atendimentos UBS em Bundle FHIR R4 (fichaAtendimentoIndividual).
    Ref: https://simplifier.net/redenacionaldedadosemsaude/brencounter
    """
    entries = []
    for atend in atendimentos:
        resource_id = f"enc-{atend.id}"
        paciente_ref = (
            f"Patient/{getattr(atend.prontuario, 'cns', atend.cns)}"
            if atend.prontuario else f"Patient/{atend.cns or atend.id}"
        )
        entry = {
            "fullUrl": f"urn:uuid:{resource_id}",
            "resource": {
                "resourceType": "Encounter",
                "id": resource_id,
                "meta": {
                    "profile": [
                        "https://br-core.saude.gov.br/fhir/r4/StructureDefinition/BREncounterBasic"
                    ]
                },
                "status": "finished",
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "AMB",
                    "display": "ambulatory",
                },
                "subject": {"reference": paciente_ref, "display": atend.paciente_nome},
                "participant": [
                    {
                        "type": [{"coding": [{"code": "PPRF"}]}],
                        "individual": {"display": atend.profissional},
                        "extension": [
                            {
                                "url": "http://rnds.saude.gov.br/fhir/r4/StructureDefinition/BRProfissional",
                                "valueString": atend.cbo or "",
                            }
                        ],
                    }
                ],
                "period": {"start": atend.data_atendimento.isoformat() if hasattr(atend, "data_atendimento") and atend.data_atendimento else timezone.now().date().isoformat()},
                "serviceProvider": {
                    "identifier": {
                        "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/CNES",
                        "value": cred.rnds_cnes or "",
                    }
                },
                "location": [
                    {
                        "location": {
                            "identifier": {
                                "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/CNES",
                                "value": cred.rnds_cnes or "",
                            }
                        }
                    }
                ],
            },
        }
        entries.append(entry)

    return {
        "resourceType": "Bundle",
        "type": "batch",
        "meta": {
            "profile": ["https://br-core.saude.gov.br/fhir/r4/StructureDefinition/BRBundle"]
        },
        "entry": entries,
    }


def _enviar_fichas_registro_local(empresa, pendentes_qs, total):
    """Registra fichas localmente quando RNDS não está configurado."""
    log = LogESUS.objects.create(
        empresa=empresa,
        ficha_tipo="fichaAtendimentoIndividual",
        registros_enviados=total,
        status="pendente",
        resposta_rnds={
            "modo": "registro_local",
            "aviso": "Credenciais RNDS não configuradas. Fichas salvas localmente.",
            "instrucao": "Configure o certificado ICP-Brasil em POST /api/integracoes/credenciais/rnds/",
            "registros": total,
        },
    )
    return JsonResponse({
        "ok": False,
        "enviados": 0,
        "registros_pendentes": total,
        "log_id": log.id,
        "modo": "registro_local",
        "erro": "Credenciais RNDS não configuradas.",
        "instrucao": "Configure em POST /api/integracoes/credenciais/rnds/ — certificado ICP-Brasil A1/A3 obtido junto ao CONASEMS/CONASS.",
        "link": "/api/integracoes/credenciais/",
    }, status=400)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_dict(l):
    return {
        "id": l.id,
        "ficha_tipo": l.ficha_tipo,
        "registros_enviados": l.registros_enviados,
        "status": l.status,
        "resposta_rnds": l.resposta_rnds,
        "enviado_em": l.enviado_em.isoformat(),
    }
