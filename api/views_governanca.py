"""
Governança Executiva — painel semanal de decisão por métrica.
Financial OS completo: burn multiple, runway, ARR waterfall.
Pricing por valor, scoring de leads, ciclo de venda real.
Fairness básica para modelos de ML.

Endpoint: GET /api/governanca/semanal
          GET /api/governanca/burn-multiple
          GET /api/governanca/pricing-valor
          GET /api/governanca/ml-fairness
          GET /api/governanca/causal-impact
Page:     GET /governanca/
"""
from datetime import date, timedelta
from django.http import JsonResponse
from django.db.models import Count, Avg, Sum, Q
from .services.auth_session import dono_autenticado_from_request, empresa_autenticada_from_request
from .views_financeiro import _arr_atual, _churn_ultimos_90, _nrr_estimado


def _burn_multiple(mrr_atual, mrr_anterior, burn_mensal_estimado):
    """Burn Multiple = Net Burn / Net New ARR."""
    net_new_mrr = mrr_atual - mrr_anterior
    net_new_arr = net_new_mrr * 12
    if net_new_arr <= 0:
        return None, "sem crescimento"
    bm = round(burn_mensal_estimado / net_new_mrr, 2) if net_new_mrr > 0 else None
    if bm is None:
        grade = "n/a"
    elif bm <= 1:
        grade = "excelente"
    elif bm <= 1.5:
        grade = "bom"
    elif bm <= 2:
        grade = "aceitável"
    else:
        grade = "preocupante"
    return bm, grade


def _arr_waterfall():
    """ARR Waterfall: novo + expansão - contração - churn."""
    try:
        from .models import Empresa
        TICKETS = {
            "basico": 990, "profissional": 2490,
            "enterprise": 5990, "governo": 3990, "hospital": 4490,
        }
        hoje = date.today()
        mes_atual = hoje.replace(day=1)
        mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)

        novos = Empresa.objects.filter(
            ativo=True,
            criado_em__date__gte=mes_atual,
        )
        arr_novos = sum(TICKETS.get(e["pacote_codigo"], 990) * 12 for e in novos.values("pacote_codigo"))

        churned = Empresa.objects.filter(
            ativo=False,
            atualizado_em__date__gte=mes_atual,
        )
        arr_churn = sum(TICKETS.get(e["pacote_codigo"], 990) * 12 for e in churned.values("pacote_codigo"))

        return {
            "arr_novos": arr_novos,
            "arr_expansao": 0,       # requer histórico de plano — placeholder
            "arr_contracao": 0,
            "arr_churn": arr_churn,
            "arr_liquido": arr_novos - arr_churn,
            "nota": "Expansão/contração requer histórico de mudança de plano",
        }
    except Exception:
        return {"arr_novos": 0, "arr_churn": 0, "arr_liquido": 0}


def _pricing_por_valor():
    """Sugere pricing por resultado com base em métricas reais."""
    return {
        "modelos": [
            {
                "nome": "Success-Based SST",
                "descricao": "Cobrança por conformidade alcançada — preço base + % de conformidade SST",
                "formula": "R$ 500/mês base + R$ 20 por ponto de score acima de 80",
                "metricas_vinculadas": ["score_sst_empresa", "exames_em_dia_pct"],
                "potencial_upsell": "Alto — alinha incentivos com resultado real",
            },
            {
                "nome": "Engagement Pricing",
                "descricao": "Desconto por adimplência de check-ins — clientes engajados pagam menos por colaborador",
                "formula": "R$ 15/colaborador com desconto de 20% se adimplência > 70%",
                "metricas_vinculadas": ["taxa_adimplencia_checkin"],
                "potencial_upsell": "Médio — incentiva uso e reduz churn",
            },
            {
                "nome": "Outcome-Based Burnout",
                "descricao": "Fee de sucesso por redução de burnout medida em 6 meses",
                "formula": "R$ 10.000 de fee se score burnout cair > 1 ponto em 6 meses",
                "metricas_vinculadas": ["score_burnout", "media_risco_burnout"],
                "potencial_upsell": "Alto — prova ROI tangível para RH",
            },
            {
                "nome": "Platform Tier + Usage",
                "descricao": "Tier fixo + cobrança por evento crítico tratado (SST, farmácia, hospital)",
                "formula": "R$ 2.000/mês + R$ 50 por alerta crítico resolvido dentro do SLA",
                "metricas_vinculadas": ["eventos_criticos_periodo", "sla_resolucao"],
                "potencial_upsell": "Médio — permite crescimento orgânico com clientes maiores",
            },
        ],
        "recomendacao": "Success-Based SST para segmento indústria. Engagement Pricing para PME.",
    }


