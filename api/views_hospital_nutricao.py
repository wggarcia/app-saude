"""
Hospital — Nutrição e Dietética Hospitalar
  • Prescrição e controle de dietas hospitalares (DietaHospitalar)
  • Triagem e avaliação nutricional (AvaliacaoNutricional)
  • KPIs do módulo de nutrição
"""
import json
import logging
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


# ── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ── Lazy model imports (try/except para modelos opcionais) ───────────────────

def _get_dieta_model():
    try:
        from .models import DietaHospitalar
        return DietaHospitalar
    except ImportError:
        return None


def _get_avaliacao_model():
    try:
        from .models import AvaliacaoNutricional
        return AvaliacaoNutricional
    except ImportError:
        return None


# ── Serializers ──────────────────────────────────────────────────────────────

def _dieta_to_dict(d):
    return {
        "id": d.id,
        "paciente_internado_id": d.paciente_internado_id,
        "nome_paciente": d.nome_paciente,
        "tipo_dieta": d.tipo_dieta,
        "tipo_dieta_display": d.get_tipo_dieta_display(),
        "via_administracao": d.via_administracao,
        "via_administracao_display": d.get_via_administracao_display(),
        "calorias_kcal": float(d.calorias_kcal) if d.calorias_kcal is not None else None,
        "proteinas_g": float(d.proteinas_g) if d.proteinas_g is not None else None,
        "restricoes": d.restricoes,
        "data_inicio": d.data_inicio.strftime("%Y-%m-%d") if d.data_inicio else None,
        "data_fim": d.data_fim.strftime("%Y-%m-%d") if d.data_fim else None,
        "prescrito_por": d.prescrito_por,
        "ativa": d.ativa,
        "criado_em": d.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _triagem_to_dict(a):
    return {
        "id": a.id,
        "paciente_id": a.paciente_id,
        "paciente_nome": a.paciente.nome if a.paciente_id else "",
        "peso_kg": float(a.peso_kg) if a.peso_kg is not None else None,
        "altura_cm": a.altura_cm,
        "imc": float(a.imc) if a.imc is not None else None,
        "diagnostico_nutricional": a.diagnostico_nutricional,
        "via_alimentacao": a.via_alimentacao,
        "via_alimentacao_display": a.get_via_alimentacao_display(),
        "necessidade_calorica_kcal": a.necessidade_calorica_kcal,
        "necessidade_proteica_g": a.necessidade_proteica_g,
        "restricoes_alergias": a.restricoes_alergias,
        "responsavel": a.responsavel,
        "crn": a.crn,
        "status": a.status,
        "criado_em": a.criado_em.strftime("%d/%m/%Y %H:%M"),
        "atualizado_em": a.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ── Página ───────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.clinico", "Nutrição")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_nutricao_page(request):
    return render(request, "hospital_nutricao.html")


# ── Dietas ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.clinico")
def api_nutricao_dietas(request):
    """
    GET  /api/hospital/nutricao/dietas — lista DietaHospitalar ativas
    POST /api/hospital/nutricao/dietas — prescreve nova dieta
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado ou setor inválido"}, status=401)

    DietaHospitalar = _get_dieta_model()
    if DietaHospitalar is None:
        return JsonResponse({"erro": "Módulo de dietas não disponível"}, status=503)

    if request.method == "GET":
        try:
            qs = DietaHospitalar.objects.filter(empresa=empresa, ativa=True).order_by("-data_inicio")[:200]
            return JsonResponse({"dietas": [_dieta_to_dict(d) for d in qs]})
        except Exception as exc:
            logger.exception("Erro ao listar dietas: %s", exc)
            return JsonResponse({"erro": "Erro interno ao listar dietas"}, status=500)

    # POST
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_internado_id = data.get("paciente_internado_id")
    tipo_dieta = (data.get("tipo_dieta") or "livre").strip()
    via_administracao = (data.get("via_administracao") or "oral").strip()
    calorias_kcal = data.get("calorias_kcal")
    proteinas_g = data.get("proteinas_g")
    restricoes = (data.get("restricoes") or "").strip()
    data_inicio_raw = data.get("data_inicio")
    prescrito_por = (data.get("prescrito_por") or "").strip()

    if not data_inicio_raw:
        return JsonResponse({"erro": "data_inicio é obrigatório"}, status=400)

    try:
        data_inicio = date.fromisoformat(str(data_inicio_raw))
    except ValueError:
        return JsonResponse({"erro": "data_inicio inválido — use YYYY-MM-DD"}, status=400)

    # Resolve nome do paciente
    nome_paciente = ""
    paciente_obj = None
    if paciente_internado_id:
        try:
            from .models import PacienteInternado
            paciente_obj = PacienteInternado.objects.filter(
                pk=paciente_internado_id, empresa=empresa
            ).first()
            if paciente_obj:
                nome_paciente = paciente_obj.nome
        except Exception:
            pass

    try:
        dieta = DietaHospitalar.objects.create(
            empresa=empresa,
            paciente_internado=paciente_obj,
            nome_paciente=nome_paciente,
            tipo_dieta=tipo_dieta,
            via_administracao=via_administracao,
            calorias_kcal=calorias_kcal if calorias_kcal not in (None, "") else None,
            proteinas_g=proteinas_g if proteinas_g not in (None, "") else None,
            restricoes=restricoes,
            data_inicio=data_inicio,
            prescrito_por=prescrito_por,
            ativa=True,
        )
        return JsonResponse({"ok": True, "dieta": _dieta_to_dict(dieta)}, status=201)
    except Exception as exc:
        logger.exception("Erro ao criar dieta: %s", exc)
        return JsonResponse({"erro": "Erro interno ao criar dieta"}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.clinico")
def api_nutricao_dieta_detalhe(request, pk):
    """
    GET   /api/hospital/nutricao/dietas/<pk> — detalhe da dieta
    PATCH /api/hospital/nutricao/dietas/<pk> — atualiza dieta
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado ou setor inválido"}, status=401)

    DietaHospitalar = _get_dieta_model()
    if DietaHospitalar is None:
        return JsonResponse({"erro": "Módulo de dietas não disponível"}, status=503)

    try:
        dieta = DietaHospitalar.objects.get(pk=pk, empresa=empresa)
    except DietaHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Dieta não encontrada"}, status=404)
    except Exception as exc:
        logger.exception("Erro ao buscar dieta %s: %s", pk, exc)
        return JsonResponse({"erro": "Erro interno"}, status=500)

    if request.method == "GET":
        return JsonResponse({"dieta": _dieta_to_dict(dieta)})

    # PATCH
    try:
        data = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    try:
        if "tipo_dieta" in data:
            dieta.tipo_dieta = data["tipo_dieta"]
        if "via_administracao" in data or "via" in data:
            dieta.via_administracao = data.get("via_administracao") or data.get("via") or dieta.via_administracao
        if "calorias_kcal" in data or "calorias" in data:
            val = data.get("calorias_kcal") if "calorias_kcal" in data else data.get("calorias")
            dieta.calorias_kcal = val if val not in (None, "") else None
        if "data_fim" in data:
            raw = data["data_fim"]
            dieta.data_fim = date.fromisoformat(str(raw)) if raw else None
        if "ativa" in data:
            dieta.ativa = bool(data["ativa"])
        dieta.save()
        return JsonResponse({"ok": True, "dieta": _dieta_to_dict(dieta)})
    except Exception as exc:
        logger.exception("Erro ao atualizar dieta %s: %s", pk, exc)
        return JsonResponse({"erro": "Erro interno ao atualizar dieta"}, status=500)


# ── Triagens / Avaliações Nutricionais ───────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.clinico")
def api_nutricao_triagens(request):
    """
    GET  /api/hospital/nutricao/triagens — lista AvaliacaoNutricional do mês atual
    POST /api/hospital/nutricao/triagens — cria nova AvaliacaoNutricional
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado ou setor inválido"}, status=401)

    AvaliacaoNutricional = _get_avaliacao_model()
    if AvaliacaoNutricional is None:
        return JsonResponse({"erro": "Módulo de avaliação nutricional não disponível"}, status=503)

    if request.method == "GET":
        try:
            hoje = timezone.now()
            qs = AvaliacaoNutricional.objects.filter(
                paciente__empresa=empresa,
                criado_em__year=hoje.year,
                criado_em__month=hoje.month,
            ).select_related("paciente").order_by("-criado_em")[:200]
            return JsonResponse({"triagens": [_triagem_to_dict(a) for a in qs]})
        except Exception as exc:
            logger.exception("Erro ao listar triagens: %s", exc)
            return JsonResponse({"erro": "Erro interno ao listar triagens"}, status=500)

    # POST
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_id = data.get("paciente_id") or data.get("paciente_internado_id")
    peso = data.get("peso") or data.get("peso_kg")
    altura = data.get("altura") or data.get("altura_cm")
    imc_informado = data.get("imc")

    if not paciente_id:
        return JsonResponse({"erro": "paciente_id é obrigatório"}, status=400)

    try:
        from .models import PacienteInternado
        paciente_obj = PacienteInternado.objects.filter(
            pk=paciente_id, empresa=empresa
        ).first()
    except Exception:
        paciente_obj = None

    if not paciente_obj:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    # Calcula IMC se peso e altura fornecidos e imc não informado
    imc_calculado = imc_informado
    try:
        if peso and altura and not imc_informado:
            altura_m = float(altura) / 100.0
            if altura_m > 0:
                imc_calculado = round(float(peso) / (altura_m ** 2), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        imc_calculado = None

    try:
        avaliacao = AvaliacaoNutricional.objects.create(
            paciente=paciente_obj,
            peso_kg=peso if peso not in (None, "") else None,
            altura_cm=altura if altura not in (None, "") else None,
            imc=imc_calculado,
            diagnostico_nutricional=(data.get("diagnostico_nutricional") or "").strip(),
            via_alimentacao=(data.get("via_alimentacao") or "oral").strip(),
            necessidade_calorica_kcal=data.get("necessidade_calorica_kcal") or None,
            necessidade_proteica_g=data.get("necessidade_proteica_g") or None,
            restricoes_alergias=(data.get("restricoes_alergias") or "").strip(),
            responsavel=(data.get("responsavel") or "").strip(),
            crn=(data.get("crn") or "").strip(),
            status="ativa",
        )
        return JsonResponse({"ok": True, "triagem": _triagem_to_dict(avaliacao)}, status=201)
    except Exception as exc:
        logger.exception("Erro ao criar triagem nutricional: %s", exc)
        return JsonResponse({"erro": "Erro interno ao criar triagem"}, status=500)


# ── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.clinico")
def api_nutricao_kpis(request):
    """GET /api/hospital/nutricao/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado ou setor inválido"}, status=401)

    kpis = {
        "dietas_ativas": 0,
        "dietas_enteral": 0,
        "dietas_parenteral": 0,
        "triagens_mes": 0,
    }

    DietaHospitalar = _get_dieta_model()
    if DietaHospitalar is not None:
        try:
            kpis["dietas_ativas"] = DietaHospitalar.objects.filter(
                empresa=empresa, ativa=True
            ).count()
            kpis["dietas_enteral"] = DietaHospitalar.objects.filter(
                empresa=empresa, ativa=True, tipo_dieta="enteral"
            ).count()
            kpis["dietas_parenteral"] = DietaHospitalar.objects.filter(
                empresa=empresa, ativa=True, tipo_dieta="parenteral"
            ).count()
        except Exception as exc:
            logger.warning("KPI dietas indisponível: %s", exc)

    AvaliacaoNutricional = _get_avaliacao_model()
    if AvaliacaoNutricional is not None:
        try:
            hoje = timezone.now()
            kpis["triagens_mes"] = AvaliacaoNutricional.objects.filter(
                paciente__empresa=empresa,
                criado_em__year=hoje.year,
                criado_em__month=hoje.month,
            ).count()
        except Exception as exc:
            logger.warning("KPI triagens indisponível: %s", exc)

    return JsonResponse(kpis)
