"""
CCIH — Comissão de Controle de Infecção Hospitalar
Vigilância epidemiológica intra-hospitalar, IRAS, protocolos de isolamento e
indicadores ANS/ANVISA (RDC 36/2008 — ANVISA).
"""
import json
import logging
from datetime import date, timedelta
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Q, Avg
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)


def _get_ccih_models():
    from .models import InfeccaoHospitalar, ProtocoloIsolamento, IndicadorCCIH
    return InfeccaoHospitalar, ProtocoloIsolamento, IndicadorCCIH


# ── IRAS (Infecções Relacionadas à Assistência à Saúde) ───────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ccih_infeccoes(request):
    """GET/POST /api/hospital/ccih/infeccoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InfeccaoHospitalar, *_ = _get_ccih_models()

    if request.method == "GET":
        qs = InfeccaoHospitalar.objects.filter(empresa=empresa)
        topografia = request.GET.get("topografia")
        status_f = request.GET.get("status")
        agente = request.GET.get("agente")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        q = request.GET.get("q")

        if topografia:
            qs = qs.filter(topografia=topografia)
        if status_f:
            qs = qs.filter(status=status_f)
        if agente:
            qs = qs.filter(agente=agente)
        if data_ini:
            qs = qs.filter(data_diagnostico__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_diagnostico__lte=data_fim)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q)
                           | Q(setor__icontains=q))

        return JsonResponse({
            "total": qs.count(),
            "infeccoes": [
                {
                    "id": i.id,
                    "paciente_nome": i.paciente_nome,
                    "cpf_paciente": i.cpf_paciente,
                    "leito": i.leito,
                    "setor": i.setor,
                    "topografia": i.topografia,
                    "topografia_display": i.get_topografia_display(),
                    "agente": i.agente,
                    "agente_display": i.get_agente_display(),
                    "agente_descricao": i.agente_descricao,
                    "status": i.status,
                    "status_display": i.get_status_display(),
                    "data_diagnostico": i.data_diagnostico.isoformat(),
                    "obito": i.obito,
                    "notificado_anvisa": i.notificado_anvisa,
                    "perfil_resistencia": i.perfil_resistencia,
                }
                for i in qs.order_by("-data_diagnostico")[:300]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        ih = InfeccaoHospitalar.objects.create(
            empresa=empresa,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            internacao_id=data.get("internacao_id"),
            leito=data.get("leito", ""),
            setor=data.get("setor", ""),
            topografia=data["topografia"],
            agente=data.get("agente", "outro"),
            agente_descricao=data.get("agente_descricao", ""),
            status=data.get("status", "suspeita"),
            perfil_resistencia=data.get("perfil_resistencia", {}),
            data_diagnostico=data.get("data_diagnostico", date.today().isoformat()),
            obito=data.get("obito", False),
            observacoes=data.get("observacoes", ""),
        )
    return JsonResponse({"id": ih.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_ccih_infeccao_detalhe(request, ih_id):
    """GET/PUT /api/hospital/ccih/infeccoes/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InfeccaoHospitalar, *_ = _get_ccih_models()
    try:
        ih = InfeccaoHospitalar.objects.get(id=ih_id, empresa=empresa)
    except InfeccaoHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": ih.id,
            "paciente_nome": ih.paciente_nome,
            "cpf_paciente": ih.cpf_paciente,
            "leito": ih.leito,
            "setor": ih.setor,
            "topografia": ih.topografia,
            "topografia_display": ih.get_topografia_display(),
            "agente": ih.agente,
            "agente_display": ih.get_agente_display(),
            "agente_descricao": ih.agente_descricao,
            "status": ih.status,
            "status_display": ih.get_status_display(),
            "perfil_resistencia": ih.perfil_resistencia,
            "data_diagnostico": ih.data_diagnostico.isoformat(),
            "data_alta": ih.data_alta.isoformat() if ih.data_alta else None,
            "obito": ih.obito,
            "notificado_anvisa": ih.notificado_anvisa,
            "observacoes": ih.observacoes,
        })

    data = json.loads(request.body)
    campos = ["status", "agente", "agente_descricao", "perfil_resistencia",
              "data_alta", "obito", "notificado_anvisa", "observacoes"]
    for c in campos:
        if c in data:
            setattr(ih, c, data[c])
    ih.save()
    return JsonResponse({"ok": True})


