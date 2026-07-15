"""
views_governo_sala_situacao.py
Sala de Situação Epidemiológica (Governo) — consolida, num único painel,
sinais que hoje vivem espalhados em módulos distintos:
  • Surtos ativos e notificações compulsórias (NotificacaoCompulsoria/SurtoEpidemiologico)
  • Índice de infestação do combate a endemias (VisitaCombateEndemias)
  • Sintomas relatados pela população (App Cidadão / epidemiologia.py)
"""
from datetime import date, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from .access_control import (
    api_requer_feature, get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .models import NotificacaoCompulsoria, SurtoEpidemiologico, VisitaCombateEndemias
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def governo_sala_situacao_page(request):
    return render(request, "governo_sala_situacao.html", contexto_navegacao_setorial(request, "governo"))


@api_requer_feature("governo.sala_situacao")
def api_governo_sala_situacao(request):
    """GET /api/governo/sala-situacao/ — painel situacional consolidado."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    trinta_dias = hoje - timedelta(days=30)

    # Uma query com aggregate — substitui 3 counts separados
    surtos_ativos_qs = SurtoEpidemiologico.objects.filter(empresa=e, status="ativo")
    surtos_stats = surtos_ativos_qs.aggregate(
        vermelhos=Count("id", filter=Q(nivel_alerta="vermelho")),
        laranja=Count("id", filter=Q(nivel_alerta="laranja")),
    )
    surtos_vermelhos = surtos_stats["vermelhos"]
    surtos_laranja = surtos_stats["laranja"]
    surtos = list(surtos_ativos_qs.values(
        "id", "doenca", "municipio", "uf",
        "total_casos", "total_obitos", "nivel_alerta", "data_inicio",
    ))
    for s in surtos:
        s["data_inicio"] = s["data_inicio"].isoformat() if s["data_inicio"] else ""

    # Uma query com aggregate — substitui 2 counts separados
    notif_30d = NotificacaoCompulsoria.objects.filter(empresa=e, data_notificacao__gte=trinta_dias)
    notif_stats = notif_30d.aggregate(
        total=Count("id"),
        obitos=Count("id", filter=Q(evolucao="obito")),
    )
    total_notif_30d = notif_stats["total"]
    obitos_30d = notif_stats["obitos"]

    por_doenca = list(
        notif_30d.values("doenca").annotate(total=Count("id")).order_by("-total")[:10]
    )
    for item in por_doenca:
        item["doenca_label"] = dict(NotificacaoCompulsoria.DOENCA_CHOICES).get(item["doenca"], item["doenca"])

    tendencia_semanal = list(
        notif_30d.annotate(semana=TruncWeek("data_notificacao"))
        .values("semana").annotate(total=Count("id")).order_by("semana")
    )
    for t in tendencia_semanal:
        t["semana"] = t["semana"].isoformat() if t["semana"] else ""

    # Tendência: cresceu ou caiu nas últimas 2 semanas registradas
    crescendo = False
    if len(tendencia_semanal) >= 2:
        crescendo = tendencia_semanal[-1]["total"] > tendencia_semanal[-2]["total"]

    # Uma query com aggregate — substitui 2 counts separados
    endemias_stats = VisitaCombateEndemias.objects.filter(
        empresa=e, data_visita__gte=trinta_dias
    ).aggregate(
        total=Count("id"),
        com_foco=Count("id", filter=Q(foco_encontrado=True)),
    )
    total_imoveis_30d = endemias_stats["total"]
    imoveis_foco_30d = endemias_stats["com_foco"]
    indice_infestacao_pct = round((imoveis_foco_30d / total_imoveis_30d) * 100, 2) if total_imoveis_30d else 0.0

    sintomas_populacao = None
    try:
        from .epidemiologia import build_panorama_payload
        payload = build_panorama_payload()
        overview = payload.get("overview", {})
        sintomas_populacao = {
            "risco": overview.get("risk_level", "BAIXO"),
            "crescimento_percent": overview.get("growth_percent", 0),
            "casos_total": overview.get("total_cases", 0),
            "doenca_dominante": (overview.get("probable_diseases") or [{}])[0].get("name", ""),
        }
    except Exception:
        pass

    # Nível situacional consolidado — combina os 3 sinais reais acima.
    if surtos_vermelhos > 0 or indice_infestacao_pct >= 4.0:
        nivel_situacional = "vermelho"
    elif surtos_laranja > 0 or indice_infestacao_pct >= 1.0 or crescendo:
        nivel_situacional = "laranja"
    elif total_notif_30d > 0:
        nivel_situacional = "amarelo"
    else:
        nivel_situacional = "verde"

    return JsonResponse({
        "nivel_situacional": nivel_situacional,
        "atualizado_em": hoje.isoformat(),
        "surtos": {
            "ativos": len(surtos),
            "vermelhos": surtos_vermelhos,
            "laranja": surtos_laranja,
            "lista": surtos,
        },
        "notificacoes": {
            "total_30d": total_notif_30d,
            "obitos_30d": obitos_30d,
            "por_doenca": por_doenca,
            "tendencia_semanal": tendencia_semanal,
            "crescendo": crescendo,
        },
        "endemias": {
            "imoveis_visitados_30d": total_imoveis_30d,
            "imoveis_com_foco_30d": imoveis_foco_30d,
            "indice_infestacao_pct": indice_infestacao_pct,
        },
        "sintomas_populacao": sintomas_populacao,
    })
