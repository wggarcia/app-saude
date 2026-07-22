"""
Views for SST scheduling (AgendamentoSST).
Provides full CRUD + calendar/agenda view with status management.
"""
import json
import logging
from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import AgendamentoSST, ASOOcupacional, FuncionarioSST
from .views_dashboard import _empresa_autenticada
from .access_control import api_requer_feature, get_setor

logger = logging.getLogger(__name__)

# Mapeamento AgendamentoSST.tipo → ASOOcupacional.tipo
_TIPO_AGENDAMENTO_PARA_ASO = {
    "exame_admissional": "admissional",
    "exame_periodico":   "periodico",
    "exame_retorno":     "retorno_trabalho",
    "exame_demissional": "demissional",
    "exame_mudanca":     "mudanca_risco",
}


def _auto_gerar_aso(ag):
    """
    Cria um ASOOcupacional vinculado ao agendamento, se ainda não existir.
    Só é acionado para tipos de exame ocupacional (não consulta, treinamento, outro).
    Retorna o ASO criado, o ASO já existente, ou None se o tipo não gera ASO.
    """
    tipo_aso = _TIPO_AGENDAMENTO_PARA_ASO.get(ag.tipo)
    if not tipo_aso:
        return None  # consulta / treinamento / outro — não gera ASO automático

    # Idempotente: se já existe um ASO vinculado a este agendamento, não cria outro.
    # Usamos try/except pois o acesso ao reverse OneToOneField levanta
    # RelatedObjectDoesNotExist quando não há registro relacionado.
    try:
        return ag.aso_gerado  # já existe — devolve sem criar novo
    except Exception:
        pass  # não existe ainda — segue para criação

    data_exame = ag.data_hora.date()
    aso = ASOOcupacional.objects.create(
        empresa=ag.empresa,
        funcionario=ag.funcionario,
        agendamento_origem=ag,
        tipo=tipo_aso,
        data_emissao=data_exame,
        medico_responsavel=ag.medico,
        resultado="apto",  # pré-preenchido; médico deve confirmar/ajustar
        observacoes=(
            f"ASO gerado automaticamente a partir do agendamento #{ag.id}. "
            f"{ag.observacoes}".strip()
        ),
    )
    logger.info(
        "ASO id=%s gerado automaticamente para agendamento id=%s (funcionario=%s)",
        aso.id, ag.id, ag.funcionario_id,
    )
    return aso


def _agenda_to_dict(a):
    aso_id = None
    try:
        # OneToOneField reverso: levanta RelatedObjectDoesNotExist (subclasse de
        # AttributeError) quando não há ASO vinculado.
        aso_id = a.aso_gerado.id
    except Exception:
        pass
    return {
        "id": a.id,
        "funcionario_id": a.funcionario_id,
        "funcionario_nome": a.funcionario.nome,
        "funcionario_cargo": a.funcionario.cargo or "",
        "tipo": a.tipo,
        "tipo_label": a.get_tipo_display(),
        "status": a.status,
        "status_label": a.get_status_display(),
        "data_hora": a.data_hora.strftime("%Y-%m-%dT%H:%M"),
        "data_exib": a.data_hora.strftime("%d/%m/%Y %H:%M"),
        "local": a.local,
        "medico": a.medico,
        "observacoes": a.observacoes,
        "criado_em": a.criado_em.strftime("%d/%m/%Y"),
        "aso_gerado_id": aso_id,
    }


