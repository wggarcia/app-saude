import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, OperationalError
from django.utils import timezone

from api.models import DispositivoAutorizado, DonoSaaS, Empresa, EmpresaUsuario
from api.planos import detalhes_pacote


COOKIE_MAX_AGE = 7 * 24 * 60 * 60
TAB_SESSION_MAX_AGE = 8 * 60 * 60
SESSION_IDLE_TIMEOUT = timedelta(minutes=15) if settings.DEBUG else timedelta(hours=8)
COOKIE_SECURE = not settings.DEBUG
DEVICE_IDLE_TIMEOUT = SESSION_IDLE_TIMEOUT

# Contas de demonstração (App Store / Google Play / avaliadores).
# Estas contas são compartilhadas por múltiplos revisores em dispositivos
# diferentes ao mesmo tempo, então NÃO podem ficar presas no bloqueio de
# sessão única nem no limite de dispositivos — caso contrário o avaliador
# recebe 409 "sessao_em_uso" / 403 "limite de dispositivos" e não consegue
# logar (causa da rejeição Apple Guideline 2.1).
DEMO_LOGIN_EMAILS = frozenset({
    "demo.sst@soluscrt.com",
    "demo.farmacia@soluscrt.com",
    "demo.hospital@soluscrt.com",
    "demo.governo@soluscrt.com",
    "demo.plano@soluscrt.com",
})


def is_demo_account(empresa) -> bool:
    """True se a empresa for um ambiente de demonstração para avaliadores."""
    email = (getattr(empresa, "email", "") or "").strip().lower()
    return email in DEMO_LOGIN_EMAILS


def destino_conta(empresa):
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        if empresa.ativo and empresa.acesso_governo:
            return "/dashboard-governo/"
        return "/contrato-governo/"

    if empresa.ativo:
        setor = detalhes_pacote(empresa.pacote_codigo).get("setor")
        if setor == "farmacia":
            return "/dashboard-farmacia/"
        if setor == "hospital":
            return "/dashboard-hospital/"
        if setor == "plano_saude":
            return "/dashboard-plano-saude/"
        return "/dashboard-empresa/"
    return "/pagamento/"


def payload_resposta(empresa, token, device_id, dispositivos_em_uso, principal_kind, principal_id, principal_nome):
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
        "destination": destino_conta(empresa),
    }


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def resolver_device_id(request, dados):
    explicit_device_id = (dados or {}).get("device_id") or request.headers.get("X-Device-Id")
    if explicit_device_id:
        return str(explicit_device_id).strip()[:120]

    base = "|".join([
        str(client_ip(request) or ""),
        str(request.META.get("HTTP_USER_AGENT") or ""),
    ])
    return "legacy-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def limpar_sessao_principal(principal):
    principal.sessao_ativa_chave = None
    principal.sessao_ativa_device_id = None
    principal.sessao_ativa_em = None
    principal.save(update_fields=["sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em"])


def _liberar_dispositivos_ociosos(empresa):
    limite = timezone.now() - DEVICE_IDLE_TIMEOUT
    DispositivoAutorizado.objects.filter(
        empresa=empresa,
        ativo=True,
        ultimo_acesso__lt=limite,
    ).update(ativo=False)


def _rls_set_empresa_auth(empresa_id: int) -> None:
    """
    Define app.empresa_id (SET SESSION) para queries RLS durante o fluxo de autenticação.

    Usa is_local=False (SET SESSION) — necessário com psycopg3, cujo modo "autobegin"
    não garante persistência de SET LOCAL entre cursors dentro do mesmo atomic().
    """
    from django.db import connection
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(empresa_id)])
    except Exception:
        pass  # nunca quebra o login por falha de RLS


