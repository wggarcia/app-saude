"""
views_governo_rag.py
RAG / RDQA / PAS — relatórios de gestão DigiSUS.
"""
import json
from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import RelatorioRAG
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import requer_setor, requer_operacao_page, requer_permissao_modulo


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def governo_rag_page(request):
    return render(request, "governo_rag_rdqa.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_rag_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = RelatorioRAG.objects.filter(empresa=e)
    total = qs.count()
    enviados = qs.filter(enviado_digisus=True).count()
    pendentes = total - enviados
    return JsonResponse({
        "total": total,
        "enviados": enviados,
        "pendentes": pendentes,
    })


# ── Lista ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_rag_lista(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = RelatorioRAG.objects.filter(empresa=e)
    tipo = request.GET.get("tipo")
    if tipo:
        qs = qs.filter(tipo=tipo)
    return JsonResponse({"relatorios": [_rag_dict(r) for r in qs[:200]]})


# ── Criar ─────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_rag_criar(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    r = RelatorioRAG.objects.create(
        empresa=e,
        tipo=data.get("tipo", "rag"),
        exercicio=int(data.get("exercicio", datetime.now().year)),
        quadrimestre=data.get("quadrimestre") or None,
        conteudo=data.get("conteudo", {}),
        enviado_digisus=False,
    )
    return JsonResponse({"id": r.id}, status=201)


# ── Atualizar ─────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_rag_atualizar(request, rag_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        r = RelatorioRAG.objects.get(pk=rag_id, empresa=e)
    except RelatorioRAG.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    if "conteudo" in data:
        r.conteudo = data["conteudo"]
    if "enviado_digisus" in data:
        r.enviado_digisus = bool(data["enviado_digisus"])
        if r.enviado_digisus and not r.enviado_em:
            r.enviado_em = timezone.now()
    r.save()
    return JsonResponse({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rag_dict(r):
    return {
        "id": r.id,
        "tipo": r.tipo,
        "tipo_label": r.get_tipo_display(),
        "exercicio": r.exercicio,
        "quadrimestre": r.quadrimestre,
        "enviado_digisus": r.enviado_digisus,
        "enviado_em": r.enviado_em.isoformat() if r.enviado_em else "",
        "conteudo": r.conteudo,
        "criado_em": r.criado_em.isoformat(),
        "atualizado_em": r.atualizado_em.isoformat(),
    }
