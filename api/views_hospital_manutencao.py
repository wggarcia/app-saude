"""
Hospital — Manutenção Predial / Infraestrutura
  • Ordens de Serviço prediais (preventiva, corretiva, emergencial)
  • KPIs operacionais de manutenção
"""
import json
import logging
from datetime import timedelta

from django.db.models import Avg, Q
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


def _get_modelo():
    from .models import OrdemServicoPredial
    return OrdemServicoPredial


def _os_to_dict(o):
    return {
        "id": o.id,
        "numero_os": o.numero_os,
        "descricao": o.descricao,
        "tipo": o.tipo,
        "setor": o.setor,
        "prioridade": o.prioridade,
        "status": o.status,
        "responsavel": o.responsavel,
        "solicitante": o.solicitante,
        "data_abertura": o.data_abertura.strftime("%d/%m/%Y %H:%M"),
        "data_previsao": o.data_previsao.isoformat() if o.data_previsao else None,
        "data_conclusao": o.data_conclusao.strftime("%d/%m/%Y %H:%M") if o.data_conclusao else None,
        "custo_estimado": float(o.custo_estimado) if o.custo_estimado is not None else None,
        "custo_real": float(o.custo_real) if o.custo_real is not None else None,
        "observacoes": o.observacoes,
    }


# ── Página ────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.operacional", "Manutenção")
@requer_operacao_page
@requer_permissao_modulo("hospital.operacional")
def hospital_manutencao_page(request):
    return render(request, "hospital_manutencao.html")


