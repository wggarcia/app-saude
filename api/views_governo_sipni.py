"""
SIPNI — Sistema de Informação do Programa Nacional de Imunizações
Integrado ao RNDS desde 2021 (Portaria GM/MS nº 1.792/2022).
Vacinações registradas no módulo SST (empresa) ou UBS (governo) são
transmitidas como recursos FHIR `Immunization` ao RNDS/SIPNI.

GET  /api/governo/sipni/status            Status credenciais RNDS
GET  /api/governo/sipni/historico         Histórico de transmissões
POST /api/governo/sipni/transmitir        Transmite lote da competência
POST /api/governo/sipni/reprocessar/<id> Reprocessa lote com erro
GET  /api/governo/sipni/kpis             Cobertura vacinal por competência
"""
import json
import logging
import math
from datetime import date

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)

# Catálogo de imunobiológicos com código SIPNI
_IMUNO_CATALOGO = {
    # vacina_nome (lowercase, partial match) → (código SIPNI, sistema)
    "influenza": ("87", "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "covid":     ("720", "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "hepatite b": ("8",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "hepatite a": ("7",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "tetano":    ("27",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "febre amarela": ("12", "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "sarampo":   ("19",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "pneumo":    ("25",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "meningite": ("20",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
    "varicela":  ("30",  "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"),
}

_RNDS_URLS = {
    "homologacao": "https://sandbox.rnds.saude.gov.br/api/fhir/r4",
    "producao":    "https://ehr.saude.gov.br/api/fhir/r4",
}


def _gov(request):
    emp = empresa_autenticada_from_request(request)
    if emp and emp.tipo_conta == "governo":
        return emp
    return None


def _get_cred(empresa):
    try:
        from .models import CredenciaisIntegracoes
        cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
        return cred
    except Exception:
        return None


# ── Status ────────────────────────────────────────────────────────────────────

def api_sipni_status(request):
    """GET /api/governo/sipni/status."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    cred = _get_cred(empresa)
    configurado = cred.rnds_configurado() if cred and hasattr(cred, "rnds_configurado") else False

    from .models import TransmissaoSIPNI
    ultima = TransmissaoSIPNI.objects.filter(empresa=empresa).first()

    return JsonResponse({
        "configurado":          configurado,
        "ambiente":             getattr(cred, "rnds_ambiente", "homologacao") if cred else None,
        "cnes":                 getattr(cred, "rnds_cnes", "") if cred else None,
        "ultima_transmissao":   ultima.transmitido_em.isoformat() if ultima and ultima.transmitido_em else None,
        "ultimo_status":        ultima.status if ultima else None,
        "aviso": (
            "Configure as credenciais RNDS em Configurações → Integrações → RNDS. "
            "O SIPNI usa as mesmas credenciais do RNDS."
        ) if not configurado else None,
    })


# ── Histórico ─────────────────────────────────────────────────────────────────

def api_sipni_historico(request):
    """GET /api/governo/sipni/historico."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import TransmissaoSIPNI

    page = max(1, int(request.GET.get("page") or 1))
    ps   = 30

    qs    = TransmissaoSIPNI.objects.filter(empresa=empresa)
    total = qs.count()
    items = qs[(page - 1) * ps: page * ps]

    return JsonResponse({
        "total":   total,
        "pagina":  page,
        "paginas": math.ceil(total / ps) if total else 1,
        "transmissoes": [_tx_dict(t) for t in items],
    })


# ── Transmitir ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_sipni_transmitir(request):
    """
    POST /api/governo/sipni/transmitir
    Body: {"competencia": "202601"}

    Coleta RegistroVacinacao (SST) e CampanhaVacinacao da competência
    e envia como Bundle FHIR Immunization ao RNDS/SIPNI.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    competencia = (body.get("competencia") or date.today().strftime("%Y%m")).strip()
    if len(competencia) != 6 or not competencia.isdigit():
        return JsonResponse({"erro": "competencia deve ser AAAAMM (ex: 202601)"}, status=400)

    cred = _get_cred(empresa)
    if not cred or not (cred.rnds_configurado() if hasattr(cred, "rnds_configurado") else False):
        return JsonResponse({
            "erro": "Credenciais RNDS não configuradas.",
            "codigo": "rnds_nao_configurado",
        }, status=422)

    # Coleta registros de vacinação da competência
    registros = _coletar_registros(empresa, competencia)
    total = len(registros)

    if total == 0:
        return JsonResponse({
            "ok":         True,
            "competencia": competencia,
            "total":      0,
            "mensagem":   "Nenhum registro de vacinação encontrado para esta competência.",
        })

    from .models import TransmissaoSIPNI

    tx = TransmissaoSIPNI.objects.create(
        empresa         = empresa,
        competencia     = competencia,
        total_registros = total,
        status          = "pendente",
    )

    # Transmite em lotes de 50
    transmitidos = 0
    erros_count  = 0
    protocolo    = ""
    ultimo_erro  = ""

    for i in range(0, total, 50):
        lote       = registros[i: i + 50]
        bundle     = _gerar_bundle_immunization(lote, empresa, cred, competencia)
        ok, prot, err = _transmitir_rnds_sipni(bundle, cred)
        if ok:
            transmitidos += len(lote)
            protocolo     = prot or protocolo
        else:
            erros_count  += len(lote)
            ultimo_erro   = err or ""

    tx.transmitidos   = transmitidos
    tx.erros          = erros_count
    tx.protocolo      = protocolo
    tx.status         = (
        "transmitido" if erros_count == 0
        else ("parcial" if transmitidos > 0 else "erro")
    )
    if transmitidos > 0:
        tx.transmitido_em = timezone.now()
        tx.resposta_sipni = {"protocolo": protocolo}
    if ultimo_erro:
        tx.resposta_sipni = {"erro": ultimo_erro}
    tx.save()

    return JsonResponse({
        "ok":            erros_count == 0,
        "transmissao_id": tx.id,
        "competencia":   competencia,
        "total":         total,
        "transmitidos":  transmitidos,
        "erros":         erros_count,
        "protocolo":     protocolo,
        "status":        tx.status,
        "mensagem": (
            f"{transmitidos} registro(s) transmitido(s) ao SIPNI com sucesso."
            if erros_count == 0
            else f"{transmitidos} transmitidos, {erros_count} com erro. Reprocesse os erros."
        ),
    }, status=200 if erros_count == 0 else 207)


@csrf_exempt
def api_sipni_reprocessar(request, tx_id):
    """POST /api/governo/sipni/reprocessar/<id>."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import TransmissaoSIPNI

    try:
        tx = TransmissaoSIPNI.objects.get(id=tx_id, empresa=empresa)
    except TransmissaoSIPNI.DoesNotExist:
        return JsonResponse({"erro": "Transmissão não encontrada"}, status=404)

    if tx.status == "transmitido":
        return JsonResponse({"aviso": "Transmissão já bem-sucedida.", "protocolo": tx.protocolo})

    cred     = _get_cred(empresa)
    registros = _coletar_registros(empresa, tx.competencia)
    bundle   = _gerar_bundle_immunization(registros, empresa, cred, tx.competencia)
    ok, prot, err = _transmitir_rnds_sipni(bundle, cred)

    tx.transmitidos  = len(registros) if ok else 0
    tx.erros         = 0 if ok else len(registros)
    tx.status        = "transmitido" if ok else "erro"
    tx.protocolo     = prot or ""
    tx.resposta_sipni = {"protocolo": prot} if ok else {"erro": err}
    if ok:
        tx.transmitido_em = timezone.now()
    tx.save()

    return JsonResponse({
        "ok":        ok,
        "status":    tx.status,
        "protocolo": prot,
        "mensagem":  "Reprocessado com sucesso." if ok else f"Erro: {err}",
    }, status=200 if ok else 422)


# ── KPIs ─────────────────────────────────────────────────────────────────────

def api_sipni_kpis(request):
    """GET /api/governo/sipni/kpis."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import TransmissaoSIPNI, RegistroVacinacao, CampanhaVacinacao
    from django.db.models import Sum

    comp_atual  = date.today().strftime("%Y%m")
    txs         = TransmissaoSIPNI.objects.filter(empresa=empresa)
    ultima_ok   = txs.filter(status__in=("transmitido", "parcial")).first()

    total_reg   = RegistroVacinacao.objects.filter(
        campanha__empresa=empresa
    ).count()

    transmitidos_total = txs.aggregate(t=Sum("transmitidos"))["t"] or 0

    return JsonResponse({
        "competencia_atual":     comp_atual,
        "total_registros_sistema": total_reg,
        "total_transmitidos_sipni": transmitidos_total,
        "cobertura_pct": round(transmitidos_total / total_reg * 100, 1) if total_reg else 0,
        "ultima_transmissao": ultima_ok.transmitido_em.isoformat() if ultima_ok and ultima_ok.transmitido_em else None,
        "transmissoes_com_erro": txs.filter(status="erro").count(),
        "historico_resumo": [_tx_dict(t) for t in txs[:5]],
    })


# ── Helpers internos ──────────────────────────────────────────────────────────

def _coletar_registros(empresa, competencia):
    """Coleta RegistroVacinacao da competência para a empresa governo."""
    from .models import RegistroVacinacao, CampanhaVacinacao, UnidadeSaude
    from datetime import datetime

    # competencia = AAAAMM
    try:
        ano  = int(competencia[:4])
        mes  = int(competencia[4:6])
        ini  = date(ano, mes, 1)
        fim_mes = date(ano, mes + 1, 1) if mes < 12 else date(ano + 1, 1, 1)
    except (ValueError, TypeError):
        return []

    registros = RegistroVacinacao.objects.filter(
        campanha__empresa=empresa,
        data_aplicacao__gte=ini,
        data_aplicacao__lt=fim_mes,
    ).select_related("campanha", "funcionario")

    return list(registros)


def _codigo_imuno(vacina_nome):
    """Mapeia nome da vacina para código SIPNI."""
    nome_lower = vacina_nome.lower()
    for keyword, (codigo, sistema) in _IMUNO_CATALOGO.items():
        if keyword in nome_lower:
            return codigo, sistema
    return "999", "http://www.saude.gov.br/fhir/r4/CodeSystem/BRSIGTAP"


def _gerar_bundle_immunization(registros, empresa, cred, competencia):
    """Gera Bundle FHIR R4 com recursos Immunization para o SIPNI."""
    entries = []
    cnes    = getattr(cred, "rnds_cnes", "") or ""

    for reg in registros:
        func       = reg.funcionario
        campanha   = reg.campanha
        codigo, sistema = _codigo_imuno(campanha.vacina)

        entries.append({
            "fullUrl":  f"urn:uuid:imun-{reg.id}",
            "resource": {
                "resourceType": "Immunization",
                "status":       "completed",
                "vaccineCode": {
                    "coding": [{
                        "system":  sistema,
                        "code":    codigo,
                        "display": campanha.vacina,
                    }]
                },
                "patient": {
                    "identifier": {
                        "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
                        "value":  getattr(func, "cpf", "") or "",
                    },
                    "display": func.nome,
                },
                "occurrenceDateTime": reg.data_aplicacao.isoformat(),
                "lotNumber":          reg.lote_vacina or "",
                "performer": [{
                    "actor": {
                        "identifier": {
                            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnes",
                            "value":  cnes,
                        },
                        "display": empresa.nome,
                    }
                }],
                "protocolApplied": [{
                    "doseNumberString": reg.get_dose_display(),
                }],
                "meta": {
                    "profile": ["https://rnds-fhir.saude.gov.br/StructureDefinition/BRImunobiologicoAdministrado-1.0"]
                },
            }
        })

    return {
        "resourceType": "Bundle",
        "type":         "batch",
        "timestamp":    timezone.now().isoformat(),
        "entry":        entries,
    }


def _transmitir_rnds_sipni(bundle, cred):
    """Envia Bundle ao RNDS via HTTPS. Retorna (ok, protocolo, erro)."""
    try:
        import requests as req
        import tempfile
        import base64
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

        ambiente = getattr(cred, "rnds_ambiente", "homologacao")
        base_url = _RNDS_URLS.get(ambiente, _RNDS_URLS["homologacao"])

        pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "")
        if not pfx_b64:
            return False, None, "Certificado RNDS não carregado"

        pfx_bytes   = base64.b64decode(pfx_b64)
        senha       = cred.get_rnds_certificado_senha() if hasattr(cred, "get_rnds_certificado_senha") else ""
        senha_bytes = senha.encode() if senha else None

        priv_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, senha_bytes)
        pem_cert = cert.public_bytes(Encoding.PEM)
        pem_key  = priv_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as fc:
            fc.write(pem_cert); cert_path = fc.name
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as fk:
            fk.write(pem_key); key_path = fk.name

        try:
            resp = req.post(
                f"{base_url}/Bundle",
                json=bundle,
                cert=(cert_path, key_path),
                headers={"Content-Type": "application/fhir+json"},
                timeout=30,
            )
            if resp.status_code in (200, 201):
                protocolo = resp.json().get("id") or resp.headers.get("Location", "").split("/")[-1]
                return True, protocolo, None
            return False, None, f"HTTP {resp.status_code}: {resp.text[:300]}"
        finally:
            import os
            for p in (cert_path, key_path):
                try: os.unlink(p)
                except Exception: pass

    except ImportError:
        return False, None, "Instale 'cryptography' e 'requests'"
    except Exception as e:
        logger.exception("Erro SIPNI: %s", e)
        return False, None, str(e)[:500]


def _tx_dict(t):
    return {
        "id":            t.id,
        "competencia":   t.competencia,
        "total":         t.total_registros,
        "transmitidos":  t.transmitidos,
        "erros":         t.erros,
        "status":        t.status,
        "protocolo":     t.protocolo,
        "criado_em":     t.criado_em.isoformat(),
        "transmitido_em": t.transmitido_em.isoformat() if t.transmitido_em else None,
    }
