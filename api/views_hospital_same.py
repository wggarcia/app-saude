"""
Hospital — SAME (Serviço de Arquivo Médico e Estatístico)

Endpoints:
  GET  /api/hospital/same/pacientes          — busca por nome/prontuário (q=)
  POST /api/hospital/same/pacientes          — cria novo código SAME
  GET  /api/hospital/same/pacientes/<pk>     — detalhe + histórico de empréstimos
  POST /api/hospital/same/emprestimos        — registra empréstimo
  POST /api/hospital/same/emprestimos/<pk>/devolver — marca devolução
  GET  /api/hospital/same/emprestimos        — lista empréstimos em aberto
  GET  /api/hospital/same/kpis               — totais do painel

Página:
  hospital_same_page — renderiza hospital_same.html
"""
import json

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature,
    get_setor,
    requer_feature_pacote,
    requer_operacao_page,
    requer_permissao_modulo,
    requer_setor,
)

try:
    from .models import CodigoSAME, EmprestimoSAME
except ImportError:
    CodigoSAME = None
    EmprestimoSAME = None


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Serializers ──────────────────────────────────────────────────────────────

def _same_to_dict(obj):
    return {
        "id": obj.id,
        "prontuario": obj.prontuario,
        "paciente": obj.paciente,
        "data_nascimento": obj.data_nascimento.strftime("%Y-%m-%d") if obj.data_nascimento else None,
        "sexo": obj.sexo,
        "data_abertura": obj.data_abertura.strftime("%Y-%m-%d") if obj.data_abertura else None,
        "ativo": obj.ativo,
        "observacoes": obj.observacoes,
        "criado_em": obj.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _emprestimo_to_dict(obj):
    return {
        "id": obj.id,
        "codigo_same_id": obj.codigo_same_id,
        "prontuario": obj.codigo_same.prontuario,
        "paciente": obj.codigo_same.paciente,
        "solicitante": obj.solicitante,
        "setor": obj.setor,
        "data_saida": obj.data_saida.strftime("%d/%m/%Y %H:%M"),
        "data_prevista_devolucao": obj.data_prevista_devolucao.strftime("%Y-%m-%d"),
        "data_devolucao": obj.data_devolucao.strftime("%d/%m/%Y %H:%M") if obj.data_devolucao else None,
        "status": obj.status,
        "observacoes": obj.observacoes,
        "criado_em": obj.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Pacientes (CodigoSAME) ───────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.administrativo", "SAME")
def api_same_pacientes(request):
    """
    GET  — lista/busca pacientes pelo código SAME.
    POST — cria novo código SAME.
    """
    if CodigoSAME is None:
        return JsonResponse({"erro": "Módulo SAME não disponível."}, status=503)

    empresa = _hosp(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado ou setor inválido."}, status=401)

    if request.method == "GET":
        q = request.GET.get("q", "").strip()
        qs = CodigoSAME.objects.filter(empresa=empresa, ativo=True)
        if q:
            qs = qs.filter(
                Q(prontuario__icontains=q) | Q(paciente__icontains=q)
            )
        qs = qs.order_by("prontuario")[:100]
        return JsonResponse({"resultados": [_same_to_dict(o) for o in qs]})

    # POST — criar novo código SAME
    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    prontuario = (dados.get("prontuario") or "").strip()
    nome_paciente = (dados.get("nome_paciente") or "").strip()
    data_nascimento = dados.get("data_nascimento") or None
    sexo = (dados.get("sexo") or "I").strip().upper()

    if not prontuario or not nome_paciente:
        return JsonResponse({"erro": "prontuario e nome_paciente são obrigatórios."}, status=400)

    if CodigoSAME.objects.filter(empresa=empresa, prontuario=prontuario).exists():
        return JsonResponse({"erro": "Já existe um código SAME com este prontuário."}, status=409)

    obj = CodigoSAME.objects.create(
        empresa=empresa,
        prontuario=prontuario,
        paciente=nome_paciente,
        data_nascimento=data_nascimento,
        sexo=sexo if sexo in ("M", "F", "I") else "I",
    )
    return JsonResponse({"codigo_same": _same_to_dict(obj)}, status=201)


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.administrativo", "SAME")
def api_same_paciente_detalhe(request, pk):
    """
    GET /api/hospital/same/pacientes/<pk>
    Retorna detalhe do código SAME e histórico completo de empréstimos.
    """
    if CodigoSAME is None or EmprestimoSAME is None:
        return JsonResponse({"erro": "Módulo SAME não disponível."}, status=503)

    empresa = _hosp(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado ou setor inválido."}, status=401)

    try:
        obj = CodigoSAME.objects.get(pk=pk, empresa=empresa)
    except CodigoSAME.DoesNotExist:
        return JsonResponse({"erro": "Código SAME não encontrado."}, status=404)

    historico = obj.emprestimos.all().order_by("-data_saida")
    return JsonResponse({
        "codigo_same": _same_to_dict(obj),
        "historico_emprestimos": [_emprestimo_to_dict(e) for e in historico],
    })


# ─── Empréstimos ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.administrativo", "SAME")
def api_same_emprestimos(request):
    """
    GET  — lista empréstimos em aberto (status=emprestado).
    POST — registra novo empréstimo.
    """
    if EmprestimoSAME is None or CodigoSAME is None:
        return JsonResponse({"erro": "Módulo SAME não disponível."}, status=503)

    empresa = _hosp(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado ou setor inválido."}, status=401)

    if request.method == "GET":
        qs = EmprestimoSAME.objects.filter(
            empresa=empresa, status="emprestado"
        ).select_related("codigo_same").order_by("data_prevista_devolucao")
        return JsonResponse({"emprestimos": [_emprestimo_to_dict(e) for e in qs]})

    # POST — registrar empréstimo
    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    codigo_same_id = dados.get("codigo_same_id")
    solicitante = (dados.get("solicitante") or "").strip()
    setor = (dados.get("setor") or "").strip()
    data_prevista_devolucao = dados.get("data_prevista_devolucao")

    if not codigo_same_id or not solicitante or not setor or not data_prevista_devolucao:
        return JsonResponse(
            {"erro": "codigo_same_id, solicitante, setor e data_prevista_devolucao são obrigatórios."},
            status=400,
        )

    try:
        codigo_same = CodigoSAME.objects.get(pk=codigo_same_id, empresa=empresa)
    except CodigoSAME.DoesNotExist:
        return JsonResponse({"erro": "Código SAME não encontrado."}, status=404)

    # Bloqueia novo empréstimo se o prontuário já estiver emprestado
    if EmprestimoSAME.objects.filter(codigo_same=codigo_same, status="emprestado").exists():
        return JsonResponse({"erro": "Este prontuário já está emprestado."}, status=409)

    emprestimo = EmprestimoSAME.objects.create(
        empresa=empresa,
        codigo_same=codigo_same,
        solicitante=solicitante,
        setor=setor,
        data_prevista_devolucao=data_prevista_devolucao,
        observacoes=dados.get("observacoes", ""),
    )
    return JsonResponse({"emprestimo": _emprestimo_to_dict(emprestimo)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.administrativo", "SAME")
def api_same_emprestimo_devolver(request, pk):
    """
    POST /api/hospital/same/emprestimos/<pk>/devolver
    Marca a devolução do prontuário com a data/hora atual.
    """
    if EmprestimoSAME is None:
        return JsonResponse({"erro": "Módulo SAME não disponível."}, status=503)

    empresa = _hosp(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado ou setor inválido."}, status=401)

    try:
        emprestimo = EmprestimoSAME.objects.get(pk=pk, empresa=empresa)
    except EmprestimoSAME.DoesNotExist:
        return JsonResponse({"erro": "Empréstimo não encontrado."}, status=404)

    if emprestimo.status != "emprestado":
        return JsonResponse(
            {"erro": f"Empréstimo já encerrado com status '{emprestimo.status}'."},
            status=409,
        )

    emprestimo.status = "devolvido"
    emprestimo.data_devolucao = timezone.now()
    emprestimo.save(update_fields=["status", "data_devolucao"])

    return JsonResponse({"emprestimo": _emprestimo_to_dict(emprestimo)})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.administrativo", "SAME")
def api_same_kpis(request):
    """
    GET /api/hospital/same/kpis
    Retorna totais consolidados do SAME.
    """
    if CodigoSAME is None or EmprestimoSAME is None:
        return JsonResponse({"erro": "Módulo SAME não disponível."}, status=503)

    empresa = _hosp(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado ou setor inválido."}, status=401)

    hoje = timezone.localdate()

    total_prontuarios = CodigoSAME.objects.filter(empresa=empresa, ativo=True).count()
    emprestados = EmprestimoSAME.objects.filter(empresa=empresa, status="emprestado").count()
    vencidos = EmprestimoSAME.objects.filter(
        empresa=empresa,
        status="emprestado",
        data_prevista_devolucao__lt=hoje,
    ).count()
    extraviados = EmprestimoSAME.objects.filter(empresa=empresa, status="extraviado").count()

    return JsonResponse({
        "total_prontuarios": total_prontuarios,
        "emprestados": emprestados,
        "vencidos": vencidos,
        "extraviados": extraviados,
    })


# ─── Página HTML ──────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.administrativo", "SAME")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_same_page(request):
    """Renderiza a interface do SAME hospitalar."""
    return render(request, "hospital_same.html")
