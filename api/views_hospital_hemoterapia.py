"""
Hemoterapia — Banco de Sangue
Rastreabilidade de bolsas, solicitações de transfusão, registro de reações adversas
e notificação ANVISA NOTIVISA (RDC 34/2014).
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)


def _get_hemo_models():
    from .models import BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, ReacaoTransfusional
    return BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, ReacaoTransfusional


# ── Bolsas ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_hemo_bolsas(request):
    """GET/POST /api/hospital/hemoterapia/bolsas/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, *_ = _get_hemo_models()

    if request.method == "GET":
        qs = BolsaSangue.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        tipo_f   = request.GET.get("tipo")
        q        = request.GET.get("q")
        vencendo = request.GET.get("vencendo_dias")

        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        if q:
            qs = qs.filter(
                Q(codigo_bolsa__icontains=q) | Q(isbt128__icontains=q)
                | Q(doador_codigo__icontains=q)
            )
        if vencendo:
            try:
                limite = date.today() + timedelta(days=int(vencendo))
                qs = qs.filter(validade__lte=limite, validade__gte=date.today(),
                               status="disponivel")
            except ValueError:
                pass

        hoje = date.today()
        return JsonResponse({
            "total": qs.count(),
            "bolsas": [
                {
                    "id": b.id,
                    "codigo_bolsa": b.codigo_bolsa,
                    "tipo": b.tipo,
                    "tipo_display": b.get_tipo_display(),
                    "tipo_abo": b.tipo_abo,
                    "fator_rh": b.fator_rh,
                    "grupo_sanguineo": f"{b.tipo_abo}{b.fator_rh}",
                    "volume_ml": b.volume_ml,
                    "validade": b.validade.isoformat(),
                    "vencida": b.validade < hoje,
                    "dias_validade": (b.validade - hoje).days,
                    "status": b.status,
                    "status_display": b.get_status_display(),
                    "isbt128": b.isbt128,
                    "coletada_em": b.coletada_em.isoformat() if b.coletada_em else None,
                }
                for b in qs.order_by("validade")[:300]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        bolsa = BolsaSangue.objects.create(
            empresa=empresa,
            codigo_bolsa=data["codigo_bolsa"],
            tipo=data["tipo"],
            tipo_abo=data.get("tipo_abo", ""),
            fator_rh=data.get("fator_rh", ""),
            volume_ml=data.get("volume_ml"),
            doador_codigo=data.get("doador_codigo", ""),
            coletada_em=data.get("coletada_em"),
            processada_em=data.get("processada_em"),
            validade=data["validade"],
            isbt128=data.get("isbt128", ""),
            obs=data.get("obs", ""),
        )
    return JsonResponse({"id": bolsa.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_hemo_bolsa_detalhe(request, bolsa_id):
    """GET/PUT /api/hospital/hemoterapia/bolsas/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, *_ = _get_hemo_models()
    try:
        bolsa = BolsaSangue.objects.get(id=bolsa_id, empresa=empresa)
    except BolsaSangue.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": bolsa.id,
            "codigo_bolsa": bolsa.codigo_bolsa,
            "tipo": bolsa.tipo,
            "tipo_display": bolsa.get_tipo_display(),
            "tipo_abo": bolsa.tipo_abo,
            "fator_rh": bolsa.fator_rh,
            "volume_ml": bolsa.volume_ml,
            "doador_codigo": bolsa.doador_codigo,
            "coletada_em": bolsa.coletada_em.isoformat() if bolsa.coletada_em else None,
            "processada_em": bolsa.processada_em.isoformat() if bolsa.processada_em else None,
            "validade": bolsa.validade.isoformat(),
            "status": bolsa.status,
            "status_display": bolsa.get_status_display(),
            "isbt128": bolsa.isbt128,
            "obs": bolsa.obs,
        })

    data = json.loads(request.body)
    campos = ["status", "tipo_abo", "fator_rh", "volume_ml", "isbt128", "obs"]
    for c in campos:
        if c in data:
            setattr(bolsa, c, data[c])
    bolsa.save()
    return JsonResponse({"ok": True})


# ── Solicitações de Hemoterapia ────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_hemo_solicitacoes(request):
    """GET/POST /api/hospital/hemoterapia/solicitacoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, SolicitacaoHemoterapia, *_ = _get_hemo_models()

    if request.method == "GET":
        qs = SolicitacaoHemoterapia.objects.filter(empresa=empresa)
        status_f   = request.GET.get("status")
        urgencia_f = request.GET.get("urgencia")
        q          = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if urgencia_f:
            qs = qs.filter(urgencia=urgencia_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "solicitacoes": [
                {
                    "id": s.id,
                    "paciente_nome": s.paciente_nome,
                    "cpf_paciente": s.cpf_paciente,
                    "tipo_hemocomponente": s.tipo_hemocomponente,
                    "tipo_hemocomponente_display": s.get_tipo_hemocomponente_display(),
                    "tipo_abo": s.tipo_abo,
                    "fator_rh": s.fator_rh,
                    "quantidade": s.quantidade,
                    "urgencia": s.urgencia,
                    "urgencia_display": s.get_urgencia_display(),
                    "status": s.status,
                    "status_display": s.get_status_display(),
                    "data_solicitacao": s.data_solicitacao.isoformat(),
                    "leito": s.leito,
                    "medico_solicitante": s.medico_solicitante,
                }
                for s in qs.order_by("-criado_em")[:200]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        sol = SolicitacaoHemoterapia.objects.create(
            empresa=empresa,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            tipo_abo=data.get("tipo_abo", ""),
            fator_rh=data.get("fator_rh", ""),
            tipo_hemocomponente=data["tipo_hemocomponente"],
            quantidade=data.get("quantidade", 1),
            urgencia=data.get("urgencia", "eletiva"),
            cid10=data.get("cid10", ""),
            medico_solicitante=data.get("medico_solicitante", ""),
            crm_medico=data.get("crm_medico", ""),
            leito=data.get("leito", ""),
            justificativa=data.get("justificativa", ""),
        )
    return JsonResponse({"id": sol.id}, status=201)


# ── Transfusões ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_hemo_transfusoes(request):
    """GET/POST /api/hospital/hemoterapia/transfusoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, _ = _get_hemo_models()

    if request.method == "GET":
        qs = TransfusaoPaciente.objects.filter(empresa=empresa).select_related("bolsa")
        q  = request.GET.get("q")
        reacao = request.GET.get("com_reacao")

        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))
        if reacao == "true":
            qs = qs.filter(houve_reacao=True)

        return JsonResponse({
            "total": qs.count(),
            "transfusoes": [
                {
                    "id": t.id,
                    "paciente_nome": t.paciente_nome,
                    "cpf_paciente": t.cpf_paciente,
                    "bolsa_codigo": t.bolsa.codigo_bolsa,
                    "bolsa_tipo": t.bolsa.get_tipo_display(),
                    "data_inicio": t.data_inicio.isoformat(),
                    "data_fim": t.data_fim.isoformat() if t.data_fim else None,
                    "houve_reacao": t.houve_reacao,
                    "enfermeiro": t.enfermeiro,
                }
                for t in qs.order_by("-data_inicio")[:200]
            ],
        })

    data = json.loads(request.body)
    try:
        bolsa = BolsaSangue.objects.get(id=data["bolsa_id"], empresa=empresa)
    except BolsaSangue.DoesNotExist:
        return JsonResponse({"erro": "Bolsa não encontrada"}, status=404)

    if bolsa.status not in ("disponivel", "reservada"):
        return JsonResponse({"erro": f"Bolsa não disponível — status: {bolsa.status}"}, status=400)

    if bolsa.validade < date.today():
        return JsonResponse({"erro": "Bolsa vencida — descarte obrigatório (RDC 34/2014)"}, status=400)

    with transaction.atomic():
        transf = TransfusaoPaciente.objects.create(
            empresa=empresa,
            bolsa=bolsa,
            solicitacao_id=data.get("solicitacao_id"),
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            data_inicio=data.get("data_inicio", timezone.now().isoformat()),
            volume_ml=data.get("volume_ml"),
            enfermeiro=data.get("enfermeiro", ""),
            coren=data.get("coren", ""),
            medico_responsavel=data.get("medico_responsavel", ""),
            obs=data.get("obs", ""),
        )
        bolsa.status = "transfundida"
        bolsa.save()
        if data.get("solicitacao_id"):
            SolicitacaoHemoterapia.objects.filter(
                id=data["solicitacao_id"], empresa=empresa
            ).update(status="transfundida")

    return JsonResponse({"id": transf.id}, status=201)


# ── Reações Transfusionais ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_hemo_reacoes(request):
    """GET/POST /api/hospital/hemoterapia/reacoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, ReacaoTransfusional = _get_hemo_models()

    if request.method == "GET":
        qs = ReacaoTransfusional.objects.filter(empresa=empresa)
        gravidade_f = request.GET.get("gravidade")
        nao_notif   = request.GET.get("nao_notificado")

        if gravidade_f:
            qs = qs.filter(gravidade=gravidade_f)
        if nao_notif == "true":
            qs = qs.filter(notificado_anvisa=False)

        return JsonResponse({
            "total": qs.count(),
            "reacoes": [
                {
                    "id": r.id,
                    "paciente_nome": r.paciente_nome,
                    "tipo_reacao": r.tipo_reacao,
                    "tipo_reacao_display": r.get_tipo_reacao_display(),
                    "gravidade": r.gravidade,
                    "gravidade_display": r.get_gravidade_display(),
                    "data_reacao": r.data_reacao.isoformat(),
                    "notificado_anvisa": r.notificado_anvisa,
                    "protocolo_notivisa": r.protocolo_notivisa,
                }
                for r in qs.order_by("-data_reacao")[:200]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        reacao = ReacaoTransfusional.objects.create(
            empresa=empresa,
            transfusao_id=data.get("transfusao_id"),
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            tipo_reacao=data["tipo_reacao"],
            gravidade=data["gravidade"],
            data_reacao=data.get("data_reacao", timezone.now().isoformat()),
            descricao=data["descricao"],
            conduta=data.get("conduta", ""),
        )
    return JsonResponse({"id": reacao.id}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def api_hemo_notificar_anvisa(request, reacao_id):
    """POST /api/hospital/hemoterapia/reacoes/<id>/notificar-anvisa/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, ReacaoTransfusional = _get_hemo_models()
    try:
        reacao = ReacaoTransfusional.objects.get(id=reacao_id, empresa=empresa)
    except ReacaoTransfusional.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if reacao.notificado_anvisa:
        return JsonResponse({"ok": True, "protocolo": reacao.protocolo_notivisa,
                             "mensagem": "Já notificado ao NOTIVISA"})

    # Integração NOTIVISA — ANVISA
    try:
        import requests as req
        payload = {
            "tipo_reacao": reacao.tipo_reacao,
            "gravidade": reacao.gravidade,
            "data_reacao": reacao.data_reacao.isoformat(),
            "descricao": reacao.descricao,
            "cnes": "",
        }
        resp = req.post(
            "https://notivisa.anvisa.gov.br/api/v1/notificacao/hemovigilancia",
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201, 202):
            protocolo = resp.json().get("protocolo", f"NOTIVISA-{reacao.id}")
            reacao.notificado_anvisa = True
            reacao.protocolo_notivisa = protocolo
            reacao.save()
            return JsonResponse({"ok": True, "protocolo": protocolo})
        else:
            return JsonResponse({"erro": f"NOTIVISA HTTP {resp.status_code}"}, status=502)
    except Exception as e:
        logger.error("Erro NOTIVISA reação %s: %s", reacao_id, e)
        return JsonResponse({"erro": str(e)}, status=502)


# ── KPIs ───────────────────────────────────────────────────────────────────────

def api_hemo_kpis(request):
    """GET /api/hospital/hemoterapia/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, ReacaoTransfusional = _get_hemo_models()

    hoje     = date.today()
    mes_ini  = hoje.replace(day=1)
    sete_dias = hoje + timedelta(days=7)

    # Estoque
    por_tipo = dict(
        BolsaSangue.objects.filter(empresa=empresa, status="disponivel")
        .values_list("tipo").annotate(n=Count("id")).order_by()
    )
    vencendo_7d = BolsaSangue.objects.filter(
        empresa=empresa, status="disponivel",
        validade__gte=hoje, validade__lte=sete_dias,
    ).count()
    vencidas = BolsaSangue.objects.filter(
        empresa=empresa, status="disponivel", validade__lt=hoje
    ).count()

    # Transfusões no mês
    transf_mes = TransfusaoPaciente.objects.filter(
        empresa=empresa, data_inicio__date__gte=mes_ini
    ).count()
    reacoes_mes = ReacaoTransfusional.objects.filter(
        empresa=empresa, data_reacao__gte=mes_ini
    ).count()
    graves_nao_notif = ReacaoTransfusional.objects.filter(
        empresa=empresa,
        gravidade__in=["grave", "fatal"],
        notificado_anvisa=False,
    ).count()

    return JsonResponse({
        "estoque_por_tipo": por_tipo,
        "vencendo_7_dias": vencendo_7d,
        "bolsas_vencidas_estoque": vencidas,
        "transfusoes_mes": transf_mes,
        "reacoes_mes": reacoes_mes,
        "graves_nao_notificadas_anvisa": graves_nao_notif,
        "alerta_estoque_critico": vencendo_7d > 0 or vencidas > 0 or graves_nao_notif > 0,
    })
