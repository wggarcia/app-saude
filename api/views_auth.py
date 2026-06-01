from django.views.decorators.csrf import csrf_exempt
import json
import logging
import os
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.hashers import check_password, make_password
from .models import Empresa, EmpresaUsuario, DonoSaaS, TrialEmpresa
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import redirect
from .middleware import clear_login_rate_limit
from .planos import pacote_padrao, detalhes_pacote, normalizar_codigo_pacote
from .services.auth_session import (
    COOKIE_MAX_AGE,
    aplicar_cookie_owner,
    aplicar_cookies_autenticacao as _aplicar_cookies_autenticacao,
    criar_owner_token,
    criar_token as _criar_token,
    destino_conta as _destino_conta,
    limpar_sessao_empresa_por_token,
    limpar_sessao_owner_por_token,
    limpar_sessao_principal as _limpar_sessao_principal,
    payload_resposta as _payload_resposta,
    registrar_dispositivo_login as _registrar_dispositivo_login,
    registrar_sessao_aba as _registrar_sessao_aba,
    resolver_sessao_empresa_por_token,
    validar_sessao_principal as _validar_sessao_principal,
    ativar_sessao as _ativar_sessao,
)

logger = logging.getLogger(__name__)

def _provisionar_dono_por_ambiente(email, senha):
    env_email = os.environ.get("SOLUSCRT_BOOTSTRAP_OWNER_EMAIL", "").strip().lower()
    env_senha = os.environ.get("SOLUSCRT_BOOTSTRAP_OWNER_PASSWORD", "").strip()
    env_nome = os.environ.get("SOLUSCRT_BOOTSTRAP_OWNER_NOME", "Operacao SolusCRT").strip()

    if email.strip().lower() != env_email or senha != env_senha:
        return None

    return DonoSaaS.objects.create(
        nome=env_nome or "Operacao SolusCRT",
        email=env_email,
        senha=make_password(env_senha),
        ativo=True,
    )



def _destino_ti_empresa(empresa):
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return "/governo/plataforma/"
    return "/ti/"


def _login_conta(request, portal_tipo=None):
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    try:
        dados = json.loads(request.body)
    except:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    email = dados.get("email")
    senha = dados.get("senha")

    if not email or not senha:
        return JsonResponse({"erro": "Email e senha obrigatórios"}, status=400)

    empresa = Empresa.objects.filter(email=email).first()
    usuario = None

    if not empresa:
        usuario = EmpresaUsuario.objects.filter(email=email, ativo=True).select_related("empresa").first()
        empresa = usuario.empresa if usuario else None

    if not empresa:
        return JsonResponse({"status": "erro", "mensagem": "Conta não encontrada"}, status=404)

    if portal_tipo == Empresa.TIPO_EMPRESA and empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return JsonResponse({
            "status": "erro",
            "mensagem": "Esta credencial pertence ao ambiente governamental dedicado.",
        }, status=403)

    if portal_tipo == Empresa.TIPO_GOVERNO and empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        return JsonResponse({
            "status": "erro",
            "mensagem": "Esta credencial não pertence ao ambiente governamental.",
        }, status=403)

    senha_ok = check_password(senha, usuario.senha if usuario else empresa.senha)
    if not senha_ok:
        return JsonResponse({"status": "erro", "mensagem": "Senha incorreta"}, status=401)

    try:
        autorizado, device_id, dispositivos_em_uso, erro_dispositivo = _registrar_dispositivo_login(empresa, request, dados)
    except Exception as _exc_reg:
        logger.exception(
            "LOGIN 500 — registrar_dispositivo_login falhou | empresa_id=%s email=%s | %s",
            getattr(empresa, "id", "?"), email, type(_exc_reg).__name__,
        )
        raise
    if not autorizado:
        return JsonResponse({"status": "erro", "mensagem": erro_dispositivo}, status=403)

    if usuario:
        principal = usuario
        principal_kind = "usuario_empresa"
        principal_id = usuario.id
        principal_nome = usuario.nome
    else:
        principal = empresa
        principal_kind = "empresa_admin"
        principal_id = empresa.id
        principal_nome = empresa.nome

    sessao_ok, erro_sessao = _validar_sessao_principal(principal, device_id)
    if not sessao_ok:
        if dados.get("force_login") is True:
            _limpar_sessao_principal(principal)
        else:
            return JsonResponse({
                "status": "erro",
                "codigo": "sessao_em_uso",
                "mensagem": erro_sessao,
                "acao": "force_login",
            }, status=409)

    session_key = _ativar_sessao(principal, device_id)
    token = _criar_token(empresa, session_key, principal_kind, principal_id, device_id=device_id)
    clear_login_rate_limit(request)
    payload = _payload_resposta(
        empresa,
        token,
        device_id,
        dispositivos_em_uso,
        principal_kind,
        principal_id,
        principal_nome,
    )
    try:
        from .access_control import destino_por_perfil

        class _LoginRequestProxy:
            pass

        if principal_kind == "usuario_empresa":
            req_proxy = _LoginRequestProxy()
            req_proxy.empresa = empresa
            req_proxy.principal = principal
            payload["destination"] = destino_por_perfil(req_proxy, empresa)
    except Exception:
        if principal_kind == "usuario_empresa" and getattr(principal, "cargo", "").strip().lower() == "ti":
            payload["destination"] = _destino_ti_empresa(empresa)

    response = JsonResponse(payload)
    return _aplicar_cookies_autenticacao(response, empresa, token)


