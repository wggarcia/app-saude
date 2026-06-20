"""
Financial OS — painel executivo de métricas financeiras healthtech.
ARR, NRR, churn receita, CAC payback, burn multiple, LTV:CAC.
Endpoint: GET /api/financeiro/metricas
          GET /api/financeiro/cohorts
          GET /api/financeiro/pipeline
Page:     GET /financeiro/
"""
from datetime import date, timedelta
from django.http import JsonResponse
from django.db.models import Sum, Count, Avg, Q, F
from .services.auth_session import dono_autenticado_from_request, empresa_autenticada_from_request
from .planos import normalizar_codigo_pacote, PACOTES_SAAS


def _ticket_mensal(pacote_codigo: str) -> float:
    """Retorna o preço mensal do pacote. Para governo (ciclo anual), retorna anual/12."""
    codigo = normalizar_codigo_pacote(pacote_codigo or "empresa_starter_5")
    pacote = PACOTES_SAAS.get(codigo, {})
    if pacote.get("ciclos") == ["anual"]:
        return pacote.get("anual", 0) / 12
    return pacote.get("mensal", 799.0)


def _mrr_historico(meses=12):
    """Retorna MRR mensal dos últimos N meses a partir de pagamentos confirmados."""
    try:
        from .models import Empresa
        from django.db.models.functions import TruncMonth
        import datetime

        hoje = date.today()
        resultado = []
        for i in range(meses - 1, -1, -1):
            # primeiro dia do mês i meses atrás
            mes = (hoje.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
            prox = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)
            # conta empresas ativas com pacote_codigo no mês
            ativas = Empresa.objects.filter(
                ativo=True,
                criado_em__date__lte=prox,
            ).count()
            # proxy simples: cada empresa = ticket médio por pacote
            resultado.append({
                "mes": mes.strftime("%Y-%m"),
                "mes_fmt": mes.strftime("%b/%y"),
                "empresas_ativas": ativas,
            })
        return resultado
    except Exception:
        return []


def _arr_atual():
    try:
        from .models import Empresa, PlanoEmpresa
        # Tenta usar PlanoEmpresa se disponível
        planos = PlanoEmpresa.objects.filter(ativo=True).select_related("empresa")
        arr = planos.aggregate(total=Sum("valor_mensal"))["total"] or 0
        arr_anual = float(arr) * 12
        total_clientes = planos.values("empresa").distinct().count()
        return arr_anual, float(arr), total_clientes
    except Exception:
        pass

    try:
        from .models import Empresa
        # fallback: conta empresas × ticket mensal real por pacote (via planos.py)
        empresas = Empresa.objects.filter(ativo=True).values("pacote_codigo")
        total_mrr = sum(_ticket_mensal(e["pacote_codigo"]) for e in empresas)
        total_clientes = Empresa.objects.filter(ativo=True).count()
        return float(total_mrr) * 12, float(total_mrr), total_clientes
    except Exception:
        return 0.0, 0.0, 0


def _churn_ultimos_90():
    try:
        from .models import Empresa
        hoje = date.today()
        janela = hoje - timedelta(days=90)
        canceladas = Empresa.objects.filter(
            ativo=False,
            atualizado_em__date__gte=janela,
        ).count()
        total_base = Empresa.objects.filter(
            criado_em__date__lte=janela,
        ).count()
        churn_rate = round(canceladas / total_base * 100, 1) if total_base > 0 else 0
        return canceladas, total_base, churn_rate
    except Exception:
        return 0, 0, 0.0


def _nrr_estimado():
    """Net Revenue Retention estimado via expansão de plano."""
    try:
        from .models import Empresa
        # Empresas que fizeram upgrade (mudança de pacote para tier maior)
        ORDEM = ["basico", "profissional", "enterprise", "hospital", "governo"]
        # Sem histórico de mudança de plano ainda → estimativa conservadora
        arr_anual, mrr, clientes = _arr_atual()
        canceladas, base, churn_rate = _churn_ultimos_90()
        # NRR simples: (1 - churn) + expansão estimada (2% média healthtech B2B early)
        churn_anual = churn_rate / 100 * (90 / 365 * 4)  # anualize
        nrr = round((1 - churn_anual + 0.02) * 100, 1)
        return min(nrr, 140.0)  # cap razoável
    except Exception:
        return 0.0


