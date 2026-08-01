"""
Escala de Profissionais da Rede Assistencial — RH da rede (SUS).
Lotação de médicos, enfermeiros, técnicos e demais categorias nas unidades
de saúde, por turno/plantão, vínculo e carga horária.

GET/POST  /api/governo/escala-rede/escalas
GET/PATCH /api/governo/escala-rede/escalas/<id>
GET       /api/governo/escala-rede/kpis
"""
import json
import logging
from datetime import date

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial, api_requer_permissao_modulo,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .views_dashboard import contexto_navegacao_setorial

logger = logging.getLogger(__name__)


def _e(request):
    empresa = get_empresa(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.administrativo")
def governo_escala_rede_page(request):
    return render(request, "governo_escala_rede.html", contexto_navegacao_setorial(request, "governo"))


# ── Escalas ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_escala_rede_lista(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import EscalaProfissionalRede, UnidadeSaude

    if request.method == "GET":
        qs = EscalaProfissionalRede.objects.filter(empresa=empresa).select_related("unidade")
        q = request.GET.get("q")
        categoria = request.GET.get("categoria")
        unidade_id = request.GET.get("unidade_id")
        status_f = request.GET.get("status", "ativo")
        if status_f and status_f != "todos":
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(profissional_nome__icontains=q) | Q(conselho_registro__icontains=q))
        if categoria:
            qs = qs.filter(categoria=categoria)
        if unidade_id:
            qs = qs.filter(unidade_id=unidade_id)

        return JsonResponse({
            "total": qs.count(),
            "escalas": [
                {
                    "id": e.id,
                    "profissional_nome": e.profissional_nome,
                    "categoria": e.categoria,
                    "categoria_display": e.get_categoria_display(),
                    "cbo": e.cbo,
                    "conselho_registro": e.conselho_registro,
                    "vinculo": e.vinculo,
                    "vinculo_display": e.get_vinculo_display(),
                    "turno": e.turno,
                    "turno_display": e.get_turno_display(),
                    "dias_semana": e.dias_semana,
                    "carga_horaria_semanal": e.carga_horaria_semanal,
                    "unidade": e.unidade.nome if e.unidade else None,
                    "unidade_id": e.unidade_id,
                    "data_inicio": e.data_inicio.isoformat(),
                    "data_fim": e.data_fim.isoformat() if e.data_fim else None,
                    "status": e.status,
                    "status_display": e.get_status_display(),
                }
                for e in qs.order_by("profissional_nome")[:300]
            ],
            "unidades": [{"id": u.id, "nome": u.nome} for u in UnidadeSaude.objects.filter(empresa=empresa, status="ativa").order_by("nome")],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not data.get("profissional_nome") or not data.get("categoria") or not data.get("data_inicio"):
        return JsonResponse({"erro": "Nome, categoria e data de início são obrigatórios"}, status=400)

    unidade = None
    if data.get("unidade_id"):
        unidade = UnidadeSaude.objects.filter(id=data["unidade_id"], empresa=empresa).first()

    e = EscalaProfissionalRede.objects.create(
        empresa=empresa,
        unidade=unidade,
        profissional_nome=data["profissional_nome"],
        categoria=data["categoria"],
        cbo=data.get("cbo", ""),
        conselho_registro=data.get("conselho_registro", ""),
        vinculo=data.get("vinculo", "estatutario"),
        turno=data.get("turno", "manha"),
        dias_semana=data.get("dias_semana", []),
        carga_horaria_semanal=data.get("carga_horaria_semanal", 40),
        data_inicio=data["data_inicio"],
        data_fim=data.get("data_fim") or None,
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"id": e.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("governo.administrativo")
def api_escala_rede_detalhe(request, esc_id):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import EscalaProfissionalRede
    try:
        e = EscalaProfissionalRede.objects.get(id=esc_id, empresa=empresa)
    except EscalaProfissionalRede.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": e.id, "profissional_nome": e.profissional_nome, "categoria": e.categoria,
            "cbo": e.cbo, "conselho_registro": e.conselho_registro, "vinculo": e.vinculo,
            "turno": e.turno, "dias_semana": e.dias_semana,
            "carga_horaria_semanal": e.carga_horaria_semanal,
            "unidade_id": e.unidade_id,
            "data_inicio": e.data_inicio.isoformat(),
            "data_fim": e.data_fim.isoformat() if e.data_fim else None,
            "status": e.status, "observacoes": e.observacoes,
        })

    data = json.loads(request.body)
    campos = ("profissional_nome", "categoria", "cbo", "conselho_registro", "vinculo",
              "turno", "dias_semana", "carga_horaria_semanal", "data_fim", "status", "observacoes")
    for campo in campos:
        if campo in data:
            setattr(e, campo, data[campo])
    e.save()
    return JsonResponse({"ok": True})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.administrativo")
def api_escala_rede_kpis(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import EscalaProfissionalRede

    qs = EscalaProfissionalRede.objects.filter(empresa=empresa)
    ativos = qs.filter(status="ativo")
    por_categoria = dict(ativos.values_list("categoria").annotate(n=Count("id")).order_by())
    por_vinculo = dict(ativos.values_list("vinculo").annotate(n=Count("id")).order_by())

    return JsonResponse({
        "total_ativos": ativos.count(),
        "afastados": qs.filter(status="afastado").count(),
        "por_categoria": por_categoria,
        "por_vinculo": por_vinculo,
        "carga_horaria_total_semanal": sum(ativos.values_list("carga_horaria_semanal", flat=True)),
    })
