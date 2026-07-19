"""
views_governo_ppi.py
PPI — Planejamento Programação Integrada, segmento Governo.

Endpoints:
  GET  /api/governo/ppi/programacoes            Lista programações da empresa
  POST /api/governo/ppi/programacoes            Cria nova programação
  GET  /api/governo/ppi/programacoes/<id>       Detalhe com itens
  POST /api/governo/ppi/programacoes/<id>/itens Adiciona ItemPPI
  POST /api/governo/ppi/programacoes/<id>/aprovar  Muda status para aprovado
  POST /api/governo/ppi/programacoes/<id>/exportar Retorna JSON para download/envio
  GET  /api/governo/ppi/kpis                    Indicadores rápidos

Page:
  governo_ppi_page — renderiza governo_ppi.html
"""
import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor,
    principal_pode_operacao_setorial,
    requer_setor,
    requer_operacao_page,
    requer_permissao_modulo,
    api_requer_permissao_modulo,
)
from .services.auth_session import empresa_autenticada_from_request
from .views_dashboard import contexto_navegacao_setorial

# Models são opcionais: carregam quando o schema já existe em banco.
try:
    from .models import ProgramacaoPPI, ItemPPI
    _MODELS_OK = True
except ImportError:
    ProgramacaoPPI = None  # type: ignore[assignment]
    ItemPPI = None         # type: ignore[assignment]
    _MODELS_OK = False


# ── Auth helper ───────────────────────────────────────────────────────────────

def _gov(request):
    """Retorna a empresa autenticada se o setor for 'governo', senão None."""
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ── Serializers ───────────────────────────────────────────────────────────────

def _programacao_dict(prog, incluir_itens=False):
    dados = {
        "id": prog.pk,
        "competencia": str(prog.competencia) if prog.competencia else None,
        "municipio_origem": prog.municipio_origem,
        "municipio_destino": prog.municipio_destino,
        "status": prog.status,
        "criado_em": prog.criado_em.isoformat() if prog.criado_em else None,
        "atualizado_em": prog.atualizado_em.isoformat() if prog.atualizado_em else None,
    }
    if incluir_itens:
        dados["itens"] = [_item_dict(i) for i in prog.itens.all()]
    return dados


