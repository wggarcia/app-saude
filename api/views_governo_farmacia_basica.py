"""
views_governo_farmacia_basica.py
Farmácia Básica UBS — estoque RENAME + dispensação.
"""
import json
from datetime import date

from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import FarmaciaBasicaItem, DispensacaoFarmaciaBasica
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
def governo_farmacia_basica_page(request):
    return render(request, "governo_farmacia_basica.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_basica_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = timezone.now().date()
    total_itens = FarmaciaBasicaItem.objects.filter(empresa=e).count()
    abaixo_minimo = FarmaciaBasicaItem.objects.filter(
        empresa=e, estoque_atual__lt=F("estoque_minimo")
    ).count()
    dispensacoes_hoje = DispensacaoFarmaciaBasica.objects.filter(
        empresa=e, dispensado_em__date=hoje
    ).count()
    return JsonResponse({
        "total_itens": total_itens,
        "abaixo_minimo": abaixo_minimo,
        "dispensacoes_hoje": dispensacoes_hoje,
    })


# ── Itens (estoque) ───────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_farmacia_basica_itens(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = FarmaciaBasicaItem.objects.filter(empresa=e)
        return JsonResponse({"itens": [_item_dict(i) for i in qs]})
    data = json.loads(request.body or "{}")
    item = FarmaciaBasicaItem.objects.create(
        empresa=e,
        rename_codigo=data.get("rename_codigo", ""),
        descricao=data.get("descricao", ""),
        apresentacao=data.get("apresentacao", ""),
        estoque_atual=int(data.get("estoque_atual", 0)),
        estoque_minimo=int(data.get("estoque_minimo", 0)),
        unidade_saude=data.get("unidade_saude", ""),
    )
    return JsonResponse({"id": item.id, "descricao": item.descricao}, status=201)


# ── Dispensação ───────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_farmacia_basica_dispensar(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    item_id = data.get("item_id")
    if not item_id:
        return JsonResponse({"erro": "item_id obrigatório"}, status=400)
    try:
        item = FarmaciaBasicaItem.objects.get(pk=item_id, empresa=e)
    except FarmaciaBasicaItem.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)
    quantidade = int(data.get("quantidade", 1))
    if quantidade <= 0:
        return JsonResponse({"erro": "Quantidade deve ser positiva"}, status=400)
    if item.estoque_atual < quantidade:
        return JsonResponse({"erro": "Estoque insuficiente", "estoque_atual": item.estoque_atual}, status=400)
    disp = DispensacaoFarmaciaBasica.objects.create(
        empresa=e,
        item=item,
        cns_cidadao=data.get("cns_cidadao", ""),
        paciente_nome=data.get("paciente_nome", ""),
        quantidade=quantidade,
        profissional=data.get("profissional", ""),
        receita_numero=data.get("receita_numero", ""),
    )
    # Decrement stock
    item.estoque_atual = max(0, item.estoque_atual - quantidade)
    item.save(update_fields=["estoque_atual", "atualizado_em"])
    return JsonResponse({"id": disp.id, "estoque_atual": item.estoque_atual}, status=201)


# ── Dispensações recentes ─────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_basica_dispensacoes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = DispensacaoFarmaciaBasica.objects.filter(empresa=e).select_related("item")[:50]
    return JsonResponse({"dispensacoes": [_disp_dict(d) for d in qs]})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_dict(i):
    return {
        "id": i.id,
        "rename_codigo": i.rename_codigo,
        "descricao": i.descricao,
        "apresentacao": i.apresentacao,
        "estoque_atual": i.estoque_atual,
        "estoque_minimo": i.estoque_minimo,
        "abaixo_minimo": i.estoque_atual < i.estoque_minimo,
        "unidade_saude": i.unidade_saude,
        "atualizado_em": i.atualizado_em.isoformat(),
    }


def _disp_dict(d):
    return {
        "id": d.id,
        "item_id": d.item_id,
        "item_descricao": d.item.descricao,
        "cns_cidadao": d.cns_cidadao,
        "paciente_nome": d.paciente_nome,
        "quantidade": d.quantidade,
        "profissional": d.profissional,
        "receita_numero": d.receita_numero,
        "dispensado_em": d.dispensado_em.isoformat(),
    }
