"""
views_governo_almoxarifado.py
Almoxarifado municipal (Governo) — estoque por lote/validade (FEFO), multi-unidade,
transferências entre almoxarifados com aceite/devolução, ajustes de saldo.
"""
import json
from decimal import Decimal

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
    api_requer_permissao_modulo,
)
from .models import ProdutoAlmoxarifado, LoteAlmoxarifado, MovimentacaoAlmoxarifado, EmpresaUnidade
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.administrativo")
def governo_almoxarifado_page(request):
    return render(request, "governo_almoxarifado.html", contexto_navegacao_setorial(request, "governo"))


# ── Unidades internas (almoxarifados/postos) ──────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_governo_unidades(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = EmpresaUnidade.objects.filter(empresa=e, ativo=True)
        return JsonResponse({"unidades": [{"id": u.id, "nome": u.nome, "codigo": u.codigo} for u in qs]})

    data = json.loads(request.body or "{}")
    nome = data.get("nome", "").strip()
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)
    if EmpresaUnidade.objects.filter(empresa=e, nome=nome).exists():
        return JsonResponse({"erro": "Já existe uma unidade com esse nome"}, status=409)
    unidade = EmpresaUnidade.objects.create(empresa=e, nome=nome, codigo=data.get("codigo", ""))
    return JsonResponse({"id": unidade.id, "nome": unidade.nome, "codigo": unidade.codigo}, status=201)


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = timezone.localtime(timezone.now()).date()
    lotes = LoteAlmoxarifado.objects.filter(empresa=e, quantidade_atual__gt=0)
    return JsonResponse({
        "produtos_ativos": ProdutoAlmoxarifado.objects.filter(empresa=e, ativo=True).count(),
        "lotes_em_estoque": lotes.count(),
        "lotes_vencidos": lotes.filter(data_validade__lt=hoje).count(),
        "transferencias_pendentes": MovimentacaoAlmoxarifado.objects.filter(
            empresa=e, tipo="transferencia_entrada", status="pendente"
        ).count(),
    })


# ── Produtos ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_produtos(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = ProdutoAlmoxarifado.objects.filter(empresa=e, ativo=True)
        grupo = request.GET.get("grupo")
        if grupo:
            qs = qs.filter(grupo=grupo)
        return JsonResponse({"produtos": [_produto_dict(p) for p in qs]})

    data = json.loads(request.body or "{}")
    nome = data.get("nome", "").strip()
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)
    produto = ProdutoAlmoxarifado.objects.create(
        empresa=e, nome=nome,
        principio_ativo=data.get("principio_ativo", ""),
        grupo=data.get("grupo", ""),
        subgrupo=data.get("subgrupo", ""),
        forma_apresentacao=data.get("forma_apresentacao", ""),
        unidade_medida=data.get("unidade_medida", "unidade"),
        codigo_barras=data.get("codigo_barras", ""),
    )
    return JsonResponse(_produto_dict(produto), status=201)


# ── Lotes (entrada de estoque) ─────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_lotes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = LoteAlmoxarifado.objects.filter(empresa=e).select_related("produto", "unidade")
        unidade_id = request.GET.get("unidade_id")
        if unidade_id:
            qs = qs.filter(unidade_id=unidade_id)
        produto_id = request.GET.get("produto_id")
        if produto_id:
            qs = qs.filter(produto_id=produto_id)
        apenas_disponivel = request.GET.get("disponivel")
        if apenas_disponivel:
            qs = qs.filter(quantidade_atual__gt=0, bloqueado=False)
        return JsonResponse({"lotes": [_lote_dict(l) for l in qs]})

    data = json.loads(request.body or "{}")
    try:
        unidade = EmpresaUnidade.objects.get(pk=data["unidade_id"], empresa=e)
        produto = ProdutoAlmoxarifado.objects.get(pk=data["produto_id"], empresa=e)
    except (KeyError, EmpresaUnidade.DoesNotExist, ProdutoAlmoxarifado.DoesNotExist):
        return JsonResponse({"erro": "unidade_id e produto_id válidos são obrigatórios"}, status=400)
    quantidade = Decimal(str(data.get("quantidade", 0)))
    if quantidade <= 0:
        return JsonResponse({"erro": "quantidade deve ser positiva"}, status=400)
    data_validade = parse_date(data.get("data_validade", ""))
    if not data_validade:
        return JsonResponse({"erro": "data_validade obrigatória (formato AAAA-MM-DD)"}, status=400)

    lote, criado = LoteAlmoxarifado.objects.get_or_create(
        empresa=e, unidade=unidade, produto=produto, numero_lote=data.get("numero_lote", "UNICO"),
        defaults={
            "data_validade": data_validade,
            "quantidade_inicial": quantidade,
            "quantidade_atual": quantidade,
            "fornecedor": data.get("fornecedor", ""),
        },
    )
    if not criado:
        lote.quantidade_inicial += quantidade
        lote.quantidade_atual += quantidade
        lote.save(update_fields=["quantidade_inicial", "quantidade_atual"])

    MovimentacaoAlmoxarifado.objects.create(
        empresa=e, lote=lote, tipo="entrada", quantidade=quantidade,
        motivo=data.get("motivo", "Entrada de estoque"),
    )
    return JsonResponse(_lote_dict(lote), status=201)


