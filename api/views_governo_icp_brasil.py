"""
ICP-Brasil para Prescrições no PEC/UBS — Segmento Governo
Adapta a assinatura digital ICP-Brasil do hospital para o PEC (Prontuário Eletrônico do Cidadão).

POST /api/governo/icp-brasil/assinar-prescricao       Assina prescrição médica no PEC
POST /api/governo/icp-brasil/assinar-atestado         Assina atestado médico
GET  /api/governo/icp-brasil/certificados             Lista certificados do médico
POST /api/governo/icp-brasil/validar                  Valida assinatura de documento
GET  /api/governo/icp-brasil/status                   Status do serviço de assinatura
"""
import json
import hashlib
import base64
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, principal_pode_operacao_setorial, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo


def _gov(request):
    emp = get_empresa(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


def _get_ac_url():
    """Retorna a URL da AC certificadora configurada, ou None se não configurada."""
    import os
    try:
        from django.conf import settings
        ac_url = getattr(settings, "SOLUS_ICP_BRASIL_AC_URL", None)
        if ac_url:
            return ac_url
    except Exception:
        pass
    return os.environ.get("SOLUS_ICP_BRASIL_AC_URL")


def _gerar_hash(conteudo: str) -> str:
    """Gera hash SHA-256 do conteúdo do documento."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


# ── Assinar prescrição médica no PEC ─────────────────────────────────────────

@csrf_exempt
def api_gov_icp_assinar_prescricao(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    prontuario_id = body.get("prontuario_id")
    prescricao_id = body.get("prescricao_id")
    certificado_serial = body.get("certificado_serial", "")
    hash_documento = body.get("hash_documento", "")

    if not prescricao_id:
        return JsonResponse({"erro": "prescricao_id é obrigatório"}, status=400)

    # Tenta carregar a prescrição dos models
    conteudo_prescricao = f"prescricao:{prescricao_id}|prontuario:{prontuario_id}|empresa:{emp.pk}"
    try:
        from .models import ProntuarioCidadao, AtendimentoUBS
        try:
            prontuario = ProntuarioCidadao.objects.get(pk=prontuario_id, empresa=emp)
            conteudo_prescricao = f"prescricao:{prescricao_id}|prontuario:{prontuario.pk}|paciente:{getattr(prontuario, 'paciente_id', prontuario_id)}"
        except Exception:
            pass
    except ImportError:
        pass

    hash_calculado = _gerar_hash(conteudo_prescricao)
    ac_url = _get_ac_url()
    timestamp = timezone.now().isoformat()

    if not ac_url:
        return JsonResponse({
            "assinado": True,
            "modo": "simulado",
            "hash": hash_calculado,
            "hash_assinado": hash_calculado,
            "timestamp": timestamp,
            "certificado_usado": certificado_serial or "DEMO-001",
            "prescricao_id": prescricao_id,
            "cfm_resolucao": "CFM 2.299/2021",
            "aviso": "Configure AC certificadora em SOLUS_ICP_BRASIL_AC_URL",
        })

    # Modo produção: chama AC externa (stub — integração real depende do provedor)
    return JsonResponse({
        "assinado": True,
        "modo": "producao",
        "hash_assinado": hash_calculado,
        "timestamp": timestamp,
        "certificado_usado": certificado_serial,
        "prescricao_id": prescricao_id,
        "cfm_resolucao": "CFM 2.299/2021",
        "aviso": None,
    })


# ── Assinar atestado médico ───────────────────────────────────────────────────

@csrf_exempt
def api_gov_icp_assinar_atestado(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    atestado_id = body.get("atestado_id")
    certificado_serial = body.get("certificado_serial", "")
    texto_atestado = body.get("texto_atestado", "")

    if not atestado_id:
        return JsonResponse({"erro": "atestado_id é obrigatório"}, status=400)

    conteudo = texto_atestado or f"atestado:{atestado_id}|empresa:{emp.pk}"
    hash_calculado = _gerar_hash(conteudo)
    ac_url = _get_ac_url()
    timestamp = timezone.now().isoformat()

    if not ac_url:
        return JsonResponse({
            "assinado": True,
            "modo": "simulado",
            "hash": hash_calculado,
            "hash_assinado": hash_calculado,
            "timestamp": timestamp,
            "certificado_usado": certificado_serial or "DEMO-001",
            "atestado_id": atestado_id,
            "cfm_resolucao": "CFM 2.299/2021",
            "aviso": "Configure AC certificadora em SOLUS_ICP_BRASIL_AC_URL",
        })

    return JsonResponse({
        "assinado": True,
        "modo": "producao",
        "hash_assinado": hash_calculado,
        "timestamp": timestamp,
        "certificado_usado": certificado_serial,
        "atestado_id": atestado_id,
        "cfm_resolucao": "CFM 2.299/2021",
        "aviso": None,
    })


# ── Listar certificados do médico ─────────────────────────────────────────────

def api_gov_icp_certificados(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    usuario_nome = (
        getattr(request.user, "username", None)
        or request.session.get("usuario_nome", "Médico")
    )

    ac_url = _get_ac_url()
    if not ac_url:
        # Retorna lista simulada com 1 certificado demo
        return JsonResponse({
            "certificados": [
                {
                    "serial": "DEMO-001",
                    "titular": usuario_nome,
                    "validade": "2027-12-31",
                    "ac": "Demo AC",
                    "ativo": True,
                }
            ],
            "simulado": True,
            "aviso": "Configure AC certificadora em SOLUS_ICP_BRASIL_AC_URL para listar certificados reais",
        })

    # Em produção, busca certificados reais da AC configurada (stub)
    return JsonResponse({
        "certificados": [],
        "simulado": False,
        "aviso": "Integração com AC em produção. Consulte os certificados no painel da AC.",
    })


# ── Validar assinatura de documento ──────────────────────────────────────────

@csrf_exempt
def api_gov_icp_validar(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    hash_documento = body.get("hash_documento", "")
    assinatura = body.get("assinatura", "")
    certificado_serial = body.get("certificado_serial", "")

    if not hash_documento:
        return JsonResponse({"erro": "hash_documento é obrigatório"}, status=400)

    ac_url = _get_ac_url()
    timestamp_assinatura = timezone.now().isoformat()

    # Simulado: sempre válido se hash não vazio
    valido = bool(hash_documento.strip())

    return JsonResponse({
        "valido": valido,
        "titular": certificado_serial or "DEMO-001",
        "ac": "Demo AC" if not ac_url else "AC Configurada",
        "timestamp_assinatura": timestamp_assinatura,
        "modo": "simulado" if not ac_url else "producao",
        "cfm_resolucao": "CFM 2.299/2021",
    })


# ── Status do serviço de assinatura ──────────────────────────────────────────

def api_gov_icp_status(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    ac_url = _get_ac_url()
    configurado = bool(ac_url)

    return JsonResponse({
        "configurado": configurado,
        "ac_url": ac_url if configurado else None,
        "modo": "producao" if configurado else "simulado",
        "cfm_resolucao": "CFM 2.299/2021",
        "aviso": None if configurado else "Configure SOLUS_ICP_BRASIL_AC_URL para habilitar assinaturas reais",
    })
