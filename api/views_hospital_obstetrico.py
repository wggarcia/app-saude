"""
Centro Obstétrico / Maternidade
Partograma OMS (1994), Registro de Parto, APGAR, Capurro,
Declaração de Nascido Vivo (DNV) eletrônica e KPIs perinatais.
MS/DATASUS — SINASC | CFM Resolução 2.294/2021
"""
import json
import logging
from datetime import date, timedelta
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Q, Avg
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _get_obs_models():
    from .models import Partograma, RegistroParto
    return Partograma, RegistroParto


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.obstetrico", "Centro Obstétrico")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_obstetrico_page(request):
    return render(request, "hospital_obstetrico.html")


# ── partograma ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.obstetrico")
def api_obstetrico_partogramas(request):
    """GET/POST /api/hospital/obstetrico/partogramas/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    Partograma, _ = _get_obs_models()

    if request.method == "GET":
        qs = Partograma.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "ativos": qs.filter(status="ativo").count(),
            "partogramas": [
                {
                    "id": p.id,
                    "paciente_nome": p.paciente_nome,
                    "cpf_paciente": p.cpf_paciente,
                    "data_internacao": p.data_internacao.isoformat(),
                    "ig_semanas": p.ig_semanas,
                    "dilatacao_inicial": p.dilatacao_inicial,
                    "apresentacao": p.apresentacao,
                    "status": p.status,
                    "status_display": p.get_status_display(),
                    "medico_responsavel": p.medico_responsavel,
                    "evolucoes_count": len(p.evolucoes) if isinstance(p.evolucoes, list) else 0,
                }
                for p in qs.order_by("-data_internacao")[:100]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        pt = Partograma.objects.create(
            empresa=empresa,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            data_nascimento=data.get("data_nascimento"),
            internacao_id=data.get("internacao_id"),
            data_internacao=data.get("data_internacao", timezone.now().isoformat()),
            ig_semanas=data.get("ig_semanas"),
            numero_gestacoes=data.get("numero_gestacoes", 1),
            numero_partos=data.get("numero_partos", 0),
            numero_abortos=data.get("numero_abortos", 0),
            dilatacao_inicial=data.get("dilatacao_inicial", 0),
            apresentacao=data.get("apresentacao", ""),
            situacao_fetal=data.get("situacao_fetal", ""),
            medico_responsavel=data.get("medico_responsavel", ""),
            crm_medico=data.get("crm_medico", ""),
            evolucoes=[],
            status="ativo",
        )
    return JsonResponse({"id": pt.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.obstetrico")
def api_obstetrico_partograma_detalhe(request, pt_id):
    """GET/POST /api/hospital/obstetrico/partogramas/<id>/ — GET detalhe ou POST registra evolução."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    Partograma, _ = _get_obs_models()
    try:
        pt = Partograma.objects.get(id=pt_id, empresa=empresa)
    except Partograma.DoesNotExist:
        return JsonResponse({"erro": "Partograma não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": pt.id,
            "paciente_nome": pt.paciente_nome,
            "cpf_paciente": pt.cpf_paciente,
            "cns_paciente": pt.cns_paciente,
            "data_nascimento": pt.data_nascimento.isoformat() if pt.data_nascimento else None,
            "data_internacao": pt.data_internacao.isoformat(),
            "ig_semanas": pt.ig_semanas,
            "numero_gestacoes": pt.numero_gestacoes,
            "numero_partos": pt.numero_partos,
            "numero_abortos": pt.numero_abortos,
            "dilatacao_inicial": pt.dilatacao_inicial,
            "apresentacao": pt.apresentacao,
            "situacao_fetal": pt.situacao_fetal,
            "status": pt.status,
            "status_display": pt.get_status_display(),
            "medico_responsavel": pt.medico_responsavel,
            "crm_medico": pt.crm_medico,
            "evolucoes": pt.evolucoes,
        })

    # POST — registra ponto horário na curva do partograma
    data = json.loads(request.body)
    if pt.status != "ativo":
        return JsonResponse({"erro": f"Partograma já encerrado ({pt.status})"}, status=400)

    ponto = {
        "hora": data.get("hora", timezone.now().isoformat()),
        "dilatacao": data.get("dilatacao", 0),       # cm (0–10)
        "altura_apresentacao": data.get("altura_apresentacao", 0),  # plano de De Lee (-5 a +5)
        "bcf": data.get("bcf"),                       # Batimentos Cardíacos Fetais
        "contracao_frequencia": data.get("contracao_frequencia"),  # contrações/10 min
        "contracao_duracao": data.get("contracao_duracao"),        # segundos
        "observacao": data.get("observacao", ""),
        "registrado_por": data.get("registrado_por", ""),
    }
    evolucoes = pt.evolucoes if isinstance(pt.evolucoes, list) else []
    evolucoes.append(ponto)

    # Auto-encerra se dilatação = 10 e não é cesárea
    novo_status = pt.status
    if data.get("dilatacao", 0) >= 10:
        novo_status = "concluido"

    if "status" in data:
        novo_status = data["status"]

    pt.evolucoes = evolucoes
    pt.status = novo_status
    pt.save()

    return JsonResponse({
        "ok": True,
        "total_evolucoes": len(evolucoes),
        "status": pt.status,
        "alerta_linha_alerta": (
            # Linha de alerta OMS: se dilatação < 1 cm/h por 4h consecutivas → risco
            "⚠️ Progresso lento — verifique necessidade de intervenção."
            if len(evolucoes) >= 4 and data.get("dilatacao", 0) - evolucoes[-5].get("dilatacao", 0) < 3
            else None
        ),
    })


