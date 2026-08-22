"""
Custos Hospitalares — Centros de Responsabilidade, custo por competência e
margem por DRG (custo real vs. reembolso esperado), com causa-raiz por IA.
"""
import json
import logging
import os
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Avg, Q
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo, api_requer_feature, api_requer_permissao_modulo
from .views_dashboard import contexto_navegacao_setorial

try:
    from .models import CentroResponsabilidade, CustoAssistencial, ClassificacaoDRG, PacienteInternado
except ImportError:
    CentroResponsabilidade = CustoAssistencial = ClassificacaoDRG = PacienteInternado = None

logger = logging.getLogger(__name__)

# Valor de referência por ponto de peso relativo DRG, usado só para estimar o
# reembolso esperado e calcular margem. É um parâmetro de configuração local
# (não é tabela oficial ANS/SUS) — por isso é sempre exibido de forma
# transparente na tela, nunca apresentado como valor oficial.
_DRG_VALOR_BASE_PADRAO = 3000.0


def _drg_valor_base():
    try:
        return float(os.environ.get("DRG_VALOR_BASE", _DRG_VALOR_BASE_PADRAO))
    except (TypeError, ValueError):
        return _DRG_VALOR_BASE_PADRAO


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.faturamento_avancado", "Custos")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_custos_page(request):
    return render(request, "hospital_custos.html")
# ─── Centros de Responsabilidade ─────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
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
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
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
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
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
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
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
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
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

    sigquali_url = os.environ.get("SIGQUALI_API_URL")
    sigquali_token = os.environ.get("SIGQUALI_API_TOKEN")
    if not sigquali_url or not sigquali_token:
        return JsonResponse({
            "erro": "Integração Sigquali não configurada",
            "mensagem": "Configure as variáveis de ambiente SIGQUALI_API_URL e "
                        "SIGQUALI_API_TOKEN para habilitar o envio ao Valor Saúde Brasil.",
            "drg_id": drg.id,
        }, status=503)

    try:
        import requests
        resp = requests.post(
            sigquali_url,
            json={
                "episodeId": str(drg.id),
                "drgCode": drg.codigo_drg,
                "aihNumero": drg.aih_numero,
                "competencia": drg.competencia,
                "relativeWeight": float(drg.peso_relativo) if drg.peso_relativo else None,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {sigquali_token}",
            },
            timeout=15,
        )
    except Exception as exc:
        logger.warning("Erro ao enviar DRG %s ao Sigquali: %s", pk, exc)
        return JsonResponse({
            "erro": f"Falha na comunicação com Sigquali: {exc}",
            "drg_id": drg.id,
        }, status=502)

    if resp.status_code != 200:
        return JsonResponse({
            "erro": f"Sigquali retornou HTTP {resp.status_code}",
            "detalhe": resp.text[:300],
            "drg_id": drg.id,
        }, status=502)

    try:
        resposta_json = resp.json()
    except ValueError:
        resposta_json = {"raw": resp.text[:500]}

    protocolo = resposta_json.get("protocolo") or resposta_json.get("id") or f"VSB-{drg.id}"
    drg.enviado_valor_saude = True
    drg.data_envio = timezone.now()
    drg.resposta_api = resposta_json
    drg.save()
    return JsonResponse({"status": "enviado", "protocolo": protocolo})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
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


# ─── Margem por DRG (o diferencial vs. Tasy) ─────────────────────────────────
# Cruza o custo real lançado (CustoAssistencial.drg_codigo) com o peso relativo
# classificado (ClassificacaoDRG.codigo_drg) para estimar, por código DRG, se a
# internação está dando margem positiva ou prejuízo — e por quê.

