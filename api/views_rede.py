"""
Dashboard Executivo de Rede — comparação entre unidades, ranking e KPIs consolidados.
Endpoint: GET /api/rede/kpis
Page:     GET /dashboard-rede/
"""
from datetime import date, timedelta
from django.http import JsonResponse
from django.db.models import Avg, Count, Q
from .views_dashboard import _empresa_autenticada


def api_rede_kpis(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    semana_ini = hoje - timedelta(days=hoje.weekday())
    mes_ini = hoje.replace(day=1)
    ultimos_7 = hoje - timedelta(days=6)
    ultimos_30 = hoje - timedelta(days=29)

    unidades = list(empresa.unidades_corporativas.filter(ativo=True).order_by("nome"))

    # ── Consolidated totals ──────────────────────────────────────────────────
    try:
        from .models import FuncionarioSST, CheckinDiarioCorporativo, CheckinSemanalCorporativo, PedidoApoioCorporativo

        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()

        checkins_mes = CheckinDiarioCorporativo.objects.filter(
            empresa=empresa, data_referencia__gte=mes_ini
        )
        avg_bem_estar = checkins_mes.aggregate(
            humor=Avg("humor"), energia=Avg("energia"),
            estresse=Avg("estresse"), sono=Avg("sono"),
        )
        bem_estar_geral = round(
            ((avg_bem_estar["humor"] or 0) + (avg_bem_estar["energia"] or 0)
             + (avg_bem_estar["sono"] or 0)
             + (5 - (avg_bem_estar["estresse"] or 3))) / 4, 1
        ) if checkins_mes.exists() else None

        semanais_mes = CheckinSemanalCorporativo.objects.filter(
            empresa=empresa, semana_referencia__gte=mes_ini
        )
        risco_burnout_pct = None
        if semanais_mes.exists():
            alto_risco = semanais_mes.filter(risco_burnout__gte=4).count()
            risco_burnout_pct = round(alto_risco / semanais_mes.count() * 100)

        apoios_abertos = PedidoApoioCorporativo.objects.filter(
            empresa=empresa,
            status__in=["novo", "em_analise"]
        ).count()

        checkins_hoje = CheckinDiarioCorporativo.objects.filter(
            empresa=empresa, data_referencia=hoje
        ).count()

    except Exception:
        total_func = 0
        bem_estar_geral = None
        risco_burnout_pct = None
        apoios_abertos = 0
        checkins_hoje = 0

    # ── Per-unit breakdown ───────────────────────────────────────────────────
    unidades_data = []
    for u in unidades:
        try:
            func_count = FuncionarioSST.objects.filter(empresa=empresa, unidade=u, ativo=True).count()

            checkins_u = CheckinDiarioCorporativo.objects.filter(
                empresa=empresa, unidade=u, data_referencia__gte=ultimos_7
            )
            avg_u = checkins_u.aggregate(
                humor=Avg("humor"), energia=Avg("energia"),
                estresse=Avg("estresse"), sono=Avg("sono"),
            )
            score = None
            if checkins_u.exists():
                score = round(
                    ((avg_u["humor"] or 0) + (avg_u["energia"] or 0)
                     + (avg_u["sono"] or 0)
                     + (5 - (avg_u["estresse"] or 3))) / 4, 1
                )

            semanais_u = CheckinSemanalCorporativo.objects.filter(
                empresa=empresa, unidade=u, semana_referencia__gte=mes_ini
            )
            burnout_u = None
            if semanais_u.exists():
                alto = semanais_u.filter(risco_burnout__gte=4).count()
                burnout_u = round(alto / semanais_u.count() * 100)

            apoios_u = PedidoApoioCorporativo.objects.filter(
                empresa=empresa, unidade=u, status__in=["novo", "em_analise"]
            ).count()

            checkins_u_hoje = CheckinDiarioCorporativo.objects.filter(
                empresa=empresa, unidade=u, data_referencia=hoje
            ).count()

            adesao = round(checkins_u_hoje / func_count * 100) if func_count > 0 else 0

        except Exception:
            func_count = 0
            score = None
            burnout_u = None
            apoios_u = 0
            adesao = 0

        unidades_data.append({
            "id": u.id,
            "nome": u.nome,
            "codigo": u.codigo or "",
            "funcionarios": func_count,
            "score_bem_estar": score,
            "risco_burnout_pct": burnout_u,
            "apoios_abertos": apoios_u,
            "adesao_hoje_pct": adesao,
        })

    # Sort by score descending (best units first)
    unidades_data.sort(key=lambda x: (x["score_bem_estar"] or 0), reverse=True)

    # ── 30-day trend (company-wide daily avg) ────────────────────────────────
    tendencia = []
    try:
        for delta in range(29, -1, -1):
            d = hoje - timedelta(days=delta)
            dias_checkins = CheckinDiarioCorporativo.objects.filter(
                empresa=empresa, data_referencia=d
            )
            if dias_checkins.exists():
                avg_d = dias_checkins.aggregate(
                    humor=Avg("humor"), energia=Avg("energia"),
                    estresse=Avg("estresse"), sono=Avg("sono"),
                )
                score_d = round(
                    ((avg_d["humor"] or 0) + (avg_d["energia"] or 0)
                     + (avg_d["sono"] or 0)
                     + (5 - (avg_d["estresse"] or 3))) / 4, 2
                )
                tendencia.append({"data": str(d), "score": score_d, "checkins": dias_checkins.count()})
            else:
                tendencia.append({"data": str(d), "score": None, "checkins": 0})
    except Exception:
        tendencia = []

    return JsonResponse({
        "empresa": empresa.nome,
        "data": str(hoje),
        "total_unidades": len(unidades),
        "total_funcionarios": total_func,
        "bem_estar_geral": bem_estar_geral,
        "risco_burnout_pct": risco_burnout_pct,
        "apoios_abertos": apoios_abertos,
        "checkins_hoje": checkins_hoje,
        "unidades": unidades_data,
        "tendencia_30d": tendencia,
    })


def dashboard_rede_page(request):
    from django.shortcuts import render
    return render(request, "dashboard_rede.html")
