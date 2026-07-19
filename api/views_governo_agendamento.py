"""
views_governo_agendamento.py
Agendamento de consultas com automação WhatsApp para o segmento Governo/APS.
"""
import json
import logging
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    requer_setor,
    requer_operacao_page,
    requer_permissao_modulo,
    api_requer_permissao_modulo,
    get_setor,
    principal_pode_operacao_setorial,
)
from .views_dashboard import (
    _empresa_autenticada as _empresa_autenticada_base,
    contexto_navegacao_setorial,
)

try:
    from .models import AgendamentoUBS
except ImportError:
    AgendamentoUBS = None

try:
    from .whatsapp_service import WhatsAppService
except ImportError:
    WhatsAppService = None

logger = logging.getLogger(__name__)


# ── Auth helper ───────────────────────────────────────────────────────────────

def _gov(request):
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
@requer_permissao_modulo("governo.atencao_clinica")
def governo_agendamento_page(request):
    return render(
        request,
        "governo_agendamento.html",
        contexto_navegacao_setorial(request, "governo"),
    )


# ── GET /api/governo/agendamento/agenda ───────────────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["GET"])
def api_governo_agenda(request):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    qs = AgendamentoUBS.objects.filter(empresa=e)

    data_consulta = request.GET.get("data_consulta")
    if data_consulta:
        qs = qs.filter(data_consulta=data_consulta)

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    unidade = request.GET.get("unidade")
    if unidade:
        qs = qs.filter(unidade__icontains=unidade)

    agendamentos = [
        {
            "id": ag.id,
            "paciente_nome": ag.paciente_nome,
            "paciente_cpf": ag.paciente_cpf,
            "paciente_telefone": ag.paciente_telefone,
            "unidade": ag.unidade,
            "profissional": ag.profissional,
            "especialidade": ag.especialidade,
            "data_consulta": ag.data_consulta.isoformat(),
            "horario": ag.horario.strftime("%H:%M"),
            "tipo": ag.tipo,
            "status": ag.status,
            "confirmado_whatsapp": ag.confirmado_whatsapp,
            "lembrete_enviado": ag.lembrete_enviado,
            "observacoes": ag.observacoes,
            "criado_em": ag.criado_em.isoformat(),
        }
        for ag in qs
    ]
    return JsonResponse({"agendamentos": agendamentos, "total": len(agendamentos)})


# ── POST /api/governo/agendamento/agendar ─────────────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["POST"])
def api_governo_agendar(request):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    campos_obrigatorios = ["paciente_nome", "unidade", "data_consulta", "horario"]
    for campo in campos_obrigatorios:
        if not body.get(campo):
            return JsonResponse({"erro": f"Campo obrigatório ausente: {campo}"}, status=400)

    try:
        ag = AgendamentoUBS.objects.create(
            empresa=e,
            paciente_nome=body["paciente_nome"],
            paciente_cpf=body.get("paciente_cpf", ""),
            paciente_telefone=body.get("paciente_telefone", ""),
            unidade=body["unidade"],
            profissional=body.get("profissional", ""),
            especialidade=body.get("especialidade", ""),
            data_consulta=body["data_consulta"],
            horario=body["horario"],
            tipo=body.get("tipo", "consulta"),
            status="agendado",
            observacoes=body.get("observacoes", ""),
        )
    except Exception as exc:
        logger.exception("Erro ao criar agendamento UBS")
        return JsonResponse({"erro": str(exc)}, status=400)

    return JsonResponse({"id": ag.id, "ok": True}, status=201)


# ── GET /api/governo/agendamento/<ag_id> ──────────────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["GET"])
def api_governo_agendamento_detalhe(request, ag_id):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    ag = get_object_or_404(AgendamentoUBS, pk=ag_id, empresa=e)
    return JsonResponse(
        {
            "id": ag.id,
            "paciente_nome": ag.paciente_nome,
            "paciente_cpf": ag.paciente_cpf,
            "paciente_telefone": ag.paciente_telefone,
            "unidade": ag.unidade,
            "profissional": ag.profissional,
            "especialidade": ag.especialidade,
            "data_consulta": ag.data_consulta.isoformat(),
            "horario": ag.horario.strftime("%H:%M"),
            "tipo": ag.tipo,
            "status": ag.status,
            "confirmado_whatsapp": ag.confirmado_whatsapp,
            "data_confirmacao_whatsapp": (
                ag.data_confirmacao_whatsapp.isoformat()
                if ag.data_confirmacao_whatsapp
                else None
            ),
            "lembrete_enviado": ag.lembrete_enviado,
            "observacoes": ag.observacoes,
            "criado_em": ag.criado_em.isoformat(),
        }
    )


# ── POST /api/governo/agendamento/<ag_id>/confirmar ───────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["POST"])
def api_governo_agendamento_confirmar(request, ag_id):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    ag = get_object_or_404(AgendamentoUBS, pk=ag_id, empresa=e)
    ag.status = "confirmado"
    ag.confirmado_whatsapp = False
    ag.save(update_fields=["status", "confirmado_whatsapp"])
    return JsonResponse({"id": ag.id, "status": ag.status, "ok": True})


