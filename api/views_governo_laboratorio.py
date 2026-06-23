"""
views_governo_laboratorio.py
Laboratório municipal — LIS (Governo): solicitação → coleta → digitação → liberação →
entrega, com protocolo de acesso do paciente ao resultado.
"""
import json
import random
import string
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
    api_requer_permissao_modulo,
)
from .models import ExameLaboratorialCatalogo, SolicitacaoExameLab, EmpresaUnidade
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


def _gerar_protocolo():
    sufixo = "".join(random.choices(string.digits, k=8))
    return f"LAB{sufixo}"


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def governo_laboratorio_page(request):
    return render(request, "governo_laboratorio.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_lab_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    qs = SolicitacaoExameLab.objects.filter(empresa=e)
    return JsonResponse({
        "aguardando_coleta": qs.filter(status="aguardando_coleta").count(),
        "em_analise": qs.filter(status__in=["coletado", "em_analise"]).count(),
        "liberados_hoje": qs.filter(
            status="liberado", liberado_em__date=timezone.localtime(timezone.now()).date()
        ).count(),
        "fora_referencia_pendente": qs.filter(status="em_analise", fora_referencia=True).count(),
    })


# ── Catálogo de exames ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_lab_catalogo(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = ExameLaboratorialCatalogo.objects.filter(empresa=e, ativo=True)
        return JsonResponse({"exames": [_catalogo_dict(x) for x in qs]})

    data = json.loads(request.body or "{}")
    nome = data.get("nome", "").strip()
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)
    exame = ExameLaboratorialCatalogo.objects.create(
        empresa=e, nome=nome,
        sigla=data.get("sigla", ""),
        metodo_analise=data.get("metodo_analise", ""),
        tipo_amostra=data.get("tipo_amostra", ""),
        valor_referencia_min=_to_decimal_or_none(data.get("valor_referencia_min")),
        valor_referencia_max=_to_decimal_or_none(data.get("valor_referencia_max")),
        valor_referencia_texto=data.get("valor_referencia_texto", ""),
        unidade_medida=data.get("unidade_medida", ""),
        prazo_entrega_dias=int(data.get("prazo_entrega_dias", 2)),
    )
    return JsonResponse(_catalogo_dict(exame), status=201)