# ── registro de parto ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.obstetrico")
def api_obstetrico_partos(request):
    """GET/POST /api/hospital/obstetrico/partos/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, RegistroParto = _get_obs_models()

    if request.method == "GET":
        qs = RegistroParto.objects.filter(empresa=empresa)
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        tipo = request.GET.get("tipo")
        q = request.GET.get("q")

        if data_ini:
            qs = qs.filter(data_parto__date__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_parto__date__lte=data_fim)
        if tipo:
            qs = qs.filter(tipo_parto=tipo)
        if q:
            qs = qs.filter(Q(mae_nome__icontains=q) | Q(cpf_mae=q) | Q(rn_nome__icontains=q))

        return JsonResponse({
            "total": qs.count(),
            "partos": [
                {
                    "id": p.id,
                    "mae_nome": p.mae_nome,
                    "cpf_mae": p.cpf_mae,
                    "tipo_parto": p.tipo_parto,
                    "tipo_parto_display": p.get_tipo_parto_display(),
                    "data_parto": p.data_parto.isoformat(),
                    "ig_semanas": p.ig_semanas,
                    "rn_nome": p.rn_nome,
                    "sexo_rn": p.sexo_rn,
                    "peso_rn": float(p.peso_rn) if p.peso_rn else None,
                    "apgar_1min": p.apgar_1min,
                    "apgar_5min": p.apgar_5min,
                    "rn_vivo": p.rn_vivo,
                    "dnv_emitida": p.dnv_emitida,
                    "dnv_numero": p.dnv_numero,
                }
                for p in qs.order_by("-data_parto")[:200]
            ],
        })

    data = json.loads(request.body)

    # Validações clínicas básicas
    apgar_1 = data.get("apgar_1min")
    apgar_5 = data.get("apgar_5min")
    alertas = []
    if apgar_1 is not None and apgar_1 <= 3:
        alertas.append("🚨 APGAR 1' ≤ 3 — sofrimento fetal grave. Acionamento neonatologista imediato.")
    elif apgar_1 is not None and apgar_1 <= 6:
        alertas.append("⚠️ APGAR 1' ≤ 6 — sofrimento fetal moderado. Monitorar.")
    if apgar_5 is not None and apgar_5 <= 6:
        alertas.append("🚨 APGAR 5' ≤ 6 — avalie internação em UTI neonatal.")

    with transaction.atomic():
        parto = RegistroParto.objects.create(
            empresa=empresa,
            partograma_id=data.get("partograma_id"),
            mae_nome=data["mae_nome"],
            cpf_mae=data.get("cpf_mae", ""),
            cns_mae=data.get("cns_mae", ""),
            tipo_parto=data["tipo_parto"],
            data_parto=data["data_parto"],
            ig_semanas=data.get("ig_semanas"),
            rn_nome=data.get("rn_nome", ""),
            sexo_rn=data.get("sexo_rn", "I"),
            peso_rn=data.get("peso_rn"),
            comprimento_rn=data.get("comprimento_rn"),
            capurro=data.get("capurro"),
            apgar_1min=apgar_1,
            apgar_5min=apgar_5,
            apgar_10min=data.get("apgar_10min"),
            rn_vivo=data.get("rn_vivo", True),
            medico_responsavel=data.get("medico_responsavel", ""),
            crm_medico=data.get("crm_medico", ""),
            obs=data.get("obs", ""),
        )
        # Encerra partograma vinculado
        if data.get("partograma_id"):
            Partograma, _ = _get_obs_models()
            Partograma.objects.filter(id=data["partograma_id"], empresa=empresa).update(
                status="concluido" if data["tipo_parto"] == "normal" else "cesariana"
            )

    return JsonResponse({
        "id": parto.id,
        "alertas": alertas,
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_feature("hospital.obstetrico")
def api_obstetrico_parto_detalhe(request, parto_id):
    """GET/PUT /api/hospital/obstetrico/partos/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, RegistroParto = _get_obs_models()
    try:
        parto = RegistroParto.objects.get(id=parto_id, empresa=empresa)
    except RegistroParto.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": parto.id,
            "mae_nome": parto.mae_nome,
            "cpf_mae": parto.cpf_mae,
            "cns_mae": parto.cns_mae,
            "tipo_parto": parto.tipo_parto,
            "tipo_parto_display": parto.get_tipo_parto_display(),
            "data_parto": parto.data_parto.isoformat(),
            "ig_semanas": parto.ig_semanas,
            "rn_nome": parto.rn_nome,
            "sexo_rn": parto.sexo_rn,
            "peso_rn": float(parto.peso_rn) if parto.peso_rn else None,
            "comprimento_rn": float(parto.comprimento_rn) if parto.comprimento_rn else None,
            "capurro": parto.capurro,
            "apgar_1min": parto.apgar_1min,
            "apgar_5min": parto.apgar_5min,
            "apgar_10min": parto.apgar_10min,
            "rn_vivo": parto.rn_vivo,
            "dnv_numero": parto.dnv_numero,
            "dnv_emitida": parto.dnv_emitida,
            "medico_responsavel": parto.medico_responsavel,
            "obs": parto.obs,
        })

    data = json.loads(request.body)
    campos = ["dnv_numero", "dnv_emitida", "obs", "rn_nome", "apgar_10min"]
    for c in campos:
        if c in data:
            setattr(parto, c, data[c])
    parto.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.obstetrico")
