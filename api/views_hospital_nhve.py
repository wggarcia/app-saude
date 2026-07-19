"""
NHVE — Núcleo de Vigilância Epidemiológica Hospitalar
Notificações compulsórias e integração SINAN.
"""
import json
import logging
from datetime import date, datetime
from collections import Counter

from django.db import transaction
from django.db.models import Count, Q
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


def _get_nhve_model():
    from .models import NotificacaoNHVE
    return NotificacaoNHVE


# ── Página ────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.epidemiologia", "NHVE")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_nhve_page(request):
    return render(request, "hospital_nhve.html")


# ── helpers ───────────────────────────────────────────────────────────────────

def _notificacao_dict(n):
    return {
        "id":                      n.id,
        "doenca_cid":              n.doenca_cid,
        "nome_paciente":           n.nome_paciente,
        "data_nascimento":         n.data_nascimento.isoformat() if n.data_nascimento else None,
        "sexo":                    n.sexo,
        "sexo_display":            n.get_sexo_display(),
        "data_notificacao":        n.data_notificacao.isoformat(),
        "data_inicio_sintomas":    n.data_inicio_sintomas.isoformat() if n.data_inicio_sintomas else None,
        "status":                  n.status,
        "status_display":          n.get_status_display(),
        "notificado_sinan":        n.notificado_sinan,
        "data_notificacao_sinan":  n.data_notificacao_sinan.isoformat() if n.data_notificacao_sinan else None,
        "notificado_por":          n.notificado_por,
        "unidade":                 n.unidade,
        "observacoes":             n.observacoes,
        "criado_em":               n.criado_em.isoformat(),
    }


# ── Lista / Criação ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.epidemiologia")
def api_nhve_notificacoes(request):
    """GET/POST /api/hospital/nhve/notificacoes"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    NotificacaoNHVE = _get_nhve_model()

    if request.method == "GET":
        qs = NotificacaoNHVE.objects.filter(empresa=empresa)

        status_f = request.GET.get("status")
        notificado_sinan = request.GET.get("notificado_sinan")
        data_gte = request.GET.get("data_notificacao__gte")

        if status_f:
            qs = qs.filter(status=status_f)
        if notificado_sinan is not None:
            qs = qs.filter(notificado_sinan=(notificado_sinan.lower() == "true"))
        if data_gte:
            qs = qs.filter(data_notificacao__gte=data_gte)

        return JsonResponse({
            "total": qs.count(),
            "notificacoes": [_notificacao_dict(n) for n in qs.order_by("-data_notificacao")[:500]],
        })

    # POST — cria notificação
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"erro": f"JSON inválido: {exc}"}, status=400)

    campos_obrigatorios = ["doenca_cid", "data_notificacao"]
    for campo in campos_obrigatorios:
        if not data.get(campo):
            return JsonResponse({"erro": f"Campo obrigatório ausente: {campo}"}, status=400)

    try:
        with transaction.atomic():
            n = NotificacaoNHVE.objects.create(
                empresa=empresa,
                doenca_cid=data["doenca_cid"],
                nome_paciente=data.get("nome_paciente", ""),
                data_nascimento=data.get("data_nascimento") or None,
                sexo=data.get("sexo", "I"),
                data_notificacao=data["data_notificacao"],
                data_inicio_sintomas=data.get("data_inicio_sintomas") or None,
                status=data.get("status", "suspeito"),
                notificado_por=data.get("notificado_por", ""),
                unidade=data.get("unidade", ""),
                observacoes=data.get("observacoes", ""),
            )
    except Exception as exc:
        logger.exception("Erro ao criar NotificacaoNHVE")
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({"id": n.id}, status=201)


# ── Detalhe / Atualização ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.epidemiologia")
def api_nhve_notificacao_detalhe(request, pk):
    """GET/PATCH /api/hospital/nhve/notificacoes/<pk>"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    NotificacaoNHVE = _get_nhve_model()
    try:
        n = NotificacaoNHVE.objects.get(pk=pk, empresa=empresa)
    except NotificacaoNHVE.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_notificacao_dict(n))

    # PATCH
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"erro": f"JSON inválido: {exc}"}, status=400)

    campos_editaveis = ["status", "observacoes", "notificado_por", "unidade",
                        "data_inicio_sintomas", "data_nascimento", "sexo"]
    try:
        for campo in campos_editaveis:
            if campo in data:
                valor = data[campo]
                # Aceita string vazia para campos de data (converte para None)
                if valor == "" and campo in ("data_inicio_sintomas", "data_nascimento"):
                    valor = None
                setattr(n, campo, valor)
        n.save()
    except Exception as exc:
        logger.exception("Erro ao atualizar NotificacaoNHVE pk=%s", pk)
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({"ok": True})