# 🔐 LOGIN
@csrf_exempt
def login_empresa(request):
    return _login_conta(request)


@csrf_exempt
def login_portal_empresa(request):
    return _login_conta(request, Empresa.TIPO_EMPRESA)


@csrf_exempt
def login_portal_governo(request):
    return _login_conta(request, Empresa.TIPO_GOVERNO)


# 🚀 CADASTRO
@csrf_exempt
def registrar_empresa(request):

    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    try:
        dados = json.loads(request.body)
    except:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = dados.get("nome")
    email = dados.get("email")
    senha = dados.get("senha")

    # 🔥 validação
    if not nome or not email or not senha:
        return JsonResponse({"erro": "Preencha todos os campos"}, status=400)

    if len(senha) < 8:
        return JsonResponse({"erro": "Senha deve ter pelo menos 8 caracteres"}, status=400)

    if Empresa.objects.filter(email=email).exists():
        return JsonResponse({"erro": "Email já cadastrado"}, status=400)

    # Resolve pacote — governo só via contrato, nunca via self-service
    from .planos import PACOTES_SAAS
    pacote_solicitado = normalizar_codigo_pacote(dados.get("pacote_codigo") or pacote_padrao())
    pacote_info = PACOTES_SAAS.get(pacote_solicitado, PACOTES_SAAS[pacote_padrao()])
    if pacote_info.get("setor") == "governo":
        pacote_solicitado = pacote_padrao()
        pacote_info = PACOTES_SAAS[pacote_padrao()]

    # 🔐 salva empresa — INATIVA até escolher plano ou ativar trial
    empresa = Empresa.objects.create(
        nome=nome,
        email=email,
        senha=make_password(senha),
        pacote_codigo=pacote_solicitado,
        max_dispositivos=pacote_info["dispositivos"],
        max_usuarios=pacote_info["usuarios"],
        ativo=False,  # bloqueado até pagamento ou ativação do trial
    )

    autorizado, device_id, dispositivos_em_uso, erro_dispositivo = _registrar_dispositivo_login(empresa, request, dados)
    if not autorizado:
        return JsonResponse({"erro": erro_dispositivo}, status=403)

    # 🔑 gera token — acesso restrito ao /pagamento/ até ativar
    session_key = _ativar_sessao(empresa, device_id)
    token = _criar_token(empresa, session_key, "empresa_admin", empresa.id, device_id=device_id)

    payload = _payload_resposta(
        empresa,
        token,
        device_id,
        dispositivos_em_uso,
        "empresa_admin",
        empresa.id,
        empresa.nome,
    )
    # Força destino para pagamento independente do setor
    payload["destination"] = "/pagamento/"

    response = JsonResponse(payload)
    return _aplicar_cookies_autenticacao(response, empresa, token)