def registrar_dispositivo_login(empresa, request, dados):
    # ── RLS: define o tenant boundary antes de qualquer acesso a DispositivoAutorizado
    _rls_set_empresa_auth(empresa.id)
    device_id = resolver_device_id(request, dados)
    _liberar_dispositivos_ociosos(empresa)
    dispositivos_ativos = DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True)
    existente = DispositivoAutorizado.objects.filter(empresa=empresa, device_id=device_id).first()

    if existente:
        existente.user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
        existente.ip = client_ip(request)
        existente.ativo = True
        if dados and dados.get("device_name") and not existente.apelido:
            existente.apelido = dados.get("device_name", "")[:120]
        try:
            existente.save(update_fields=["user_agent", "ip", "ativo", "apelido", "ultimo_acesso"])
        except OperationalError:
            pass
        return True, device_id, DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).count(), None

    if dispositivos_ativos.count() >= empresa.max_dispositivos and not is_demo_account(empresa):
        if dados and dados.get("force_login") is True:
            antigo = dispositivos_ativos.order_by("ultimo_acesso").first()
            if antigo:
                antigo.ativo = False
                antigo.save(update_fields=["ativo"])
                dispositivos_ativos = DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True)
        if dispositivos_ativos.count() < empresa.max_dispositivos:
            return registrar_dispositivo_login(empresa, request, {**(dados or {}), "force_login": False})
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
            ip=client_ip(request),
        )
        return True, device_id, dispositivos_ativos.count() + 1, None
    except IntegrityError:
        existente = DispositivoAutorizado.objects.filter(empresa=empresa, device_id=device_id).first()
        if existente:
            existente.ativo = True
            existente.user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
            existente.ip = client_ip(request)
            existente.save(update_fields=["ativo", "user_agent", "ip", "ultimo_acesso"])
            return True, device_id, DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).count(), None
        return False, device_id, dispositivos_ativos.count(), "Nao foi possivel autorizar este dispositivo agora. Tente novamente."
    except OperationalError:
        return True, device_id, dispositivos_ativos.count(), None


def validar_sessao_principal(principal, device_id):
    # Contas de demonstração nunca ficam presas no bloqueio de sessão única:
    # vários avaliadores (Apple/Google) usam a mesma conta simultaneamente.
    if is_demo_account(principal):
        return True, None
    if principal.sessao_ativa_chave and principal.sessao_ativa_device_id and principal.sessao_ativa_device_id != device_id:
        if principal.sessao_ativa_em and timezone.now() - principal.sessao_ativa_em > SESSION_IDLE_TIMEOUT:
            limpar_sessao_principal(principal)
            return True, None
        return False, (
            "Este usuário já está em uso em outro computador. "
            "Faça logout na máquina atual antes de entrar em uma nova."
        )
    return True, None


def ativar_sessao(principal, device_id):
    session_key = secrets.token_urlsafe(24)
    principal.sessao_ativa_chave = session_key
    principal.sessao_ativa_device_id = device_id
    principal.sessao_ativa_em = timezone.now()
    principal.save(update_fields=["sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em"])
    return session_key


def jwt_claim_times():
    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(hours=settings.JWT_EXP_HOURS)
    return issued_at, expires_at


def criar_token(empresa, session_key, principal_kind, principal_id, device_id=None):
    issued_at, expires_at = jwt_claim_times()
    return jwt.encode({
        "empresa_id": empresa.id,
        "acesso_governo": empresa.acesso_governo,
        "tipo_conta": empresa.tipo_conta,
        "max_dispositivos": empresa.max_dispositivos,
        "max_usuarios": empresa.max_usuarios,
        "pacote_codigo": empresa.pacote_codigo,
        "principal_kind": principal_kind,
        "principal_id": principal_id,
        "device_id": device_id,
        "session_key": session_key,
        "iat": issued_at,
        "exp": expires_at,
    }, settings.JWT_SECRET_KEY, algorithm="HS256")


def criar_owner_token(dono):
    session_key = secrets.token_urlsafe(24)
    dono.sessao_ativa_chave = session_key
    dono.sessao_ativa_em = timezone.now()
    dono.save(update_fields=["sessao_ativa_chave", "sessao_ativa_em"])

    issued_at, expires_at = jwt_claim_times()
    token = jwt.encode({
        "owner_id": dono.id,
        "session_key": session_key,
        "iat": issued_at,
        "exp": expires_at,
    }, settings.JWT_SECRET_KEY, algorithm="HS256")
    return token


