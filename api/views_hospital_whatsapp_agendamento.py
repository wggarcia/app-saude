"""
WhatsApp Automação — Agendamentos Hospitalares
Integra com Meta Cloud API para envio automático de lembretes e confirmações.

GET  /api/hospital/whatsapp-agendamento/status            Status do serviço
POST /api/hospital/whatsapp-agendamento/enviar-lembrete   Envia lembrete de internação/consulta
POST /api/hospital/whatsapp-agendamento/confirmar-via-wa  Processa resposta de confirmação
GET  /api/hospital/whatsapp-agendamento/historico         Histórico de mensagens enviadas
POST /api/hospital/whatsapp-agendamento/webhook           Webhook Meta Cloud API
GET  /api/hospital/whatsapp-agendamento/kpis              KPIs de envio
"""
import json
import logging
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _get_wa_config():
    """Retorna (token_wa, phone_id_wa) das settings ou env."""
    import os
    token_wa = None
    phone_id_wa = None
    try:
        from django.conf import settings
        token_wa = getattr(settings, "SOLUS_WA_TOKEN", None)
        phone_id_wa = getattr(settings, "SOLUS_WA_PHONE_ID", None)
    except Exception:
        pass
    if not token_wa:
        token_wa = os.environ.get("SOLUS_WA_TOKEN")
    if not phone_id_wa:
        phone_id_wa = os.environ.get("SOLUS_WA_PHONE_ID")
    return token_wa, phone_id_wa