def _item_dict(item):
    return {
        "id": item.pk,
        "procedimento_sigtap": item.procedimento_sigtap,
        "descricao_procedimento": item.descricao_procedimento,
        "quantidade_programada": item.quantidade_programada,
        "valor_unitario": str(item.valor_unitario) if item.valor_unitario is not None else None,
        "valor_total": str(
            (item.quantidade_programada or 0) * (item.valor_unitario or 0)
        ),
    }


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.administrativo")
def governo_ppi_page(request):
    return render(request, "governo_ppi.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def api_ppi_kpis(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = timezone.localtime(timezone.now()).date()
    competencia_atual = hoje.strftime("%Y-%m")

    if not _MODELS_OK:
        return JsonResponse({
            "total_programacoes": 0,
            "aprovadas": 0,
            "competencia_atual": competencia_atual,
            "meta_cumprida_pct": 0.0,
        })

    total = ProgramacaoPPI.objects.filter(empresa=empresa).count()
    aprovadas = ProgramacaoPPI.objects.filter(empresa=empresa, status="aprovado").count()

    meta_cumprida_pct = round((aprovadas / total * 100), 2) if total > 0 else 0.0

    return JsonResponse({
        "total_programacoes": total,
        "aprovadas": aprovadas,
        "competencia_atual": competencia_atual,
        "meta_cumprida_pct": meta_cumprida_pct,
    })


# ── Programações ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_ppi_programacoes(request):
    """
    GET  /api/governo/ppi/programacoes  — lista
    POST /api/governo/ppi/programacoes  — cria
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if not _MODELS_OK:
        if request.method == "GET":
            return JsonResponse({"programacoes": []})
        return JsonResponse({"erro": "Módulo PPI ainda não disponível (models não instalados)"}, status=503)

    if request.method == "GET":
        qs = ProgramacaoPPI.objects.filter(empresa=empresa).order_by("-criado_em")
        competencia = request.GET.get("competencia")
        if competencia:
            qs = qs.filter(competencia=competencia)
        status_filtro = request.GET.get("status")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        return JsonResponse({"programacoes": [_programacao_dict(p) for p in qs]})

    # POST — cria nova programação
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    competencia = data.get("competencia", "").strip()
    municipio_origem = data.get("municipio_origem", "").strip()
    municipio_destino = data.get("municipio_destino", "").strip()

    if not competencia:
        return JsonResponse({"erro": "competencia é obrigatório (formato YYYY-MM)"}, status=400)
    if not municipio_origem:
        return JsonResponse({"erro": "municipio_origem é obrigatório"}, status=400)
    if not municipio_destino:
        return JsonResponse({"erro": "municipio_destino é obrigatório"}, status=400)

    prog = ProgramacaoPPI.objects.create(
        empresa=empresa,
        competencia=competencia,
        municipio_origem=municipio_origem,
        municipio_destino=municipio_destino,
        status="rascunho",
    )
    return JsonResponse({"programacao": _programacao_dict(prog)}, status=201)


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def api_ppi_programacao_detalhe(request, pk):
    """
    GET /api/governo/ppi/programacoes/<id> — detalhe com itens
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if not _MODELS_OK:
        return JsonResponse({"erro": "Módulo PPI ainda não disponível"}, status=503)

    prog = get_object_or_404(ProgramacaoPPI, pk=pk, empresa=empresa)
    return JsonResponse({"programacao": _programacao_dict(prog, incluir_itens=True)})


# ── Itens ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_ppi_programacao_itens(request, pk):
    """
    POST /api/governo/ppi/programacoes/<id>/itens — adiciona ItemPPI
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if not _MODELS_OK:
        return JsonResponse({"erro": "Módulo PPI ainda não disponível"}, status=503)

    prog = get_object_or_404(ProgramacaoPPI, pk=pk, empresa=empresa)

    if prog.status == "aprovado":
        return JsonResponse({"erro": "Não é possível adicionar itens a uma programação já aprovada"}, status=400)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    procedimento_sigtap = data.get("procedimento_sigtap", "").strip()
    descricao_procedimento = data.get("descricao_procedimento", "").strip()
    quantidade_programada = data.get("quantidade_programada")
    valor_unitario = data.get("valor_unitario")

    if not procedimento_sigtap:
        return JsonResponse({"erro": "procedimento_sigtap é obrigatório"}, status=400)
    if not descricao_procedimento:
        return JsonResponse({"erro": "descricao_procedimento é obrigatório"}, status=400)
    if quantidade_programada is None:
        return JsonResponse({"erro": "quantidade_programada é obrigatório"}, status=400)

    try:
        quantidade_programada = int(quantidade_programada)
        if quantidade_programada < 1:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"erro": "quantidade_programada deve ser inteiro positivo"}, status=400)

    if valor_unitario is not None:
        try:
            from decimal import Decimal, InvalidOperation
            valor_unitario = Decimal(str(valor_unitario))
            if valor_unitario < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            return JsonResponse({"erro": "valor_unitario deve ser número não-negativo"}, status=400)

    item = ItemPPI.objects.create(
        programacao=prog,
        procedimento_sigtap=procedimento_sigtap,
        descricao_procedimento=descricao_procedimento,
        quantidade_programada=quantidade_programada,
        valor_unitario=valor_unitario,
    )
    return JsonResponse({"item": _item_dict(item)}, status=201)


# ── Aprovar ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_ppi_programacao_aprovar(request, pk):
    """
    POST /api/governo/ppi/programacoes/<id>/aprovar — muda status para aprovado
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if not _MODELS_OK:
        return JsonResponse({"erro": "Módulo PPI ainda não disponível"}, status=503)

    prog = get_object_or_404(ProgramacaoPPI, pk=pk, empresa=empresa)

    if prog.status == "aprovado":
        return JsonResponse({"aviso": "Programação já estava aprovada", "programacao": _programacao_dict(prog)})

    if not prog.itens.exists():
        return JsonResponse({"erro": "Não é possível aprovar uma programação sem itens"}, status=400)

    prog.status = "aprovado"
    prog.save(update_fields=["status", "atualizado_em"])
    return JsonResponse({"programacao": _programacao_dict(prog)})


# ── Exportar ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_ppi_programacao_exportar(request, pk):
    """
    POST /api/governo/ppi/programacoes/<id>/exportar
    Retorna JSON estruturado da programação para download ou envio a sistema externo.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if not _MODELS_OK:
        return JsonResponse({"erro": "Módulo PPI ainda não disponível"}, status=503)

    prog = get_object_or_404(ProgramacaoPPI, pk=pk, empresa=empresa)

    itens = [_item_dict(i) for i in prog.itens.all()]
    total_geral = sum(
        float(i["valor_total"]) for i in itens if i["valor_total"] is not None
    )

    payload = {
        "exportado_em": timezone.now().isoformat(),
        "empresa": {
            "id": empresa.pk,
            "nome": getattr(empresa, "nome", str(empresa)),
            "cnpj": getattr(empresa, "cnpj", None),
        },
        "programacao": {
            **_programacao_dict(prog),
            "itens": itens,
            "total_geral": round(total_geral, 2),
            "total_itens": len(itens),
        },
    }
    return JsonResponse(payload)
