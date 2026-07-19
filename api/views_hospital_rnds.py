"""
RNDS Hospital — Sumário de Alta (IPS-BR) e Registro de Atendimento Clínico (RAC)
Obrigatório para interoperabilidade com SUS (Portaria GM/MS nº 1.434/2020).

GET  /api/hospital/rnds/status              Status das credenciais RNDS
GET  /api/hospital/rnds/transmissoes        Histórico de transmissões
POST /api/hospital/rnds/transmitir-alta/<internacao_id>   Envia IPS-BR de alta
POST /api/hospital/rnds/transmitir-rac/<prontuario_id>    Envia RAC de atendimento
POST /api/hospital/rnds/reprocessar/<id>    Reprocessa transmissão com erro
GET  /api/hospital/rnds/kpis                KPIs de cobertura
"""
import json
import logging
import math
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.utils import timezone

from .services.auth_session import empresa_autenticada_from_request
from .access_control import (
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _hosp(request):
    """Valida sessão hospital + permissão de módulo RNDS para o usuário."""
    emp = empresa_autenticada_from_request(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _hosp_gerencia(request):
    """Acesso restrito a operações sensíveis RNDS: exige setor hospital + perfil gerência."""
    from .access_control import principal_pode_operacao_setorial
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "hospital":
        return None
    if not principal_pode_operacao_setorial(request, "rnds_gerencia"):
        return None
    return emp


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.rnds", "RNDS / e-SUS")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_rnds_page(request):
    return render(request, "hospital_rnds.html")


def _get_cred(empresa):
    """Retorna CredenciaisIntegracoes ou None."""
    try:
        from .models import CredenciaisIntegracoes
        cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
        return cred
    except Exception:
        return None


# ── Status das credenciais ────────────────────────────────────────────────────

@api_requer_feature("hospital.rnds")
def api_hospital_rnds_status(request):
    """GET /api/hospital/rnds/status — verifica se RNDS está configurado."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    cred = _get_cred(empresa)
    if not cred:
        return JsonResponse({"configurado": False, "erro": "Credenciais não inicializadas"})

    from .models import TransmissaoRNDSHospital

    ultima = TransmissaoRNDSHospital.objects.filter(empresa=empresa).first()

    return JsonResponse({
        "configurado":          cred.rnds_configurado() if hasattr(cred, "rnds_configurado") else False,
        "cnes":                 getattr(cred, "rnds_cnes", "") or None,
        "cpf_gestor":           getattr(cred, "rnds_cpf_gestor", "") or None,
        "ambiente":             getattr(cred, "rnds_ambiente", "homologacao"),
        "ativo":                getattr(cred, "rnds_ativo", False),
        "ultima_transmissao":   getattr(cred, "rnds_ultima_transmissao", None),
        "ultima_transmissao_iso": (
            cred.rnds_ultima_transmissao.isoformat()
            if getattr(cred, "rnds_ultima_transmissao", None) else None
        ),
        "ultimo_status":        ultima.status if ultima else None,
        "aviso": (
            "Configure as credenciais RNDS em Configurações → Integrações → RNDS "
            "com o certificado ICP-Brasil do gestor habilitado."
        ) if not (cred.rnds_configurado() if hasattr(cred, "rnds_configurado") else False) else None,
    })


# ── Histórico ─────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.rnds")
def api_hospital_rnds_transmissoes(request):
    """GET /api/hospital/rnds/transmissoes — histórico paginado."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import TransmissaoRNDSHospital

    tipo   = request.GET.get("tipo")
    status = request.GET.get("status")
    page   = max(1, int(request.GET.get("page") or 1))
    ps     = 50

    qs = TransmissaoRNDSHospital.objects.filter(empresa=empresa)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if status:
        qs = qs.filter(status=status)

    total  = qs.count()
    items  = qs[(page - 1) * ps: page * ps]

    return JsonResponse({
        "total":      total,
        "pagina":     page,
        "paginas":    math.ceil(total / ps) if total else 1,
        "transmissoes": [_tx_dict(t) for t in items],
    })


# ── Transmitir IPS-BR (Sumário de Alta) ───────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.rnds")
def api_hospital_rnds_transmitir_alta(request, internacao_id):
    """
    POST /api/hospital/rnds/transmitir-alta/<internacao_id>
    Gera e envia o Sumário de Alta (IPS-BR) ao RNDS para uma internação.
    """
    empresa = _hosp_gerencia(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import InternacaoHospital, TransmissaoRNDSHospital

    try:
        internacao = InternacaoHospital.objects.get(id=internacao_id, empresa=empresa)
    except InternacaoHospital.DoesNotExist:
        return JsonResponse({"erro": "Internação não encontrada"}, status=404)

    cred = _get_cred(empresa)
    if not cred or not (cred.rnds_configurado() if hasattr(cred, "rnds_configurado") else False):
        return JsonResponse({
            "erro": "Credenciais RNDS não configuradas. Configure em Integrações → RNDS.",
            "codigo": "rnds_nao_configurado",
        }, status=422)

    # Gera o Bundle FHIR IPS-BR
    bundle = _gerar_bundle_ips_br(internacao, empresa)

    # Bug 2 — InternacaoHospital não tem campo "paciente_nome" nem "cns" direto:
    # o nome está em internacao.paciente.nome e CNS não é modelado no legado.
    # getattr() silencioso retornava "" em vez de buscar no FK correto.
    _pac_hosp = internacao.paciente
    # Cria registro de transmissão
    tx = TransmissaoRNDSHospital.objects.create(
        empresa         = empresa,
        tipo            = "ips_br",
        internacao_id   = internacao.id,
        paciente_nome   = getattr(_pac_hosp, "nome", "") if _pac_hosp else "",
        cns_paciente    = "",  # PacienteHospital não modela CNS — campo sempre vazio neste flow
        cpf_paciente    = getattr(_pac_hosp, "cpf", "") if _pac_hosp else "",
        bundle_fhir     = bundle,
        status          = "pendente",
    )

    # Tenta transmitir
    ok, protocolo, erro = _transmitir_rnds(bundle, cred, empresa)

    tx.status         = "transmitido" if ok else "erro"
    tx.protocolo_rnds = protocolo or ""
    tx.ultimo_erro    = erro or ""
    tx.tentativas     = 1
    if ok:
        tx.transmitido_em = timezone.now()
        cred.rnds_ultima_transmissao = timezone.now()
        cred.save(update_fields=["rnds_ultima_transmissao"])
    tx.save()

    return JsonResponse({
        "ok":               ok,
        "transmissao_id":   tx.id,
        "protocolo_rnds":   protocolo,
        "status":           tx.status,
        "mensagem":         "IPS-BR transmitido com sucesso ao RNDS." if ok else f"Erro: {erro}",
        "internacao_id":    internacao_id,
    }, status=200 if ok else 422)


@csrf_exempt
@api_requer_feature("hospital.rnds")
def api_hospital_rnds_transmitir_rac(request, prontuario_id):
    """
    POST /api/hospital/rnds/transmitir-rac/<prontuario_id>
    Envia o Registro de Atendimento Clínico (RAC) para consultas ambulatoriais.
    """
    empresa = _hosp_gerencia(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import ProntuarioHospitalar, TransmissaoRNDSHospital

    try:
        prontuario = ProntuarioHospitalar.objects.get(id=prontuario_id, empresa=empresa)
    except ProntuarioHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Prontuário não encontrado"}, status=404)

    cred = _get_cred(empresa)
    if not cred or not (cred.rnds_configurado() if hasattr(cred, "rnds_configurado") else False):
        return JsonResponse({
            "erro": "Credenciais RNDS não configuradas.",
            "codigo": "rnds_nao_configurado",
        }, status=422)

    bundle = _gerar_bundle_rac(prontuario, empresa)

    # Bug 2 — ProntuarioHospitalar tem paciente_nome e paciente_cpf como campos
    # diretos, mas não tem "cns". O getattr("cns", "") retornava vazio.
    # Usar os campos corretos do model e gravar cpf_paciente quando disponível.
    tx = TransmissaoRNDSHospital.objects.create(
        empresa         = empresa,
        tipo            = "rac",
        internacao_id   = prontuario.id,
        paciente_nome   = prontuario.paciente_nome,
        cns_paciente    = "",  # ProntuarioHospitalar não modela CNS
        cpf_paciente    = prontuario.paciente_cpf or "",
        bundle_fhir     = bundle,
        status          = "pendente",
    )

    ok, protocolo, erro = _transmitir_rnds(bundle, cred, empresa)

    tx.status         = "transmitido" if ok else "erro"
    tx.protocolo_rnds = protocolo or ""
    tx.ultimo_erro    = erro or ""
    tx.tentativas     = 1
    if ok:
        tx.transmitido_em = timezone.now()
    tx.save()

    return JsonResponse({
        "ok":             ok,
        "transmissao_id": tx.id,
        "protocolo_rnds": protocolo,
        "status":         tx.status,
        "mensagem":       "RAC transmitido com sucesso." if ok else f"Erro: {erro}",
    }, status=200 if ok else 422)


@csrf_exempt
@api_requer_feature("hospital.rnds")
def api_hospital_rnds_reprocessar(request, tx_id):
    """POST /api/hospital/rnds/reprocessar/<id> — reprocessa transmissão com erro."""
    empresa = _hosp_gerencia(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import TransmissaoRNDSHospital

    try:
        tx = TransmissaoRNDSHospital.objects.get(id=tx_id, empresa=empresa)
    except TransmissaoRNDSHospital.DoesNotExist:
        return JsonResponse({"erro": "Transmissão não encontrada"}, status=404)

    if tx.status == "transmitido":
        return JsonResponse({"aviso": "Transmissão já foi bem-sucedida.", "protocolo": tx.protocolo_rnds})

    cred = _get_cred(empresa)
    ok, protocolo, erro = _transmitir_rnds(tx.bundle_fhir, cred, empresa)

    tx.status     = "transmitido" if ok else "erro"
    tx.protocolo_rnds = protocolo or ""
    tx.ultimo_erro    = erro or ""
    tx.tentativas    += 1
    if ok:
        tx.transmitido_em = timezone.now()
    tx.save()

    return JsonResponse({
        "ok":       ok,
        "status":   tx.status,
        "protocolo": protocolo,
        "mensagem": "Reprocessado com sucesso." if ok else f"Erro: {erro}",
    }, status=200 if ok else 422)


# ── KPIs ─────────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.rnds")
def api_hospital_rnds_kpis(request):
    """GET /api/hospital/rnds/kpis — cobertura e status das transmissões."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import TransmissaoRNDSHospital, InternacaoHospital
    from django.db.models import Count

    txs = TransmissaoRNDSHospital.objects.filter(empresa=empresa)
    total_altas       = txs.filter(tipo="ips_br").count()
    altas_transmitidas = txs.filter(tipo="ips_br", status="transmitido").count()
    total_rac         = txs.filter(tipo="rac").count()
    rac_transmitidos  = txs.filter(tipo="rac", status="transmitido").count()
    com_erro          = txs.filter(status="erro").count()

    # Internações ainda sem IPS-BR transmitido (alta)
    internacoes_com_tx = set(
        txs.filter(tipo="ips_br", status="transmitido").values_list("internacao_id", flat=True)
    )
    total_internacoes  = InternacaoHospital.objects.filter(empresa=empresa).count()
    sem_ips_br         = max(0, total_internacoes - len(internacoes_com_tx))

    return JsonResponse({
        "ips_br": {
            "total_transmitidos":    altas_transmitidas,
            "total_erros":           txs.filter(tipo="ips_br", status="erro").count(),
            "internacoes_sem_ips_br": sem_ips_br,
            "cobertura_pct": round(altas_transmitidas / total_internacoes * 100, 1) if total_internacoes else 0,
        },
        "rac": {
            "total_transmitidos": rac_transmitidos,
            "total_erros":        txs.filter(tipo="rac", status="erro").count(),
        },
        "total_erros_pendentes": com_erro,
        # TOCTOU fix — .exists() + .first() eram duas queries separadas:
        # se o registro fosse deletado entre as duas, .first() retornava None
        # e .transmitido_em levantava AttributeError. Consolidado em query única.
        "ultima_transmissao": getattr(
            txs.filter(status="transmitido").only("transmitido_em").first(),
            "transmitido_em",
            None,
        ),
    })


# ── Geração FHIR ─────────────────────────────────────────────────────────────

def _gerar_bundle_ips_br(internacao, empresa):
    """
    Gera Bundle FHIR R4 no perfil IPS-BR (Sumário de Alta).
    Referência: https://rnds-guia.saude.gov.br/docs/cdRnds/usar-ips-rac/
    """
    cnes = getattr(empresa, "sus_cnes", "") or ""
    try:
        cred = empresa.credenciais_integracoes
        cnes = cred.sus_cnes or cnes
    except Exception:
        pass

    paciente       = internacao.paciente
    paciente_nome  = getattr(paciente, "nome", None) or "Paciente"
    cns            = ""  # PacienteHospital não modela CNS ainda
    cpf            = getattr(paciente, "cpf", "") or ""
    data_entrada   = getattr(internacao, "data_entrada", None) or date.today()
    data_alta      = getattr(internacao, "data_saida", None) or date.today()

    # InternacaoHospital/PacienteHospital não modelam CID codificado — mas
    # há sincronização opcional com o cadastro moderno (PacienteInternado),
    # que possui o campo diagnostico_cid. Usa-o quando disponível.
    cid_principal  = ""
    cid_display    = ""
    try:
        paciente_sync = getattr(internacao, "paciente_interno_sync", None)
        if paciente_sync and getattr(paciente_sync, "diagnostico_cid", ""):
            cid_principal = paciente_sync.diagnostico_cid
            cid_display   = paciente_sync.diagnostico_descricao or cid_principal
    except Exception:
        pass

    bundle_id = f"ips-br-{empresa.id}-{internacao.id}"

    return {
        "resourceType": "Bundle",
        "id":           bundle_id,
        "meta": {
            "profile": ["https://rnds-fhir.saude.gov.br/StructureDefinition/BRSumarioAlta-1.0"]
        },
        "type":      "document",
        "timestamp": timezone.now().isoformat(),
        "entry": [
            {
                "fullUrl":  f"urn:uuid:composition-{internacao.id}",
                "resource": {
                    "resourceType": "Composition",
                    "status":       "final",
                    "type": {
                        "coding": [{
                            "system":  "http://loinc.org",
                            "code":    "60591-5",
                            "display": "Patient Summary",
                        }]
                    },
                    "subject":  {"reference": f"urn:uuid:patient-{internacao.id}"},
                    "date":     timezone.now().date().isoformat(),
                    "author":   [{"reference": f"urn:uuid:org-{empresa.id}"}],
                    "title":    "Sumário de Alta — IPS-BR",
                    "attester": [{
                        "mode": "professional",
                        "party": {"reference": f"urn:uuid:org-{empresa.id}"},
                    }],
                    "custodian": {"reference": f"urn:uuid:org-{empresa.id}"},
                    "section": [
                        {
                            "title":  "Problemas/Diagnósticos",
                            "code": {"coding": [{"system": "http://loinc.org", "code": "11450-4"}]},
                            "entry": [{"reference": f"urn:uuid:condition-{internacao.id}"}],
                        }
                    ],
                },
            },
            {
                "fullUrl":  f"urn:uuid:patient-{internacao.id}",
                "resource": {
                    "resourceType": "Patient",
                    "identifier": [
                        {"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf", "value": cpf} if cpf else None,
                        {"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns", "value": cns} if cns else None,
                    ],
                    "name": [{"text": paciente_nome}],
                },
            },
            {
                "fullUrl":  f"urn:uuid:org-{empresa.id}",
                "resource": {
                    "resourceType": "Organization",
                    "identifier": [{"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnes", "value": cnes}],
                    "name": empresa.nome,
                },
            },
            {
                "fullUrl":  f"urn:uuid:condition-{internacao.id}",
                "resource": {
                    "resourceType": "Condition",
                    "clinicalStatus": {
                        "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "resolved"}]
                    },
                    "code": {
                        "coding": [{
                            "system":  "http://www.who.int/classifications/icd/en/",
                            "code":    cid_principal,
                            "display": cid_display or cid_principal,
                        }]
                    } if cid_principal else {},
                    "subject":      {"reference": f"urn:uuid:patient-{internacao.id}"},
                    "onsetDateTime": data_entrada.isoformat() if hasattr(data_entrada, "isoformat") else str(data_entrada),
                    "abatementDateTime": data_alta.isoformat() if hasattr(data_alta, "isoformat") else str(data_alta),
                },
            },
        ],
    }


def _gerar_bundle_rac(prontuario, empresa):
    """
    Gera Bundle FHIR R4 no perfil RAC (Registro de Atendimento Clínico).
    Referência: https://rnds-guia.saude.gov.br/docs/cdRnds/usar-ips-rac/
    """
    cnes = ""
    try:
        cred = empresa.credenciais_integracoes
        cnes = cred.sus_cnes or ""
    except Exception:
        pass

    paciente_nome = getattr(prontuario, "paciente_nome", "Paciente")
    cns           = getattr(prontuario, "cns", "") or ""
    data_atend    = getattr(prontuario, "data_atendimento", date.today()) or date.today()
    cid           = getattr(prontuario, "cid_principal", "") or ""

    return {
        "resourceType": "Bundle",
        "id":           f"rac-{empresa.id}-{prontuario.id}",
        "meta": {
            "profile": ["https://rnds-fhir.saude.gov.br/StructureDefinition/BRRegistroAtendimentoClinico-1.0"]
        },
        "type":      "document",
        "timestamp": timezone.now().isoformat(),
        "entry": [
            {
                "fullUrl":  f"urn:uuid:composition-rac-{prontuario.id}",
                "resource": {
                    "resourceType": "Composition",
                    "status":       "final",
                    "type": {
                        "coding": [{
                            "system":  "http://loinc.org",
                            "code":    "34109-9",
                            "display": "Note",
                        }]
                    },
                    "subject":    {"reference": f"urn:uuid:patient-rac-{prontuario.id}"},
                    "date":       timezone.now().date().isoformat(),
                    "author":     [{"reference": f"urn:uuid:org-{empresa.id}"}],
                    "title":      "Registro de Atendimento Clínico — RAC",
                    "custodian":  {"reference": f"urn:uuid:org-{empresa.id}"},
                    "event": [{
                        "period": {
                            "start": data_atend.isoformat() if hasattr(data_atend, "isoformat") else str(data_atend),
                            "end":   data_atend.isoformat() if hasattr(data_atend, "isoformat") else str(data_atend),
                        }
                    }],
                    "section": [
                        {
                            "title": "Diagnósticos",
                            "code":  {"coding": [{"system": "http://loinc.org", "code": "29548-5"}]},
                            "entry": [{"reference": f"urn:uuid:condition-rac-{prontuario.id}"}] if cid else [],
                        }
                    ],
                },
            },
            {
                "fullUrl":  f"urn:uuid:patient-rac-{prontuario.id}",
                "resource": {
                    "resourceType": "Patient",
                    "identifier": [
                        {"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns", "value": cns}
                    ] if cns else [],
                    "name": [{"text": paciente_nome}],
                },
            },
            {
                "fullUrl":  f"urn:uuid:org-{empresa.id}",
                "resource": {
                    "resourceType": "Organization",
                    "identifier": [{"system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnes", "value": cnes}],
                    "name": empresa.nome,
                },
            },
        ] + ([{
            "fullUrl": f"urn:uuid:condition-rac-{prontuario.id}",
            "resource": {
                "resourceType": "Condition",
                "code": {
                    "coding": [{"system": "http://www.who.int/classifications/icd/en/", "code": cid}]
                },
                "subject": {"reference": f"urn:uuid:patient-rac-{prontuario.id}"},
            },
        }] if cid else []),
    }


# ── Transmissão HTTP real ao RNDS ─────────────────────────────────────────────

def _transmitir_rnds(bundle_fhir, cred, empresa):
    """
    Envia Bundle FHIR ao RNDS via HTTPS.
    Retorna (ok: bool, protocolo: str | None, erro: str | None).
    Usa o mesmo padrão do e-SUS (views_governo_esus.py): token OAuth2 + mTLS.
    """
    try:
        import requests as req
        import tempfile
        import base64
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

        ambiente = getattr(cred, "rnds_ambiente", "homologacao")
        _URLS = {
            "homologacao": "https://sandbox.rnds.saude.gov.br/api/fhir/r4",
            "producao":    "https://ehr.saude.gov.br/api/fhir/r4",
        }
        base_url = _URLS.get(ambiente, _URLS["homologacao"])

        # Carrega certificado PKCS#12
        pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "")
        if not pfx_b64:
            return False, None, "Certificado RNDS não carregado"

        pfx_bytes = base64.b64decode(pfx_b64)
        senha     = cred.get_rnds_certificado_senha() if hasattr(cred, "get_rnds_certificado_senha") else ""
        senha_bytes = senha.encode() if senha else None

        priv_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, senha_bytes)
        pem_cert = cert.public_bytes(Encoding.PEM)
        pem_key  = priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

        # Escreve PEM temporários com permissões restritas (0o600 — apenas processo atual)
        import os as _os
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as fc:
            cert_path = fc.name
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as fk:
            key_path = fk.name
        _os.chmod(cert_path, 0o600)
        _os.chmod(key_path, 0o600)
        with open(cert_path, "wb") as fc:
            fc.write(pem_cert)
        with open(key_path, "wb") as fk:
            fk.write(pem_key)

        try:
            response = req.post(
                f"{base_url}/Bundle",
                json=bundle_fhir,
                cert=(cert_path, key_path),
                headers={
                    "Content-Type":  "application/fhir+json",
                    "X-Authorization-Server": "Bearer",
                    "RNDS-AUTH-TOKEN": _obter_token_rnds(cred, cert_path, key_path, ambiente),
                },
                timeout=30,
            )

            if response.status_code in (200, 201):
                protocolo = (
                    response.json().get("id") or
                    response.headers.get("Location", "").split("/")[-1]
                )
                return True, protocolo, None
            else:
                return False, None, f"HTTP {response.status_code}: {response.text[:300]}"

        finally:
            import os
            for p in (cert_path, key_path):
                try:
                    os.unlink(p)
                except Exception:
                    pass

    except ImportError:
        return False, None, "Instale 'cryptography' e 'requests' para transmissão RNDS"
    except Exception as e:
        logger.exception("Erro ao transmitir ao RNDS: %s", e)
        return False, None, str(e)[:500]


def _obter_token_rnds(cred, cert_path, key_path, ambiente):
    """
    Obtém token OAuth2 do RNDS usando certificado digital.
    Referência: https://rnds-guia.saude.gov.br/docs/rnds/autenticacao/
    """
    try:
        import requests as req
        _AUTH_URLS = {
            "homologacao": "https://ehr-auth.saude.gov.br/api/token",
            "producao":    "https://ehr-auth.saude.gov.br/api/token",
        }
        auth_url = _AUTH_URLS.get(ambiente, _AUTH_URLS["homologacao"])
        resp = req.post(
            auth_url,
            data={"grant_type": "client_credentials"},
            cert=(cert_path, key_path),
            timeout=15,
        )
        return resp.json().get("access_token", "")
    except Exception:
        return ""


# ── Helper ────────────────────────────────────────────────────────────────────

def _tx_dict(t):
    return {
        "id":            t.id,
        "tipo":          t.tipo,
        "tipo_display":  t.get_tipo_display(),
        "paciente_nome": t.paciente_nome,
        "cns_paciente":  t.cns_paciente,
        "status":        t.status,
        "protocolo_rnds": t.protocolo_rnds,
        "ultimo_erro":   t.ultimo_erro,
        "tentativas":    t.tentativas,
        "criado_em":     t.criado_em.isoformat(),
        "transmitido_em": t.transmitido_em.isoformat() if t.transmitido_em else None,
    }