# ── POST /api/governo/agendamento/<ag_id>/cancelar ────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["POST"])
def api_governo_agendamento_cancelar(request, ag_id):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    ag = get_object_or_404(AgendamentoUBS, pk=ag_id, empresa=e)
    ag.status = "cancelado"
    ag.save(update_fields=["status"])
    return JsonResponse({"id": ag.id, "status": ag.status, "ok": True})


# ── POST /api/governo/agendamento/<ag_id>/realizar ────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["POST"])
def api_governo_agendamento_realizar(request, ag_id):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    ag = get_object_or_404(AgendamentoUBS, pk=ag_id, empresa=e)
    ag.status = "realizado"
    ag.save(update_fields=["status"])
    return JsonResponse({"id": ag.id, "status": ag.status, "ok": True})


# ── POST /api/governo/agendamento/enviar-lembretes ────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["POST"])
def api_governo_enviar_lembretes(request):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    amanha = date.today() + timedelta(days=1)
    pendentes = AgendamentoUBS.objects.filter(
        empresa=e,
        data_consulta=amanha,
        lembrete_enviado=False,
        status__in=["agendado", "confirmado"],
    )

    enviados = 0
    erros = []

    for ag in pendentes:
        numero = ag.paciente_telefone
        if not numero:
            erros.append({"id": ag.id, "motivo": "Telefone não cadastrado"})
            continue

        mensagem = (
            f"Olá {ag.paciente_nome}, seu atendimento está agendado para amanhã às "
            f"{ag.horario.strftime('%H:%M')} na {ag.unidade}. "
            f"Responda SIM para confirmar ou NÃO para cancelar."
        )

        if WhatsAppService is not None:
            try:
                from .models import ConfiguracaoWhatsApp
                cfg = ConfiguracaoWhatsApp.objects.filter(empresa=e).first()
                if cfg:
                    svc = WhatsAppService(cfg)
                    ok, erro = svc.enviar(numero, mensagem)
                    if ok:
                        ag.lembrete_enviado = True
                        ag.save(update_fields=["lembrete_enviado"])
                        enviados += 1
                    else:
                        erros.append({"id": ag.id, "motivo": erro or "Falha ao enviar"})
                else:
                    erros.append({"id": ag.id, "motivo": "Configuração WhatsApp não encontrada"})
            except Exception as exc:
                logger.exception("Erro ao enviar lembrete WhatsApp para agendamento %s", ag.id)
                erros.append({"id": ag.id, "motivo": str(exc)})
        else:
            # WhatsApp indisponível — marca como enviado para não reprocessar
            logger.warning(
                "WhatsAppService indisponível; lembrete não enviado para agendamento %s", ag.id
            )
            erros.append({"id": ag.id, "motivo": "WhatsAppService indisponível"})

    return JsonResponse(
        {
            "ok": True,
            "data_lembrete": amanha.isoformat(),
            "enviados": enviados,
            "erros": erros,
            "total_processado": enviados + len(erros),
        }
    )


# ── GET /api/governo/agendamento/kpis ─────────────────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["GET"])
def api_governo_agendamento_kpis(request):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    qs = AgendamentoUBS.objects.filter(empresa=e, data_consulta__gte=inicio_mes)

    agendados = qs.filter(status="agendado").count()
    confirmados = qs.filter(status="confirmado").count()
    cancelados = qs.filter(status="cancelado").count()
    faltou = qs.filter(status="faltou").count()
    realizados = qs.filter(status="realizado").count()
    total = qs.count()

    return JsonResponse(
        {
            "mes_referencia": inicio_mes.isoformat(),
            "agendados": agendados,
            "confirmados": confirmados,
            "cancelados": cancelados,
            "faltou": faltou,
            "realizados": realizados,
            "total": total,
        }
    )


# ── GET /api/governo/agendamento/disponibilidade ──────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica")
@require_http_methods(["GET"])
def api_governo_agendamento_disponibilidade(request):
    e = _gov(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if AgendamentoUBS is None:
        return JsonResponse({"erro": "Modelo indisponível"}, status=503)

    unidade = request.GET.get("unidade", "")
    profissional = request.GET.get("profissional", "")
    data_str = request.GET.get("data", "")

    if not data_str:
        return JsonResponse({"erro": "Parâmetro 'data' obrigatório (YYYY-MM-DD)"}, status=400)

    qs = AgendamentoUBS.objects.filter(
        empresa=e,
        data_consulta=data_str,
        status__in=["agendado", "confirmado"],
    )

    if unidade:
        qs = qs.filter(unidade__icontains=unidade)
    if profissional:
        qs = qs.filter(profissional__icontains=profissional)

    ocupados = list(qs.values_list("horario", flat=True))
    horarios_ocupados = [h.strftime("%H:%M") for h in ocupados]

    # Grade padrão APS: 07h–17h em intervalos de 30 min
    from datetime import time as dtime

    grade = []
    hora = 7
    minuto = 0
    while hora < 17:
        slot = dtime(hora, minuto).strftime("%H:%M")
        grade.append(
            {
                "horario": slot,
                "disponivel": slot not in horarios_ocupados,
            }
        )
        minuto += 30
        if minuto >= 60:
            minuto = 0
            hora += 1

    return JsonResponse(
        {
            "data": data_str,
            "unidade": unidade,
            "profissional": profissional,
            "grade": grade,
            "ocupados": len(horarios_ocupados),
            "livres": sum(1 for s in grade if s["disponivel"]),
        }
    )
