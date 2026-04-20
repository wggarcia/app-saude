from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.utils import timezone

from .models import AuditoriaInstitucional, FonteOficialAgregado, RegistroSintoma


DADOLOGIA_CAMADAS = [
    {
        "id": "cidadao",
        "nome": "Relatos da populacao",
        "descricao": "Sinais anonimos enviados pelo app, uteis como alerta precoce e radar territorial.",
        "confianca": "variavel",
        "uso": "deteccao antecipada, crescimento local, calor territorial",
        "limite": "nao confirma surto sozinho e pode conter vieses de adesao ou envio repetido",
    },
    {
        "id": "oficial",
        "nome": "Fontes oficiais",
        "descricao": "Dados agregados de fontes publicas e institucionais como IBGE, Fiocruz, OpenDataSUS e DATASUS.",
        "confianca": "alta",
        "uso": "validacao, incidencia/prevalencia, historico e comparacao por 100 mil habitantes",
        "limite": "pode ter atraso de publicacao e revisoes posteriores",
    },
    {
        "id": "ia_estimativa",
        "nome": "Estimativas da IA",
        "descricao": "Classificacao probabilistica e leitura de tendencia a partir dos sinais disponiveis.",
        "confianca": "estimada",
        "uso": "priorizacao, triagem gerencial e apoio a decisao",
        "limite": "nao substitui investigacao epidemiologica ou diagnostico medico",
    },
    {
        "id": "institucional",
        "nome": "Registros institucionais",
        "descricao": "Dados de empresas, hospitais, farmacias, laboratorios e governo quando integrados.",
        "confianca": "contratual",
        "uso": "planejamento de estoque, leitos, atendimento e resposta local",
        "limite": "depende da qualidade e periodicidade de cada integracao",
    },
]


def registrar_auditoria_institucional(request, acao, objeto=None, detalhes=None):
    empresa = getattr(request, "empresa", None)
    principal = getattr(request, "principal", None)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    principal_nome = ""
    if principal:
        principal_nome = getattr(principal, "nome", "") or getattr(principal, "email", "") or str(getattr(principal, "id", ""))

    AuditoriaInstitucional.objects.create(
        empresa=empresa,
        principal_tipo=principal.__class__.__name__ if principal else "sistema",
        principal_id=str(getattr(principal, "id", "")) if principal else "",
        principal_nome=principal_nome,
        acao=acao,
        objeto_tipo=objeto.__class__.__name__ if objeto else "",
        objeto_id=str(getattr(objeto, "id", "")) if objeto else "",
        ip=ip or None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        detalhes=detalhes or {},
    )


def api_metodologia_epidemiologica(request):
    return JsonResponse({
        "nome": "SolusCRT Saude - metodologia de sala de controle",
        "principio": "Separar sinal precoce, fonte oficial, estimativa IA e alerta confirmado.",
        "camadas_de_dados": DADOLOGIA_CAMADAS,
        "regras_de_confianca": [
            "Relato cidadao e sinal precoce, nao confirmacao clinica.",
            "Fonte oficial valida historico, incidencia, prevalencia e taxas por 100 mil habitantes.",
            "IA prioriza risco e probabilidade, mas exige revisao humana em comunicados publicos.",
            "Alertas governamentais publicados exigem trilha de auditoria, status e responsavel.",
        ],
        "limites_eticos": [
            "Nao fornecer diagnostico medico individual.",
            "Nao expor dados pessoais ou localizacao individual da populacao.",
            "Nao publicar alerta critico sem contexto, justificativa e possibilidade de revogacao.",
        ],
    })


def api_matriz_decisao(request):
    agora = timezone.now()
    atual = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(days=7))
    anterior = RegistroSintoma.objects.filter(
        data_registro__gte=agora - timedelta(days=14),
        data_registro__lt=agora - timedelta(days=7),
    )
    atual_total = atual.count()
    anterior_total = anterior.count()
    crescimento = 0.0
    if anterior_total:
        crescimento = round(((atual_total - anterior_total) / anterior_total) * 100, 2)
    elif atual_total:
        crescimento = 100.0

    suspeitos = atual.filter(suspeito=True).count()
    confianca_media = round(float(atual.aggregate(media=Avg("confianca"))["media"] or 0), 2)
    oficiais = FonteOficialAgregado.objects.count()
    origem = (
        atual.values("origem_dado")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    recomendacoes = []
    if crescimento >= 50 or atual_total >= 500:
        recomendacoes.append("governo: ativar sala de situacao e revisar alerta publico.")
        recomendacoes.append("hospitais: preparar triagem e plano de contingencia.")
        recomendacoes.append("farmacias: revisar estoque de itens relacionados ao grupo dominante.")
    elif crescimento >= 15 or atual_total >= 100:
        recomendacoes.append("governo: intensificar vigilancia territorial e comunicacao preventiva.")
        recomendacoes.append("hospitais: acompanhar demanda espontanea e equipe de retaguarda.")
        recomendacoes.append("farmacias: monitorar giro de produtos e reposicao regional.")
    else:
        recomendacoes.append("manter vigilancia ativa e atualizacao das fontes oficiais.")

    return JsonResponse({
        "janela": "7 dias comparado aos 7 dias anteriores",
        "indicadores": {
            "registros_7d": atual_total,
            "registros_7d_anteriores": anterior_total,
            "crescimento_percentual": crescimento,
            "suspeitos_7d": suspeitos,
            "confianca_media": confianca_media,
            "agregados_oficiais": oficiais,
        },
        "composicao_dados": [
            {"origem": item["origem_dado"], "total": item["total"]}
            for item in origem
        ],
        "recomendacoes": recomendacoes,
        "regras": {
            "baixo": "crescimento baixo e poucos registros",
            "atencao": "crescimento positivo ou sinais concentrados",
            "alto": "crescimento forte, volume alto ou baixa confianca exigindo revisao",
        },
    })


def api_auditoria_institucional(request):
    registros = AuditoriaInstitucional.objects.select_related("empresa")[:100]
    return JsonResponse({
        "auditoria": [
            {
                "id": item.id,
                "empresa": item.empresa.nome if item.empresa else None,
                "principal_tipo": item.principal_tipo,
                "principal_nome": item.principal_nome,
                "acao": item.acao,
                "objeto_tipo": item.objeto_tipo,
                "objeto_id": item.objeto_id,
                "detalhes": item.detalhes,
                "criado_em": item.criado_em.isoformat(),
            }
            for item in registros
        ]
    })
