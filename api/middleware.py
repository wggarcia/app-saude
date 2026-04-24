import jwt
import logging
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import redirect
from django.conf import settings
from django.utils import timezone
from .models import Empresa, EmpresaUsuario, DonoSaaS, DispositivoAutorizado

logger = logging.getLogger(__name__)
SESSION_IDLE_TIMEOUT = timedelta(minutes=15) if settings.DEBUG else timedelta(hours=8)
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)


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
        empresa=empresa,
        device_id=device_id,
        ativo=True,
    ).first()
    if not dispositivo:
        return False
    if timezone.now() - dispositivo.ultimo_acesso >= SESSION_TOUCH_INTERVAL:
        dispositivo.save(update_fields=["ultimo_acesso"])
    return True


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
            "/cadastro/",
            "/apresentacao/",
            "/privacidade/",
            "/termos/",
            "/seguranca-lgpd/",
            "/metodologia/",
            "/suporte/",
        }
        rotas_livres_prefixo = (
            "/api/login",
            "/api/operacao-central/login",
            "/api/registrar_empresa",
            "/api/public/",
            "/api/assinatura/",
            "/static/",
            "/media/",
        )

        if request.path in rotas_livres_exatas:
            return self.get_response(request)

        for rota in rotas_livres_prefixo:
            if request.path.startswith(rota):
                return self.get_response(request)

        owner_paths = (
            "/console-operacional/",
            "/api/operacao-central/",
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
                if dono.sessao_ativa_chave and owner_data.get("session_key") != dono.sessao_ativa_chave:
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

        # 🔐 AUTENTICAÇÃO JWT DO CLIENTE
        auth = request.headers.get("Authorization")
        token = None

        if auth and "Bearer" in auth:
            token = auth.split(" ")[1]
        else:
            token = request.COOKIES.get("auth_token")

        if not token:
            if request.path.startswith("/api/"):
                return JsonResponse({"erro": "não autenticado"}, status=401)
            return redirect("/")

        try:
            data = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=["HS256"]
            )

            empresa = Empresa.objects.get(id=data["empresa_id"])
            principal_kind = data.get("principal_kind")
            principal_id = data.get("principal_id")
            if principal_kind == "usuario_empresa":
                principal = EmpresaUsuario.objects.get(id=principal_id, empresa=empresa, ativo=True)
            else:
                principal = empresa

            if principal.sessao_ativa_chave and data.get("session_key") != principal.sessao_ativa_chave:
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

        except Exception as e:
            logger.warning("Token invalido no middleware: %s", e)
            if request.path.startswith("/api/"):
                return JsonResponse({"erro": "Token inválido"}, status=401)
            if request.path.startswith("/dashboard-governo/") or request.path.startswith("/contrato-governo/"):
                return redirect("/login-governo/")
            return redirect("/login-empresa/")

        # 💣 BLOQUEIO DE ACESSO SEM PAGAMENTO
        if not empresa.ativo:
            if request.path.startswith("/api/"):
                redirect_target = "/contrato-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/pagamento/"
                return JsonResponse({
                    "erro": "plano não ativo",
                    "redirect": redirect_target
                }, status=403)
            if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
                return redirect("/contrato-governo/")
            return redirect("/pagamento/")

        return self.get_response(request)
