import unicodedata
from functools import wraps
from django.shortcuts import redirect, render
from django.http import JsonResponse
from .planos import detalhes_pacote
from .services.auth_session import dono_autenticado_from_request

TODOS_SETORES = ("empresa", "farmacia", "hospital", "governo", "rede", "plano_saude")


def get_setor(empresa):
    """Return the sector/module for this empresa based on its plan."""
    setor = detalhes_pacote(empresa.pacote_codigo).get("setor", "empresa")
    # Safety fallback: TIPO_GOVERNO accounts must never land on empresa sector
    if setor == "empresa" and getattr(empresa, "tipo_conta", "empresa") == "governo":
        return "governo"
    return setor


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
        dono = dono_autenticado_from_request(request)
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
        dono = dono_autenticado_from_request(request)
        if not dono:
            return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def _texto_normalizado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return texto.encode("ascii", "ignore").decode("ascii").lower().strip()


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
    texto = _texto_normalizado(getattr(usuario, "cargo", ""))
    if not texto:
        return False
    palavras = set(texto.replace("/", " ").replace("-", " ").split())
    marcadores = {
        "ti",
        "tecnologia",
        "suporte",
        "infra",
        "infraestrutura",
        "devops",
        "sistemas",
        "seguranca",
        "security",
        "helpdesk",
    }
    if palavras & marcadores:
        return True
    return any(
        trecho in texto
        for trecho in (
            "seguranca da informacao",
            "seguranca informacao",
            "tecnologia da informacao",
            "tecnologia informacao",
        )
    )


def _principal_tem_permissao(empresa, principal, permissao):
    if not empresa or not principal:
        return False
    if principal.__class__.__name__ != "EmpresaUsuario":
        return False
    try:
        from .models import RBACAtribuicao
        return RBACAtribuicao.objects.filter(
            empresa=empresa,
            usuario_id=principal.id,
            permissao__codigo=permissao,
            ativo=True,
        ).exists()
    except Exception:
        return False


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

    if _principal_tem_permissao(empresa, principal, "plataforma_ti"):
        return True

    if _atribuir_permissao_ti_por_cargo(empresa, principal):
        return True

    return False


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
            return render(
                request,
                "plataforma_ti_restrita.html",
                {
                    "empresa_nome": empresa.nome,
                    "return_url": _destino_correto(setor),
                    "return_label": {
                        "farmacia": "Gestão Farmácia",
                        "hospital": "Gestão Hospitalar",
                        "plano_saude": "Gestão Operadora",
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
            return JsonResponse({
                "erro": "Acesso restrito à Plataforma TI. Entre com um usuário de TI (cargo TI/Suporte/Infra/DevOps) para continuar.",
            }, status=403)
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
