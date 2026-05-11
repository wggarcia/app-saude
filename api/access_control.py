from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse
from .planos import detalhes_pacote

TODOS_SETORES = ("empresa", "farmacia", "hospital", "governo", "rede", "plano_saude")


def get_setor(empresa):
    """Return the sector/module for this empresa based on its plan."""
    return detalhes_pacote(empresa.pacote_codigo).get("setor", "empresa")


def _destino_correto(setor):
    destinos = {
        "farmacia": "/farmacia/gestao/",
        "hospital": "/hospital/gestao/",
        "governo": "/dashboard-governo/",
        "rede": "/rede/gestao/",
        "plano_saude": "/plano-saude/gestao/",
    }
    return destinos.get(setor, "/dashboard-empresa/")


def requer_setor(*setores):
    """Decorator for page views. Redirects to correct home if wrong module."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return redirect("/login-empresa/")
            setor = get_setor(empresa)
            if setor not in setores:
                return redirect(_destino_correto(setor))
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def api_requer_setor(*setores):
    """Decorator for API views. Returns 403 JSON if wrong module."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            setor = get_setor(empresa)
            if setor not in setores:
                return JsonResponse(
                    {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
                    status=403
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requer_dono(view_func):
    """Decorator for operator-only page views. Requires DonoSaaS auth (owner_token cookie)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .views_dashboard import _dono_autenticado
        dono = _dono_autenticado(request)
        if not dono:
            empresa = getattr(request, "empresa", None)
            if empresa:
                return redirect(_destino_correto(get_setor(empresa)))
            return redirect("/operacao-central/")
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_dono(view_func):
    """Decorator for operator-only API views. Returns 403 for tenant requests."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .views_dashboard import _dono_autenticado
        dono = _dono_autenticado(request)
        if not dono:
            return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def requer_permissao(permissao):
    """RBAC decorator — checks RBACAtribuicao for the authenticated principal."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            principal = getattr(request, "principal", None)
            if principal:
                try:
                    from .models import RBACAtribuicao
                    tem = RBACAtribuicao.objects.filter(
                        empresa=empresa,
                        usuario_id=principal.id,
                        permissao__codigo=permissao,
                        ativo=True,
                    ).exists()
                    if not tem:
                        return JsonResponse({"erro": f"Permissão necessária: {permissao}"}, status=403)
                except Exception:
                    pass  # tabela ainda não existe — deixa passar
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
