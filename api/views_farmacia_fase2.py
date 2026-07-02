"""
Farmácia — Fase 2: Multi-unidade & Rede
  • Estoque consolidado da rede
  • Transferências entre unidades (MedicamentoFarmacia)
  • KPIs de rede
  • Alertas cross-unit (ruptura, vencimento)
"""
import json
from datetime import date, timedelta

from decimal import Decimal

from django.db.models import Case, F, IntegerField, Q, Sum, Count, Value, When
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import (
    MedicamentoFarmacia, LoteMedicamento,
    TransferenciaFarmaciaMed, Rede, UnidadeRede,
)
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    setor = get_setor(empresa)
    if setor != "farmacia":
        return JsonResponse(
            {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
            status=403,
        )
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência da farmácia."}, status=403)
    return empresa


def _get_unidade(empresa):
    try:
        return empresa.unidade_rede
    except Exception:
        return None


def _transf_to_dict(t):
    return {
        "id": t.id,
        "medicamento_id": t.medicamento_id,
        "medicamento_nome": t.medicamento.nome,
        "medicamento_forma": t.medicamento.forma_farmaceutica,
        "lote_numero": t.lote.numero_lote if t.lote else "",
        "quantidade_solicitada": float(t.quantidade_solicitada),
        "quantidade_aprovada": float(t.quantidade_aprovada) if t.quantidade_aprovada is not None else None,
        "status": t.status,
        "urgente": t.urgente,
        "motivo": t.motivo,
        "observacoes": t.observacoes,
        "solicitante_nome": t.empresa_solicitante.nome,
        "fornecedora_nome": t.empresa_fornecedora.nome,
        "solicitado_por": t.solicitado_por,
        "aprovado_por": t.aprovado_por,
        "solicitado_em": t.solicitado_em.strftime("%d/%m/%Y %H:%M"),
        "atualizado_em": t.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Estoque consolidado da rede ──────────────────────────────────────────────

@require_http_methods(["GET"])
def api_rede_farmacia_estoque(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    unidade = _get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({"aviso": "Empresa não pertence a uma rede", "unidades": []})

    rede = unidade.rede
    unidades_rede = rede.unidades.filter(ativa=True).select_related("empresa")

    # Pré-carrega IDs das empresas para evitar N+1 queries
    empresa_ids = [u.empresa_id for u in unidades_rede]
    em_30 = date.today() + timedelta(days=30)

    _CRITICO = Decimal("1.10")
    _BAIXO   = Decimal("1.50")
    meds_por_empresa = {
        row["empresa_id"]: row
        for row in MedicamentoFarmacia.objects
            .filter(empresa_id__in=empresa_ids, ativo=True)
            .annotate(
                is_critico=Case(
                    When(quantidade_atual__lte=0, then=Value(1)),
                    When(quantidade_minima__gt=0,
                         quantidade_atual__lte=F("quantidade_minima") * _CRITICO,
                         then=Value(1)),
                    default=Value(0), output_field=IntegerField(),
                ),
                is_baixo=Case(
                    When(quantidade_atual__lte=0, then=Value(0)),
                    When(quantidade_minima__gt=0,
                         quantidade_atual__lte=F("quantidade_minima") * _CRITICO,
                         then=Value(0)),
                    When(quantidade_minima__gt=0,
                         quantidade_atual__lte=F("quantidade_minima") * _BAIXO,
                         then=Value(1)),
                    default=Value(0), output_field=IntegerField(),
                ),
            )
            .values("empresa_id")
            .annotate(criticos=Sum("is_critico"), baixos=Sum("is_baixo"))
    }
    lotes_vencendo = {
        row["empresa_id"]: row["n"]
        for row in LoteMedicamento.objects
            .filter(empresa_id__in=empresa_ids,
                    data_validade__lte=em_30, data_validade__gte=date.today(),
                    quantidade_atual__gt=0)
            .values("empresa_id").annotate(n=Count("id"))
    }
    lotes_vencidos = {
        row["empresa_id"]: row["n"]
        for row in LoteMedicamento.objects
            .filter(empresa_id__in=empresa_ids,
                    data_validade__lt=date.today(), quantidade_atual__gt=0)
            .values("empresa_id").annotate(n=Count("id"))
    }

    resultado = []
    for u in unidades_rede:
        meds = MedicamentoFarmacia.objects.filter(empresa=u.empresa, ativo=True)
        _m = meds_por_empresa.get(u.empresa_id, {})
        criticos = _m.get("criticos", 0)
        baixos = _m.get("baixos", 0)
        vencendo = lotes_vencendo.get(u.empresa_id, 0)
        vencidos = lotes_vencidos.get(u.empresa_id, 0)

        resultado.append({
            "unidade_id": u.id,
            "empresa_id": u.empresa_id,
            "unidade_nome": u.nome_unidade or u.empresa.nome,
            "codigo": u.codigo_unidade,
            "cidade": u.cidade,
            "estado": u.estado,
            "eh_minha": u.empresa_id == empresa.id,
            "total_medicamentos": meds.count(),
            "criticos": criticos,
            "baixos": baixos,
            "lotes_vencendo": vencendo,
            "lotes_vencidos": vencidos,
            "medicamentos": [
                {
                    "id": m.id,
                    "nome": m.nome,
                    "forma": m.forma_farmaceutica,
                    "quantidade_atual": float(m.quantidade_atual),
                    "quantidade_minima": float(m.quantidade_minima),
                    "status_estoque": m.status_estoque,
                    "controlado": m.controlado,
                    "lista_portaria_344": m.lista_portaria_344,
                }
                for m in meds
            ],
        })

    return JsonResponse({
        "rede_nome": rede.nome,
        "rede_tipo": rede.tipo,
        "total_unidades": len(resultado),
        "unidades": resultado,
    })


# ─── Disponibilidade de medicamento na rede ───────────────────────────────────

@require_http_methods(["GET"])
def api_rede_farmacia_disponibilidade(request, nome_med):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    unidade = _get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({"disponibilidade": []})

    rede = unidade.rede
    outras_unidades = rede.unidades.filter(ativa=True).exclude(empresa=empresa).select_related("empresa")

    disponibilidade = []
    for u in outras_unidades:
        meds = MedicamentoFarmacia.objects.filter(
            empresa=u.empresa, ativo=True,
            nome__icontains=nome_med, quantidade_atual__gt=0
        )
        if meds.exists():
            disponibilidade.append({
                "unidade_nome": u.nome_unidade or u.empresa.nome,
                "empresa_id": u.empresa_id,
                "cidade": u.cidade,
                "estado": u.estado,
                "medicamentos": [
                    {
                        "id": m.id,
                        "nome": m.nome,
                        "concentracao": m.concentracao,
                        "quantidade_disponivel": float(m.quantidade_atual - m.quantidade_minima),
                        "quantidade_atual": float(m.quantidade_atual),
                    }
                    for m in meds
                ],
            })

    return JsonResponse({"medicamento": nome_med, "disponibilidade": disponibilidade})


# ─── Transferências ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_rede_farmacia_transferencias(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    unidade = _get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({"erro": "Empresa não pertence a uma rede"}, status=400)

    rede = unidade.rede

    if request.method == "GET":
        filtro = request.GET.get("filtro", "todas")
        qs = TransferenciaFarmaciaMed.objects.filter(rede=rede).filter(
            Q(empresa_solicitante=empresa) | Q(empresa_fornecedora=empresa)
        ).select_related("medicamento", "empresa_solicitante", "empresa_fornecedora", "lote")

        if filtro == "enviadas":
            qs = qs.filter(empresa_solicitante=empresa)
        elif filtro == "recebidas":
            qs = qs.filter(empresa_fornecedora=empresa)
        elif filtro == "pendentes":
            qs = qs.filter(status="pendente")

        return JsonResponse({"transferencias": [_transf_to_dict(t) for t in qs[:100]]})

    # POST — nova solicitação de transferência
    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    med_id = data.get("medicamento_id")
    empresa_forn_id = data.get("empresa_fornecedora_id")
    qtd = data.get("quantidade_solicitada")

    if not all([med_id, empresa_forn_id, qtd]):
        return JsonResponse({"erro": "medicamento_id, empresa_fornecedora_id e quantidade_solicitada são obrigatórios"}, status=400)

    try:
        med = MedicamentoFarmacia.objects.get(pk=med_id, empresa=empresa)
    except MedicamentoFarmacia.DoesNotExist:
        # Pode solicitar um medicamento de outra unidade (não precisa ser do próprio estoque)
        try:
            med = MedicamentoFarmacia.objects.get(pk=med_id)
        except MedicamentoFarmacia.DoesNotExist:
            return JsonResponse({"erro": "Medicamento não encontrado"}, status=404)

    # Validar que a empresa fornecedora é da mesma rede
    try:
        unidade_forn = UnidadeRede.objects.get(empresa_id=empresa_forn_id, rede=rede)
    except UnidadeRede.DoesNotExist:
        return JsonResponse({"erro": "Empresa fornecedora não pertence à mesma rede"}, status=400)

    if empresa_forn_id == empresa.id:
        return JsonResponse({"erro": "Não pode solicitar transferência para a própria unidade"}, status=400)

    from decimal import Decimal, InvalidOperation
    try:
        qtd_dec = Decimal(str(qtd))
    except (InvalidOperation, TypeError):
        return JsonResponse({"erro": "Quantidade inválida"}, status=400)

    t = TransferenciaFarmaciaMed.objects.create(
        rede=rede,
        empresa_solicitante=empresa,
        empresa_fornecedora_id=empresa_forn_id,
        medicamento=med,
        quantidade_solicitada=qtd_dec,
        urgente=data.get("urgente", False),
        motivo=data.get("motivo", ""),
        observacoes=data.get("observacoes", ""),
        solicitado_por=data.get("solicitado_por", ""),
        status="pendente",
    )

    return JsonResponse({"ok": True, "transferencia": _transf_to_dict(t)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def api_rede_farmacia_transferencia_acao(request, transf_id):
    """Approve / send / receive / cancel / reject a transfer."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        t = TransferenciaFarmaciaMed.objects.select_related("medicamento", "empresa_solicitante", "empresa_fornecedora").get(pk=transf_id)
    except TransferenciaFarmaciaMed.DoesNotExist:
        return JsonResponse({"erro": "Transferência não encontrada"}, status=404)

    # Validar acesso
    if t.empresa_solicitante != empresa and t.empresa_fornecedora != empresa:
        return JsonResponse({"erro": "Sem permissão"}, status=403)

    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao")  # aprovar, rejeitar, enviar, receber, cancelar

    transicoes_validas = {
        "pendente":  ["aprovar", "rejeitar", "cancelar"],
        "aprovada":  ["enviar", "cancelar"],
        "enviada":   ["receber", "cancelar"],
    }
    permitidas = transicoes_validas.get(t.status, [])
    if acao not in permitidas:
        return JsonResponse({"erro": f"Ação '{acao}' não permitida no status '{t.status}'"}, status=400)

    novo_status_map = {
        "aprovar": "aprovada", "rejeitar": "rejeitada",
        "enviar": "enviada", "receber": "recebida", "cancelar": "cancelada",
    }
    t.status = novo_status_map[acao]

    if acao == "aprovar":
        from decimal import Decimal, InvalidOperation
        qtd_apr = data.get("quantidade_aprovada")
        if qtd_apr is not None:
            try:
                t.quantidade_aprovada = Decimal(str(qtd_apr))
            except (InvalidOperation, TypeError):
                pass
        else:
            t.quantidade_aprovada = t.quantidade_solicitada
        t.aprovado_por = data.get("aprovado_por", "")

    if acao == "receber":
        # Dar entrada no estoque do solicitante
        med_sol = MedicamentoFarmacia.objects.filter(
            empresa=t.empresa_solicitante, nome=t.medicamento.nome
        ).first()
        qtd_recebida = t.quantidade_aprovada or t.quantidade_solicitada

        if med_sol:
            med_sol.quantidade_atual += qtd_recebida
            med_sol.save(update_fields=["quantidade_atual", "atualizado_em"])

        # Baixar estoque do fornecedor
        med_forn = MedicamentoFarmacia.objects.filter(
            empresa=t.empresa_fornecedora, pk=t.medicamento_id
        ).first()
        if med_forn and med_forn.quantidade_atual >= qtd_recebida:
            med_forn.quantidade_atual -= qtd_recebida
            med_forn.save(update_fields=["quantidade_atual", "atualizado_em"])

    t.save()

    return JsonResponse({"ok": True, "transferencia": _transf_to_dict(t)})


# ─── KPIs de rede ────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_rede_farmacia_kpis(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    unidade = _get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({"aviso": "Não pertence a uma rede"})

    rede = unidade.rede
    unidades_rede = rede.unidades.filter(ativa=True)
    empresas_ids = unidades_rede.values_list("empresa_id", flat=True)

    hoje = date.today()
    em_30 = hoje + timedelta(days=30)

    total_meds = MedicamentoFarmacia.objects.filter(empresa_id__in=empresas_ids, ativo=True).count()
    criticos = sum(
        1 for m in MedicamentoFarmacia.objects.filter(empresa_id__in=empresas_ids, ativo=True)
        if m.status_estoque == "critico"
    )
    vencendo = LoteMedicamento.objects.filter(
        empresa_id__in=empresas_ids, data_validade__range=(hoje, em_30), quantidade_atual__gt=0
    ).count()
    vencidos = LoteMedicamento.objects.filter(
        empresa_id__in=empresas_ids, data_validade__lt=hoje, quantidade_atual__gt=0
    ).count()
    transf_pendentes = TransferenciaFarmaciaMed.objects.filter(rede=rede, status="pendente").count()
    transf_urgentes = TransferenciaFarmaciaMed.objects.filter(rede=rede, status="pendente", urgente=True).count()

    return JsonResponse({
        "rede_nome": rede.nome,
        "total_unidades": unidades_rede.count(),
        "total_medicamentos": total_meds,
        "medicamentos_criticos": criticos,
        "lotes_vencendo_30d": vencendo,
        "lotes_vencidos": vencidos,
        "transferencias_pendentes": transf_pendentes,
        "transferencias_urgentes": transf_urgentes,
    })
