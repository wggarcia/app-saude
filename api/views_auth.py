from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json
import hashlib
import jwt
import os
from django.db import OperationalError
from django.http import JsonResponse
from django.contrib.auth.hashers import check_password, make_password
from .models import Empresa, DispositivoAutorizado, EmpresaUsuario, DonoSaaS
from django.conf import settings
from django.db import IntegrityError
from datetime import datetime, timedelta
import secrets
from django.shortcuts import redirect
from django.utils import timezone
from .planos import pacote_padrao, detalhes_pacote


COOKIE_MAX_AGE = 7 * 24 * 60 * 60
SESSION_IDLE_TIMEOUT = timedelta(minutes=15) if settings.DEBUG else timedelta(hours=8)


def _destino_conta(empresa):
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        if empresa.ativo and empresa.acesso_governo:
            return "/dashboard-governo/"
        return "/contrato-governo/"

    if empresa.ativo:
        return "/dashboard/"
    return "/pagamento/"


def _payload_resposta(empresa, token, device_id, dispositivos_em_uso, principal_kind, principal_id, principal_nome):
    return {
        "status": "ok",
        "token": token,
        "empresa_id": empresa.id,
        "empresa_nome": empresa.nome,
        "acesso_governo": empresa.acesso_governo,
        "tipo_conta": empresa.tipo_conta,
        "ativo": empresa.ativo,
        "device_id": device_id,
        "max_dispositivos": empresa.max_dispositivos,
        "max_usuarios": empresa.max_usuarios,
        "dispositivos_em_uso": dispositivos_em_uso,
        "pacote_codigo": empresa.pacote_codigo,
        "principal_kind": principal_kind,
        "principal_id": principal_id,
        "principal_nome": principal_nome,
        "destination": _destino_conta(empresa),
    }


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _resolver_device_id(request, dados):
    explicit_device_id = (dados or {}).get("device_id") or request.headers.get("X-Device-Id")
    if explicit_device_id:
        return str(explicit_device_id).strip()[:120]

    base = "|".join([
        str(_client_ip(request) or ""),
        str(request.META.get("HTTP_USER_AGENT") or ""),
    ])
    return "legacy-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def _registrar_dispositivo_login(empresa, request, dados):
    device_id = _resolver_device_id(request, dados)
    dispositivos_ativos = DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True)
    existente = DispositivoAutorizado.objects.filter(empresa=empresa, device_id=device_id).first()

    if existente:
        existente.user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
        existente.ip = _client_ip(request)
        existente.ativo = True
        if dados and dados.get("device_name") and not existente.apelido:
            existente.apelido = dados.get("device_name", "")[:120]
        try:
            existente.save(update_fields=["user_agent", "ip", "ativo", "apelido", "ultimo_acesso"])
        except OperationalError:
            pass
        return True, device_id, DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).count(), None

    if dispositivos_ativos.count() >= empresa.max_dispositivos:
        if dados and dados.get("force_login") is True:
            antigo = dispositivos_ativos.order_by("ultimo_acesso").first()
            if antigo:
                antigo.ativo = False
                antigo.save(update_fields=["ativo"])
                dispositivos_ativos = DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True)
        if dispositivos_ativos.count() < empresa.max_dispositivos:
            return _registrar_dispositivo_login(empresa, request, {**(dados or {}), "force_login": False})
        return False, device_id, dispositivos_ativos.count(), (
            f"Limite de dispositivos atingido para este contrato. "
            f"Plano atual permite {empresa.max_dispositivos} dispositivo(s)."
        )

    try:
        DispositivoAutorizado.objects.create(
            empresa=empresa,
            device_id=device_id,
            apelido=(dados or {}).get("device_name", "")[:120],
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
            ip=_client_ip(request),
        )
        return True, device_id, dispositivos_ativos.count() + 1, None
    except IntegrityError:
        existente = DispositivoAutorizado.objects.filter(empresa=empresa, device_id=device_id).first()
        if existente:
            existente.ativo = True
            existente.user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
            existente.ip = _client_ip(request)
            existente.save(update_fields=["ativo", "user_agent", "ip", "ultimo_acesso"])
            return True, device_id, DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).count(), None
        return False, device_id, dispositivos_ativos.count(), "Nao foi possivel autorizar este dispositivo agora. Tente novamente."
    except OperationalError:
        return True, device_id, dispositivos_ativos.count(), None


def _validar_sessao_unica(empresa, device_id):
    if empresa.sessao_ativa_chave and empresa.sessao_ativa_device_id and empresa.sessao_ativa_device_id != device_id:
        if empresa.sessao_ativa_em and timezone.now() - empresa.sessao_ativa_em > SESSION_IDLE_TIMEOUT:
            _limpar_sessao_principal(empresa)
            return True, None
        return False, (
            "Esta conta já está em uso em outro computador. "
            "Faça logout na máquina atual antes de entrar em uma nova."
        )
    return True, None


def _validar_sessao_principal(principal, device_id):
    if principal.sessao_ativa_chave and principal.sessao_ativa_device_id and principal.sessao_ativa_device_id != device_id:
        if principal.sessao_ativa_em and timezone.now() - principal.sessao_ativa_em > SESSION_IDLE_TIMEOUT:
            _limpar_sessao_principal(principal)
            return True, None
        return False, (
            "Este usuário já está em uso em outro computador. "
            "Faça logout na máquina atual antes de entrar em uma nova."
        )
    return True, None


