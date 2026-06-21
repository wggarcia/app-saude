"""
Hospital — Manutenção de Equipamentos Médicos
  • Cadastro de equipamento médico-assistencial com calibração
  • Ordens de serviço de manutenção preventiva/corretiva/calibração
"""
import json
from datetime import date

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import EquipamentoMedico, ManutencaoEquipamentoMedico, LeitoHospitalar
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    setor = get_setor(empresa)
    if setor != "hospital":
        return JsonResponse(
            {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
            status=403,
        )
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência hospitalar."}, status=403)
    return empresa


def _equip_to_dict(e):
    return {
        "id": e.id,
        "nome": e.nome,
        "categoria": e.categoria,
        "numero_serie": e.numero_serie,
        "fabricante": e.fabricante,
        "modelo": e.modelo,
        "setor_localizacao": e.setor_localizacao,
        "leito_id": e.leito_id,
        "leito_numero": e.leito.numero if e.leito else "",
        "criticidade": e.criticidade,
        "status": e.status,
        "ultima_calibracao_em": e.ultima_calibracao_em.isoformat() if e.ultima_calibracao_em else None,
        "proxima_calibracao_em": e.proxima_calibracao_em.isoformat() if e.proxima_calibracao_em else None,
        "ativo": e.ativo,
        "total_manutencoes": e.ordens_manutencao.count(),
    }


def _os_to_dict(o):
    return {
        "id": o.id,
        "equipamento_id": o.equipamento_id,
        "equipamento_nome": o.equipamento.nome,
        "tipo": o.tipo,
        "descricao_problema": o.descricao_problema,
        "descricao_servico": o.descricao_servico,
        "responsavel_tecnico": o.responsavel_tecnico,
        "empresa_terceirizada": o.empresa_terceirizada,
        "custo": float(o.custo) if o.custo is not None else None,
        "status": o.status,
        "aberta_em": o.aberta_em.strftime("%d/%m/%Y %H:%M"),
        "concluida_em": o.concluida_em.strftime("%d/%m/%Y %H:%M") if o.concluida_em else None,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_equipamentos_medicos(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    if request.method == "GET":
        qs = EquipamentoMedico.objects.filter(empresa=empresa, ativo=True).select_related("leito")
        status_f = request.GET.get("status", "")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({"equipamentos": [_equip_to_dict(e) for e in qs[:300]]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = (data.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"erro": "nome é obrigatório"}, status=400)

    leito = None
    leito_id = data.get("leito_id")
    if leito_id:
        leito = LeitoHospitalar.objects.filter(pk=leito_id, empresa=empresa).first()

    equip = EquipamentoMedico.objects.create(
        empresa=empresa,
        nome=nome,
        categoria=(data.get("categoria") or "").strip(),
        numero_serie=(data.get("numero_serie") or "").strip(),
        fabricante=(data.get("fabricante") or "").strip(),
        modelo=(data.get("modelo") or "").strip(),
        setor_localizacao=(data.get("setor_localizacao") or "").strip(),
        leito=leito,
        criticidade=data.get("criticidade", 3),
        ultima_calibracao_em=data.get("ultima_calibracao_em") or None,
        proxima_calibracao_em=data.get("proxima_calibracao_em") or None,
    )
    return JsonResponse({"ok": True, "equipamento": _equip_to_dict(equip)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_manutencoes_equipamento(request, equip_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    equip = EquipamentoMedico.objects.filter(pk=equip_id, empresa=empresa).first()
    if not equip:
        return JsonResponse({"erro": "Equipamento não encontrado"}, status=404)

    if request.method == "GET":
        qs = equip.ordens_manutencao.all()[:100]
        return JsonResponse({"ordens": [_os_to_dict(o) for o in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    ordem = ManutencaoEquipamentoMedico.objects.create(
        equipamento=equip,
        tipo=data.get("tipo", "preventiva"),
        descricao_problema=(data.get("descricao_problema") or "").strip(),
        responsavel_tecnico=(data.get("responsavel_tecnico") or "").strip(),
        empresa_terceirizada=(data.get("empresa_terceirizada") or "").strip(),
    )
    equip.status = "manutencao"
    equip.save(update_fields=["status"])

    return JsonResponse({"ok": True, "ordem": _os_to_dict(ordem)}, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
def api_manutencao_concluir(request, os_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    ordem = ManutencaoEquipamentoMedico.objects.select_related("equipamento").filter(
        pk=os_id, equipamento__empresa=empresa,
    ).first()
    if not ordem:
        return JsonResponse({"erro": "Ordem de serviço não encontrada"}, status=404)

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    ordem.descricao_servico = (data.get("descricao_servico") or ordem.descricao_servico).strip()
    custo = data.get("custo")
    if custo not in (None, ""):
        ordem.custo = custo
    ordem.status = "concluida"
    ordem.concluida_em = timezone.now()
    ordem.save()

    ordem.equipamento.status = "operacional"
    if data.get("tipo_calibracao") or ordem.tipo == "calibracao":
        ordem.equipamento.ultima_calibracao_em = date.today()
    ordem.equipamento.save()

    return JsonResponse({"ok": True, "ordem": _os_to_dict(ordem)})
