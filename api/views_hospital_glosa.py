"""
Hospital — Anti-Glosa Fase 3: glosa RECEBIDA (item a item) + RECURSO com IA de mérito.

Lado PRESTADOR: registra a glosa que a operadora devolveu sobre uma guia TISS
enviada, abre recurso e usa a heurística de mérito (reaproveitada do portal do
prestador do lado operadora) para pré-pontuar a chance de deferimento e priorizar.
Tudo isolado por tenant (empresa) e gated por hospital.anti_glosa.
"""
import json
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_feature, api_requer_permissao_modulo,
    requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo,
)
from .models import GuiaTISS, GlosaRecebida, RecursoGlosaPrestador
from .views_hospital_tiss import _empresa as _empresa_hospital
from .views_dashboard import contexto_navegacao_setorial
from .views_plano_portal_prestador import _ia_merito_recurso


# ── Cockpit Anti-Glosa (Fase 4) ──────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.anti_glosa", "Anti-Glosa")
@requer_operacao_page
@requer_permissao_modulo("hospital.operacional")
def hospital_anti_glosa_page(request):
    return render(request, "hospital_anti_glosa.html",
                  contexto_navegacao_setorial(request, "hospital"))


# ── Sugestão de texto de recurso por código de glosa (parte editável) ────────

_TEXTO_RECURSO = {
    "1403": ("Solicitamos revisão da glosa por duplicidade. Os procedimentos referem-se a "
             "atendimentos distintos, com registros e horários próprios em prontuário, não "
             "configurando cobrança em duplicidade."),
    "1704": ("Solicitamos revisão da glosa de quantidade. A quantidade executada está "
             "respaldada clinicamente na evolução e na conduta registradas em prontuário."),
    "1707": ("Solicitamos revisão da glosa de código. O procedimento executado corresponde "
             "ao código TUSS informado, conforme descrição e laudo anexos."),
    "1401": ("Solicitamos revisão da glosa de credenciamento. O atendimento foi prestado sob "
             "vínculo contratual vigente na data do fato gerador."),
}


def _sugerir_texto_recurso(codigo_glosa):
    return _TEXTO_RECURSO.get((codigo_glosa or "").strip(),
                              "Solicitamos revisão da glosa. Anexamos a documentação assistencial "
                              "(prontuário, laudos e autorização) que respalda o procedimento cobrado.")