# ── Ordens de Serviço ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.operacional")
def api_manutencao_ordens(request):
    """GET/POST /api/hospital/manutencao/ordens"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        OrdemServicoPredial = _get_modelo()
    except Exception as exc:
        logger.exception("Erro ao carregar OrdemServicoPredial")
        return JsonResponse({"erro": "Modelo indisponível", "detalhe": str(exc)}, status=500)

    if request.method == "GET":
        try:
            qs = OrdemServicoPredial.objects.filter(empresa=empresa)
            status_f = request.GET.get("status", "").strip()
            prioridade_f = request.GET.get("prioridade", "").strip()
            setor_f = request.GET.get("setor", "").strip()

            if status_f:
                qs = qs.filter(status=status_f)
            if prioridade_f:
                qs = qs.filter(prioridade=prioridade_f)
            if setor_f:
                qs = qs.filter(setor__icontains=setor_f)

            return JsonResponse({
                "total": qs.count(),
                "ordens": [_os_to_dict(o) for o in qs[:500]],
            })
        except Exception as exc:
            logger.exception("Erro ao listar ordens prediais")
            return JsonResponse({"erro": "Erro interno", "detalhe": str(exc)}, status=500)

    # POST — abrir OS
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    descricao = (data.get("descricao") or "").strip()
    setor = (data.get("setor") or "").strip()
    if not descricao or not setor:
        return JsonResponse({"erro": "descricao e setor são obrigatórios"}, status=400)

    try:
        os_obj = OrdemServicoPredial.objects.create(
            empresa=empresa,
            descricao=descricao,
            tipo=data.get("tipo", "corretiva"),
            setor=setor,
            prioridade=data.get("prioridade", "media"),
            solicitante=(data.get("solicitante") or "").strip(),
            data_previsao=data.get("data_previsao") or None,
        )
        return JsonResponse({"ok": True, "ordem": _os_to_dict(os_obj)}, status=201)
    except Exception as exc:
        logger.exception("Erro ao criar OrdemServicoPredial")
        return JsonResponse({"erro": "Erro ao criar OS", "detalhe": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.operacional")
def api_manutencao_ordem_detalhe(request, pk):
    """GET/PATCH /api/hospital/manutencao/ordens/<pk>"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        OrdemServicoPredial = _get_modelo()
        os_obj = OrdemServicoPredial.objects.filter(pk=pk, empresa=empresa).first()
    except Exception as exc:
        logger.exception("Erro ao buscar OrdemServicoPredial pk=%s", pk)
        return JsonResponse({"erro": "Erro interno", "detalhe": str(exc)}, status=500)

    if not os_obj:
        return JsonResponse({"erro": "Ordem de serviço não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"ordem": _os_to_dict(os_obj)})

    # PATCH — atualizar campos
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    try:
        campos_permitidos = ("status", "responsavel", "custo_real", "observacoes")
        for campo in campos_permitidos:
            valor = data.get(campo)
            if valor is not None:
                setattr(os_obj, campo, valor)
        os_obj.save()
        return JsonResponse({"ok": True, "ordem": _os_to_dict(os_obj)})
    except Exception as exc:
        logger.exception("Erro ao atualizar OrdemServicoPredial pk=%s", pk)
        return JsonResponse({"erro": "Erro ao atualizar OS", "detalhe": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.operacional")
def api_manutencao_ordem_concluir(request, pk):
    """POST /api/hospital/manutencao/ordens/<pk>/concluir"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        OrdemServicoPredial = _get_modelo()
        os_obj = OrdemServicoPredial.objects.filter(pk=pk, empresa=empresa).first()
    except Exception as exc:
        logger.exception("Erro ao buscar OrdemServicoPredial pk=%s para conclusão", pk)
        return JsonResponse({"erro": "Erro interno", "detalhe": str(exc)}, status=500)

    if not os_obj:
        return JsonResponse({"erro": "Ordem de serviço não encontrada"}, status=404)

    if os_obj.status == "concluida":
        return JsonResponse({"erro": "OS já está concluída"}, status=400)

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    try:
        os_obj.status = "concluida"
        os_obj.data_conclusao = timezone.now()
        custo_real = data.get("custo_real")
        if custo_real not in (None, ""):
            os_obj.custo_real = custo_real
        os_obj.save()
        return JsonResponse({"ok": True, "ordem": _os_to_dict(os_obj)})
    except Exception as exc:
        logger.exception("Erro ao concluir OrdemServicoPredial pk=%s", pk)
        return JsonResponse({"erro": "Erro ao concluir OS", "detalhe": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.operacional")
def api_manutencao_ordem_cancelar(request, pk):
    """POST /api/hospital/manutencao/ordens/<pk>/cancelar"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        OrdemServicoPredial = _get_modelo()
        os_obj = OrdemServicoPredial.objects.filter(pk=pk, empresa=empresa).first()
    except Exception as exc:
        logger.exception("Erro ao buscar OrdemServicoPredial pk=%s para cancelamento", pk)
        return JsonResponse({"erro": "Erro interno", "detalhe": str(exc)}, status=500)

    if not os_obj:
        return JsonResponse({"erro": "Ordem de serviço não encontrada"}, status=404)

    if os_obj.status in ("concluida", "cancelada"):
        return JsonResponse({"erro": f"OS não pode ser cancelada (status atual: {os_obj.status})"}, status=400)

    try:
        os_obj.status = "cancelada"
        os_obj.save(update_fields=["status"])
        return JsonResponse({"ok": True, "ordem": _os_to_dict(os_obj)})
    except Exception as exc:
        logger.exception("Erro ao cancelar OrdemServicoPredial pk=%s", pk)
        return JsonResponse({"erro": "Erro ao cancelar OS", "detalhe": str(exc)}, status=500)


# ── KPIs ──────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.operacional")
def api_manutencao_kpis(request):
    """GET /api/hospital/manutencao/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        OrdemServicoPredial = _get_modelo()
        qs = OrdemServicoPredial.objects.filter(empresa=empresa)

        abertas = qs.filter(status="aberta").count()
        em_andamento = qs.filter(status="em_andamento").count()
        criticas = qs.filter(prioridade="critica").exclude(status__in=("concluida", "cancelada")).count()

        inicio_mes = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        concluidas_mes = qs.filter(status="concluida", data_conclusao__gte=inicio_mes).count()

        # Tempo médio de resolução em horas (apenas OS concluídas com data_conclusao)
        concluidas_qs = qs.filter(
            status="concluida",
            data_conclusao__isnull=False,
        )
        tempo_medio_h = 0.0
        total_concluidas = concluidas_qs.count()
        if total_concluidas:
            # Calcular em Python para compatibilidade (evita F() com DateTimeField diff)
            duracao_total = timedelta()
            for o in concluidas_qs.only("data_abertura", "data_conclusao")[:500]:
                if o.data_conclusao and o.data_abertura:
                    duracao_total += o.data_conclusao - o.data_abertura
            tempo_medio_h = round(duracao_total.total_seconds() / 3600 / total_concluidas, 1)

        return JsonResponse({
            "abertas": abertas,
            "em_andamento": em_andamento,
            "criticas": criticas,
            "concluidas_mes": concluidas_mes,
            "tempo_medio_resolucao_h": tempo_medio_h,
        })
    except Exception as exc:
        logger.exception("Erro ao calcular KPIs de manutenção predial")
        return JsonResponse({"erro": "Erro ao calcular KPIs", "detalhe": str(exc)}, status=500)
