from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse
from .planos import detalhes_pacote


def get_setor(empresa):
    """Return the sector/module for this empresa based on its plan."""
    return detalhes_pacote(empresa.pacote_codigo).get("setor", "empresa")


def _destino_correto(setor):
    destinos = {
        "farmacia": "/farmacia/gestao/",
        "hospital": "/hospital/gestao/",
        "governo": "/dashboard-governo/",
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
