"""
Combate a Endemias — vigilância ambiental municipal (LIRAa / Aedes aegypti).

Distinto do módulo ACS (visita clínica e-SUS CDS): aqui o agente registra
inspeção entomológica de imóvel — depósitos inspecionados, criadouro
encontrado, ação de controle realizada (tratamento focal/perifocal,
eliminação mecânica).
"""
import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_permissao_modulo
from .services.auth_session import empresa_autenticada_from_request as get_empresa


def _e(request):
    empresa = get_empresa(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


def _get_endemias_model():
    from .models import VisitaCombateEndemias
    return VisitaCombateEndemias


def _visita_to_dict(v):
    return {
        "id": v.id,
        "agente_nome": v.agente_nome,
        "data_visita": v.data_visita.isoformat(),
        "endereco": v.endereco,
        "bairro": v.bairro,
        "municipio_ibge": v.municipio_ibge,
        "tipo_imovel": v.tipo_imovel,
        "status_visita": v.status_visita,
        "depositos_inspecionados": v.depositos_inspecionados,
        "foco_encontrado": v.foco_encontrado,
        "tipo_criadouro": v.tipo_criadouro,
        "acao_realizada": v.acao_realizada,
        "larvas_coletadas": v.larvas_coletadas,
        "observacoes": v.observacoes,
        "criado_em": v.criado_em.isoformat(),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_endemias_visitas(request):
    """GET/POST /api/governo/endemias/visitas/"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    VisitaCombateEndemias = _get_endemias_model()

    if request.method == "GET":
        qs = VisitaCombateEndemias.objects.filter(empresa=empresa)

        bairro_f = request.GET.get("bairro")
        if bairro_f:
            qs = qs.filter(bairro__icontains=bairro_f)

        foco_f = request.GET.get("foco_encontrado")
        if foco_f == "true":
            qs = qs.filter(foco_encontrado=True)

        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        if data_ini:
            qs = qs.filter(data_visita__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_visita__lte=data_fim)

        limit = min(int(request.GET.get("limit", 100)), 500)
        return JsonResponse({"visitas": [_visita_to_dict(v) for v in qs[:limit]]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    agente_nome = (data.get("agente_nome") or "").strip()
    data_visita = data.get("data_visita")
    if not agente_nome or not data_visita:
        return JsonResponse({"erro": "agente_nome e data_visita são obrigatórios"}, status=400)

    visita = VisitaCombateEndemias.objects.create(
        empresa=empresa,
        agente_nome=agente_nome,
        data_visita=data_visita,
        endereco=(data.get("endereco") or "").strip(),
        bairro=(data.get("bairro") or "").strip(),
        municipio_ibge=(data.get("municipio_ibge") or "").strip(),
        tipo_imovel=data.get("tipo_imovel", "residencial"),
        status_visita=data.get("status_visita", "realizada"),
        depositos_inspecionados=data.get("depositos_inspecionados", 0),
        foco_encontrado=bool(data.get("foco_encontrado", False)),
        tipo_criadouro=data.get("tipo_criadouro", ""),
        acao_realizada=data.get("acao_realizada", ""),
        larvas_coletadas=bool(data.get("larvas_coletadas", False)),
        observacoes=(data.get("observacoes") or "").strip(),
    )
    return JsonResponse({"ok": True, "visita": _visita_to_dict(visita)}, status=201)


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_endemias_indicadores(request):
    """GET /api/governo/endemias/indicadores/ — índice de infestação por bairro (estilo LIRAa)."""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    VisitaCombateEndemias = _get_endemias_model()
    qs = VisitaCombateEndemias.objects.filter(empresa=empresa)

    data_ini = request.GET.get("data_inicio")
    data_fim = request.GET.get("data_fim")
    if data_ini:
        qs = qs.filter(data_visita__gte=data_ini)
    if data_fim:
        qs = qs.filter(data_visita__lte=data_fim)

    por_bairro = (
        qs.exclude(bairro="")
        .values("bairro")
        .annotate(
            total_imoveis=Count("id"),
            imoveis_com_foco=Count("id", filter=Q(foco_encontrado=True)),
        )
        .order_by("-imoveis_com_foco")
    )

    resultado = []
    for item in por_bairro:
        total = item["total_imoveis"] or 1
        indice = round((item["imoveis_com_foco"] / total) * 100, 2)
        resultado.append({
            "bairro": item["bairro"],
            "total_imoveis_visitados": item["total_imoveis"],
            "imoveis_com_foco": item["imoveis_com_foco"],
            "indice_infestacao_pct": indice,
        })

    total_geral = qs.count()
    total_foco = qs.filter(foco_encontrado=True).count()

    return JsonResponse({
        "indicadores_por_bairro": resultado,
        "total_visitas": total_geral,
        "total_com_foco": total_foco,
        "indice_infestacao_geral_pct": round((total_foco / total_geral) * 100, 2) if total_geral else 0,
    })
