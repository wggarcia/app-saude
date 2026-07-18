"""
CEAF — Componente Especializado da Assistência Farmacêutica
Gestão de LME (Laudo para Solicitação, Avaliação e Autorização),
dispensação de medicamentos de alto custo e relatório HÓRUS/BNAFAR.
Portaria GM/MS 1.554/2013 | RDC ANVISA 204/2017

Integração HÓRUS/BNAFAR: RNDS FHIR R4 MedicationDispense
  • Autenticação: certificado ICP-Brasil A1/A3 (PKCS#12) por empresa
  • Endpoint prod:  https://ehr.saude.gov.br/api/fhir/r4/Bundle
  • Endpoint hmg:   https://ehr-hmg.saude.gov.br/api/fhir/r4/Bundle
  • Profile FHIR:   BRDispensacaoMedicamento-1.0
  • Credenciais configuradas em: Integrações → RNDS
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_permissao_modulo
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .services.rnds_fhir import transmitir_bundle, get_cred as _rnds_cred

logger = logging.getLogger(__name__)


def _e(request):
    empresa = get_empresa(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa

# ── Catálogo RENAME 7ª Edição (2020) — Componente Especializado ───────────────
# Código: CATMAT DATASUS (código de sequência do Banco de Preços em Saúde / BPS)
# Fonte: RENAME 2020 (Portaria GM/MS 2.012/2019) + CATMAT/DATASUS
# Os CIDs (grupo_diagnostico) seguem ATC OMS.
# Operadores devem manter o catálogo atualizado via painel de Integrações → CEAF.
_RENAME_SEEDS = [
    # (codigo_catmat,   principio_ativo,       concentracao,   forma,             componente, atc)
    ("0136280",  "Metotrexato",          "2,5 mg",    "comprimido",             "II",  "L04AX03"),
    ("0620420",  "Infliximabe",          "100 mg",    "pó p/ sol. injetável",   "I-A", "L04AB02"),
    ("0724770",  "Adalimumabe",          "40 mg",     "sol. injetável",         "I-A", "L04AB04"),
    ("0725013",  "Trastuzumabe",         "440 mg",    "pó p/ sol. injetável",   "I-A", "L01FD01"),
    ("0519847",  "Imatinibe",            "100 mg",    "comprimido revestido",   "I-A", "L01EA01"),
    ("0535416",  "Insulina Glargina",    "100 UI/mL", "sol. injetável",         "I-B", "A10AE04"),
    ("0221014",  "Rivastigmina",         "3 mg",      "cápsula",                "II",  "N06DA03"),
    ("0707155",  "Acetato de Glatirâmer","20 mg",     "sol. injetável",         "I-A", "L03AX13"),
    ("0515531",  "Tacrolimo",            "1 mg",      "cápsula",                "I-A", "L04AD02"),
    ("0221325",  "Micofenolato de Mofetila","500 mg", "comprimido revestido",   "I-B", "L04AA06"),
    ("0519820",  "Leflunomida",          "20 mg",     "comprimido",             "II",  "L04AA13"),
    ("0469076",  "Interferona Beta-1a",  "30 mcg",    "sol. injetável",         "I-A", "L03AB07"),
    ("0222237",  "Ciclosporina",         "25 mg",     "cápsula",                "I-A", "L04AD01"),
    ("0519863",  "Micofenolato de Sódio","360 mg",    "comprimido gastrorresistente","I-B","L04AA06"),
    ("0469092",  "Sevelâmer",            "800 mg",    "comprimido",             "II",  "V03AE02"),
]


def _get_ceaf_models():
    from .models import MedicamentoCEAF, SolicitacaoCEAF, DispensacaoCEAF
    return MedicamentoCEAF, SolicitacaoCEAF, DispensacaoCEAF


# ── catálogo RENAME ────────────────────────────────────────────────────────────

def api_ceaf_medicamentos(request):
    """GET /api/governo/ceaf/medicamentos/ — catálogo RENAME com filtros."""
    MedicamentoCEAF, *_ = _get_ceaf_models()

    # Seed automático se catálogo vazio
    if MedicamentoCEAF.objects.count() == 0:
        for cod, pa, conc, forma, comp, cid in _RENAME_SEEDS:
            MedicamentoCEAF.objects.get_or_create(
                codigo_rename=cod,
                defaults={
                    "principio_ativo": pa,
                    "concentracao": conc,
                    "forma_farmaceutica": forma,
                    "componente": comp,
                    "grupo_diagnostico": cid,
                    "ativo": True,
                },
            )

    qs = MedicamentoCEAF.objects.filter(ativo=True)
    q = request.GET.get("q")
    componente = request.GET.get("componente")
    if q:
        qs = qs.filter(Q(principio_ativo__icontains=q) | Q(codigo_rename__icontains=q)
                       | Q(cids_validos__icontains=q))
    if componente:
        qs = qs.filter(componente=componente)

    return JsonResponse({
        "total": qs.count(),
        "medicamentos": [
            {
                "id": m.id,
                "codigo_rename": m.codigo_rename,
                "principio_ativo": m.principio_ativo,
                "concentracao": m.concentracao,
                "forma_farmaceutica": m.forma_farmaceutica,
                "componente": m.componente,
                "componente_display": m.get_componente_display(),
                "grupo_diagnostico": m.grupo_diagnostico,
                "cids_validos": m.cids_validos,
                "dose_padrao": m.dose_padrao,
            }
            for m in qs.order_by("principio_ativo")
        ],
    })


# ── LME / solicitações ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.farmacia", "governo.atencao_clinica")
def api_ceaf_solicitacoes(request):
    """GET/POST /api/governo/ceaf/solicitacoes/"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    MedicamentoCEAF, SolicitacaoCEAF, DispensacaoCEAF = _get_ceaf_models()

    if request.method == "GET":
        qs = SolicitacaoCEAF.objects.filter(empresa=empresa).select_related("medicamento")
        status_f = request.GET.get("status")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q)
                           | Q(numero_lme__icontains=q))

        return JsonResponse({
            "total": qs.count(),
            "solicitacoes": [
                {
                    "id": s.id,
                    "numero_lme": s.numero_lme,
                    "paciente_nome": s.paciente_nome,
                    "cpf_paciente": s.cpf_paciente,
                    "cns_paciente": s.cns_paciente,
                    "medicamento_pa": s.medicamento.principio_ativo,
                    "medicamento_componente": s.medicamento.componente,
                    "cid10_principal": s.cid10_principal,
                    "medico_solicitante": s.medico_solicitante,
                    "dose_prescrita": s.dose_prescrita,
                    "status": s.status,
                    "status_display": s.get_status_display(),
                    "data_solicitacao": s.data_solicitacao.isoformat(),
                    "data_validade": s.data_validade.isoformat() if s.data_validade else None,
                    "vencida": bool(s.data_validade and s.data_validade < date.today()),
                }
                for s in qs.order_by("-criado_em")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    try:
        med = MedicamentoCEAF.objects.get(id=data["medicamento_id"])
    except MedicamentoCEAF.DoesNotExist:
        return JsonResponse({"erro": "Medicamento não encontrado no RENAME CEAF"}, status=404)

    # Número LME sequencial
    total = SolicitacaoCEAF.objects.filter(empresa=empresa).count() + 1
    numero_lme = f"LME-{empresa.id:06d}-{total:06d}"

    # Validade padrão por componente
    validade_meses = {"I-A": 6, "I-B": 12, "II": 12, "III": 6}
    meses = validade_meses.get(med.componente, 6)
    validade = date.today().replace(day=1) + timedelta(days=30 * meses)

    with transaction.atomic():
        sol = SolicitacaoCEAF.objects.create(
            empresa=empresa,
            medicamento=med,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data["cpf_paciente"],
            cns_paciente=data.get("cns_paciente", ""),
            data_nascimento=data.get("data_nascimento"),
            cid10_principal=data["cid10_principal"],
            cid10_secundario=data.get("cid10_secundario", ""),
            medico_solicitante=data["medico_solicitante"],
            crm_medico=data.get("crm_medico", ""),
            dose_prescrita=data.get("dose_prescrita", ""),
            duracao_tratamento=data.get("duracao_tratamento", ""),
            justificativa=data.get("justificativa", ""),
            status="em_analise",
            numero_lme=numero_lme,
            data_validade=data.get("data_validade") or validade.isoformat(),
        )
    return JsonResponse({"id": sol.id, "numero_lme": numero_lme}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_permissao_modulo("governo.farmacia", "governo.atencao_clinica")
def api_ceaf_solicitacao_detalhe(request, sol_id):
    """GET/PUT /api/governo/ceaf/solicitacoes/<id>/"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, SolicitacaoCEAF, DispensacaoCEAF = _get_ceaf_models()
    try:
        sol = SolicitacaoCEAF.objects.get(id=sol_id, empresa=empresa)
    except SolicitacaoCEAF.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        dispensacoes = DispensacaoCEAF.objects.filter(solicitacao=sol).order_by("-data_dispensacao")
        return JsonResponse({
            "id": sol.id,
            "numero_lme": sol.numero_lme,
            "paciente_nome": sol.paciente_nome,
            "cpf_paciente": sol.cpf_paciente,
            "cns_paciente": sol.cns_paciente,
            "medicamento": {
                "id": sol.medicamento.id,
                "principio_ativo": sol.medicamento.principio_ativo,
                "concentracao": sol.medicamento.concentracao,
                "componente": sol.medicamento.componente,
                "codigo_rename": sol.medicamento.codigo_rename,
            },
            "cid10_principal": sol.cid10_principal,
            "medico_solicitante": sol.medico_solicitante,
            "dose_prescrita": sol.dose_prescrita,
            "duracao_tratamento": sol.duracao_tratamento,
            "justificativa": sol.justificativa,
            "status": sol.status,
            "status_display": sol.get_status_display(),
            "data_solicitacao": sol.data_solicitacao.isoformat(),
            "data_validade": sol.data_validade.isoformat() if sol.data_validade else None,
            "obs_farmaceutico": sol.obs_farmaceutico,
            "dispensacoes": [
                {
                    "id": d.id,
                    "data_dispensacao": d.data_dispensacao.isoformat(),
                    "quantidade": d.quantidade,
                    "lote": d.lote,
                    "horus_enviado": d.horus_enviado,
                }
                for d in dispensacoes
            ],
        })

    data = json.loads(request.body)
    campos = ["status", "obs_farmaceutico", "data_validade"]
    for c in campos:
        if c in data:
            setattr(sol, c, data[c])
    sol.save()
    return JsonResponse({"ok": True})


# ── dispensação ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.farmacia", "governo.atencao_clinica")
def api_ceaf_dispensar(request, sol_id):
    """POST /api/governo/ceaf/solicitacoes/<id>/dispensar/ — registra dispensação."""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, SolicitacaoCEAF, DispensacaoCEAF = _get_ceaf_models()
    try:
        sol = SolicitacaoCEAF.objects.get(id=sol_id, empresa=empresa)
    except SolicitacaoCEAF.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if sol.status == "negada":
        return JsonResponse({"erro": "Solicitação negada — dispensação bloqueada"}, status=400)

    if sol.data_validade and sol.data_validade < date.today():
        return JsonResponse({"erro": "Autorização vencida — renove a LME"}, status=400)

    data = json.loads(request.body)
    with transaction.atomic():
        disp = DispensacaoCEAF.objects.create(
            empresa=empresa,
            solicitacao=sol,
            data_dispensacao=data.get("data_dispensacao", date.today().isoformat()),
            quantidade=data.get("quantidade", 1),
            lote=data.get("lote", ""),
            validade_lote=data.get("validade_lote"),
            fabricante=data.get("fabricante", ""),
            farmaceutico=data.get("farmaceutico", ""),
            crf_farmaceutico=data.get("crf_farmaceutico", ""),
            obs=data.get("obs", ""),
        )
        # Atualiza status para aprovada se ainda em análise
        if sol.status == "em_analise":
            sol.status = "aprovada"
            sol.save()

    return JsonResponse({"id": disp.id}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.farmacia", "governo.atencao_clinica")
def api_ceaf_horus_enviar(request, disp_id):
    """
    POST /api/governo/ceaf/dispensacoes/<id>/horus/

    Transmite dispensação ao BNAFAR/HÓRUS via RNDS FHIR R4 (MedicationDispense).
    Requer certificado ICP-Brasil A1/A3 configurado em Integrações → RNDS.

    Referência RNDS:
      Profile: BRDispensacaoMedicamento-1.0
      https://simplifier.net/redenacionaldedadosemsaude
    """
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, DispensacaoCEAF = _get_ceaf_models()
    try:
        disp = DispensacaoCEAF.objects.get(id=disp_id, solicitacao__empresa=empresa)
    except DispensacaoCEAF.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if disp.horus_enviado:
        return JsonResponse({"ok": True, "protocolo": disp.horus_protocolo,
                             "mensagem": "Já transmitido ao BNAFAR/HÓRUS via RNDS"})

    cred = _rnds_cred(empresa)
    if not cred or not (cred.rnds_configurado() if hasattr(cred, "rnds_configurado") else False):
        return JsonResponse({
            "erro": "Credenciais RNDS não configuradas.",
            "instrucao": "Configure o certificado ICP-Brasil em Configurações → Integrações → RNDS.",
            "codigo": "rnds_nao_configurado",
        }, status=422)

    sol = disp.solicitacao
    med = sol.medicamento
    cnes = getattr(cred, "rnds_cnes", "") or getattr(cred, "sus_cnes", "")

    # Bundle FHIR R4 — MedicationDispense para BNAFAR
    bundle = {
        "resourceType": "Bundle",
        "type": "batch",
        "timestamp": timezone.now().isoformat(),
        "entry": [{
            "fullUrl": f"urn:uuid:ceaf-disp-{disp.id}",
            "request": {"method": "POST", "url": "MedicationDispense"},
            "resource": {
                "resourceType": "MedicationDispense",
                "meta": {
                    "profile": [
                        "https://rnds-fhir.saude.gov.br/StructureDefinition/BRDispensacaoMedicamento-1.0"
                    ]
                },
                "status": "completed",
                "medicationCodeableConcept": {
                    "coding": [{
                        # Sistema CATMAT — código usado pelo BNAFAR/HÓRUS
                        "system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRNomesMedicamentos",
                        "code":    med.codigo_rename,
                        "display": f"{med.principio_ativo} {med.concentracao} {med.forma_farmaceutica}",
                    }]
                },
                "subject": {
                    "identifier": {
                        "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns",
                        "value":   sol.cns_paciente,
                    },
                    "display": sol.paciente_nome,
                },
                "performer": [{
                    "actor": {
                        "identifier": {
                            "system": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnes",
                            "value":   cnes,
                        },
                        "display": empresa.nome,
                    }
                }],
                "authorizingPrescription": [{
                    "identifier": {
                        "system": "https://rnds-fhir.saude.gov.br/NamingSystem/BRNumeroLME",
                        "value":   sol.numero_lme,
                    }
                }],
                "quantity": {
                    "value": float(disp.quantidade),
                    "unit":  med.forma_farmaceutica,
                    "system": "http://unitsofmeasure.org",
                },
                "whenHandedOver": (
                    disp.data_dispensacao.isoformat()
                    if hasattr(disp.data_dispensacao, "isoformat")
                    else str(disp.data_dispensacao)
                ),
                "lotNumber": disp.lote or "",
                **({"note": [{"text": disp.obs}]} if disp.obs else {}),
            },
        }],
    }

    ok, protocolo, erro = transmitir_bundle(bundle, cred)

    if ok:
        disp.horus_enviado   = True
        disp.horus_protocolo = protocolo
        disp.save()
        return JsonResponse({
            "ok": True,
            "protocolo": protocolo,
            "mensagem": "Dispensação transmitida ao BNAFAR/HÓRUS via RNDS com sucesso.",
        })
    else:
        logger.error("Erro RNDS BNAFAR disp %s: %s", disp_id, erro)
        return JsonResponse({"ok": False, "erro": erro}, status=502)


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.farmacia", "governo.atencao_clinica")
def api_ceaf_kpis(request):
    """GET /api/governo/ceaf/kpis/"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, SolicitacaoCEAF, DispensacaoCEAF = _get_ceaf_models()

    hoje = date.today()
    mes_ini = hoje.replace(day=1)

    sol_qs = SolicitacaoCEAF.objects.filter(empresa=empresa)
    por_status = dict(sol_qs.values_list("status").annotate(n=Count("id")).order_by())
    vencidas = sol_qs.filter(
        status="aprovada", data_validade__lt=hoje
    ).count()
    vencendo_30d = sol_qs.filter(
        status="aprovada",
        data_validade__gte=hoje,
        data_validade__lte=hoje + timedelta(days=30),
    ).count()
    disp_mes = DispensacaoCEAF.objects.filter(
        solicitacao__empresa=empresa,
        data_dispensacao__gte=mes_ini,
    ).count()
    pendente_horus = DispensacaoCEAF.objects.filter(
        solicitacao__empresa=empresa,
        horus_enviado=False,
    ).count()

    return JsonResponse({
        "solicitacoes_por_status": por_status,
        "lmes_vencidas": vencidas,
        "lmes_vencendo_30d": vencendo_30d,
        "dispensacoes_mes": disp_mes,
        "pendente_horus": pendente_horus,
    })
