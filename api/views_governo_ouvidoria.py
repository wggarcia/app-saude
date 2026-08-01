"""
Ouvidoria do SUS — canal de manifestação do cidadão (reclamação, denúncia,
sugestão, elogio, solicitação de informação), nos termos da Lei de Acesso à
Informação (Lei 12.527/2011) e da Política Nacional de Ouvidoria do SUS.

GET/POST /api/governo/ouvidoria/manifestacoes        Lista / registra manifestação
GET/PATCH /api/governo/ouvidoria/manifestacoes/<id>   Detalhe / responder
GET      /api/governo/ouvidoria/kpis                  KPIs de prazo e volume
"""
import json
import logging
from datetime import date, timedelta

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial, api_requer_permissao_modulo,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .views_dashboard import contexto_navegacao_setorial

logger = logging.getLogger(__name__)

# LAI (Lei 12.527/2011): prazo de resposta de 20 dias úteis, prorrogável por
# mais 10. Usamos 30 dias corridos como aproximação conservadora (superestima
# o prazo em vez de subestimar) — evita cálculo de dias úteis/feriados.
_PRAZO_RESPOSTA_DIAS = 30


def _e(request):
    empresa = get_empresa(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.secretaria_agendamento", "governo.administrativo")
def governo_ouvidoria_page(request):
    return render(request, "governo_ouvidoria.html", contexto_navegacao_setorial(request, "governo"))


# ── Manifestações ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.secretaria_agendamento", "governo.administrativo")
def api_ouvidoria_manifestacoes(request):
    """GET/POST /api/governo/ouvidoria/manifestacoes"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ManifestacaoOuvidoria

    if request.method == "GET":
        qs = ManifestacaoOuvidoria.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        tipo_f = request.GET.get("tipo")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        if q:
            qs = qs.filter(
                Q(protocolo__icontains=q) | Q(manifestante_nome__icontains=q)
                | Q(manifestante_cpf__icontains=q)
            )

        hoje = date.today()
        return JsonResponse({
            "total": qs.count(),
            "manifestacoes": [
                {
                    "id": m.id,
                    "protocolo": m.protocolo,
                    "tipo": m.tipo,
                    "tipo_display": m.get_tipo_display(),
                    "canal": m.canal,
                    "canal_display": m.get_canal_display(),
                    "anonima": m.anonima,
                    "manifestante_nome": "(anônimo)" if m.anonima else (m.manifestante_nome or "—"),
                    "unidade_relacionada": m.unidade_relacionada.nome if m.unidade_relacionada else None,
                    "descricao": m.descricao[:200],
                    "sigiloso": m.sigiloso,
                    "status": m.status,
                    "status_display": m.get_status_display(),
                    "prazo_resposta": m.prazo_resposta.isoformat() if m.prazo_resposta else None,
                    "prazo_vencido": bool(
                        m.prazo_resposta and m.prazo_resposta < hoje and m.status not in ("respondida", "encerrada")
                    ),
                    "criado_em": m.criado_em.isoformat(),
                }
                for m in qs.order_by("-criado_em")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    tipo = data.get("tipo")
    descricao = (data.get("descricao") or "").strip()
    if tipo not in dict(ManifestacaoOuvidoria.TIPO):
        return JsonResponse({"erro": "Tipo de manifestação inválido"}, status=400)
    if not descricao:
        return JsonResponse({"erro": "Descrição é obrigatória"}, status=400)

    total = ManifestacaoOuvidoria.objects.filter(empresa=empresa).count() + 1
    protocolo = f"OUV-{empresa.id:06d}-{total:06d}"

    unidade = None
    unidade_id = data.get("unidade_relacionada_id")
    if unidade_id:
        from .models import UnidadeSaude
        unidade = UnidadeSaude.objects.filter(id=unidade_id, empresa=empresa).first()

    anonima = bool(data.get("anonima"))
    m = ManifestacaoOuvidoria.objects.create(
        empresa=empresa,
        protocolo=protocolo,
        tipo=tipo,
        canal=data.get("canal") or "app",
        anonima=anonima,
        manifestante_nome="" if anonima else (data.get("manifestante_nome") or ""),
        manifestante_cpf="" if anonima else (data.get("manifestante_cpf") or ""),
        manifestante_telefone="" if anonima else (data.get("manifestante_telefone") or ""),
        manifestante_email="" if anonima else (data.get("manifestante_email") or ""),
        unidade_relacionada=unidade,
        descricao=descricao,
        sigiloso=bool(data.get("sigiloso")),
        status="aberta",
        prazo_resposta=date.today() + timedelta(days=_PRAZO_RESPOSTA_DIAS),
    )
    return JsonResponse({"id": m.id, "protocolo": protocolo}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("governo.secretaria_agendamento", "governo.administrativo")
def api_ouvidoria_manifestacao_detalhe(request, man_id):
    """GET/PATCH /api/governo/ouvidoria/manifestacoes/<id>"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ManifestacaoOuvidoria

    try:
        m = ManifestacaoOuvidoria.objects.get(id=man_id, empresa=empresa)
    except ManifestacaoOuvidoria.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": m.id,
            "protocolo": m.protocolo,
            "tipo": m.tipo,
            "tipo_display": m.get_tipo_display(),
            "canal_display": m.get_canal_display(),
            "anonima": m.anonima,
            "manifestante_nome": m.manifestante_nome,
            "manifestante_cpf": m.manifestante_cpf,
            "manifestante_telefone": m.manifestante_telefone,
            "manifestante_email": m.manifestante_email,
            "unidade_relacionada": m.unidade_relacionada.nome if m.unidade_relacionada else None,
            "descricao": m.descricao,
            "sigiloso": m.sigiloso,
            "status": m.status,
            "status_display": m.get_status_display(),
            "resposta": m.resposta,
            "respondido_por": m.respondido_por,
            "prazo_resposta": m.prazo_resposta.isoformat() if m.prazo_resposta else None,
            "criado_em": m.criado_em.isoformat(),
            "respondido_em": m.respondido_em.isoformat() if m.respondido_em else None,
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if "resposta" in data:
        m.resposta = data["resposta"]
        m.respondido_por = data.get("respondido_por", m.respondido_por)
        m.respondido_em = timezone.now()
        m.status = "respondida"
    if "status" in data and data["status"] in dict(ManifestacaoOuvidoria.STATUS):
        m.status = data["status"]
    m.save()
    return JsonResponse({"ok": True, "status": m.status})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.secretaria_agendamento", "governo.administrativo")
def api_ouvidoria_kpis(request):
    """GET /api/governo/ouvidoria/kpis"""
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ManifestacaoOuvidoria

    hoje = date.today()
    qs = ManifestacaoOuvidoria.objects.filter(empresa=empresa)
    por_status = dict(qs.values_list("status").annotate(n=Count("id")).order_by())
    por_tipo = dict(qs.values_list("tipo").annotate(n=Count("id")).order_by())
    prazo_vencido = qs.filter(
        prazo_resposta__lt=hoje
    ).exclude(status__in=("respondida", "encerrada")).count()

    return JsonResponse({
        "total": qs.count(),
        "por_status": por_status,
        "por_tipo": por_tipo,
        "prazo_vencido": prazo_vencido,
        "abertas": por_status.get("aberta", 0) + por_status.get("em_analise", 0),
    })
