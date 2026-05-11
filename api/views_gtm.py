"""
GTM Analytics — funil de vendas, pipeline, Land-and-Expand, ciclo de venda.
Endpoint: GET /api/gtm/funil
          GET /api/gtm/pipeline
          GET /api/gtm/expansao
Page:     GET /gtm/
"""
from datetime import date, timedelta
from django.http import JsonResponse
from .views_dashboard import _empresa_autenticada


ETAPAS_FUNIL = [
    {"etapa": "leads", "label": "Leads Captados", "ordem": 1},
    {"etapa": "qualificados", "label": "Qualificados (MQL)", "ordem": 2},
    {"etapa": "demo", "label": "Demo Realizada", "ordem": 3},
    {"etapa": "proposta", "label": "Proposta Enviada", "ordem": 4},
    {"etapa": "negociacao", "label": "Em Negociação", "ordem": 5},
    {"etapa": "fechado", "label": "Fechado (Won)", "ordem": 6},
]

SEGMENTOS = ["industria", "saude", "varejo", "governo", "financeiro", "outros"]

# Ticket médio por plano (espelho de views_financeiro)
TICKETS = {
    "basico": 990,
    "profissional": 2490,
    "enterprise": 5990,
    "governo": 3990,
    "hospital": 4490,
}


def _funil_dados():
    """Dados do funil de vendas — usa LeadComercial se disponível, senão estima."""
    try:
        from .models import LeadComercial
        from django.db.models import Count

        hoje = date.today()
        desde = hoje - timedelta(days=30)

        funil = []
        for etapa in ETAPAS_FUNIL:
            count = LeadComercial.objects.filter(
                etapa=etapa["etapa"],
                atualizado_em__date__gte=desde,
            ).count()
            funil.append({**etapa, "quantidade": count})

        # Taxa de conversão por etapa
        for i in range(1, len(funil)):
            ant = funil[i - 1]["quantidade"]
            funil[i]["conversao_pct"] = round(funil[i]["quantidade"] / ant * 100, 1) if ant > 0 else 0

        return funil, True
    except Exception:
        # Modelo não existe ainda — retorna estrutura vazia com zeros
        funil = [{**e, "quantidade": 0, "conversao_pct": 0} for e in ETAPAS_FUNIL]
        return funil, False


def _pipeline_valor():
    try:
        from .models import LeadComercial
        from django.db.models import Sum, Count, Avg

        pipeline = LeadComercial.objects.filter(
            etapa__in=["demo", "proposta", "negociacao"]
        ).aggregate(
            total=Count("id"),
            valor_total=Sum("valor_estimado"),
            ticket_medio=Avg("valor_estimado"),
        )
        fechados = LeadComercial.objects.filter(etapa="fechado").aggregate(
            total=Count("id"),
            receita=Sum("valor_estimado"),
        )
        return {
            "oportunidades_ativas": pipeline["total"] or 0,
            "valor_pipeline": float(pipeline["valor_total"] or 0),
            "ticket_medio_pipeline": float(pipeline["ticket_medio"] or 0),
            "fechados_total": fechados["total"] or 0,
            "receita_fechada": float(fechados["receita"] or 0),
            "win_rate_pct": round(
                fechados["total"] / (pipeline["total"] + fechados["total"]) * 100, 1
            ) if (pipeline["total"] or 0) + (fechados["total"] or 0) > 0 else 0,
        }
    except Exception:
        return {
            "oportunidades_ativas": 0,
            "valor_pipeline": 0.0,
            "ticket_medio_pipeline": 0.0,
            "fechados_total": 0,
            "receita_fechada": 0.0,
            "win_rate_pct": 0.0,
        }


