"""
Views para rastreabilidade de lotes de medicamentos (FEFO) e prescrições médicas.
"""
import json
from datetime import date, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import LoteMedicamento, ItemFarmacia, FornecedorFarmacia, MovimentoEstoque
from .views_dashboard import _empresa_autenticada
from .access_control import get_setor, api_requer_feature


def _e(req):
    empresa = _empresa_autenticada(req)
    if empresa and get_setor(empresa) not in ('farmacia',):
        return None
    return empresa


def _lote_to_dict(l):
    hoje = date.today()
    dias = (l.data_validade - hoje).days
    return {
        "id": l.id,
        "item_id": l.item_id,
        "item_nome": l.item.nome if l.item else (l.medicamento.nome if l.medicamento else ""),
        "medicamento_id": l.medicamento_id,
        "numero_lote": l.numero_lote,
        "fabricante": l.fabricante,
        "data_fabricacao": str(l.data_fabricacao) if l.data_fabricacao else None,
        "data_validade": str(l.data_validade),
        "dias_para_vencer": dias,
        "vencido": dias < 0,
        "alerta": 0 <= dias <= 30,
        "quantidade_inicial": float(l.quantidade_inicial),
        "quantidade_atual": float(l.quantidade_atual),
        "nota_fiscal": l.nota_fiscal,
        "fornecedor_id": l.fornecedor_id,
        "fornecedor_nome": l.fornecedor.nome if l.fornecedor else None,
        "criado_em": l.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
@api_requer_feature("farmacia.lotes")
def api_lotes_farmacia(request):
    """GET list / POST create lotes de medicamentos."""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = LoteMedicamento.objects.filter(empresa=empresa).select_related("item", "fornecedor")

        item_id = request.GET.get("item_id")
        if item_id:
            qs = qs.filter(item_id=item_id)

        # filtros de validade
        filtro = request.GET.get("filtro")
        hoje = date.today()
        if filtro == "vencidos":
            qs = qs.filter(data_validade__lt=hoje)
        elif filtro == "vencendo_30":
            qs = qs.filter(data_validade__gte=hoje, data_validade__lte=hoje + timedelta(days=30))
        elif filtro == "vigentes":
            qs = qs.filter(data_validade__gt=hoje + timedelta(days=30))

        # Apenas com estoque > 0 por padrão (a menos que ?todos=1)
        if not request.GET.get("todos"):
            qs = qs.filter(quantidade_atual__gt=0)

        return JsonResponse({"lotes": [_lote_to_dict(l) for l in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        item_id = data.get("item_id")
        if not item_id:
            return JsonResponse({"erro": "item_id obrigatório"}, status=400)
        try:
            item = ItemFarmacia.objects.get(id=item_id, empresa=empresa)
        except ItemFarmacia.DoesNotExist:
            return JsonResponse({"erro": "Item não encontrado"}, status=404)

        data_val = data.get("data_validade")
        if not data_val:
            return JsonResponse({"erro": "data_validade obrigatório"}, status=400)

        fornecedor = None
        if data.get("fornecedor_id"):
            try:
                fornecedor = FornecedorFarmacia.objects.get(id=data["fornecedor_id"], empresa=empresa)
            except FornecedorFarmacia.DoesNotExist:
                pass

        qtd = float(data.get("quantidade_inicial", 0))

        lote = LoteMedicamento.objects.create(
            empresa=empresa,
            item=item,
            numero_lote=data.get("numero_lote", ""),
            fabricante=data.get("fabricante", ""),
            data_fabricacao=data.get("data_fabricacao") or None,
            data_validade=data_val,
            quantidade_inicial=qtd,
            quantidade_atual=qtd,
            nota_fiscal=data.get("nota_fiscal", ""),
            fornecedor=fornecedor,
        )

        # Atualizar estoque do item
        anterior = float(item.estoque_atual)
        item.estoque_atual = float(item.estoque_atual) + qtd
        item.save()

        MovimentoEstoque.objects.create(
            empresa=empresa,
            item=item,
            tipo="entrada",
            quantidade=qtd,
            motivo=f"Entrada lote {lote.numero_lote}",
            estoque_anterior=anterior,
            estoque_posterior=float(item.estoque_atual),
        )

        return JsonResponse({"lote": _lote_to_dict(lote)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
@api_requer_feature("farmacia.lotes")
def api_lote_farmacia_detalhe(request, lote_id):
    """GET / PUT / DELETE lote."""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        lote = LoteMedicamento.objects.get(id=lote_id, empresa=empresa)
    except LoteMedicamento.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"lote": _lote_to_dict(lote)})

    elif request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        for field in ("numero_lote", "fabricante", "data_fabricacao", "data_validade",
                      "nota_fiscal"):
            if field in data:
                setattr(lote, field, data[field] or None if field == "data_fabricacao" else data[field])
        if "fornecedor_id" in data:
            try:
                lote.fornecedor = FornecedorFarmacia.objects.get(id=data["fornecedor_id"], empresa=empresa)
            except FornecedorFarmacia.DoesNotExist:
                lote.fornecedor = None
        lote.save()
        return JsonResponse({"lote": _lote_to_dict(lote)})

    elif request.method == "DELETE":
        # Estornar estoque se lote ainda tem quantidade. Lotes de MedicamentoFarmacia
        # não têm ItemFarmacia associado (item=None) — nesse caso não há estoque de
        # item a estornar aqui.
        if lote.quantidade_atual > 0 and lote.item_id:
            item = lote.item
            anterior = float(item.estoque_atual)
            item.estoque_atual = max(0, float(item.estoque_atual) - float(lote.quantidade_atual))
            item.save()
            MovimentoEstoque.objects.create(
                empresa=empresa, item=item, tipo="saida",
                quantidade=float(lote.quantidade_atual),
                motivo=f"Exclusão lote {lote.numero_lote}",
                estoque_anterior=anterior,
                estoque_posterior=float(item.estoque_atual),
            )
        lote.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@api_requer_feature("farmacia.lotes")
def api_lotes_farmacia_kpis(request):
    """KPIs de rastreabilidade: vencidos, vencendo, alertas."""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    qs = LoteMedicamento.objects.filter(empresa=empresa, quantidade_atual__gt=0)

    vencidos     = qs.filter(data_validade__lt=hoje).count()
    vencendo_7   = qs.filter(data_validade__gte=hoje, data_validade__lte=hoje + timedelta(days=7)).count()
    vencendo_30  = qs.filter(data_validade__gte=hoje, data_validade__lte=hoje + timedelta(days=30)).count()
    vigentes     = qs.filter(data_validade__gt=hoje + timedelta(days=30)).count()
    total_lotes  = qs.count()

    # Lotes vencendo nos próximos 30 dias (lista)
    proximos = qs.filter(
        data_validade__gte=hoje,
        data_validade__lte=hoje + timedelta(days=30)
    ).select_related("item").order_by("data_validade")[:15]

    return JsonResponse({
        "kpis": {
            "total_lotes": total_lotes,
            "vencidos": vencidos,
            "vencendo_7": vencendo_7,
            "vencendo_30": vencendo_30,
            "vigentes": vigentes,
        },
        "proximos_vencer": [_lote_to_dict(l) for l in proximos],
    })
