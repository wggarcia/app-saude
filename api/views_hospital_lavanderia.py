"""
Hospital — Lavanderia e Rouparia Hospitalar
  • Cadastro de itens de roupa (ItemRoupa)
  • Registro de ciclos de entrada/saída (CicloLavanderia)
  • Saldo por setor e KPIs operacionais
"""
import json
import logging
from datetime import date

from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _get_lavanderia_models():
    from .models import ItemRoupa, CicloLavanderia
    return ItemRoupa, CicloLavanderia


# ── Página ────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.operacional", "Lavanderia")
@requer_operacao_page
@requer_permissao_modulo("hospital.operacional")
def hospital_lavanderia_page(request):
    return render(request, "hospital_lavanderia.html")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_to_dict(item):
    return {
        "id": item.id,
        "descricao": item.descricao,
        "quantidade_total": item.quantidade_total,
        "quantidade_disponivel": item.quantidade_disponivel,
        "setor": item.setor,
        "ativo": item.ativo,
        "criado_em": item.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _ciclo_to_dict(ciclo):
    return {
        "id": ciclo.id,
        "item_id": ciclo.item_id,
        "item_descricao": ciclo.item.descricao,
        "quantidade": ciclo.quantidade,
        "tipo": ciclo.tipo,
        "tipo_display": ciclo.get_tipo_display(),
        "setor_origem": ciclo.setor_origem,
        "responsavel": ciclo.responsavel,
        "observacoes": ciclo.observacoes,
        "data_registro": ciclo.data_registro.strftime("%d/%m/%Y %H:%M"),
    }


# ── Itens de Roupa ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.lavanderia")
def api_lavanderia_itens(request):
    """GET/POST /api/hospital/lavanderia/itens"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ItemRoupa, _CicloLavanderia = _get_lavanderia_models()
    except Exception as exc:
        logger.exception("Erro ao carregar models de lavanderia: %s", exc)
        return JsonResponse({"erro": "Módulo de lavanderia indisponível."}, status=500)

    if request.method == "GET":
        try:
            qs = ItemRoupa.objects.filter(empresa=empresa, ativo=True).order_by("descricao")
            setor = request.GET.get("setor")
            if setor:
                qs = qs.filter(setor__iexact=setor)
            return JsonResponse({"total": qs.count(), "itens": [_item_to_dict(i) for i in qs]})
        except Exception as exc:
            logger.exception("Erro ao listar itens de roupa: %s", exc)
            return JsonResponse({"erro": "Erro ao listar itens."}, status=500)

    # POST — criar item
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    descricao = (data.get("descricao") or "").strip()
    if not descricao:
        return JsonResponse({"erro": "Campo 'descricao' é obrigatório."}, status=400)

    try:
        qtd_total = int(data.get("quantidade_total", 0))
    except (ValueError, TypeError):
        qtd_total = 0

    setor = (data.get("setor") or "").strip()

    try:
        item = ItemRoupa.objects.create(
            empresa=empresa,
            descricao=descricao,
            quantidade_total=qtd_total,
            quantidade_disponivel=qtd_total,
            setor=setor,
        )
        return JsonResponse({"ok": True, "item": _item_to_dict(item)}, status=201)
    except Exception as exc:
        logger.exception("Erro ao criar item de roupa: %s", exc)
        return JsonResponse({"erro": "Erro ao criar item."}, status=500)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_feature("hospital.lavanderia")
def api_lavanderia_item_detail(request, pk):
    """PATCH /api/hospital/lavanderia/itens/<pk>"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ItemRoupa, _CicloLavanderia = _get_lavanderia_models()
    except Exception as exc:
        logger.exception("Erro ao carregar models de lavanderia: %s", exc)
        return JsonResponse({"erro": "Módulo de lavanderia indisponível."}, status=500)

    try:
        item = ItemRoupa.objects.get(pk=pk, empresa=empresa)
    except ItemRoupa.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado."}, status=404)
    except Exception as exc:
        logger.exception("Erro ao buscar item de roupa pk=%s: %s", pk, exc)
        return JsonResponse({"erro": "Erro ao buscar item."}, status=500)

    try:
        data = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    try:
        campos_permitidos = ("descricao", "quantidade_total", "quantidade_disponivel", "setor", "ativo")
        for campo in campos_permitidos:
            if campo in data:
                if campo in ("quantidade_total", "quantidade_disponivel"):
                    setattr(item, campo, int(data[campo]))
                elif campo == "ativo":
                    setattr(item, campo, bool(data[campo]))
                else:
                    setattr(item, campo, str(data[campo]).strip())
        item.save()
        return JsonResponse({"ok": True, "item": _item_to_dict(item)})
    except Exception as exc:
        logger.exception("Erro ao atualizar item de roupa pk=%s: %s", pk, exc)
        return JsonResponse({"erro": "Erro ao atualizar item."}, status=500)


# ── Ciclos de Lavanderia ───────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.lavanderia")
def api_lavanderia_ciclos(request):
    """GET/POST /api/hospital/lavanderia/ciclos"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ItemRoupa, CicloLavanderia = _get_lavanderia_models()
    except Exception as exc:
        logger.exception("Erro ao carregar models de lavanderia: %s", exc)
        return JsonResponse({"erro": "Módulo de lavanderia indisponível."}, status=500)

    if request.method == "GET":
        try:
            qs = CicloLavanderia.objects.filter(empresa=empresa).select_related("item")

            tipo = request.GET.get("tipo")
            data_gte = request.GET.get("data__gte")
            if tipo:
                qs = qs.filter(tipo=tipo)
            if data_gte:
                qs = qs.filter(data_registro__date__gte=data_gte)

            total = qs.count()
            qs = qs[:200]
            return JsonResponse({"total": total, "ciclos": [_ciclo_to_dict(c) for c in qs]})
        except Exception as exc:
            logger.exception("Erro ao listar ciclos de lavanderia: %s", exc)
            return JsonResponse({"erro": "Erro ao listar ciclos."}, status=500)

    # POST — registrar ciclo
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    item_id = data.get("item_id")
    if not item_id:
        return JsonResponse({"erro": "Campo 'item_id' é obrigatório."}, status=400)

    try:
        item = ItemRoupa.objects.get(pk=item_id, empresa=empresa)
    except ItemRoupa.DoesNotExist:
        return JsonResponse({"erro": "Item de roupa não encontrado."}, status=404)
    except Exception as exc:
        logger.exception("Erro ao buscar item pk=%s: %s", item_id, exc)
        return JsonResponse({"erro": "Erro ao buscar item."}, status=500)

    try:
        quantidade = int(data.get("quantidade", 0))
    except (ValueError, TypeError):
        quantidade = 0

    if quantidade <= 0:
        return JsonResponse({"erro": "Campo 'quantidade' deve ser maior que zero."}, status=400)

    tipo = data.get("tipo", "entrada_sujo")
    tipos_validos = [t[0] for t in CicloLavanderia.TIPO_CHOICES]
    if tipo not in tipos_validos:
        return JsonResponse({"erro": f"Tipo inválido. Valores aceitos: {tipos_validos}"}, status=400)

    setor_origem = (data.get("setor_origem") or "").strip()
    responsavel = (data.get("responsavel") or "").strip()
    observacoes = (data.get("observacoes") or "").strip()

    try:
        ciclo = CicloLavanderia.objects.create(
            empresa=empresa,
            item=item,
            quantidade=quantidade,
            tipo=tipo,
            setor_origem=setor_origem,
            responsavel=responsavel,
            observacoes=observacoes,
        )

        # Atualiza saldo do item
        if tipo == "saida_limpo":
            item.quantidade_disponivel = max(0, item.quantidade_disponivel + quantidade)
        elif tipo == "entrada_sujo":
            item.quantidade_disponivel = max(0, item.quantidade_disponivel - quantidade)
        item.save(update_fields=["quantidade_disponivel"])

        return JsonResponse({"ok": True, "ciclo": _ciclo_to_dict(ciclo)}, status=201)
    except Exception as exc:
        logger.exception("Erro ao registrar ciclo de lavanderia: %s", exc)
        return JsonResponse({"erro": "Erro ao registrar ciclo."}, status=500)


# ── Saldo por Setor ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.lavanderia")
def api_lavanderia_saldo(request):
    """GET /api/hospital/lavanderia/saldo — saldo atual de roupas por setor"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ItemRoupa, _CicloLavanderia = _get_lavanderia_models()
    except Exception as exc:
        logger.exception("Erro ao carregar models de lavanderia: %s", exc)
        return JsonResponse({"erro": "Módulo de lavanderia indisponível."}, status=500)

    try:
        qs = ItemRoupa.objects.filter(empresa=empresa, ativo=True)
        saldo = {}
        for item in qs:
            setor_key = item.setor or "sem_setor"
            if setor_key not in saldo:
                saldo[setor_key] = {"setor": setor_key, "total": 0, "disponivel": 0, "em_uso": 0}
            saldo[setor_key]["total"] += item.quantidade_total
            saldo[setor_key]["disponivel"] += item.quantidade_disponivel
            saldo[setor_key]["em_uso"] += max(0, item.quantidade_total - item.quantidade_disponivel)

        return JsonResponse({"saldo": list(saldo.values())})
    except Exception as exc:
        logger.exception("Erro ao calcular saldo de lavanderia: %s", exc)
        return JsonResponse({"erro": "Erro ao calcular saldo."}, status=500)


# ── KPIs ───────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.lavanderia")
def api_lavanderia_kpis(request):
    """GET /api/hospital/lavanderia/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ItemRoupa, CicloLavanderia = _get_lavanderia_models()
    except Exception as exc:
        logger.exception("Erro ao carregar models de lavanderia: %s", exc)
        return JsonResponse({"erro": "Módulo de lavanderia indisponível."}, status=500)

    try:
        itens = ItemRoupa.objects.filter(empresa=empresa, ativo=True)

        total_pecas = itens.aggregate(t=Sum("quantidade_total"))["t"] or 0
        disponivel = itens.aggregate(d=Sum("quantidade_disponivel"))["d"] or 0
        em_lavagem = max(0, total_pecas - disponivel)

        hoje = date.today()
        ciclos_hoje = CicloLavanderia.objects.filter(
            empresa=empresa,
            data_registro__date=hoje,
        ).count()

        return JsonResponse({
            "total_pecas": total_pecas,
            "em_lavagem": em_lavagem,
            "disponivel": disponivel,
            "ciclos_hoje": ciclos_hoje,
        })
    except Exception as exc:
        logger.exception("Erro ao calcular KPIs de lavanderia: %s", exc)
        return JsonResponse({
            "total_pecas": 0,
            "em_lavagem": 0,
            "disponivel": 0,
            "ciclos_hoje": 0,
        })