def _dec(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _glosa_dict(g):
    return {
        "id": g.id,
        "guia_id": g.guia_id,
        "guia_numero": g.guia.numero_guia if g.guia_id else "",
        "beneficiario": g.guia.beneficiario_nome if g.guia_id else "",
        "protocolo_operadora": g.protocolo_operadora,
        "data_glosa": g.data_glosa.strftime("%d/%m/%Y") if g.data_glosa else None,
        "origem": g.origem,
        "valor_glosado_total": float(g.valor_glosado_total),
        "itens": g.itens,
        "status": g.status,
        "status_label": dict(GlosaRecebida.STATUS_CHOICES).get(g.status, g.status),
        "recursos": [_recurso_dict(r) for r in g.recursos.all()],
        "criado_em": g.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _recurso_dict(r):
    return {
        "id": r.id,
        "glosa_id": r.glosa_id,
        "codigo_glosa": r.codigo_glosa,
        "justificativa": r.justificativa,
        "ia_merito_score": r.ia_merito_score,
        "ia_parecer": r.ia_parecer,
        "valor_recorrido": float(r.valor_recorrido),
        "valor_recuperado": float(r.valor_recuperado),
        "protocolo": r.protocolo,
        "resposta_operadora": r.resposta_operadora,
        "status": r.status,
        "status_label": dict(RecursoGlosaPrestador.STATUS_CHOICES).get(r.status, r.status),
        "criado_em": r.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ── Registrar glosa recebida (item a item) ───────────────────────────────────

@api_requer_feature("hospital.anti_glosa")
@api_requer_permissao_modulo("hospital.operacional")
@csrf_exempt
@require_http_methods(["POST"])
def api_glosa_registrar(request, guia_id):
    empresa = _empresa_hospital(request)
    if isinstance(empresa, JsonResponse):
        return empresa
    try:
        guia = GuiaTISS.objects.get(pk=guia_id, empresa=empresa)
    except GuiaTISS.DoesNotExist:
        return JsonResponse({"erro": "Guia não encontrada"}, status=404)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    itens_in = data.get("itens", [])
    if not isinstance(itens_in, list) or not itens_in:
        return JsonResponse({"erro": "Informe ao menos um item glosado."}, status=400)

    itens = []
    total = Decimal("0")
    for it in itens_in:
        vg = _dec(it.get("valor_glosado", 0))
        total += vg
        itens.append({
            "codigo": str(it.get("codigo", "") or ""),
            "descricao": str(it.get("descricao", "") or ""),
            "codigo_glosa": str(it.get("codigo_glosa", "") or ""),
            "motivo_glosa": str(it.get("motivo_glosa", "") or ""),
            "valor_glosado": float(vg),
        })

    data_glosa = None
    if data.get("data_glosa"):
        from django.utils.dateparse import parse_date
        data_glosa = parse_date(str(data.get("data_glosa")))

    glosa = GlosaRecebida.objects.create(
        empresa=empresa, guia=guia,
        protocolo_operadora=str(data.get("protocolo_operadora", "") or ""),
        data_glosa=data_glosa,
        origem=data.get("origem", "manual") if data.get("origem") in dict(GlosaRecebida.ORIGEM_CHOICES) else "manual",
        valor_glosado_total=total,
        itens=itens,
        status="recebida",
    )

    # reflete na guia: passa a glosada e ajusta o valor aprovado
    guia.status = "glosada"
    aprovado = _dec(guia.valor_apresentado) - total
    guia.valor_aprovado = aprovado if aprovado > 0 else Decimal("0")
    guia.save(update_fields=["status", "valor_aprovado"])

    return JsonResponse({"ok": True, "glosa": _glosa_dict(glosa)}, status=201)


# ── Lista de glosas + KPIs ───────────────────────────────────────────────────

@api_requer_feature("hospital.anti_glosa")
@api_requer_permissao_modulo("hospital.operacional")
@require_http_methods(["GET"])
def api_glosas_lista(request):
    empresa = _empresa_hospital(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = GlosaRecebida.objects.filter(empresa=empresa).select_related("guia").prefetch_related("recursos")
    guia_id = request.GET.get("guia")
    if guia_id:
        qs = qs.filter(guia_id=guia_id)
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    glosas = [_glosa_dict(g) for g in qs.order_by("-criado_em")[:200]]

    total_glosado = float(GlosaRecebida.objects.filter(empresa=empresa)
                          .aggregate(t=Sum("valor_glosado_total"))["t"] or 0)
    total_recuperado = float(RecursoGlosaPrestador.objects.filter(
        empresa=empresa, status__in=["deferido", "parcial"])
        .aggregate(t=Sum("valor_recuperado"))["t"] or 0)
    total_recorrido = float(RecursoGlosaPrestador.objects.filter(empresa=empresa)
                            .aggregate(t=Sum("valor_recorrido"))["t"] or 0)
    em_recurso = GlosaRecebida.objects.filter(empresa=empresa, status="em_recurso").count()
    taxa_recuperacao = round(total_recuperado / total_recorrido * 100, 1) if total_recorrido else 0.0

    # top motivos de glosa (por código, somando valor)
    motivos = {}
    for g in GlosaRecebida.objects.filter(empresa=empresa).values_list("itens", flat=True):
        for it in (g or []):
            cod = (it.get("codigo_glosa") or "sem_codigo").strip() or "sem_codigo"
            motivos[cod] = motivos.get(cod, 0.0) + float(it.get("valor_glosado", 0) or 0)
    top_motivos = sorted(
        [{"codigo_glosa": k, "valor": round(v, 2)} for k, v in motivos.items()],
        key=lambda x: x["valor"], reverse=True)[:5]

    return JsonResponse({
        "glosas": glosas,
        "kpis": {
            "total_glosado": round(total_glosado, 2),
            "total_recuperado": round(total_recuperado, 2),
            "total_recorrido": round(total_recorrido, 2),
            "taxa_recuperacao": taxa_recuperacao,
            "glosas_em_recurso": em_recurso,
            "top_motivos": top_motivos,
        },
    })


# ── Sugerir recurso (preview de mérito por IA, sem gravar) ────────────────────

@api_requer_feature("hospital.anti_glosa")
@api_requer_permissao_modulo("hospital.operacional")
@require_http_methods(["GET"])
def api_glosa_sugerir_recurso(request, glosa_id):
    empresa = _empresa_hospital(request)
    if isinstance(empresa, JsonResponse):
        return empresa
    try:
        glosa = GlosaRecebida.objects.get(pk=glosa_id, empresa=empresa)
    except GlosaRecebida.DoesNotExist:
        return JsonResponse({"erro": "Glosa não encontrada"}, status=404)
    codigo = request.GET.get("codigo_glosa") or _codigo_glosa_predominante(glosa)
    texto = _sugerir_texto_recurso(codigo)
    score, parecer = _ia_merito_recurso(codigo, texto)
    return JsonResponse({
        "codigo_glosa": codigo,
        "texto_sugerido": texto,
        "ia_merito_score": score,
        "ia_parecer": parecer,
        "valor_sugerido": float(glosa.valor_glosado_total),
    })


def _codigo_glosa_predominante(glosa):
    """Código de glosa com maior valor entre os itens (para pré-selecionar o recurso)."""
    por_codigo = {}
    for it in (glosa.itens or []):
        cod = (it.get("codigo_glosa") or "").strip()
        if cod:
            por_codigo[cod] = por_codigo.get(cod, 0.0) + float(it.get("valor_glosado", 0) or 0)
    return max(por_codigo, key=por_codigo.get) if por_codigo else ""


# ── Abrir recurso (grava, com IA de mérito) ──────────────────────────────────

@api_requer_feature("hospital.anti_glosa")
@api_requer_permissao_modulo("hospital.operacional")
@csrf_exempt
@require_http_methods(["POST"])
def api_glosa_recurso_abrir(request, glosa_id):
    empresa = _empresa_hospital(request)
    if isinstance(empresa, JsonResponse):
        return empresa
    try:
        glosa = GlosaRecebida.objects.get(pk=glosa_id, empresa=empresa)
    except GlosaRecebida.DoesNotExist:
        return JsonResponse({"erro": "Glosa não encontrada"}, status=404)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    codigo = str(data.get("codigo_glosa", "") or "").strip() or _codigo_glosa_predominante(glosa)
    justificativa = str(data.get("justificativa", "") or "").strip() or _sugerir_texto_recurso(codigo)
    valor = _dec(data.get("valor_recorrido", glosa.valor_glosado_total))
    score, parecer = _ia_merito_recurso(codigo, justificativa)

    recurso = RecursoGlosaPrestador.objects.create(
        empresa=empresa, glosa=glosa,
        codigo_glosa=codigo, justificativa=justificativa,
        ia_merito_score=score, ia_parecer=parecer,
        valor_recorrido=valor, status="aberto",
    )
    if glosa.status == "recebida":
        glosa.status = "em_recurso"
        glosa.save(update_fields=["status"])

    return JsonResponse({"ok": True, "recurso": _recurso_dict(recurso)}, status=201)


# ── Atualizar status do recurso (desfecho da operadora) ──────────────────────

@api_requer_feature("hospital.anti_glosa")
@api_requer_permissao_modulo("hospital.operacional")
@csrf_exempt
@require_http_methods(["POST"])
def api_recurso_status(request, recurso_id):
    empresa = _empresa_hospital(request)
    if isinstance(empresa, JsonResponse):
        return empresa
    try:
        recurso = RecursoGlosaPrestador.objects.select_related("glosa__guia").get(pk=recurso_id, empresa=empresa)
    except RecursoGlosaPrestador.DoesNotExist:
        return JsonResponse({"erro": "Recurso não encontrado"}, status=404)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    validos = [s[0] for s in RecursoGlosaPrestador.STATUS_CHOICES]
    novo = data.get("status", recurso.status)
    if novo not in validos:
        return JsonResponse({"erro": f"status inválido. Opções: {validos}"}, status=400)

    recurso.status = novo
    if "valor_recuperado" in data:
        recurso.valor_recuperado = _dec(data["valor_recuperado"])
    if "protocolo" in data:
        recurso.protocolo = str(data["protocolo"] or "")
    if "resposta_operadora" in data:
        recurso.resposta_operadora = str(data["resposta_operadora"] or "")

    # deferimento total sem valor informado → recupera o valor recorrido
    if novo == "deferido" and recurso.valor_recuperado == 0:
        recurso.valor_recuperado = recurso.valor_recorrido
    recurso.save()

    # desfecho encerra a glosa e devolve o valor recuperado ao aprovado da guia
    if novo in ("deferido", "parcial", "indeferido"):
        glosa = recurso.glosa
        glosa.status = "encerrada"
        glosa.save(update_fields=["status"])
        if recurso.valor_recuperado > 0 and glosa.guia_id:
            guia = glosa.guia
            guia.valor_aprovado = _dec(guia.valor_aprovado) + recurso.valor_recuperado
            if guia.status == "glosada":
                guia.status = "paga" if _dec(guia.valor_aprovado) >= _dec(guia.valor_apresentado) else guia.status
            guia.save(update_fields=["valor_aprovado", "status"])

    return JsonResponse({"ok": True, "recurso": _recurso_dict(recurso)})