def _scoring_leads():
    """Modelo de scoring de leads por fit e timing."""
    return {
        "criterios": [
            {"criterio": "Tamanho da empresa", "peso": 25, "valores": {"<50": 5, "50-200": 15, "200-500": 22, ">500": 25}},
            {"criterio": "Setor de alto risco SST", "peso": 20, "valores": {"sim": 20, "nao": 5}},
            {"criterio": "Possui farmácia/ambulatório", "peso": 15, "valores": {"sim": 15, "nao": 0}},
            {"criterio": "Nível de maturidade digital", "peso": 15, "valores": {"baixo": 3, "medio": 10, "alto": 15}},
            {"criterio": "Ciclo de compra ativo", "peso": 15, "valores": {"sim": 15, "nao": 0}},
            {"criterio": "Budget confirmado", "peso": 10, "valores": {"sim": 10, "parcial": 5, "nao": 0}},
        ],
        "segmentos": {
            "industria_pesada": {"score_min": 70, "ciclo_dias": 60, "ticket_medio": 4990},
            "saude_privada": {"score_min": 65, "ciclo_dias": 90, "ticket_medio": 5990},
            "varejo_grande": {"score_min": 55, "ciclo_dias": 45, "ticket_medio": 2490},
            "governo_municipal": {"score_min": 60, "ciclo_dias": 180, "ticket_medio": 3990},
            "pme_geral": {"score_min": 40, "ciclo_dias": 21, "ticket_medio": 990},
        },
        "nota": "Implemente LeadComercial model e registre scores reais para análise estatística",
    }


def _ml_fairness(empresa):
    """Análise básica de fairness dos modelos por grupo."""
    try:
        from .models import ModeloML, RunModelo
        from django.db.models import Count

        modelos = ModeloML.objects.filter(empresa=empresa, status="producao")
        fairness = []
        for m in modelos:
            runs_com_gt = RunModelo.objects.filter(modelo=m, correto__isnull=False)
            total = runs_com_gt.count()
            if total == 0:
                continue
            corretos = runs_com_gt.filter(correto=True).count()
            precisao_global = round(corretos / total * 100, 1)
            fairness.append({
                "modelo": m.nome,
                "slug": m.slug,
                "precisao_global": precisao_global,
                "total_runs_avaliados": total,
                "slo_min": round(m.slo_precisao_min * 100, 0),
                "dentro_slo": precisao_global >= m.slo_precisao_min * 100,
                "nota_fairness": "Adicione campo 'grupo' nos RunModelo para análise de fairness por segmento",
                "proximos_passos": [
                    "Segmentar precisão por cargo/setor",
                    "Verificar disparidade de taxa de erro por grupo demográfico",
                    "Implementar rebalanceamento de dados de treino se disparidade > 5pp",
                ],
            })
        return fairness
    except Exception:
        return []


def _causal_impact(empresa):
    """Estimativa de impacto causal da plataforma em KPIs operacionais."""
    try:
        from .models import CheckinSemanalCorporativo, AfastamentoSST, FuncionarioSST
        from django.db.models import Avg
        hoje = date.today()

        # Impacto em burnout: compara primeiros 30 dias vs últimos 30 dias
        ini = hoje - timedelta(days=180)
        mid = hoje - timedelta(days=90)

        antes = CheckinSemanalCorporativo.objects.filter(
            empresa=empresa, semana_referencia__gte=ini, semana_referencia__lt=mid
        ).aggregate(avg=Avg("risco_burnout"))["avg"] or 0

        depois = CheckinSemanalCorporativo.objects.filter(
            empresa=empresa, semana_referencia__gte=mid
        ).aggregate(avg=Avg("risco_burnout"))["avg"] or 0

        delta_burnout = round(antes - depois, 2)

        # Impacto em afastamentos
        afast_antes = AfastamentoSST.objects.filter(
            funcionario__empresa=empresa,
            data_inicio__gte=ini, data_inicio__lt=mid,
        ).count()
        afast_depois = AfastamentoSST.objects.filter(
            funcionario__empresa=empresa,
            data_inicio__gte=mid,
        ).count()

        return {
            "periodo_analise": f"{str(ini)} → {str(hoje)} (180 dias, split no meio)",
            "burnout": {
                "media_antes": round(antes, 2),
                "media_depois": round(depois, 2),
                "delta": delta_burnout,
                "direcao": "melhora" if delta_burnout > 0 else ("piora" if delta_burnout < 0 else "estavel"),
            },
            "afastamentos": {
                "antes_90d": afast_antes,
                "depois_90d": afast_depois,
                "delta": afast_depois - afast_antes,
                "direcao": "melhora" if afast_depois < afast_antes else ("piora" if afast_depois > afast_antes else "estavel"),
            },
            "nota_causalidade": "Correlação observacional — não inferência causal. Para análise causal real, implemente grupo de controle (holdout set) ou diferença-em-diferenças com dados históricos pré-plataforma.",
            "proximos_passos": [
                "Coletar dados 6 meses antes da implantação como baseline",
                "Definir grupo de controle (unidades sem plataforma)",
                "Usar DiD ou Synthetic Control para estimativa causal",
                "Traduzir em ROI: R$ economizados por afastamento evitado",
            ],
        }
    except Exception:
        return {"nota": "Dados insuficientes para análise de impacto causal"}