def _margem_por_drg(emp, competencia):
    valor_base = _drg_valor_base()

    custos_por_drg = {}
    if CustoAssistencial is not None:
        qs = (CustoAssistencial.objects
              .filter(empresa=emp, competencia=competencia)
              .exclude(drg_codigo="")
              .values("drg_codigo")
              .annotate(custo_total=Sum("valor"), qtd_lancamentos=Count("id")))
        for r in qs:
            custos_por_drg[r["drg_codigo"]] = {
                "custo_total": float(r["custo_total"] or 0),
                "qtd_lancamentos": r["qtd_lancamentos"],
            }

    pesos_por_drg = {}
    if ClassificacaoDRG is not None:
        qs = (ClassificacaoDRG.objects
              .filter(empresa=emp, competencia=competencia)
              .exclude(codigo_drg="")
              .values("codigo_drg")
              .annotate(peso_medio=Avg("peso_relativo"), qtd_casos=Count("id")))
        for r in qs:
            pesos_por_drg[r["codigo_drg"]] = {
                "peso_medio": float(r["peso_medio"] or 0),
                "qtd_casos": r["qtd_casos"],
            }

    codigos = set(custos_por_drg) | set(pesos_por_drg)
    linhas = []
    for codigo in codigos:
        c = custos_por_drg.get(codigo, {"custo_total": 0.0, "qtd_lancamentos": 0})
        p = pesos_por_drg.get(codigo, {"peso_medio": 0.0, "qtd_casos": 0})
        valor_esperado = round(p["peso_medio"] * valor_base * max(p["qtd_casos"], 1), 2) if p["qtd_casos"] else None
        margem = round(valor_esperado - c["custo_total"], 2) if valor_esperado is not None else None
        margem_pct = round(margem / valor_esperado * 100, 1) if valor_esperado else None
        linhas.append({
            "drg_codigo": codigo,
            "custo_total": c["custo_total"],
            "qtd_lancamentos": c["qtd_lancamentos"],
            "peso_medio": p["peso_medio"],
            "qtd_casos": p["qtd_casos"],
            "valor_esperado": valor_esperado,
            "margem": margem,
            "margem_pct": margem_pct,
        })
    linhas.sort(key=lambda r: (r["margem"] is None, r["margem"]))
    return linhas, valor_base


