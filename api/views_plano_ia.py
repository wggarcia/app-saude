"""
Plano de Saúde — IA Autorização de Guias.
Motor de análise automática de guias médicas com revisão humana.
"""
import json
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Count, Avg
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .access_control import api_requer_gerencia, contexto_navegacao_setorial, requer_setor, requer_operacao_page, requer_permissao_modulo
from .models import IAAutorizacaoGuia
from .views_dashboard import _empresa_autenticada


# ── helpers ──────────────────────────────────────────────────────────────────

def _ps_auth(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return empresa, None


def _ia_dict(ia):
    return {
        "id": ia.id,
        "numero_guia": ia.numero_guia,
        "beneficiario": ia.beneficiario,
        "procedimento": ia.procedimento,
        "codigo_tuss": ia.codigo_tuss,
        "cid10": ia.cid10,
        "decisao": ia.decisao,
        "decisao_label": dict(IAAutorizacaoGuia.DECISAO_CHOICES).get(ia.decisao, ia.decisao),
        "score_confianca": ia.score_confianca,
        "justificativa_ia": ia.justificativa_ia,
        "revisada_por": ia.revisada_por,
        "decisao_final": ia.decisao_final,
        "decisao_final_label": (
            dict(IAAutorizacaoGuia.DECISAO_CHOICES).get(ia.decisao_final, ia.decisao_final)
            if ia.decisao_final else None
        ),
        "criado_em": ia.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _analisar_guia(procedimento: str, cid10: str):
    """
    Motor de análise simples baseado em regras:
    - CID10 iniciando com 'Z' (preventivo) → aprovada, confiança 0.95
    - Procedimento com palavras experimentais/estéticas → negada, 0.85
    - Demais → revisão humana, 0.60
    """
    cid = (cid10 or "").strip().upper()
    proc = (procedimento or "").strip().lower()

    KEYWORDS_NEGADA = [
        "experimental", "estético", "estetico", "estética", "estetica",
        "cosmético", "cosmetico", "cosmética", "cosmetica",
        "não padronizado", "nao padronizado", "off-label", "off label",
        "não coberto", "nao coberto",
    ]

    if cid.startswith("Z"):
        return "aprovada", 0.95, (
            f"Procedimento preventivo/controle (CID-10 {cid}). "
            "Aprovação automática conforme protocolo preventivo."
        )

    for kw in KEYWORDS_NEGADA:
        if kw in proc:
            return "negada", 0.85, (
                f"Procedimento identificado como não coberto pelo plano "
                f"(termo detectado: '{kw}'). Requer análise de cobertura contratual."
            )

    return "revisao", 0.60, (
        "Procedimento não enquadrado nas regras automáticas. "
        "Encaminhado para revisão pela equipe de auditoria médica."
    )


# ── page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.autorizacao")
def plano_ia_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_ia_autorizacao.html", ctx)


# ── API: listagem ─────────────────────────────────────────────────────────────

def api_ia_autorizacoes(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "GET":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    qs = IAAutorizacaoGuia.objects.filter(empresa=empresa)

    decisao = request.GET.get("decisao")
    if decisao:
        qs = qs.filter(decisao=decisao)

    revisada = request.GET.get("revisada")
    if revisada == "0":
        qs = qs.filter(decisao="revisao", decisao_final__isnull=True)

    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(numero_guia__icontains=busca) | qs.filter(beneficiario__icontains=busca)

    limit = min(int(request.GET.get("limit", 100)), 500)
    return JsonResponse({"autorizacoes": [_ia_dict(ia) for ia in qs[:limit]]})


# ── API: analisar nova guia ───────────────────────────────────────────────────

@csrf_exempt
def api_ia_analisar(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    numero_guia = (data.get("numero_guia") or "").strip()
    beneficiario = (data.get("beneficiario") or "").strip()
    procedimento = (data.get("procedimento") or "").strip()

    if not numero_guia or not procedimento:
        return JsonResponse({"erro": "numero_guia e procedimento são obrigatórios"}, status=400)

    cid10 = (data.get("cid10") or "").strip()
    codigo_tuss = (data.get("codigo_tuss") or "").strip()

    decisao, score, justificativa = _analisar_guia(procedimento, cid10)

    ia = IAAutorizacaoGuia.objects.create(
        empresa=empresa,
        numero_guia=numero_guia,
        beneficiario=beneficiario,
        procedimento=procedimento,
        codigo_tuss=codigo_tuss,
        cid10=cid10,
        decisao=decisao,
        score_confianca=score,
        justificativa_ia=justificativa,
    )
    return JsonResponse({"autorizacao": _ia_dict(ia)}, status=201)


# ── API: revisão humana ───────────────────────────────────────────────────────

@csrf_exempt
def api_ia_revisar(request, ia_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    try:
        ia = IAAutorizacaoGuia.objects.get(id=ia_id, empresa=empresa)
    except IAAutorizacaoGuia.DoesNotExist:
        return JsonResponse({"erro": "Autorização não encontrada"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    decisao_final = data.get("decisao_final")
    if decisao_final not in ("aprovada", "negada"):
        return JsonResponse({"erro": "decisao_final deve ser 'aprovada' ou 'negada'"}, status=400)

    revisada_por = (data.get("revisada_por") or "Auditor").strip()

    ia.decisao_final = decisao_final
    ia.revisada_por = revisada_por
    ia.save()
    return JsonResponse({"autorizacao": _ia_dict(ia)})


# ── API: KPIs ─────────────────────────────────────────────────────────────────

def api_ia_kpis(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    qs = IAAutorizacaoGuia.objects.filter(empresa=empresa)
    total = qs.count()

    aprovadas = qs.filter(decisao="aprovada").count()
    negadas = qs.filter(decisao="negada").count()
    em_revisao = qs.filter(decisao="revisao", decisao_final__isnull=True).count()
    revisadas = qs.filter(decisao="revisao", decisao_final__isnull=False).count()

    hoje = date.today()
    processadas_hoje = qs.filter(criado_em__date=hoje).count()

    pct_aprovadas = round((aprovadas / total * 100), 1) if total else 0
    pct_negadas = round((negadas / total * 100), 1) if total else 0
    pct_revisao = round(((em_revisao + revisadas) / total * 100), 1) if total else 0

    # Tempo médio de resposta (diferença entre criado_em e agora, só para as processadas)
    # Como não temos campo updated_at, simulamos com a média de score como proxy
    avg_score = qs.aggregate(avg=Avg("score_confianca"))["avg"] or 0

    return JsonResponse({
        "total": total,
        "aprovadas": aprovadas,
        "negadas": negadas,
        "em_revisao": em_revisao,
        "revisadas_por_humano": revisadas,
        "processadas_hoje": processadas_hoje,
        "pct_aprovadas": pct_aprovadas,
        "pct_negadas": pct_negadas,
        "pct_revisao": pct_revisao,
        "score_medio": round(avg_score * 100, 1),
    })
