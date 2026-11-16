"""
views_governo_esus.py
e-SUS / RNDS — envio de fichas ao ecossistema nacional de saúde digital.

Integração com RNDS (Rede Nacional de Dados em Saúde) pelo cliente único
api/services/rnds_fhir.py (token no servidor Auth + servidor EHR por UF).
O perfil Encounter enviado aqui só se confirma na homologação da RNDS.

Quando o certificado RNDS está configurado em CredenciaisIntegracoes:
  → transmissão real ao RNDS
Quando não está configurado:
  → modo registro local (dados salvos, aguardando credenciais)

Referência:
  https://rnds-guia.saude.gov.br/
  https://simplifier.net/redenacionaldedadosemsaude
"""
import logging
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_permissao_modulo, get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .models import AtendimentoUBS, CredenciaisIntegracoes, LogESUS
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial

logger = logging.getLogger(__name__)


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
@api_requer_permissao_modulo("governo.atencao_clinica")
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
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_esus_logs(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = LogESUS.objects.filter(empresa=e).order_by("-enviado_em")[:50]
    return JsonResponse({"logs": [_log_dict(l) for l in qs]})


# ── Enviar fichas ─────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
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
    """Transmissão ao RNDS pelo cliente único (api/services/rnds_fhir.py)."""
    from .services.rnds_fhir import ambiente_de, enviar_bundle

    atendimentos = list(pendentes_qs.select_related("prontuario")[:200])
    bundle = _montar_bundle_fhir(atendimentos, cred)
    r = enviar_bundle(cred, bundle)

    if r.ok:
        pendentes_qs.filter(id__in=[a.id for a in atendimentos]).update(enviado_esus=True)
        log = LogESUS.objects.create(
            empresa=empresa,
            ficha_tipo="fichaAtendimentoIndividual",
            registros_enviados=len(atendimentos),
            status="enviado",
            resposta_rnds=r.dados or {"ok": True, "protocolo": r.protocolo},
        )
        cred.rnds_ultima_transmissao = timezone.now()
        cred.save(update_fields=["rnds_ultima_transmissao"])
        return JsonResponse({
            "ok": True,
            "enviados": len(atendimentos),
            "log_id": log.id,
            "modo": "rnds_real",
            "ambiente": ambiente_de(cred),
            "mensagem": f"{len(atendimentos)} ficha(s) transmitida(s) ao RNDS.",
        })

    log = LogESUS.objects.create(
        empresa=empresa,
        ficha_tipo="fichaAtendimentoIndividual",
        registros_enviados=total,
        status="erro",
        resposta_rnds={"status_http": r.status_http, "erro": r.erro[:2000]},
    )
    return JsonResponse({"ok": False, "erro": r.erro, "log_id": log.id}, status=502)


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
