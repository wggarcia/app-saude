"""
Hospital — Fase 2: Pedidos de Exame + Resultados + Administração de Medicamentos
  • PedidoExame (lab, imagem, ECG, endoscopia)
  • ResultadoExame com interpretação e alerta crítico
  • AdministracaoMedicamento — registro dos 5 certos
  • Dashboard de exames pendentes e resultados críticos
  • Integração: prescrição hospitalar → checklist de administração
"""
import json
from datetime import datetime, date, time as dtime

from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .views_dashboard import _empresa_autenticada
from .models import (
    PacienteInternado, PrescricaoHospitalar,
    PedidoExame, ResultadoExame, AdministracaoMedicamento,
)


def _pac_or_404(empresa, pac_id):
    try:
        return PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
    except PacienteInternado.DoesNotExist:
        return None


def _pedido_to_dict(p):
    return {
        "id": p.id,
        "paciente_id": p.paciente_id,
        "paciente_nome": p.paciente.nome,
        "tipo": p.tipo,
        "exames": p.exames,
        "prioridade": p.prioridade,
        "status": p.status,
        "solicitante": p.solicitante,
        "solicitante_crm": p.solicitante_crm,
        "observacoes_clinicas": p.observacoes_clinicas,
        "jejum_horas": p.jejum_horas,
        "material": p.material,
        "data_solicitacao": p.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
        "data_coleta": p.data_coleta.strftime("%d/%m/%Y %H:%M") if p.data_coleta else None,
        "total_resultados": p.resultados.count(),
        "tem_critico": p.resultados.filter(interpretacao="critico").exists(),
    }


def _resultado_to_dict(r):
    return {
        "id": r.id,
        "pedido_id": r.pedido_id,
        "paciente_id": r.paciente_id,
        "paciente_nome": r.paciente.nome,
        "data_resultado": r.data_resultado.strftime("%d/%m/%Y %H:%M"),
        "resultados_json": r.resultados_json,
        "laudo": r.laudo,
        "interpretacao": r.interpretacao,
        "responsavel_laudo": r.responsavel_laudo,
        "crm_responsavel": r.crm_responsavel,
        "url_imagem": r.url_imagem,
        "visualizado_por": r.visualizado_por,
        "visualizado_em": r.visualizado_em.strftime("%d/%m/%Y %H:%M") if r.visualizado_em else None,
    }


