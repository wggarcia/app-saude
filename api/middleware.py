import jwt
import logging
import sys
import time
from datetime import timedelta
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect
from django.conf import settings
from django.utils import timezone
from .models import Empresa, EmpresaUsuario, DonoSaaS, DispositivoAutorizado

logger = logging.getLogger(__name__)
SESSION_IDLE_TIMEOUT = timedelta(minutes=15) if settings.DEBUG else timedelta(hours=8)
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)
COOKIE_MAX_AGE = 7 * 24 * 60 * 60

# Rate limiting: max tentativas de login por IP
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300  # 5 minutos


def _sessao_expirada(principal):
    if not principal.sessao_ativa_em:
        return False
    return timezone.now() - principal.sessao_ativa_em > SESSION_IDLE_TIMEOUT


def _encerrar_sessao_principal(principal):
    update_fields = ["sessao_ativa_chave", "sessao_ativa_em"]
    principal.sessao_ativa_chave = None
    principal.sessao_ativa_em = None
    if hasattr(principal, "sessao_ativa_device_id"):
        principal.sessao_ativa_device_id = None
        update_fields.append("sessao_ativa_device_id")
    principal.save(update_fields=update_fields)


def _touch_sessao_principal(principal):
    if not principal.sessao_ativa_em or timezone.now() - principal.sessao_ativa_em >= SESSION_TOUCH_INTERVAL:
        principal.sessao_ativa_em = timezone.now()
        principal.save(update_fields=["sessao_ativa_em"])


def _touch_dispositivo_empresa(empresa, device_id):
    if not device_id:
        return True
    dispositivo = DispositivoAutorizado.objects.filter(
        empresa=empresa, device_id=device_id, ativo=True,
    ).first()
    if not dispositivo:
        return False
    if timezone.now() - dispositivo.ultimo_acesso >= SESSION_TOUCH_INTERVAL:
        dispositivo.save(update_fields=["ultimo_acesso"])
    return True


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_login(request):
    """Retorna True se o IP estiver bloqueado, False se ainda pode tentar."""
    from django.conf import settings
    if getattr(settings, "DJANGO_ENV", "") == "test" or "test" in sys.argv:
        return False
    ip = _client_ip(request)
    cache_key = f"login_attempts:{ip}"
    attempts = cache.get(cache_key, [])
    now_ts = time.time()
    # Limpa tentativas fora da janela
    attempts = [t for t in attempts if now_ts - t < _LOGIN_WINDOW_SECONDS]
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        return True
    attempts.append(now_ts)
    cache.set(cache_key, attempts, _LOGIN_WINDOW_SECONDS)
    return False


def _plano_expirado(empresa):
    if empresa.data_expiracao and empresa.data_expiracao < timezone.now():
        if empresa.ativo:
            empresa.ativo = False
            empresa.save(update_fields=["ativo"])
        return True
    return False


class EmpresaMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        rotas_livres_exatas = {
            "/",
            "/login-empresa/",
            "/login-governo/",
            "/operacao-central/",
            "/contrato-governo/",
            "/pagamento/",
            "/sucesso/",
            "/erro/",
            "/pendente/",
            "/logout/",
            "/logout-governo/",
            "/logout-operacao/",
            "/cadastro/",
            "/apresentacao/",
            "/privacidade/",
            "/termos/",
            "/seguranca-lgpd/",
            "/metodologia/",
            "/suporte/",
            "/solicitar-reset-senha/",
            "/reset-senha-sucesso/",
        }
        rotas_livres_prefixo = (
            "/redefinir-senha/",
            "/api/funcionario/",   # portal do trabalhador — auth própria via Bearer
            "/api/funcionario",
            "/api/login",
            "/api/operacao-central/login",
            "/api/registrar_empresa",
            "/api/corporativo/",
            "/api/corporativo/mobile/",
            "/api/colaborador-mobile/",
            "/api/public/",
            "/api/assinatura/",
            "/api/planos-publicos",
            "/api/status-pagamento",
            "/api/webhook",
            "/colaborador/c/",
            "/mobile/c/",
            "/colaborador-mobile/c/",
            "/static/",
            "/media/",
        )

        # Rate limiting apenas nas rotas de login
        rotas_login = (
            "/api/login",
            "/api/login-empresa",
            "/api/login-governo",
        )
        if any(request.path.startswith(r) for r in rotas_login):
            if _rate_limit_login(request):
                return JsonResponse({
                    "status": "erro",
                    "mensagem": "Muitas tentativas de acesso. Aguarde alguns minutos.",
                    "codigo": "rate_limit",
                }, status=429)

        if request.path in rotas_livres_exatas:
            return self.get_response(request)

        for rota in rotas_livres_prefixo:
            if request.path.startswith(rota):
                return self.get_response(request)

        owner_paths = (
            "/console-operacional/",
            "/api/operacao/",
            "/api/operacao-central/",
            "/financeiro/",
            "/governanca/",
            "/gtm/",
        )

        if any(request.path.startswith(path) for path in owner_paths):
            owner_token = request.COOKIES.get("owner_token")
            if not owner_token:
                if request.path.startswith("/api/"):
                    return JsonResponse({"erro": "não autenticado"}, status=401)
                return redirect("/operacao-central/")

            try:
                owner_data = jwt.decode(owner_token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
                dono = DonoSaaS.objects.get(id=owner_data["owner_id"], ativo=True)
                if owner_data.get("session_key") != dono.sessao_ativa_chave:
                    if request.path.startswith("/api/"):
                        return JsonResponse({"erro": "sessão operacional encerrada"}, status=401)
                    return redirect("/operacao-central/")
                if _sessao_expirada(dono):
                    _encerrar_sessao_principal(dono)
                    if request.path.startswith("/api/"):
                        return JsonResponse({"erro": "sessão operacional encerrada"}, status=401)
                    return redirect("/operacao-central/")
                _touch_sessao_principal(dono)
                request.dono_saas = dono
                return self.get_response(request)
            except Exception:
                if request.path.startswith("/api/"):
                    return JsonResponse({"erro": "Token operacional inválido"}, status=401)
                return redirect("/operacao-central/")

        # 🔐 AUTENTICAÇÃO JWT
        auth = request.headers.get("Authorization")
        token = None
        token_from_tab = False

        tab_key = (request.GET.get("tab") or "").strip()
        if tab_key:
            cached_token = cache.get(f"tab_auth:{tab_key}")
            if cached_token:
                token = cached_token
                token_from_tab = True

        if not token and auth and "Bearer" in auth:
            token = auth.split(" ")[1]
        elif not token:
            token = request.COOKIES.get("auth_token")

        if not token:
            if request.path.startswith("/api/"):
                return JsonResponse({"erro": "não autenticado"}, status=401)
            return redirect("/")

        try:
            data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])

            empresa = Empresa.objects.get(id=data["empresa_id"])
            principal_kind = data.get("principal_kind")
            principal_id = data.get("principal_id")
            if principal_kind == "usuario_empresa":
                principal = EmpresaUsuario.objects.get(id=principal_id, empresa=empresa, ativo=True)
            else:
                principal = empresa

            if data.get("session_key") != principal.sessao_ativa_chave:
                if request.path.startswith("/api/"):
                    return JsonResponse({"erro": "sessão encerrada ou substituída"}, status=401)
                login_target = "/login-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/login-empresa/"
                return redirect(login_target)

            if _sessao_expirada(principal):
                _encerrar_sessao_principal(principal)
                if request.path.startswith("/api/"):
                    return JsonResponse({"erro": "sessão expirada"}, status=401)
                login_target = "/login-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/login-empresa/"
                return redirect(login_target)

            if not _touch_dispositivo_empresa(empresa, data.get("device_id")):
                _encerrar_sessao_principal(principal)
                if request.path.startswith("/api/"):
                    return JsonResponse({"erro": "dispositivo revogado ou inválido"}, status=401)
                login_target = "/login-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/login-empresa/"
                return redirect(login_target)

            _touch_sessao_principal(principal)
            request.empresa = empresa
            request.principal = principal
            if token_from_tab:
                request._tab_auth_token = token

        except Exception as e:
            logger.warning("Token invalido no middleware: %s", e)
            if request.path.startswith("/api/"):
                return JsonResponse({"erro": "Token inválido"}, status=401)
            if request.path.startswith("/dashboard-governo/") or request.path.startswith("/contrato-governo/"):
                return redirect("/login-governo/")
            return redirect("/login-empresa/")

        # 💣 BLOQUEIO: plano vencido
        if _plano_expirado(empresa) or not empresa.ativo:
            if request.path.startswith("/api/"):
                redirect_target = "/contrato-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/pagamento/"
                return JsonResponse({"erro": "plano não ativo", "redirect": redirect_target}, status=403)
            if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
                return redirect("/contrato-governo/")
            return redirect("/pagamento/")

        response = self.get_response(request)
        if getattr(request, "_tab_auth_token", None):
            response.set_cookie(
                "auth_token",
                request._tab_auth_token,
                httponly=True,
                samesite="Lax",
                max_age=COOKIE_MAX_AGE,
                secure=not settings.DEBUG,
            )
            response.set_cookie(
                "empresa_id",
                str(empresa.id),
                samesite="Lax",
                max_age=COOKIE_MAX_AGE,
                secure=not settings.DEBUG,
            )
            response.set_cookie(
                "tipo_conta",
                empresa.tipo_conta,
                samesite="Lax",
                max_age=COOKIE_MAX_AGE,
                secure=not settings.DEBUG,
            )
        return response
