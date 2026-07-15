"""
views_governo_teleconsulta.py
Teleconsulta governo — agendamento, sala médico (JaaS), sala paciente (TCLE + vídeo).
"""
import base64
import json
import logging
import time
import uuid

import jwt as pyjwt
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor,
    principal_pode_operacao_setorial,
    requer_operacao_page,
    requer_permissao_modulo,
    requer_setor,
)
from .models import TeleconsultaGoverno
from .views_dashboard import (
    _empresa_autenticada as _empresa_autenticada_base,
    contexto_navegacao_setorial,
)

logger = logging.getLogger(__name__)


# ── Auth helper ───────────────────────────────────────────────────────────────

def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Jitsi JaaS JWT ────────────────────────────────────────────────────────────

def _jaas_private_key():
    path = getattr(settings, "JITSI_PRIVATE_KEY_PATH", "")
    if path:
        try:
            with open(path) as f:
                return f.read()
        except OSError as exc:
            logger.error("Não foi possível ler JITSI_PRIVATE_KEY_PATH %s: %s", path, exc)
            return None
    b64 = getattr(settings, "JITSI_PRIVATE_KEY_B64", "")
    if b64:
        return base64.b64decode(b64).decode()
    return None


def _gerar_token_jitsi(nome, email, moderador, sala_jitsi):
    """Retorna dict com token JWT JaaS (RS256) ou modo dev (meet.jit.si público)."""
    app_id = getattr(settings, "JITSI_APP_ID", "")
    kid = getattr(settings, "JITSI_KID", "")
    private_key = _jaas_private_key()

    if not private_key or not app_id or not kid:
        return {
            "token": None,
            "domain": "meet.jit.si",
            "room": sala_jitsi,
            "link": f"https://meet.jit.si/{sala_jitsi}",
            "dev_mode": True,
        }

    jaas_room = f"{app_id}/{sala_jitsi}"
    agora = int(time.time())
    payload = {
        "iss": "chat",
        "aud": "jitsi",
        "iat": agora,
        "nbf": agora - 10,
        "exp": agora + 7200,
        "sub": app_id,
        "room": "*",
        "context": {
            "user": {
                "name": nome,
                "email": email,
                "avatar": "",
                "moderator": "true" if moderador else "false",
            },
            "features": {
                "livestreaming": "false",
                "recording": "false",
                "transcription": "false",
                "outbound-call": "false",
            },
        },
    }
    token = pyjwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})
    return {
        "token": token,
        "domain": "8x8.vc",
        "room": jaas_room,
        "link": f"https://8x8.vc/{jaas_room}?jwt={token}",
        "dev_mode": False,
    }


# ── Page views ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def governo_teleconsulta_page(request):
    return render(request, "governo_teleconsulta.html", contexto_navegacao_setorial(request, "governo"))


