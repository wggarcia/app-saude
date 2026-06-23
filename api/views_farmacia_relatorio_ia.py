"""
Relatório executivo gerado por IA — Farmácia.

Reúne dados reais (vendas dos últimos 30 dias, estoque crítico, mix de
pagamento) e pede ao Claude uma síntese executiva em português: tendências,
alertas de ruptura e recomendações. Mesma integração Anthropic já usada
no Assistente SST (views_sst_rag.py), aplicada à farmácia.

Requer ANTHROPIC_API_KEY configurada no ambiente.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum, Count, Avg, F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ItemFarmacia, PDVVenda, PDVItemVenda
from .access_control import api_requer_gerencia, api_requer_feature


def _coletar_dados_farmacia(empresa):
    hoje = date.today()
    desde = hoje - timedelta(days=30)

    vendas_qs = PDVVenda.objects.filter(empresa=empresa, criado_em__date__gte=desde, cancelada=False)
    total_vendas = vendas_qs.count()
    faturamento = vendas_qs.aggregate(s=Sum("total"))["s"] or Decimal("0")
    ticket_medio = vendas_qs.aggregate(m=Avg("total"))["m"] or Decimal("0")

    mix_pagamento = list(
        vendas_qs.values("forma_pagamento").annotate(total=Count("id")).order_by("-total")
    )

    itens_baixo_estoque = list(
        ItemFarmacia.objects.filter(empresa=empresa, ativo=True, estoque_atual__lte=F("estoque_minimo"))
        .values("nome", "estoque_atual", "estoque_minimo")[:20]
    )

    top_vendidos = list(
        PDVItemVenda.objects.filter(venda__empresa=empresa, venda__criado_em__date__gte=desde, venda__cancelada=False)
        .values("descricao")
        .annotate(qtd_total=Sum("quantidade"))
        .order_by("-qtd_total")[:10]
    )

    return {
        "periodo": f"{desde.isoformat()} a {hoje.isoformat()}",
        "total_vendas": total_vendas,
        "faturamento_total": float(faturamento),
        "ticket_medio": float(ticket_medio),
        "mix_pagamento": mix_pagamento,
        "itens_baixo_estoque": itens_baixo_estoque,
        "top_vendidos": [{"nome": t["descricao"], "quantidade": float(t["qtd_total"])} for t in top_vendidos],
    }


@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.relatorio_ia")
def api_farmacia_relatorio_ia(request):
    """GET — gera um relatório executivo com IA a partir dos dados reais da farmácia."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return JsonResponse(
            {"erro": "Relatório com IA não configurado. Contate o suporte SolusCRT."},
            status=503,
        )

    dados = _coletar_dados_farmacia(empresa)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "Você é o assistente de gestão da plataforma SolusCRT Farmácia. "
            "Receberá dados reais de vendas e estoque dos últimos 30 dias de uma farmácia. "
            "Escreva um relatório executivo curto em português, com 3 seções: "
            "1) Tendências de venda, 2) Alertas de ruptura de estoque, 3) Recomendações práticas. "
            "Use apenas os dados fornecidos — nunca invente números. "
            "Se não houver dados suficientes em alguma seção, diga isso claramente."
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{
                "role": "user",
                "content": f"Dados da farmácia (JSON):\n{json.dumps(dados, ensure_ascii=False)}",
            }],
        )

        texto = next((b.text for b in response.content if hasattr(b, "text")), "")
        if not texto:
            return JsonResponse({"erro": "Não foi possível gerar o relatório."}, status=502)

        return JsonResponse({"ok": True, "relatorio": texto, "dados_base": dados})

    except Exception as exc:
        return JsonResponse({"erro": f"Erro ao gerar relatório com IA: {exc}"}, status=502)
