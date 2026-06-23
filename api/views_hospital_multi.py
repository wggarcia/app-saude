"""
Hospital — Equipe Multiprofissional
  • SAE (Sistematização da Assistência de Enfermagem) — avaliação, escalas, diagnósticos, plano de cuidados
  • Avaliação funcional de Fisioterapia — ADM, força muscular (MRC), dor (EVA), plano terapêutico
  • Avaliação e plano Nutricional — antropometria, via de alimentação, necessidades, dieta
"""
import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_feature
from .models import (
    PacienteInternado,
    AvaliacaoEnfermagem, AvaliacaoFisioterapia, AvaliacaoNutricional,
)
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


def _pac_or_404(empresa, pac_id):
    try:
        return PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
    except PacienteInternado.DoesNotExist:
        return None


def _dec(val):
    try:
        return Decimal(str(val)) if val not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(val):
    try:
        return int(val) if val not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ─── SAE — Enfermagem ─────────────────────────────────────────────────────────

def _enferm_to_dict(a):
    return {
        "id": a.id,
        "historico_enfermagem": a.historico_enfermagem,
        "exame_fisico": a.exame_fisico,
        "escala_braden": a.escala_braden,
        "escala_morse": a.escala_morse,
        "diagnosticos_enfermagem": a.diagnosticos_enfermagem,
        "plano_cuidados": a.plano_cuidados,
        "responsavel": a.responsavel,
        "coren": a.coren,
        "status": a.status,
        "criado_em": a.criado_em.strftime("%d/%m/%Y %H:%M"),
        "atualizado_em": a.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.equipe_multi")
def api_avaliacoes_enfermagem(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        qs = pac.avaliacoes_enfermagem.all()[:100]
        return JsonResponse({"avaliacoes": [_enferm_to_dict(a) for a in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    avaliacao = AvaliacaoEnfermagem.objects.create(
        paciente=pac,
        historico_enfermagem=(data.get("historico_enfermagem") or "").strip(),
        exame_fisico=data.get("exame_fisico") or {},
        escala_braden=_int(data.get("escala_braden")),
        escala_morse=_int(data.get("escala_morse")),
        diagnosticos_enfermagem=data.get("diagnosticos_enfermagem") or [],
        plano_cuidados=data.get("plano_cuidados") or [],
        responsavel=(data.get("responsavel") or "").strip(),
        coren=(data.get("coren") or "").strip(),
        status=data.get("status", "ativa"),
    )
    return JsonResponse({"ok": True, "avaliacao": _enferm_to_dict(avaliacao)}, status=201)


# ─── Fisioterapia ─────────────────────────────────────────────────────────────

def _fisio_to_dict(a):
    return {
        "id": a.id,
        "queixa_principal": a.queixa_principal,
        "amplitude_movimento": a.amplitude_movimento,
        "forca_muscular": a.forca_muscular,
        "escala_dor_eva": a.escala_dor_eva,
        "capacidade_funcional": a.capacidade_funcional,
        "diagnostico_fisioterapeutico": a.diagnostico_fisioterapeutico,
        "plano_terapeutico": a.plano_terapeutico,
        "objetivos": a.objetivos,
        "responsavel": a.responsavel,
        "crefito": a.crefito,
        "status": a.status,
        "criado_em": a.criado_em.strftime("%d/%m/%Y %H:%M"),
        "atualizado_em": a.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.equipe_multi")
def api_avaliacoes_fisioterapia(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        qs = pac.avaliacoes_fisioterapia.all()[:100]
        return JsonResponse({"avaliacoes": [_fisio_to_dict(a) for a in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    avaliacao = AvaliacaoFisioterapia.objects.create(
        paciente=pac,
        queixa_principal=(data.get("queixa_principal") or "").strip(),
        amplitude_movimento=data.get("amplitude_movimento") or {},
        forca_muscular=data.get("forca_muscular") or {},
        escala_dor_eva=_int(data.get("escala_dor_eva")),
        capacidade_funcional=(data.get("capacidade_funcional") or "").strip(),
        diagnostico_fisioterapeutico=(data.get("diagnostico_fisioterapeutico") or "").strip(),
        plano_terapeutico=data.get("plano_terapeutico") or [],
        objetivos=(data.get("objetivos") or "").strip(),
        responsavel=(data.get("responsavel") or "").strip(),
        crefito=(data.get("crefito") or "").strip(),
        status=data.get("status", "ativa"),
    )
    return JsonResponse({"ok": True, "avaliacao": _fisio_to_dict(avaliacao)}, status=201)


# ─── Nutrição ──────────────────────────────────────────────────────────────────

def _nutri_to_dict(a):
    return {
        "id": a.id,
        "peso_kg": float(a.peso_kg) if a.peso_kg is not None else None,
        "altura_cm": a.altura_cm,
        "imc": float(a.imc) if a.imc is not None else None,
        "circunferencias": a.circunferencias,
        "diagnostico_nutricional": a.diagnostico_nutricional,
        "via_alimentacao": a.via_alimentacao,
        "necessidade_calorica_kcal": a.necessidade_calorica_kcal,
        "necessidade_proteica_g": a.necessidade_proteica_g,
        "restricoes_alergias": a.restricoes_alergias,
        "plano_dietetico": a.plano_dietetico,
        "responsavel": a.responsavel,
        "crn": a.crn,
        "status": a.status,
        "criado_em": a.criado_em.strftime("%d/%m/%Y %H:%M"),
        "atualizado_em": a.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.equipe_multi")
def api_avaliacoes_nutricionais(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        qs = pac.avaliacoes_nutricionais.all()[:100]
        return JsonResponse({"avaliacoes": [_nutri_to_dict(a) for a in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    peso = _dec(data.get("peso_kg"))
    altura = _int(data.get("altura_cm"))
    imc = None
    if peso and altura:
        altura_m = Decimal(altura) / Decimal(100)
        imc = round(peso / (altura_m * altura_m), 2)

    avaliacao = AvaliacaoNutricional.objects.create(
        paciente=pac,
        peso_kg=peso,
        altura_cm=altura,
        imc=imc,
        circunferencias=data.get("circunferencias") or {},
        diagnostico_nutricional=(data.get("diagnostico_nutricional") or "").strip(),
        via_alimentacao=data.get("via_alimentacao", "oral"),
        necessidade_calorica_kcal=_int(data.get("necessidade_calorica_kcal")),
        necessidade_proteica_g=_int(data.get("necessidade_proteica_g")),
        restricoes_alergias=(data.get("restricoes_alergias") or "").strip(),
        plano_dietetico=data.get("plano_dietetico") or [],
        responsavel=(data.get("responsavel") or "").strip(),
        crn=(data.get("crn") or "").strip(),
        status=data.get("status", "ativa"),
    )
    return JsonResponse({"ok": True, "avaliacao": _nutri_to_dict(avaliacao)}, status=201)
