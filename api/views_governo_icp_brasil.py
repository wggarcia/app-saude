"""
ICP-Brasil para Prescrições no PEC/UBS — Segmento Governo
Adapta a assinatura digital ICP-Brasil do hospital para o PEC (Prontuário Eletrônico do Cidadão).

POST /api/governo/icp-brasil/assinar-prescricao       Assina prescrição médica no PEC
POST /api/governo/icp-brasil/assinar-atestado         Assina atestado médico
GET  /api/governo/icp-brasil/certificados             Lista certificados do médico
POST /api/governo/icp-brasil/validar                  Valida assinatura de documento
GET  /api/governo/icp-brasil/status                   Status do serviço de assinatura

IMPORTANTE: este módulo NÃO possui integração HTTP real com nenhuma Autoridade
Certificadora (AC) ICP-Brasil — isso exigiria credenciais/contrato reais com uma AC
que este ambiente não possui. Os endpoints de ação (assinar prescrição, assinar
atestado, validar assinatura, listar certificados) portanto NUNCA retornam sucesso
fabricado: quando a integração real não está configurada/implementada, respondem
com erro explícito HTTP 503, deixando claro que a operação não foi realizada de
verdade. Apenas o endpoint de status (somente leitura) responde 200, pois ele
apenas relata a configuração atual — nunca simula uma assinatura.
"""
import json
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, principal_pode_operacao_setorial, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo


def _gov(request):
    emp = get_empresa(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


def _icp_config():
    """Lê a configuração da AC certificadora ICP-Brasil diretamente das variáveis de
    ambiente (nada é lido de settings.py — integração 100% via env vars).

    ICP_BRASIL_AC_URL   — URL da Autoridade Certificadora configurada.
    ICP_BRASIL_AC_TOKEN — token/credencial de acesso à AC.
    ICP_BRASIL_MODO     — deve ser exatamente 'producao' para operação real.
    """
    return {
        "ac_url": os.environ.get("ICP_BRASIL_AC_URL"),
        "ac_token": os.environ.get("ICP_BRASIL_AC_TOKEN"),
        "modo": os.environ.get("ICP_BRASIL_MODO", "simulado"),
    }


def _icp_erro_indisponivel(config, contexto=None):
    """Resposta honesta e explícita (HTTP 503) para quando a operação ICP-Brasil
    solicitada não pôde ser executada de verdade — substitui o comportamento antigo
    que fingia sucesso (assinado/valido = True) mesmo sem nenhuma integração real."""
    if config["modo"] != "producao":
        mensagem = (
            f"ICP_BRASIL_MODO='{config['modo']}' (esperado 'producao' para operação "
            "real). O sistema está em modo simulado: nenhuma assinatura ou validação "
            "real foi realizada."
        )
        modo_resposta = "simulado"
    elif not config["ac_url"]:
        mensagem = (
            "ICP_BRASIL_MODO='producao', porém ICP_BRASIL_AC_URL não está configurada. "
            "Nenhuma assinatura ou validação real foi realizada."
        )
        modo_resposta = "simulado"
    else:
        mensagem = (
            "ICP_BRASIL_MODO='producao' e ICP_BRASIL_AC_URL configuradas, mas a "
            "integração HTTP real com a Autoridade Certificadora ainda não está "
            "implementada neste servidor. Nenhuma assinatura ou validação real foi "
            "realizada."
        )
        modo_resposta = "producao_nao_implementado"

    payload = {
        "erro": "servico_icp_brasil_indisponivel",
        "assinado": False,
        "valido": False,
        "modo": modo_resposta,
        "mensagem": mensagem,
        "cfm_resolucao": "CFM 2.299/2021",
    }
    if contexto:
        payload.update(contexto)
    return JsonResponse(payload, status=503)


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

    prescricao_id = body.get("prescricao_id")
    if not prescricao_id:
        return JsonResponse({"erro": "prescricao_id é obrigatório"}, status=400)

    config = _icp_config()
    return _icp_erro_indisponivel(config, contexto={"prescricao_id": prescricao_id})


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
    if not atestado_id:
        return JsonResponse({"erro": "atestado_id é obrigatório"}, status=400)

    config = _icp_config()
    return _icp_erro_indisponivel(config, contexto={"atestado_id": atestado_id})


# ── Listar certificados do médico ─────────────────────────────────────────────

def api_gov_icp_certificados(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    config = _icp_config()
    return _icp_erro_indisponivel(config, contexto={"certificados": []})


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
    if not hash_documento:
        return JsonResponse({"erro": "hash_documento é obrigatório"}, status=400)

    config = _icp_config()
    return _icp_erro_indisponivel(config)


# ── Status do serviço de assinatura ──────────────────────────────────────────

def api_gov_icp_status(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    emp = _gov(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento governo requerido."}, status=403)

    config = _icp_config()
    producao_configurada = config["modo"] == "producao" and bool(config["ac_url"])

    if config["modo"] != "producao":
        aviso = (
            "Modo simulado. Configure ICP_BRASIL_MODO=producao e ICP_BRASIL_AC_URL "
            "(além de ICP_BRASIL_AC_TOKEN) para habilitar o modo produção."
        )
    elif not config["ac_url"]:
        aviso = "ICP_BRASIL_MODO=producao mas ICP_BRASIL_AC_URL não está configurada."
    else:
        aviso = (
            "ICP_BRASIL_MODO=producao e ICP_BRASIL_AC_URL configuradas, porém a "
            "integração HTTP real com a Autoridade Certificadora ainda não está "
            "implementada neste servidor — nenhuma assinatura real pode ser feita."
        )

    return JsonResponse({
        "configurado": producao_configurada,
        "integracao_http_implementada": False,
        "ac_url": config["ac_url"] if producao_configurada else None,
        "modo": config["modo"],
        "cfm_resolucao": "CFM 2.299/2021",
        "aviso": aviso,
    })