@csrf_exempt
def login_dono_saas(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    email = dados.get("email")
    senha = dados.get("senha")

    dono = DonoSaaS.objects.filter(email=email, ativo=True).first()
    if not dono:
        dono = _provisionar_dono_por_ambiente(email or "", senha or "")
    if not dono:
        return JsonResponse({"status": "erro", "mensagem": "Credencial operacional não encontrada"}, status=404)

    if not check_password(senha, dono.senha):
        return JsonResponse({"status": "erro", "mensagem": "Senha incorreta"}, status=401)

    token = criar_owner_token(dono)

    response = JsonResponse({
        "status": "ok",
        "token": token,
        "owner_nome": dono.nome,
        "destination": "/console-operacional/",
    })
    return aplicar_cookie_owner(response, token)


@csrf_exempt
def ativar_sessao_aba(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JsonResponse({"erro": "token ausente"}, status=401)

    token = auth.split(" ", 1)[1].strip()

    # Decode the token from the Authorization header directly — do NOT rely on
    # request.empresa (middleware cookie), which may already point to a different
    # account if the user is logged into another tab.
    try:
        data, empresa, principal = resolver_sessao_empresa_por_token(token, require_active_empresa=True)
        if principal.sessao_ativa_chave and data.get("session_key") != principal.sessao_ativa_chave:
            return JsonResponse({"erro": "sessão encerrada"}, status=401)
    except Exception:
        return JsonResponse({"erro": "token inválido"}, status=401)

    response = JsonResponse({
        "status": "ok",
        "empresa_id": empresa.id,
        "tipo_conta": empresa.tipo_conta,
        "destination": _destino_conta(empresa),
        "tab_key": _registrar_sessao_aba(token),
    })
    # Re-apply cookie so this tab's cookie matches its sessionStorage token
    return _aplicar_cookies_autenticacao(response, empresa, token)


def logout_empresa(request):
    return _logout(request, redirect_to="/")


def logout_governo(request):
    return _logout(request, redirect_to="/login-governo/")


def logout_operacao(request):
    return _logout(request, redirect_to="/operacao-central/")


@csrf_exempt
def ativar_trial(request):
    """Ativa o trial self-service para a empresa autenticada."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return JsonResponse({"status": "erro", "mensagem": "Governo não usa trial"}, status=403)

    # Verifica se já tem trial ativo
    trial = getattr(empresa, "trial", None)
    if trial:
        if not trial.convertido and trial.expira_em > timezone.now():
            # Trial ainda válido — ativa a empresa e redireciona
            if not empresa.ativo:
                empresa.ativo = True
                empresa.save(update_fields=["ativo"])
            from .services.auth_session import destino_conta as _destino_conta
            return JsonResponse({
                "status": "ja_ativo",
                "dias_restantes": trial.dias_restantes(),
                "destination": _destino_conta(empresa),
            })
        else:
            return JsonResponse({"status": "erro", "mensagem": "Período de avaliação já utilizado. Contrate um plano para continuar."}, status=403)

    # Cria trial + ativa a empresa
    TrialEmpresa.objects.create(
        empresa=empresa,
        expira_em=timezone.now() + timedelta(days=settings.TRIAL_DAYS),
    )
    empresa.ativo = True
    empresa.save(update_fields=["ativo"])

    # Email de boas-vindas enviado aqui — momento correto após ativação
    try:
        from .email_service import enviar_email_boas_vindas
        enviar_email_boas_vindas(empresa)
    except Exception:
        pass

    from .services.auth_session import destino_conta as _destino_conta
    return JsonResponse({
        "status": "ok",
        "dias_restantes": settings.TRIAL_DAYS,
        "destination": _destino_conta(empresa),
    })


def _logout(request, redirect_to="/"):
    token = request.COOKIES.get("auth_token")
    if token:
        limpar_sessao_empresa_por_token(token)

    owner_token = request.COOKIES.get("owner_token")
    if owner_token:
        limpar_sessao_owner_por_token(owner_token)

    response = redirect(redirect_to)
    response.delete_cookie("empresa_id")
    response.delete_cookie("auth_token")
    response.delete_cookie("tipo_conta")
    response.delete_cookie("owner_token")
    return response
