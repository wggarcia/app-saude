"""
views_ia.py — Endpoints REST do motor de IA epidemiológica
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• /api/ia/classificar       → classifica sintomas para um setor específico
• /api/ia/doencas           → lista todas as doenças modeladas
• /api/ia/sintomas          → lista todos os campos de sintoma disponíveis
• /api/ia/populacao         → análise agregada da empresa no setor
• /api/ia/calibracao        → relatório de acurácia da IA (por confirmações)
• /api/ia/urgencias         → verifica flags de urgência em sintomas enviados
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .classificador_doencas import (
    DOENCAS_BRASIL,
    TODOS_SINTOMAS,
    URGENCIA_ABSOLUTA,
    CONTEXTO_SETOR,
    classificar,
)
from .models import RegistroSintoma
from .utils_ia import (
    analisar_populacao_setor,
    listar_doencas,
    listar_sintomas,
    relatorio_calibracao,
    verificar_urgencias,
    obter_contexto_setor,
)
from .views_dashboard import _empresa_autenticada
from .access_control import get_setor


def _get_setor_empresa(empresa) -> str:
    """Deriva o setor canônico da empresa autenticada."""
    setor_raw = get_setor(empresa) or "governo"
    _mapa = {
        "plano_saude": "plano_saude",
        "farmacia": "farmacia",
        "hospital": "hospital",
        "governo": "governo",
        "rede": "farmacia",
        "sst": "sst",
        "empresa": "empresa",
    }
    return _mapa.get(setor_raw, "governo")


@csrf_exempt
def api_ia_classificar(request):
    """
    Classifica um conjunto de sintomas e retorna resultado completo.

    POST /api/ia/classificar
    Body: {
        "febre": true,
        "tosse": false,
        "dor_articular": true,
        "conjuntivite": true,
        "exantema": true,
        "intensidade_febre": "baixa",
        "setor": "hospital"   # opcional — usa o setor da empresa se omitido
    }
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "POST":
        try:
            dados = json.loads(request.body or "{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    elif request.method == "GET":
        # Suporte GET com query params para testes rápidos
        dados = {k: request.GET.get(k, "false").lower() in ("1", "true", "sim") for k in TODOS_SINTOMAS}
        dados["intensidade_febre"] = request.GET.get("intensidade_febre", "")
        dados["intensidade_articular"] = request.GET.get("intensidade_articular", "")
    else:
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    setor = dados.pop("setor", None) or _get_setor_empresa(empresa)
    resultado = classificar(dados, setor=setor)
    resultado["empresa_setor"] = setor
    return JsonResponse(resultado)


def api_ia_doencas(request):
    """
    GET /api/ia/doencas
    Lista todas as doenças modeladas no motor com metadados completos.
    Retorna: grupos, CID-10, vetores, sintomas com pesos, red flags, sazonalidade.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    setor = _get_setor_empresa(empresa)
    ctx = CONTEXTO_SETOR.get(setor, CONTEXTO_SETOR["governo"])
    prioridades = set(ctx.get("prioridade", []))

    doencas = []
    for nome, info in DOENCAS_BRASIL.items():
        doencas.append({
            "nome": nome,
            "grupo": info["grupo"],
            "cid10": info.get("cid10", ""),
            "vetor": info.get("vetor", ""),
            "descricao": info["descricao"],
            "sazonalidade_meses": info.get("sazonalidade", []),
            "red_flags": info.get("red_flags", []),
            "diferencial_vs": info.get("diferencial_vs", {}),
            "n_sintomas_modelados": len([k for k in info["sintomas"] if not k.startswith("_")]),
            "prioritaria_no_setor": nome in prioridades,
            "requer_notificacao": nome in ctx.get("alerta_notificacao", []),
        })

    doencas.sort(key=lambda x: (-x["prioritaria_no_setor"], x["nome"]))
    return JsonResponse({
        "total": len(doencas),
        "setor": setor,
        "doencas": doencas,
        "contexto_setor": ctx,
    })


def api_ia_sintomas(request):
    """
    GET /api/ia/sintomas
    Lista todos os campos de sintoma com labels e descrições.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .epidemiologia import SYMPTOM_LABELS
    urgencia_campos = {u[0] for u in URGENCIA_ABSOLUTA}

    sintomas = []
    for campo in TODOS_SINTOMAS:
        sintomas.append({
            "campo": campo,
            "label": SYMPTOM_LABELS.get(campo, campo.replace("_", " ").title()),
            "urgencia_absoluta": campo in urgencia_campos,
        })

    # Intensidades
    intensidades = [
        {"campo": "intensidade_febre", "label": "Intensidade da Febre",
         "opcoes": ["", "baixa", "moderada", "alta"],
         "descricao": "Ajuda a diferenciar dengue (alta) de Zika (baixa)"},
        {"campo": "intensidade_articular", "label": "Intensidade da Dor Articular",
         "opcoes": ["", "leve", "moderada", "intensa"],
         "descricao": "Artralgia intensa é patognomônica de Chikungunya"},
    ]

    return JsonResponse({
        "total_sintomas": len(sintomas),
        "sintomas": sintomas,
        "campos_intensidade": intensidades,
        "urgencias_absolutas": [
            {"campo": u[0], "titulo": u[1], "descricao": u[2]}
            for u in URGENCIA_ABSOLUTA
        ],
    })


def api_ia_populacao(request):
    """
    GET /api/ia/populacao?dias=30
    Análise epidemiológica agregada dos registros da empresa no setor correto.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from datetime import timedelta
    from django.utils import timezone

    dias = int(request.GET.get("dias", 30))
    setor = _get_setor_empresa(empresa)
    inicio = timezone.now() - timedelta(days=dias)

    qs = RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=inicio)
    resultado = analisar_populacao_setor(qs, setor=setor)
    resultado["janela_dias"] = dias
    resultado["setor"] = setor
    return JsonResponse(resultado)


def api_ia_calibracao(request):
    """
    GET /api/ia/calibracao
    Relatório de acurácia da IA comparando previsões com doenca_confirmada.
    Disponível apenas para setores governo e hospital (maior precisão diagnóstica).
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    setor = _get_setor_empresa(empresa)
    if setor not in ("governo", "hospital", "plano_saude"):
        return JsonResponse({
            "erro": "Relatório de calibração disponível para setores governo, hospital e plano_saude"
        }, status=403)

    qs = RegistroSintoma.objects.filter(empresa=empresa)
    resultado = relatorio_calibracao(qs)
    resultado["setor"] = setor
    return JsonResponse(resultado)


@csrf_exempt
def api_ia_urgencias(request):
    """
    POST /api/ia/urgencias
    Verifica flags de urgência em sintomas sem autenticar completamente.
    Retorna lista de urgências absolutas detectadas.
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    urgencias = verificar_urgencias(dados)
    return JsonResponse({
        "urgencias": urgencias,
        "tem_urgencia": len(urgencias) > 0,
        "safeguard": "Não substitui avaliação médica. Procure atendimento imediato se houver sintomas graves.",
    })
