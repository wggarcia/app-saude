from django.apps import apps
from django.contrib import admin

from .models import Empresa, EmpresaUsuario, UnidadeRede, Rede


# ── Modelos críticos — admin curado ────────────────────────────────────────

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "email", "tipo_conta", "pacote_codigo", "ativo", "data_expiracao")
    list_filter = ("tipo_conta", "ativo", "pacote_codigo", "cortesia_ativa")
    search_fields = ("nome", "email", "codigo_acesso_corporativo")
    readonly_fields = ("senha",)
    list_per_page = 50


@admin.register(EmpresaUsuario)
class EmpresaUsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "nome", "email", "empresa", "perfil", "ativo", "is_admin", "criado_em")
    list_filter = ("perfil", "ativo", "is_admin")
    search_fields = ("nome", "email", "empresa__nome")
    readonly_fields = ("senha",)
    list_per_page = 50
    autocomplete_fields = ("empresa",)


@admin.register(Rede)
class RedeAdmin(admin.ModelAdmin):
    list_display = ("id", "nome")
    search_fields = ("nome",)


@admin.register(UnidadeRede)
class UnidadeRedeAdmin(admin.ModelAdmin):
    list_display = ("id", "nome_unidade", "empresa", "rede", "tipo", "cidade", "estado", "ativa")
    list_filter = ("tipo", "ativa", "estado")
    search_fields = ("nome_unidade", "codigo_unidade", "empresa__nome")
    autocomplete_fields = ("empresa", "rede")


# ── Demais modelos — registro automático genérico ──────────────────────────
# 294 modelos no app `api`; registrar um a um seria inviável de manter.
# Em vez disso, cada modelo recebe um ModelAdmin genérico com list_display,
# search_fields e list_filter inferidos pelos nomes de campo mais comuns —
# dá ao suporte uma tela de consulta/edição sem expor senhas em texto puro.

_CAMPOS_BUSCA_CANDIDATOS = (
    "nome", "nome_unidade", "nome_fantasia", "paciente_nome", "beneficiario_nome",
    "razao_social", "email", "cpf", "cnpj", "cpf_paciente", "numero_protocolo",
    "codigo", "titulo", "assunto", "descricao",
)
_CAMPOS_FILTRO_CANDIDATOS = ("ativo", "ativa", "status", "tipo", "perfil")
_CAMPOS_SENSIVEIS = ("senha", "password", "token", "api_key", "chave_secreta")


def _gerar_admin_generico(model):
    field_names = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}

    search_fields = tuple(c for c in _CAMPOS_BUSCA_CANDIDATOS if c in field_names)
    list_filter = tuple(c for c in _CAMPOS_FILTRO_CANDIDATOS if c in field_names)
    readonly_fields = tuple(c for c in _CAMPOS_SENSIVEIS if c in field_names)

    attrs = {
        "list_display": ("__str__", "pk"),
        "list_per_page": 50,
    }
    if search_fields:
        attrs["search_fields"] = search_fields
    if list_filter:
        attrs["list_filter"] = list_filter
    if readonly_fields:
        attrs["readonly_fields"] = readonly_fields

    return type(f"{model.__name__}AutoAdmin", (admin.ModelAdmin,), attrs)


for _model in apps.get_app_config("api").get_models():
    if _model in admin.site._registry:
        continue
    try:
        admin.site.register(_model, _gerar_admin_generico(_model))
    except admin.sites.AlreadyRegistered:
        pass