# ── Dispensação (FEFO) ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_dispensar(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    try:
        produto = ProdutoAlmoxarifado.objects.get(pk=data["produto_id"], empresa=e)
        unidade = EmpresaUnidade.objects.get(pk=data["unidade_id"], empresa=e)
    except (KeyError, ProdutoAlmoxarifado.DoesNotExist, EmpresaUnidade.DoesNotExist):
        return JsonResponse({"erro": "produto_id e unidade_id válidos são obrigatórios"}, status=400)
    quantidade_solicitada = Decimal(str(data.get("quantidade", 0)))
    if quantidade_solicitada <= 0:
        return JsonResponse({"erro": "quantidade deve ser positiva"}, status=400)

    # FEFO: lotes não bloqueados, ordenados por data de validade (Meta.ordering já garante isso)
    lotes = LoteAlmoxarifado.objects.filter(
        empresa=e, unidade=unidade, produto=produto, bloqueado=False, quantidade_atual__gt=0
    )
    restante = quantidade_solicitada
    consumido = []
    for lote in lotes:
        if restante <= 0:
            break
        retirar = min(lote.quantidade_atual, restante)
        lote.quantidade_atual -= retirar
        lote.save(update_fields=["quantidade_atual"])
        MovimentacaoAlmoxarifado.objects.create(
            empresa=e, lote=lote, tipo="saida", quantidade=retirar,
            motivo=data.get("motivo", "Dispensação"),
        )
        consumido.append({"lote": lote.numero_lote, "quantidade": str(retirar)})
        restante -= retirar

    atendido = quantidade_solicitada - restante
    return JsonResponse({
        "quantidade_solicitada": str(quantidade_solicitada),
        "quantidade_atendida": str(atendido),
        "fornecimento_parcial": restante > 0,
        "lotes_consumidos": consumido,
    }, status=200 if restante == 0 else 206)


# ── Ajuste de saldo ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_ajustar(request, lote_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        lote = LoteAlmoxarifado.objects.get(pk=lote_id, empresa=e)
    except LoteAlmoxarifado.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    nova_quantidade = data.get("quantidade_atual")
    motivo = data.get("motivo", "")
    if nova_quantidade is None or not motivo:
        return JsonResponse({"erro": "quantidade_atual e motivo são obrigatórios"}, status=400)
    nova_quantidade = Decimal(str(nova_quantidade))
    diferenca = nova_quantidade - lote.quantidade_atual
    lote.quantidade_atual = nova_quantidade
    lote.save(update_fields=["quantidade_atual"])
    MovimentacaoAlmoxarifado.objects.create(
        empresa=e, lote=lote, tipo="ajuste", quantidade=diferenca, motivo=motivo,
    )
    return JsonResponse(_lote_dict(lote))