def api_governanca_semanal(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    arr_anual, mrr, clientes = _arr_atual()
    canceladas, base, churn_rate = _churn_ultimos_90()
    nrr = _nrr_estimado()
    waterfall = _arr_waterfall()

    # Burn multiple estimado (sem dados reais de despesas ainda)
    burn_mensal_est = mrr * 0.7  # estimativa conservadora: 70% do MRR em despesas
    # MRR mês anterior (proxy: MRR - novos + churned)
    mrr_anterior = mrr - (waterfall["arr_novos"] / 12) + (waterfall["arr_churn"] / 12)
    bm, bm_grade = _burn_multiple(mrr, mrr_anterior, burn_mensal_est)

    # Runway
    caixa_estimado = mrr * 6  # placeholder — sem dados reais de caixa
    burn_liquido = max(burn_mensal_est - mrr, 0)
    runway_meses = round(caixa_estimado / burn_liquido) if burn_liquido > 0 else 999

    hoje = date.today()
    semana = hoje.isocalendar()[1]

    pauta = []
    if churn_rate > 3:
        pauta.append({"prioridade": 1, "topico": "Churn acima de 3%", "acao": "Revisar clientes em risco + entrevistar churned accounts", "owner": "CS"})
    if nrr < 100:
        pauta.append({"prioridade": 1, "topico": "NRR < 100% — base encolhendo", "acao": "Ativar plano de expansão: upsell + cross-sell", "owner": "Sales"})
    if waterfall["arr_novos"] == 0:
        pauta.append({"prioridade": 2, "topico": "Sem novos clientes no mês", "acao": "Revisar pipeline e acelerar demos", "owner": "Sales"})
    if bm and bm > 2:
        pauta.append({"prioridade": 2, "topico": f"Burn Multiple em {bm}x", "acao": "Revisar alocação de headcount e CAC", "owner": "CEO/CFO"})
    if not pauta:
        pauta.append({"prioridade": 3, "topico": "Métricas dentro do esperado", "acao": "Manter cadência de crescimento e execução", "owner": "Time"})

    return JsonResponse({
        "empresa": empresa.nome,
        "semana": f"S{semana}/{hoje.year}",
        "gerado_em": str(hoje),
        "kpis_semana": {
            "arr": round(arr_anual, 2),
            "mrr": round(mrr, 2),
            "clientes": clientes,
            "churn_rate_90d": churn_rate,
            "nrr": nrr,
            "burn_multiple": bm,
            "burn_multiple_grade": bm_grade,
            "runway_meses": runway_meses,
        },
        "arr_waterfall": waterfall,
        "pauta_executiva": pauta,
        "proxima_revisao": str(hoje + timedelta(days=7 - hoje.weekday())),
    })


def api_governanca_burn_multiple(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    arr_anual, mrr, clientes = _arr_atual()
    waterfall = _arr_waterfall()
    burn_mensal_est = mrr * 0.7
    mrr_anterior = mrr - (waterfall["arr_novos"] / 12) + (waterfall["arr_churn"] / 12)
    bm, grade = _burn_multiple(mrr, mrr_anterior, burn_mensal_est)

    return JsonResponse({
        "burn_multiple": bm,
        "grade": grade,
        "mrr_atual": round(mrr, 2),
        "mrr_anterior_estimado": round(mrr_anterior, 2),
        "burn_mensal_estimado": round(burn_mensal_est, 2),
        "arr_waterfall": waterfall,
        "benchmarks": {
            "excelente": "<= 1x",
            "bom": "1x - 1.5x",
            "aceitavel": "1.5x - 2x",
            "preocupante": "> 2x",
        },
        "nota": "Burn estimado em 70% do MRR. Integre dados reais de despesas para cálculo preciso.",
    })


def api_governanca_pricing_valor(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
    return JsonResponse({
        "empresa": empresa.nome,
        **_pricing_por_valor(),
        "scoring_leads": _scoring_leads(),
    })


def api_governanca_ml_fairness(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
    return JsonResponse({
        "empresa": empresa.nome,
        "modelos": _ml_fairness(empresa),
        "framework_fairness": {
            "metricas_avaliadas": ["precisao_global", "taxa_erro_por_grupo"],
            "limiar_disparidade": "5 pontos percentuais",
            "politica": "Modelos com disparidade > 5pp devem ser rebalanceados antes de produção",
        },
    })


def api_governanca_causal_impact(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
    return JsonResponse({
        "empresa": empresa.nome,
        **_causal_impact(empresa),
    })


def governanca_page(request):
    from django.shortcuts import render, redirect
    dono = dono_autenticado_from_request(request)
    if not dono:
        empresa = getattr(request, "empresa", None)
        if empresa:
            from .access_control import get_setor, _destino_correto
            return redirect(_destino_correto(get_setor(empresa)))
        return redirect("/operacao-central/")
    return render(request, "governanca.html")
