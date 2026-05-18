"""
Farmácia — Fase 1: Conformidade & Segurança
  • Livro de Registro Controlado (Portaria 344)
  • Recall / bloqueio de lote
  • Trilha de auditoria
"""
import json
from datetime import date, timedelta

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .views_dashboard import _empresa_autenticada
from .models import (
    LivroRegistroControlado, LoteMedicamento, MedicamentoFarmacia,
    FarmaciaAuditLog, Dispensacao,
)


def _get_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def _audit(empresa, acao, modelo, objeto_id, descricao, usuario="", ip="", dados_antes=None, dados_depois=None):
    FarmaciaAuditLog.objects.create(
        empresa=empresa,
        acao=acao,
        modelo=modelo,
        objeto_id=objeto_id,
        descricao=descricao,
        dados_antes=dados_antes,
        dados_depois=dados_depois,
        usuario=usuario,
        ip=ip,
    )


# ─── Livro de Registro Controlado ────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
def api_livro_controlado(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = LivroRegistroControlado.objects.filter(empresa=empresa).select_related("medicamento", "lote")

    med_id = request.GET.get("medicamento_id")
    if med_id:
        qs = qs.filter(medicamento_id=med_id)

    tipo = request.GET.get("tipo")
    if tipo:
        qs = qs.filter(tipo=tipo)

    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")
    if data_inicio:
        qs = qs.filter(data_operacao__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(data_operacao__date__lte=data_fim)

    registros = []
    for r in qs[:200]:
        registros.append({
            "id": r.id,
            "medicamento_id": r.medicamento_id,
            "medicamento_nome": r.medicamento.nome,
            "lista_portaria_344": r.medicamento.lista_portaria_344,
            "lote_numero": r.lote.numero_lote if r.lote else "",
            "tipo": r.tipo,
            "data_operacao": r.data_operacao.strftime("%d/%m/%Y %H:%M"),
            "quantidade": float(r.quantidade),
            "saldo_apos": float(r.saldo_apos),
            "paciente_nome": r.paciente_nome,
            "paciente_cpf": r.paciente_cpf,
            "prescricao_numero": r.prescricao_numero,
            "medico_crm": r.medico_crm,
            "responsavel": r.responsavel,
            "observacao": r.observacao,
        })

    return JsonResponse({"registros": registros})


# ─── Recall / Bloqueio de Lote ────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_lotes_bloqueio(request, lote_id=None):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    if request.method == "GET":
        qs = LoteMedicamento.objects.filter(empresa=empresa).select_related("item")
        apenas_bloqueados = request.GET.get("bloqueados") == "1"
        if apenas_bloqueados:
            qs = qs.filter(bloqueado=True)

        lotes = []
        for l in qs:
            lotes.append({
                "id": l.id,
                "numero_lote": l.numero_lote,
                "item_nome": l.item.nome if l.item else "",
                "data_validade": l.data_validade.strftime("%d/%m/%Y"),
                "quantidade_atual": float(l.quantidade_atual),
                "bloqueado": l.bloqueado,
                "motivo_bloqueio": l.motivo_bloqueio,
                "vencido": l.vencido,
                "dias_para_vencer": l.dias_para_vencer,
            })
        return JsonResponse({"lotes": lotes})

    # POST — bloquear ou desbloquear lote
    try:
        data = json.loads(request.body)
    except (ValueError, KeyError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    lote_id = lote_id or data.get("lote_id")
    if not lote_id:
        return JsonResponse({"erro": "lote_id obrigatório"}, status=400)

    try:
        lote = LoteMedicamento.objects.get(id=lote_id, empresa=empresa)
    except LoteMedicamento.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)

    acao_bloquear = data.get("bloquear", True)
    motivo = data.get("motivo", "").strip()

    dados_antes = {"bloqueado": lote.bloqueado, "motivo_bloqueio": lote.motivo_bloqueio}

    lote.bloqueado = acao_bloquear
    lote.motivo_bloqueio = motivo if acao_bloquear else ""
    lote.save(update_fields=["bloqueado", "motivo_bloqueio", "atualizado_em"])

    acao_str = "bloquear_lote" if acao_bloquear else "desbloquear_lote"
    _audit(
        empresa=empresa,
        acao=acao_str,
        modelo="LoteMedicamento",
        objeto_id=lote.id,
        descricao=f"Lote {lote.numero_lote} {'bloqueado' if acao_bloquear else 'desbloqueado'}. Motivo: {motivo}",
        ip=_get_ip(request),
        dados_antes=dados_antes,
        dados_depois={"bloqueado": lote.bloqueado, "motivo_bloqueio": lote.motivo_bloqueio},
    )

    return JsonResponse({"ok": True, "bloqueado": lote.bloqueado})


# ─── Auditoria ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_auditoria(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = FarmaciaAuditLog.objects.filter(empresa=empresa)

    acao = request.GET.get("acao")
    if acao:
        qs = qs.filter(acao=acao)

    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")
    if data_inicio:
        qs = qs.filter(criado_em__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(criado_em__date__lte=data_fim)

    logs = []
    for log in qs[:300]:
        logs.append({
            "id": log.id,
            "acao": log.acao,
            "modelo": log.modelo,
            "objeto_id": log.objeto_id,
            "descricao": log.descricao,
            "usuario": log.usuario,
            "ip": log.ip,
            "criado_em": log.criado_em.strftime("%d/%m/%Y %H:%M"),
            "dados_antes": log.dados_antes,
            "dados_depois": log.dados_depois,
        })

    return JsonResponse({"logs": logs})


# ─── Dashboard de conformidade ────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_conformidade(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = date.today()
    em_30_dias = hoje + timedelta(days=30)

    lotes_vencidos = LoteMedicamento.objects.filter(
        empresa=empresa, data_validade__lt=hoje, quantidade_atual__gt=0
    ).count()

    lotes_vencendo = LoteMedicamento.objects.filter(
        empresa=empresa, data_validade__range=(hoje, em_30_dias), quantidade_atual__gt=0
    ).count()

    lotes_bloqueados = LoteMedicamento.objects.filter(
        empresa=empresa, bloqueado=True, quantidade_atual__gt=0
    ).count()

    controlados_sem_lista = MedicamentoFarmacia.objects.filter(
        empresa=empresa, controlado=True, lista_portaria_344=""
    ).count()

    dispensacoes_controladas_sem_receita = Dispensacao.objects.filter(
        empresa=empresa, status="dispensada",
        medico_crm="",
    ).filter(
        medicamentos__contains=[{"controlado": True}]
    ).count()

    return JsonResponse({
        "lotes_vencidos": lotes_vencidos,
        "lotes_vencendo_30_dias": lotes_vencendo,
        "lotes_bloqueados": lotes_bloqueados,
        "controlados_sem_lista_344": controlados_sem_lista,
        "alertas_totais": lotes_vencidos + lotes_bloqueados + controlados_sem_lista,
    })