# ── Solicitações ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_lab_solicitacoes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = SolicitacaoExameLab.objects.filter(empresa=e).select_related("exame", "unidade")
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        protocolo = request.GET.get("protocolo")
        if protocolo:
            qs = qs.filter(protocolo=protocolo)
        return JsonResponse({"total": qs.count(), "solicitacoes": [_solicitacao_dict(s) for s in qs[:200]]})

    data = json.loads(request.body or "{}")
    try:
        exame = ExameLaboratorialCatalogo.objects.get(pk=data["exame_id"], empresa=e)
    except (KeyError, ExameLaboratorialCatalogo.DoesNotExist):
        return JsonResponse({"erro": "exame_id válido é obrigatório"}, status=400)
    paciente_nome = data.get("paciente_nome", "").strip()
    if not paciente_nome:
        return JsonResponse({"erro": "paciente_nome obrigatório"}, status=400)

    unidade = None
    if data.get("unidade_id"):
        unidade = EmpresaUnidade.objects.filter(pk=data["unidade_id"], empresa=e).first()

    protocolo = _gerar_protocolo()
    while SolicitacaoExameLab.objects.filter(protocolo=protocolo).exists():
        protocolo = _gerar_protocolo()

    data_entrega = None
    data_agendamento = parse_datetime(data.get("data_agendamento", "")) if data.get("data_agendamento") else None
    if data_agendamento:
        data_entrega = (data_agendamento + timezone.timedelta(days=exame.prazo_entrega_dias)).date()

    solicitacao = SolicitacaoExameLab.objects.create(
        empresa=e, unidade=unidade, exame=exame, protocolo=protocolo,
        paciente_nome=paciente_nome,
        paciente_cpf=data.get("paciente_cpf", ""),
        paciente_cns=data.get("paciente_cns", ""),
        profissional_solicitante=data.get("profissional_solicitante", ""),
        urgente=bool(data.get("urgente", False)),
        data_agendamento=data_agendamento,
        data_entrega_prevista=data_entrega,
    )
    return JsonResponse(_solicitacao_dict(solicitacao), status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_lab_solicitacao_detalhe(request, sol_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        sol = SolicitacaoExameLab.objects.get(pk=sol_id, empresa=e)
    except SolicitacaoExameLab.DoesNotExist:
        return JsonResponse({"erro": "Solicitação não encontrada"}, status=404)
    data = json.loads(request.body or "{}")
    acao = data.get("acao")

    if acao == "coletar":
        sol.status = "coletado"
        sol.data_coleta = timezone.now()

    elif acao == "digitar_resultado":
        valor = data.get("valor_resultado", "")
        if not valor:
            return JsonResponse({"erro": "valor_resultado obrigatório"}, status=400)
        sol.valor_resultado = valor
        sol.fora_referencia = _checar_fora_referencia(sol.exame, valor)
        sol.status = "em_analise"

    elif acao == "liberar":
        liberado_por = data.get("liberado_por", "").strip()
        if not liberado_por:
            return JsonResponse({"erro": "liberado_por (nome do bioquímico/biomédico) obrigatório"}, status=400)
        if not sol.valor_resultado:
            return JsonResponse({"erro": "Não é possível liberar sem resultado digitado"}, status=400)
        sol.status = "liberado"
        sol.liberado_por = liberado_por
        sol.liberado_em = timezone.now()

    elif acao == "retificar":
        retificado_por = data.get("retificado_por", "").strip()
        novo_valor = data.get("valor_resultado", "")
        if not retificado_por or not novo_valor:
            return JsonResponse({"erro": "retificado_por e valor_resultado são obrigatórios"}, status=400)
        sol.valor_resultado = novo_valor
        sol.fora_referencia = _checar_fora_referencia(sol.exame, novo_valor)
        sol.retificado_por = retificado_por
        sol.retificado_em = timezone.now()

    elif acao == "cancelar":
        sol.status = "cancelado"

    else:
        return JsonResponse({"erro": "acao inválida (coletar|digitar_resultado|liberar|retificar|cancelar)"}, status=400)

    sol.save()
    return JsonResponse(_solicitacao_dict(sol))


# ── Protocolo de acesso do paciente ao resultado ──────────────────────────────

@require_http_methods(["GET"])
def api_lab_resultado_paciente(request):
    """Consulta pública do resultado por protocolo + CPF — não exige login de operador."""
    protocolo = request.GET.get("protocolo", "").strip()
    cpf = request.GET.get("cpf", "").strip()
    if not protocolo or not cpf:
        return JsonResponse({"erro": "protocolo e cpf são obrigatórios"}, status=400)
    try:
        sol = SolicitacaoExameLab.objects.get(protocolo=protocolo, paciente_cpf=cpf)
    except SolicitacaoExameLab.DoesNotExist:
        return JsonResponse({"erro": "Protocolo não encontrado para o CPF informado"}, status=404)
    if sol.status != "liberado":
        return JsonResponse({"status": sol.status, "status_display": sol.get_status_display(),
                              "mensagem": "Resultado ainda não liberado."})
    return JsonResponse(_solicitacao_dict(sol))


def _checar_fora_referencia(exame, valor):
    if exame.valor_referencia_min is None and exame.valor_referencia_max is None:
        return False
    try:
        v = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return False
    if exame.valor_referencia_min is not None and v < exame.valor_referencia_min:
        return True
    if exame.valor_referencia_max is not None and v > exame.valor_referencia_max:
        return True
    return False


def _to_decimal_or_none(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _catalogo_dict(x):
    return {
        "id": x.id, "nome": x.nome, "sigla": x.sigla, "metodo_analise": x.metodo_analise,
        "tipo_amostra": x.tipo_amostra,
        "valor_referencia_min": str(x.valor_referencia_min) if x.valor_referencia_min is not None else None,
        "valor_referencia_max": str(x.valor_referencia_max) if x.valor_referencia_max is not None else None,
        "valor_referencia_texto": x.valor_referencia_texto,
        "unidade_medida": x.unidade_medida,
        "prazo_entrega_dias": x.prazo_entrega_dias,
    }


def _solicitacao_dict(s):
    return {
        "id": s.id,
        "protocolo": s.protocolo,
        "exame_nome": s.exame.nome,
        "unidade_nome": s.unidade.nome if s.unidade else None,
        "paciente_nome": s.paciente_nome,
        "paciente_cpf": s.paciente_cpf,
        "profissional_solicitante": s.profissional_solicitante,
        "urgente": s.urgente,
        "status": s.status,
        "status_display": s.get_status_display(),
        "data_agendamento": s.data_agendamento.isoformat() if s.data_agendamento else None,
        "data_coleta": s.data_coleta.isoformat() if s.data_coleta else None,
        "data_entrega_prevista": s.data_entrega_prevista.isoformat() if s.data_entrega_prevista else None,
        "valor_resultado": s.valor_resultado,
        "fora_referencia": s.fora_referencia,
        "liberado_por": s.liberado_por,
        "liberado_em": s.liberado_em.isoformat() if s.liberado_em else None,
        "retificado_por": s.retificado_por,
        "criado_em": s.criado_em.isoformat(),
    }