# ── isolamentos ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ccih_isolamentos(request):
    """GET/POST /api/hospital/ccih/isolamentos/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, ProtocoloIsolamento, _ = _get_ccih_models()

    if request.method == "GET":
        qs = ProtocoloIsolamento.objects.filter(empresa=empresa)
        ativo = request.GET.get("ativo")
        tipo = request.GET.get("tipo")
        if ativo == "true":
            qs = qs.filter(ativo=True)
        elif ativo == "false":
            qs = qs.filter(ativo=False)
        if tipo:
            qs = qs.filter(tipo=tipo)

        return JsonResponse({
            "total": qs.count(),
            "ativos": qs.filter(ativo=True).count(),
            "isolamentos": [
                {
                    "id": iso.id,
                    "paciente_nome": iso.paciente_nome,
                    "leito": iso.leito,
                    "tipo": iso.tipo,
                    "tipo_display": iso.get_tipo_display(),
                    "motivo": iso.motivo,
                    "ativo": iso.ativo,
                    "iniciado_em": iso.iniciado_em.isoformat(),
                    "encerrado_em": iso.encerrado_em.isoformat() if iso.encerrado_em else None,
                }
                for iso in qs.order_by("-ativo", "-iniciado_em")
            ],
        })

    data = json.loads(request.body)
    iso = ProtocoloIsolamento.objects.create(
        empresa=empresa,
        infeccao_id=data.get("infeccao_id"),
        paciente_nome=data["paciente_nome"],
        leito=data["leito"],
        tipo=data["tipo"],
        motivo=data["motivo"],
        ativo=True,
    )
    return JsonResponse({"id": iso.id}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def api_ccih_isolamento_encerrar(request, iso_id):
    """POST /api/hospital/ccih/isolamentos/<id>/encerrar/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, ProtocoloIsolamento, _ = _get_ccih_models()
    try:
        iso = ProtocoloIsolamento.objects.get(id=iso_id, empresa=empresa)
    except ProtocoloIsolamento.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    data = json.loads(request.body) if request.body else {}
    iso.ativo = False
    iso.encerrado_em = timezone.now()
    iso.encerrado_por = data.get("encerrado_por", "")
    iso.save()
    return JsonResponse({"ok": True})


# ── indicadores mensais ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ccih_indicadores(request):
    """GET/POST /api/hospital/ccih/indicadores/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, IndicadorCCIH = _get_ccih_models()

    if request.method == "GET":
        qs = IndicadorCCIH.objects.filter(empresa=empresa).order_by("-competencia")
        return JsonResponse({
            "indicadores": [
                {
                    "id": ind.id,
                    "competencia": ind.competencia,
                    "di_ics": float(ind.di_ics),
                    "di_itu_rc": float(ind.di_itu_rc),
                    "di_pav": float(ind.di_pav),
                    "taxa_isc": float(ind.taxa_isc),
                    "total_infeccoes": ind.total_infeccoes,
                    "total_cirurgias": ind.total_cirurgias,
                }
                for ind in qs[:24]
            ],
        })

    data = json.loads(request.body)
    competencia = data.get("competencia", date.today().strftime("%Y%m"))

    # Calcula automaticamente a partir das IRAS registradas
    ano, mes = int(competencia[:4]), int(competencia[4:6])
    from .models import InfeccaoHospitalar as IH
    iras_mes = IH.objects.filter(
        empresa=empresa,
        data_diagnostico__year=ano,
        data_diagnostico__month=mes,
        status="confirmada",
    )
    total = iras_mes.count()

    ind, _ = IndicadorCCIH.objects.update_or_create(
        empresa=empresa,
        competencia=competencia,
        defaults={
            "di_ics": data.get("di_ics", 0),
            "di_itu_rc": data.get("di_itu_rc", 0),
            "di_pav": data.get("di_pav", 0),
            "taxa_isc": data.get("taxa_isc", 0),
            "total_paciente_dia": data.get("total_paciente_dia", 0),
            "total_cateter_dia": data.get("total_cateter_dia", 0),
            "total_vm_dia": data.get("total_vm_dia", 0),
            "total_cirurgias": data.get("total_cirurgias", 0),
            "total_infeccoes": total,
            "obs": data.get("obs", ""),
        },
    )
    return JsonResponse({"id": ind.id}, status=201)


# ── KPIs ───────────────────────────────────────────────────────────────────────

def api_ccih_kpis(request):
    """GET /api/hospital/ccih/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InfeccaoHospitalar, ProtocoloIsolamento, IndicadorCCIH = _get_ccih_models()

    hoje = date.today()
    mes_ini = hoje.replace(day=1)
    trinta_dias = hoje - timedelta(days=30)

    qs_total = InfeccaoHospitalar.objects.filter(empresa=empresa)
    qs_mes = qs_total.filter(data_diagnostico__gte=mes_ini)

    por_topografia = dict(
        qs_mes.values_list("topografia").annotate(n=Count("id")).order_by()
    )
    por_agente = dict(
        qs_mes.filter(status="confirmada")
        .values_list("agente").annotate(n=Count("id")).order_by()
    )
    isolamentos_ativos = ProtocoloIsolamento.objects.filter(
        empresa=empresa, ativo=True
    ).count()
    obitos = qs_mes.filter(obito=True).count()
    nao_notificados = qs_mes.filter(
        status="confirmada", notificado_anvisa=False
    ).count()

    # Último indicador
    ultimo_ind = IndicadorCCIH.objects.filter(empresa=empresa).order_by("-competencia").first()

    return JsonResponse({
        "infeccoes_mes": qs_mes.count(),
        "infeccoes_confirmadas_mes": qs_mes.filter(status="confirmada").count(),
        "obitos_mes": obitos,
        "por_topografia_mes": por_topografia,
        "agentes_predominantes_mes": por_agente,
        "isolamentos_ativos": isolamentos_ativos,
        "nao_notificados_anvisa": nao_notificados,
        "ultimo_indicador": {
            "competencia": ultimo_ind.competencia,
            "di_ics": float(ultimo_ind.di_ics),
            "di_itu_rc": float(ultimo_ind.di_itu_rc),
            "di_pav": float(ultimo_ind.di_pav),
        } if ultimo_ind else None,
        "alerta_resistencia": qs_mes.filter(
            agente__in=["mrsa", "kpc", "vre"]
        ).count(),
    })
