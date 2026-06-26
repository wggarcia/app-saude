import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import (
    EmpresaUnidade, FornecedorFarmacia, ItemFarmacia, MovimentoEstoque,
    PedidoCompraFarmacia, ItemPedidoCompra, DispensacaoMedicamento,
)
from .views_dashboard import _empresa_autenticada
from .access_control import (
    api_requer_operacao_ou_gerencia,
    api_requer_setor,
    get_setor,
    principal_pode_operacao_setorial,
    api_requer_feature,
)


def _e(req):
    empresa = _empresa_autenticada(req)
    if empresa and get_setor(empresa) not in ('farmacia',):
        return None  # Block non-farmacia empresas
    if empresa and not principal_pode_operacao_setorial(req):
        return None
    return empresa


# ── Fornecedores ───────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pedidos")
def api_fornecedores_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = FornecedorFarmacia.objects.filter(empresa=e)
        return JsonResponse({"fornecedores": [
            {"id": f.id, "nome": f.nome, "cnpj": f.cnpj,
             "email": f.email, "telefone": f.telefone,
             "contato": f.contato, "ativo": f.ativo}
            for f in qs
        ]})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    f = FornecedorFarmacia.objects.create(
        empresa=e,
        nome=data.get("nome", ""),
        cnpj=data.get("cnpj", ""),
        contato=data.get("contato", ""),
        email=data.get("email", ""),
        telefone=data.get("telefone", ""),
    )
    return JsonResponse({"id": f.id, "nome": f.nome}, status=201)