@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def teleconsulta_sala_medico(request, tc_id):
    empresa = _e(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/governo/teleconsulta/")
    tc = get_object_or_404(TeleconsultaGoverno, pk=tc_id, empresa=empresa)
    ctx = contexto_navegacao_setorial(request, "governo")
    ctx["tc"] = tc
    return render(request, "governo_teleconsulta_sala_medico.html", ctx)


def teleconsulta_sala_paciente(request, token):
    """Sala do paciente — sem autenticação."""
    tc = get_object_or_404(TeleconsultaGoverno, token_paciente=token)
    if tc.status == "cancelada":
        return render(request, "teleconsulta_sala_paciente.html", {"cancelada": True})
    return render(request, "teleconsulta_sala_paciente.html", {
        "tc": tc,
        "token": token,
        "tcle_aceito": tc.tcle_aceito_em is not None,
    })


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    from datetime import date
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    qs = TeleconsultaGoverno.objects.filter(empresa=e)
    return JsonResponse({
        "agendadas_hoje": qs.filter(data_hora__date=hoje, status="agendada").count(),
        "concluidas_mes": qs.filter(status="concluida", data_hora__date__gte=inicio_mes).count(),
        "em_curso": qs.filter(status="em_curso").count(),
        "total": qs.count(),
    })


# ── Lista ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_lista(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = TeleconsultaGoverno.objects.filter(empresa=e)
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    return JsonResponse({"teleconsultas": [_tc_dict(t) for t in qs[:200]]})


# ── Agendar ───────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_teleconsulta_agendar(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    sala_jitsi = uuid.uuid4().hex
    token_paciente = uuid.uuid4().hex[:32]
    tc = TeleconsultaGoverno.objects.create(
        empresa=e,
        paciente_nome=data.get("paciente_nome", ""),
        cns=data.get("cns", ""),
        profissional=data.get("profissional", ""),
        especialidade=data.get("especialidade", ""),
        data_hora=data.get("data_hora"),
        status="agendada",
        link_sala="",
        resumo="",
        sala_jitsi=sala_jitsi,
        token_paciente=token_paciente,
    )
    link_paciente = request.build_absolute_uri(f"/teleconsulta/paciente/{token_paciente}/")
    return JsonResponse({"id": tc.id, "link_paciente": link_paciente}, status=201)


# ── Atualizar ─────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_teleconsulta_atualizar(request, tc_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        tc = TeleconsultaGoverno.objects.get(pk=tc_id, empresa=e)
    except TeleconsultaGoverno.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    if "status" in data:
        tc.status = data["status"]
    if "resumo" in data:
        tc.resumo = data["resumo"]
    tc.save()
    return JsonResponse({"ok": True})


# ── Token Jitsi — médico ──────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_sala_token(request, tc_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    tc = get_object_or_404(TeleconsultaGoverno, pk=tc_id, empresa=e)
    if not tc.sala_jitsi:
        return JsonResponse({"erro": "Sala não configurada"}, status=400)
    if tc.status == "agendada":
        tc.status = "em_curso"
        tc.save(update_fields=["status"])
    resultado = _gerar_token_jitsi(
        nome=tc.profissional,
        email="",
        moderador=True,
        sala_jitsi=tc.sala_jitsi,
    )
    resultado["sala_jitsi"] = tc.sala_jitsi
    return JsonResponse(resultado)


# ── Token Jitsi — paciente ────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_paciente_token(request, token):
    tc = get_object_or_404(TeleconsultaGoverno, token_paciente=token)
    if tc.status not in ("em_curso", "agendada"):
        return JsonResponse({"erro": "Consulta não disponível"}, status=400)
    if not tc.tcle_aceito_em:
        return JsonResponse({"erro": "TCLE não aceito"}, status=403)
    resultado = _gerar_token_jitsi(
        nome=tc.paciente_nome or "Paciente",
        email="",
        moderador=False,
        sala_jitsi=tc.sala_jitsi,
    )
    resultado["sala_jitsi"] = tc.sala_jitsi
    resultado["status"] = tc.status
    return JsonResponse(resultado)


# ── Status — paciente (polling) ───────────────────────────────────────────────

@require_http_methods(["GET"])
def api_teleconsulta_paciente_status(request, token):
    tc = get_object_or_404(TeleconsultaGoverno, token_paciente=token)
    return JsonResponse({
        "status": tc.status,
        "tcle_aceito": tc.tcle_aceito_em is not None,
    })


# ── TCLE aceitar ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_teleconsulta_tcle_aceitar(request, token):
    tc = get_object_or_404(TeleconsultaGoverno, token_paciente=token)
    if tc.status == "cancelada":
        return JsonResponse({"erro": "Consulta cancelada"}, status=400)
    if not tc.tcle_aceito_em:
        tc.tcle_aceito_em = timezone.now()
        tc.save(update_fields=["tcle_aceito_em"])
    return JsonResponse({"ok": True})


# ── Encerrar (médico + CID-10) ────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_teleconsulta_encerrar(request, tc_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    tc = get_object_or_404(TeleconsultaGoverno, pk=tc_id, empresa=e)
    data = json.loads(request.body or "{}")
    tc.status = "concluida"
    tc.encerrado_em = timezone.now()
    if data.get("cid10"):
        tc.cid10 = data["cid10"].strip().upper()
    if data.get("resumo"):
        tc.resumo = data["resumo"]
    tc.save(update_fields=["status", "encerrado_em", "cid10", "resumo"])
    # Fase 2: feed sentinel layer do panorama epidemiológico
    if tc.cid10:
        _registrar_cid10_panorama(e, tc.cid10, tc.data_hora)
    return JsonResponse({"ok": True})


def _registrar_cid10_panorama(empresa, cid10, data_hora):
    """Registra diagnóstico confirmado anonimamente no panorama governo (Fase 2)."""
    try:
        from .epidemiologia import registrar_diagnostico_confirmado
        registrar_diagnostico_confirmado(empresa, cid10, data_hora)
    except Exception as exc:
        logger.warning("panorama sentinel layer não disponível: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tc_dict(t):
    link_paciente = (
        f"/teleconsulta/paciente/{t.token_paciente}/" if t.token_paciente else ""
    )
    return {
        "id": t.id,
        "paciente_nome": t.paciente_nome,
        "cns": t.cns,
        "profissional": t.profissional,
        "especialidade": t.especialidade,
        "data_hora": t.data_hora.isoformat(),
        "status": t.status,
        "status_label": t.get_status_display(),
        "link_sala": f"/governo/teleconsulta/{t.id}/sala/",
        "link_paciente": link_paciente,
        "resumo": t.resumo,
        "cid10": t.cid10,
        "criado_em": t.criado_em.isoformat(),
    }
