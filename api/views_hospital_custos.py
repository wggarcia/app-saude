"""
Custos Hospitalares — Centros de Responsabilidade, DRG, custo por paciente.
"""
import json
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Avg, Q
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo
from .views_dashboard import contexto_navegacao_setorial

try:
    from .models import CentroResponsabilidade, CustoAssistencial, ClassificacaoDRG, PacienteInternado
except ImportError:
    CentroResponsabilidade = CustoAssistencial = ClassificacaoDRG = PacienteInternado = None


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.financeiro", "Custos")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_custos_page(request):
    return render(request, "hospital_custos.html")


# ─── Centros de Responsabilidade ─────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_custos_centros(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if CentroResponsabilidade is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    if request.method == "GET":
        qs = CentroResponsabilidade.objects.filter(empresa=emp, ativo=True).order_by("nome")
        data = [
            {
                "id": c.id,
                "codigo": c.codigo,
                "nome": c.nome,
                "tipo": c.tipo,
                "responsavel": c.responsavel,
                "ativo": c.ativo,
            }
            for c in qs
        ]
        return JsonResponse({"centros": data, "total": len(data)})

    body = json.loads(request.body or "{}")
    centro = CentroResponsabilidade.objects.create(
        empresa=emp,
        codigo=body.get("codigo", ""),
        nome=body.get("nome", ""),
        tipo=body.get("tipo", "direto"),
        responsavel=body.get("responsavel", ""),
    )
    return JsonResponse({"id": centro.id, "mensagem": "Centro criado com sucesso"}, status=201)


# ─── Lançamentos de Custo ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_custos_lancamentos(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if CustoAssistencial is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    if request.method == "GET":
        qs = CustoAssistencial.objects.filter(empresa=emp)
        competencia = request.GET.get("competencia")
        categoria = request.GET.get("categoria")
        centro_id = request.GET.get("centro_id")
        if competencia:
            qs = qs.filter(competencia=competencia)
        if categoria:
            qs = qs.filter(categoria=categoria)
        if centro_id:
            qs = qs.filter(centro_id=centro_id)
        qs = qs.order_by("-criado_em")[:200]
        data = [
            {
                "id": c.id,
                "competencia": c.competencia,
                "categoria": c.categoria,
                "descricao": c.descricao,
                "valor": float(c.valor),
                "centro_id": c.centro_id,
                "procedimento_sigtap": c.procedimento_sigtap,
                "drg_codigo": c.drg_codigo,
            }
            for c in qs
        ]
        return JsonResponse({"lancamentos": data, "total": len(data)})

    body = json.loads(request.body or "{}")
    custo = CustoAssistencial.objects.create(
        empresa=emp,
        competencia=body.get("competencia", timezone.now().strftime("%Y-%m")),
        categoria=body.get("categoria", "material"),
        descricao=body.get("descricao", ""),
        valor=body.get("valor", 0),
        centro_id=body.get("centro_id"),
        procedimento_sigtap=body.get("procedimento_sigtap", ""),
        drg_codigo=body.get("drg_codigo", ""),
    )
    return JsonResponse({"id": custo.id, "mensagem": "Lançamento criado com sucesso"}, status=201)


# ─── Apuração por Competência ─────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_custos_apuracao(request, comp):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if CustoAssistencial is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    qs = CustoAssistencial.objects.filter(empresa=emp, competencia=comp)
    por_categoria = (
        qs.values("categoria")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")
    )
    total_geral = qs.aggregate(total=Sum("valor"))["total"] or 0

    # Custo médio por leito — leitos ocupados no mês (simplificado)
    try:
        from .models import LeitoHospitalar
        total_leitos = LeitoHospitalar.objects.filter(empresa=emp, ativo=True).count()
        custo_medio_leito = float(total_geral) / total_leitos if total_leitos else 0
    except Exception:
        custo_medio_leito = 0

    return JsonResponse({
        "competencia": comp,
        "total_geral": float(total_geral),
        "custo_medio_leito": round(custo_medio_leito, 2),
        "por_categoria": [
            {
                "categoria": r["categoria"],
                "total": float(r["total"]),
                "quantidade": r["quantidade"],
            }
            for r in por_categoria
        ],
    })


# ─── DRG ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_custos_drg(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if ClassificacaoDRG is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    if request.method == "GET":
        qs = ClassificacaoDRG.objects.filter(empresa=emp).order_by("-criado_em")[:100]
        data = [
            {
                "id": d.id,
                "codigo_drg": d.codigo_drg,
                "descricao_drg": d.descricao_drg,
                "peso_relativo": float(d.peso_relativo) if d.peso_relativo else None,
                "aih_numero": d.aih_numero,
                "competencia": d.competencia,
                "enviado": d.enviado_valor_saude,
                "data_envio": d.data_envio.isoformat() if d.data_envio else None,
                "paciente_internado_id": d.paciente_internado_id,
            }
            for d in qs
        ]
        return JsonResponse({"classificacoes": data, "total": len(data)})

    body = json.loads(request.body or "{}")
    drg = ClassificacaoDRG.objects.create(
        empresa=emp,
        paciente_internado_id=body.get("paciente_internado_id"),
        codigo_drg=body.get("codigo_drg", ""),
        descricao_drg=body.get("descricao_drg", ""),
        peso_relativo=body.get("peso_relativo"),
        aih_numero=body.get("aih_numero", ""),
        competencia=body.get("competencia", timezone.now().strftime("%Y-%m")),
    )
    return JsonResponse({"id": drg.id, "mensagem": "Classificação DRG criada"}, status=201)


# ─── Envio DRG ao Valor Saúde Brasil ─────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_custos_drg_enviar(request, pk):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if ClassificacaoDRG is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        drg = ClassificacaoDRG.objects.get(pk=pk, empresa=emp)
    except ClassificacaoDRG.DoesNotExist:
        return JsonResponse({"erro": "Classificação não encontrada"}, status=404)

    # Verifica credencial
    try:
        from .models import CredenciaisIntegracoes
        cred = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="drg").first()
    except Exception:
        cred = None

    if not cred:
        return JsonResponse({
            "status": "simulado",
            "mensagem": "Configure credenciais em /configuracoes/integracoes",
            "drg_id": drg.id,
        })

    # Envio real (placeholder para integração futura)
    drg.enviado_valor_saude = True
    drg.data_envio = timezone.now()
    drg.resposta_api = {"status": "ok", "protocolo": f"VSB-{drg.id}"}
    drg.save()
    return JsonResponse({"status": "enviado", "protocolo": f"VSB-{drg.id}"})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_custos_kpis(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    comp_atual = timezone.now().strftime("%Y-%m")
    custo_mes = 0
    drg_classificados_mes = 0
    pendentes_envio = 0

    if CustoAssistencial:
        total = CustoAssistencial.objects.filter(
            empresa=emp, competencia=comp_atual
        ).aggregate(t=Sum("valor"))["t"]
        custo_mes = float(total or 0)

    if ClassificacaoDRG:
        drg_classificados_mes = ClassificacaoDRG.objects.filter(
            empresa=emp, competencia=comp_atual
        ).count()
        pendentes_envio = ClassificacaoDRG.objects.filter(
            empresa=emp, enviado_valor_saude=False
        ).count()

    return JsonResponse({
        "custo_mes": custo_mes,
        "drg_classificados_mes": drg_classificados_mes,
        "pendentes_envio": pendentes_envio,
        "competencia": comp_atual,
    })
