import logging
import unicodedata
from functools import wraps
from django.shortcuts import redirect, render
from django.http import JsonResponse
from .planos import detalhes_pacote
from .services.auth_session import dono_autenticado_from_request

logger = logging.getLogger(__name__)

TODOS_SETORES = ("empresa", "farmacia", "hospital", "governo", "rede", "plano_saude")


# ─── Feature gating ──────────────────────────────────────────────────────────
#
# Uso em views:
#   @api_requer_feature("sst.esocial")
#   def minha_view(request): ...
#
# Verificação programática:
#   if empresa_tem_feature(request.empresa, "plano.coparticipacao"):
#       ...
#
# Verificação de limite:
#   if not dentro_do_limite(request.empresa, "max_unidades", unidades_atuais):
#       return JsonResponse({"erro": "Limite de unidades atingido"}, status=403)

def get_features(empresa) -> set:
    """Retorna o conjunto de features habilitadas para o plano desta empresa."""
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return set(pacote.get("features", []))


def get_limites(empresa) -> dict:
    """Retorna os limites numéricos do plano desta empresa."""
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return pacote.get("limites", {})


def empresa_tem_feature(empresa, feature: str) -> bool:
    """Verifica se a empresa tem acesso à feature pelo seu plano ativo."""
    return feature in get_features(empresa)


def dentro_do_limite(empresa, chave: str, valor_atual: int) -> bool:
    """
    Verifica se um valor está dentro do limite do plano.
    Retorna True se não houver limite definido (ilimitado).
    Exemplos de chave: 'max_usuarios', 'max_unidades', 'max_funcionarios'.
    """
    limite = get_limites(empresa).get(chave)
    if limite is None:
        return True  # sem limite declarado → ilimitado
    return valor_atual < limite


