"""
Hospital — LIS (Laboratory Information System)
  • ExameLIS — solicitação, coleta, análise, resultado, entrega
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
from .models import ExameLIS
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

def _exame_to_dict(e):
    return {
        "id": e.id,
        "paciente_nome": e.paciente_nome,
        "prontuario_id": e.prontuario_id,
        "tipo_exame": e.tipo_exame,
        "codigo_tuss": e.codigo_tuss,
        "solicitante": e.solicitante,
        "status": e.status,
        "resultado": e.resultado,
        "valores_referencia": e.valores_referencia,
        "solicitado_em": e.solicitado_em.strftime("%d/%m/%Y %H:%M"),
        "resultado_em": e.resultado_em.strftime("%d/%m/%Y %H:%M") if e.resultado_em else None,
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
def hospital_lis_page(request):
    return render(request, "hospital_lis.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Lista exames ────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_lis_exames(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = ExameLIS.objects.filter(empresa=empresa)

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(paciente_nome__icontains=q) |
            Q(tipo_exame__icontains=q) |
            Q(solicitante__icontains=q)
        )

    data_de = request.GET.get("data_de")
    data_ate = request.GET.get("data_ate")
    if data_de:
        qs = qs.filter(solicitado_em__date__gte=data_de)
    if data_ate:
        qs = qs.filter(solicitado_em__date__lte=data_ate)

    qs = qs.order_by("-solicitado_em")[:100]
    return JsonResponse({"exames": [_exame_to_dict(e) for e in qs]})


# ─── API: Solicitar exame ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_lis_solicitar(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    tipo_exame = (data.get("tipo_exame") or "").strip()
    solicitante = (data.get("solicitante") or "").strip()

    if not paciente_nome or not tipo_exame or not solicitante:
        return JsonResponse({"erro": "paciente_nome, tipo_exame e solicitante são obrigatórios"}, status=400)

    prontuario_id = data.get("prontuario_id")
    prontuario = None
    if prontuario_id:
        from .models import ProntuarioHospitalar
        try:
            prontuario = ProntuarioHospitalar.objects.get(pk=prontuario_id, empresa=empresa)
        except ProntuarioHospitalar.DoesNotExist:
            pass

    exame = ExameLIS.objects.create(
        empresa=empresa,
        prontuario=prontuario,
        paciente_nome=paciente_nome,
        tipo_exame=tipo_exame,
        codigo_tuss=data.get("codigo_tuss", ""),
        solicitante=solicitante,
        status="solicitado",
        valores_referencia=data.get("valores_referencia", ""),
    )
    return JsonResponse({"ok": True, "exame": _exame_to_dict(exame)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_lis(request):
    if request.method == "POST":
        return api_lis_solicitar(request)
    return api_lis_exames(request)


# ─── API: Registrar resultado ─────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_lis_resultado(request, exame_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        exame = ExameLIS.objects.get(pk=exame_id, empresa=empresa)
    except ExameLIS.DoesNotExist:
        return JsonResponse({"erro": "Exame não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    status_validos = [s[0] for s in ExameLIS.STATUS_CHOICES]
    novo_status = data.get("status", exame.status)
    if novo_status not in status_validos:
        return JsonResponse({"erro": f"status inválido. Opções: {status_validos}"}, status=400)

    exame.status = novo_status
    if "resultado" in data:
        exame.resultado = data["resultado"]
    if "valores_referencia" in data:
        exame.valores_referencia = data["valores_referencia"]

    if novo_status in ("resultado", "entregue") and not exame.resultado_em:
        exame.resultado_em = timezone.now()

    exame.save()
    return JsonResponse({"ok": True, "exame": _exame_to_dict(exame)})


# ─── API: KPIs ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_lis_kpis(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = timezone.now().date()
    mes_inicio = hoje.replace(day=1)

    qs = ExameLIS.objects.filter(empresa=empresa)

    solicitados_hoje = qs.filter(solicitado_em__date=hoje).count()
    aguardando_resultado = qs.filter(status__in=["solicitado", "coletado", "em_analise"]).count()
    entregues_mes = qs.filter(status="entregue", resultado_em__date__gte=mes_inicio).count()

    por_status = list(
        qs.values("status").annotate(n=Count("id")).order_by("status")
    )

    return JsonResponse({
        "solicitados_hoje": solicitados_hoje,
        "aguardando_resultado": aguardando_resultado,
        "entregues_mes": entregues_mes,
        "por_status": por_status,
    })
