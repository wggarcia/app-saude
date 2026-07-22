"""
views_governo_tfd.py
Gestão de Veículos e Agendamento de Viagens — TFD (Tratamento Fora de Domicílio), Governo.
GET /api/governo/tfd/cidadao-lookup  Busca cidadão por CNS para pré-preenchimento (Governo isolado)
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .utils import validar_cpf_cadastro
from .access_control import (
    get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
    api_requer_permissao_modulo,
)
from .models import VeiculoTFD, ViagemTFD
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.regulacao_urgencia")
def governo_tfd_page(request):
    return render(request, "governo_tfd.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_tfd_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = timezone.localtime(timezone.now()).date()
    return JsonResponse({
        "veiculos_disponiveis": VeiculoTFD.objects.filter(empresa=e, status="disponivel").count(),
        "veiculos_total": VeiculoTFD.objects.filter(empresa=e).count(),
        "viagens_hoje": ViagemTFD.objects.filter(empresa=e, data_viagem__date=hoje).exclude(status="cancelada").count(),
        "viagens_agendadas": ViagemTFD.objects.filter(empresa=e, status__in=["agendada", "confirmada"]).count(),
    })


# ── Veículos ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_tfd_veiculos(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = VeiculoTFD.objects.filter(empresa=e)
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return JsonResponse({"veiculos": [_veiculo_dict(v) for v in qs]})

    data = json.loads(request.body or "{}")
    placa = data.get("placa", "").strip().upper()
    if not placa:
        return JsonResponse({"erro": "placa obrigatória"}, status=400)
    veiculo = VeiculoTFD.objects.create(
        empresa=e, placa=placa,
        modelo=data.get("modelo", ""),
        tipo=data.get("tipo", "van"),
        capacidade=int(data.get("capacidade", 1)),
        motorista_nome=data.get("motorista_nome", ""),
        motorista_cnh=data.get("motorista_cnh", ""),
        km_atual=int(data.get("km_atual", 0)),
    )
    return JsonResponse(_veiculo_dict(veiculo), status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_tfd_veiculo_detalhe(request, veiculo_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        veiculo = VeiculoTFD.objects.get(pk=veiculo_id, empresa=e)
    except VeiculoTFD.DoesNotExist:
        return JsonResponse({"erro": "Veículo não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    if "status" in data:
        if data["status"] not in dict(VeiculoTFD.STATUS):
            return JsonResponse({"erro": "status inválido"}, status=400)
        veiculo.status = data["status"]
    if "km_atual" in data:
        veiculo.km_atual = int(data["km_atual"])
    if "motorista_nome" in data:
        veiculo.motorista_nome = data["motorista_nome"]
    veiculo.save()
    return JsonResponse(_veiculo_dict(veiculo))


# ── Viagens TFD ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_tfd_viagens(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = ViagemTFD.objects.filter(empresa=e).select_related("veiculo")
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        data_de = request.GET.get("data_de")
        if data_de:
            qs = qs.filter(data_viagem__date__gte=data_de)
        data_ate = request.GET.get("data_ate")
        if data_ate:
            qs = qs.filter(data_viagem__date__lte=data_ate)
        return JsonResponse({"total": qs.count(), "viagens": [_viagem_dict(v) for v in qs[:200]]})

    data = json.loads(request.body or "{}")

    # Pré-preenchimento por CNS: busca no ProntuarioCidadao do próprio município
    cns_informado = (data.get("paciente_cns") or "").strip()
    if cns_informado and not data.get("paciente_nome"):
        from .models import ProntuarioCidadao
        cidadao_ref = ProntuarioCidadao.objects.filter(
            empresa=e, cns=cns_informado
        ).first()
        if cidadao_ref:
            if not data.get("paciente_nome"):
                data["paciente_nome"] = cidadao_ref.nome_completo
            if not data.get("paciente_cpf") and cidadao_ref.cpf:
                data["paciente_cpf"] = cidadao_ref.cpf

    paciente_nome = data.get("paciente_nome", "").strip()
    destino_cidade = data.get("destino_cidade", "").strip()
    data_viagem = parse_datetime(data.get("data_viagem", ""))
    if not paciente_nome or not destino_cidade or not data_viagem:
        return JsonResponse({"erro": "paciente_nome, destino_cidade e data_viagem (ISO) são obrigatórios"}, status=400)

    veiculo = None
    veiculo_id = data.get("veiculo_id")
    if veiculo_id:
        veiculo = VeiculoTFD.objects.filter(pk=veiculo_id, empresa=e).first()

    data_retorno = parse_datetime(data.get("data_retorno_prevista", "")) if data.get("data_retorno_prevista") else None

    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("paciente_cpf", ""), e)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    viagem = ViagemTFD.objects.create(
        empresa=e, veiculo=veiculo,
        paciente_nome=paciente_nome,
        paciente_cpf=data.get("paciente_cpf", ""),
        paciente_cns=data.get("paciente_cns", ""),
        acompanhante_nome=data.get("acompanhante_nome", ""),
        destino_cidade=destino_cidade,
        destino_estabelecimento=data.get("destino_estabelecimento", ""),
        motivo=data.get("motivo", ""),
        data_viagem=data_viagem,
        data_retorno_prevista=data_retorno,
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse(_viagem_dict(viagem), status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_tfd_viagem_detalhe(request, viagem_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        viagem = ViagemTFD.objects.get(pk=viagem_id, empresa=e)
    except ViagemTFD.DoesNotExist:
        return JsonResponse({"erro": "Viagem não encontrada"}, status=404)
    data = json.loads(request.body or "{}")

    if "veiculo_id" in data:
        veiculo = VeiculoTFD.objects.filter(pk=data["veiculo_id"], empresa=e).first() if data["veiculo_id"] else None
        viagem.veiculo = veiculo

    novo_status = data.get("status")
    if novo_status:
        if novo_status not in dict(ViagemTFD.STATUS):
            return JsonResponse({"erro": "status inválido"}, status=400)
        viagem.status = novo_status
        if novo_status == "em_andamento" and viagem.veiculo:
            viagem.veiculo.status = "em_viagem"
            viagem.veiculo.save(update_fields=["status"])
        if novo_status in ("concluida", "cancelada") and viagem.veiculo:
            viagem.veiculo.status = "disponivel"
            viagem.veiculo.save(update_fields=["status"])

    if "km_percorrido" in data:
        viagem.km_percorrido = int(data["km_percorrido"]) if data["km_percorrido"] is not None else None
        if viagem.km_percorrido and viagem.veiculo:
            viagem.veiculo.km_atual += viagem.km_percorrido
            viagem.veiculo.save(update_fields=["km_atual"])

    viagem.save()
    return JsonResponse(_viagem_dict(viagem))


# ── Lookup de cidadão por CNS ─────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_tfd_cidadao_lookup(request):
    """
    GET /api/governo/tfd/cidadao-lookup?cns=<CNS>
    Busca cidadão pelo CNS no cadastro do próprio município para pré-preenchimento
    do agendamento de viagem TFD. Isolado no segmento Governo.
    """
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    cns = (request.GET.get("cns") or "").strip()
    if not cns:
        return JsonResponse({"erro": "Parâmetro 'cns' obrigatório"}, status=400)

    from .models import ProntuarioCidadao

    try:
        cidadao = ProntuarioCidadao.objects.get(empresa=e, cns=cns)
    except ProntuarioCidadao.DoesNotExist:
        return JsonResponse({"encontrado": False, "cidadao": None})
    except ProntuarioCidadao.MultipleObjectsReturned:
        cidadao = ProntuarioCidadao.objects.filter(empresa=e, cns=cns).first()

    return JsonResponse({
        "encontrado": True,
        "cidadao": {
            "nome":            cidadao.nome_completo,
            "data_nascimento": cidadao.data_nascimento.isoformat() if cidadao.data_nascimento else None,
            "cpf":             cidadao.cpf,
            "cns":             cidadao.cns,
            "telefone":        cidadao.telefone,
            "unidade_saude":   cidadao.unidade_saude,
        },
    })


def _veiculo_dict(v):
    return {
        "id": v.id,
        "placa": v.placa,
        "modelo": v.modelo,
        "tipo": v.tipo,
        "tipo_display": v.get_tipo_display(),
        "capacidade": v.capacidade,
        "motorista_nome": v.motorista_nome,
        "status": v.status,
        "status_display": v.get_status_display(),
        "km_atual": v.km_atual,
    }


def _viagem_dict(v):
    return {
        "id": v.id,
        "veiculo_id": v.veiculo_id,
        "veiculo_placa": v.veiculo.placa if v.veiculo else None,
        "paciente_nome": v.paciente_nome,
        "paciente_cpf": v.paciente_cpf,
        "acompanhante_nome": v.acompanhante_nome,
        "destino_cidade": v.destino_cidade,
        "destino_estabelecimento": v.destino_estabelecimento,
        "motivo": v.motivo,
        "data_viagem": v.data_viagem.isoformat(),
        "data_retorno_prevista": v.data_retorno_prevista.isoformat() if v.data_retorno_prevista else None,
        "status": v.status,
        "status_display": v.get_status_display(),
        "km_percorrido": v.km_percorrido,
    }
