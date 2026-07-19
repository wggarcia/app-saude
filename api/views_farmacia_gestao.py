"""
Views Farmácia Gestão — Módulo completo de gestão de farmácia.
Endpoints para: Estoque, Dispensações, Movimentos, Fornecedores, Pedidos e Dashboard.
"""
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Sum, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Dispensacao,
    EstoqueMovimento,
    FornecedorFarmaciaGestao,
    LivroRegistroControlado,
    LoteMedicamento,
    MedicamentoFarmacia,
    PedidoFarmacia,
    FarmaciaAuditLog,
)
from .access_control import api_requer_operacao_ou_gerencia, api_requer_setor, api_requer_feature


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_empresa(request):
    """Retorna a empresa autenticada via middleware JWT ou None."""
    return getattr(request, "empresa", None)


def _paginar(request, qs, limit_default=50, limit_max=500):
    """Aplica paginação via ?limit= e ?offset= na queryset."""
    try:
        limit = min(int(request.GET.get("limit", limit_default)), limit_max)
    except (ValueError, TypeError):
        limit = limit_default
    try:
        offset = max(int(request.GET.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0
    total = qs.count()
    return qs[offset: offset + limit], {"total": total, "limit": limit, "offset": offset}


def _decimal(value, default=None):
    """Converte valor para Decimal de forma segura.

    Retorna `default` (None por padrão) quando `value` é None/ausente ou
    inválido — isso permite que o chamador distinga "campo não informado"
    de "campo enviado com valor zero explícito" (ex.: em ajustes de
    estoque, onde `None` significa "não altere" e `Decimal('0')` significa
    "zere o estoque"). Chamadas que precisam de um fallback numérico
    garantido (ex.: criação de registros com campo NOT NULL) devem passar
    `default=Decimal("0")` explicitamente.
    """
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _med_to_dict(med):
    """Serializa um MedicamentoFarmacia para dicionário."""
    return {
        "id": med.id,
        "nome": med.nome,
        "principio_ativo": med.principio_ativo,
        "forma_farmaceutica": med.forma_farmaceutica,
        "concentracao": med.concentracao,
        "registro_anvisa": med.registro_anvisa,
        "codigo_barras": med.codigo_barras,
        "fabricante": med.fabricante,
        "classe_terapeutica": med.classe_terapeutica,
        "quantidade_atual": float(med.quantidade_atual),
        "quantidade_minima": float(med.quantidade_minima),
        "quantidade_maxima": float(med.quantidade_maxima),
        "preco_custo": float(med.preco_custo),
        "preco_venda": float(med.preco_venda),
        "controlado": med.controlado,
        "refrigerado": med.refrigerado,
        "validade_media_dias": med.validade_media_dias,
        "ativo": med.ativo,
        "status": med.status_estoque,
        "criado_em": med.criado_em.isoformat(),
    }


def _mov_to_dict(mov):
    """Serializa um EstoqueMovimento para dicionário."""
    return {
        "id": mov.id,
        "medicamento_id": mov.medicamento_id,
        "medicamento_nome": mov.medicamento.nome,
        "tipo": mov.tipo,
        "quantidade": float(mov.quantidade),
        "motivo": mov.motivo,
        "lote": mov.lote,
        "data_validade": mov.data_validade.isoformat() if mov.data_validade else None,
        "responsavel": mov.responsavel,
        "observacao": mov.observacao,
        "criado_em": mov.criado_em.isoformat(),
    }


def _disp_to_dict(disp):
    """Serializa uma Dispensacao para dicionário."""
    return {
        "id": disp.id,
        "data": disp.data.isoformat() if disp.data else None,
        "paciente_nome": disp.paciente_nome,
        "paciente_cpf": disp.paciente_cpf,
        "prescricao_numero": disp.prescricao_numero,
        "medico_crm": disp.medico_crm,
        "medicamentos": disp.medicamentos,
        "valor_total": float(disp.valor_total),
        "convenio": disp.convenio,
        "status": disp.status,
        "observacoes": disp.observacoes,
        "criado_em": disp.criado_em.isoformat(),
    }


def _forn_to_dict(forn):
    """Serializa um FornecedorFarmaciaGestao para dicionário."""
    return {
        "id": forn.id,
        "nome": forn.nome,
        "cnpj": forn.cnpj,
        "contato": forn.contato,
        "email": forn.email,
        "telefone": forn.telefone,
        "prazo_entrega_dias": forn.prazo_entrega_dias,
        "ativo": forn.ativo,
        "criado_em": forn.criado_em.isoformat(),
    }


def _pedido_to_dict(pedido):
    """Serializa um PedidoFarmacia para dicionário."""
    return {
        "id": pedido.id,
        "fornecedor_id": pedido.fornecedor_id,
        "fornecedor_nome": pedido.fornecedor.nome if pedido.fornecedor else "",
        "data_pedido": pedido.data_pedido.isoformat() if pedido.data_pedido else None,
        "data_entrega_prevista": pedido.data_entrega_prevista.isoformat() if pedido.data_entrega_prevista else None,
        "status": pedido.status,
        "itens": pedido.itens,
        "valor_total": float(pedido.valor_total),
        "observacao": pedido.observacao,
        "criado_em": pedido.criado_em.isoformat(),
    }


# ─── Dashboard ────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_farmacia_dashboard(request):
    """KPIs e alertas do módulo de farmácia."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    hoje = date.today()
    limite_vencimento = hoje + timedelta(days=30)

    medicamentos_qs = MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True)
    total_medicamentos = medicamentos_qs.count()

    itens_baixo = 0
    itens_critico = 0
    alertas_vencimento = 0
    valor_estoque_total = Decimal("0")

    for med in medicamentos_qs:
        status = med.status_estoque
        if status == "baixo":
            itens_baixo += 1
        elif status == "critico":
            itens_critico += 1
        valor_estoque_total += med.quantidade_atual * med.preco_custo

    # Alertas de vencimento: movimentos com data_validade < 30 dias e quantidade > 0
    alertas_vencimento = EstoqueMovimento.objects.filter(
        empresa=empresa,
        tipo="entrada",
        data_validade__isnull=False,
        data_validade__lte=limite_vencimento,
        data_validade__gte=hoje,
    ).values("medicamento").distinct().count()

    # Dispensações hoje
    dispensacoes_hoje = Dispensacao.objects.filter(
        empresa=empresa,
        criado_em__date=hoje,
    ).count()

    return JsonResponse({
        "ok": True,
        "dashboard": {
            "total_medicamentos": total_medicamentos,
            "itens_baixo_estoque": itens_baixo,
            "itens_critico": itens_critico,
            "dispensacoes_hoje": dispensacoes_hoje,
            "valor_estoque_total": float(valor_estoque_total),
            "alertas_vencimento": alertas_vencimento,
        },
    })


# ─── Estoque ──────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_farmacia_estoque(request):
    """Lista e cadastra medicamentos no estoque."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = MedicamentoFarmacia.objects.filter(empresa=empresa)

        # Filtros opcionais
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(nome__icontains=q) |
                Q(principio_ativo__icontains=q) |
                Q(codigo_barras__icontains=q) |
                Q(registro_anvisa__icontains=q)
            )

        status_filtro = request.GET.get("status", "").strip()
        if status_filtro == "baixo":
            qs = qs.filter(
                quantidade_atual__gt=0,
                quantidade_minima__gt=0,
            )
        elif status_filtro == "critico":
            qs = qs.filter(quantidade_atual__lte=0)

        ativo = request.GET.get("ativo", "").strip()
        if ativo == "1":
            qs = qs.filter(ativo=True)
        elif ativo == "0":
            qs = qs.filter(ativo=False)

        page_qs, meta = _paginar(request, qs)
        medicamentos = [_med_to_dict(m) for m in page_qs]

        # Filtro pós-queryset para status (evita lógica complexa no ORM)
        if status_filtro in ("baixo", "critico"):
            medicamentos = [m for m in medicamentos if m["status"] == status_filtro]

        return JsonResponse({
            "ok": True,
            "medicamentos": medicamentos,
            "paginacao": meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = (data.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Campo 'nome' é obrigatório"}, status=400)

        med = MedicamentoFarmacia.objects.create(
            empresa=empresa,
            nome=nome,
            principio_ativo=data.get("principio_ativo", ""),
            forma_farmaceutica=data.get("forma_farmaceutica", "comprimido"),
            concentracao=data.get("concentracao", ""),
            registro_anvisa=data.get("registro_anvisa", ""),
            codigo_barras=data.get("codigo_barras", ""),
            fabricante=data.get("fabricante", ""),
            classe_terapeutica=data.get("classe_terapeutica", "outro"),
            quantidade_atual=_decimal(data.get("quantidade_atual", 0), default=Decimal("0")),
            quantidade_minima=_decimal(data.get("quantidade_minima", 0), default=Decimal("0")),
            quantidade_maxima=_decimal(data.get("quantidade_maxima", 0), default=Decimal("0")),
            preco_custo=_decimal(data.get("preco_custo", 0), default=Decimal("0")),
            preco_venda=_decimal(data.get("preco_venda", 0), default=Decimal("0")),
            controlado=bool(data.get("controlado", False)),
            refrigerado=bool(data.get("refrigerado", False)),
            validade_media_dias=int(data.get("validade_media_dias", 365)),
            ativo=bool(data.get("ativo", True)),
        )

        return JsonResponse({"ok": True, "medicamento": _med_to_dict(med)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── Dispensações ─────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.dispensacoes")
def api_farmacia_dispensacao(request):
    """Lista e registra dispensações de medicamentos."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = Dispensacao.objects.filter(empresa=empresa)

        # Filtros
        status = request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        paciente = request.GET.get("paciente", "").strip()
        if paciente:
            qs = qs.filter(
                Q(paciente_nome__icontains=paciente) |
                Q(paciente_cpf__icontains=paciente)
            )

        data_inicio = request.GET.get("data_inicio", "").strip()
        if data_inicio:
            qs = qs.filter(criado_em__date__gte=data_inicio)

        data_fim = request.GET.get("data_fim", "").strip()
        if data_fim:
            qs = qs.filter(criado_em__date__lte=data_fim)

        page_qs, meta = _paginar(request, qs)
        return JsonResponse({
            "ok": True,
            "dispensacoes": [_disp_to_dict(d) for d in page_qs],
            "paginacao": meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        paciente_nome = (data.get("paciente_nome") or "").strip()
        if not paciente_nome:
            return JsonResponse({"erro": "Campo 'paciente_nome' é obrigatório"}, status=400)

        medicamentos = data.get("medicamentos", [])
        if not isinstance(medicamentos, list):
            medicamentos = []

        medico_crm = (data.get("medico_crm") or "").strip()
        prescricao_numero = (data.get("prescricao_numero") or "").strip()

        # Validações de segurança por medicamento dispensado
        for item in medicamentos:
            med_id = item.get("medicamento_id")
            if not med_id:
                continue
            try:
                med = MedicamentoFarmacia.objects.get(pk=med_id, empresa=empresa)
            except MedicamentoFarmacia.DoesNotExist:
                continue

            # Bloquear dispensação de controlado sem prescrição
            if med.controlado and not medico_crm:
                return JsonResponse({
                    "erro": f"Medicamento controlado '{med.nome}' exige CRM do médico prescritor."
                }, status=400)

            # Verificar lote informado
            lote_numero = (item.get("lote") or "").strip()
            if lote_numero:
                try:
                    lote = LoteMedicamento.objects.get(numero_lote=lote_numero, empresa=empresa)
                    if lote.bloqueado:
                        return JsonResponse({
                            "erro": f"Lote {lote_numero} de '{med.nome}' está BLOQUEADO (recall). Motivo: {lote.motivo_bloqueio}"
                        }, status=400)
                    if lote.vencido:
                        return JsonResponse({
                            "erro": f"Lote {lote_numero} de '{med.nome}' está VENCIDO desde {lote.data_validade.strftime('%d/%m/%Y')}."
                        }, status=400)
                except LoteMedicamento.DoesNotExist:
                    pass

        disp = Dispensacao.objects.create(
            empresa=empresa,
            paciente_nome=paciente_nome,
            paciente_cpf=data.get("paciente_cpf", ""),
            prescricao_numero=prescricao_numero,
            medico_crm=medico_crm,
            medicamentos=medicamentos,
            valor_total=_decimal(data.get("valor_total", 0), default=Decimal("0")),
            convenio=data.get("convenio", ""),
            status=data.get("status", "pendente"),
            observacoes=data.get("observacoes", ""),
        )

        # Pós-criação: livro de registro + auditoria para controlados
        for item in medicamentos:
            med_id = item.get("medicamento_id")
            if not med_id:
                continue
            try:
                med = MedicamentoFarmacia.objects.get(pk=med_id, empresa=empresa)
            except MedicamentoFarmacia.DoesNotExist:
                continue

            if med.controlado and med.lista_portaria_344:
                lote_obj = None
                lote_numero = (item.get("lote") or "").strip()
                if lote_numero:
                    lote_obj = LoteMedicamento.objects.filter(numero_lote=lote_numero, empresa=empresa).first()

                LivroRegistroControlado.objects.create(
                    empresa=empresa,
                    medicamento=med,
                    lote=lote_obj,
                    dispensacao=disp,
                    tipo="dispensacao",
                    quantidade=_decimal(item.get("quantidade", 0), default=Decimal("0")),
                    saldo_apos=med.quantidade_atual,
                    paciente_nome=paciente_nome,
                    paciente_cpf=data.get("paciente_cpf", ""),
                    prescricao_numero=prescricao_numero,
                    medico_crm=medico_crm,
                )

        FarmaciaAuditLog.objects.create(
            empresa=empresa,
            acao="dispensar",
            modelo="Dispensacao",
            objeto_id=disp.id,
            descricao=f"Dispensação #{disp.id} para {paciente_nome} — {len(medicamentos)} item(ns)",
            usuario=getattr(getattr(request, "usuario_jwt", None), "get", lambda k, d="": d)("nome", ""),
            ip=request.META.get("REMOTE_ADDR", ""),
        )

        return JsonResponse({"ok": True, "dispensacao": _disp_to_dict(disp)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── Movimentos de Estoque ────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.estoque")
def api_farmacia_movimentos(request):
    """Lista e registra movimentos de estoque."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = EstoqueMovimento.objects.filter(empresa=empresa).select_related("medicamento")

        # Filtro por medicamento
        medicamento_id = request.GET.get("medicamento_id", "").strip()
        if medicamento_id:
            qs = qs.filter(medicamento_id=medicamento_id)

        # Filtro por tipo
        tipo = request.GET.get("tipo", "").strip()
        if tipo:
            qs = qs.filter(tipo=tipo)

        # Filtro por data
        data_inicio = request.GET.get("data_inicio", "").strip()
        if data_inicio:
            qs = qs.filter(criado_em__date__gte=data_inicio)

        data_fim = request.GET.get("data_fim", "").strip()
        if data_fim:
            qs = qs.filter(criado_em__date__lte=data_fim)

        page_qs, meta = _paginar(request, qs)
        return JsonResponse({
            "ok": True,
            "movimentos": [_mov_to_dict(m) for m in page_qs],
            "paginacao": meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        medicamento_id = data.get("medicamento_id")
        if not medicamento_id:
            return JsonResponse({"erro": "Campo 'medicamento_id' é obrigatório"}, status=400)

        try:
            med = MedicamentoFarmacia.objects.get(pk=medicamento_id, empresa=empresa)
        except MedicamentoFarmacia.DoesNotExist:
            return JsonResponse({"erro": "Medicamento não encontrado"}, status=404)

        tipo = data.get("tipo", "entrada")
        if tipo not in dict(EstoqueMovimento.TIPO_CHOICES):
            return JsonResponse({"erro": f"Tipo inválido. Opções: {list(dict(EstoqueMovimento.TIPO_CHOICES).keys())}"}, status=400)

        quantidade = _decimal(data.get("quantidade", 0), default=Decimal("0"))
        if quantidade <= 0:
            return JsonResponse({"erro": "Quantidade deve ser maior que zero"}, status=400)

        # Atualiza estoque do medicamento
        if tipo in ("entrada",):
            med.quantidade_atual += quantidade
        elif tipo in ("saida", "descarte"):
            med.quantidade_atual -= quantidade
        elif tipo == "ajuste":
            # Sem default=Decimal("0") propositalmente: precisamos distinguir
            # "nova_quantidade não foi enviada" (None → cai no delta abaixo)
            # de "nova_quantidade enviada como 0" (zera o estoque de fato).
            nova_quantidade = _decimal(data.get("nova_quantidade"))
            if nova_quantidade is not None and nova_quantidade >= 0:
                med.quantidade_atual = nova_quantidade
            else:
                med.quantidade_atual += quantidade
        # transferencia não altera o estoque diretamente aqui

        med.save(update_fields=["quantidade_atual", "atualizado_em"])

        # Resolve data_validade
        data_validade = None
        dv_str = (data.get("data_validade") or "").strip()
        if dv_str:
            try:
                data_validade = date.fromisoformat(dv_str)
            except ValueError:
                pass

        mov = EstoqueMovimento.objects.create(
            empresa=empresa,
            medicamento=med,
            tipo=tipo,
            quantidade=quantidade,
            motivo=data.get("motivo", ""),
            lote=data.get("lote", ""),
            data_validade=data_validade,
            responsavel=data.get("responsavel", ""),
            observacao=data.get("observacao", ""),
        )

        return JsonResponse({"ok": True, "movimento": _mov_to_dict(mov)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── Fornecedores ─────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pedidos")
def api_farmacia_fornecedores(request):
    """Lista e cadastra fornecedores de medicamentos."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = FornecedorFarmaciaGestao.objects.filter(empresa=empresa)

        ativo = request.GET.get("ativo", "").strip()
        if ativo == "1":
            qs = qs.filter(ativo=True)
        elif ativo == "0":
            qs = qs.filter(ativo=False)

        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(cnpj__icontains=q))

        page_qs, meta = _paginar(request, qs)
        return JsonResponse({
            "ok": True,
            "fornecedores": [_forn_to_dict(f) for f in page_qs],
            "paginacao": meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = (data.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Campo 'nome' é obrigatório"}, status=400)

        forn = FornecedorFarmaciaGestao.objects.create(
            empresa=empresa,
            nome=nome,
            cnpj=data.get("cnpj", ""),
            contato=data.get("contato", ""),
            email=data.get("email", ""),
            telefone=data.get("telefone", ""),
            prazo_entrega_dias=int(data.get("prazo_entrega_dias", 7)),
            ativo=bool(data.get("ativo", True)),
        )

        return JsonResponse({"ok": True, "fornecedor": _forn_to_dict(forn)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── Pedidos ──────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
@api_requer_feature("farmacia.pedidos")
def api_farmacia_pedidos(request):
    """Lista e cadastra pedidos de compra de medicamentos."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = PedidoFarmacia.objects.filter(empresa=empresa).select_related("fornecedor")

        status = request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        fornecedor_id = request.GET.get("fornecedor_id", "").strip()
        if fornecedor_id:
            qs = qs.filter(fornecedor_id=fornecedor_id)

        page_qs, meta = _paginar(request, qs)
        return JsonResponse({
            "ok": True,
            "pedidos": [_pedido_to_dict(p) for p in page_qs],
            "paginacao": meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        fornecedor = None
        fornecedor_id = data.get("fornecedor_id")
        if fornecedor_id:
            try:
                fornecedor = FornecedorFarmaciaGestao.objects.get(pk=fornecedor_id, empresa=empresa)
            except FornecedorFarmaciaGestao.DoesNotExist:
                return JsonResponse({"erro": "Fornecedor não encontrado"}, status=404)

        itens = data.get("itens", [])
        if not isinstance(itens, list):
            itens = []

        # Resolve data_entrega_prevista
        data_entrega_prevista = None
        dep_str = (data.get("data_entrega_prevista") or "").strip()
        if dep_str:
            try:
                data_entrega_prevista = date.fromisoformat(dep_str)
            except ValueError:
                pass

        # Calcula valor_total a partir dos itens se não fornecido
        valor_total = _decimal(data.get("valor_total", 0), default=Decimal("0"))
        if valor_total == 0 and itens:
            for item in itens:
                qty = _decimal(item.get("quantidade", 0), default=Decimal("0"))
                preco = _decimal(item.get("preco_unitario", 0), default=Decimal("0"))
                valor_total += qty * preco

        pedido = PedidoFarmacia.objects.create(
            empresa=empresa,
            fornecedor=fornecedor,
            data_entrega_prevista=data_entrega_prevista,
            status=data.get("status", "rascunho"),
            itens=itens,
            valor_total=valor_total,
            observacao=data.get("observacao", ""),
        )

        return JsonResponse({"ok": True, "pedido": _pedido_to_dict(pedido)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)
