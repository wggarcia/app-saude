"""
views_governo_reuniao.py
Ambiente B — Reuniões institucionais para gestores de saúde.
Jitsi JaaS + pauta + notas em tempo real + ata gerada por IA (Anthropic Claude).
Completamente separado do módulo de teleconsulta clínica (Ambiente A).
"""
import base64
import json
import logging
import time

import jwt as pyjwt
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    contexto_navegacao_setorial,
    get_setor,
    principal_pode_operacao_setorial,
    requer_operacao_page,
    requer_permissao_modulo,
    requer_setor,
)
from .models import ReuniaoGoverno
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base

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


def _gerar_token_jitsi_reuniao(nome, sala_jitsi, moderador=True):
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
        "exp": agora + 14400,
        "sub": app_id,
        "room": "*",
        "context": {
            "user": {
                "name": nome,
                "email": "",
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
@requer_permissao_modulo("governo.atencao_clinica", "governo.secretaria_agendamento", "governo.administrativo")
def governo_reuniao_page(request):
    return render(request, "governo_reuniao.html", contexto_navegacao_setorial(request, "governo"))


@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica", "governo.secretaria_agendamento", "governo.administrativo")
def governo_reuniao_sala(request, reuniao_id):
    empresa = _e(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/governo/reuniao/")
    reuniao = get_object_or_404(ReuniaoGoverno, pk=reuniao_id, empresa=empresa)
    ctx = contexto_navegacao_setorial(request, "governo")
    ctx["reuniao"] = reuniao
    return render(request, "governo_reuniao_sala.html", ctx)


# ── CRUD API ──────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_reuniao_gov_lista(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = ReuniaoGoverno.objects.filter(empresa=e)
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    return JsonResponse({"reunioes": [_r_dict(r) for r in qs[:100]]})


@require_http_methods(["POST"])
def api_reuniao_gov_criar(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    if not data.get("titulo") or not data.get("data_hora"):
        return JsonResponse({"erro": "titulo e data_hora são obrigatórios"}, status=400)
    reuniao = ReuniaoGoverno.objects.create(
        empresa=e,
        titulo=data["titulo"],
        descricao=data.get("descricao", ""),
        data_hora=data["data_hora"],
        duracao_minutos=int(data.get("duracao_minutos", 60)),
        participantes_nomes=data.get("participantes_nomes", ""),
        pauta=data.get("pauta", ""),
        status="agendada",
    )
    return JsonResponse({"id": reuniao.id, "sala_url": f"/governo/reuniao/{reuniao.id}/sala/"}, status=201)


@require_http_methods(["POST"])
def api_reuniao_gov_atualizar(request, reuniao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    reuniao = get_object_or_404(ReuniaoGoverno, pk=reuniao_id, empresa=e)
    data = json.loads(request.body or "{}")
    campos = ["titulo", "descricao", "data_hora", "duracao_minutos", "participantes_nomes", "pauta", "status"]
    for campo in campos:
        if campo in data:
            setattr(reuniao, campo, data[campo])
    reuniao.save()
    return JsonResponse({"ok": True})


# ── Token Jitsi ───────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_reuniao_gov_token(request, reuniao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    reuniao = get_object_or_404(ReuniaoGoverno, pk=reuniao_id, empresa=e)
    if reuniao.status == "agendada":
        reuniao.status = "em_andamento"
        reuniao.save(update_fields=["status"])
    resultado = _gerar_token_jitsi_reuniao(
        nome=e.nome,
        sala_jitsi=reuniao.sala_jitsi,
        moderador=True,
    )
    resultado["sala_jitsi"] = reuniao.sala_jitsi
    resultado["titulo"] = reuniao.titulo
    return JsonResponse(resultado)


# ── Notas em tempo real ───────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_reuniao_gov_salvar_notas(request, reuniao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    reuniao = get_object_or_404(ReuniaoGoverno, pk=reuniao_id, empresa=e)
    data = json.loads(request.body or "{}")
    if "notas" in data:
        reuniao.notas = data["notas"]
        reuniao.save(update_fields=["notas"])
    return JsonResponse({"ok": True})


# ── Encerrar + gerar ata IA ───────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_reuniao_gov_encerrar(request, reuniao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    reuniao = get_object_or_404(ReuniaoGoverno, pk=reuniao_id, empresa=e)
    data = json.loads(request.body or "{}")
    if "notas" in data:
        reuniao.notas = data["notas"]
    reuniao.status = "encerrada"
    reuniao.save(update_fields=["status", "notas"])

    ata = _gerar_ata_ia(reuniao, e)
    if ata:
        reuniao.ata = ata
        reuniao.ata_gerada_em = timezone.now()
        reuniao.save(update_fields=["ata", "ata_gerada_em"])

    return JsonResponse({"ok": True, "ata": reuniao.ata})


@require_http_methods(["GET"])
def api_reuniao_gov_ata(request, reuniao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    reuniao = get_object_or_404(ReuniaoGoverno, pk=reuniao_id, empresa=e)
    return JsonResponse({
        "ata": reuniao.ata,
        "ata_gerada_em": reuniao.ata_gerada_em.isoformat() if reuniao.ata_gerada_em else None,
    })


# ── IA — Ata de reunião ───────────────────────────────────────────────────────

def _gerar_ata_ia(reuniao, empresa):
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return _ata_fallback(reuniao)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        situacao_epi = _resumo_situacao_epi(empresa)

        prompt = f"""Você é secretário(a) de reunião de uma Secretaria Municipal de Saúde brasileira.
Gere uma **Ata de Reunião** formal, profissional e completa em português brasileiro.

## Dados da Reunião
- **Título:** {reuniao.titulo}
- **Descrição:** {reuniao.descricao or 'Não informada'}
- **Data/Hora:** {timezone.localtime(reuniao.data_hora).strftime('%d/%m/%Y às %H:%M')}
- **Duração prevista:** {reuniao.duracao_minutos} minutos
- **Organização:** {empresa.nome}

## Participantes
{reuniao.participantes_nomes or 'Não informados'}

## Pauta
{reuniao.pauta or 'Pauta não definida previamente'}

## Notas da Reunião
{reuniao.notas or 'Sem notas registradas durante a reunião'}

## Contexto Epidemiológico Atual
{situacao_epi}

---

Gere a ata completa com as seguintes seções:
1. **Abertura** — data, hora, local (videoconferência), quórum
2. **Participantes** — lista com nomes e cargos
3. **Pauta** — itens discutidos
4. **Deliberações e Encaminhamentos** — decisões tomadas, responsáveis e prazos (infira dos dados disponíveis)
5. **Contexto Situacional** — breve menção ao panorama epidemiológico se relevante para a reunião
6. **Encerramento** — hora de encerramento (estime com base na duração), aprovação da ata

Seja formal e objetivo. Use linguagem técnica administrativa adequada à gestão pública de saúde.
Formate com Markdown (negrito para títulos de seção, listas para encaminhamentos)."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("Falha ao gerar ata por IA: %s", exc)
        return _ata_fallback(reuniao)


def _resumo_situacao_epi(empresa):
    try:
        from .views_governo_sala_situacao import api_governo_sala_situacao
        from django.test import RequestFactory
        from .models import DiagnosticoConfirmadoGov
        from datetime import date, timedelta
        from django.db.models import Count

        diagnosticos = (
            DiagnosticoConfirmadoGov.objects
            .filter(empresa=empresa, data_registro__gte=date.today() - timedelta(days=30))
            .values("cid10")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        if not diagnosticos:
            return "Nenhum diagnóstico confirmado registrado nos últimos 30 dias."
        linhas = [f"- {d['cid10']}: {d['total']} caso(s)" for d in diagnosticos]
        return "Top CID-10 confirmados nos últimos 30 dias:\n" + "\n".join(linhas)
    except Exception:
        return "Dados epidemiológicos não disponíveis no momento."


def _ata_fallback(reuniao):
    dh = timezone.localtime(reuniao.data_hora).strftime('%d/%m/%Y às %H:%M')
    partic = reuniao.participantes_nomes or "Não informados"
    pauta = reuniao.pauta or "Não definida"
    notas = reuniao.notas or "Sem notas"
    return f"""## Ata de Reunião

**Reunião:** {reuniao.titulo}
**Data/Hora:** {dh}
**Duração:** {reuniao.duracao_minutos} minutos

### Participantes
{partic}

### Pauta
{pauta}

### Notas / Deliberações
{notas}

### Encerramento
Reunião encerrada conforme agendado.

*Ata gerada automaticamente pelo SolusCRT — para ata com IA configure ANTHROPIC_API_KEY.*"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _r_dict(r):
    return {
        "id": r.id,
        "titulo": r.titulo,
        "descricao": r.descricao,
        "data_hora": r.data_hora.isoformat(),
        "duracao_minutos": r.duracao_minutos,
        "status": r.status,
        "status_label": r.get_status_display(),
        "sala_url": f"/governo/reuniao/{r.id}/sala/",
        "participantes_nomes": r.participantes_nomes,
        "pauta": r.pauta,
        "tem_ata": bool(r.ata),
        "ata_gerada_em": r.ata_gerada_em.isoformat() if r.ata_gerada_em else None,
        "criado_em": r.criado_em.isoformat(),
    }
