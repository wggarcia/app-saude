"""
Assistência Social — Conselho Tutelar, Vigilância Socioassistencial e Busca Ativa.
Três instrumentos formais do SUAS que não existiam na plataforma.

GET/POST  /api/assistencia-social/conselho-tutelar
GET/PATCH /api/assistencia-social/conselho-tutelar/<id>

GET/POST  /api/assistencia-social/vigilancia-social/territorios
GET/PATCH /api/assistencia-social/vigilancia-social/territorios/<id>

GET/POST  /api/assistencia-social/busca-ativa
GET/PATCH /api/assistencia-social/busca-ativa/<id>

GET       /api/assistencia-social/protecao-especial/kpis
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
    api_requer_permissao_modulo, get_setor, principal_pode_operacao_setorial,
    contexto_navegacao_setorial, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)


def _assoc(request):
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "assistencia_social":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("assistencia_social")
@requer_feature_pacote("assistencia.gestao_suas", "Proteção Especial e Vigilância Social")
@requer_operacao_page
@requer_permissao_modulo("assistencia.gestao_suas")
def assistencia_protecao_especial_page(request):
    return render(request, "assistencia_protecao_especial.html",
                  contexto_navegacao_setorial(request, "assistencia_social"))


# ── Conselho Tutelar ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_conselho_tutelar(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import EncaminhamentoConselhoTutelar, FamiliaCRAS

    if request.method == "GET":
        qs = EncaminhamentoConselhoTutelar.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({
            "total": qs.count(),
            "encaminhamentos": [
                {
                    "id": e.id, "protocolo": e.protocolo, "crianca_nome": e.crianca_nome,
                    "tipo_violacao": e.tipo_violacao, "tipo_violacao_display": e.get_tipo_violacao_display(),
                    "status": e.status, "status_display": e.get_status_display(),
                    "conselheiro_responsavel": e.conselheiro_responsavel,
                    "data_encaminhamento": e.data_encaminhamento.isoformat(),
                    "data_retorno": e.data_retorno.isoformat() if e.data_retorno else None,
                }
                for e in qs.order_by("-data_encaminhamento")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not data.get("crianca_nome") or data.get("tipo_violacao") not in dict(EncaminhamentoConselhoTutelar.TIPO_VIOLACAO):
        return JsonResponse({"erro": "Nome da criança e tipo de violação são obrigatórios"}, status=400)
    if not data.get("descricao"):
        return JsonResponse({"erro": "Descrição é obrigatória"}, status=400)

    familia = None
    if data.get("familia_id"):
        familia = FamiliaCRAS.objects.filter(id=data["familia_id"], empresa=empresa).first()

    total = EncaminhamentoConselhoTutelar.objects.filter(empresa=empresa).count() + 1
    protocolo = f"CT-{empresa.id:06d}-{total:06d}"

    e = EncaminhamentoConselhoTutelar.objects.create(
        empresa=empresa, protocolo=protocolo,
        crianca_nome=data["crianca_nome"],
        crianca_data_nascimento=data.get("crianca_data_nascimento") or None,
        responsavel_nome=data.get("responsavel_nome", ""),
        familia=familia,
        tipo_violacao=data["tipo_violacao"],
        descricao=data["descricao"],
        conselheiro_responsavel=data.get("conselheiro_responsavel", ""),
    )
    return JsonResponse({"id": e.id, "protocolo": protocolo}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_conselho_tutelar_detalhe(request, ct_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import EncaminhamentoConselhoTutelar
    try:
        e = EncaminhamentoConselhoTutelar.objects.get(id=ct_id, empresa=empresa)
    except EncaminhamentoConselhoTutelar.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": e.id, "protocolo": e.protocolo, "crianca_nome": e.crianca_nome,
            "crianca_data_nascimento": e.crianca_data_nascimento.isoformat() if e.crianca_data_nascimento else None,
            "responsavel_nome": e.responsavel_nome,
            "tipo_violacao": e.tipo_violacao, "tipo_violacao_display": e.get_tipo_violacao_display(),
            "descricao": e.descricao, "conselheiro_responsavel": e.conselheiro_responsavel,
            "status": e.status, "status_display": e.get_status_display(),
            "data_encaminhamento": e.data_encaminhamento.isoformat(),
            "data_retorno": e.data_retorno.isoformat() if e.data_retorno else None,
            "parecer_retorno": e.parecer_retorno,
        })

    data = json.loads(request.body)
    if "parecer_retorno" in data:
        e.parecer_retorno = data["parecer_retorno"]
        e.data_retorno = data.get("data_retorno") or date.today().isoformat()
        e.status = "concluido"
    if "status" in data and data["status"] in dict(EncaminhamentoConselhoTutelar.STATUS):
        e.status = data["status"]
    if "conselheiro_responsavel" in data:
        e.conselheiro_responsavel = data["conselheiro_responsavel"]
    e.save()
    return JsonResponse({"ok": True, "status": e.status})


# ── Vigilância Socioassistencial ──────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_vigilancia_territorios(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import TerritorioVigilanciaSocial

    if request.method == "GET":
        qs = TerritorioVigilanciaSocial.objects.filter(empresa=empresa)
        return JsonResponse({
            "total": qs.count(),
            "territorios": [
                {
                    "id": t.id, "bairro": t.bairro,
                    "populacao_estimada": t.populacao_estimada,
                    "familias_cadunico": t.familias_cadunico,
                    "familias_extrema_pobreza": t.familias_extrema_pobreza,
                    "cobertura_cras": t.cobertura_cras, "cobertura_creas": t.cobertura_creas,
                    "indice_vulnerabilidade": t.indice_vulnerabilidade,
                    "indice_vulnerabilidade_display": t.get_indice_vulnerabilidade_display(),
                    "observacoes": t.observacoes,
                }
                for t in qs.order_by("bairro")
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    bairro = (data.get("bairro") or "").strip()
    if not bairro:
        return JsonResponse({"erro": "Bairro é obrigatório"}, status=400)
    if TerritorioVigilanciaSocial.objects.filter(empresa=empresa, bairro=bairro).exists():
        return JsonResponse({"erro": "Já existe um território cadastrado com esse bairro"}, status=409)

    t = TerritorioVigilanciaSocial.objects.create(
        empresa=empresa, bairro=bairro,
        populacao_estimada=data.get("populacao_estimada"),
        familias_cadunico=data.get("familias_cadunico", 0),
        familias_extrema_pobreza=data.get("familias_extrema_pobreza", 0),
        cobertura_cras=data.get("cobertura_cras", False),
        cobertura_creas=data.get("cobertura_creas", False),
        indice_vulnerabilidade=data.get("indice_vulnerabilidade", "medio"),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"id": t.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_vigilancia_territorio_detalhe(request, t_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import TerritorioVigilanciaSocial
    try:
        t = TerritorioVigilanciaSocial.objects.get(id=t_id, empresa=empresa)
    except TerritorioVigilanciaSocial.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"id": t.id, "bairro": t.bairro, "indice_vulnerabilidade": t.indice_vulnerabilidade})

    data = json.loads(request.body)
    campos = ("populacao_estimada", "familias_cadunico", "familias_extrema_pobreza",
              "cobertura_cras", "cobertura_creas", "indice_vulnerabilidade", "observacoes")
    for campo in campos:
        if campo in data:
            setattr(t, campo, data[campo])
    t.save()
    return JsonResponse({"ok": True})


# ── Busca Ativa ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_busca_ativa(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BuscaAtivaSocial

    if request.method == "GET":
        qs = BuscaAtivaSocial.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({
            "total": qs.count(),
            "buscas": [
                {
                    "id": b.id, "nome_referencia": b.nome_referencia,
                    "endereco_referencia": b.endereco_referencia,
                    "motivo": b.motivo, "motivo_display": b.get_motivo_display(),
                    "status": b.status, "status_display": b.get_status_display(),
                    "tecnico_responsavel": b.tecnico_responsavel,
                    "data_inicio": b.data_inicio.isoformat(),
                    "data_localizacao": b.data_localizacao.isoformat() if b.data_localizacao else None,
                }
                for b in qs.order_by("-data_inicio")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not data.get("nome_referencia") or data.get("motivo") not in dict(BuscaAtivaSocial.MOTIVO):
        return JsonResponse({"erro": "Nome de referência e motivo são obrigatórios"}, status=400)

    from .models import FamiliaCRAS
    familia = None
    if data.get("familia_id"):
        familia = FamiliaCRAS.objects.filter(id=data["familia_id"], empresa=empresa).first()

    b = BuscaAtivaSocial.objects.create(
        empresa=empresa, familia=familia,
        nome_referencia=data["nome_referencia"],
        endereco_referencia=data.get("endereco_referencia", ""),
        motivo=data["motivo"],
        tecnico_responsavel=data.get("tecnico_responsavel", ""),
    )
    return JsonResponse({"id": b.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_busca_ativa_detalhe(request, b_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BuscaAtivaSocial
    try:
        b = BuscaAtivaSocial.objects.get(id=b_id, empresa=empresa)
    except BuscaAtivaSocial.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": b.id, "nome_referencia": b.nome_referencia, "status": b.status,
            "resultado": b.resultado,
        })

    data = json.loads(request.body)
    if "status" in data and data["status"] in dict(BuscaAtivaSocial.STATUS):
        b.status = data["status"]
        if data["status"] in ("localizada", "nao_localizada"):
            b.data_localizacao = data.get("data_localizacao") or date.today().isoformat()
    if "resultado" in data:
        b.resultado = data["resultado"]
    if "tecnico_responsavel" in data:
        b.tecnico_responsavel = data["tecnico_responsavel"]
    b.save()
    return JsonResponse({"ok": True, "status": b.status})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_protecao_especial_kpis(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import EncaminhamentoConselhoTutelar, TerritorioVigilanciaSocial, BuscaAtivaSocial

    ct_qs = EncaminhamentoConselhoTutelar.objects.filter(empresa=empresa)
    ba_qs = BuscaAtivaSocial.objects.filter(empresa=empresa)

    return JsonResponse({
        "conselho_tutelar_abertos": ct_qs.exclude(status="concluido").count(),
        "conselho_tutelar_total": ct_qs.count(),
        "territorios_mapeados": TerritorioVigilanciaSocial.objects.filter(empresa=empresa).count(),
        "territorios_alto_risco": TerritorioVigilanciaSocial.objects.filter(
            empresa=empresa, indice_vulnerabilidade__in=["alto", "muito_alto"]
        ).count(),
        "busca_ativa_pendentes": ba_qs.filter(status__in=["pendente", "em_busca"]).count(),
        "busca_ativa_localizadas": ba_qs.filter(status="localizada").count(),
    })
