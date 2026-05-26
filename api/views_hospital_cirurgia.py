"""
Hospital — Bloco Cirúrgico
  • BlocoCirurgico — agendamento, situação, relatório cirúrgico, KPIs
"""
import json
from datetime import timedelta

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
from .models import BlocoCirurgico
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

def _cir_to_dict(c):
    return {
        "id": c.id,
        "paciente_nome": c.paciente_nome,
        "prontuario_id": c.prontuario_id,
        "tipo_cirurgia": c.tipo_cirurgia,
        "cid10": c.cid10,
        "cbhpm": c.cbhpm,
        "cirurgiao": c.cirurgiao,
        "anestesista": c.anestesista,
        "sala": c.sala,
        "data_hora": c.data_hora.strftime("%d/%m/%Y %H:%M"),
        "data_hora_iso": c.data_hora.isoformat(),
        "duracao_prevista_min": c.duracao_prevista_min,
        "situacao": c.situacao,
        "relatorio_cirurgico": c.relatorio_cirurgico,
        "criado_em": c.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
def hospital_cirurgia_page(request):
    return render(request, "hospital_cirurgia.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Agenda (hoje + 7 dias) ──────────────────────────────────────────────

@require_http_methods(["GET"])
def api_cirurgia_agenda(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = timezone.now().date()
    ate = hoje + timedelta(days=7)
    cirurgias = BlocoCirurgico.objects.filter(
        empresa=empresa,
        data_hora__date__gte=hoje,
        data_hora__date__lte=ate,
    ).select_related("prontuario").order_by("data_hora")

    return JsonResponse({"agenda": [_cir_to_dict(c) for c in cirurgias]})


# ─── API: Lista (todos, com filtros) ──────────────────────────────────────────

@require_http_methods(["GET"])
def api_cirurgia_lista(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = BlocoCirurgico.objects.filter(empresa=empresa)

    situacao = request.GET.get("situacao")
    if situacao:
        qs = qs.filter(situacao=situacao)

    data_de = request.GET.get("data_de")
    data_ate = request.GET.get("data_ate")
    if data_de:
        qs = qs.filter(data_hora__date__gte=data_de)
    if data_ate:
        qs = qs.filter(data_hora__date__lte=data_ate)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(paciente_nome__icontains=q) | Q(tipo_cirurgia__icontains=q) | Q(cirurgiao__icontains=q))

    qs = qs.order_by("-data_hora")[:100]
    return JsonResponse({"cirurgias": [_cir_to_dict(c) for c in qs]})


# ─── API: Nova cirurgia ───────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_cirurgia_nova(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    tipo_cirurgia = (data.get("tipo_cirurgia") or "").strip()
    cirurgiao = (data.get("cirurgiao") or "").strip()
    data_hora_str = (data.get("data_hora") or "").strip()

    if not paciente_nome or not tipo_cirurgia or not cirurgiao or not data_hora_str:
        return JsonResponse({"erro": "paciente_nome, tipo_cirurgia, cirurgiao e data_hora são obrigatórios"}, status=400)

    from datetime import datetime
    try:
        data_hora = datetime.fromisoformat(data_hora_str)
        if timezone.is_naive(data_hora):
            data_hora = timezone.make_aware(data_hora)
    except ValueError:
        return JsonResponse({"erro": "data_hora inválida (use ISO 8601)"}, status=400)

    prontuario_id = data.get("prontuario_id")
    prontuario = None
    if prontuario_id:
        from .models import ProntuarioHospitalar
        try:
            prontuario = ProntuarioHospitalar.objects.get(pk=prontuario_id, empresa=empresa)
        except ProntuarioHospitalar.DoesNotExist:
            pass

    cir = BlocoCirurgico.objects.create(
        empresa=empresa,
        prontuario=prontuario,
        paciente_nome=paciente_nome,
        tipo_cirurgia=tipo_cirurgia,
        cid10=data.get("cid10", ""),
        cbhpm=data.get("cbhpm", ""),
        cirurgiao=cirurgiao,
        anestesista=data.get("anestesista", ""),
        sala=data.get("sala", ""),
        data_hora=data_hora,
        duracao_prevista_min=int(data.get("duracao_prevista_min", 60)),
        situacao="agendada",
    )
    return JsonResponse({"ok": True, "cirurgia": _cir_to_dict(cir)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_cirurgia(request):
    if request.method == "POST":
        return api_cirurgia_nova(request)
    return api_cirurgia_lista(request)


# ─── API: Atualizar situação / relatório ──────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_cirurgia_atualizar(request, cir_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        cir = BlocoCirurgico.objects.get(pk=cir_id, empresa=empresa)
    except BlocoCirurgico.DoesNotExist:
        return JsonResponse({"erro": "Cirurgia não encontrada"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    situacoes_validas = [s[0] for s in BlocoCirurgico.SITUACAO_CHOICES]
    if "situacao" in data:
        if data["situacao"] not in situacoes_validas:
            return JsonResponse({"erro": f"situacao inválida. Opções: {situacoes_validas}"}, status=400)
        cir.situacao = data["situacao"]

    if "relatorio_cirurgico" in data:
        cir.relatorio_cirurgico = data["relatorio_cirurgico"]

    for field in ("cirurgiao", "anestesista", "sala", "cbhpm", "cid10"):
        if field in data:
            setattr(cir, field, data[field])

    cir.save()
    return JsonResponse({"ok": True, "cirurgia": _cir_to_dict(cir)})


# ─── API: KPIs ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_cirurgia_kpis(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = timezone.now().date()
    mes_inicio = hoje.replace(day=1)

    agendadas_hoje = BlocoCirurgico.objects.filter(
        empresa=empresa, situacao="agendada", data_hora__date=hoje
    ).count()

    em_andamento = BlocoCirurgico.objects.filter(
        empresa=empresa, situacao="em_andamento"
    ).count()

    concluidas_mes = BlocoCirurgico.objects.filter(
        empresa=empresa, situacao="concluida", data_hora__date__gte=mes_inicio
    ).count()

    canceladas_mes = BlocoCirurgico.objects.filter(
        empresa=empresa, situacao__in=["cancelada", "suspensa"], data_hora__date__gte=mes_inicio
    ).count()

    total_mes = BlocoCirurgico.objects.filter(
        empresa=empresa, data_hora__date__gte=mes_inicio
    ).count()

    salas = list(
        BlocoCirurgico.objects.filter(empresa=empresa, situacao__in=["agendada", "em_andamento"])
        .values("sala")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    return JsonResponse({
        "agendadas_hoje": agendadas_hoje,
        "em_andamento": em_andamento,
        "concluidas_mes": concluidas_mes,
        "canceladas_mes": canceladas_mes,
        "total_mes": total_mes,
        "salas_ativas": salas,
    })
