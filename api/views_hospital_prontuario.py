"""
Hospital — Prontuário Eletrônico (EMR)
  • ProntuarioHospitalar  — cadastro do paciente
  • EvolucaoProntuario   — evoluções clínicas
  • PrescricaoProntuario — prescrições
"""
import json

from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .utils import validar_cpf_cadastro
from .services.identidade_paciente import resolver_identidade
from .access_control import (
    api_requer_feature,
    api_requer_gerencia,
    get_setor,
    principal_pode_operacao_setorial,
    requer_setor,
    requer_feature_pacote,
    requer_operacao_page,
    requer_permissao_modulo,
)
from .models import ProntuarioHospitalar, EvolucaoProntuario, PrescricaoProntuario
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _empresa(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "hospital":
        return JsonResponse({"erro": "Módulo não disponível para este plano."}, status=403)
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência hospitalar."}, status=403)
    return empresa


# ─── Serializers ──────────────────────────────────────────────────────────────

def _pront_to_dict(p):
    return {
        "id": p.id,
        "numero_prontuario": p.numero_prontuario,
        "paciente_nome": p.paciente_nome,
        "paciente_cpf": p.paciente_cpf,
        "paciente_nascimento": p.paciente_nascimento.strftime("%Y-%m-%d") if p.paciente_nascimento else None,
        "paciente_sexo": p.paciente_sexo,
        "paciente_telefone": p.paciente_telefone,
        "alergias": p.alergias,
        "comorbidades": p.comorbidades,
        "observacoes": p.observacoes,
        "criado_em": p.criado_em.strftime("%d/%m/%Y %H:%M"),
        "atualizado_em": p.atualizado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _evo_to_dict(e):
    return {
        "id": e.id,
        "prontuario_id": e.prontuario_id,
        "profissional": e.profissional,
        "crm_coren": e.crm_coren,
        "tipo": e.tipo,
        "texto": e.texto,
        "cid10": e.cid10,
        "assinado_em": e.assinado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _presc_to_dict(p):
    return {
        "id": p.id,
        "prontuario_id": p.prontuario_id,
        "profissional": p.profissional,
        "medicamento": p.medicamento,
        "dose": p.dose,
        "via": p.via,
        "frequencia": p.frequencia,
        "duracao": p.duracao,
        "dispensado": p.dispensado,
        "prescrito_em": p.prescrito_em.strftime("%d/%m/%Y %H:%M"),
        "ia_aprovada": p.ia_aprovada,
        "ia_observacao": p.ia_observacao,
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.emr", "Prontuário Eletrônico")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_prontuario_page(request):
    return render(request, "hospital_prontuario.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Prontuário lista / novo ─────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.emr")
@require_http_methods(["GET"])
def api_prontuario_hospitalar_lista(request):
    """GET ?q=nome_ou_cpf"""
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    q = (request.GET.get("q") or "").strip()
    qs = ProntuarioHospitalar.objects.filter(empresa=empresa)
    if q:
        qs = qs.filter(Q(paciente_nome__icontains=q) | Q(paciente_cpf__icontains=q))
    qs = qs[:50]
    return JsonResponse({"prontuarios": [_pront_to_dict(p) for p in qs]})


@csrf_exempt
@api_requer_feature("hospital.emr")
@require_http_methods(["POST"])
def api_prontuario_hospitalar_novo(request):
    """POST → create ProntuarioHospitalar"""
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = (data.get("paciente_nome") or "").strip()
    if not nome:
        return JsonResponse({"erro": "paciente_nome é obrigatório"}, status=400)

    nasc = data.get("paciente_nascimento") or None
    if nasc:
        from datetime import datetime
        try:
            nasc = datetime.strptime(nasc, "%Y-%m-%d").date()
        except ValueError:
            nasc = None

    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("paciente_cpf", ""), empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    identidade = resolver_identidade(
        empresa, nome=nome, cpf=data.get("paciente_cpf", ""), data_nascimento=nasc,
    )
    p = ProntuarioHospitalar.objects.create(
        empresa=empresa,
        numero_prontuario=data.get("numero_prontuario", ""),
        paciente_nome=nome,
        paciente_cpf=data.get("paciente_cpf", ""),
        paciente_nascimento=nasc,
        paciente_sexo=data.get("paciente_sexo", "M"),
        paciente_telefone=data.get("paciente_telefone", ""),
        alergias=data.get("alergias", ""),
        comorbidades=data.get("comorbidades", ""),
        observacoes=data.get("observacoes", ""),
        identidade=identidade,
    )
    return JsonResponse({"ok": True, "prontuario": _pront_to_dict(p)}, status=201)


@csrf_exempt
@api_requer_feature("hospital.emr")
@require_http_methods(["GET", "POST"])
def api_prontuario_hospitalar(request):
    if request.method == "POST":
        return api_prontuario_hospitalar_novo(request)
    return api_prontuario_hospitalar_lista(request)


# ─── API: Prontuário detalhe / update ─────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.emr")
@require_http_methods(["GET", "PUT"])
def api_prontuario_hospitalar_detalhe(request, pront_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        p = ProntuarioHospitalar.objects.get(pk=pront_id, empresa=empresa)
    except ProntuarioHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Prontuário não encontrado"}, status=404)

    if request.method == "GET":
        d = _pront_to_dict(p)
        d["evolucoes"] = [_evo_to_dict(e) for e in p.evolucoes.all()[:20]]
        d["prescricoes"] = [_presc_to_dict(pr) for pr in p.prescricoes.all()[:20]]
        return JsonResponse({"prontuario": d})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    for field in ("numero_prontuario", "paciente_nome", "paciente_cpf", "paciente_sexo",
                  "paciente_telefone", "alergias", "comorbidades", "observacoes"):
        if field in data:
            setattr(p, field, data[field])

    if "paciente_nascimento" in data and data["paciente_nascimento"]:
        from datetime import datetime
        try:
            p.paciente_nascimento = datetime.strptime(data["paciente_nascimento"], "%Y-%m-%d").date()
        except ValueError:
            pass

    if {"paciente_nome", "paciente_cpf", "paciente_nascimento"} & set(data):
        p.identidade = resolver_identidade(
            empresa, nome=p.paciente_nome, cpf=p.paciente_cpf,
            data_nascimento=p.paciente_nascimento,
        )

    p.save()
    return JsonResponse({"ok": True, "prontuario": _pront_to_dict(p)})


# ─── API: Evoluções ────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.emr")
@require_http_methods(["GET", "POST"])
def api_prontuario_evolucoes(request, pront_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pront = ProntuarioHospitalar.objects.get(pk=pront_id, empresa=empresa)
    except ProntuarioHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Prontuário não encontrado"}, status=404)

    if request.method == "GET":
        evos = pront.evolucoes.all()
        return JsonResponse({"evolucoes": [_evo_to_dict(e) for e in evos]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    texto = (data.get("texto") or "").strip()
    profissional = (data.get("profissional") or "").strip()
    if not texto or not profissional:
        return JsonResponse({"erro": "texto e profissional são obrigatórios"}, status=400)

    evo = EvolucaoProntuario.objects.create(
        prontuario=pront,
        profissional=profissional,
        crm_coren=data.get("crm_coren", ""),
        tipo=data.get("tipo", "medica"),
        texto=texto,
        cid10=data.get("cid10", ""),
    )
    return JsonResponse({"ok": True, "evolucao": _evo_to_dict(evo)}, status=201)


# ─── API: Prescrições ─────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.emr")
@require_http_methods(["GET", "POST"])
def api_prontuario_prescricoes(request, pront_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        pront = ProntuarioHospitalar.objects.get(pk=pront_id, empresa=empresa)
    except ProntuarioHospitalar.DoesNotExist:
        return JsonResponse({"erro": "Prontuário não encontrado"}, status=404)

    if request.method == "GET":
        prescs = pront.prescricoes.all()
        return JsonResponse({"prescricoes": [_presc_to_dict(p) for p in prescs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    medicamento = (data.get("medicamento") or "").strip()
    profissional = (data.get("profissional") or "").strip()
    if not medicamento or not profissional:
        return JsonResponse({"erro": "medicamento e profissional são obrigatórios"}, status=400)

    presc = PrescricaoProntuario.objects.create(
        prontuario=pront,
        profissional=profissional,
        medicamento=medicamento,
        dose=data.get("dose", ""),
        via=data.get("via", ""),
        frequencia=data.get("frequencia", ""),
        duracao=data.get("duracao", ""),
        dispensado=bool(data.get("dispensado", False)),
    )
    return JsonResponse({"ok": True, "prescricao": _presc_to_dict(presc)}, status=201)
