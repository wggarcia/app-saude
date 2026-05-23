from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect, render

from .planos import detalhes_pacote
from .profile_access import (
    PERFIL_RH,
    PERFIL_TI,
    principal_tem_permissao,
    resolver_perfil_principal,
    texto_normalizado,
    usuario_tem_cargo_ti,
)
from .services.auth_session import dono_autenticado_from_request

TODOS_SETORES = ("empresa", "farmacia", "hospital", "governo", "rede", "plano_saude")


def get_setor(empresa):
    """Return the sector/module for this empresa based on its plan."""
    setor = detalhes_pacote(empresa.pacote_codigo).get("setor", "empresa")
    # Safety fallback: TIPO_GOVERNO accounts must never land on empresa sector
    if setor == "empresa" and getattr(empresa, "tipo_conta", "empresa") == "governo":
        return "governo"
    return setor


def _destino_gestao(setor):
    destinos = {
        "farmacia": "/farmacia/gestao/",
        "hospital": "/hospital/gestao/",
        "governo": "/governo/gestao/",
        "rede": "/rede/gestao/",
        "plano_saude": "/plano-saude/gestao/",
    }
    return destinos.get(setor, "/gestao/")


def _destino_operacao(setor):
    destinos = {
        "farmacia": "/dashboard-farmacia/",
        "hospital": "/dashboard-hospital/",
        "governo": "/dashboard-governo/",
        "plano_saude": "/dashboard-plano-saude/",
        "rede": "/rede/gestao/",
    }
    return destinos.get(setor, "/dashboard-empresa/")


def _destino_correto(setor):
    # Compat: mantem o nome usado por trechos antigos.
    return _destino_gestao(setor)


def destino_por_perfil(empresa, principal=None, prefer_operacao=False):
    """
    Resolve a landing route based on account sector + authenticated profile.

    prefer_operacao=True keeps classic dashboard destination for conta principal.
    """
    if not empresa:
        return "/login-empresa/"

    setor = get_setor(empresa)
    principal = principal or empresa
    acesso = resolver_perfil_principal(empresa, principal)

    if acesso["acesso_gerencia"]:
        if prefer_operacao:
            return _destino_operacao(setor)
        return _destino_gestao(setor)

    if acesso["perfil"] == PERFIL_RH:
        return "/usuarios/"

    if acesso["perfil"] == PERFIL_TI:
        return "/governo/plataforma/" if setor == "governo" else "/gestao/plataforma/"

    return _destino_operacao(setor)


def perfil_principal_request(request):
    empresa = getattr(request, "empresa", None)
    principal = getattr(request, "principal", None) or empresa
    return resolver_perfil_principal(empresa, principal)


def contexto_acesso_por_perfil(request):
    acesso = perfil_principal_request(request)
    return {
        "perfil_principal": acesso["perfil"],
        "acesso_gerencia": acesso["acesso_gerencia"],
        "acesso_rh": acesso["acesso_rh"],
        "acesso_ti": acesso["acesso_ti"],
        "acesso_operacao": acesso["acesso_operacao"],
        "mostrar_menu_ti": acesso["acesso_ti"] or acesso["acesso_gerencia"],
        "mostrar_menu_rh": acesso["acesso_rh"] or acesso["acesso_gerencia"],
        "mostrar_command_center": acesso["acesso_gerencia"],
    }


def _principal_tem_perfil(request, perfis):
    acesso = perfil_principal_request(request)
    if acesso["acesso_gerencia"]:
        return True
    return acesso["perfil"] in set(perfis)


