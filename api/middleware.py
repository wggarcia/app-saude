import json
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


def _rls_set_empresa(empresa_id: int) -> None:
    """
    Ativa o tenant boundary RLS para esta requisição.

    Usa is_local=False (SET SESSION) — necessário com psycopg3, cujo modo
    "autobegin" não garante persistência de SET LOCAL entre cursors dentro
    do mesmo atomic(). Deve ser chamado antes de qualquer query de banco
    que toque tabelas protegidas por RLS.

    Em SQLite (dev local) retorna silenciosamente sem erro.
    """
    from django.db import connection
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.empresa_id', %s, false)",
                [str(empresa_id)],
            )
    except Exception as exc:
        # Loga mas não quebra a requisição — o RLS do banco ainda protege
        logger.error(
            "RLS set_empresa falhou empresa_id=%s tipo=%s: %s",
            empresa_id, type(exc).__name__, exc,
        )
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
    remote_ip = request.META.get("REMOTE_ADDR", "unknown")
    if not getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        return remote_ip
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip() or remote_ip
    return remote_ip


def _login_identifier(request):
    payload = {}
    try:
        if request.content_type and "application/json" in request.content_type:
            bruto = request.body.decode("utf-8") if isinstance(request.body, (bytes, bytearray)) else (request.body or "")
            payload = json.loads(bruto or "{}")
        else:
            payload = request.POST
    except Exception:
        payload = {}

    email = str(payload.get("email") or "").strip().lower()
    if email:
        return f"email:{email}"
    cpf = "".join(ch for ch in str(payload.get("cpf") or "") if ch.isdigit())
    if cpf:
        return f"cpf:{cpf}"
    return ""


def _rate_limit_keys(request):
    keys = [f"login_attempts:ip:{_client_ip(request)}"]
    identifier = _login_identifier(request)
    if identifier:
        keys.append(f"login_attempts:principal:{identifier}")
    return keys


def _rate_limit_login(request):
    """Retorna True se o IP estiver bloqueado, False se ainda pode tentar."""
    from django.conf import settings
    if getattr(settings, "DJANGO_ENV", "") == "test" or "test" in sys.argv:
        return False
    now_ts = time.time()
    windows = {}
    for cache_key in _rate_limit_keys(request):
        attempts = cache.get(cache_key, [])
        attempts = [t for t in attempts if now_ts - t < _LOGIN_WINDOW_SECONDS]
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            return True
        windows[cache_key] = attempts
    for cache_key, attempts in windows.items():
        attempts.append(now_ts)
        cache.set(cache_key, attempts, _LOGIN_WINDOW_SECONDS)
    return False


def clear_login_rate_limit(request):
    """Limpa o histórico de tentativas após um login bem-sucedido."""
    from django.conf import settings
    if getattr(settings, "DJANGO_ENV", "") == "test" or "test" in sys.argv:
        return
    for cache_key in _rate_limit_keys(request):
        cache.delete(cache_key)


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
            "/api/platform/status",
            "/logout/",
            "/logout-governo/",
            "/logout-operacao/",
            "/cadastro/",
            "/apresentacao/",
            "/privacidade/",
            "/privacidade",        # sem barra — APPEND_SLASH do Django redireciona para /privacidade/
            "/termos/",
            "/termos",
            "/seguranca-lgpd/",
            "/seguranca-lgpd",
            "/metodologia/",
            "/metodologia",
            "/suporte/",
            "/suporte",
            "/sla/",
            "/sla",
            "/status/",
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
            "/assinatura/sst/",    # página pública de assinatura SST (link por e-mail)
            "/validar-assinatura/", # página pública de validação de assinatura SST
            "/sst/aso/portal/",    # portal público de visualização de ASO (LGPD — link por e-mail)
            "/api/gestao/integracoes/webhook/",  # webhook de sistemas de RH (auth própria via HMAC)
            "/api/farmacia/ifood/webhook/",      # webhook do iFood (auth própria via assinatura por farmácia)
            "/api/v1/dados",        # dados via API Key (BI/ERP externo)
            "/api/v1/plano-saude/dados",  # dados via API Key (Plano de Saúde — Enterprise)
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
            "/api/login-empresa-api",
            "/api/login-governo",
            "/api/operacao-central/login",
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

        if not token and auth:
            auth_norm = auth.strip()
            if auth_norm:
                scheme, sep, credentials = auth_norm.partition(" ")
                if scheme.lower() == "bearer":
                    token = credentials.strip() if sep else ""
        elif not token:
            token = request.COOKIES.get("auth_token")

        if not token:
            if request.path.startswith("/api/"):
                return JsonResponse({"erro": "não autenticado"}, status=401)
            return redirect("/")

        try:
            data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
            # ── RLS: define tenant boundary antes de qualquer query de DB.
            # O JWT já contém empresa_id sem precisar de query.
            # SET SESSION garante persistência com psycopg3 (sem is_local).
            _rls_set_empresa(data["empresa_id"])

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

        # Trial activation é permitido mesmo com empresa inativa
        if request.path == "/api/trial/ativar":
            return self.get_response(request)

        # Endpoints admin de manutenção: bypass de plano (auth por sessão)
        _ADMIN_BYPASS = {"/api/simular-focos", "/api/regeocodificar-focos", "/api/limpar-casos"}
        if request.path in _ADMIN_BYPASS:
            return self.get_response(request)

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


