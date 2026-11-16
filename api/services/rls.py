"""
Utilitários de tenant RLS para código que roda antes de existir tenant na
requisição (rotas públicas por token, webhooks, logins).

Cada requisição começa sem tenant (_rls_limpar no EmpresaMiddleware). Pela
conexão "default", tabelas com empresa_id não mostram nenhuma linha nesse
estado. O padrão é: localizar o registro pela conexão sem RLS e, achada a
empresa, fixar o tenant antes de ler ou gravar qualquer outra coisa.
"""
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_OWNER = {"checked": False, "ok": True}


def alias_sem_rls():
    """"owner" quando o papel dono está acessível; senão "default" (dev/SQLite,
    onde não há RLS a contornar)."""
    if not _OWNER["checked"]:
        from ..models import ApiKeyEmpresa
        try:
            ApiKeyEmpresa.objects.using("owner").exists()
        except Exception:
            _OWNER["ok"] = False
            logger.warning("Conexão 'owner' indisponível — buscas pré-tenant seguem pela default.")
        _OWNER["checked"] = True
    return "owner" if _OWNER["ok"] else "default"


def objetos_sem_rls(model):
    """Manager do modelo pela conexão sem RLS — só para localizar o registro
    que identifica o tenant."""
    return model.objects.using(alias_sem_rls())


def fixar_tenant(empresa_id):
    from ..middleware import _rls_set_empresa
    if empresa_id:
        _rls_set_empresa(empresa_id)


def localizar_e_fixar(model, empresa_de, *, select_related=(), **filtros):
    """Localiza o registro que identifica o tenant pela conexão sem RLS, fixa o
    tenant e devolve o registro relido pela default.

    Reler importa: uma instância vinda de "owner" grava por "owner" (fora da
    transação da requisição e sem RLS) em qualquer save() que herde dela.
    `empresa_de(registro)` devolve o empresa_id do tenant.
    """
    qs = objetos_sem_rls(model).filter(**filtros)
    if select_related:
        qs = qs.select_related(*select_related)
    achado = qs.first()
    if achado is None:
        return None
    empresa_id = empresa_de(achado)
    if not empresa_id:
        return None
    fixar_tenant(empresa_id)
    qs = model.objects.all()
    if select_related:
        qs = qs.select_related(*select_related)
    return qs.filter(pk=achado.pk).first()


def tenant_atual():
    from django.db import connection
    return getattr(connection, "_rls_tenant", None)


@contextmanager
def preservar_tenant():
    """Garante que o tenant em vigor ao entrar volte a valer ao sair, mesmo que
    o bloco troque de tenant (ex.: leitura da camada pública da população)."""
    from ..middleware import _rls_limpar
    anterior = tenant_atual()
    try:
        yield
    finally:
        if tenant_atual() != anterior:
            if anterior is not None:
                fixar_tenant(anterior)
            else:
                _rls_limpar()


@contextmanager
def tenant_temporario(empresa_id):
    """Executa o bloco como outro tenant e devolve o tenant anterior ao sair."""
    with preservar_tenant():
        fixar_tenant(empresa_id)
        yield
