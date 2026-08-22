"""
Qualidade Hospitalar e NSP — Núcleo de Segurança do Paciente
Gestão de incidentes de segurança do paciente, indicadores ONA/JCI e KPIs
de qualidade assistencial (RDC 36/2013 - ANVISA / Portaria GM/MS 529/2013).
"""
import json
import logging
from datetime import date

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_permissao_modulo,
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _get_qualidade_models():
    from .models import IncidenteSegurancaPaciente
    return IncidenteSegurancaPaciente


# ── Página ────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.qualidade", "Qualidade/NSP")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_qualidade_page(request):
    return render(request, "hospital_qualidade.html")
# ── Incidentes de Segurança do Paciente ───────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.qualidade")
@api_requer_permissao_modulo("hospital.administrativo")
def api_qualidade_incidentes(request):
    """GET/POST /api/hospital/qualidade/incidentes"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    IncidenteSegurancaPaciente = _get_qualidade_models()

    if request.method == "GET":
        try:
            qs = IncidenteSegurancaPaciente.objects.filter(empresa=empresa)

            encerrado = request.GET.get("encerrado")
            gravidade = request.GET.get("gravidade")
            tipo = request.GET.get("tipo")

            if encerrado is not None:
                qs = qs.filter(encerrado=(encerrado.lower() == "true"))
            if gravidade:
                qs = qs.filter(gravidade=gravidade)
            if tipo:
                qs = qs.filter(tipo=tipo)

            return JsonResponse({
                "total": qs.count(),
                "incidentes": [
                    {
                        "id": inc.id,
                        "tipo": inc.tipo,
                        "tipo_display": inc.get_tipo_display(),
                        "descricao": inc.descricao,
                        "setor": inc.setor,
                        "data_ocorrencia": inc.data_ocorrencia.isoformat(),
                        "gravidade": inc.gravidade,
                        "gravidade_display": inc.get_gravidade_display(),
                        "paciente": inc.paciente,
                        "notificado_anvisa": inc.notificado_anvisa,
                        "acao_tomada": inc.acao_tomada,
                        "encerrado": inc.encerrado,
                        "registrado_por": inc.registrado_por,
                        "criado_em": inc.criado_em.isoformat(),
                    }
                    for inc in qs.order_by("-data_ocorrencia")[:500]
                ],
            })
        except Exception:
            logger.exception("Erro ao listar incidentes NSP")
            return JsonResponse({"erro": "Erro interno"}, status=500)

    # POST — criar incidente
    try:
        data = json.loads(request.body)
        with transaction.atomic():
            inc = IncidenteSegurancaPaciente.objects.create(
                empresa=empresa,
                tipo=data.get("tipo", "outro"),
                descricao=data["descricao"],
                setor=data["setor"],
                data_ocorrencia=data.get("data_ocorrencia", timezone.now().isoformat()),
                gravidade=data.get("gravidade", "near_miss"),
                paciente=data.get("paciente", ""),
                registrado_por=data.get("registrado_por", ""),
                notificado_anvisa=data.get("notificado_anvisa", False),
                acao_tomada=data.get("acao_tomada", ""),
            )
        return JsonResponse({"id": inc.id}, status=201)
    except KeyError as exc:
        return JsonResponse({"erro": f"Campo obrigatório ausente: {exc}"}, status=400)
    except Exception:
        logger.exception("Erro ao criar incidente NSP")
        return JsonResponse({"erro": "Erro interno"}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.qualidade")
@api_requer_permissao_modulo("hospital.administrativo")
def api_qualidade_incidente_detalhe(request, pk):
    """GET/PATCH /api/hospital/qualidade/incidentes/<pk>"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    IncidenteSegurancaPaciente = _get_qualidade_models()

    try:
        inc = IncidenteSegurancaPaciente.objects.get(id=pk, empresa=empresa)
    except IncidenteSegurancaPaciente.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    except Exception:
        logger.exception("Erro ao buscar incidente NSP pk=%s", pk)
        return JsonResponse({"erro": "Erro interno"}, status=500)

    if request.method == "GET":
        return JsonResponse({
            "id": inc.id,
            "tipo": inc.tipo,
            "tipo_display": inc.get_tipo_display(),
            "descricao": inc.descricao,
            "setor": inc.setor,
            "data_ocorrencia": inc.data_ocorrencia.isoformat(),
            "gravidade": inc.gravidade,
            "gravidade_display": inc.get_gravidade_display(),
            "paciente": inc.paciente,
            "notificado_anvisa": inc.notificado_anvisa,
            "acao_tomada": inc.acao_tomada,
            "encerrado": inc.encerrado,
            "registrado_por": inc.registrado_por,
            "criado_em": inc.criado_em.isoformat(),
        })

    # PATCH
    try:
        data = json.loads(request.body)
        campos_editaveis = ["acao_tomada", "encerrado", "notificado_anvisa"]
        for campo in campos_editaveis:
            if campo in data:
                setattr(inc, campo, data[campo])
        inc.save()
        return JsonResponse({"ok": True})
    except Exception:
        logger.exception("Erro ao atualizar incidente NSP pk=%s", pk)
        return JsonResponse({"erro": "Erro interno"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.qualidade")
@api_requer_permissao_modulo("hospital.administrativo")
def api_qualidade_incidente_encerrar(request, pk):
    """POST /api/hospital/qualidade/incidentes/<pk>/encerrar"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    IncidenteSegurancaPaciente = _get_qualidade_models()

    try:
        inc = IncidenteSegurancaPaciente.objects.get(id=pk, empresa=empresa)
    except IncidenteSegurancaPaciente.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    except Exception:
        logger.exception("Erro ao buscar incidente NSP para encerrar pk=%s", pk)
        return JsonResponse({"erro": "Erro interno"}, status=500)

    try:
        data = json.loads(request.body) if request.body else {}
        inc.encerrado = True
        if data.get("acao_tomada"):
            inc.acao_tomada = data["acao_tomada"]
        inc.save()
        return JsonResponse({"ok": True})
    except Exception:
        logger.exception("Erro ao encerrar incidente NSP pk=%s", pk)
        return JsonResponse({"erro": "Erro interno"}, status=500)


# ── Indicadores ONA/JCI mensais ───────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("hospital.qualidade")
@api_requer_permissao_modulo("hospital.administrativo")
def api_qualidade_indicadores(request):
    """GET /api/hospital/qualidade/indicadores
    Indicadores ONA/JCI do mês atual calculados a partir de IncidenteSegurancaPaciente.
    - taxa_queda: incidentes tipo=queda / total do mês * 100
    - taxa_evento_adverso_medicamento: tipo=medicamento / total * 100
    - taxa_identificacao_incorreta: tipo=identificacao / total * 100
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    IncidenteSegurancaPaciente = _get_qualidade_models()

    try:
        hoje = date.today()
        ano, mes = hoje.year, hoje.month

        qs_mes = IncidenteSegurancaPaciente.objects.filter(
            empresa=empresa,
            data_ocorrencia__year=ano,
            data_ocorrencia__month=mes,
        )
        total_mes = qs_mes.count()

        por_tipo = dict(
            qs_mes.values_list("tipo").annotate(n=Count("id")).order_by()
        )
        por_gravidade = dict(
            qs_mes.values_list("gravidade").annotate(n=Count("id")).order_by()
        )

        def taxa(tipo_key):
            if not total_mes:
                return 0.0
            return round(por_tipo.get(tipo_key, 0) / total_mes * 100, 2)

        return JsonResponse({
            "competencia": f"{ano}{mes:02d}",
            "total_incidentes_mes": total_mes,
            "taxa_queda": taxa("queda"),
            "taxa_evento_adverso_medicamento": taxa("medicamento"),
            "taxa_identificacao_incorreta": taxa("identificacao"),
            "por_tipo": por_tipo,
            "por_gravidade": por_gravidade,
        })
    except Exception:
        logger.exception("Erro ao calcular indicadores NSP")
        return JsonResponse({"erro": "Erro interno"}, status=500)


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.qualidade")
@api_requer_permissao_modulo("hospital.administrativo")
def api_qualidade_kpis(request):
    """GET /api/hospital/qualidade/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    IncidenteSegurancaPaciente = _get_qualidade_models()

    try:
        hoje = date.today()
        ano, mes = hoje.year, hoje.month

        qs_mes = IncidenteSegurancaPaciente.objects.filter(
            empresa=empresa,
            data_ocorrencia__year=ano,
            data_ocorrencia__month=mes,
        )

        near_miss_mes = qs_mes.filter(gravidade="near_miss").count()
        dano_grave_mes = qs_mes.filter(
            gravidade__in=["dano_grave", "obito"]
        ).count()
        aguardando_anvisa = IncidenteSegurancaPaciente.objects.filter(
            empresa=empresa,
            notificado_anvisa=False,
            gravidade__in=["dano_grave", "obito"],
        ).count()
        encerrados_mes = qs_mes.filter(encerrado=True).count()

        return JsonResponse({
            "near_miss_mes": near_miss_mes,
            "dano_grave_mes": dano_grave_mes,
            "aguardando_anvisa": aguardando_anvisa,
            "encerrados_mes": encerrados_mes,
        })
    except Exception:
        logger.exception("Erro ao calcular KPIs NSP")
        return JsonResponse({"erro": "Erro interno"}, status=500)


# ── IA de causa-raiz (o diferencial vs. Tasy) ──────────────────────────────────

_TAXONOMIA_OMS = {
    "queda": "Quedas", "medicamento": "Erro de medicação",
    "procedimento": "Procedimento clínico/cirúrgico", "identificacao": "Identificação do paciente",
    "comunicacao": "Falha de comunicação", "infeccao": "Infecção associada à assistência (IRAS)",
    "outro": "Outros",
}


def _analise_causa_raiz_fallback(inc):
    """Análise determinística por regras — usada quando a IA não está disponível.
    Garante que o recurso sempre entrega algo útil (nunca tela vazia)."""
    risco = ("alto" if inc.gravidade in ("dano_grave", "obito")
             else "medio" if inc.gravidade in ("dano_leve", "dano_moderado")
             else "baixo")
    return {
        "classificacao": _TAXONOMIA_OMS.get(inc.tipo, "Outros"),
        "risco_recorrencia": risco,
        "ishikawa": {
            "Pessoas": f"Avaliar dimensionamento e treinamento da equipe de {inc.setor or 'do setor'}.",
            "Processo": f"Revisar o protocolo assistencial de {_TAXONOMIA_OMS.get(inc.tipo, inc.tipo)}.",
            "Ambiente": "Verificar condições físicas, sinalização e fluxo do setor.",
            "Equipamento/Material": "Checar disponibilidade e conformidade de insumos e dispositivos.",
        },
        "cinco_porques": [
            "Por que o incidente ocorreu? — mapear o fato relatado.",
            "Por que a barreira de segurança falhou? — identificar a barreira ausente.",
            "Por que essa barreira não existia ou estava fraca? — revisar o processo.",
            "Por que o processo permitiu o erro? — checar padronização e dupla checagem.",
            "Causa-raiz provável: falha sistêmica de processo (não culpa individual).",
        ],
        "acoes_preventivas": [
            "Implantar dupla checagem no ponto exato da falha.",
            "Capacitação dirigida da equipe do setor envolvido.",
            "Alerta/checklist no sistema para este tipo de incidente.",
        ],
        "fonte": "regras",
    }


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.qualidade")
@api_requer_permissao_modulo("hospital.administrativo")
def api_qualidade_ia_analise(request, pk):
    """POST /api/hospital/qualidade/incidentes/<pk>/ia-analise
    Classifica o incidente (taxonomia OMS), monta Ishikawa + 5 Porquês e estima
    risco de recorrência. Usa Anthropic quando há chave; cai em análise por
    regras se não houver/der erro — nunca falha."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    IncidenteSegurancaPaciente = _get_qualidade_models()
    try:
        inc = IncidenteSegurancaPaciente.objects.get(id=pk, empresa=empresa)
    except IncidenteSegurancaPaciente.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    from django.conf import settings
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return JsonResponse({"analise": _analise_causa_raiz_fallback(inc)})

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system = (
            "Você é especialista em segurança do paciente (RDC 36/2013 ANVISA, "
            "taxonomia OMS/WHO ICPS, acreditação ONA/JCI). Analise o incidente e "
            "responda SOMENTE com um JSON válido (sem markdown, sem texto fora do JSON) "
            'no formato: {"classificacao":"<categoria OMS>","risco_recorrencia":"baixo|medio|alto",'
            '"ishikawa":{"Pessoas":"...","Processo":"...","Ambiente":"...","Equipamento/Material":"..."},'
            '"cinco_porques":["...","...","...","...","<causa-raiz>"],'
            '"acoes_preventivas":["...","...","..."]}. Escreva em português, objetivo e acionável.'
        )
        user_msg = (
            f"Tipo: {inc.get_tipo_display()}\nGravidade: {inc.get_gravidade_display()}\n"
            f"Setor: {inc.setor}\nDescrição: {inc.descricao}\n"
            f"Ação já tomada: {inc.acao_tomada or '—'}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1200,
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
        logger.exception("IA análise NSP pk=%s — caindo em fallback por regras", pk)
        return JsonResponse({"analise": _analise_causa_raiz_fallback(inc)})