@require_http_methods(["GET"])
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
def api_custos_margem(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    competencia = request.GET.get("competencia") or timezone.now().strftime("%Y-%m")
    linhas, valor_base = _margem_por_drg(emp, competencia)
    return JsonResponse({
        "competencia": competencia,
        "valor_base_ponto_drg": valor_base,
        "drgs": linhas,
        "total_drgs_prejuizo": sum(1 for r in linhas if r["margem"] is not None and r["margem"] < 0),
    })


_CATEGORIA_LABEL = dict(CustoAssistencial.CATEGORIA_CHOICES) if CustoAssistencial else {}


def _margem_causa_fallback(codigo, competencia, linha, por_categoria):
    """Explicação determinística por regras — sempre entrega algo útil."""
    if not por_categoria:
        return {
            "diagnostico": "Sem lançamentos de custo detalhados para este DRG na competência.",
            "causas_provaveis": ["Registrar os lançamentos de custo vinculados a este código DRG "
                                  "para permitir a análise de margem."],
            "acoes_recomendadas": ["Vincular os lançamentos de custo ao campo drg_codigo no momento do apontamento."],
            "fonte": "regras",
        }
    maior = max(por_categoria, key=lambda c: c["total"])
    label = _CATEGORIA_LABEL.get(maior["categoria"], maior["categoria"])
    dicas = {
        "material": "Negociar preços com fornecedores/OPME e revisar consumo por procedimento.",
        "pessoal": "Revisar dimensionamento de equipe e produtividade no setor envolvido.",
        "servico": "Renegociar contratos de serviços terceirizados vinculados a este DRG.",
        "depreciacao": "Avaliar taxa de ocupação dos equipamentos alocados a este procedimento.",
        "overhead": "Revisar rateio de custos indiretos aplicado a este centro de custo.",
    }
    margem = linha.get("margem")
    diagnostico = (
        f"Margem negativa de R$ {abs(margem):,.2f} — categoria '{label}' concentra "
        f"{maior['total']/sum(c['total'] for c in por_categoria)*100:.0f}% do custo lançado."
        if margem is not None and margem < 0 else
        "Margem dentro do esperado para o valor de referência configurado."
    )
    return {
        "diagnostico": diagnostico,
        "causas_provaveis": [f"Concentração de custo em '{label}' acima do peso relativo médio do DRG."],
        "acoes_recomendadas": [dicas.get(maior["categoria"], "Revisar composição de custo deste DRG.")],
        "fonte": "regras",
    }


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.faturamento_avancado")
@api_requer_permissao_modulo("hospital.administrativo")
def api_custos_margem_ia_analise(request):
    """POST /api/hospital/custos/margem/ia-analise  {drg_codigo, competencia}
    Explica por que um DRG está dando prejuízo (ou não) cruzando custo real x
    reembolso esperado. Usa Anthropic quando há chave; cai em regras determinísticas
    caso contrário — nunca falha."""
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if CustoAssistencial is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        body = {}
    codigo = body.get("drg_codigo", "")
    competencia = body.get("competencia") or timezone.now().strftime("%Y-%m")
    if not codigo:
        return JsonResponse({"erro": "drg_codigo obrigatório"}, status=400)

    linhas, _ = _margem_por_drg(emp, competencia)
    linha = next((r for r in linhas if r["drg_codigo"] == codigo), None)
    if linha is None:
        return JsonResponse({"erro": "DRG não encontrado nesta competência"}, status=404)

    por_categoria = list(
        CustoAssistencial.objects
        .filter(empresa=emp, competencia=competencia, drg_codigo=codigo)
        .values("categoria")
        .annotate(total=Sum("valor"))
        .order_by("-total")
    )
    por_categoria = [{"categoria": r["categoria"], "total": float(r["total"] or 0)} for r in por_categoria]

    from django.conf import settings
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return JsonResponse({"analise": _margem_causa_fallback(codigo, competencia, linha, por_categoria)})

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system = (
            "Você é controller hospitalar especialista em custeio por DRG. Analise a "
            "margem de um código DRG (custo real lançado vs. reembolso esperado estimado "
            "pelo peso relativo) e responda SOMENTE com um JSON válido (sem markdown) no "
            'formato: {"diagnostico":"...","causas_provaveis":["...","..."],'
            '"acoes_recomendadas":["...","...","..."]}. Português, objetivo, acionável, '
            "sem inventar valores que não foram informados."
        )
        user_msg = (
            f"DRG: {codigo}\nCompetência: {competencia}\n"
            f"Custo total lançado: R$ {linha['custo_total']:.2f} ({linha['qtd_lancamentos']} lançamentos)\n"
            f"Peso relativo médio: {linha['peso_medio']}\nCasos classificados: {linha['qtd_casos']}\n"
            f"Valor esperado de reembolso (estimado): "
            f"{'R$ %.2f' % linha['valor_esperado'] if linha['valor_esperado'] is not None else 'não estimável'}\n"
            f"Margem: {'R$ %.2f' % linha['margem'] if linha['margem'] is not None else '—'}"
            f" ({linha['margem_pct']}%)\n"
            f"Custo por categoria: {por_categoria}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=900,
            system=system, messages=[{"role": "user", "content": user_msg}],
        )
        raw = (resp.content[0].text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw[:4].lower() == "json":
                raw = raw[4:]
            raw = raw.strip()
        analise = json.loads(raw)
        analise["fonte"] = "ia"
        return JsonResponse({"analise": analise})
    except Exception:
        logger.exception("IA de margem DRG %s/%s — caindo em fallback por regras", codigo, competencia)
        return JsonResponse({"analise": _margem_causa_fallback(codigo, competencia, linha, por_categoria)})
