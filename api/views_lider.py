import json
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .corporativo_ai import MIN_GROUP_SIZE
from .models import (
    AcaoCorporativa,
    CheckinDiarioCorporativo,
    CheckinSemanalCorporativo,
    EmpresaSetor,
    EmpresaUnidade,
    PedidoApoioCorporativo,
)
from .views_dashboard import _empresa_autenticada, _setor_conta


def _empresa_lider(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    if _setor_conta(empresa) != "empresa":
        return None
    return empresa


def painel_lider(request):
    empresa = _empresa_lider(request)
    if not empresa:
        return redirect("/")
    unidades = list(EmpresaUnidade.objects.filter(empresa=empresa, ativo=True).values("id", "nome"))
    return render(request, "painel_lider.html", {
        "empresa_nome": empresa.nome,
        "unidades": unidades,
        "unidades_json": json.dumps(unidades),
        "min_group": MIN_GROUP_SIZE,
    })


def api_unidade_dados(request, unidade_id):
    empresa = _empresa_lider(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    unidade = EmpresaUnidade.objects.filter(id=unidade_id, empresa=empresa).first()
    if not unidade:
        return JsonResponse({"erro": "unidade nao encontrada"}, status=404)

    now = timezone.now()
    cutoff = now.date() - timedelta(days=30)
    prev_cutoff = now.date() - timedelta(days=60)

    base_d = CheckinDiarioCorporativo.objects.filter(empresa=empresa, unidade=unidade, data_referencia__gte=cutoff)
    prev_d = CheckinDiarioCorporativo.objects.filter(
        empresa=empresa, unidade=unidade,
        data_referencia__gte=prev_cutoff, data_referencia__lt=cutoff
    )
    base_s = CheckinSemanalCorporativo.objects.filter(empresa=empresa, unidade=unidade, semana_referencia__gte=cutoff)

    def agg_d(qs):
        return qs.aggregate(
            respondents=Count("id"),
            avg_humor=Avg("humor"),
            avg_energia=Avg("energia"),
            avg_estresse=Avg("estresse"),
            avg_sono=Avg("sono"),
            avg_fadiga=Avg("fadiga"),
            avg_dor_fisica=Avg("dor_fisica"),
            avg_ansiedade=Avg("ansiedade"),
            pedidos_apoio=Count("id", filter=Q(apoio_solicitado=True)),
        )

    curr = agg_d(base_d)
    prev = agg_d(prev_d)
    semanal = base_s.aggregate(
        avg_risco_burnout=Avg("risco_burnout"),
        avg_carga_emocional=Avg("carga_emocional"),
        avg_seguranca_psicologica=Avg("seguranca_psicologica"),
    )

    def safe(v):
        return round(float(v or 0), 1)

    def delta(c, p):
        d = safe(c) - safe(p)
        return round(d, 1) if abs(d) >= 0.1 else 0

    respondents = curr.get("respondents") or 0
    privacy_ok = respondents >= MIN_GROUP_SIZE

    apoio_aberto = PedidoApoioCorporativo.objects.filter(
        empresa=empresa, unidade=unidade,
        status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE]
    ).count()

    acoes_abertas = AcaoCorporativa.objects.filter(
        empresa=empresa, unidade=unidade,
        status__in=[AcaoCorporativa.STATUS_ABERTA, AcaoCorporativa.STATUS_EM_ANDAMENTO]
    ).count()

    setores = (
        base_d.exclude(setor__isnull=True)
        .values("setor__nome")
        .annotate(n=Count("id"), estresse=Avg("estresse"), fadiga=Avg("fadiga"))
        .order_by("-estresse")[:6]
    )

    return JsonResponse({
        "unidade": {"id": unidade.id, "nome": unidade.nome},
        "respondents": respondents,
        "privacy_ok": privacy_ok,
        "periodo": "ultimos 30 dias",
        "metricas": {
            "humor": {"atual": safe(curr["avg_humor"]), "delta": delta(curr["avg_humor"], prev["avg_humor"])},
            "energia": {"atual": safe(curr["avg_energia"]), "delta": delta(curr["avg_energia"], prev["avg_energia"])},
            "estresse": {"atual": safe(curr["avg_estresse"]), "delta": delta(curr["avg_estresse"], prev["avg_estresse"])},
            "sono": {"atual": safe(curr["avg_sono"]), "delta": delta(curr["avg_sono"], prev["avg_sono"])},
            "fadiga": {"atual": safe(curr["avg_fadiga"]), "delta": delta(curr["avg_fadiga"], prev["avg_fadiga"])},
            "ansiedade": {"atual": safe(curr["avg_ansiedade"]), "delta": delta(curr["avg_ansiedade"], prev["avg_ansiedade"])},
            "risco_burnout": {"atual": safe(semanal["avg_risco_burnout"]), "delta": 0},
            "carga_emocional": {"atual": safe(semanal["avg_carga_emocional"]), "delta": 0},
            "seguranca_psicologica": {"atual": safe(semanal["avg_seguranca_psicologica"]), "delta": 0},
        },
        "apoio_aberto": apoio_aberto,
        "acoes_abertas": acoes_abertas,
        "setores": [
            {
                "nome": s["setor__nome"],
                "respondents": s["n"],
                "estresse": round(float(s["estresse"] or 0), 1),
                "fadiga": round(float(s["fadiga"] or 0), 1),
            }
            for s in setores if s["n"] >= MIN_GROUP_SIZE
        ],
    })
