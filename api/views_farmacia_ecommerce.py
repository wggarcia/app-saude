"""
Views Farmácia E-commerce / Delivery.
Endpoints para: listagem de pedidos, novo pedido, atualizar status, KPIs.
"""
import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum, Count, Q, Avg
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .models import PedidoDelivery, ItemPedidoDelivery, MedicamentoFarmacia
from .views_farmacia_pdv import dar_baixa_estoque_medicamento
from .access_control import api_requer_gerencia, requer_setor, requer_operacao_page, requer_permissao_modulo, api_requer_feature


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _item_to_dict(i):
    return {
        "id": i.id,
        "medicamento_id": i.medicamento_id,
        "descricao": i.descricao,
        "codigo_barras": i.codigo_barras,
        "quantidade": float(i.quantidade),
        "preco_unitario": float(i.preco_unitario),
        "total_item": float(i.total_item),
    }


def _pedido_to_dict(p):
    return {
        "id": p.id,
        "numero_pedido": p.numero_pedido,
        "cliente_nome": p.cliente_nome,
        "cliente_telefone": p.cliente_telefone,
        "cliente_endereco": p.cliente_endereco,
        "status": p.status,
        "origem": p.origem,
        "total": float(p.total),
        "observacoes": p.observacoes,
        "estoque_baixado": p.estoque_baixado,
        "itens": [_item_to_dict(i) for i in p.itens.all()],
        "criado_em": p.criado_em.isoformat(),
        "atualizado_em": p.atualizado_em.isoformat(),
    }


STATUS_VALIDOS = ["aguardando", "confirmado", "em_preparo", "saiu", "entregue", "cancelado"]

# Estados em que o pedido está confirmado/em atendimento e o estoque deve ser
# baixado. A baixa acontece na primeira transição para qualquer um deles.
STATUS_CONFIRMA_BAIXA = {"confirmado", "em_preparo", "saiu", "entregue"}


def baixar_estoque_pedido(pedido):
    """Dispara a mesma baixa de estoque do PDV para os itens de um PedidoDelivery.

    Idempotente: trava o pedido, confere `estoque_baixado` e só baixa uma vez.
    Reutilizada tanto pelo e-commerce/WhatsApp quanto pelo webhook do iFood."""
    with transaction.atomic():
        p = (PedidoDelivery.objects.select_for_update()
             .filter(pk=pedido.pk, empresa=pedido.empresa_id).first())
        if p is None or p.estoque_baixado:
            return
        for item in p.itens.filter(medicamento__isnull=False):
            dar_baixa_estoque_medicamento(
                p.empresa,
                medicamento_id=item.medicamento_id,
                codigo_barras=item.codigo_barras,
                quantidade=item.quantidade,
                motivo=f"Venda delivery — pedido {p.numero_pedido} ({p.origem})",
            )
        p.estoque_baixado = True
        p.save(update_fields=["estoque_baixado", "atualizado_em"])


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("farmacia")
@requer_operacao_page
@requer_permissao_modulo("farmacia.gestao")
def farmacia_ecommerce_page(request):
    return render(request, "farmacia_ecommerce.html")


