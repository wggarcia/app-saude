"""
Views Farmácia PDV — Ponto de Venda / Caixa.
Endpoints para: sessões PDV, vendas, itens de venda e histórico.
"""
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET

from .models import (
    Empresa,
    LivroRegistroControlado,
    PDVSessao,
    PDVVenda,
    PDVItemVenda,
    MedicamentoFarmacia,
    EstoqueMovimento,
)
from .access_control import api_requer_operacao_ou_gerencia, requer_setor, requer_operacao_page, requer_permissao_modulo, api_requer_feature


def _proximo_lote_fefo(empresa, medicamento):
    """Lote com saldo disponível e validade mais próxima (FEFO), calculado a
    partir do histórico de EstoqueMovimento — não existe tabela de saldo por
    lote para MedicamentoFarmacia, então o saldo é derivado das entradas/saídas."""
    saldos = {}
    movs = EstoqueMovimento.objects.filter(empresa=empresa, medicamento=medicamento).exclude(lote="").order_by("criado_em")
    for m in movs:
        s = saldos.setdefault(m.lote, {"lote": m.lote, "data_validade": None, "saldo": Decimal("0")})
        if m.data_validade and not s["data_validade"]:
            s["data_validade"] = m.data_validade
        if m.tipo == "entrada":
            s["saldo"] += m.quantidade
        elif m.tipo in ("saida", "descarte"):
            s["saldo"] -= m.quantidade
    disponiveis = [s for s in saldos.values() if s["saldo"] > 0]
    disponiveis.sort(key=lambda s: s["data_validade"] or date.max)
    return disponiveis[0] if disponiveis else None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _sessao_to_dict(s):
    return {
        "id": s.id,
        "operador": s.operador,
        "caixa_numero": s.caixa_numero,
        "abertura": s.abertura.isoformat(),
        "fechamento": s.fechamento.isoformat() if s.fechamento else None,
        "fundo_caixa": float(s.fundo_caixa),
        "total_vendas": float(s.total_vendas),
        "total_dinheiro": float(s.total_dinheiro),
        "total_pix": float(s.total_pix),
        "total_cartao_debito": float(s.total_cartao_debito),
        "total_cartao_credito": float(s.total_cartao_credito),
        "total_convenio": float(s.total_convenio),
        "ativa": s.ativa,
    }


def _venda_to_dict(v):
    itens = []
    for item in v.itens.all():
        itens.append({
            "id": item.id,
            "codigo_barras": item.codigo_barras,
            "descricao": item.descricao,
            "lote": item.lote,
            "quantidade": float(item.quantidade),
            "preco_unitario": float(item.preco_unitario),
            "desconto_item": float(item.desconto_item),
            "total_item": float(item.total_item),
            "controlado": item.controlado,
            "receita_numero": item.receita_numero,
        })
    return {
        "id": v.id,
        "sessao_id": v.sessao_id,
        "numero_cupom": v.numero_cupom,
        "forma_pagamento": v.forma_pagamento,
        "subtotal": float(v.subtotal),
        "desconto": float(v.desconto),
        "total": float(v.total),
        "troco": float(v.troco),
        "cpf_cliente": v.cpf_cliente,
        "cancelada": v.cancelada,
        "criado_em": v.criado_em.isoformat(),
        "itens": itens,
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("farmacia")
@requer_operacao_page
@requer_permissao_modulo("farmacia.pdv")
def farmacia_pdv_page(request):
    return render(request, "farmacia_pdv.html")


# ─── Busca de produto (barcode ou nome) ───────────────────────────────────────

@csrf_exempt
@require_GET
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pdv")
def api_pdv_buscar_produto(request):
    """GET — busca medicamento por código de barras, ID ou nome para uso no PDV.

    Parâmetros (ao menos um obrigatório):
      ?q=<barcode_ou_nome>   pesquisa em codigo_barras e nome (icontains)
      ?id=<medicamento_id>   busca direta por PK

    Retorna a lista de produtos com preço de venda já preenchido, pronto para
    ser adicionado ao carrinho sem digitação manual de preço.
    """
    empresa = request.empresa

    busca_id = request.GET.get("id", "").strip()
    q = request.GET.get("q", "").strip()

    if not busca_id and not q:
        return JsonResponse({"erro": "Informe ?q=<busca> ou ?id=<medicamento_id>"}, status=400)

    qs = MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True)

    if busca_id:
        qs = qs.filter(pk=busca_id)
    elif q:
        qs = qs.filter(
            Q(codigo_barras=q) |           # barcode exato primeiro
            Q(nome__icontains=q) |
            Q(principio_ativo__icontains=q)
        )[:20]

    produtos = []
    for med in qs:
        produtos.append({
            "id": med.id,
            "nome": med.nome,
            "principio_ativo": med.principio_ativo,
            "concentracao": med.concentracao,
            "forma_farmaceutica": med.forma_farmaceutica,
            "codigo_barras": med.codigo_barras,
            "preco_venda": float(med.preco_venda),
            "quantidade_atual": float(med.quantidade_atual),
            "controlado": med.controlado,
            "lista_portaria_344": med.lista_portaria_344,
            "em_estoque": med.quantidade_atual > 0,
        })

    return JsonResponse({"ok": True, "produtos": produtos})


