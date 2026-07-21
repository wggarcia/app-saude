"""
Portabilidade ANS Formal (RN 438/2018)
Processo completo de portabilidade de beneficiário entre operadoras:
prazos ANS, documentação, notificação e protocolo de transferência.
ANS Resolução Normativa 438/2018
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .utils import validar_cpf_cadastro

logger = logging.getLogger(__name__)

# Prazos ANS (RN 438/2018, art. 11-15)
_PRAZO_ANALISE_DIAS_UTEIS = 10  # 10 dias úteis para resposta
_PRAZO_EFETIVACAO_DIAS = 30     # 30 dias corridos para efetivação após aprovação


def _calc_prazo_uteis(dias_uteis: int) -> date:
    """Calcula data-limite em dias úteis (exclui sábado e domingo)."""
    d = date.today()
    uteis = 0
    while uteis < dias_uteis:
        d += timedelta(days=1)
        if d.weekday() < 5:  # seg-sex
            uteis += 1
    return d


def _get_port_models():
    from .models import SolicitacaoPortabilidade
    return SolicitacaoPortabilidade


# ── solicitações ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_portabilidade_lista(request):
    """GET/POST /api/plano-saude/portabilidade-ans/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    SolicitacaoPortabilidade = _get_port_models()

    if request.method == "GET":
        qs = SolicitacaoPortabilidade.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        tipo_f = request.GET.get("tipo")
        q = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        if q:
            qs = qs.filter(
                Q(beneficiario_nome__icontains=q) | Q(cpf_beneficiario=q)
                | Q(numero_protocolo__icontains=q)
            )

        hoje = date.today()
        return JsonResponse({
            "total": qs.count(),
            "solicitacoes": [
                {
                    "id": s.id,
                    "numero_protocolo": s.numero_protocolo,
                    "tipo": s.tipo,
                    "tipo_display": s.get_tipo_display(),
                    "beneficiario_nome": s.beneficiario_nome,
                    "cpf_beneficiario": s.cpf_beneficiario,
                    "plano_origem": s.plano_origem,
                    "plano_destino": s.plano_destino,
                    "status": s.status,
                    "status_display": s.get_status_display(),
                    "data_solicitacao": s.data_solicitacao.isoformat(),
                    "prazo_resposta": s.prazo_resposta.isoformat() if s.prazo_resposta else None,
                    "prazo_vencido": bool(
                        s.prazo_resposta and s.prazo_resposta < hoje
                        and s.status in ("iniciada", "documentacao", "analise_operadora")
                    ),
                    "data_efetivacao": s.data_efetivacao.isoformat() if s.data_efetivacao else None,
                    "carencias_cumpridas": s.carencias_cumpridas,
                }
                for s in qs.order_by("-criado_em")[:200]
            ],
        })

    data = json.loads(request.body)

    # Protocolo sequencial
    total = SolicitacaoPortabilidade.objects.filter(empresa=empresa).count() + 1
    protocolo = f"PORT-ANS-{date.today().year}-{total:06d}"

    # Prazo de resposta: 10 dias úteis (RN 438, art. 11)
    prazo_resposta = _calc_prazo_uteis(_PRAZO_ANALISE_DIAS_UTEIS)

    with transaction.atomic():
        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_beneficiario", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        sol = SolicitacaoPortabilidade.objects.create(
            empresa=empresa,
            tipo=data.get("tipo", "saida"),
            beneficiario_nome=data["beneficiario_nome"],
            cpf_beneficiario=data["cpf_beneficiario"],
            cns_beneficiario=data.get("cns_beneficiario", ""),
            numero_carteirinha=data.get("numero_carteirinha", ""),
            plano_origem=data.get("plano_origem", ""),
            registro_ans_origem=data.get("registro_ans_origem", ""),
            plano_destino=data.get("plano_destino", ""),
            registro_ans_destino=data.get("registro_ans_destino", ""),
            carencias_cumpridas=data.get("carencias_cumpridas", False),
            declaracao_carencia=data.get("declaracao_carencia", ""),
            status="iniciada",
            numero_protocolo=protocolo,
            prazo_resposta=prazo_resposta,
            obs=data.get("obs", ""),
        )

    return JsonResponse({
        "id": sol.id,
        "numero_protocolo": protocolo,
        "prazo_resposta": prazo_resposta.isoformat(),
        "mensagem": f"Portabilidade registrada. Prazo de resposta: {prazo_resposta.strftime('%d/%m/%Y')} (RN 438/2018)",
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_portabilidade_detalhe(request, sol_id):
    """GET/PUT /api/plano-saude/portabilidade-ans/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    SolicitacaoPortabilidade = _get_port_models()
    try:
        sol = SolicitacaoPortabilidade.objects.get(id=sol_id, empresa=empresa)
    except SolicitacaoPortabilidade.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": sol.id,
            "numero_protocolo": sol.numero_protocolo,
            "tipo": sol.tipo,
            "tipo_display": sol.get_tipo_display(),
            "beneficiario_nome": sol.beneficiario_nome,
            "cpf_beneficiario": sol.cpf_beneficiario,
            "cns_beneficiario": sol.cns_beneficiario,
            "numero_carteirinha": sol.numero_carteirinha,
            "plano_origem": sol.plano_origem,
            "registro_ans_origem": sol.registro_ans_origem,
            "plano_destino": sol.plano_destino,
            "registro_ans_destino": sol.registro_ans_destino,
            "carencias_cumpridas": sol.carencias_cumpridas,
            "declaracao_carencia": sol.declaracao_carencia,
            "status": sol.status,
            "status_display": sol.get_status_display(),
            "motivo_negativa": sol.motivo_negativa,
            "data_solicitacao": sol.data_solicitacao.isoformat(),
            "prazo_resposta": sol.prazo_resposta.isoformat() if sol.prazo_resposta else None,
            "data_resposta": sol.data_resposta.isoformat() if sol.data_resposta else None,
            "data_efetivacao": sol.data_efetivacao.isoformat() if sol.data_efetivacao else None,
            "obs": sol.obs,
        })

    data = json.loads(request.body)
    campos = ["status", "motivo_negativa", "data_resposta", "data_efetivacao",
              "carencias_cumpridas", "declaracao_carencia", "obs"]
    for c in campos:
        if c in data:
            setattr(sol, c, data[c])
    sol.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def api_portabilidade_acao(request, sol_id):
    """POST /api/plano-saude/portabilidade-ans/<id>/acao/ — aprovar/negar/efetivar."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    SolicitacaoPortabilidade = _get_port_models()
    try:
        sol = SolicitacaoPortabilidade.objects.get(id=sol_id, empresa=empresa)
    except SolicitacaoPortabilidade.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    data = json.loads(request.body)
    acao = data.get("acao")

    mapa = {
        "solicitar_doc": "documentacao",
        "analisar": "analise_operadora",
        "aprovar": "aprovada",
        "negar": "negada",
        "cancelar": "cancelada",
        "efetivar": "concluida",
    }
    if acao not in mapa:
        return JsonResponse({"erro": f"Ação inválida: {acao}"}, status=400)

    with transaction.atomic():
        sol.status = mapa[acao]
        sol.data_resposta = date.today()
        if acao == "negar":
            sol.motivo_negativa = data.get("motivo", "")
        elif acao == "aprovar":
            # Prazo de efetivação: 30 dias a partir da aprovação (RN 438, art. 14)
            sol.data_efetivacao = date.today() + timedelta(days=_PRAZO_EFETIVACAO_DIAS)
        elif acao == "efetivar":
            sol.data_efetivacao = date.today()
        sol.save()

    return JsonResponse({
        "ok": True,
        "novo_status": sol.status,
        "data_efetivacao": sol.data_efetivacao.isoformat() if sol.data_efetivacao else None,
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_portabilidade_declaracao(request, sol_id):
    """GET /api/plano-saude/portabilidade-ans/<id>/declaracao/ — gera declaração de carência."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    SolicitacaoPortabilidade = _get_port_models()
    try:
        sol = SolicitacaoPortabilidade.objects.get(id=sol_id, empresa=empresa)
    except SolicitacaoPortabilidade.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    # Declaração de carências cumpridas — texto legal (RN 438/2018, art. 7º)
    declaracao = {
        "numero_protocolo": sol.numero_protocolo,
        "emitida_em": date.today().isoformat(),
        "operadora": empresa.nome,
        "registro_ans": sol.registro_ans_origem or "---",
        "beneficiario": {
            "nome": sol.beneficiario_nome,
            "cpf": sol.cpf_beneficiario,
            "cns": sol.cns_beneficiario,
            "carteirinha": sol.numero_carteirinha,
        },
        "plano_atual": sol.plano_origem,
        "plano_destino": sol.plano_destino,
        "carencias_cumpridas": sol.carencias_cumpridas,
        "texto_legal": (
            f"Declaramos para os devidos fins, nos termos da Resolução Normativa ANS nº 438/2018, "
            f"que o beneficiário {sol.beneficiario_nome} (CPF {sol.cpf_beneficiario}), "
            f"portador do plano '{sol.plano_origem}', cumpriu integralmente as carências contratuais, "
            f"estando apto ao exercício do direito de portabilidade de carências conforme previsto "
            f"na legislação vigente."
        ) if sol.carencias_cumpridas else (
            f"Declaramos que o beneficiário {sol.beneficiario_nome} (CPF {sol.cpf_beneficiario}) "
            f"NÃO cumpriu integralmente as carências do plano '{sol.plano_origem}', "
            f"não estando apto à portabilidade de carências (RN 438/2018, art. 4º)."
        ),
        "validade": (date.today() + timedelta(days=30)).isoformat(),
        "alerta_prazo": "Documentação válida por 30 dias (RN 438/2018, art. 8º, §2º).",
    }
    return JsonResponse(declaracao)


# ── KPIs ───────────────────────────────────────────────────────────────────────

def api_portabilidade_kpis(request):
    """GET /api/plano-saude/portabilidade-ans/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    SolicitacaoPortabilidade = _get_port_models()

    qs = SolicitacaoPortabilidade.objects.filter(empresa=empresa)
    por_status = dict(qs.values_list("status").annotate(n=Count("id")).order_by())
    hoje = date.today()
    vencidas = qs.filter(
        prazo_resposta__lt=hoje,
        status__in=["iniciada", "documentacao", "analise_operadora"],
    ).count()
    saidas = qs.filter(tipo="saida", status="concluida").count()
    entradas = qs.filter(tipo="entrada", status="concluida").count()

    return JsonResponse({
        "por_status": por_status,
        "prazo_vencido": vencidas,
        "saidas_concluidas": saidas,
        "entradas_concluidas": entradas,
        "saldo_liquido": entradas - saidas,
    })