# ─── Listar pedidos ───────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.delivery")
def api_delivery_pedidos(request):
    """GET — lista pedidos de delivery com filtros."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    qs = PedidoDelivery.objects.filter(empresa=empresa)

    # Filtros
    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)

    origem = request.GET.get("origem", "").strip()
    if origem:
        qs = qs.filter(origem=origem)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(cliente_nome__icontains=q) |
            Q(numero_pedido__icontains=q) |
            Q(cliente_telefone__icontains=q)
        )

    data_inicio = request.GET.get("data_inicio", "").strip()
    if data_inicio:
        qs = qs.filter(criado_em__date__gte=data_inicio)

    data_fim = request.GET.get("data_fim", "").strip()
    if data_fim:
        qs = qs.filter(criado_em__date__lte=data_fim)

    limit = min(int(request.GET.get("limit", 100)), 500)
    offset = max(int(request.GET.get("offset", 0)), 0)
    total = qs.count()
    page_qs = qs[offset: offset + limit]

    return JsonResponse({
        "ok": True,
        "pedidos": [_pedido_to_dict(p) for p in page_qs],
        "paginacao": {"total": total, "limit": limit, "offset": offset},
    })


# ─── Novo pedido ─────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.delivery")
def api_delivery_novo(request):
    """POST — cria um novo pedido de delivery."""
    empresa = request.empresa

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cliente_nome = (data.get("cliente_nome") or "").strip()
    if not cliente_nome:
        return JsonResponse({"erro": "Campo 'cliente_nome' é obrigatório"}, status=400)

    cliente_telefone = (data.get("cliente_telefone") or "").strip()
    if not cliente_telefone:
        return JsonResponse({"erro": "Campo 'cliente_telefone' é obrigatório"}, status=400)

    cliente_endereco = (data.get("cliente_endereco") or "").strip()

    # Gerar número de pedido automático se não fornecido
    numero_pedido = (data.get("numero_pedido") or "").strip()
    if not numero_pedido:
        hoje = date.today()
        numero_pedido = f"DEL-{hoje.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    status = data.get("status", "aguardando")
    if status not in STATUS_VALIDOS:
        status = "aguardando"

    # Resolve os itens contra o catálogo MedicamentoFarmacia da própria empresa.
    itens_payload = data.get("itens", [])
    if not isinstance(itens_payload, list):
        itens_payload = []

    itens_resolvidos = []
    total_itens = Decimal("0")
    for it in itens_payload:
        med_id = it.get("medicamento_id")
        med = None
        if med_id:
            med = MedicamentoFarmacia.objects.filter(pk=med_id, empresa=empresa, ativo=True).first()
            if med is None:
                return JsonResponse({"erro": f"Medicamento {med_id} não encontrado nesta empresa"}, status=400)
        quantidade = _decimal(it.get("quantidade", 1))
        if quantidade <= 0:
            return JsonResponse({"erro": "Quantidade do item deve ser maior que zero"}, status=400)
        preco_unitario = _decimal(it.get("preco_unitario", 0))
        if preco_unitario <= 0 and med is not None:
            preco_unitario = med.preco_venda
        total_item = quantidade * preco_unitario
        total_itens += total_item
        itens_resolvidos.append({
            "medicamento": med,
            "descricao": (it.get("descricao") or (med.nome if med else "")).strip(),
            "codigo_barras": (it.get("codigo_barras") or (med.codigo_barras if med else "")).strip(),
            "quantidade": quantidade,
            "preco_unitario": preco_unitario,
            "total_item": total_item,
        })

    # Total explícito prevalece; senão, soma dos itens.
    total_informado = _decimal(data.get("total", 0))
    total = total_informado if total_informado > 0 else total_itens

    with transaction.atomic():
        pedido = PedidoDelivery.objects.create(
            empresa=empresa,
            numero_pedido=numero_pedido,
            cliente_nome=cliente_nome,
            cliente_telefone=cliente_telefone,
            cliente_endereco=cliente_endereco,
            status=status,
            origem=data.get("origem", "whatsapp"),
            total=total,
            observacoes=data.get("observacoes", ""),
        )
        for r in itens_resolvidos:
            ItemPedidoDelivery.objects.create(
                pedido=pedido,
                empresa=empresa,
                medicamento=r["medicamento"],
                descricao=r["descricao"],
                codigo_barras=r["codigo_barras"],
                quantidade=r["quantidade"],
                preco_unitario=r["preco_unitario"],
                total_item=r["total_item"],
            )

    # Se o pedido já nasce confirmado (ex.: criado manualmente pós-confirmação),
    # baixa o estoque imediatamente.
    if status in STATUS_CONFIRMA_BAIXA and itens_resolvidos:
        baixar_estoque_pedido(pedido)
        pedido.refresh_from_db()

    return JsonResponse({"ok": True, "pedido": _pedido_to_dict(pedido)}, status=201)


# ─── Atualizar status ─────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.delivery")
def api_delivery_atualizar_status(request, pedido_id):
    """POST — atualiza o status de um pedido de delivery."""
    empresa = request.empresa

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        pedido = PedidoDelivery.objects.get(pk=pedido_id, empresa=empresa)
    except PedidoDelivery.DoesNotExist:
        return JsonResponse({"erro": "Pedido não encontrado"}, status=404)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    novo_status = (data.get("status") or "").strip()
    if not novo_status:
        return JsonResponse({"erro": "Campo 'status' é obrigatório"}, status=400)

    if novo_status not in STATUS_VALIDOS:
        return JsonResponse({
            "erro": f"Status inválido. Opções: {STATUS_VALIDOS}"
        }, status=400)

    # Validar transições de status (opcional mas útil)
    if pedido.status == "entregue" and novo_status not in ("cancelado",):
        return JsonResponse({"erro": "Pedido já foi entregue"}, status=400)

    if pedido.status == "cancelado":
        return JsonResponse({"erro": "Pedido já está cancelado"}, status=400)

    pedido.status = novo_status
    if "observacoes" in data:
        pedido.observacoes = data["observacoes"]
    pedido.save()

    # Baixa de estoque na confirmação (uma única vez).
    if novo_status in STATUS_CONFIRMA_BAIXA and not pedido.estoque_baixado:
        baixar_estoque_pedido(pedido)
        pedido.refresh_from_db()

    return JsonResponse({"ok": True, "pedido": _pedido_to_dict(pedido)})


# ─── KPIs delivery ────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.delivery")
def api_delivery_kpis(request):
    """GET — KPIs do dia: pedidos hoje, em preparo, entregues, ticket médio."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    hoje = date.today()
    qs_hoje = PedidoDelivery.objects.filter(empresa=empresa, criado_em__date=hoje)

    pedidos_hoje = qs_hoje.count()
    em_preparo = PedidoDelivery.objects.filter(empresa=empresa, status="em_preparo").count()
    aguardando = PedidoDelivery.objects.filter(empresa=empresa, status="aguardando").count()
    saiu_entrega = PedidoDelivery.objects.filter(empresa=empresa, status="saiu").count()
    entregues_hoje = qs_hoje.filter(status="entregue").count()

    # Ticket médio dos pedidos entregues hoje (excluindo cancelados e zerados)
    entregues_qs = qs_hoje.filter(status="entregue", total__gt=0)
    ticket_medio = float(
        entregues_qs.aggregate(media=Avg("total"))["media"] or Decimal("0")
    )

    # Faturamento do dia
    faturamento_dia = float(
        qs_hoje.exclude(status="cancelado").aggregate(soma=Sum("total"))["soma"] or Decimal("0")
    )

    return JsonResponse({
        "ok": True,
        "kpis": {
            "pedidos_hoje": pedidos_hoje,
            "aguardando": aguardando,
            "em_preparo": em_preparo,
            "saiu_para_entrega": saiu_entrega,
            "entregues_hoje": entregues_hoje,
            "ticket_medio": round(ticket_medio, 2),
            "faturamento_dia": round(faturamento_dia, 2),
        },
    })