def _enviar_whatsapp(telefone, mensagem, token_wa, phone_id_wa):
    """Envia mensagem via Meta Cloud API. Retorna (sucesso, resposta_dict)."""
    import urllib.request
    if not token_wa or not phone_id_wa:
        return False, {"erro": "WhatsApp não configurado", "simulado": True}
    telefone_limpo = "".join(c for c in telefone if c.isdigit())
    if not telefone_limpo.startswith("55"):
        telefone_limpo = "55" + telefone_limpo
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": telefone_limpo,
        "type": "text",
        "text": {"body": mensagem}
    }).encode()
    req = urllib.request.Request(
        f"https://graph.facebook.com/v19.0/{phone_id_wa}/messages",
        data=payload,
        headers={
            "Authorization": f"Bearer {token_wa}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True, json.loads(resp.read())
    except Exception as e:
        return False, {"erro": str(e)}


def _montar_mensagem(tipo, paciente_nome, data, horario, setor, observacoes=""):
    """Monta mensagem personalizada por tipo de agendamento."""
    nome = paciente_nome or "Paciente"
    if tipo == "internacao":
        msg = (
            f"Olá {nome}! Sua internação está agendada para {data} às {horario} "
            f"no setor {setor}. Lembre de trazer documentos e exames. "
            f"Confirme respondendo SIM."
        )
    elif tipo == "cirurgia":
        msg = (
            f"Olá {nome}! Sua cirurgia está agendada para {data} às {horario} "
            f"no {setor}. JEJUM A PARTIR DE MEIA-NOITE. Confirme respondendo SIM."
        )
    else:
        # consulta (padrão)
        msg = (
            f"Olá {nome}! Sua consulta está agendada para {data} às {horario}. "
            f"Responda SIM para confirmar ou NÃO para cancelar."
        )
    if observacoes:
        msg += f" Obs: {observacoes}"
    return msg


def _salvar_log(emp, telefone, mensagem, tipo, enviado, simulado):
    """Tenta salvar log em LogMensagemWhatsApp, ignora silenciosamente se model não existir."""
    try:
        from .models import LogMensagemWhatsApp
        LogMensagemWhatsApp.objects.create(
            empresa=emp,
            telefone=telefone,
            mensagem=mensagem,
            tipo=tipo,
            enviado=enviado,
            simulado=simulado,
            criado_em=timezone.now(),
        )
    except Exception:
        pass


# ── Status do serviço WhatsApp ────────────────────────────────────────────────

def api_hosp_wa_status(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    token_wa, phone_id_wa = _get_wa_config()
    configurado = bool(token_wa and phone_id_wa)

    return JsonResponse({
        "configurado": configurado,
        "phone_id": phone_id_wa if configurado else None,
        "modo": "producao" if configurado else "simulado",
        "aviso": None if configurado else "Configure SOLUS_WA_TOKEN e SOLUS_WA_PHONE_ID para habilitar envios reais",
    })


# ── Enviar lembrete de agendamento ────────────────────────────────────────────

@csrf_exempt
def api_hosp_wa_enviar_lembrete(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    tipo = body.get("tipo", "consulta")
    paciente_nome = body.get("paciente_nome", "")
    telefone = body.get("telefone", "")
    data = body.get("data", "")
    horario = body.get("horario", "")
    setor = body.get("setor", "")
    observacoes = body.get("observacoes", "")

    if not telefone:
        return JsonResponse({"erro": "telefone é obrigatório"}, status=400)
    if not data or not horario:
        return JsonResponse({"erro": "data e horario são obrigatórios"}, status=400)

    mensagem = _montar_mensagem(tipo, paciente_nome, data, horario, setor, observacoes)
    token_wa, phone_id_wa = _get_wa_config()
    enviado, resposta = _enviar_whatsapp(telefone, mensagem, token_wa, phone_id_wa)
    simulado = resposta.get("simulado", False) or not bool(token_wa and phone_id_wa)

    _salvar_log(emp, telefone, mensagem, tipo, enviado, simulado)

    logger.info(
        "WhatsApp lembrete %s | hospital=%s | enviado=%s | simulado=%s",
        tipo, emp.pk, enviado, simulado,
    )

    return JsonResponse({
        "enviado": enviado or simulado,
        "simulado": simulado,
        "mensagem_enviada": mensagem,
        "telefone": telefone,
        "tipo": tipo,
        "resposta_api": resposta if not simulado else None,
    })


# ── Processar resposta de confirmação ─────────────────────────────────────────

@csrf_exempt
def api_hosp_wa_confirmar(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    telefone = body.get("telefone", "")
    resposta_raw = (body.get("resposta") or "").strip().upper()

    if resposta_raw in ("SIM", "S", "1", "CONFIRMO", "OK"):
        acao = "confirmado"
    elif resposta_raw in ("NAO", "NÃO", "N", "0", "CANCELO", "CANCELAR"):
        acao = "cancelado"
    else:
        acao = "ignorado"

    logger.info(
        "WhatsApp confirmação | hospital=%s | telefone=%s | acao=%s",
        emp.pk, telefone, acao,
    )

    return JsonResponse({
        "processado": True,
        "acao": acao,
        "telefone": telefone,
    })


# ── Histórico de mensagens enviadas ──────────────────────────────────────────

def api_hosp_wa_historico(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    tipo_filtro = request.GET.get("tipo")
    data_inicio = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")

    try:
        from .models import LogMensagemWhatsApp
        qs = LogMensagemWhatsApp.objects.filter(empresa=emp).order_by("-criado_em")
        if tipo_filtro:
            qs = qs.filter(tipo=tipo_filtro)
        if data_inicio:
            qs = qs.filter(criado_em__date__gte=data_inicio)
        if data_fim:
            qs = qs.filter(criado_em__date__lte=data_fim)

        mensagens = list(qs.values(
            "id", "telefone", "mensagem", "tipo", "enviado", "simulado", "criado_em"
        )[:200])
        return JsonResponse({"mensagens": mensagens, "total": len(mensagens)})
    except Exception:
        return JsonResponse({
            "mensagens": [],
            "total": 0,
            "aviso": "Histórico disponível após primeira mensagem enviada",
        })


# ── Webhook Meta Cloud API ────────────────────────────────────────────────────

@csrf_exempt
def api_hosp_wa_webhook(request):
    # GET: verificação do webhook pela Meta
    if request.method == "GET":
        import os
        verify_token_esperado = os.environ.get("SOLUS_WA_VERIFY_TOKEN", "soluscrt-webhook")
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and token == verify_token_esperado:
            from django.http import HttpResponse
            return HttpResponse(challenge, content_type="text/plain")
        return JsonResponse({"erro": "Verificação falhou"}, status=403)

    # POST: notificações de entrega/leitura/resposta da Meta
    if request.method == "POST":
        try:
            payload = json.loads(request.body)
            logger.info("WhatsApp webhook recebido: %s", json.dumps(payload)[:500])
        except Exception:
            pass
        # Retorna 200 OK para a Meta (obrigatório)
        return JsonResponse({"status": "ok"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── KPIs de envio ─────────────────────────────────────────────────────────────

def api_hosp_wa_kpis(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    token_wa, phone_id_wa = _get_wa_config()
    simulado = not bool(token_wa and phone_id_wa)

    hoje = timezone.now().date()

    try:
        from .models import LogMensagemWhatsApp
        qs_hoje = LogMensagemWhatsApp.objects.filter(empresa=emp, criado_em__date=hoje)
        enviados_hoje = qs_hoje.filter(enviado=True).count()
        confirmados_hoje = qs_hoje.filter(acao="confirmado").count() if hasattr(LogMensagemWhatsApp, "acao") else 0
        cancelados_hoje = qs_hoje.filter(acao="cancelado").count() if hasattr(LogMensagemWhatsApp, "acao") else 0
        taxa = f"{int(confirmados_hoje / enviados_hoje * 100)}%" if enviados_hoje else "0%"
    except Exception:
        enviados_hoje = 0
        confirmados_hoje = 0
        cancelados_hoje = 0
        taxa = "0%"

    return JsonResponse({
        "enviados_hoje": enviados_hoje,
        "confirmados_hoje": confirmados_hoje,
        "cancelados_hoje": cancelados_hoje,
        "taxa_confirmacao": taxa,
        "simulado": simulado,
    })