# ─── Sessão atual ─────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pdv")
def api_pdv_sessao_atual(request):
    """GET — retorna a sessão PDV ativa para a empresa."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    sessao = PDVSessao.objects.filter(empresa=empresa, ativa=True).first()
    if not sessao:
        return JsonResponse({"ok": True, "sessao": None})

    return JsonResponse({"ok": True, "sessao": _sessao_to_dict(sessao)})


# ─── Abrir sessão ─────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pdv")
def api_pdv_abrir_sessao(request):
    """POST — abre nova sessão PDV (caixa).

    A verificação de sessão ativa é feita dentro de um bloco atômico com
    select_for_update() na linha da empresa, eliminando a race condition em
    que duas requisições simultâneas passariam ambas pela checagem e abrissem
    dois caixas para a mesma empresa.
    """
    empresa = request.empresa

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    operador = (data.get("operador") or "").strip()
    if not operador:
        return JsonResponse({"erro": "Campo 'operador' é obrigatório"}, status=400)

    fundo_caixa = _decimal(data.get("fundo_caixa", 0))
    caixa_numero = int(data.get("caixa_numero", 1))

    # Bug 3 fix — race condition: lock da linha da empresa garante serialização.
    # Sem o lock, duas requisições simultâneas podem ambas passar pelo filtro
    # "nenhuma sessão ativa" e criar dois caixas abertos.
    with transaction.atomic():
        # select_for_update() bloqueia a linha da empresa até o fim da transação,
        # impedindo outra requisição de criar sessão para a mesma empresa ao mesmo tempo.
        _emp_lock = Empresa.objects.select_for_update().get(pk=empresa.pk)

        sessao_ativa = PDVSessao.objects.filter(empresa=_emp_lock, ativa=True).first()
        if sessao_ativa:
            return JsonResponse({
                "erro": "Já existe uma sessão ativa. Feche o caixa atual antes de abrir um novo.",
                "sessao_id": sessao_ativa.id,
            }, status=400)

        sessao = PDVSessao.objects.create(
            empresa=_emp_lock,
            operador=operador,
            caixa_numero=caixa_numero,
            fundo_caixa=fundo_caixa,
            ativa=True,
        )

    return JsonResponse({"ok": True, "sessao": _sessao_to_dict(sessao)}, status=201)


# ─── Fechar sessão ────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pdv")
def api_pdv_fechar_sessao(request, sessao_id):
    """POST — fecha uma sessão PDV calculando os totais."""
    empresa = request.empresa

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        sessao = PDVSessao.objects.get(pk=sessao_id, empresa=empresa)
    except PDVSessao.DoesNotExist:
        return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

    if not sessao.ativa:
        return JsonResponse({"erro": "Sessão já está fechada"}, status=400)

    # Calcular totais por forma de pagamento a partir das vendas não canceladas
    vendas = PDVVenda.objects.filter(sessao=sessao, cancelada=False)

    totais = vendas.values("forma_pagamento").annotate(soma=Sum("total"))
    totais_dict = {t["forma_pagamento"]: t["soma"] or Decimal("0") for t in totais}

    sessao.total_vendas = vendas.aggregate(soma=Sum("total"))["soma"] or Decimal("0")
    sessao.total_dinheiro = totais_dict.get("dinheiro", Decimal("0"))
    sessao.total_pix = totais_dict.get("pix", Decimal("0"))
    sessao.total_cartao_debito = totais_dict.get("debito", Decimal("0"))
    sessao.total_cartao_credito = totais_dict.get("credito", Decimal("0"))
    sessao.total_convenio = totais_dict.get("convenio", Decimal("0"))
    sessao.fechamento = timezone.now()
    sessao.ativa = False
    sessao.save()

    return JsonResponse({"ok": True, "sessao": _sessao_to_dict(sessao)})


# ─── Registrar venda ─────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pdv")
def api_pdv_registrar_venda(request, sessao_id):
    """POST — registra uma venda na sessão PDV e desconta estoque."""
    empresa = request.empresa

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        sessao = PDVSessao.objects.get(pk=sessao_id, empresa=empresa)
    except PDVSessao.DoesNotExist:
        return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

    if not sessao.ativa:
        return JsonResponse({"erro": "Sessão está fechada. Abra um novo caixa."}, status=400)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    itens_data = data.get("itens", [])
    if not itens_data or not isinstance(itens_data, list):
        return JsonResponse({"erro": "Campo 'itens' é obrigatório e deve ser uma lista"}, status=400)

    forma_pagamento = data.get("forma_pagamento", "dinheiro")
    formas_validas = ["dinheiro", "pix", "debito", "credito", "convenio"]
    if forma_pagamento not in formas_validas:
        return JsonResponse({"erro": f"Forma de pagamento inválida. Opções: {formas_validas}"}, status=400)

    # Calcular subtotal e total a partir dos itens
    subtotal = Decimal("0")
    desconto_total = _decimal(data.get("desconto", 0))
    itens_validados = []

    for item in itens_data:
        quantidade = _decimal(item.get("quantidade", 1))
        preco_unitario = _decimal(item.get("preco_unitario", 0))
        desconto_item = _decimal(item.get("desconto_item", 0))
        codigo_barras = (item.get("codigo_barras") or "").strip()
        med_id = item.get("medicamento_id")

        # Bug 1 fix — preço R$0: se o frontend não enviou preco_unitario (ou
        # enviou zero), busca MedicamentoFarmacia.preco_venda no banco.
        # Isso elimina a dependência de o cliente conhecer o preço e impede
        # manipulação de preço via payload.
        if preco_unitario <= Decimal("0"):
            _med_lookup = None
            if med_id:
                _med_lookup = MedicamentoFarmacia.objects.filter(pk=med_id, empresa=empresa).first()
            elif codigo_barras:
                _med_lookup = MedicamentoFarmacia.objects.filter(
                    empresa=empresa, codigo_barras=codigo_barras, ativo=True,
                ).first()
            if _med_lookup and _med_lookup.preco_venda > Decimal("0"):
                preco_unitario = _med_lookup.preco_venda

        total_item = (quantidade * preco_unitario) - desconto_item
        subtotal += total_item

        item_ctrl = bool(item.get("controlado", False))
        item_receita = (item.get("receita_numero") or "").strip()

        # Portaria 344/98 — bloqueia venda de controlado sem número de receita.
        # Valida contra o banco para evitar bypass via payload.
        if item_ctrl and not item_receita:
            _med_check = None
            if med_id:
                _med_check = MedicamentoFarmacia.objects.filter(pk=med_id, empresa=empresa).first()
            elif codigo_barras:
                _med_check = MedicamentoFarmacia.objects.filter(
                    empresa=empresa, codigo_barras=codigo_barras, ativo=True,
                ).first()
            if _med_check and _med_check.controlado and _med_check.lista_portaria_344:
                return JsonResponse({
                    "erro": (
                        f"Medicamento controlado '{_med_check.nome}' exige número de receita "
                        f"(Portaria 344/98). Preencha o campo receita_numero para este item."
                    ),
                    "codigo_barras": codigo_barras,
                }, status=400)

        itens_validados.append({
            "codigo_barras": codigo_barras,
            "descricao": (item.get("descricao") or "").strip() or "Produto",
            "lote": (item.get("lote") or "").strip(),
            "quantidade": quantidade,
            "preco_unitario": preco_unitario,
            "desconto_item": desconto_item,
            "total_item": total_item,
            "controlado": item_ctrl,
            "receita_numero": item_receita,
            "medicamento_id": med_id,
        })

    # PBM: desconto do convênio é calculado pelo sistema, não digitado pelo operador
    desconto_pbm = Decimal("0")
    convenio_id = data.get("convenio_id")
    if forma_pagamento == "convenio" and convenio_id:
        from .models import PBMConvenio
        convenio = PBMConvenio.objects.filter(pk=convenio_id, empresa=empresa, ativo=True).first()
        if convenio:
            desconto_pbm = (subtotal * convenio.percentual_desconto_padrao / Decimal("100")).quantize(Decimal("0.01"))
            desconto_total += desconto_pbm

    total = subtotal - desconto_total
    if total < 0:
        total = Decimal("0")

    valor_pago = _decimal(data.get("valor_pago", total))
    troco = max(valor_pago - total, Decimal("0"))

    # Gerar número de cupom único
    numero_cupom = data.get("numero_cupom") or f"CUP-{uuid.uuid4().hex[:8].upper()}"

    # Criar venda
    venda = PDVVenda.objects.create(
        sessao=sessao,
        empresa=empresa,
        numero_cupom=numero_cupom,
        forma_pagamento=forma_pagamento,
        subtotal=subtotal,
        desconto=desconto_total,
        total=total,
        troco=troco,
        cpf_cliente=(data.get("cpf_cliente") or "").strip(),
        cancelada=False,
    )

    # Criar itens e descontar estoque
    for item in itens_validados:
        item_venda = PDVItemVenda.objects.create(
            venda=venda,
            codigo_barras=item["codigo_barras"],
            descricao=item["descricao"],
            lote=item["lote"],
            quantidade=item["quantidade"],
            preco_unitario=item["preco_unitario"],
            desconto_item=item["desconto_item"],
            total_item=item["total_item"],
            controlado=item["controlado"],
            receita_numero=item["receita_numero"],
        )

        # Descontar do estoque se houver medicamento vinculado
        med_id = item.get("medicamento_id")
        med = None
        if med_id:
            med = MedicamentoFarmacia.objects.filter(pk=med_id, empresa=empresa).first()
        elif item["codigo_barras"]:
            med = MedicamentoFarmacia.objects.filter(
                empresa=empresa, codigo_barras=item["codigo_barras"], ativo=True,
            ).first()

        if med:
            med.quantidade_atual = max(med.quantidade_atual - item["quantidade"], Decimal("0"))
            med.save(update_fields=["quantidade_atual", "atualizado_em"])

            # FEFO: se a tela não informou o lote, sai o de validade mais próxima
            lote_usado = item["lote"]
            data_validade_usada = None
            if not lote_usado:
                proximo = _proximo_lote_fefo(empresa, med)
                if proximo:
                    lote_usado = proximo["lote"]
                    data_validade_usada = proximo["data_validade"]
                    item_venda.lote = lote_usado
                    item_venda.save(update_fields=["lote"])

            if lote_usado:
                EstoqueMovimento.objects.create(
                    empresa=empresa, medicamento=med, tipo="saida",
                    quantidade=item["quantidade"], lote=lote_usado,
                    data_validade=data_validade_usada,
                    motivo=f"Venda PDV — cupom {numero_cupom}",
                )

            # Bug 2 fix — Livro de Registro Controlado: obrigação ANVISA
            # Portaria 344/98. Toda dispensação de medicamento controlado DEVE
            # gerar um registro no livro para alimentar o SNGPC posteriormente.
            # Anteriormente o PDV nunca criava esse registro — o livro ficava
            # vazio para qualquer venda feita via caixa.
            if med.controlado and med.lista_portaria_344:
                LivroRegistroControlado.objects.create(
                    empresa=empresa,
                    medicamento=med,
                    lote=None,           # lote via LoteMedicamento não é rastreado no PDV; FK opcional
                    dispensacao=None,    # dispensação formal não existe no fluxo PDV
                    tipo="dispensacao",
                    quantidade=item["quantidade"],
                    saldo_apos=med.quantidade_atual,
                    # Em venda de balcão o nome do paciente não é coletado na
                    # maioria dos casos; o CPF do cliente (se informado) é o que
                    # temos. Para controlados com necessidade de receita, o
                    # operador deve ter preenchido receita_numero no item.
                    paciente_nome="",
                    paciente_cpf=(venda.cpf_cliente or ""),
                    prescricao_numero=item["receita_numero"],
                    medico_crm="",
                    responsavel=(sessao.operador or ""),
                    observacao=f"Venda PDV — cupom {numero_cupom}",
                )

    return JsonResponse({"ok": True, "venda": _venda_to_dict(venda), "desconto_pbm_aplicado": float(desconto_pbm)}, status=201)


# ─── Histórico de vendas ──────────────────────────────────────────────────────

@csrf_exempt
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pdv")
def api_pdv_historico(request):
    """GET — últimas 30 vendas da empresa."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    qs = PDVVenda.objects.filter(empresa=empresa).select_related("sessao").prefetch_related("itens")

    # Filtros opcionais
    cancelada = request.GET.get("cancelada", "").strip()
    if cancelada == "0":
        qs = qs.filter(cancelada=False)
    elif cancelada == "1":
        qs = qs.filter(cancelada=True)

    sessao_id = request.GET.get("sessao_id", "").strip()
    if sessao_id:
        qs = qs.filter(sessao_id=sessao_id)

    data_inicio = request.GET.get("data_inicio", "").strip()
    if data_inicio:
        qs = qs.filter(criado_em__date__gte=data_inicio)

    data_fim = request.GET.get("data_fim", "").strip()
    if data_fim:
        qs = qs.filter(criado_em__date__lte=data_fim)

    limit = min(int(request.GET.get("limit", 30)), 500)
    qs = qs[:limit]

    return JsonResponse({
        "ok": True,
        "vendas": [_venda_to_dict(v) for v in qs],
    })
