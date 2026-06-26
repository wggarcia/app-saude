"""
Hospital — IA de Autorização Clínica (internação / cirurgia / exame de alta
complexidade), seguindo o mesmo motor de regras já validado em
views_plano_ia.py (plano.ia_autorizacao), adaptado ao contexto hospitalar.
"""
import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Avg
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from django.core.cache import cache

from .access_control import (
    api_requer_feature, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)
from .models import IAAutorizacaoClinica
from .views_dashboard import _empresa_autenticada, contexto_navegacao_setorial
from .views_hospital_ia_autorizacao_ml import inferir_autorizacao_clinica


def _empresa(request):
    return _empresa_autenticada(request)


def _ia_dict(ia):
    return {
        "id": ia.id,
        "paciente_nome": ia.paciente_nome,
        "tipo_solicitacao": ia.tipo_solicitacao,
        "tipo_solicitacao_label": dict(IAAutorizacaoClinica.TIPO_CHOICES).get(ia.tipo_solicitacao, ia.tipo_solicitacao),
        "procedimento": ia.procedimento,
        "cid10": ia.cid10,
        "urgente": ia.urgente,
        "decisao": ia.decisao,
        "decisao_label": dict(IAAutorizacaoClinica.DECISAO_CHOICES).get(ia.decisao, ia.decisao),
        "score_confianca": ia.score_confianca,
        "justificativa_ia": ia.justificativa_ia,
        "revisada_por": ia.revisada_por,
        "decisao_final": ia.decisao_final,
        "decisao_final_label": (
            dict(IAAutorizacaoClinica.DECISAO_CHOICES).get(ia.decisao_final, ia.decisao_final)
            if ia.decisao_final else None
        ),
        "criado_em": ia.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _analisar_solicitacao_fallback(tipo_solicitacao: str, procedimento: str, cid10: str, urgente: bool):
    """
    Motor de regras — usado apenas como rede de seguranca se o ensemble de ML
    real (views_hospital_ia_autorizacao_ml.inferir_autorizacao_clinica) falhar.
    """
    proc = (procedimento or "").strip().lower()
    cid = (cid10 or "").strip().upper()

    if urgente:
        return "aprovada", 0.97, (
            "Solicitação classificada como urgente — aprovação automática para "
            "garantir atendimento imediato, sujeita a auditoria retroativa. [motor de regras — fallback]"
        )

    KEYWORDS_NEGADA = [
        "experimental", "estético", "estetico", "estética", "estetica",
        "cosmético", "cosmetico", "cosmética", "cosmetica",
        "não padronizado", "nao padronizado", "off-label", "off label",
    ]
    for kw in KEYWORDS_NEGADA:
        if kw in proc:
            return "negada", 0.85, (
                f"Procedimento identificado como não coberto/experimental "
                f"(termo detectado: '{kw}'). Requer análise de cobertura. [motor de regras — fallback]"
            )

    if tipo_solicitacao == "exame_alta_complexidade" and cid.startswith("Z"):
        return "aprovada", 0.9, (
            f"Exame de alta complexidade com indicação preventiva/controle "
            f"(CID-10 {cid}). Aprovação automática conforme protocolo. [motor de regras — fallback]"
        )

    return "revisao", 0.6, (
        "Solicitação não enquadrada nas regras automáticas. "
        "Encaminhada para revisão da auditoria médica hospitalar. [motor de regras — fallback]"
    )


def _analisar_solicitacao(tipo_solicitacao: str, procedimento: str, cid10: str, urgente: bool, paciente_nome: str = "", empresa_id=None):
    """
    Analisa a solicitacao com o ensemble de ML real (RandomForest+GradientBoosting,
    views_hospital_ia_autorizacao_ml.py), treinado no historico real de decisoes
    desta unidade (com bootstrap sintetico ate acumular 30 decisoes reais). Cai
    no motor de regras simples apenas se a inferencia de ML falhar.
    """
    try:
        resultado = inferir_autorizacao_clinica({
            "cid10": cid10,
            "procedimento": procedimento,
            "tipo_solicitacao": tipo_solicitacao,
            "urgente": urgente,
            "paciente_nome": paciente_nome,
            "empresa_id": empresa_id,
        })
        return resultado["decisao"], resultado["score_confianca"], resultado["justificativa_ia"]
    except Exception:
        return _analisar_solicitacao_fallback(tipo_solicitacao, procedimento, cid10, urgente)


# ── Page ───────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.ia_autorizacao", "IA de Autorização Clínica")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_ia_autorizacao_page(request):
    return render(request, "hospital_ia_autorizacao.html", contexto_navegacao_setorial(request, "hospital"))


# ── API: listagem ──────────────────────────────────────────────────────────────

@api_requer_feature("hospital.ia_autorizacao")
def api_hospital_ia_autorizacoes(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method != "GET":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    qs = IAAutorizacaoClinica.objects.filter(empresa=empresa)
    decisao = request.GET.get("decisao")
    if decisao:
        qs = qs.filter(decisao=decisao)
    pendentes = request.GET.get("pendentes")
    if pendentes == "1":
        qs = qs.filter(decisao="revisao", decisao_final__isnull=True)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(paciente_nome__icontains=q)

    limit = min(int(request.GET.get("limit", 100)), 500)
    return JsonResponse({"autorizacoes": [_ia_dict(ia) for ia in qs[:limit]]})


# ── API: analisar nova solicitação ─────────────────────────────────────────────

_ML_RATE_LIMIT = 30  # max inferências por empresa por hora

@csrf_exempt
@api_requer_feature("hospital.ia_autorizacao")
def api_hospital_ia_analisar(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    # Rate limiting: max 30 inferências ML por empresa por hora
    rl_key = f"ml_rl_hosp:{empresa.id}"
    count = cache.get(rl_key, 0)
    if count >= _ML_RATE_LIMIT:
        return JsonResponse({"erro": "Limite de análises excedido (30/hora). Tente mais tarde."}, status=429)
    cache.set(rl_key, count + 1, timeout=3600)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    procedimento = (data.get("procedimento") or "").strip()
    if not paciente_nome or not procedimento:
        return JsonResponse({"erro": "paciente_nome e procedimento são obrigatórios"}, status=400)

    tipo_solicitacao = data.get("tipo_solicitacao", "procedimento")
    cid10 = (data.get("cid10") or "").strip()
    urgente = bool(data.get("urgente", False))

    decisao, score, justificativa = _analisar_solicitacao(
        tipo_solicitacao, procedimento, cid10, urgente, paciente_nome=paciente_nome, empresa_id=empresa.pk
    )

    ia = IAAutorizacaoClinica.objects.create(
        empresa=empresa,
        paciente_nome=paciente_nome,
        tipo_solicitacao=tipo_solicitacao,
        procedimento=procedimento,
        cid10=cid10,
        urgente=urgente,
        decisao=decisao,
        score_confianca=score,
        justificativa_ia=justificativa,
    )
    return JsonResponse({"autorizacao": _ia_dict(ia)}, status=201)


# ── API: revisão humana ─────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.ia_autorizacao")
def api_hospital_ia_revisar(request, ia_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    try:
        ia = IAAutorizacaoClinica.objects.get(id=ia_id, empresa=empresa)
    except IAAutorizacaoClinica.DoesNotExist:
        return JsonResponse({"erro": "Autorização não encontrada"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    decisao_final = data.get("decisao_final")
    if decisao_final not in ("aprovada", "negada"):
        return JsonResponse({"erro": "decisao_final deve ser 'aprovada' ou 'negada'"}, status=400)

    ia.decisao_final = decisao_final
    ia.revisada_por = (data.get("revisada_por") or "Auditor Médico").strip()
    ia.save()
    return JsonResponse({"autorizacao": _ia_dict(ia)})


# ── API: KPIs ───────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.ia_autorizacao")
def api_hospital_ia_kpis(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    qs = IAAutorizacaoClinica.objects.filter(empresa=empresa)
    total = qs.count()
    aprovadas = qs.filter(decisao="aprovada").count()
    negadas = qs.filter(decisao="negada").count()
    em_revisao = qs.filter(decisao="revisao", decisao_final__isnull=True).count()
    revisadas = qs.filter(decisao="revisao", decisao_final__isnull=False).count()
    processadas_hoje = qs.filter(criado_em__date=date.today()).count()
    avg_score = qs.aggregate(avg=Avg("score_confianca"))["avg"] or 0

    return JsonResponse({
        "total": total,
        "aprovadas": aprovadas,
        "negadas": negadas,
        "em_revisao": em_revisao,
        "revisadas_por_humano": revisadas,
        "processadas_hoje": processadas_hoje,
        "pct_aprovadas": round((aprovadas / total * 100), 1) if total else 0,
        "pct_negadas": round((negadas / total * 100), 1) if total else 0,
        "score_medio": round(avg_score * 100, 1),
    })
