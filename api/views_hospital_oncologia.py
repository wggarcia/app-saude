"""
Oncologia — Alta Complexidade
Protocolos quimioterápicos (PCDT/INCA), ciclos, APAC SUS faturamento e
toxicidade CTCAE v5.0.
"""
import json
import logging
from datetime import date, timedelta
import math

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .utils import validar_cpf_cadastro
from .access_control import (
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.oncologia", "Oncologia")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_oncologia_page(request):
    return render(request, "hospital_oncologia.html")

# Protocolos PCDT/INCA mais prevalentes para seed
_PROTOCOLOS_SEED = [
    ("FOLFOX-6",   "C18", "EV", 12, 14, [
        {"droga": "Oxaliplatina", "dose": 85, "unidade": "mg/m²", "dia": 1},
        {"droga": "Leucovorina",  "dose": 400, "unidade": "mg/m²", "dia": 1},
        {"droga": "Fluorouracila","dose": 400, "unidade": "mg/m²", "dia": 1, "modo": "bolus"},
        {"droga": "Fluorouracila","dose": 2400, "unidade": "mg/m²", "dia": "1-2", "modo": "CI 46h"},
    ]),
    ("FOLFIRI",    "C18", "EV", 12, 14, [
        {"droga": "Irinotecana",  "dose": 180, "unidade": "mg/m²", "dia": 1},
        {"droga": "Leucovorina",  "dose": 400, "unidade": "mg/m²", "dia": 1},
        {"droga": "Fluorouracila","dose": 400, "unidade": "mg/m²", "dia": 1, "modo": "bolus"},
        {"droga": "Fluorouracila","dose": 2400, "unidade": "mg/m²", "dia": "1-2", "modo": "CI 46h"},
    ]),
    ("AC-T",       "C50", "EV", 8, 21, [
        {"droga": "Doxorrubicina","dose": 60, "unidade": "mg/m²", "dia": 1, "ciclos": "1-4"},
        {"droga": "Ciclofosfamida","dose": 600,"unidade": "mg/m²", "dia": 1, "ciclos": "1-4"},
        {"droga": "Paclitaxel",  "dose": 175, "unidade": "mg/m²", "dia": 1, "ciclos": "5-8"},
    ]),
    ("BEP",        "C62", "EV", 3, 21, [
        {"droga": "Bleomicina",  "dose": 30, "unidade": "UI", "dia": "1,8,15"},
        {"droga": "Etoposida",   "dose": 100,"unidade": "mg/m²", "dia": "1-5"},
        {"droga": "Cisplatina",  "dose": 20, "unidade": "mg/m²", "dia": "1-5"},
    ]),
    ("CHOP",       "C83", "EV", 6, 21, [
        {"droga": "Ciclofosfamida","dose": 750,"unidade": "mg/m²", "dia": 1},
        {"droga": "Doxorrubicina","dose": 50, "unidade": "mg/m²", "dia": 1},
        {"droga": "Vincristina", "dose": 1.4, "unidade": "mg/m²", "dia": 1},
        {"droga": "Prednisona",  "dose": 100,"unidade": "mg/dia",  "dia": "1-5"},
    ]),
]


def _get_onco_models():
    from .models import ProtocoloOncologico, CicloQuimioterapia, APACOncologia, ToxicidadeQuimio
    return ProtocoloOncologico, CicloQuimioterapia, APACOncologia, ToxicidadeQuimio


def _sc_dubois(peso_kg, altura_cm):
    """Superfície corporal DuBois & DuBois."""
    if peso_kg and altura_cm:
        return round(0.20247 * (float(altura_cm) / 100) ** 0.725 * float(peso_kg) ** 0.425, 4)
    return None


# ── Protocolos ─────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.oncologia")
def api_onco_protocolos(request):
    """GET /api/hospital/oncologia/protocolos/ — catálogo com seed PCDT."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProtocoloOncologico, *_ = _get_onco_models()

    # Seed automático
    if ProtocoloOncologico.objects.filter(empresa=empresa).count() == 0:
        for nome, cid, via, ciclos, intervalo, drogas in _PROTOCOLOS_SEED:
            ProtocoloOncologico.objects.get_or_create(
                empresa=empresa, codigo=nome,
                defaults={
                    "nome": nome,
                    "indicacao_cid": cid,
                    "via": via,
                    "ciclos_total": ciclos,
                    "intervalo_dias": intervalo,
                    "drogas": drogas,
                    "ativo": True,
                },
            )

    qs = ProtocoloOncologico.objects.filter(empresa=empresa, ativo=True)
    cid_f = request.GET.get("cid")
    q     = request.GET.get("q")

    if cid_f:
        qs = qs.filter(indicacao_cid__icontains=cid_f)
    if q:
        qs = qs.filter(Q(nome__icontains=q) | Q(codigo__icontains=q))

    return JsonResponse({
        "total": qs.count(),
        "protocolos": [
            {
                "id": p.id,
                "codigo": p.codigo,
                "nome": p.nome,
                "indicacao_cid": p.indicacao_cid,
                "via": p.via,
                "ciclos_total": p.ciclos_total,
                "intervalo_dias": p.intervalo_dias,
                "drogas": p.drogas,
            }
            for p in qs.order_by("nome")
        ],
    })


# ── Ciclos ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
def api_onco_ciclos(request):
    """GET/POST /api/hospital/oncologia/ciclos/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProtocoloOncologico, CicloQuimioterapia, *_ = _get_onco_models()

    if request.method == "GET":
        qs = CicloQuimioterapia.objects.filter(empresa=empresa).select_related("protocolo")
        status_f = request.GET.get("status")
        q        = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "ciclos": [
                {
                    "id": c.id,
                    "protocolo": c.protocolo.codigo,
                    "paciente_nome": c.paciente_nome,
                    "cpf_paciente": c.cpf_paciente,
                    "cid10_principal": c.cid10_principal,
                    "numero_ciclo": c.numero_ciclo,
                    "data_inicio": c.data_inicio.isoformat(),
                    "data_fim": c.data_fim.isoformat() if c.data_fim else None,
                    "status": c.status,
                    "status_display": c.get_status_display(),
                    "sc_m2": float(c.sc_m2) if c.sc_m2 else None,
                }
                for c in qs.order_by("-data_inicio")[:200]
            ],
        })

    data = json.loads(request.body)
    try:
        protocolo = ProtocoloOncologico.objects.get(id=data["protocolo_id"], empresa=empresa)
    except ProtocoloOncologico.DoesNotExist:
        return JsonResponse({"erro": "Protocolo não encontrado"}, status=404)

    peso    = data.get("peso_kg")
    altura  = data.get("altura_cm")
    sc_m2   = _sc_dubois(peso, altura) if peso and altura else None

    with transaction.atomic():
        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        ciclo = CicloQuimioterapia.objects.create(
            empresa=empresa,
            protocolo=protocolo,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            cid10_principal=data["cid10_principal"],
            numero_ciclo=data.get("numero_ciclo", 1),
            data_inicio=data["data_inicio"],
            data_fim=data.get("data_fim"),
            medico_oncologista=data.get("medico_oncologista", ""),
            crm=data.get("crm", ""),
            peso_kg=peso,
            altura_cm=altura,
            sc_m2=sc_m2,
            obs=data.get("obs", ""),
        )
    return JsonResponse({"id": ciclo.id, "sc_m2": sc_m2}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_feature("hospital.oncologia")
def api_onco_ciclo_detalhe(request, ciclo_id):
    """GET/PUT /api/hospital/oncologia/ciclos/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, _, ToxicidadeQuimio = _get_onco_models()
    try:
        ciclo = CicloQuimioterapia.objects.get(id=ciclo_id, empresa=empresa)
    except CicloQuimioterapia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        toxs = ToxicidadeQuimio.objects.filter(ciclo=ciclo).order_by("-data_registro")
        return JsonResponse({
            "id": ciclo.id,
            "protocolo": {"id": ciclo.protocolo.id, "codigo": ciclo.protocolo.codigo,
                          "nome": ciclo.protocolo.nome, "drogas": ciclo.protocolo.drogas},
            "paciente_nome": ciclo.paciente_nome,
            "cpf_paciente": ciclo.cpf_paciente,
            "cid10_principal": ciclo.cid10_principal,
            "numero_ciclo": ciclo.numero_ciclo,
            "data_inicio": ciclo.data_inicio.isoformat(),
            "data_fim": ciclo.data_fim.isoformat() if ciclo.data_fim else None,
            "status": ciclo.status,
            "status_display": ciclo.get_status_display(),
            "peso_kg": float(ciclo.peso_kg) if ciclo.peso_kg else None,
            "altura_cm": float(ciclo.altura_cm) if ciclo.altura_cm else None,
            "sc_m2": float(ciclo.sc_m2) if ciclo.sc_m2 else None,
            "medico_oncologista": ciclo.medico_oncologista,
            "obs": ciclo.obs,
            "toxicidades": [
                {
                    "id": t.id,
                    "categoria": t.categoria,
                    "grau": t.grau,
                    "grau_display": t.get_grau_display(),
                    "data_registro": t.data_registro.isoformat(),
                    "dose_reduzida": t.dose_reduzida,
                    "ciclo_suspenso": t.ciclo_suspenso,
                }
                for t in toxs
            ],
        })

    data = json.loads(request.body)
    campos = ["status", "data_fim", "obs"]
    for c in campos:
        if c in data:
            setattr(ciclo, c, data[c])
    ciclo.save()
    return JsonResponse({"ok": True})


# ── Toxicidade ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.oncologia")
def api_onco_toxicidade(request, ciclo_id):
    """POST /api/hospital/oncologia/ciclos/<id>/toxicidade/ — registra toxicidade CTCAE."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, _, ToxicidadeQuimio = _get_onco_models()
    try:
        ciclo = CicloQuimioterapia.objects.get(id=ciclo_id, empresa=empresa)
    except CicloQuimioterapia.DoesNotExist:
        return JsonResponse({"erro": "Ciclo não encontrado"}, status=404)

    data = json.loads(request.body)
    with transaction.atomic():
        tox = ToxicidadeQuimio.objects.create(
            empresa=empresa,
            ciclo=ciclo,
            categoria=data["categoria"],
            grau=data["grau"],
            data_registro=data.get("data_registro", date.today().isoformat()),
            conduta=data.get("conduta", ""),
            dose_reduzida=data.get("dose_reduzida", False),
            ciclo_suspenso=data.get("ciclo_suspenso", False),
        )
        # Suspende ciclo se toxicidade grau ≥3 e ciclo_suspenso=True
        if tox.ciclo_suspenso and ciclo.status == "em_curso":
            ciclo.status = "suspenso"
            ciclo.save()

    alerta = None
    if tox.grau >= 3:
        alerta = f"⚠️ Toxicidade CTCAE Grau {tox.grau} — {tox.categoria} — avalie suspensão do protocolo"

    return JsonResponse({"id": tox.id, "alerta": alerta}, status=201)


# ── APACs ──────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
def api_onco_apacs(request):
    """GET/POST /api/hospital/oncologia/apacs/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, APACOncologia, _ = _get_onco_models()

    if request.method == "GET":
        qs = APACOncologia.objects.filter(empresa=empresa)
        status_f     = request.GET.get("status")
        competencia_f = request.GET.get("competencia")
        q            = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if competencia_f:
            qs = qs.filter(competencia=competencia_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(numero_apac__icontains=q)
                           | Q(cns_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "valor_total_solicitado": float(
                qs.filter(status__in=["submetida", "aprovada"])
                  .aggregate(v=Sum("valor_solicitado"))["v"] or 0
            ),
            "valor_total_aprovado": float(
                qs.filter(status="aprovada")
                  .aggregate(v=Sum("valor_aprovado"))["v"] or 0
            ),
            "apacs": [
                {
                    "id": a.id,
                    "numero_apac": a.numero_apac,
                    "paciente_nome": a.paciente_nome,
                    "cid10_principal": a.cid10_principal,
                    "procedimento_principal": a.procedimento_principal,
                    "competencia": a.competencia,
                    "valor_solicitado": float(a.valor_solicitado) if a.valor_solicitado else None,
                    "valor_aprovado": float(a.valor_aprovado) if a.valor_aprovado else None,
                    "status": a.status,
                    "status_display": a.get_status_display(),
                }
                for a in qs.order_by("-competencia")[:200]
            ],
        })

    data = json.loads(request.body)
    competencia = data.get("competencia", date.today().strftime("%Y%m"))

    # Valida que o ciclo referenciado pertence a ESTA empresa antes de vincular —
    # senão a APAC poderia apontar para um ciclo de outro tenant (ciclo_id vinha
    # cru do payload, sem checagem de posse).
    ciclo_ref = None
    ciclo_id = data.get("ciclo_id")
    if ciclo_id:
        ciclo_ref = CicloQuimioterapia.objects.filter(id=ciclo_id, empresa=empresa).first()
        if ciclo_ref is None:
            return JsonResponse({"erro": "Ciclo de quimioterapia não encontrado para esta empresa"}, status=400)

    with transaction.atomic():
        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        apac = APACOncologia.objects.create(
            empresa=empresa,
            numero_apac=data.get("numero_apac", ""),
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            cid10_principal=data["cid10_principal"],
            cid10_secundario=data.get("cid10_secundario", ""),
            procedimento_principal=data.get("procedimento_principal", ""),
            ciclo_referencia=ciclo_ref,
            competencia=competencia,
            valor_solicitado=data.get("valor_solicitado"),
        )
    return JsonResponse({"id": apac.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_feature("hospital.oncologia")
def api_onco_apac_detalhe(request, apac_id):
    """GET/PUT /api/hospital/oncologia/apacs/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, APACOncologia, _ = _get_onco_models()
    try:
        apac = APACOncologia.objects.get(id=apac_id, empresa=empresa)
    except APACOncologia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": apac.id,
            "numero_apac": apac.numero_apac,
            "paciente_nome": apac.paciente_nome,
            "cpf_paciente": apac.cpf_paciente,
            "cns_paciente": apac.cns_paciente,
            "cid10_principal": apac.cid10_principal,
            "cid10_secundario": apac.cid10_secundario,
            "procedimento_principal": apac.procedimento_principal,
            "competencia": apac.competencia,
            "valor_solicitado": float(apac.valor_solicitado) if apac.valor_solicitado else None,
            "valor_aprovado": float(apac.valor_aprovado) if apac.valor_aprovado else None,
            "status": apac.status,
            "status_display": apac.get_status_display(),
            "motivo_glosa": apac.motivo_glosa,
        })

    data = json.loads(request.body)
    campos = ["numero_apac", "status", "valor_aprovado", "motivo_glosa",
              "procedimento_principal"]
    for c in campos:
        if c in data:
            setattr(apac, c, data[c])
    apac.save()
    return JsonResponse({"ok": True})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.oncologia")
