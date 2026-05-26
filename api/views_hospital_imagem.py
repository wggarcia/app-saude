"""
Hospital — RIS/PACS (Radiology Information System)
  • ExameRIS — modalidade, laudo, link PACS, workflow de status
"""
import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_gerencia,
    get_setor,
    principal_pode_operacao_setorial,
    requer_setor,
    requer_operacao_page,
)
from .models import ExameRIS
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


# ─── Serializer ───────────────────────────────────────────────────────────────

def _ris_to_dict(e):
    return {
        "id": e.id,
        "paciente_nome": e.paciente_nome,
        "prontuario_id": e.prontuario_id,
        "modalidade": e.modalidade,
        "modalidade_label": dict(ExameRIS.MODALIDADES).get(e.modalidade, e.modalidade),
        "regiao_anatomica": e.regiao_anatomica,
        "solicitante": e.solicitante,
        "laudo": e.laudo,
        "imagem_url": e.imagem_url,
        "laudado": bool(e.laudo),
        "laudado_em": e.laudado_em.strftime("%d/%m/%Y %H:%M") if e.laudado_em else None,
        "solicitado_em": e.solicitado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
def hospital_imagem_page(request):
    return render(request, "hospital_imagem.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Lista exames RIS ────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_ris_exames(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = ExameRIS.objects.filter(empresa=empresa)

    modalidade = request.GET.get("modalidade")
    if modalidade:
        qs = qs.filter(modalidade=modalidade)

    laudado = request.GET.get("laudado")
    if laudado == "1":
        qs = qs.exclude(laudo="")
    elif laudado == "0":
        qs = qs.filter(laudo="")

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(paciente_nome__icontains=q) |
            Q(regiao_anatomica__icontains=q) |
            Q(solicitante__icontains=q)
        )

    data_de = request.GET.get("data_de")
    data_ate = request.GET.get("data_ate")
    if data_de:
        qs = qs.filter(solicitado_em__date__gte=data_de)
    if data_ate:
        qs = qs.filter(solicitado_em__date__lte=data_ate)

    qs = qs.order_by("-solicitado_em")[:100]
    return JsonResponse({"exames": [_ris_to_dict(e) for e in qs]})


# ─── API: Solicitar exame RIS ─────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_ris_solicitar(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    regiao_anatomica = (data.get("regiao_anatomica") or "").strip()
    solicitante = (data.get("solicitante") or "").strip()

    if not paciente_nome or not regiao_anatomica or not solicitante:
        return JsonResponse({"erro": "paciente_nome, regiao_anatomica e solicitante são obrigatórios"}, status=400)

    modalidades_validas = [m[0] for m in ExameRIS.MODALIDADES]
    modalidade = data.get("modalidade", "rx")
    if modalidade not in modalidades_validas:
        return JsonResponse({"erro": f"modalidade inválida. Opções: {modalidades_validas}"}, status=400)

    prontuario_id = data.get("prontuario_id")
    prontuario = None
    if prontuario_id:
        from .models import ProntuarioHospitalar
        try:
            prontuario = ProntuarioHospitalar.objects.get(pk=prontuario_id, empresa=empresa)
        except ProntuarioHospitalar.DoesNotExist:
            pass

    exame = ExameRIS.objects.create(
        empresa=empresa,
        prontuario=prontuario,
        paciente_nome=paciente_nome,
        modalidade=modalidade,
        regiao_anatomica=regiao_anatomica,
        solicitante=solicitante,
    )
    return JsonResponse({"ok": True, "exame": _ris_to_dict(exame)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ris(request):
    if request.method == "POST":
        return api_ris_solicitar(request)
    return api_ris_exames(request)


# ─── API: Laudar exame ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_ris_laudar(request, exame_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        exame = ExameRIS.objects.get(pk=exame_id, empresa=empresa)
    except ExameRIS.DoesNotExist:
        return JsonResponse({"erro": "Exame não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    laudo = (data.get("laudo") or "").strip()
    if not laudo:
        return JsonResponse({"erro": "laudo é obrigatório"}, status=400)

    exame.laudo = laudo
    if "imagem_url" in data:
        exame.imagem_url = data["imagem_url"]
    if not exame.laudado_em:
        exame.laudado_em = timezone.now()

    exame.save()
    return JsonResponse({"ok": True, "exame": _ris_to_dict(exame)})


# ─── API: KPIs por modalidade ─────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_ris_kpis(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = timezone.now().date()
    qs = ExameRIS.objects.filter(empresa=empresa)

    por_modalidade = list(
        qs.values("modalidade").annotate(n=Count("id")).order_by("-n")
    )
    # Add human-readable label
    modal_map = dict(ExameRIS.MODALIDADES)
    for row in por_modalidade:
        row["label"] = modal_map.get(row["modalidade"], row["modalidade"])

    solicitados_hoje = qs.filter(solicitado_em__date=hoje).count()
    pendentes_laudo = qs.filter(laudo="").count()
    laudados_hoje = qs.filter(laudado_em__date=hoje).count()
    total = qs.count()

    return JsonResponse({
        "total": total,
        "solicitados_hoje": solicitados_hoje,
        "pendentes_laudo": pendentes_laudo,
        "laudados_hoje": laudados_hoje,
        "por_modalidade": por_modalidade,
    })
