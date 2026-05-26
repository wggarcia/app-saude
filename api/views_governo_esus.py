"""
views_governo_esus.py
e-SUS / RNDS — envio de fichas e log de integração.
Nota: integração real com RNDS exige certificado ICP-Brasil e OAuth2 via
      CONASS/CONASEMS. Este módulo é um stub que registra as fichas e simula o envio.
"""
import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import AtendimentoUBS, LogESUS
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import requer_setor, requer_operacao_page


def _e(request):
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
def governo_esus_page(request):
    return render(request, "governo_esus.html", contexto_navegacao_setorial(request, "governo"))


# ── Status ────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_esus_status(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    pendentes = AtendimentoUBS.objects.filter(empresa=e, enviado_esus=False).count()
    enviados_hoje = LogESUS.objects.filter(empresa=e, enviado_em__date=hoje, status="enviado").count()
    erros = LogESUS.objects.filter(empresa=e, status="erro").count()
    return JsonResponse({
        "pendentes": pendentes,
        "enviados_hoje": enviados_hoje,
        "erros": erros,
    })


# ── Logs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_esus_logs(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = LogESUS.objects.filter(empresa=e)[:50]
    return JsonResponse({"logs": [_log_dict(l) for l in qs]})


# ── Enviar fichas ─────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_esus_enviar_fichas(request):
    """
    Stub: coleta AtendimentoUBS não enviados, registra LogESUS e marca como enviado.
    Produção requereria: certificado ICP-Brasil A3, autenticação OAuth2 RNDS e
    serialização das fichas nos padrões FHIR/e-SUS (fichaIndividual, fichaAtendimento etc.).
    """
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    pendentes_qs = AtendimentoUBS.objects.filter(empresa=e, enviado_esus=False)
    total = pendentes_qs.count()
    if total == 0:
        return JsonResponse({"enviados": 0, "mensagem": "Nenhuma ficha pendente."})
    # Create log record
    log = LogESUS.objects.create(
        empresa=e,
        ficha_tipo="fichaAtendimentoIndividual",
        registros_enviados=total,
        status="pendente",
        resposta_rnds={"stub": True, "registros": total,
                       "aviso": "Integração RNDS real requer certificado ICP-Brasil."},
    )
    # Mark records as sent
    pendentes_qs.update(enviado_esus=True)
    # Simulate successful stub response
    log.status = "enviado"
    log.save(update_fields=["status"])
    return JsonResponse({
        "enviados": total,
        "log_id": log.id,
        "mensagem": f"{total} ficha(s) marcada(s) como enviada(s) (stub — produção requer RNDS).",
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_dict(l):
    return {
        "id": l.id,
        "ficha_tipo": l.ficha_tipo,
        "registros_enviados": l.registros_enviados,
        "status": l.status,
        "resposta_rnds": l.resposta_rnds,
        "enviado_em": l.enviado_em.isoformat(),
    }