def _ativar_sessao(principal, device_id):
    session_key = secrets.token_urlsafe(24)
    principal.sessao_ativa_chave = session_key
    principal.sessao_ativa_device_id = device_id
    principal.sessao_ativa_em = timezone.now()
    principal.save(update_fields=["sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em"])
    return session_key


def _criar_token(empresa, session_key, principal_kind, principal_id):
    return jwt.encode({
        "empresa_id": empresa.id,
        "acesso_governo": empresa.acesso_governo,
        "tipo_conta": empresa.tipo_conta,
        "max_dispositivos": empresa.max_dispositivos,
        "max_usuarios": empresa.max_usuarios,
        "pacote_codigo": empresa.pacote_codigo,
        "principal_kind": principal_kind,
        "principal_id": principal_id,
        "session_key": session_key,
        "exp": datetime.utcnow() + timedelta(days=7)
    }, settings.JWT_SECRET_KEY, algorithm="HS256")


def _aplicar_cookies_autenticacao(response, empresa, token):
    response.set_cookie("empresa_id", str(empresa.id), samesite="Lax", max_age=COOKIE_MAX_AGE)
    response.set_cookie("tipo_conta", empresa.tipo_conta, samesite="Lax", max_age=COOKIE_MAX_AGE)
    response.set_cookie(
        "auth_token",
        token,
        httponly=True,
        samesite="Lax",
        max_age=COOKIE_MAX_AGE,
    )
    return response


def _limpar_sessao_principal(principal):
    principal.sessao_ativa_chave = None
    principal.sessao_ativa_device_id = None
    principal.sessao_ativa_em = None
    principal.save(update_fields=["sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em"])


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

    autorizado, device_id, dispositivos_em_uso, erro_dispositivo = _registrar_dispositivo_login(empresa, request, dados)
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
    token = _criar_token(empresa, session_key, principal_kind, principal_id)
    response = JsonResponse(_payload_resposta(
        empresa,
        token,
        device_id,
        dispositivos_em_uso,
        principal_kind,
        principal_id,
        principal_nome,
    ))
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

    if Empresa.objects.filter(email=email).exists():
        return JsonResponse({"erro": "Email já existe"}, status=400)

    # 🔐 salva empresa
    empresa = Empresa.objects.create(
        nome=nome,
        email=email,
        senha=make_password(senha),
        pacote_codigo=pacote_padrao(),
        max_dispositivos=1,
        max_usuarios=1,
    )

    pacote = detalhes_pacote(empresa.pacote_codigo)
    empresa.max_dispositivos = pacote["dispositivos"]
    empresa.max_usuarios = pacote["usuarios"]
    empresa.save(update_fields=["pacote_codigo", "max_dispositivos", "max_usuarios"])

    autorizado, device_id, dispositivos_em_uso, erro_dispositivo = _registrar_dispositivo_login(empresa, request, dados)
    if not autorizado:
        return JsonResponse({"erro": erro_dispositivo}, status=403)

    # 🔑 gera token AUTOMÁTICO
    session_key = _ativar_sessao(empresa, device_id)
    token = _criar_token(empresa, session_key, "empresa_admin", empresa.id)

    response = JsonResponse(_payload_resposta(
        empresa,
        token,
        device_id,
        dispositivos_em_uso,
        "empresa_admin",
        empresa.id,
        empresa.nome,
    ))

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

    session_key = secrets.token_urlsafe(24)
    dono.sessao_ativa_chave = session_key
    dono.sessao_ativa_em = timezone.now()
    dono.save(update_fields=["sessao_ativa_chave", "sessao_ativa_em"])

    token = jwt.encode({
        "owner_id": dono.id,
        "session_key": session_key,
        "exp": datetime.utcnow() + timedelta(days=7)
    }, settings.JWT_SECRET_KEY, algorithm="HS256")

    response = JsonResponse({
        "status": "ok",
        "token": token,
        "owner_nome": dono.nome,
        "destination": "/console-operacional/",
    })
    response.set_cookie("owner_token", token, httponly=True, samesite="Lax", max_age=COOKIE_MAX_AGE)
    return response


def logout_empresa(request):
    token = request.COOKIES.get("auth_token")
    if token:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
            principal_kind = payload.get("principal_kind")
            principal_id = payload.get("principal_id")
            if principal_kind == "usuario_empresa":
                principal = EmpresaUsuario.objects.filter(id=principal_id).first()
            else:
                principal = Empresa.objects.filter(id=payload.get("empresa_id")).first()

            if principal and payload.get("session_key") == principal.sessao_ativa_chave:
                _limpar_sessao_principal(principal)
        except Exception:
            pass

    owner_token = request.COOKIES.get("owner_token")
    if owner_token:
        try:
            payload = jwt.decode(owner_token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
            dono = DonoSaaS.objects.filter(id=payload.get("owner_id")).first()
            if dono and payload.get("session_key") == dono.sessao_ativa_chave:
                dono.sessao_ativa_chave = None
                dono.sessao_ativa_em = None
                dono.save(update_fields=["sessao_ativa_chave", "sessao_ativa_em"])
        except Exception:
            pass

    response = redirect("/")
    response.delete_cookie("empresa_id")
    response.delete_cookie("auth_token")
    response.delete_cookie("tipo_conta")
    response.delete_cookie("owner_token")
    return response