def _land_and_expand():
    """Métricas de expansão de clientes existentes."""
    try:
        from .models import Empresa
        from django.db.models import Count

        hoje = date.today()
        # Empresas com múltiplas unidades (já expandiram)
        multi_unidade = Empresa.objects.filter(ativo=True).annotate(
            n_unidades=Count("unidades")
        ).filter(n_unidades__gt=1)

        total_ativas = Empresa.objects.filter(ativo=True).count()
        expandidas = multi_unidade.count()
        taxa_expansao = round(expandidas / total_ativas * 100, 1) if total_ativas > 0 else 0

        # Novas unidades nos últimos 30 dias
        from .models import EmpresaUnidade
        novas_unidades = EmpresaUnidade.objects.filter(
            criado_em__date__gte=hoje - timedelta(days=30)
        ).count()

        return {
            "total_clientes_ativos": total_ativas,
            "clientes_multi_unidade": expandidas,
            "taxa_expansao_pct": taxa_expansao,
            "novas_unidades_30d": novas_unidades,
        }
    except Exception:
        try:
            from .models import Empresa
            total = Empresa.objects.filter(ativo=True).count()
            return {
                "total_clientes_ativos": total,
                "clientes_multi_unidade": 0,
                "taxa_expansao_pct": 0.0,
                "novas_unidades_30d": 0,
            }
        except Exception:
            return {
                "total_clientes_ativos": 0,
                "clientes_multi_unidade": 0,
                "taxa_expansao_pct": 0.0,
                "novas_unidades_30d": 0,
            }


def _metas_trimestre():
    hoje = date.today()
    mes = hoje.month
    trimestre = (mes - 1) // 3 + 1
    return {
        "trimestre": f"Q{trimestre}/{hoje.year}",
        "meta_novos_clientes": 20,
        "meta_arr_incremental": 500000,
        "meta_nrr": 110,
        "meta_churn_max_pct": 2.0,
        "nota": "Metas definidas manualmente — integrar com CRM para automação",
    }


def api_gtm_funil(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    funil, tem_dados = _funil_dados()
    return JsonResponse({
        "empresa": empresa.nome,
        "periodo": "últimos 30 dias",
        "funil": funil,
        "tem_dados_crm": tem_dados,
        "nota": "Integre LeadComercial para dados reais de funil" if not tem_dados else None,
    })


def api_gtm_pipeline(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    pipeline = _pipeline_valor()
    expansao = _land_and_expand()
    metas = _metas_trimestre()

    # Ciclo médio de venda estimado (benchmark SaaS enterprise B2B)
    ciclo_medio = {
        "basico": 21,        # dias
        "profissional": 45,
        "enterprise": 90,
        "governo": 180,
    }

    return JsonResponse({
        "empresa": empresa.nome,
        "gerado_em": str(date.today()),
        "pipeline": pipeline,
        "land_and_expand": expansao,
        "metas_trimestre": metas,
        "ciclo_venda_estimado_dias": ciclo_medio,
        "distribuicao_por_segmento": [
            {"segmento": s, "oportunidades": 0, "nota": "integrar CRM"} for s in SEGMENTOS
        ],
    })


def api_gtm_expansao(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    expansao = _land_and_expand()

    # Oportunidades de expansão por cliente
    try:
        from .models import Empresa
        MODULOS_EXTRAS = ["farmacia", "hospital", "sst", "competencia", "escalas"]
        clientes_sem_modulos = []
        for emp in Empresa.objects.filter(ativo=True)[:50]:
            modulos_ativos = emp.pacote_codigo or "basico"
            oportunidades = [m for m in MODULOS_EXTRAS if m not in modulos_ativos]
            if oportunidades:
                clientes_sem_modulos.append({
                    "empresa": emp.nome,
                    "plano_atual": emp.pacote_codigo,
                    "modulos_oportunidade": oportunidades[:3],
                })
        expansao["oportunidades_upsell"] = clientes_sem_modulos[:10]
    except Exception:
        expansao["oportunidades_upsell"] = []

    return JsonResponse(expansao)


def gtm_page(request):
    from django.shortcuts import render
    return render(request, "gtm.html")