# ── Ações de Status ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.epidemiologia")
def api_nhve_confirmar(request, pk):
    """POST /api/hospital/nhve/notificacoes/<pk>/confirmar"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    NotificacaoNHVE = _get_nhve_model()
    try:
        n = NotificacaoNHVE.objects.get(pk=pk, empresa=empresa)
    except NotificacaoNHVE.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    try:
        n.status = "confirmado"
        n.save(update_fields=["status"])
    except Exception as exc:
        logger.exception("Erro ao confirmar NotificacaoNHVE pk=%s", pk)
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({"ok": True, "status": "confirmado"})


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.epidemiologia")
def api_nhve_descartar(request, pk):
    """POST /api/hospital/nhve/notificacoes/<pk>/descartar"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    NotificacaoNHVE = _get_nhve_model()
    try:
        n = NotificacaoNHVE.objects.get(pk=pk, empresa=empresa)
    except NotificacaoNHVE.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    try:
        data = json.loads(request.body) if request.body else {}
        n.status = "descartado"
        if data.get("observacoes"):
            n.observacoes = data["observacoes"]
        n.save(update_fields=["status", "observacoes"])
    except Exception as exc:
        logger.exception("Erro ao descartar NotificacaoNHVE pk=%s", pk)
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({"ok": True, "status": "descartado"})


# ── Notificação SINAN ─────────────────────────────────────────────────────────

def _gerar_ficha_sinan(n, empresa):
    """Retorna dict no padrão SINAN NET para download."""
    return {
        "ficha_sinan": {
            "versao":                  "SINAN-NET",
            "data_geracao":            datetime.now().isoformat(),
            "tp_not":                  2,          # 2 = individual
            "id_agravo":               n.doenca_cid,
            "dt_notific":              n.data_notificacao.strftime("%Y-%m-%d"),
            "dt_sin_pri":              n.data_inicio_sintomas.strftime("%Y-%m-%d") if n.data_inicio_sintomas else None,
            "nm_pacient":              n.nome_paciente or "NÃO INFORMADO",
            "dt_nasc":                 n.data_nascimento.strftime("%Y-%m-%d") if n.data_nascimento else None,
            "cs_sexo":                 n.sexo,
            "nm_notif":                n.notificado_por or "NÃO INFORMADO",
            "nm_unidade":              n.unidade or getattr(empresa, "nome", "NÃO INFORMADO"),
            "co_uni_not":              getattr(empresa, "cnes", "") or "",
            "sg_uf_not":               getattr(empresa, "uf", "") or "",
            "id_municip":              getattr(empresa, "municipio", "") or "",
            "status_notificacao":      n.status,
            "id_notificacao_interno":  n.id,
            "dt_notificacao_sinan":    n.data_notificacao_sinan.isoformat() if n.data_notificacao_sinan else None,
            "observacoes":             n.observacoes,
        }
    }


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.epidemiologia")
def api_nhve_notificar_sinan(request, pk):
    """POST /api/hospital/nhve/notificacoes/<pk>/notificar-sinan
    Marca notificado_sinan=True, registra data/hora e retorna ficha JSON SINAN.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    NotificacaoNHVE = _get_nhve_model()
    try:
        n = NotificacaoNHVE.objects.get(pk=pk, empresa=empresa)
    except NotificacaoNHVE.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    try:
        n.notificado_sinan = True
        n.data_notificacao_sinan = timezone.now()
        n.save(update_fields=["notificado_sinan", "data_notificacao_sinan"])
    except Exception as exc:
        logger.exception("Erro ao marcar SINAN em NotificacaoNHVE pk=%s", pk)
        return JsonResponse({"erro": str(exc)}, status=500)

    ficha = _gerar_ficha_sinan(n, empresa)
    return JsonResponse({
        "ok": True,
        "notificado_sinan":       True,
        "data_notificacao_sinan": n.data_notificacao_sinan.isoformat(),
        "ficha_sinan":            ficha["ficha_sinan"],
    })


# ── KPIs ───────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.epidemiologia")
def api_nhve_kpis(request):
    """GET /api/hospital/nhve/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    NotificacaoNHVE = _get_nhve_model()

    hoje = date.today()
    mes_ini = hoje.replace(day=1)

    try:
        qs = NotificacaoNHVE.objects.filter(empresa=empresa)

        suspeitos = qs.filter(status="suspeito").count()

        confirmados_mes = qs.filter(
            status="confirmado",
            data_notificacao__gte=mes_ini,
        ).count()

        aguardando_sinan = qs.filter(
            notificado_sinan=False,
        ).exclude(status="descartado").count()

        # Doenças mais frequentes (todos os tempos, top 5)
        freq_qs = (
            qs.values("doenca_cid")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        doencas_mais_freq = [
            {"doenca_cid": row["doenca_cid"], "total": row["total"]}
            for row in freq_qs
        ]
    except Exception as exc:
        logger.exception("Erro ao calcular KPIs NHVE")
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({
        "suspeitos":          suspeitos,
        "confirmados_mes":    confirmados_mes,
        "aguardando_sinan":   aguardando_sinan,
        "doencas_mais_freq":  doencas_mais_freq,
    })
