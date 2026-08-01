"""
Conselho Municipal/Estadual de Saúde — controle social do SUS (Lei 8.142/1990).
Cadastro de conselheiros (paridade por segmento), reuniões (pauta/ata) e
deliberações (resoluções, recomendações, moções).

GET/POST  /api/governo/conselho-saude/conselheiros
GET/PATCH /api/governo/conselho-saude/conselheiros/<id>
GET/POST  /api/governo/conselho-saude/reunioes
GET/PATCH /api/governo/conselho-saude/reunioes/<id>
GET/POST  /api/governo/conselho-saude/deliberacoes
GET       /api/governo/conselho-saude/kpis
"""
import json
import logging
from datetime import date

from django.db.models import Count
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

_PERMS = ("governo.secretaria_agendamento", "governo.administrativo")


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
@requer_permissao_modulo(*_PERMS)
def governo_conselho_saude_page(request):
    return render(request, "governo_conselho_saude.html", contexto_navegacao_setorial(request, "governo"))


# ── Conselheiros ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo(*_PERMS)
def api_conselho_conselheiros(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ConselheiroSaude

    if request.method == "GET":
        qs = ConselheiroSaude.objects.filter(empresa=empresa)
        if request.GET.get("ativo") != "todos":
            qs = qs.filter(ativo=True)
        return JsonResponse({
            "total": qs.count(),
            "conselheiros": [
                {
                    "id": c.id,
                    "nome": c.nome,
                    "segmento": c.segmento,
                    "segmento_display": c.get_segmento_display(),
                    "titular": c.titular,
                    "entidade_representada": c.entidade_representada,
                    "mandato_inicio": c.mandato_inicio.isoformat(),
                    "mandato_fim": c.mandato_fim.isoformat(),
                    "mandato_vencido": c.mandato_fim < date.today(),
                    "ativo": c.ativo,
                }
                for c in qs.order_by("segmento", "nome")
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if data.get("segmento") not in dict(ConselheiroSaude.SEGMENTO):
        return JsonResponse({"erro": "Segmento inválido"}, status=400)
    if not data.get("nome") or not data.get("mandato_inicio") or not data.get("mandato_fim"):
        return JsonResponse({"erro": "Nome, início e fim do mandato são obrigatórios"}, status=400)

    c = ConselheiroSaude.objects.create(
        empresa=empresa,
        nome=data["nome"],
        segmento=data["segmento"],
        titular=data.get("titular", True),
        entidade_representada=data.get("entidade_representada", ""),
        mandato_inicio=data["mandato_inicio"],
        mandato_fim=data["mandato_fim"],
    )
    return JsonResponse({"id": c.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo(*_PERMS)
def api_conselho_conselheiro_detalhe(request, c_id):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ConselheiroSaude
    try:
        c = ConselheiroSaude.objects.get(id=c_id, empresa=empresa)
    except ConselheiroSaude.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": c.id, "nome": c.nome, "segmento": c.segmento,
            "titular": c.titular, "entidade_representada": c.entidade_representada,
            "mandato_inicio": c.mandato_inicio.isoformat(), "mandato_fim": c.mandato_fim.isoformat(),
            "ativo": c.ativo,
        })

    data = json.loads(request.body)
    for campo in ("nome", "entidade_representada", "titular", "ativo", "mandato_fim"):
        if campo in data:
            setattr(c, campo, data[campo])
    c.save()
    return JsonResponse({"ok": True})


# ── Reuniões ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo(*_PERMS)
def api_conselho_reunioes(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ReuniaoConselhoSaude

    if request.method == "GET":
        qs = ReuniaoConselhoSaude.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({
            "total": qs.count(),
            "reunioes": [
                {
                    "id": r.id,
                    "data_reuniao": r.data_reuniao.isoformat(),
                    "tipo": r.tipo,
                    "tipo_display": r.get_tipo_display(),
                    "pauta": r.pauta[:200],
                    "presentes_count": r.presentes_count,
                    "status": r.status,
                    "status_display": r.get_status_display(),
                    "total_deliberacoes": r.deliberacoes.count(),
                }
                for r in qs.order_by("-data_reuniao")[:100]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not data.get("data_reuniao"):
        return JsonResponse({"erro": "Data da reunião é obrigatória"}, status=400)

    r = ReuniaoConselhoSaude.objects.create(
        empresa=empresa,
        data_reuniao=data["data_reuniao"],
        tipo=data.get("tipo", "ordinaria"),
        pauta=data.get("pauta", ""),
    )
    return JsonResponse({"id": r.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo(*_PERMS)
def api_conselho_reuniao_detalhe(request, r_id):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ReuniaoConselhoSaude
    try:
        r = ReuniaoConselhoSaude.objects.get(id=r_id, empresa=empresa)
    except ReuniaoConselhoSaude.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": r.id,
            "data_reuniao": r.data_reuniao.isoformat(),
            "tipo": r.tipo, "tipo_display": r.get_tipo_display(),
            "pauta": r.pauta, "ata_texto": r.ata_texto,
            "presentes_count": r.presentes_count,
            "status": r.status, "status_display": r.get_status_display(),
            "deliberacoes": [
                {
                    "id": d.id, "numero": d.numero, "tipo": d.tipo,
                    "tipo_display": d.get_tipo_display(), "texto": d.texto,
                    "votos_favor": d.votos_favor, "votos_contra": d.votos_contra,
                    "votos_abstencao": d.votos_abstencao, "aprovada": d.aprovada,
                }
                for d in r.deliberacoes.all().order_by("-criado_em")
            ],
        })

    data = json.loads(request.body)
    for campo in ("pauta", "ata_texto", "presentes_count", "status"):
        if campo in data:
            setattr(r, campo, data[campo])
    r.save()
    return JsonResponse({"ok": True})


# ── Deliberações ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo(*_PERMS)
def api_conselho_deliberacoes(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import DeliberacaoConselhoSaude, ReuniaoConselhoSaude

    if request.method == "GET":
        qs = DeliberacaoConselhoSaude.objects.filter(empresa=empresa)
        reuniao_id = request.GET.get("reuniao_id")
        if reuniao_id:
            qs = qs.filter(reuniao_id=reuniao_id)
        return JsonResponse({
            "total": qs.count(),
            "deliberacoes": [
                {
                    "id": d.id, "reuniao_id": d.reuniao_id, "numero": d.numero,
                    "tipo": d.tipo, "tipo_display": d.get_tipo_display(),
                    "texto": d.texto, "aprovada": d.aprovada,
                    "votos_favor": d.votos_favor, "votos_contra": d.votos_contra,
                    "votos_abstencao": d.votos_abstencao,
                    "criado_em": d.criado_em.isoformat(),
                }
                for d in qs.order_by("-criado_em")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    try:
        reuniao = ReuniaoConselhoSaude.objects.get(id=data["reuniao_id"], empresa=empresa)
    except (KeyError, ReuniaoConselhoSaude.DoesNotExist):
        return JsonResponse({"erro": "Reunião não encontrada"}, status=404)
    if not data.get("texto"):
        return JsonResponse({"erro": "Texto da deliberação é obrigatório"}, status=400)

    d = DeliberacaoConselhoSaude.objects.create(
        empresa=empresa,
        reuniao=reuniao,
        numero=data.get("numero", ""),
        tipo=data.get("tipo", "resolucao"),
        texto=data["texto"],
        votos_favor=data.get("votos_favor", 0),
        votos_contra=data.get("votos_contra", 0),
        votos_abstencao=data.get("votos_abstencao", 0),
        aprovada=data.get("aprovada", True),
    )
    return JsonResponse({"id": d.id}, status=201)


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo(*_PERMS)
def api_conselho_kpis(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ConselheiroSaude, ReuniaoConselhoSaude, DeliberacaoConselhoSaude

    conselheiros = ConselheiroSaude.objects.filter(empresa=empresa, ativo=True)
    por_segmento = dict(conselheiros.values_list("segmento").annotate(n=Count("id")).order_by())

    ano_atual = date.today().year
    reunioes_ano = ReuniaoConselhoSaude.objects.filter(
        empresa=empresa, data_reuniao__year=ano_atual
    )

    return JsonResponse({
        "conselheiros_ativos": conselheiros.count(),
        "por_segmento": por_segmento,
        "mandatos_vencidos": conselheiros.filter(mandato_fim__lt=date.today()).count(),
        "reunioes_ano_atual": reunioes_ano.count(),
        "reunioes_realizadas_ano": reunioes_ano.filter(status="realizada").count(),
        "deliberacoes_total": DeliberacaoConselhoSaude.objects.filter(empresa=empresa).count(),
    })