def api_onco_kpis(request):
    """GET /api/hospital/oncologia/kpis/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, APACOncologia, ToxicidadeQuimio = _get_onco_models()

    hoje    = date.today()
    mes_ini = hoje.replace(day=1)
    comp    = hoje.strftime("%Y%m")

    ciclos_ativos = CicloQuimioterapia.objects.filter(
        empresa=empresa, status__in=["agendado", "em_curso"]
    ).count()
    por_status = dict(
        CicloQuimioterapia.objects.filter(empresa=empresa)
        .values_list("status").annotate(n=Count("id")).order_by()
    )
    tox_graves_mes = ToxicidadeQuimio.objects.filter(
        empresa=empresa,
        grau__gte=3,
        data_registro__gte=mes_ini,
    ).count()

    apac_mes    = APACOncologia.objects.filter(empresa=empresa, competencia=comp)
    apac_glosa  = apac_mes.filter(status="glosada").count()
    val_aprovado = float(
        apac_mes.filter(status="aprovada")
                .aggregate(v=Sum("valor_aprovado"))["v"] or 0
    )

    return JsonResponse({
        "ciclos_ativos": ciclos_ativos,
        "ciclos_por_status": por_status,
        "toxicidades_grau3_mais_mes": tox_graves_mes,
        "apac_glosas_mes": apac_glosa,
        "valor_aprovado_mes": val_aprovado,
    })
