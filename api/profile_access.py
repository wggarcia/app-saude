import unicodedata

PERFIL_GERENCIA = "gerencia"
PERFIL_RH = "rh"
PERFIL_TI = "ti"
PERFIL_OPERACAO = "operacao"


MARCADORES_TI = {
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

MARCADORES_RH = {
    "rh",
    "people",
    "talentos",
    "recrutamento",
    "dp",
}

MARCADORES_GERENCIA = {
    "gerente",
    "gerencia",
    "gestor",
    "diretor",
    "diretoria",
    "coordenador",
    "coordenacao",
    "supervisor",
    "lider",
    "head",
    "owner",
    "administrador",
    "admin",
    "ceo",
    "cfo",
    "coo",
    "cto",
}


def texto_normalizado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return texto.encode("ascii", "ignore").decode("ascii").lower().strip()


def palavras_normalizadas(valor):
    texto = texto_normalizado(valor).replace("/", " ").replace("-", " ")
    return {p for p in texto.split() if p}


def usuario_tem_cargo_ti(usuario):
    texto = texto_normalizado(getattr(usuario, "cargo", ""))
    if not texto:
        return False
    palavras = palavras_normalizadas(texto)
    if palavras & MARCADORES_TI:
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


def usuario_tem_cargo_rh(usuario):
    texto = texto_normalizado(getattr(usuario, "cargo", ""))
    if not texto:
        return False
    palavras = palavras_normalizadas(texto)
    if palavras & MARCADORES_RH:
        return True
    return any(
        trecho in texto
        for trecho in (
            "recursos humanos",
            "departamento pessoal",
            "gestao de pessoas",
            "gente e gestao",
            "people operations",
            "people ops",
        )
    )


def usuario_tem_cargo_gerencia(usuario):
    texto = texto_normalizado(getattr(usuario, "cargo", ""))
    if not texto:
        return False
    palavras = palavras_normalizadas(texto)
    if palavras & MARCADORES_GERENCIA:
        return True
    return any(
        trecho in texto
        for trecho in (
            "gerente de",
            "diretor de",
            "coordenador de",
            "supervisor de",
        )
    )


def principal_tem_permissao(empresa, principal, permissao):
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


def resolver_perfil_principal(empresa, principal):
    if not empresa:
        return {
            "perfil": PERFIL_OPERACAO,
            "acesso_gerencia": False,
            "acesso_rh": False,
            "acesso_ti": False,
            "acesso_operacao": False,
        }

    principal = principal or empresa

    acesso_gerencia = False
    acesso_rh = False
    acesso_ti = False

    if principal == empresa:
        acesso_gerencia = True
    elif principal.__class__.__name__ == "EmpresaUsuario":
        if getattr(principal, "is_admin", False):
            acesso_gerencia = True
        if usuario_tem_cargo_gerencia(principal):
            acesso_gerencia = True
        if usuario_tem_cargo_rh(principal):
            acesso_rh = True
        if usuario_tem_cargo_ti(principal) or principal_tem_permissao(empresa, principal, "plataforma_ti"):
            acesso_ti = True

    if acesso_gerencia:
        perfil = PERFIL_GERENCIA
    elif acesso_rh:
        perfil = PERFIL_RH
    elif acesso_ti:
        perfil = PERFIL_TI
    else:
        perfil = PERFIL_OPERACAO

    return {
        "perfil": perfil,
        "acesso_gerencia": acesso_gerencia,
        "acesso_rh": acesso_rh,
        "acesso_ti": acesso_ti,
        "acesso_operacao": True,
    }