def api_requer_feature(feature: str):
    """
    Decorator para views de API. Retorna 403 se a feature não estiver no plano.
    Inclui detalhes no response para o frontend mostrar modal de upgrade.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            if not empresa_tem_feature(empresa, feature):
                pacote = detalhes_pacote(empresa.pacote_codigo)
                return JsonResponse({
                    "erro": "Funcionalidade não disponível no seu plano atual.",
                    "feature_requerida": feature,
                    "plano_atual": pacote.get("label", empresa.pacote_codigo),
                    "setor": pacote.get("setor", ""),
                    "upgrade_necessario": True,
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requer_feature(feature: str):
    """
    Decorator para views de página (HTML). Renderiza tela de bloqueio se a
    feature não estiver no plano, em vez de redirecionar.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return redirect("/login-empresa/")
            if not empresa_tem_feature(empresa, feature):
                pacote = detalhes_pacote(empresa.pacote_codigo)
                return render(request, "feature_restrita.html", {
                    "feature_requerida": feature,
                    "plano_atual": pacote.get("label", ""),
                    "setor": pacote.get("setor", ""),
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


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


def _cargo_tem_marcador_rh(cargo):
    texto = _texto_normalizado(cargo)
    if not texto:
        return False
    palavras = set(texto.replace("/", " ").replace("-", " ").split())
    if "rh" in palavras:
        return True
    return any(
        trecho in texto
        for trecho in (
            "recursos humanos",
            "departamento pessoal",
            "gestao de pessoas",
            "gente e gestao",
            "people",
            "talentos",
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
    return principal_tem_acesso_ti(empresa, principal)


def principal_tem_acesso_ti(empresa, principal):
    return _principal_tem_permissao(empresa, principal, "plataforma_ti")


def acesso_plataforma_ti_em_bootstrap(request):
    return False


def requer_plataforma_ti_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not (pode_acessar_plataforma_ti(request) or _gerencia_usuario_empresa(request)):
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
        if not (pode_acessar_plataforma_ti(request) or _gerencia_usuario_empresa(request)):
            return JsonResponse({
                "erro": "Acesso restrito à Plataforma TI. Entre com um usuário de TI ou gerência autorizada.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def _principal_gestor_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    principal = getattr(request, "principal", None) or empresa
    if principal == empresa:
        return True
    if principal.__class__.__name__ != "EmpresaUsuario":
        return False
    if getattr(principal, "is_admin", False):
        return True

    return _cargo_tem_marcador_rh(getattr(principal, "cargo", ""))


def principal_e_gerencia(request):
    """
    Detecta perfil de gerência de forma pragmática por cargo/permissões.
    Regra:
      - conta principal da empresa: gerência
      - usuário admin: gerência
      - cargos com marcadores de liderança: gerência
    """
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False

    principal = getattr(request, "principal", None) or empresa
    if principal == empresa:
        return True
    if getattr(principal, "is_admin", False):
        return True

    cargo = _texto_normalizado(getattr(principal, "cargo", ""))
    if not cargo:
        return False

    palavras = set(cargo.replace("/", " ").replace("-", " ").split())
    marcadores = {
        "gerencia",
        "gerente",
        "gestor",
        "coordenador",
        "supervisor",
        "diretor",
        "diretoria",
        "lider",
        "lideranca",
        "administrador",
    }
    if palavras & marcadores:
        return True

    return any(
        trecho in cargo
        for trecho in (
            "gerente",
            "gestor",
            "diretor",
            "lider de",
            "head",
            "chief",
            "coordenacao",
            "supervisao",
        )
    )


def principal_e_rh(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False

    principal = getattr(request, "principal", None) or empresa
    if principal == empresa:
        return False
    if getattr(principal, "is_admin", False):
        return False
    if principal.__class__.__name__ != "EmpresaUsuario":
        return False
    if principal_e_gerencia(request):
        return False
    return _cargo_tem_marcador_rh(getattr(principal, "cargo", ""))


def principal_e_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    principal = getattr(request, "principal", None) or empresa
    return principal_tem_acesso_ti(empresa, principal)


def principal_e_operacao(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    if principal_e_gerencia(request):
        return False
    if principal_e_rh(request):
        return False
    if principal_e_ti(request):
        return False
    return True


def principal_pode_operacao_setorial(request):
    """
    Acesso operacional setorial:
      - Operação (usuário de linha) pode operar o setor
      - Gerência pode operar e supervisionar o setor
    RH e TI ficam fora da operação por padrão (least privilege).
    """
    return principal_e_operacao(request) or principal_e_gerencia(request)


def _destino_ti_por_setor(setor):
    if setor == "governo":
        return "/governo/plataforma/"
    return "/ti/"


def _gerencia_usuario_empresa(request):
    if not principal_e_gerencia(request):
        return False
    principal = getattr(request, "principal", None)
    return bool(principal and principal.__class__.__name__ == "EmpresaUsuario")


def perfil_principal(request):
    if principal_e_gerencia(request):
        return "gerencia"
    if principal_e_rh(request):
        return "rh"
    if principal_e_ti(request):
        return "ti"
    return "operacao"


def destino_por_perfil(request, empresa=None):
    empresa_resolvida = empresa or getattr(request, "empresa", None)
    if not empresa_resolvida:
        return "/login-empresa/"
    setor = get_setor(empresa_resolvida)
    perfil = perfil_principal(request)
    if perfil == "gerencia":
        principal = getattr(request, "principal", None) or empresa_resolvida
        if principal == empresa_resolvida:
            return _destino_correto(setor)
        return "/gerencia/"
    if perfil == "rh":
        return "/rh/"
    if perfil == "ti":
        return _destino_ti_por_setor(setor)
    return _destino_correto(setor)


def principal_pode_configurar_ti(request):
    """
    RH/Gerência pode cadastrar e gerenciar credenciais TI.
    """
    return _principal_gestor_ti(request) or principal_e_gerencia(request) or principal_e_ti(request)


def contexto_navegacao_setorial(request, setor=None):
    """
    Contexto padrão de navegação por perfil para templates setoriais.
    """
    empresa = getattr(request, "empresa", None)
    setor_resolvido = setor or (get_setor(empresa) if empresa else "empresa")

    acesso_ti = principal_e_ti(request)
    acesso_gerencia = principal_e_gerencia(request)
    acesso_rh = principal_e_rh(request) or acesso_gerencia

    return {
        "setor_atual": setor_resolvido,
        "perfil_principal": perfil_principal(request),
        "acesso_ti": acesso_ti,
        "acesso_gerencia": acesso_gerencia,
        "acesso_rh": acesso_rh,
        "acesso_operacao": principal_e_operacao(request),
        "mostrar_link_ti": acesso_ti or acesso_gerencia,
        "mostrar_link_rh": acesso_rh,
        "mostrar_aba_gerencia": acesso_gerencia,
        "portal_ti_url": _destino_ti_por_setor(setor_resolvido),
        "gerencia_url": "/gerencia/",
        "rh_url": "/rh/",
    }


def requer_gerencia_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not principal_e_gerencia(request):
            return redirect(destino_por_perfil(request, empresa))
        return view_func(request, *args, **kwargs)
    return wrapper


def requer_rh_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not (principal_e_rh(request) or principal_e_gerencia(request)):
            return redirect(destino_por_perfil(request, empresa))
        return view_func(request, *args, **kwargs)
    return wrapper


def requer_operacao_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")

        if principal_e_gerencia(request) or principal_e_operacao(request):
            return view_func(request, *args, **kwargs)

        return redirect(destino_por_perfil(request, empresa))
    return wrapper


def api_requer_gerencia(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not principal_e_gerencia(request):
            return JsonResponse({
                "erro": "Acesso restrito à gerência.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_operacao_ou_gerencia(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({
                "erro": "Acesso restrito à operação/gerência.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_plataforma_ti_ou_gestor(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not (pode_acessar_plataforma_ti(request) or _principal_gestor_ti(request) or _gerencia_usuario_empresa(request)):
            return JsonResponse({
                "erro": "Acesso restrito à TI ou gestão autorizada.",
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
                except Exception as exc:
                    from django.db import ProgrammingError
                    if isinstance(exc.__cause__, ProgrammingError) or isinstance(exc, ProgrammingError):
                        # Tabela RBAC ainda não existe (migration incompleta) — deixa passar
                        pass
                    else:
                        logger.error("RBAC check falhou permissao=%s: %s", permissao, exc)
                        return JsonResponse({"erro": "Erro ao verificar permissão"}, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