# ─────────────────────────────────────────────────────────────────────────────
# Fetch 401 interceptor — injeta script em toda resposta HTML para redirecionar
# ao login quando a sessão expirar (token JWT vencido).
# ─────────────────────────────────────────────────────────────────────────────

_FETCH_INTERCEPTOR = b"""
<script>
(function(){
  var _origFetch = window.fetch;
  window.fetch = function(url, opts){
    return _origFetch.apply(this, arguments).then(function(res){
      if(res.status === 401){
        var p = window.location.pathname;
        var destino;
        // Console operacional (dono) tem login proprio - nunca enviar para login-empresa
        if (p.indexOf('/console-operacional') === 0 || p.indexOf('/financeiro') === 0 ||
            p.indexOf('/governanca') === 0 || p.indexOf('/gtm') === 0 || p.indexOf('/operacao-central') === 0) {
          destino = '/operacao-central/';
        } else {
          var tipo = document.cookie.match(/tipo_conta=([^;]+)/);
          destino = (tipo && tipo[1]==='governo') ? '/login-governo/' : '/login-empresa/';
        }
        window.location.href = destino;
        return new Response(null, {status: 401});
      }
      return res;
    });
  };
})();
</script>
"""

class SegmentoAccessMiddleware:
    """
    Isolamento de segmento por prefixo de URL.

    A SolusCRT tem 5 ambientes healthtech/govtech distintos — cada cliente assina UM segmento.
    Um cliente de Farmácia não pode acessar endpoints de Hospital, e vice-versa.

    Esta middleware garante esse isolamento verificando o prefixo da URL contra
    o setor do plano contratado pela empresa autenticada.

    Prefixos → setor(es) permitido(s):
        /api/hospital/*    → hospital
        /api/farmacia/*    → farmacia
        /api/governo/*     → governo
        /api/plano-saude/* → plano_saude
        /api/plano/*       → plano_saude
        /api/sst/*         → empresa
        /api/rede/*        → rede, hospital, farmacia (endpoints de benchmarking/
                              transferências multi-unidade são compartilhados —
                              ver _verificar_acesso_rede em views_rede.py, que já
                              libera explicitamente os 3 setores)

    Rotas de infraestrutura (/api/governanca/, /api/financeiro/, etc.) são
    protegidas pelos seus próprios decorators (dono_autenticado_from_request)
    e NÃO são alteradas aqui.
    """

    # Mapa de prefixo URL → setor(es) permitido(s)
    _PREFIXO_SETOR = (
        ("/api/hospital/",    {"hospital"}),
        ("/api/farmacia/",    {"farmacia"}),
        ("/api/governo/",     {"governo"}),
        ("/api/plano-saude/", {"plano_saude"}),
        ("/api/plano/",       {"plano_saude"}),
        ("/api/sst/",         {"empresa"}),
        ("/api/rede/",        {"rede", "hospital", "farmacia"}),
    )

    # Subprefixos que são exceção dentro de /api/plano/. Eles servem ao
    # contrato da empresa autenticada, não ao segmento plano_saude.
    _EXCECOES_PLANO = (
        "/api/plano/features",
        "/api/plano/upgrade",
        "/api/planos-publicos",
        "/api/planos-saude",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        if any(path.startswith(exc) for exc in self._EXCECOES_PLANO):
            return self.get_response(request)

        # Determina se esta URL exige um setor específico
        setores_permitidos = None
        for prefixo, setores in self._PREFIXO_SETOR:
            if path.startswith(prefixo) or path == prefixo.rstrip("/"):
                setores_permitidos = setores
                break

        if setores_permitidos is None:
            # URL não está numa namespace de segmento — passa direto
            return self.get_response(request)

        # Se não há empresa autenticada, deixa o fluxo normal tratar (retornará 401)
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return self.get_response(request)

        # Verifica o setor da empresa
        from .access_control import get_setor
        setor_empresa = get_setor(empresa)

        if setor_empresa not in setores_permitidos:
            import json
            from django.http import JsonResponse
            setor_requerido = "/".join(sorted(setores_permitidos))
            return JsonResponse(
                {
                    "erro": (
                        f"Módulo '{setor_requerido}' não faz parte do seu plano. "
                        f"Seu segmento: '{setor_empresa}'. "
                        f"Cada cliente da SolusCRT acessa apenas o segmento contratado."
                    ),
                    "setor_empresa": setor_empresa,
                    "setor_requerido": setor_requerido,
                },
                status=403,
            )

        return self.get_response(request)


_PAGINAS_PUBLICAS_SEM_INTERCEPTOR = {
    "/privacidade/",
    "/termos/",
    "/seguranca-lgpd/",
    "/metodologia/",
    "/suporte/",
    "/sla/",
    "/status/",
}


class FetchAuthInterceptorMiddleware:
    """
    Injeta um interceptor de fetch em respostas HTML para redirecionar ao login
    quando qualquer chamada de API retornar 401 (sessão/token expirado).

    Páginas legais/públicas são excluídas para evitar que GTM ou outros scripts
    disparem um fetch que retorne 401 e redirecionem para o login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path in _PAGINAS_PUBLICAS_SEM_INTERCEPTOR:
            return response
        ct = response.get("Content-Type", "")
        if "text/html" in ct and hasattr(response, "content") and b"</body>" in response.content:
            response.content = response.content.replace(b"</body>", _FETCH_INTERCEPTOR + b"</body>", 1)
        return response