@require_http_methods(["PUT", "DELETE"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pedidos")
def api_fornecedor_farmacia_detalhe(request, fornecedor_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        f = FornecedorFarmacia.objects.get(pk=fornecedor_id, empresa=e)
    except FornecedorFarmacia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        f.delete()
        return JsonResponse({"ok": True})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    for campo in ["nome", "cnpj", "contato", "email", "telefone", "ativo"]:
        if campo in data:
            setattr(f, campo, data[campo])
    f.save()
    return JsonResponse({"ok": True})


# ── Itens / Estoque ────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_itens_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = ItemFarmacia.objects.filter(empresa=e).select_related("fornecedor", "unidade_fisica")
        unidade_id = request.GET.get("unidade_id")
        if unidade_id:
            qs = qs.filter(unidade_fisica_id=unidade_id)
        return JsonResponse({"itens": [
            {"id": i.id, "nome": i.nome, "codigo": i.codigo,
             "categoria": i.categoria, "unidade_medida": i.unidade_medida,
             "estoque_atual": i.estoque_atual, "estoque_minimo": i.estoque_minimo,
             "ativo": i.ativo,
             "abaixo_minimo": i.estoque_atual < i.estoque_minimo,
             "fornecedor_id": i.fornecedor_id,
             "fornecedor_nome": i.fornecedor.nome if i.fornecedor else "",
             "unidade_fisica_id": i.unidade_fisica_id,
             "unidade_fisica_nome": i.unidade_fisica.nome if i.unidade_fisica else ""}
            for i in qs
        ]})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    forn = None
    if data.get("fornecedor_id"):
        try:
            forn = FornecedorFarmacia.objects.get(pk=data["fornecedor_id"], empresa=e)
        except FornecedorFarmacia.DoesNotExist:
            pass
    unidade_fisica = None
    if data.get("unidade_id"):
        try:
            unidade_fisica = EmpresaUnidade.objects.get(pk=data["unidade_id"], empresa=e)
        except EmpresaUnidade.DoesNotExist:
            pass
    item = ItemFarmacia.objects.create(
        empresa=e,
        nome=data.get("nome", ""),
        codigo=data.get("codigo", ""),
        categoria=data.get("categoria", "medicamento"),
        descricao=data.get("descricao", ""),
        unidade_medida=data.get("unidade_medida", "unidade"),
        estoque_minimo=int(data.get("estoque_minimo", 0)),
        fornecedor=forn,
        unidade_fisica=unidade_fisica,
    )
    return JsonResponse({"id": item.id, "nome": item.nome}, status=201)


@require_http_methods(["PUT", "DELETE"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_item_farmacia_detalhe(request, item_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        item = ItemFarmacia.objects.get(pk=item_id, empresa=e)
    except ItemFarmacia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    for campo in ["nome", "codigo", "categoria", "descricao", "unidade_medida", "estoque_minimo", "ativo"]:
        if campo in data:
            setattr(item, campo, data[campo])
    item.save()
    return JsonResponse({"ok": True})


# ── Movimentos de Estoque ──────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_movimentos_estoque(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        item_id = request.GET.get("item_id")
        qs = MovimentoEstoque.objects.filter(empresa=e).select_related("item")
        if item_id:
            qs = qs.filter(item_id=item_id)
        qs = qs[:100]
        return JsonResponse({"movimentos": [
            {"id": m.id, "tipo": m.tipo, "quantidade": m.quantidade,
             "estoque_anterior": m.estoque_anterior, "estoque_posterior": m.estoque_posterior,
             "motivo": m.motivo, "responsavel": m.responsavel,
             "item_id": m.item_id, "item_nome": m.item.nome,
             "data_movimento": m.data_movimento.isoformat()}
            for m in qs
        ]})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    try:
        item = ItemFarmacia.objects.get(pk=data["item_id"], empresa=e)
    except (KeyError, ItemFarmacia.DoesNotExist):
        return JsonResponse({"erro": "Item não encontrado"}, status=404)
    quantidade = int(data.get("quantidade", 0))
    tipo = data.get("tipo", "entrada")
    estoque_anterior = item.estoque_atual
    if tipo == "entrada":
        item.estoque_atual += quantidade
    elif tipo in ("saida", "vencimento"):
        item.estoque_atual -= quantidade
    else:  # ajuste
        item.estoque_atual = quantidade
    item.save()
    m = MovimentoEstoque.objects.create(
        empresa=e, item=item, tipo=tipo,
        quantidade=quantidade,
        estoque_anterior=estoque_anterior,
        estoque_posterior=item.estoque_atual,
        motivo=data.get("motivo", ""),
        responsavel=data.get("responsavel", ""),
    )
    return JsonResponse({"id": m.id, "estoque_atual": item.estoque_atual}, status=201)


# ── Dispensações ───────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.dispensacoes")
def api_dispensacoes_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = DispensacaoMedicamento.objects.filter(empresa=e).select_related("item")[:100]
        return JsonResponse({"dispensacoes": [
            {"id": d.id, "item_nome": d.item.nome, "paciente_nome": d.paciente_nome,
             "paciente_cpf": d.paciente_cpf, "quantidade": d.quantidade,
             "responsavel": d.responsavel, "observacoes": d.observacoes,
             "dispensado_em": d.dispensado_em.isoformat()}
            for d in qs
        ]})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    try:
        item = ItemFarmacia.objects.get(pk=data["item_id"], empresa=e)
    except (KeyError, ItemFarmacia.DoesNotExist):
        return JsonResponse({"erro": "Item não encontrado"}, status=404)
    quantidade = int(data.get("quantidade", 1))
    ant = item.estoque_atual
    item.estoque_atual -= quantidade
    item.save()
    MovimentoEstoque.objects.create(
        empresa=e, item=item, tipo="saida",
        quantidade=quantidade, estoque_anterior=ant,
        estoque_posterior=item.estoque_atual,
        motivo=f"Dispensação para {data.get('paciente_nome', '')}",
        responsavel=data.get("responsavel", ""),
    )
    d = DispensacaoMedicamento.objects.create(
        empresa=e, item=item,
        paciente_nome=data.get("paciente_nome", ""),
        paciente_cpf=data.get("paciente_cpf", ""),
        quantidade=quantidade,
        responsavel=data.get("responsavel", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"id": d.id}, status=201)


# ── Pedidos de Compra ──────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pedidos")
def api_pedidos_compra_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = PedidoCompraFarmacia.objects.filter(empresa=e).select_related("fornecedor").prefetch_related("itens__item")
        return JsonResponse({"pedidos": [
            {"id": p.id, "status": p.status,
             "fornecedor_nome": p.fornecedor.nome if p.fornecedor else "",
             "observacoes": p.observacoes,
             "criado_em": p.criado_em.isoformat(),
             "itens": [
                 {"item_nome": ip.item.nome,
                  "qtd_sol": ip.quantidade_solicitada,
                  "qtd_rec": ip.quantidade_recebida}
                 for ip in p.itens.all()
             ]}
            for p in qs
        ]})
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    forn = None
    if data.get("fornecedor_id"):
        try:
            forn = FornecedorFarmacia.objects.get(pk=data["fornecedor_id"], empresa=e)
        except FornecedorFarmacia.DoesNotExist:
            pass
    p = PedidoCompraFarmacia.objects.create(
        empresa=e, fornecedor=forn,
        observacoes=data.get("observacoes", ""),
    )
    for it in data.get("itens", []):
        try:
            item = ItemFarmacia.objects.get(pk=it["item_id"], empresa=e)
            ItemPedidoCompra.objects.create(
                pedido=p, item=item,
                quantidade_solicitada=int(it.get("quantidade", 1)),
            )
        except (KeyError, ItemFarmacia.DoesNotExist):
            pass
    return JsonResponse({"id": p.id}, status=201)


@require_http_methods(["PUT"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pedidos")
def api_pedido_compra_status(request, pedido_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        p = PedidoCompraFarmacia.objects.get(pk=pedido_id, empresa=e)
    except PedidoCompraFarmacia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    p.status = data.get("status", p.status)
    p.save()
    if p.status == "recebido":
        for ip in p.itens.select_related("item").all():
            item = ip.item
            ant = item.estoque_atual
            item.estoque_atual += ip.quantidade_solicitada
            item.save()
            ip.quantidade_recebida = ip.quantidade_solicitada
            ip.save()
            MovimentoEstoque.objects.create(
                empresa=e, item=item, tipo="entrada",
                quantidade=ip.quantidade_solicitada,
                estoque_anterior=ant,
                estoque_posterior=item.estoque_atual,
                motivo=f"Recebimento pedido #{p.id}",
            )
    return JsonResponse({"ok": True})


# ── KPIs ───────────────────────────────────────────────────────────────────────
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_farmacia_ops_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    itens = list(ItemFarmacia.objects.filter(empresa=e, ativo=True))
    abaixo_min = sum(1 for i in itens if i.estoque_atual < i.estoque_minimo)
    total_dispensacoes = DispensacaoMedicamento.objects.filter(empresa=e).count()
    pedidos_abertos = PedidoCompraFarmacia.objects.filter(
        empresa=e, status__in=["rascunho", "enviado", "aprovado"]
    ).count()
    return JsonResponse({
        "total_itens": len(itens),
        "itens_abaixo_minimo": abaixo_min,
        "total_dispensacoes": total_dispensacoes,
        "pedidos_abertos": pedidos_abertos,
    })


# ── PDFs ───────────────────────────────────────────────────────────────────────
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_farmacia_pdf_estoque(request):
    from django.http import HttpResponse
    from .pdf_ops import gerar_pdf_estoque_farmacia
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    itens = list(ItemFarmacia.objects.filter(empresa=e, ativo=True).select_related("fornecedor"))
    buf = gerar_pdf_estoque_farmacia(e, itens)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="estoque_farmacia.pdf"'
    return resp


@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.dispensacoes")
def api_farmacia_pdf_dispensacoes(request):
    from django.http import HttpResponse
    from .pdf_ops import gerar_pdf_dispensacoes_farmacia
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    disp = list(DispensacaoMedicamento.objects.filter(empresa=e).select_related("item")[:200])
    buf = gerar_pdf_dispensacoes_farmacia(e, disp)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="dispensacoes_farmacia.pdf"'
    return resp
