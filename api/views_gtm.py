"""
GTM Analytics — funil de vendas, pipeline, Land-and-Expand, ciclo de venda.
Endpoint: GET /api/gtm/funil
          GET /api/gtm/pipeline
          GET /api/gtm/expansao
Page:     GET /gtm/
"""
from datetime import date, timedelta
from django.http import JsonResponse
from .services.auth_session import dono_autenticado_from_request, empresa_autenticada_from_request


ETAPAS_FUNIL = [
    {"etapa": "leads", "label": "Leads Captados", "ordem": 1},
    {"etapa": "qualificados", "label": "Qualificados (MQL)", "ordem": 2},
    {"etapa": "demo", "label": "Demo Realizada", "ordem": 3},
    {"etapa": "proposta", "label": "Proposta Enviada", "ordem": 4},
    {"etapa": "negociacao", "label": "Em Negociação", "ordem": 5},
    {"etapa": "fechado", "label": "Fechado (Won)", "ordem": 6},
]

SEGMENTOS = ["industria", "saude", "varejo", "governo", "financeiro", "outros"]

# Ticket médio por plano — lido diretamente do planos.py (fonte da verdade)
from .planos import preco_pacote, normalizar_codigo_pacote, PACOTES_SAAS

def _ticket_mensal(pacote_codigo: str) -> float:
    """Retorna o preço mensal do pacote. Para governo (ciclo anual), retorna anual/12."""
    codigo = normalizar_codigo_pacote(pacote_codigo or "empresa_starter_5")
    pacote = PACOTES_SAAS.get(codigo, {})
    if pacote.get("ciclos") == ["anual"]:
        return pacote.get("anual", 0) / 12
    return pacote.get("mensal", 799.0)

# Legado: dicionário estático substituído — use _ticket_mensal() para novos cálculos
TICKETS = {k: _ticket_mensal(k) for k in [
    "empresa_starter_5", "empresa_profissional_25", "empresa_enterprise_100",
    "empresa_corporativo_250", "empresa_nacional_500", "empresa_nacional_1000",
    "farmacia_local", "farmacia_rede_regional", "farmacia_rede_nacional",
    "hospital_medio", "hospital_rede", "hospital_grupo",
    "governo_municipio_pequeno", "governo_municipio_medio",
    "governo_capital_regiao", "governo_estado",
    "plano_saude_operadora", "plano_saude_enterprise",
    "rede_regional", "rede_nacional",
]}


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
    }


def _nrr_real():
    """NRR real calculado via ExpansaoContrato + churn dos últimos 90 dias."""
    try:
        from .models import ExpansaoContrato, Empresa
        from django.db.models import Sum
        hoje = date.today()
        janela = hoje - timedelta(days=90)

        # MRR base (início do período)
        canceladas = Empresa.objects.filter(ativo=False, atualizado_em__date__gte=janela).count()
        base = Empresa.objects.filter(criado_em__date__lte=janela).count()

        # Expansão real de MRR no período
        expansao = ExpansaoContrato.objects.filter(
            criado_em__date__gte=janela
        ).aggregate(delta=Sum("delta_mrr"))["delta"] or 0

        mrr_base = sum(
            _ticket_mensal(e["pacote_codigo"])
            for e in Empresa.objects.filter(criado_em__date__lte=janela).values("pacote_codigo")
        )

        if mrr_base <= 0:
            return 100.0

        churn_mrr = canceladas * 799  # estimativa conservadora (Starter = menor plano)
        nrr = round(((mrr_base - churn_mrr + float(expansao)) / mrr_base) * 100, 1)
        return min(max(nrr, 0.0), 200.0)
    except Exception:
        return 0.0


def _ciclo_medio_real():
    """Ciclo médio de vendas real em dias por segmento."""
    try:
        from .models import LeadComercial
        from django.db.models import Avg
        resultado = {}
        for seg in SEGMENTOS:
            avg = LeadComercial.objects.filter(
                segmento=seg,
                etapa="fechado",
                ciclo_dias__isnull=False,
            ).aggregate(media=Avg("ciclo_dias"))["media"]
            if avg:
                resultado[seg] = round(avg, 0)
        return resultado or {"nota": "Nenhum ciclo registrado ainda"}
    except Exception:
        return {}


def api_gtm_funil(request):
    dono = dono_autenticado_from_request(request)
    if not dono:
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    funil, tem_dados = _funil_dados()
    return JsonResponse({
        "periodo": "últimos 30 dias",
        "funil": funil,
        "tem_dados_crm": tem_dados,
    })


def api_gtm_pipeline(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    pipeline = _pipeline_valor()
    expansao = _land_and_expand()
    metas = _metas_trimestre()
    nrr = _nrr_real()
    ciclo_real = _ciclo_medio_real()

    return JsonResponse({
        "gerado_em": str(date.today()),
        "pipeline": pipeline,
        "land_and_expand": expansao,
        "metas_trimestre": metas,
        "nrr_real_pct": nrr,
        "ciclo_medio_real_dias": ciclo_real,
        "distribuicao_por_segmento": [
            {"segmento": s, "oportunidades": 0, "nota": "integrar CRM"} for s in SEGMENTOS
        ],
    })


def api_gtm_expansao(request):
    if not dono_autenticado_from_request(request):
        return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)

    expansao = _land_and_expand()

    # Oportunidades de expansão — empresas em planos inferiores
    try:
        from .models import Empresa, ExpansaoContrato
        from django.db.models import Sum
        ORDEM_PLANO = [
            "empresa_starter_5", "empresa_profissional_25",
            "empresa_enterprise_100", "empresa_corporativo_250", "empresa_nacional_500",
        ]
        clientes_upsell = []
        for emp in Empresa.objects.filter(ativo=True).order_by("pacote_codigo")[:50]:
            idx = ORDEM_PLANO.index(emp.pacote_codigo) if emp.pacote_codigo in ORDEM_PLANO else -1
            if 0 <= idx < len(ORDEM_PLANO) - 1:
                clientes_upsell.append({
                    "empresa": emp.nome,
                    "plano_atual": emp.pacote_codigo,
                    "proximo_plano": ORDEM_PLANO[idx + 1],
                })
        expansao["oportunidades_upsell"] = clientes_upsell[:10]
        expansao["expansao_mrr_90d"] = float(
            ExpansaoContrato.objects.filter(
                criado_em__date__gte=date.today() - timedelta(days=90)
            ).aggregate(t=Sum("delta_mrr"))["t"] or 0
        )
    except Exception:
        expansao["oportunidades_upsell"] = []
        expansao["expansao_mrr_90d"] = 0.0

    return JsonResponse(expansao)


def gtm_page(request):
    from django.shortcuts import render, redirect
    dono = dono_autenticado_from_request(request)
    if not dono:
        empresa = getattr(request, "empresa", None)
        if empresa:
            from .access_control import get_setor, _destino_correto
            return redirect(_destino_correto(get_setor(empresa)))
        return redirect("/operacao-central/")
    return render(request, "gtm.html")