def _adm_to_dict(a):
    return {
        "id": a.id,
        "prescricao_id": a.prescricao_id,
        "paciente_id": a.paciente_id,
        "paciente_nome": a.paciente.nome,
        "nome_medicamento": a.nome_medicamento,
        "dose": a.dose,
        "via": a.via,
        "horario_prescrito": a.horario_prescrito.strftime("%H:%M"),
        "horario_administrado": a.horario_administrado.strftime("%d/%m/%Y %H:%M") if a.horario_administrado else None,
        "status": a.status,
        "responsavel": a.responsavel,
        "coren": a.coren,
        "observacao": a.observacao,
        "criado_em": a.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Pedidos de Exame ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_pedidos_exame(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    if request.method == "GET":
        qs = PedidoExame.objects.filter(empresa=empresa).select_related("paciente")

        status = request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)

        tipo = request.GET.get("tipo", "")
        if tipo:
            qs = qs.filter(tipo=tipo)

        prioridade = request.GET.get("prioridade", "")
        if prioridade:
            qs = qs.filter(prioridade=prioridade)

        pac_id = request.GET.get("paciente_id", "")
        if pac_id:
            qs = qs.filter(paciente_id=pac_id)

        data_ini = request.GET.get("data_inicio", "")
        data_fim = request.GET.get("data_fim", "")
        if data_ini:
            qs = qs.filter(data_solicitacao__date__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_solicitacao__date__lte=data_fim)

        return JsonResponse({"pedidos": [_pedido_to_dict(p) for p in qs.prefetch_related("resultados")[:200]]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    pac_id = data.get("paciente_id")
    tipo = data.get("tipo")
    exames = data.get("exames", [])

    if not all([pac_id, tipo, exames]):
        return JsonResponse({"erro": "paciente_id, tipo e exames são obrigatórios"}, status=400)

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    presc_id = data.get("prescricao_id")
    presc = None
    if presc_id:
        try:
            presc = PrescricaoHospitalar.objects.get(pk=presc_id, empresa=empresa)
        except PrescricaoHospitalar.DoesNotExist:
            pass

    pedido = PedidoExame.objects.create(
        empresa=empresa,
        paciente=pac,
        prescricao=presc,
        tipo=tipo,
        exames=exames,
        prioridade=data.get("prioridade", "rotina"),
        solicitante=data.get("solicitante", ""),
        solicitante_crm=data.get("solicitante_crm", ""),
        observacoes_clinicas=data.get("observacoes_clinicas", ""),
        jejum_horas=data.get("jejum_horas"),
        material=data.get("material", ""),
    )
    return JsonResponse({"ok": True, "pedido": _pedido_to_dict(pedido)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def api_pedido_exame_detalhe(request, pedido_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pedido = PedidoExame.objects.select_related("paciente").prefetch_related("resultados").get(pk=pedido_id, empresa=empresa)
    except PedidoExame.DoesNotExist:
        return JsonResponse({"erro": "Pedido não encontrado"}, status=404)

    if request.method == "GET":
        d = _pedido_to_dict(pedido)
        d["resultados"] = [_resultado_to_dict(r) for r in pedido.resultados.all()]
        return JsonResponse({"pedido": d})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if "status" in data:
        pedido.status = data["status"]
        if data["status"] == "coletado" and not pedido.data_coleta:
            pedido.data_coleta = timezone.now()
    pedido.save()
    return JsonResponse({"ok": True, "pedido": _pedido_to_dict(pedido)})


# ─── Resultados de Exame ──────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_resultados_exame(request, pedido_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pedido = PedidoExame.objects.select_related("paciente").get(pk=pedido_id, empresa=empresa)
    except PedidoExame.DoesNotExist:
        return JsonResponse({"erro": "Pedido não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"resultados": [_resultado_to_dict(r) for r in pedido.resultados.all()]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    interpretacao = data.get("interpretacao", "pendente")
    resultado = ResultadoExame.objects.create(
        pedido=pedido,
        paciente=pedido.paciente,
        resultados_json=data.get("resultados_json", []),
        laudo=data.get("laudo", ""),
        interpretacao=interpretacao,
        responsavel_laudo=data.get("responsavel_laudo", ""),
        crm_responsavel=data.get("crm_responsavel", ""),
        url_imagem=data.get("url_imagem", ""),
    )

    # Atualizar status do pedido para concluído
    pedido.status = "concluido"
    if not pedido.data_coleta:
        pedido.data_coleta = timezone.now()
    pedido.save(update_fields=["status", "data_coleta", "atualizado_em"])

    return JsonResponse({"ok": True, "resultado": _resultado_to_dict(resultado)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
def api_resultado_visualizar(request, resultado_id):
    """Marca resultado como visualizado pelo médico."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        resultado = ResultadoExame.objects.select_related("paciente").get(pk=resultado_id, pedido__empresa=empresa)
    except ResultadoExame.DoesNotExist:
        return JsonResponse({"erro": "Resultado não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        data = {}

    resultado.visualizado_por = data.get("visualizado_por", "")
    resultado.visualizado_em = timezone.now()
    resultado.save(update_fields=["visualizado_por", "visualizado_em"])
    return JsonResponse({"ok": True})


# ─── Administração de Medicamentos ────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_administracoes(request, presc_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        presc = PrescricaoHospitalar.objects.select_related("paciente").get(pk=presc_id, empresa=empresa)
    except PrescricaoHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Prescrição não encontrada"}, status=404)

    if request.method == "GET":
        adms = presc.administracoes.select_related("paciente").all()
        return JsonResponse({"administracoes": [_adm_to_dict(a) for a in adms]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome_med = (data.get("nome_medicamento") or "").strip()
    horario_str = data.get("horario_prescrito", "")
    if not nome_med or not horario_str:
        return JsonResponse({"erro": "nome_medicamento e horario_prescrito são obrigatórios"}, status=400)

    try:
        horario = dtime.fromisoformat(horario_str)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "horario_prescrito inválido (HH:MM)"}, status=400)

    horario_adm = None
    h_adm_str = data.get("horario_administrado")
    if h_adm_str:
        try:
            horario_adm = datetime.fromisoformat(h_adm_str)
            if not horario_adm.tzinfo:
                horario_adm = timezone.make_aware(horario_adm)
        except (ValueError, TypeError):
            horario_adm = timezone.now()
    elif data.get("status", "administrado") == "administrado":
        horario_adm = timezone.now()

    adm = AdministracaoMedicamento.objects.create(
        prescricao=presc,
        paciente=presc.paciente,
        nome_medicamento=nome_med,
        dose=data.get("dose", ""),
        via=data.get("via", ""),
        horario_prescrito=horario,
        horario_administrado=horario_adm,
        status=data.get("status", "administrado"),
        responsavel=data.get("responsavel", ""),
        coren=data.get("coren", ""),
        observacao=data.get("observacao", ""),
    )
    return JsonResponse({"ok": True, "administracao": _adm_to_dict(adm)}, status=201)


# ─── Dashboard de Exames ──────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_exames_dashboard(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pendentes = PedidoExame.objects.filter(empresa=empresa, status="solicitado").count()
    coletados = PedidoExame.objects.filter(empresa=empresa, status="coletado").count()
    urgentes  = PedidoExame.objects.filter(empresa=empresa, status="solicitado", prioridade__in=["urgente", "emergencia"]).count()
    criticos  = ResultadoExame.objects.filter(pedido__empresa=empresa, interpretacao="critico", visualizado_em__isnull=True).count()

    # Últimos resultados críticos não visualizados
    alertas_criticos = []
    for r in ResultadoExame.objects.filter(
        pedido__empresa=empresa, interpretacao="critico", visualizado_em__isnull=True
    ).select_related("paciente", "pedido")[:10]:
        alertas_criticos.append({
            "resultado_id": r.id,
            "pedido_id": r.pedido_id,
            "paciente_nome": r.paciente.nome,
            "tipo_exame": r.pedido.tipo,
            "laudo": r.laudo[:200] if r.laudo else "",
            "data_resultado": r.data_resultado.strftime("%d/%m/%Y %H:%M"),
        })

    # Pedidos urgentes pendentes
    pedidos_urgentes = []
    for p in PedidoExame.objects.filter(
        empresa=empresa, status="solicitado", prioridade__in=["urgente", "emergencia"]
    ).select_related("paciente")[:10]:
        pedidos_urgentes.append({
            "id": p.id,
            "paciente_nome": p.paciente.nome,
            "tipo": p.tipo,
            "prioridade": p.prioridade,
            "exames": p.exames,
            "data_solicitacao": p.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
        })

    return JsonResponse({
        "pedidos_pendentes": pendentes,
        "pedidos_coletados": coletados,
        "pedidos_urgentes": urgentes,
        "resultados_criticos_nao_vistos": criticos,
        "alertas_criticos": alertas_criticos,
        "pedidos_urgentes_lista": pedidos_urgentes,
    })