def requer_perfis(*perfis):
    """Decorator for page views restricted to specific profiles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return redirect("/login-empresa/")
            principal = getattr(request, "principal", None) or empresa
            if not _principal_tem_perfil(request, perfis):
                return redirect(destino_por_perfil(empresa, principal, prefer_operacao=True))
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def api_requer_perfis(*perfis):
    """Decorator for API views restricted to specific profiles."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            if not _principal_tem_perfil(request, perfis):
                return JsonResponse(
                    {
                        "erro": "Acesso restrito por perfil. Use uma credencial autorizada para este modulo.",
                        "perfil_necessario": list(perfis),
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


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
                principal = getattr(request, "principal", None) or empresa
                return redirect(destino_por_perfil(empresa, principal, prefer_operacao=True))
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
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def requer_dono(view_func):
    """Decorator for operator-only page views. Requires DonoSaaS auth (owner_token cookie)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        dono = dono_autenticado_from_request(request)
        if not dono:
            empresa = getattr(request, "empresa", None)
            if empresa:
                principal = getattr(request, "principal", None) or empresa
                return redirect(destino_por_perfil(empresa, principal, prefer_operacao=True))
            return redirect("/operacao-central/")
        return view_func(request, *args, **kwargs)

    return wrapper


def api_requer_dono(view_func):
    """Decorator for operator-only API views. Returns 403 for tenant requests."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        dono = dono_autenticado_from_request(request)
        if not dono:
            return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapper


def _texto_normalizado(valor):
    return texto_normalizado(valor)


def _garantir_permissao_ti():
    try:
        from .models import RBACPermissao

        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo="plataforma_ti",
            defaults={
                "descricao": "Acesso exclusivo à Plataforma TI",
                "modulo": "ti",
            },
        )
        return permissao
    except Exception:
        return None


def _usuario_tem_cargo_ti(usuario):
    return usuario_tem_cargo_ti(usuario)


def _principal_tem_permissao(empresa, principal, permissao):
    return principal_tem_permissao(empresa, principal, permissao)


def _atribuir_permissao_ti_por_cargo(empresa, principal):
    if not empresa or not principal or principal.__class__.__name__ != "EmpresaUsuario":
        return False
    if not _usuario_tem_cargo_ti(principal):
        return False
    permissao = _garantir_permissao_ti()
    if not permissao:
        return False
    try:
        from .models import RBACAtribuicao

        atribuicao, criada = RBACAtribuicao.objects.get_or_create(
            empresa=empresa,
            usuario=principal,
            permissao=permissao,
            defaults={"concedido_por": "auto:cargo_ti", "ativo": True},
        )
        if not criada and not atribuicao.ativo:
            atribuicao.ativo = True
            atribuicao.save(update_fields=["ativo", "atualizado_em"])
        return True
    except Exception:
        return False


def _empresa_tem_responsavel_ti(empresa):
    if not empresa:
        return False
    try:
        from .models import RBACAtribuicao

        return RBACAtribuicao.objects.filter(
            empresa=empresa,
            permissao__codigo="plataforma_ti",
            ativo=True,
            usuario__ativo=True,
        ).exists()
    except Exception:
        return False


def pode_acessar_plataforma_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False

    principal = getattr(request, "principal", None) or empresa
    acesso = resolver_perfil_principal(empresa, principal)

    # Gerencia tem acesso total ao ambiente.
    if acesso["acesso_gerencia"]:
        return True

    if _principal_tem_permissao(empresa, principal, "plataforma_ti"):
        return True

    if _atribuir_permissao_ti_por_cargo(empresa, principal):
        return True

    return acesso["perfil"] == PERFIL_TI


def acesso_plataforma_ti_em_bootstrap(request):
    return False


def requer_plataforma_ti_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not pode_acessar_plataforma_ti(request):
            setor = get_setor(empresa)
            principal = getattr(request, "principal", None) or empresa
            return_url = destino_por_perfil(empresa, principal, prefer_operacao=True)
            return render(
                request,
                "plataforma_ti_restrita.html",
                {
                    "empresa_nome": empresa.nome,
                    "return_url": return_url,
                    "return_label": {
                        "farmacia": "Painel Farmacia",
                        "hospital": "Painel Hospital",
                        "plano_saude": "Painel Operadora",
                        "governo": "Painel Governo",
                    }.get(setor, "Central SST"),
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def api_requer_plataforma_ti(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not pode_acessar_plataforma_ti(request):
            return JsonResponse(
                {
                    "erro": "Acesso restrito à Plataforma TI. Use um login TI ou Gerencia autorizada.",
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def _principal_gestor_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    principal = getattr(request, "principal", None) or empresa
    acesso = resolver_perfil_principal(empresa, principal)
    return acesso["acesso_gerencia"]


def api_requer_plataforma_ti_ou_gestor(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not (pode_acessar_plataforma_ti(request) or _principal_gestor_ti(request)):
            return JsonResponse(
                {
                    "erro": "Acesso restrito à TI ou Gerencia autorizada.",
                },
                status=403,
            )
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