@csrf_exempt
@api_requer_feature("sst.agenda_medica")
def api_agendamentos_sst(request):
    """GET list / POST create agendamentos."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "empresa":
        return JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)

    if request.method == "GET":
        qs = AgendamentoSST.objects.filter(empresa=empresa).select_related("funcionario")

        # filters
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)

        tipo_f = request.GET.get("tipo")
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)

        func_id = request.GET.get("funcionario_id")
        if func_id:
            qs = qs.filter(funcionario_id=func_id)

        # date range (default: next 60 days + last 30 days)
        data_ini = request.GET.get("data_ini")
        data_fim = request.GET.get("data_fim")
        if data_ini:
            qs = qs.filter(data_hora__date__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_hora__date__lte=data_fim)

        # upcoming this week
        semana = request.GET.get("semana")
        if semana:
            hoje = date.today()
            fim_semana = hoje + timedelta(days=7)
            qs = qs.filter(data_hora__date__gte=hoje, data_hora__date__lte=fim_semana)

        return JsonResponse({"agendamentos": [_agenda_to_dict(a) for a in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        func_id = data.get("funcionario_id")
        if not func_id:
            return JsonResponse({"erro": "funcionario_id obrigatório"}, status=400)
        try:
            func = FuncionarioSST.objects.get(id=func_id, empresa=empresa)
        except FuncionarioSST.DoesNotExist:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

        data_hora_str = data.get("data_hora")
        if not data_hora_str:
            return JsonResponse({"erro": "data_hora obrigatório"}, status=400)
        try:
            data_hora = datetime.strptime(data_hora_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            return JsonResponse({"erro": "Formato de data inválido (use YYYY-MM-DDTHH:MM)"}, status=400)

        ag = AgendamentoSST.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo=data.get("tipo", "exame_periodico"),
            status="agendado",
            data_hora=data_hora,
            local=data.get("local", ""),
            medico=data.get("medico", ""),
            observacoes=data.get("observacoes", ""),
        )

        # notificação no app do funcionário
        try:
            from .models import NotificacaoFuncionario
            tipo_label = ag.get_tipo_display() if hasattr(ag, "get_tipo_display") else ag.tipo
            data_fmt = data_hora.strftime("%d/%m/%Y às %H:%M")
            local_txt = f" — {ag.local}" if ag.local else ""
            NotificacaoFuncionario.objects.create(
                funcionario=func,
                empresa=empresa,
                tipo="aso",
                titulo=f"Agendamento: {tipo_label}",
                mensagem=f"Você tem um exame agendado para {data_fmt}{local_txt}. {ag.observacoes or ''}".strip(),
                referencia_id=ag.id,
            )
        except Exception:
            logger.warning("Falha ao enviar notificação de agendamento SST", exc_info=True)

        return JsonResponse({"agendamento": _agenda_to_dict(ag)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
@api_requer_feature("sst.agenda_medica")
def api_agendamento_sst_detalhe(request, ag_id):
    """GET / PUT / DELETE single agendamento."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "empresa":
        return JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)

    try:
        ag = AgendamentoSST.objects.get(id=ag_id, empresa=empresa)
    except AgendamentoSST.DoesNotExist:
        return JsonResponse({"erro": "Agendamento não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"agendamento": _agenda_to_dict(ag)})

    elif request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        status_anterior = ag.status
        for field in ("tipo", "status", "local", "medico", "observacoes"):
            if field in data:
                setattr(ag, field, data[field])
        if "data_hora" in data:
            try:
                ag.data_hora = datetime.strptime(data["data_hora"], "%Y-%m-%dT%H:%M")
            except ValueError:
                return JsonResponse({"erro": "Formato de data inválido"}, status=400)
        ag.save()

        # ── Auto-gera ASO quando agendamento transita para "realizado" ────────
        aso_gerado = None
        if ag.status == "realizado" and status_anterior != "realizado":
            try:
                aso_gerado = _auto_gerar_aso(ag)
            except Exception:
                logger.error(
                    "Falha ao gerar ASO automático para agendamento id=%s", ag.id, exc_info=True
                )

        resp = {"agendamento": _agenda_to_dict(ag)}
        if aso_gerado is not None:
            resp["aso_gerado"] = {"id": aso_gerado.id, "tipo": aso_gerado.tipo}
        return JsonResponse(resp)

    elif request.method == "DELETE":
        ag.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
@api_requer_feature("sst.agenda_medica")
def api_agendamentos_sst_kpis(request):
    """KPIs for the scheduling dashboard."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "empresa":
        return JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)

    hoje = date.today()
    fim_semana = hoje + timedelta(days=7)
    fim_mes = hoje + timedelta(days=30)

    qs = AgendamentoSST.objects.filter(empresa=empresa)
    total = qs.count()
    agendados = qs.filter(status="agendado").count()
    confirmados = qs.filter(status="confirmado").count()
    realizados_mes = qs.filter(status="realizado", data_hora__date__gte=hoje - timedelta(days=30)).count()
    faltou_mes = qs.filter(status="faltou", data_hora__date__gte=hoje - timedelta(days=30)).count()
    proxima_semana = qs.filter(
        status__in=["agendado", "confirmado"],
        data_hora__date__gte=hoje,
        data_hora__date__lte=fim_semana,
    ).count()
    proximo_mes = qs.filter(
        status__in=["agendado", "confirmado"],
        data_hora__date__gte=hoje,
        data_hora__date__lte=fim_mes,
    ).count()

    # próximos agendamentos (até 10)
    proximos = qs.filter(
        status__in=["agendado", "confirmado"],
        data_hora__date__gte=hoje,
    ).select_related("funcionario").order_by("data_hora")[:10]

    # atrasados (deveriam ter sido realizados mas não foram)
    atrasados = qs.filter(
        status__in=["agendado", "confirmado"],
        data_hora__date__lt=hoje,
    ).select_related("funcionario").order_by("data_hora")[:10]

    return JsonResponse({
        "kpis": {
            "total": total,
            "agendados": agendados,
            "confirmados": confirmados,
            "realizados_mes": realizados_mes,
            "faltou_mes": faltou_mes,
            "proxima_semana": proxima_semana,
            "proximo_mes": proximo_mes,
        },
        "proximos": [_agenda_to_dict(a) for a in proximos],
        "atrasados": [_agenda_to_dict(a) for a in atrasados],
    })
