"""
views_plano_integracao.py
API de Integração (Plano de Saúde, feature Enterprise "plano.api_integracao")
— exporta beneficiários, sinistros e autorizações via ApiKeyEmpresa para
sistemas legados da operadora (ERP, BI, TISS gateway externo).

Reaproveita a mesma infraestrutura de chaves de api/views_gestao.py
(ApiKeyEmpresa/UsoApiEmpresa) — o que faltava era um payload de dados real
para o setor plano_saude (o endpoint genérico existente só exporta dados de SST).
"""
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.utils import timezone

from .access_control import empresa_tem_feature, get_setor
from .models import BeneficiarioPlano, IAAutorizacaoGuia, Sinistro
from .views_gestao import _empresa_por_api_key


def api_dados_plano_saude(request):
    """GET — exporta dados da operadora via API Key (Authorization: ApiKey <chave>)."""
    empresa, key = _empresa_por_api_key(request)
    if not empresa:
        return JsonResponse({"erro": "Authorization: ApiKey <chave> inválida"}, status=401)

    if get_setor(empresa) != "plano_saude":
        return JsonResponse({"erro": "Endpoint disponível apenas para operadoras de Plano de Saúde"}, status=403)

    if not empresa_tem_feature(empresa, "plano.api_integracao"):
        return JsonResponse({
            "erro": "API de Integração disponível apenas no plano Enterprise.",
            "feature_requerida": "plano.api_integracao",
            "upgrade_necessario": True,
        }, status=403)

    beneficiarios = list(
        BeneficiarioPlano.objects.filter(plano__empresa=empresa)
        .values(
            "id", "nome", "cpf", "numero_carteirinha", "situacao",
            "plano_tipo", "acomodacao", "data_inicio_vigencia", "data_fim_vigencia",
        )[:2000]
    )
    sinistros = list(
        Sinistro.objects.filter(empresa=empresa)
        .order_by("-data_abertura")
        .values(
            "id", "numero_sinistro", "tipo", "status", "cid",
            "valor_total", "valor_pago", "data_atendimento", "data_abertura",
        )[:1000]
    )
    autorizacoes_ia = list(
        IAAutorizacaoGuia.objects.filter(empresa=empresa)
        .order_by("-criado_em")
        .values(
            "id", "numero_guia", "beneficiario", "procedimento",
            "decisao", "decisao_final", "score_confianca", "criado_em",
        )[:1000]
    )

    return JsonResponse({
        "operadora": empresa.nome,
        "beneficiarios": beneficiarios,
        "sinistros": sinistros,
        "autorizacoes_ia": autorizacoes_ia,
        "gerado_em": timezone.now().isoformat(),
    }, encoder=DjangoJSONEncoder)
