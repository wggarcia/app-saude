"""
Hospital — Farmácia Hospitalar
  • FarmaciaHospitalarItem — estoque, controlados, alertas de mínimo
"""
import json
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_gerencia,
    get_setor,
    principal_pode_operacao_setorial,
    requer_setor,
    requer_operacao_page,
)
from .models import FarmaciaHospitalarItem
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _empresa(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "hospital":
        return JsonResponse({"erro": "Módulo não disponível para este plano."}, status=403)
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência hospitalar."}, status=403)
    return empresa


# ─── Serializer ───────────────────────────────────────────────────────────────

def _item_to_dict(i):
    abaixo_minimo = i.estoque_atual < i.estoque_minimo
    return {
        "id": i.id,
        "descricao": i.descricao,
        "codigo_interno": i.codigo_interno,
        "apresentacao": i.apresentacao,
        "principio_ativo": i.principio_ativo,
        "classe_terapeutica": i.classe_terapeutica,
        "controlado": i.controlado,
        "estoque_atual": float(i.estoque_atual),
        "estoque_minimo": float(i.estoque_minimo),
        "unidade": i.unidade,
        "abaixo_minimo": abaixo_minimo,
        "atualizado_em": i.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
def hospital_farmacia_page(request):
    return render(request, "hospital_farmacia_hospitalar.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Itens (lista) ───────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_hosp_itens(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = FarmaciaHospitalarItem.objects.filter(empresa=empresa)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(descricao__icontains=q) |
            Q(principio_ativo__icontains=q) |
            Q(codigo_interno__icontains=q)
        )

    if request.GET.get("controlado") == "1":
        qs = qs.filter(controlado=True)

    if request.GET.get("abaixo_minimo") == "1":
        from django.db.models import F
        qs = qs.filter(estoque_atual__lt=F("estoque_minimo"))

    return JsonResponse({"itens": [_item_to_dict(i) for i in qs]})


# ─── API: Novo item ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_farmacia_hosp_novo_item(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    descricao = (data.get("descricao") or "").strip()
    if not descricao:
        return JsonResponse({"erro": "descricao é obrigatório"}, status=400)

    try:
        estoque_atual = Decimal(str(data.get("estoque_atual", 0)))
        estoque_minimo = Decimal(str(data.get("estoque_minimo", 0)))
    except InvalidOperation:
        return JsonResponse({"erro": "Valores de estoque inválidos"}, status=400)

    item = FarmaciaHospitalarItem.objects.create(
        empresa=empresa,
        descricao=descricao,
        codigo_interno=data.get("codigo_interno", ""),
        apresentacao=data.get("apresentacao", ""),
        principio_ativo=data.get("principio_ativo", ""),
        classe_terapeutica=data.get("classe_terapeutica", ""),
        controlado=bool(data.get("controlado", False)),
        estoque_atual=estoque_atual,
        estoque_minimo=estoque_minimo,
        unidade=data.get("unidade", "un"),
    )
    return JsonResponse({"ok": True, "item": _item_to_dict(item)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_farmacia_hosp(request):
    if request.method == "POST":
        return api_farmacia_hosp_novo_item(request)
    return api_farmacia_hosp_itens(request)


# ─── API: Movimentar estoque (entrada/saída) ──────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_farmacia_hosp_atualizar_estoque(request, item_id):
    """
    POST body: { "tipo": "entrada"|"saida", "quantidade": <number> }
    """
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        item = FarmaciaHospitalarItem.objects.get(pk=item_id, empresa=empresa)
    except FarmaciaHospitalarItem.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    tipo = data.get("tipo", "")
    if tipo not in ("entrada", "saida"):
        return JsonResponse({"erro": "tipo deve ser 'entrada' ou 'saida'"}, status=400)

    try:
        quantidade = Decimal(str(data.get("quantidade", 0)))
    except InvalidOperation:
        return JsonResponse({"erro": "quantidade inválida"}, status=400)

    if quantidade <= 0:
        return JsonResponse({"erro": "quantidade deve ser positiva"}, status=400)

    if tipo == "entrada":
        item.estoque_atual += quantidade
    else:
        if item.estoque_atual < quantidade:
            return JsonResponse({"erro": "Estoque insuficiente para saída"}, status=400)
        item.estoque_atual -= quantidade

    item.save()
    return JsonResponse({"ok": True, "item": _item_to_dict(item)})


# ─── API: KPIs ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_farmacia_hosp_kpis(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    from django.db.models import F
    qs = FarmaciaHospitalarItem.objects.filter(empresa=empresa)

    total = qs.count()
    abaixo_minimo = qs.filter(estoque_atual__lt=F("estoque_minimo")).count()
    controlados = qs.filter(controlado=True).count()
    zerados = qs.filter(estoque_atual=0).count()

    return JsonResponse({
        "total_itens": total,
        "abaixo_minimo": abaixo_minimo,
        "controlados": controlados,
        "zerados": zerados,
    })