# ── Transferência entre almoxarifados ─────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_transferir(request, lote_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    try:
        lote = LoteAlmoxarifado.objects.get(pk=lote_id, empresa=e)
        destino = EmpresaUnidade.objects.get(pk=data.get("unidade_destino_id"), empresa=e)
    except (LoteAlmoxarifado.DoesNotExist, EmpresaUnidade.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"erro": "lote ou unidade de destino inválidos"}, status=404)
    quantidade = Decimal(str(data.get("quantidade", 0)))
    if quantidade <= 0 or quantidade > lote.quantidade_atual:
        return JsonResponse({"erro": "quantidade inválida ou maior que o estoque disponível"}, status=400)

    lote.quantidade_atual -= quantidade
    lote.save(update_fields=["quantidade_atual"])
    mov = MovimentacaoAlmoxarifado.objects.create(
        empresa=e, lote=lote, tipo="transferencia_saida", quantidade=quantidade,
        unidade_destino=destino, status="pendente",
        motivo=data.get("motivo", "Transferência entre almoxarifados"),
    )
    return JsonResponse(_mov_dict(mov), status=201)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_transferencia_responder(request, mov_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        mov = MovimentacaoAlmoxarifado.objects.get(
            pk=mov_id, empresa=e, tipo="transferencia_saida", status="pendente"
        )
    except MovimentacaoAlmoxarifado.DoesNotExist:
        return JsonResponse({"erro": "Transferência pendente não encontrada"}, status=404)
    data = json.loads(request.body or "{}")
    aceitar = bool(data.get("aceitar"))

    if aceitar:
        lote_origem = mov.lote
        lote_destino, _ = LoteAlmoxarifado.objects.get_or_create(
            empresa=e, unidade=mov.unidade_destino, produto=lote_origem.produto,
            numero_lote=lote_origem.numero_lote,
            defaults={
                "data_validade": lote_origem.data_validade,
                "quantidade_inicial": mov.quantidade,
                "quantidade_atual": 0,
                "fornecedor": lote_origem.fornecedor,
            },
        )
        lote_destino.quantidade_atual += mov.quantidade
        lote_destino.save(update_fields=["quantidade_atual"])
        MovimentacaoAlmoxarifado.objects.create(
            empresa=e, lote=lote_destino, tipo="transferencia_entrada", quantidade=mov.quantidade,
            status="aceita", motivo=f"Recebido de {mov.lote.unidade.nome}",
        )
        mov.status = "aceita"
    else:
        # devolução — estorna o estoque na unidade de origem
        mov.lote.quantidade_atual += mov.quantidade
        mov.lote.save(update_fields=["quantidade_atual"])
        mov.status = "rejeitada"

    mov.save(update_fields=["status"])
    return JsonResponse(_mov_dict(mov))


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def api_almoxarifado_transferencias_pendentes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = MovimentacaoAlmoxarifado.objects.filter(
        empresa=e, tipo="transferencia_saida", status="pendente"
    ).select_related("lote__produto", "lote__unidade", "unidade_destino")
    return JsonResponse({"transferencias": [_mov_dict(m) for m in qs]})


def _produto_dict(p):
    return {
        "id": p.id, "nome": p.nome, "principio_ativo": p.principio_ativo,
        "grupo": p.grupo, "subgrupo": p.subgrupo, "forma_apresentacao": p.forma_apresentacao,
        "unidade_medida": p.unidade_medida, "codigo_barras": p.codigo_barras,
    }


def _lote_dict(l):
    return {
        "id": l.id,
        "produto_id": l.produto_id,
        "produto_nome": l.produto.nome,
        "unidade_id": l.unidade_id,
        "unidade_nome": l.unidade.nome,
        "numero_lote": l.numero_lote,
        "data_validade": l.data_validade.isoformat(),
        "vencido": l.vencido,
        "quantidade_atual": str(l.quantidade_atual),
        "bloqueado": l.bloqueado,
    }


def _mov_dict(m):
    return {
        "id": m.id,
        "tipo": m.tipo,
        "tipo_display": m.get_tipo_display(),
        "quantidade": str(m.quantidade),
        "produto_nome": m.lote.produto.nome,
        "unidade_origem": m.lote.unidade.nome,
        "unidade_destino": m.unidade_destino.nome if m.unidade_destino else None,
        "status": m.status,
        "status_display": m.get_status_display(),
        "motivo": m.motivo,
        "criado_em": m.criado_em.isoformat(),
    }
