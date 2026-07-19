"""
Hospital — CME (Central de Materiais e Esterilização)
  • InstrumentalCirurgico — cadastro e histórico de ciclos
  • CicloCME — registro de esterilização, controle de validade, uso em paciente
  • KPIs e alertas de vencimento
"""
import json
from datetime import timedelta

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature,
    get_setor,
    requer_setor,
    requer_feature_pacote,
    requer_operacao_page,
    requer_permissao_modulo,
)
from .views_dashboard import contexto_navegacao_setorial


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Model loader ─────────────────────────────────────────────────────────────

def _get_cme_models():
    from .models import InstrumentalCirurgico, CicloCME
    return InstrumentalCirurgico, CicloCME


# ─── Serializers ──────────────────────────────────────────────────────────────

def _instrumental_to_dict(inst):
    return {
        "id": inst.id,
        "nome": inst.nome,
        "codigo": inst.codigo,
        "tipo": inst.tipo,
        "tipo_display": inst.get_tipo_display(),
        "setor_origem": inst.setor_origem,
        "ativo": inst.ativo,
        "criado_em": inst.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _ciclo_to_dict(c):
    return {
        "id": c.id,
        "instrumental_id": c.instrumental_id,
        "instrumental_nome": c.instrumental.nome,
        "metodo": c.metodo,
        "metodo_display": c.get_metodo_display(),
        "numero_ciclo": c.numero_ciclo,
        "data_esterilizacao": c.data_esterilizacao.strftime("%d/%m/%Y %H:%M"),
        "data_esterilizacao_iso": c.data_esterilizacao.isoformat(),
        "validade_ate": c.validade_ate.isoformat(),
        "responsavel": c.responsavel,
        "lote_produto": c.lote_produto,
        "resultado": c.resultado,
        "resultado_display": c.get_resultado_display(),
        "paciente_uso": c.paciente_uso,
        "criado_em": c.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.cirurgia", "CME")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_cme_page(request):
    return render(request, "hospital_cme.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Instrumentais ───────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.cirurgia")
def api_cme_instrumentais(request):
    """GET/POST /api/hospital/cme/instrumentais"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InstrumentalCirurgico, _ = _get_cme_models()

    if request.method == "GET":
        try:
            qs = InstrumentalCirurgico.objects.filter(empresa=empresa, ativo=True)
            return JsonResponse({
                "total": qs.count(),
                "instrumentais": [_instrumental_to_dict(i) for i in qs],
            })
        except Exception as exc:
            return JsonResponse({"erro": str(exc)}, status=500)

    # POST — criar instrumental
    try:
        data = json.loads(request.body)
        inst = InstrumentalCirurgico.objects.create(
            empresa=empresa,
            nome=data["nome"],
            codigo=data.get("codigo", ""),
            tipo=data.get("tipo", "avulso"),
            setor_origem=data.get("setor_origem", ""),
        )
        return JsonResponse(_instrumental_to_dict(inst), status=201)
    except KeyError as exc:
        return JsonResponse({"erro": f"Campo obrigatório ausente: {exc}"}, status=400)
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.cirurgia")
def api_cme_instrumental_detalhe(request, pk):
    """GET /api/hospital/cme/instrumentais/<pk> — detalhe + histórico de ciclos"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InstrumentalCirurgico, CicloCME = _get_cme_models()

    try:
        inst = InstrumentalCirurgico.objects.get(pk=pk, empresa=empresa)
    except InstrumentalCirurgico.DoesNotExist:
        return JsonResponse({"erro": "Instrumental não encontrado."}, status=404)
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)

    try:
        ciclos = CicloCME.objects.filter(instrumental=inst).order_by("-data_esterilizacao")[:50]
        historico = [_ciclo_to_dict(c) for c in ciclos]
    except Exception as exc:
        historico = []

    result = _instrumental_to_dict(inst)
    result["historico_ciclos"] = historico
    return JsonResponse(result)


# ─── API: Ciclos ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.cirurgia")
def api_cme_ciclos(request):
    """GET/POST /api/hospital/cme/ciclos"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InstrumentalCirurgico, CicloCME = _get_cme_models()

    if request.method == "GET":
        try:
            qs = CicloCME.objects.filter(empresa=empresa).select_related("instrumental")

            resultado = request.GET.get("resultado")
            data_gte = request.GET.get("data_esterilizacao__gte")

            if resultado:
                qs = qs.filter(resultado=resultado)
            if data_gte:
                qs = qs.filter(data_esterilizacao__gte=data_gte)

            return JsonResponse({
                "total": qs.count(),
                "ciclos": [_ciclo_to_dict(c) for c in qs[:300]],
            })
        except Exception as exc:
            return JsonResponse({"erro": str(exc)}, status=500)

    # POST — registrar ciclo
    try:
        data = json.loads(request.body)
        try:
            instrumental = InstrumentalCirurgico.objects.get(
                pk=data["instrumental_id"], empresa=empresa
            )
        except InstrumentalCirurgico.DoesNotExist:
            return JsonResponse({"erro": "Instrumental não encontrado."}, status=404)

        ciclo = CicloCME.objects.create(
            empresa=empresa,
            instrumental=instrumental,
            metodo=data.get("metodo", "autoclave_134"),
            numero_ciclo=data["numero_ciclo"],
            data_esterilizacao=data["data_esterilizacao"],
            validade_ate=data["validade_ate"],
            responsavel=data.get("responsavel", ""),
            lote_produto=data.get("lote_produto", ""),
            resultado=data.get("resultado", "aprovado"),
        )
        return JsonResponse(_ciclo_to_dict(ciclo), status=201)
    except KeyError as exc:
        return JsonResponse({"erro": f"Campo obrigatório ausente: {exc}"}, status=400)
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.cirurgia")
def api_cme_ciclo_detalhe(request, pk):
    """GET /api/hospital/cme/ciclos/<pk>"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloCME = _get_cme_models()

    try:
        ciclo = CicloCME.objects.select_related("instrumental").get(pk=pk, empresa=empresa)
        return JsonResponse(_ciclo_to_dict(ciclo))
    except CicloCME.DoesNotExist:
        return JsonResponse({"erro": "Ciclo não encontrado."}, status=404)
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.cirurgia")
def api_cme_ciclo_uso(request, pk):
    """POST /api/hospital/cme/ciclos/<pk>/uso — registra paciente_uso no ciclo"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloCME = _get_cme_models()

    try:
        ciclo = CicloCME.objects.get(pk=pk, empresa=empresa)
    except CicloCME.DoesNotExist:
        return JsonResponse({"erro": "Ciclo não encontrado."}, status=404)
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)

    try:
        data = json.loads(request.body)
        paciente_uso = data.get("paciente_uso", "")
        if not paciente_uso:
            return JsonResponse({"erro": "Campo 'paciente_uso' é obrigatório."}, status=400)
        ciclo.paciente_uso = paciente_uso
        ciclo.save(update_fields=["paciente_uso"])
        return JsonResponse(_ciclo_to_dict(ciclo))
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


# ─── API: Vencimentos ─────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.cirurgia")
def api_cme_vencimentos(request):
    """GET /api/hospital/cme/vencimentos — vencidos ou a vencer em 7 dias"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InstrumentalCirurgico, CicloCME = _get_cme_models()

    try:
        hoje = timezone.now().date()
        limite = hoje + timedelta(days=7)

        # Último ciclo aprovado por instrumental
        ciclos_proximos = (
            CicloCME.objects.filter(
                empresa=empresa,
                resultado="aprovado",
                validade_ate__lte=limite,
            )
            .select_related("instrumental")
            .order_by("validade_ate")[:200]
        )

        alertas = []
        for c in ciclos_proximos:
            vencido = c.validade_ate < hoje
            alertas.append({
                **_ciclo_to_dict(c),
                "vencido": vencido,
                "dias_para_vencer": (c.validade_ate - hoje).days,
            })

        return JsonResponse({"total": len(alertas), "alertas": alertas})
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


# ─── API: KPIs ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.cirurgia")
def api_cme_kpis(request):
    """GET /api/hospital/cme/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    InstrumentalCirurgico, CicloCME = _get_cme_models()

    try:
        agora = timezone.now()
        inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_instrumentais = InstrumentalCirurgico.objects.filter(
            empresa=empresa, ativo=True
        ).count()

        ciclos_mes_qs = CicloCME.objects.filter(
            empresa=empresa,
            data_esterilizacao__gte=inicio_mes,
        )
        ciclos_mes = ciclos_mes_qs.count()
        reprovados_mes = ciclos_mes_qs.filter(resultado="reprovado").count()

        pct_aprovados = 0.0
        if ciclos_mes > 0:
            aprovados = ciclos_mes - reprovados_mes
            pct_aprovados = round(aprovados / ciclos_mes * 100, 1)

        return JsonResponse({
            "total_instrumentais": total_instrumentais,
            "ciclos_mes": ciclos_mes,
            "reprovados_mes": reprovados_mes,
            "pct_aprovados": pct_aprovados,
        })
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)
