"""
Comissão de Ética Médica (CEM) — Resolução CFM nº 2.147/2016.
Cadastro de membros e tramitação de denúncias/consultas éticas/sindicâncias
envolvendo médicos do hospital, com emissão de parecer.

GET/POST  /api/hospital/comissao-etica/membros
GET/PATCH /api/hospital/comissao-etica/membros/<id>
GET/POST  /api/hospital/comissao-etica/casos
GET/PATCH /api/hospital/comissao-etica/casos/<id>
GET       /api/hospital/comissao-etica/kpis
"""
import json
import logging
from datetime import date

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, requer_setor, requer_feature_pacote, requer_operacao_page,
    requer_permissao_modulo, api_requer_feature,
)
from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.comissao_etica", "Comissão de Ética Médica")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_comissao_etica_page(request):
    return render(request, "hospital_comissao_etica.html")


# ── Membros ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.comissao_etica")
def api_comissao_etica_membros(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    from .models import MembroComissaoEtica

    if request.method == "GET":
        qs = MembroComissaoEtica.objects.filter(empresa=emp)
        if request.GET.get("ativo") != "todos":
            qs = qs.filter(ativo=True)
        return JsonResponse({
            "total": qs.count(),
            "membros": [
                {
                    "id": m.id, "nome": m.nome, "crm": m.crm,
                    "cargo": m.cargo, "cargo_display": m.get_cargo_display(),
                    "mandato_inicio": m.mandato_inicio.isoformat(),
                    "mandato_fim": m.mandato_fim.isoformat(),
                    "mandato_vencido": m.mandato_fim < date.today(),
                    "ativo": m.ativo,
                }
                for m in qs.order_by("cargo", "nome")
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not data.get("nome") or not data.get("crm") or not data.get("mandato_inicio") or not data.get("mandato_fim"):
        return JsonResponse({"erro": "Nome, CRM, início e fim do mandato são obrigatórios"}, status=400)

    m = MembroComissaoEtica.objects.create(
        empresa=emp,
        nome=data["nome"],
        crm=data["crm"],
        cargo=data.get("cargo", "membro"),
        mandato_inicio=data["mandato_inicio"],
        mandato_fim=data["mandato_fim"],
    )
    return JsonResponse({"id": m.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.comissao_etica")
def api_comissao_etica_membro_detalhe(request, m_id):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    from .models import MembroComissaoEtica
    try:
        m = MembroComissaoEtica.objects.get(id=m_id, empresa=emp)
    except MembroComissaoEtica.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": m.id, "nome": m.nome, "crm": m.crm, "cargo": m.cargo,
            "mandato_inicio": m.mandato_inicio.isoformat(), "mandato_fim": m.mandato_fim.isoformat(),
            "ativo": m.ativo,
        })

    data = json.loads(request.body)
    for campo in ("nome", "crm", "cargo", "ativo", "mandato_fim"):
        if campo in data:
            setattr(m, campo, data[campo])
    m.save()
    return JsonResponse({"ok": True})


# ── Casos éticos ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.comissao_etica")
def api_comissao_etica_casos(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    from .models import CasoEticoMedico

    if request.method == "GET":
        qs = CasoEticoMedico.objects.filter(empresa=emp)
        status_f = request.GET.get("status")
        tipo_f = request.GET.get("tipo")
        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        return JsonResponse({
            "total": qs.count(),
            "casos": [
                {
                    "id": c.id, "protocolo": c.protocolo,
                    "tipo": c.tipo, "tipo_display": c.get_tipo_display(),
                    "descricao": c.descricao[:200],
                    "medico_envolvido_nome": "(sigiloso)" if c.sigiloso else (c.medico_envolvido_nome or "—"),
                    "sigiloso": c.sigiloso,
                    "status": c.status, "status_display": c.get_status_display(),
                    "relator": c.relator,
                    "data_abertura": c.data_abertura.isoformat(),
                    "data_parecer": c.data_parecer.isoformat() if c.data_parecer else None,
                }
                for c in qs.order_by("-data_abertura")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if data.get("tipo") not in dict(CasoEticoMedico.TIPO):
        return JsonResponse({"erro": "Tipo de caso inválido"}, status=400)
    if not data.get("descricao"):
        return JsonResponse({"erro": "Descrição é obrigatória"}, status=400)

    total = CasoEticoMedico.objects.filter(empresa=emp).count() + 1
    protocolo = f"CEM-{emp.id:06d}-{total:06d}"

    c = CasoEticoMedico.objects.create(
        empresa=emp,
        protocolo=protocolo,
        tipo=data["tipo"],
        descricao=data["descricao"],
        medico_envolvido_nome=data.get("medico_envolvido_nome", ""),
        medico_envolvido_crm=data.get("medico_envolvido_crm", ""),
        sigiloso=data.get("sigiloso", True),
        status="aberto",
    )
    return JsonResponse({"id": c.id, "protocolo": protocolo}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.comissao_etica")
def api_comissao_etica_caso_detalhe(request, c_id):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    from .models import CasoEticoMedico
    try:
        c = CasoEticoMedico.objects.get(id=c_id, empresa=emp)
    except CasoEticoMedico.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": c.id, "protocolo": c.protocolo, "tipo": c.tipo, "tipo_display": c.get_tipo_display(),
            "descricao": c.descricao, "medico_envolvido_nome": c.medico_envolvido_nome,
            "medico_envolvido_crm": c.medico_envolvido_crm, "sigiloso": c.sigiloso,
            "status": c.status, "status_display": c.get_status_display(),
            "relator": c.relator, "parecer_texto": c.parecer_texto,
            "data_abertura": c.data_abertura.isoformat(),
            "data_parecer": c.data_parecer.isoformat() if c.data_parecer else None,
        })

    data = json.loads(request.body)
    if "parecer_texto" in data:
        c.parecer_texto = data["parecer_texto"]
        c.relator = data.get("relator", c.relator)
        c.data_parecer = timezone.now()
        c.status = "parecer_emitido"
    if "status" in data and data["status"] in dict(CasoEticoMedico.STATUS):
        c.status = data["status"]
    if "relator" in data and "parecer_texto" not in data:
        c.relator = data["relator"]
    c.save()
    return JsonResponse({"ok": True, "status": c.status})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.comissao_etica")
def api_comissao_etica_kpis(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Acesso negado. Segmento hospital requerido."}, status=403)

    from .models import CasoEticoMedico, MembroComissaoEtica

    qs = CasoEticoMedico.objects.filter(empresa=emp)
    por_status = dict(qs.values_list("status").annotate(n=Count("id")).order_by())
    por_tipo = dict(qs.values_list("tipo").annotate(n=Count("id")).order_by())

    return JsonResponse({
        "total_casos": qs.count(),
        "por_status": por_status,
        "por_tipo": por_tipo,
        "abertos": por_status.get("aberto", 0) + por_status.get("em_analise", 0),
        "membros_ativos": MembroComissaoEtica.objects.filter(empresa=emp, ativo=True).count(),
    })
