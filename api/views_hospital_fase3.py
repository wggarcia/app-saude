"""
Hospital — Fase 3: Faturamento TUSS/CBhpm + Analytics
  • FaturaHospitalar  — fatura por internação (convênio/SUS/particular)
  • ItemFaturamento   — linhas com código TUSS e CBhpm
  • Analytics         — ALOS, ocupação, mortalidade, readmissão, top-CIDs,
                        faturamento mensal, cirurgias por porte, exames por tipo
"""
import json
from datetime import timedelta
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Sum, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor
from .models import (
    FaturaHospitalar, ItemFaturamento,
    PacienteInternado, LeitoHospitalar,
    SumarioAlta, CentroCirurgico, PedidoExame,
)
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    setor = get_setor(empresa)
    if setor != "hospital":
        return JsonResponse(
            {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
            status=403,
        )
    return empresa


def _as_date(value):
    if value is None:
        return None
    return value.date() if hasattr(value, "date") else value


def _fatura_to_dict(f):
    return {
        "id": f.id,
        "paciente_id": f.paciente_id,
        "paciente_nome": f.paciente.nome,
        "numero_guia": f.numero_guia,
        "convenio": f.convenio,
        "nome_convenio": f.nome_convenio,
        "numero_carteirinha": f.numero_carteirinha,
        "status": f.status,
        "valor_total": float(f.valor_total),
        "valor_glosa": float(f.valor_glosa),
        "valor_pago": float(f.valor_pago),
        "valor_liquido": float(f.valor_total - f.valor_glosa),
        "observacoes": f.observacoes,
        "data_envio": f.data_envio.strftime("%d/%m/%Y %H:%M") if f.data_envio else None,
        "data_pagamento": f.data_pagamento.strftime("%d/%m/%Y %H:%M") if f.data_pagamento else None,
        "criado_em": f.criado_em.strftime("%d/%m/%Y %H:%M"),
        "total_itens": f.itens.count(),
    }


def _item_to_dict(i):
    return {
        "id": i.id,
        "tipo": i.tipo,
        "codigo_tuss": i.codigo_tuss,
        "codigo_cbhpm": i.codigo_cbhpm,
        "descricao": i.descricao,
        "quantidade": float(i.quantidade),
        "valor_unitario": float(i.valor_unitario),
        "valor_total": float(i.valor_total),
        "data_competencia": i.data_competencia.strftime("%d/%m/%Y"),
        "observacao": i.observacao,
        "criado_em": i.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Fatura por Paciente ──────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST", "PUT"])
def api_fatura_paciente(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pac = PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
    except PacienteInternado.DoesNotExist:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        try:
            fatura = FaturaHospitalar.objects.prefetch_related("itens").get(paciente=pac)
            d = _fatura_to_dict(fatura)
            d["itens"] = [_item_to_dict(i) for i in fatura.itens.all()]
            return JsonResponse({"fatura": d})
        except FaturaHospitalar.DoesNotExist:
            return JsonResponse({"fatura": None})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if request.method == "POST":
        if FaturaHospitalar.objects.filter(paciente=pac).exists():
            return JsonResponse({"erro": "Fatura já existe para este paciente. Use PUT para atualizar."}, status=400)
        fatura = FaturaHospitalar.objects.create(
            empresa=empresa,
            paciente=pac,
            convenio=data.get("convenio", "particular"),
            nome_convenio=data.get("nome_convenio", ""),
            numero_carteirinha=data.get("numero_carteirinha", ""),
            numero_guia=data.get("numero_guia", ""),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"ok": True, "fatura": _fatura_to_dict(fatura)}, status=201)

    # PUT — update header fields
    try:
        fatura = FaturaHospitalar.objects.get(paciente=pac)
    except FaturaHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Fatura não encontrada"}, status=404)

    for field in ("convenio", "nome_convenio", "numero_carteirinha", "numero_guia", "observacoes"):
        if field in data:
            setattr(fatura, field, data[field])
    fatura.save()
    return JsonResponse({"ok": True, "fatura": _fatura_to_dict(fatura)})


@csrf_exempt
@require_http_methods(["POST"])
def api_fatura_acao(request, pac_id):
    """Transições de status: fechar, enviar, pagar, glosar, cancelar."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pac = PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
        fatura = FaturaHospitalar.objects.get(paciente=pac)
    except (PacienteInternado.DoesNotExist, FaturaHospitalar.DoesNotExist):
        return JsonResponse({"erro": "Fatura não encontrada"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao", "")
    agora = timezone.now()

    if acao == "fechar":
        fatura.recalcular_total()
        fatura.status = "fechada"
    elif acao == "enviar":
        fatura.status = "enviada"
        fatura.data_envio = agora
    elif acao == "pagar":
        fatura.status = "paga"
        fatura.data_pagamento = agora
        if "valor_pago" in data:
            fatura.valor_pago = Decimal(str(data["valor_pago"]))
    elif acao == "glosar":
        fatura.status = "glosada"
        if "valor_glosa" in data:
            fatura.valor_glosa = Decimal(str(data["valor_glosa"]))
    elif acao == "cancelar":
        fatura.status = "cancelada"
    else:
        return JsonResponse({"erro": "acao inválida. Use: fechar, enviar, pagar, glosar, cancelar"}, status=400)

    fatura.save()
    return JsonResponse({"ok": True, "fatura": _fatura_to_dict(fatura)})


# ─── Itens de Faturamento ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_itens_faturamento(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pac = PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
    except PacienteInternado.DoesNotExist:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        itens = ItemFaturamento.objects.filter(empresa=empresa, paciente=pac)
        return JsonResponse({"itens": [_item_to_dict(i) for i in itens]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    descricao = (data.get("descricao") or "").strip()
    valor_unit = data.get("valor_unitario")
    if not descricao or valor_unit is None:
        return JsonResponse({"erro": "descricao e valor_unitario são obrigatórios"}, status=400)

    try:
        valor_unit = Decimal(str(valor_unit))
        quantidade = Decimal(str(data.get("quantidade", 1)))
    except Exception:
        return JsonResponse({"erro": "Valores numéricos inválidos"}, status=400)

    # Associar à fatura aberta se existir
    fatura = None
    try:
        f = FaturaHospitalar.objects.get(paciente=pac)
        if f.status in ("rascunho", "fechada"):
            fatura = f
    except FaturaHospitalar.DoesNotExist:
        pass

    item = ItemFaturamento.objects.create(
        empresa=empresa,
        paciente=pac,
        fatura=fatura,
        tipo=data.get("tipo", "procedimento"),
        codigo_tuss=data.get("codigo_tuss", ""),
        codigo_cbhpm=data.get("codigo_cbhpm", ""),
        descricao=descricao,
        quantidade=quantidade,
        valor_unitario=valor_unit,
        valor_total=quantidade * valor_unit,
        observacao=data.get("observacao", ""),
    )

    # Recalcular total da fatura
    if fatura:
        fatura.recalcular_total()

    return JsonResponse({"ok": True, "item": _item_to_dict(item)}, status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_item_faturamento_detalhe(request, item_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        item = ItemFaturamento.objects.get(pk=item_id, empresa=empresa)
    except ItemFaturamento.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)

    fatura = item.fatura
    item.delete()
    if fatura:
        fatura.recalcular_total()
    return JsonResponse({"ok": True})


# ─── Dashboard de Faturamento ─────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_faturamento_dashboard(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    faturas = FaturaHospitalar.objects.filter(empresa=empresa)
    agg = faturas.aggregate(
        total_faturado=Sum("valor_total"),
        total_glosa=Sum("valor_glosa"),
        total_pago=Sum("valor_pago"),
    )

    rascunhos = faturas.filter(status="rascunho").count()
    enviadas  = faturas.filter(status="enviada").count()
    pagas     = faturas.filter(status="paga").count()
    glosadas  = faturas.filter(status="glosada").count()

    # Faturamento mensal últimos 6 meses
    hoje = timezone.now().date()
    mensal = []
    for i in range(5, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=i * 30)
        mes_inicio = ref.replace(day=1)
        if mes_inicio.month == 12:
            mes_fim = mes_inicio.replace(year=mes_inicio.year + 1, month=1, day=1)
        else:
            mes_fim = mes_inicio.replace(month=mes_inicio.month + 1, day=1)
        total = faturas.filter(
            criado_em__date__gte=mes_inicio,
            criado_em__date__lt=mes_fim,
        ).aggregate(t=Sum("valor_total"))["t"] or 0
        mensal.append({
            "mes": mes_inicio.strftime("%b/%Y"),
            "total": float(total),
        })

    # Últimas faturas
    ultimas = [_fatura_to_dict(f) for f in
               faturas.select_related("paciente").order_by("-criado_em")[:10]]

    return JsonResponse({
        "total_faturado": float(agg["total_faturado"] or 0),
        "total_glosa": float(agg["total_glosa"] or 0),
        "total_pago": float(agg["total_pago"] or 0),
        "total_liquido": float((agg["total_faturado"] or 0) - (agg["total_glosa"] or 0)),
        "rascunhos": rascunhos,
        "enviadas": enviadas,
        "pagas": pagas,
        "glosadas": glosadas,
        "faturamento_mensal": mensal,
        "ultimas_faturas": ultimas,
    })


# ─── Analytics Hospitalar ─────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_hospital_analytics(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    # ── Ocupação atual ─────────────────────────────────────────────────────
    leitos_totais   = LeitoHospitalar.objects.filter(empresa=empresa).count()
    leitos_ocupados = LeitoHospitalar.objects.filter(empresa=empresa, status="ocupado").count()
    taxa_ocupacao   = round(leitos_ocupados / leitos_totais * 100, 1) if leitos_totais else 0

    # ── Altas + ALOS ──────────────────────────────────────────────────────
    altas = SumarioAlta.objects.filter(paciente__empresa=empresa).select_related("paciente")
    total_altas = altas.count()

    alos_dias = None
    obitos = 0
    tipo_alta_counts = defaultdict(int)
    cid_counts = defaultdict(int)

    duracoes = []
    for a in altas:
        tipo_alta_counts[a.tipo_alta] += 1
        if a.tipo_alta == "obito":
            obitos += 1
        if a.cid_principal:
            cid_counts[a.cid_principal] += 1
        pac = a.paciente
        if pac.data_internacao:
            data_alta = _as_date(a.data_alta)
            data_internacao = _as_date(pac.data_internacao)
            if not data_alta or not data_internacao:
                continue
            delta = (data_alta - data_internacao).days
            if delta >= 0:
                duracoes.append(delta)

    if duracoes:
        alos_dias = round(sum(duracoes) / len(duracoes), 1)

    taxa_mortalidade = round(obitos / total_altas * 100, 1) if total_altas else 0

    # Top 10 CIDs
    top_cids = sorted(cid_counts.items(), key=lambda x: -x[1])[:10]

    # ── Readmissão em 30 dias ─────────────────────────────────────────────
    # Conta pacientes com >= 2 internações onde a 2ª ocorreu ≤ 30 dias após a 1ª alta
    readmissoes = 0
    pacs_com_multiplas = (
        PacienteInternado.objects.filter(empresa=empresa)
        .values("cpf")
        .annotate(n=Count("id"))
        .filter(n__gte=2)
    )
    for row in pacs_com_multiplas:
        internacoes = list(
            PacienteInternado.objects.filter(empresa=empresa, cpf=row["cpf"])
            .order_by("data_internacao")
        )
        for i in range(1, len(internacoes)):
            prev = internacoes[i - 1]
            curr = internacoes[i]
            try:
                alta_prev = _as_date(prev.sumario_alta.data_alta)
                data_atual = _as_date(curr.data_internacao)
                if alta_prev and data_atual and (data_atual - alta_prev).days <= 30:
                    readmissoes += 1
            except Exception:
                pass

    total_pac = PacienteInternado.objects.filter(empresa=empresa).values("cpf").distinct().count()
    taxa_readmissao = round(readmissoes / total_pac * 100, 1) if total_pac else 0

    # ── Cirurgias por porte ───────────────────────────────────────────────
    cirurgias_porte = list(
        CentroCirurgico.objects.filter(empresa=empresa, status="concluido")
        .values("porte")
        .annotate(n=Count("id"))
        .order_by("porte")
    )

    # ── Exames por tipo ───────────────────────────────────────────────────
    exames_tipo = list(
        PedidoExame.objects.filter(empresa=empresa)
        .values("tipo")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    # ── Internações mensais — últimos 6 meses ─────────────────────────────
    hoje = timezone.now().date()
    internacoes_mensal = []
    for i in range(5, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=i * 30)
        mes_inicio = ref.replace(day=1)
        if mes_inicio.month == 12:
            mes_fim = mes_inicio.replace(year=mes_inicio.year + 1, month=1, day=1)
        else:
            mes_fim = mes_inicio.replace(month=mes_inicio.month + 1, day=1)
        n = PacienteInternado.objects.filter(
            empresa=empresa,
            data_internacao__gte=mes_inicio,
            data_internacao__lt=mes_fim,
        ).count()
        internacoes_mensal.append({"mes": mes_inicio.strftime("%b/%Y"), "n": n})

    # ── Ticket médio por fatura paga ──────────────────────────────────────
    ticket_medio = FaturaHospitalar.objects.filter(
        empresa=empresa, status="paga"
    ).aggregate(tm=Avg("valor_pago"))["tm"] or 0

    return JsonResponse({
        "leitos_totais": leitos_totais,
        "leitos_ocupados": leitos_ocupados,
        "taxa_ocupacao": taxa_ocupacao,
        "total_altas": total_altas,
        "alos_dias": alos_dias,
        "obitos": obitos,
        "taxa_mortalidade": taxa_mortalidade,
        "readmissoes_30d": readmissoes,
        "taxa_readmissao_30d": taxa_readmissao,
        "tipo_alta_counts": dict(tipo_alta_counts),
        "top_cids": [{"cid": c, "n": n} for c, n in top_cids],
        "cirurgias_por_porte": cirurgias_porte,
        "exames_por_tipo": exames_tipo,
        "internacoes_mensal": internacoes_mensal,
        "ticket_medio_fatura": float(ticket_medio),
    })