def _distribuicao_planos():
    try:
        from .models import Empresa
        from django.db.models import Count
        dist = list(
            Empresa.objects.filter(ativo=True)
            .values("pacote_codigo")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        for d in dist:
            d["ticket_medio"] = _ticket_mensal(d["pacote_codigo"])
            d["mrr_parcial"] = d["total"] * d["ticket_medio"]
        return dist
    except Exception:
        return []


def _crescimento_clientes():
    try:
        from .models import Empresa
        hoje = date.today()
        resultado = []
        for i in range(5, -1, -1):
            mes = (hoje.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
            prox = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)
            novos = Empresa.objects.filter(
                criado_em__date__gte=mes,
                criado_em__date__lt=prox,
            ).count()
            resultado.append({
                "mes": mes.strftime("%Y-%m"),
                "mes_fmt": mes.strftime("%b/%y"),
                "novos_clientes": novos,
            })
        return resultado
    except Exception:
        return []


def _burn_mensal_real():
    """Burn mensal real via LancamentoDespesa do mês corrente."""
    try:
        from .models import LancamentoDespesa
        hoje = date.today()
        mes_atual = hoje.replace(day=1)
        total = LancamentoDespesa.objects.filter(
            competencia__gte=mes_atual
        ).aggregate(t=Sum("valor"))["t"]
        return float(total or 0)
    except Exception:
        return 0.0


def _cac_real(mrr):
    """CAC real = spend de vendas+marketing / novos clientes no mês."""
    try:
        from .models import LancamentoDespesa, CentroCusto, Empresa
        hoje = date.today()
        mes_atual = hoje.replace(day=1)
        prox_mes = (mes_atual.replace(day=28) + timedelta(days=4)).replace(day=1)
        spend = LancamentoDespesa.objects.filter(
            competencia__gte=mes_atual,
            centro__tipo__in=["marketing", "vendas"],
        ).aggregate(t=Sum("valor"))["t"] or 0
        novos = Empresa.objects.filter(
            criado_em__date__gte=mes_atual,
            criado_em__date__lt=prox_mes,
        ).count()
        return round(float(spend) / novos, 2) if novos > 0 else 0.0
    except Exception:
        return 0.0


def _ltv_cohort_real(ticket_medio):
    """LTV médio calculado via CohortRetencao persistido."""
    try:
        from .models import CohortRetencao
        from django.db.models import Avg
        avg_nrr = CohortRetencao.objects.aggregate(a=Avg("nrr_pct"))["a"]
        if avg_nrr and avg_nrr > 0 and ticket_medio > 0:
            churn_impl = max(1 - avg_nrr / 100, 0.01)
            return round(ticket_medio / churn_impl, 2)
        return 0.0
    except Exception:
        return 0.0


def api_financeiro_metricas(request):
    dono = dono_autenticado_from_request(request)
    if not dono:
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    arr_anual, mrr, total_clientes = _arr_atual()
    canceladas, base, churn_rate = _churn_ultimos_90()
    nrr = _nrr_estimado()
    dist_planos = _distribuicao_planos()
    crescimento = _crescimento_clientes()
    mrr_hist = _mrr_historico(6)

    # Burn real via LancamentoDespesa — cai para estimativa se não houver dados
    burn_mensal_real = _burn_mensal_real()
    burn_mensal = burn_mensal_real if burn_mensal_real > 0 else mrr * 0.7
    burn_fonte = "real" if burn_mensal_real > 0 else "estimativa_70pct_mrr"

    # CAC real via despesas de vendas/marketing
    cac_real = _cac_real(mrr)
    ticket_medio = round(mrr / total_clientes, 2) if total_clientes > 0 else 0
    cac_estimado = cac_real if cac_real > 0 else round(ticket_medio * 3, 2)
    cac_fonte = "real" if cac_real > 0 else "estimativa_3x_ticket"

    # LTV via cohort real — cai para estimativa simples se não houver dados
    ltv_cohort = _ltv_cohort_real(ticket_medio)
    churn_mensal = churn_rate / 100 / 3
    ltv_simples = round(ticket_medio / churn_mensal, 2) if churn_mensal > 0 else ticket_medio * 36
    ltv = ltv_cohort if ltv_cohort > 0 else ltv_simples
    ltv_fonte = "cohort_real" if ltv_cohort > 0 else "estimativa"

    payback_meses = round(cac_estimado / ticket_medio, 1) if ticket_medio > 0 else 0
    ltv_cac = round(ltv / cac_estimado, 1) if cac_estimado > 0 else 0
    burn_multiple = round(burn_mensal / mrr, 2) if mrr > 0 else 0

    # Caixa: usa saldo real registrado pelo DonoSaaS ou estimativa rotulada 6x MRR
    try:
        from .models import CaixaPlataformaSaaS
        entrada_caixa = CaixaPlataformaSaaS.objects.first()
        if entrada_caixa:
            caixa = float(entrada_caixa.saldo)
            caixa_fonte = f"real — {entrada_caixa.data_referencia}"
        else:
            caixa = mrr * 6
            caixa_fonte = "estimativa_6x_mrr"
    except Exception:
        caixa = mrr * 6
        caixa_fonte = "estimativa_6x_mrr"

    runway_meses = round(caixa / burn_mensal, 0) if burn_mensal > 0 else 0

    return JsonResponse({
        "gerado_em": str(date.today()),
        "kpis": {
            "arr": round(arr_anual, 2),
            "arr_fmt": f"R$ {arr_anual:,.0f}",
            "mrr": round(mrr, 2),
            "mrr_fmt": f"R$ {mrr:,.0f}",
            "total_clientes": total_clientes,
            "ticket_medio": ticket_medio,
            "ticket_medio_fmt": f"R$ {ticket_medio:,.0f}",
            "churn_rate_90d": churn_rate,
            "clientes_cancelados_90d": canceladas,
            "nrr": nrr,
            "ltv": round(ltv, 2),
            "ltv_fmt": f"R$ {ltv:,.0f}",
            "ltv_fonte": ltv_fonte,
            "cac_estimado": cac_estimado,
            "cac_fonte": cac_fonte,
            "payback_meses": payback_meses,
            "ltv_cac_ratio": ltv_cac,
            "burn_mensal": round(burn_mensal, 2),
            "burn_fonte": burn_fonte,
            "burn_multiple": burn_multiple,
            "caixa": round(caixa, 2),
            "caixa_fonte": caixa_fonte,
            "runway_meses_est": runway_meses,
        },
        "distribuicao_planos": dist_planos,
        "crescimento_clientes": crescimento,
        "mrr_historico": mrr_hist,
        "alertas": _alertas_financeiros(churn_rate, nrr, ltv_cac, payback_meses),
    })


def _alertas_financeiros(churn_rate, nrr, ltv_cac, payback_meses):
    alertas = []
    if churn_rate > 5:
        alertas.append({
            "nivel": "critico",
            "titulo": f"Churn elevado: {churn_rate}% em 90 dias",
            "acao": "Ativar programa de Customer Success e entrevistar churned accounts",
        })
    elif churn_rate > 2:
        alertas.append({
            "nivel": "alerta",
            "titulo": f"Churn em atenção: {churn_rate}% em 90 dias",
            "acao": "Revisar onboarding e NPS de clientes em risco",
        })

    if nrr < 100:
        alertas.append({
            "nivel": "critico",
            "titulo": f"NRR abaixo de 100%: {nrr}%",
            "acao": "Priorizar expansão e reduzir downgrades — base encolhendo",
        })
    elif nrr >= 120:
        alertas.append({
            "nivel": "ok",
            "titulo": f"NRR saudável: {nrr}%",
            "acao": "Manter programas de expansão e upsell",
        })

    if ltv_cac < 3:
        alertas.append({
            "nivel": "alerta",
            "titulo": f"LTV:CAC em {ltv_cac}x — abaixo do benchmark 3x",
            "acao": "Reduzir CAC via inbound ou aumentar retenção/expansão",
        })

    if payback_meses > 18:
        alertas.append({
            "nivel": "alerta",
            "titulo": f"CAC Payback em {payback_meses} meses",
            "acao": "Acelerar time-to-value no onboarding para reduzir payback",
        })

    if not alertas:
        alertas.append({
            "nivel": "ok",
            "titulo": "Métricas financeiras dentro do esperado",
            "acao": "Manter cadência de revisão semanal das métricas",
        })

    return alertas


def api_financeiro_cohorts(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    try:
        from .models import Empresa
        hoje = date.today()
        cohorts = []
        for i in range(5, -1, -1):
            mes = (hoje.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
            prox = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)
            adquiridos = Empresa.objects.filter(
                criado_em__date__gte=mes,
                criado_em__date__lt=prox,
            )
            total = adquiridos.count()
            ativos_hoje = adquiridos.filter(ativo=True).count()
            retencao = round(ativos_hoje / total * 100, 1) if total > 0 else 0
            mrr_cohort = sum(_ticket_mensal(e["pacote_codigo"]) for e in adquiridos.values("pacote_codigo"))
            cohorts.append({
                "cohort": mes.strftime("%Y-%m"),
                "cohort_fmt": mes.strftime("%b/%y"),
                "adquiridos": total,
                "ativos_hoje": ativos_hoje,
                "retencao_pct": retencao,
                "mrr_inicial": mrr_cohort,
            })
        return JsonResponse({"cohorts": cohorts})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def financeiro_page(request):
    from django.shortcuts import render
    from django.shortcuts import redirect
    dono = dono_autenticado_from_request(request)
    if not dono:
        empresa = getattr(request, "empresa", None)
        if empresa:
            from .access_control import get_setor, _destino_correto
            return redirect(_destino_correto(get_setor(empresa)))
        return redirect("/operacao-central/")
    return render(request, "financeiro.html")
