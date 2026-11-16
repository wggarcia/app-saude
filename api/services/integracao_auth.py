"""
Autenticação de integrações externas (chave de API, token de integração SST).

Essas chamadas chegam sem sessão, então ainda não se sabe o tenant quando a
chave é procurada. As tabelas de chave/token estão sob RLS (tenant_isolation
por app.empresa_id): pela conexão "default" a busca não enxerga nenhuma linha,
ou só as do tenant que sobrou na conexão reaproveitada. Por isso a busca usa a
conexão "owner" e, achada a empresa, o RLS é fixado nela antes de qualquer
outra leitura ou escrita.
"""
import logging

from django.db.models import F
from django.utils import timezone

from .rls import alias_sem_rls, fixar_tenant

logger = logging.getLogger(__name__)


def _fixar_tenant(empresa):
    fixar_tenant(empresa.id)


def _chave_do_header(request, prefixo):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith(prefixo):
        return ""
    chave = auth[len(prefixo):].strip()
    return chave if 0 < len(chave) <= 200 else ""


def empresa_por_api_key(request, registrar_uso_endpoint=True):
    """Resolve (empresa, ApiKeyEmpresa) pelo header "Authorization: ApiKey <chave>".

    Retorna (None, None) se a chave faltar, não existir, estiver revogada ou a
    empresa estiver inativa. Em caso de sucesso o RLS já fica fixado na empresa.
    """
    from ..models import ApiKeyEmpresa, UsoApiEmpresa

    chave = _chave_do_header(request, "ApiKey ")
    if not chave:
        return None, None

    alias = alias_sem_rls()
    key = (
        ApiKeyEmpresa.objects.using(alias)
        .filter(ativa=True, chave_hash=ApiKeyEmpresa.hash_de(chave))
        .select_related("empresa")
        .first()
    )
    if not key or not key.empresa or not key.empresa.ativo:
        return None, None

    empresa = key.empresa
    _fixar_tenant(empresa)

    agora = timezone.now()
    ApiKeyEmpresa.objects.using(alias).filter(pk=key.pk).update(
        total_chamadas=F("total_chamadas") + 1, ultimo_uso_em=agora,
    )

    if registrar_uso_endpoint:
        ano_mes = agora.strftime("%Y-%m")
        endpoint = request.path[:120]
        uso, _ = UsoApiEmpresa.objects.get_or_create(
            empresa=empresa, api_key=key, ano_mes=ano_mes, endpoint=endpoint,
            defaults={"chamadas": 0},
        )
        UsoApiEmpresa.objects.filter(pk=uso.pk).update(chamadas=F("chamadas") + 1)

    return empresa, key


def empresa_por_token_sst(request, endpoint, hash_token):
    """Resolve (empresa, TokenIntegracaoSST) pelo header X-API-Token e registra o log.

    `hash_token` é a função de hash do token usada na criação (mantida no módulo
    de views da integração SST). Em caso de sucesso o RLS já fica fixado.
    """
    from ..models import LogIntegracaoSST, TokenIntegracaoSST

    valor = (request.META.get("HTTP_X_API_TOKEN", "") or request.headers.get("X-API-Token", "")).strip()
    if not valor or len(valor) > 200:
        return None, None

    alias = alias_sem_rls()
    token = (
        TokenIntegracaoSST.objects.using(alias)
        .filter(token_hash=hash_token(valor), ativo=True)
        .select_related("empresa")
        .first()
    )
    if not token or not token.empresa or not token.empresa.ativo:
        return None, None

    _fixar_tenant(token.empresa)
    TokenIntegracaoSST.objects.using(alias).filter(pk=token.pk).update(ultimo_uso=timezone.now())
    LogIntegracaoSST.objects.using(alias).create(
        token=token, endpoint=endpoint, metodo=request.method, status_code=200,
    )
    return token.empresa, token