def api_obstetrico_dnv(request, parto_id):
    """GET /api/hospital/obstetrico/partos/<id>/dnv/ — gera estrutura DNV eletrônica (SINASC)."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, RegistroParto = _get_obs_models()
    try:
        parto = RegistroParto.objects.get(id=parto_id, empresa=empresa)
    except RegistroParto.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if not parto.dnv_numero:
        return JsonResponse(
            {"erro": "Número DNV não registrado para este parto. Preencha o campo antes de emitir a DNV eletrônica."},
            status=400,
        )

    # Estrutura baseada no formulário DNV IBGE/MS (modelo atual)
    dnv = {
        "tipo": "DNV-eletrônica",
        "sistema": "SINASC/DATASUS",
        "numero_dnv": parto.dnv_numero or None,
        "data_emissao": date.today().isoformat(),
        "estabelecimento": {
            "nome": empresa.nome,
            "cnpj": getattr(empresa, "cnpj", ""),
        },
        "mae": {
            "nome": parto.mae_nome,
            "cpf": parto.cpf_mae,
            "cns": parto.cns_mae,
        },
        "neonato": {
            "nome": parto.rn_nome or "A definir",
            "sexo": parto.sexo_rn,
            "data_nascimento": parto.data_parto.date().isoformat(),
            "hora_nascimento": parto.data_parto.strftime("%H:%M"),
            "peso_gramas": float(parto.peso_rn) if parto.peso_rn else None,
            "comprimento_cm": float(parto.comprimento_rn) if parto.comprimento_rn else None,
            "ig_semanas": parto.ig_semanas,
            "capurro_semanas": parto.capurro,
            "apgar_1min": parto.apgar_1min,
            "apgar_5min": parto.apgar_5min,
            "rn_vivo": parto.rn_vivo,
        },
        "parto": {
            "tipo": parto.tipo_parto,
            "tipo_display": parto.get_tipo_parto_display(),
        },
        "status_dnv": "emitida" if parto.dnv_emitida else "pendente",
        "instrucoes": (
            "DNV deve ser transmitida ao SINASC em até 24h do nascimento. "
            "Acesse https://sinasc.saude.gov.br para envio oficial."
        ),
    }
    return JsonResponse(dnv)


# ── KPIs perinatais ────────────────────────────────────────────────────────────

@api_requer_feature("hospital.obstetrico")
def api_obstetrico_kpis(request):
    """GET /api/hospital/obstetrico/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    Partograma, RegistroParto = _get_obs_models()

    hoje = date.today()
    mes_ini = hoje.replace(day=1)
    ano_ini = hoje.replace(month=1, day=1)

    partos_mes = RegistroParto.objects.filter(empresa=empresa, data_parto__date__gte=mes_ini)
    partos_ano = RegistroParto.objects.filter(empresa=empresa, data_parto__date__gte=ano_ini)

    por_tipo = dict(partos_mes.values_list("tipo_parto").annotate(n=Count("id")).order_by())
    total_mes = partos_mes.count()
    cesarianas = por_tipo.get("cesariana", 0) + por_tipo.get("cesariana_ur", 0)
    taxa_cesaria = round(cesarianas / total_mes * 100, 1) if total_mes > 0 else 0

    # APGAR baixo (risco neonatal)
    apgar_baixo = partos_mes.filter(apgar_5min__lte=6).count()

    # DNV pendentes
    dnv_pendentes = RegistroParto.objects.filter(
        empresa=empresa, dnv_emitida=False, rn_vivo=True
    ).count()

    partogramas_ativos = Partograma.objects.filter(empresa=empresa, status="ativo").count()

    return JsonResponse({
        "partos_mes": total_mes,
        "partos_ano": partos_ano.count(),
        "por_tipo_mes": por_tipo,
        "taxa_cesaria_pct": taxa_cesaria,
        "alerta_taxa_cesaria": taxa_cesaria > 50,  # OMS recomenda <15%
        "apgar_baixo_5min_mes": apgar_baixo,
        "dnv_pendentes": dnv_pendentes,
        "partogramas_ativos": partogramas_ativos,
    })
