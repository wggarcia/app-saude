import json
from datetime import date, timedelta
from collections import defaultdict
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import (
    PacienteFarmacia, ReceitaMedica, InventarioFarmacia, ItemInventario,
    DescarteItemFarmacia, ItemFarmacia, LoteMedicamento, MovimentoEstoque,
    DispensacaoMedicamento,
)
from .views_dashboard import _empresa_autenticada


def _e(req):
    return _empresa_autenticada(req)


# ── Pacientes ──────────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_pacientes_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        q = request.GET.get("q", "").strip()
        qs = PacienteFarmacia.objects.filter(empresa=e, ativo=True)
        if q:
            qs = qs.filter(nome__icontains=q) | PacienteFarmacia.objects.filter(empresa=e, ativo=True, cpf__icontains=q)
        return JsonResponse({"pacientes": [_pac_dict(p) for p in qs[:100]]})
    data = json.loads(request.body or "{}")
    if not data.get("nome"):
        return JsonResponse({"erro": "Nome obrigatório"}, status=400)
    # handle unique CPF gracefully
    cpf = data.get("cpf", "").strip()
    if cpf:
        existing = PacienteFarmacia.objects.filter(empresa=e, cpf=cpf).first()
        if existing:
            return JsonResponse({"erro": "CPF já cadastrado", "id": existing.id}, status=400)
    p = PacienteFarmacia.objects.create(
        empresa=e,
        nome=data.get("nome", ""),
        cpf=cpf,
        data_nascimento=data.get("data_nascimento") or None,
        sexo=data.get("sexo", ""),
        telefone=data.get("telefone", ""),
        email=data.get("email", ""),
        endereco=data.get("endereco", ""),
        alergias=data.get("alergias", ""),
        condicoes_cronicas=data.get("condicoes_cronicas", ""),
        medicamentos_uso_continuo=data.get("medicamentos_uso_continuo", ""),
    )
    return JsonResponse(_pac_dict(p), status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
def api_paciente_farmacia_detalhe(request, paciente_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        p = PacienteFarmacia.objects.get(pk=paciente_id, empresa=e)
    except PacienteFarmacia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "GET":
        d = _pac_dict(p)
        d["historico"] = [
            {"item": disp.item.nome, "quantidade": disp.quantidade,
             "data": disp.dispensado_em.isoformat()}
            for disp in DispensacaoMedicamento.objects.filter(
                empresa=e, paciente_cpf=p.cpf
            ).select_related("item")[:20] if p.cpf
        ]
        return JsonResponse(d)
    if request.method == "DELETE":
        p.ativo = False
        p.save()
        return JsonResponse({"ok": True})
    data = json.loads(request.body or "{}")
    campos = ["nome", "cpf", "data_nascimento", "sexo", "telefone", "email",
              "endereco", "alergias", "condicoes_cronicas", "medicamentos_uso_continuo", "ativo"]
    for campo in campos:
        if campo in data:
            val = data[campo]
            if campo == "data_nascimento" and val == "":
                val = None
            setattr(p, campo, val)
    p.save()
    return JsonResponse({"ok": True})


def _pac_dict(p):
    return {
        "id": p.id, "nome": p.nome, "cpf": p.cpf,
        "data_nascimento": p.data_nascimento.isoformat() if p.data_nascimento else None,
        "sexo": p.sexo, "telefone": p.telefone, "email": p.email,
        "endereco": p.endereco, "alergias": p.alergias,
        "condicoes_cronicas": p.condicoes_cronicas,
        "medicamentos_uso_continuo": p.medicamentos_uso_continuo,
        "ativo": p.ativo, "criado_em": p.criado_em.isoformat(),
    }


# ── Receitas ───────────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_receitas_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        status_f = request.GET.get("status", "")
        qs = ReceitaMedica.objects.filter(empresa=e).select_related("item", "paciente")
        if status_f:
            qs = qs.filter(status=status_f)
        # auto-marcar vencidas
        hoje = date.today()
        ids_vencer = [r.id for r in qs if r.data_validade and r.data_validade < hoje and r.status == "pendente"]
        if ids_vencer:
            ReceitaMedica.objects.filter(pk__in=ids_vencer).update(status="vencida")
            for r in qs:
                if r.id in ids_vencer:
                    r.status = "vencida"
        return JsonResponse({"receitas": [_rec_dict(r) for r in qs[:200]]})
    data = json.loads(request.body or "{}")
    if not data.get("data_emissao"):
        return JsonResponse({"erro": "Data de emissão obrigatória"}, status=400)
    item = None
    if data.get("item_id"):
        try:
            item = ItemFarmacia.objects.get(pk=data["item_id"], empresa=e)
        except ItemFarmacia.DoesNotExist:
            pass
    paciente = None
    if data.get("paciente_id"):
        try:
            paciente = PacienteFarmacia.objects.get(pk=data["paciente_id"], empresa=e)
        except PacienteFarmacia.DoesNotExist:
            pass
    r = ReceitaMedica.objects.create(
        empresa=e,
        paciente=paciente,
        paciente_nome=data.get("paciente_nome", paciente.nome if paciente else ""),
        paciente_cpf=data.get("paciente_cpf", paciente.cpf if paciente else ""),
        tipo=data.get("tipo", "simples"),
        numero_receita=data.get("numero_receita", ""),
        medico_nome=data.get("medico_nome", ""),
        medico_crm=data.get("medico_crm", ""),
        data_emissao=data["data_emissao"],
        data_validade=data.get("data_validade") or None,
        item=item,
        medicamento_descricao=data.get("medicamento_descricao", ""),
        quantidade=int(data.get("quantidade", 1)),
        posologia=data.get("posologia", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse(_rec_dict(r), status=201)


@require_http_methods(["PUT", "DELETE"])
def api_receita_farmacia_detalhe(request, receita_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        r = ReceitaMedica.objects.get(pk=receita_id, empresa=e)
    except ReceitaMedica.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        r.delete()
        return JsonResponse({"ok": True})
    data = json.loads(request.body or "{}")
    campos = ["status", "numero_receita", "medico_nome", "medico_crm",
              "medicamento_descricao", "quantidade", "posologia", "observacoes",
              "tipo", "data_validade"]
    for campo in campos:
        if campo in data:
            val = data[campo]
            if campo == "data_validade" and val == "":
                val = None
            setattr(r, campo, val)
    r.save()
    return JsonResponse({"ok": True})


def _rec_dict(r):
    return {
        "id": r.id,
        "tipo": r.tipo,
        "tipo_label": r.get_tipo_display(),
        "numero_receita": r.numero_receita,
        "paciente_nome": r.paciente_nome or (r.paciente.nome if r.paciente else ""),
        "paciente_cpf": r.paciente_cpf,
        "medico_nome": r.medico_nome,
        "medico_crm": r.medico_crm,
        "data_emissao": r.data_emissao.isoformat() if r.data_emissao else None,
        "data_validade": r.data_validade.isoformat() if r.data_validade else None,
        "item_nome": r.item.nome if r.item else r.medicamento_descricao,
        "item_id": r.item_id,
        "quantidade": r.quantidade,
        "posologia": r.posologia,
        "status": r.status,
        "status_label": r.get_status_display(),
        "observacoes": r.observacoes,
        "criado_em": r.criado_em.isoformat(),
    }


# ── Inventário Periódico ───────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_inventarios_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = InventarioFarmacia.objects.filter(empresa=e)[:50]
        return JsonResponse({"inventarios": [_inv_dict(inv) for inv in qs]})
    data = json.loads(request.body or "{}")
    inv = InventarioFarmacia.objects.create(
        empresa=e,
        descricao=data.get("descricao", ""),
        responsavel=data.get("responsavel", ""),
        observacoes=data.get("observacoes", ""),
    )
    # snapshot estoque atual
    itens = ItemFarmacia.objects.filter(empresa=e, ativo=True)
    for item in itens:
        ItemInventario.objects.create(
            inventario=inv,
            item=item,
            estoque_sistema=item.estoque_atual,
        )
    return JsonResponse(_inv_dict(inv), status=201)


@require_http_methods(["GET", "PUT"])
def api_inventario_farmacia_detalhe(request, inventario_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        inv = InventarioFarmacia.objects.get(pk=inventario_id, empresa=e)
    except InventarioFarmacia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "GET":
        d = _inv_dict(inv)
        d["itens"] = [
            {"id": ii.id, "item_id": ii.item_id, "item_nome": ii.item.nome,
             "estoque_sistema": ii.estoque_sistema,
             "estoque_contado": ii.estoque_contado,
             "diferenca": ii.diferenca, "ajustado": ii.ajustado,
             "observacao": ii.observacao}
            for ii in inv.itens.select_related("item").all()
        ]
        return JsonResponse(d)
    data = json.loads(request.body or "{}")
    # atualizar contagens
    contagens = data.get("contagens", [])
    for c in contagens:
        try:
            ii = ItemInventario.objects.get(pk=c["id"], inventario=inv)
            contado = int(c.get("estoque_contado", ii.estoque_contado or 0))
            ii.estoque_contado = contado
            ii.diferenca = contado - ii.estoque_sistema
            ii.observacao = c.get("observacao", ii.observacao)
            ii.save()
        except (ItemInventario.DoesNotExist, KeyError):
            pass
    # concluir se solicitado
    acao = data.get("acao", "")
    if acao == "concluir" and inv.status == "aberto":
        inv.status = "concluido"
        inv.concluido_em = timezone.now()
        inv.save()
        # aplicar ajustes no estoque
        aplicar = data.get("aplicar_ajustes", False)
        if aplicar:
            for ii in inv.itens.filter(diferenca__isnull=False, ajustado=False).select_related("item"):
                if ii.diferenca != 0:
                    item = ii.item
                    ant = item.estoque_atual
                    item.estoque_atual = ii.estoque_contado
                    item.save()
                    MovimentoEstoque.objects.create(
                        empresa=e, item=item, tipo="ajuste",
                        quantidade=abs(ii.diferenca),
                        estoque_anterior=ant,
                        estoque_posterior=item.estoque_atual,
                        motivo=f"Ajuste inventário #{inv.pk}",
                        responsavel=inv.responsavel,
                    )
                    ii.ajustado = True
                    ii.save()
    elif acao == "cancelar":
        inv.status = "cancelado"
        inv.save()
    return JsonResponse({"ok": True, "status": inv.status})


def _inv_dict(inv):
    total = inv.itens.count()
    contados = inv.itens.filter(estoque_contado__isnull=False).count()
    diferencas = inv.itens.filter(diferenca__isnull=False).exclude(diferenca=0).count()
    return {
        "id": inv.id, "descricao": inv.descricao, "status": inv.status,
        "status_label": inv.get_status_display(),
        "responsavel": inv.responsavel,
        "iniciado_em": inv.iniciado_em.isoformat(),
        "concluido_em": inv.concluido_em.isoformat() if inv.concluido_em else None,
        "total_itens": total, "itens_contados": contados, "diferencas": diferencas,
        "progresso": round(contados / total * 100) if total else 0,
    }


# ── Descarte de Medicamentos ───────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_descartes_farmacia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = DescarteItemFarmacia.objects.filter(empresa=e).select_related("item", "lote")[:200]
        return JsonResponse({"descartes": [_desc_dict(d) for d in qs]})
    data = json.loads(request.body or "{}")
    try:
        item = ItemFarmacia.objects.get(pk=data["item_id"], empresa=e)
    except (KeyError, ItemFarmacia.DoesNotExist):
        return JsonResponse({"erro": "Item não encontrado"}, status=404)
    lote = None
    if data.get("lote_id"):
        try:
            lote = LoteMedicamento.objects.get(pk=data["lote_id"], empresa=e)
        except LoteMedicamento.DoesNotExist:
            pass
    quantidade = int(data.get("quantidade", 1))
    # baixa no estoque
    ant = item.estoque_atual
    item.estoque_atual = max(0, item.estoque_atual - quantidade)
    item.save()
    MovimentoEstoque.objects.create(
        empresa=e, item=item, tipo="vencimento",
        quantidade=quantidade, estoque_anterior=ant,
        estoque_posterior=item.estoque_atual,
        motivo=f"Descarte — {data.get('motivo', 'vencimento')}",
        responsavel=data.get("responsavel", ""),
    )
    if lote:
        lote.quantidade_atual = max(0, lote.quantidade_atual - quantidade)
        lote.save()
    d = DescarteItemFarmacia.objects.create(
        empresa=e, item=item, lote=lote,
        motivo=data.get("motivo", "vencimento"),
        quantidade=quantidade,
        responsavel=data.get("responsavel", ""),
        empresa_descarte=data.get("empresa_descarte", ""),
        numero_manifesto=data.get("numero_manifesto", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse(_desc_dict(d), status=201)


def _desc_dict(d):
    return {
        "id": d.id, "item_nome": d.item.nome,
        "lote_numero": d.lote.numero_lote if d.lote else "",
        "motivo": d.motivo, "motivo_label": d.get_motivo_display(),
        "quantidade": d.quantidade, "responsavel": d.responsavel,
        "empresa_descarte": d.empresa_descarte,
        "numero_manifesto": d.numero_manifesto,
        "observacoes": d.observacoes,
        "data_descarte": d.data_descarte.isoformat(),
    }


# ── KPIs Avançados e Relatórios ────────────────────────────────────────────────

def api_farmacia_kpis_avancados(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    # CMM — Consumo Médio Mensal (últimos 3 meses)
    tres_meses_atras = hoje - timedelta(days=90)
    saidas = MovimentoEstoque.objects.filter(
        empresa=e, tipo__in=["saida", "vencimento"],
        data_movimento__date__gte=tres_meses_atras
    ).select_related("item")
    consumo_por_item = defaultdict(int)
    for s in saidas:
        consumo_por_item[s.item_id] += s.quantidade
    cmm_itens = {iid: round(qty / 3) for iid, qty in consumo_por_item.items()}

    # Ruptura de estoque (itens com estoque 0 que tiveram saída nos últimos 30 dias)
    itens_zerados = ItemFarmacia.objects.filter(empresa=e, ativo=True, estoque_atual__lte=0)
    ruptura = itens_zerados.count()

    # Itens vencendo em 7 dias
    vencendo_7 = LoteMedicamento.objects.filter(
        empresa=e,
        data_validade__range=[hoje, hoje + timedelta(days=7)],
        quantidade_atual__gt=0
    ).count()

    # Total descartes mês atual
    descartes_mes = DescarteItemFarmacia.objects.filter(
        empresa=e, data_descarte__date__gte=inicio_mes
    ).count()

    # Total receitas pendentes
    receitas_pendentes = ReceitaMedica.objects.filter(empresa=e, status="pendente").count()

    # Total pacientes cadastrados
    total_pacientes = PacienteFarmacia.objects.filter(empresa=e, ativo=True).count()

    # Inventários abertos
    inventarios_abertos = InventarioFarmacia.objects.filter(empresa=e, status="aberto").count()

    return JsonResponse({
        "ruptura_estoque": ruptura,
        "vencendo_7_dias": vencendo_7,
        "descartes_mes": descartes_mes,
        "receitas_pendentes": receitas_pendentes,
        "total_pacientes": total_pacientes,
        "inventarios_abertos": inventarios_abertos,
    })


def api_farmacia_relatorio_curva_abc(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    # consumo últimos 90 dias
    tres_meses_atras = date.today() - timedelta(days=90)
    saidas = MovimentoEstoque.objects.filter(
        empresa=e, tipo__in=["saida", "vencimento"],
        data_movimento__date__gte=tres_meses_atras
    ).select_related("item")

    consumo = defaultdict(lambda: {"nome": "", "quantidade": 0, "item_id": 0})
    for s in saidas:
        consumo[s.item_id]["nome"] = s.item.nome
        consumo[s.item_id]["item_id"] = s.item_id
        consumo[s.item_id]["quantidade"] += s.quantidade

    lista = sorted(consumo.values(), key=lambda x: x["quantidade"], reverse=True)
    total = sum(i["quantidade"] for i in lista)

    acum = 0
    for item in lista:
        item["percentual"] = round(item["quantidade"] / total * 100, 1) if total else 0
        acum += item["percentual"]
        item["acumulado"] = round(acum, 1)
        item["classe"] = "A" if item["acumulado"] <= 80 else ("B" if item["acumulado"] <= 95 else "C")

    return JsonResponse({
        "total_consumo": total,
        "periodo": "últimos 90 dias",
        "itens": lista,
        "resumo": {
            "A": sum(1 for i in lista if i["classe"] == "A"),
            "B": sum(1 for i in lista if i["classe"] == "B"),
            "C": sum(1 for i in lista if i["classe"] == "C"),
        }
    })


def api_farmacia_relatorio_cmm(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    tres_meses = hoje - timedelta(days=90)
    saidas = MovimentoEstoque.objects.filter(
        empresa=e, tipo__in=["saida", "vencimento"],
        data_movimento__date__gte=tres_meses
    ).select_related("item")

    por_item = defaultdict(lambda: {"nome": "", "total_3m": 0, "item_id": 0})
    for s in saidas:
        por_item[s.item_id]["nome"] = s.item.nome
        por_item[s.item_id]["item_id"] = s.item_id
        por_item[s.item_id]["total_3m"] += s.quantidade

    # enriquecer com estoque atual e CMM
    item_ids = list(por_item.keys())
    itens_db = {i.id: i for i in ItemFarmacia.objects.filter(pk__in=item_ids)}

    resultado = []
    for iid, dados in por_item.items():
        item = itens_db.get(iid)
        cmm = round(dados["total_3m"] / 3, 1)
        estoque_atual = item.estoque_atual if item else 0
        cobertura = round(estoque_atual / cmm, 1) if cmm > 0 else 0
        resultado.append({
            "item_id": iid,
            "nome": dados["nome"],
            "cmm": cmm,
            "estoque_atual": estoque_atual,
            "cobertura_meses": cobertura,
            "status": "critico" if cobertura < 1 else ("alerta" if cobertura < 2 else "ok"),
        })

    resultado.sort(key=lambda x: x["cobertura_meses"])
    return JsonResponse({"itens": resultado, "periodo": "últimos 3 meses"})


def api_farmacia_relatorio_giro(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    ano_atras = hoje - timedelta(days=365)

    saidas = MovimentoEstoque.objects.filter(
        empresa=e, tipo__in=["saida", "vencimento"],
        data_movimento__date__gte=ano_atras
    ).select_related("item")
    entradas = MovimentoEstoque.objects.filter(
        empresa=e, tipo="entrada",
        data_movimento__date__gte=ano_atras
    ).select_related("item")

    consumo = defaultdict(int)
    compras = defaultdict(int)
    for s in saidas:
        consumo[s.item_id] += s.quantidade
    for e_ in entradas:
        compras[e_.item_id] += e_.quantidade

    itens = {i.id: i for i in ItemFarmacia.objects.filter(empresa=e, ativo=True)}
    resultado = []
    for iid, item in itens.items():
        c = consumo.get(iid, 0)
        comp = compras.get(iid, 0)
        estoque_medio = (item.estoque_atual + comp - c) / 2 if (comp > 0 or c > 0) else item.estoque_atual
        giro = round(c / estoque_medio, 2) if estoque_medio > 0 else 0
        resultado.append({
            "item_id": iid,
            "nome": item.nome,
            "consumo_anual": c,
            "compras_anual": comp,
            "estoque_atual": item.estoque_atual,
            "giro": giro,
            "classificacao": "alto" if giro >= 4 else ("medio" if giro >= 1 else "baixo"),
        })

    resultado.sort(key=lambda x: x["giro"], reverse=True)
    return JsonResponse({"itens": resultado, "periodo": "últimos 12 meses"})