def aplicar_cookies_autenticacao(response, empresa, token):
    response.set_cookie("empresa_id", str(empresa.id), samesite="Lax", max_age=COOKIE_MAX_AGE, secure=COOKIE_SECURE)
    response.set_cookie("tipo_conta", empresa.tipo_conta, samesite="Lax", max_age=COOKIE_MAX_AGE, secure=COOKIE_SECURE)
    response.set_cookie(
        "auth_token",
        token,
        httponly=True,
        samesite="Lax",
        max_age=COOKIE_MAX_AGE,
        secure=COOKIE_SECURE,
    )
    return response


def aplicar_cookie_owner(response, token):
    response.set_cookie("owner_token", token, httponly=True, samesite="Lax", max_age=COOKIE_MAX_AGE, secure=COOKIE_SECURE)
    return response


def registrar_sessao_aba(token):
    tab_key = secrets.token_urlsafe(24)
    cache.set(f"tab_auth:{tab_key}", token, TAB_SESSION_MAX_AGE)
    return tab_key


def resolver_sessao_empresa_por_token(token, require_active_empresa=False):
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    empresa_filters = {"id": payload["empresa_id"]}
    if require_active_empresa:
        empresa_filters["ativo"] = True
    empresa = Empresa.objects.filter(**empresa_filters).first()
    if not empresa:
        raise ValueError("empresa_invalida")

    principal_kind = payload.get("principal_kind")
    principal_id = payload.get("principal_id")
    if principal_kind == "usuario_empresa":
        principal = EmpresaUsuario.objects.filter(id=principal_id, empresa=empresa, ativo=True).first()
    else:
        principal = empresa
    if not principal:
        raise ValueError("principal_invalido")
    return payload, empresa, principal


def resolver_sessao_owner_por_token(token):
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    dono = DonoSaaS.objects.filter(id=payload.get("owner_id"), ativo=True).first()
    if not dono:
        raise ValueError("owner_invalido")
    return payload, dono


def empresa_autenticada_from_request(request):
    empresa_request = getattr(request, "empresa", None)
    if empresa_request:
        return empresa_request

    token = request.COOKIES.get("auth_token")
    if not token:
        return None

    try:
        payload, empresa, principal = resolver_sessao_empresa_por_token(token)
        if principal.sessao_ativa_chave and payload.get("session_key") != principal.sessao_ativa_chave:
            return None
        return empresa
    except Exception:
        return None


def dono_autenticado_from_request(request):
    dono_request = getattr(request, "dono_saas", None)
    if dono_request:
        return dono_request

    token = request.COOKIES.get("owner_token")
    if not token:
        return None

    try:
        payload, dono = resolver_sessao_owner_por_token(token)
        if dono.sessao_ativa_chave and payload.get("session_key") != dono.sessao_ativa_chave:
            return None
        return dono
    except Exception:
        return None


def limpar_sessao_empresa_por_token(token):
    try:
        payload, _empresa, principal = resolver_sessao_empresa_por_token(token)
        empresa_id = payload.get("empresa_id")
        device_id = payload.get("device_id")

        if principal and payload.get("session_key") == principal.sessao_ativa_chave:
            limpar_sessao_principal(principal)
        if empresa_id and device_id:
            DispositivoAutorizado.objects.filter(
                empresa_id=empresa_id,
                device_id=device_id,
                ativo=True,
            ).update(ativo=False)
    except Exception:
        return


def limpar_sessao_owner_por_token(token):
    try:
        payload, dono = resolver_sessao_owner_por_token(token)
        if dono and payload.get("session_key") == dono.sessao_ativa_chave:
            dono.sessao_ativa_chave = None
            dono.sessao_ativa_em = None
            dono.save(update_fields=["sessao_ativa_chave", "sessao_ativa_em"])
    except Exception:
        return
