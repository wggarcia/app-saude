"""
Hospital — Faturamento TISS (ANS)
  • GuiaTISS — guias TISS, valor apresentado vs aprovado, glosa, XML stub
"""
import json
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q, Sum
from django.http import JsonResponse, HttpResponse
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
from .models import GuiaTISS
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

def _guia_to_dict(g):
    valor_glosa = float(g.valor_apresentado) - float(g.valor_aprovado)
    perc_glosa = (
        round(valor_glosa / float(g.valor_apresentado) * 100, 1)
        if g.valor_apresentado else 0
    )
    return {
        "id": g.id,
        "numero_guia": g.numero_guia,
        "tipo": g.tipo,
        "tipo_label": dict(GuiaTISS.TIPO_CHOICES).get(g.tipo, g.tipo),
        "operadora_codigo": g.operadora_codigo,
        "operadora_nome": g.operadora_nome,
        "beneficiario_nome": g.beneficiario_nome,
        "beneficiario_carteirinha": g.beneficiario_carteirinha,
        "cid10": g.cid10,
        "procedimentos": g.procedimentos,
        "valor_apresentado": float(g.valor_apresentado),
        "valor_aprovado": float(g.valor_aprovado),
        "valor_glosa": round(valor_glosa, 2),
        "perc_glosa": perc_glosa,
        "status": g.status,
        "status_label": dict(GuiaTISS.STATUS_CHOICES).get(g.status, g.status),
        "data_autorizacao": g.data_autorizacao.strftime("%d/%m/%Y %H:%M") if g.data_autorizacao else None,
        "criado_em": g.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
def hospital_tiss_page(request):
    return render(request, "hospital_faturamento_tiss.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Lista guias ─────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_tiss_guias(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = GuiaTISS.objects.filter(empresa=empresa)

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    tipo = request.GET.get("tipo")
    if tipo:
        qs = qs.filter(tipo=tipo)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(beneficiario_nome__icontains=q) |
            Q(numero_guia__icontains=q) |
            Q(operadora_nome__icontains=q)
        )

    data_de = request.GET.get("data_de")
    data_ate = request.GET.get("data_ate")
    if data_de:
        qs = qs.filter(criado_em__date__gte=data_de)
    if data_ate:
        qs = qs.filter(criado_em__date__lte=data_ate)

    qs = qs.order_by("-criado_em")[:100]
    return JsonResponse({"guias": [_guia_to_dict(g) for g in qs]})


# ─── API: Nova guia ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_tiss_nova_guia(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    beneficiario_nome = (data.get("beneficiario_nome") or "").strip()
    if not beneficiario_nome:
        return JsonResponse({"erro": "beneficiario_nome é obrigatório"}, status=400)

    tipos_validos = [t[0] for t in GuiaTISS.TIPO_CHOICES]
    tipo = data.get("tipo", "consulta")
    if tipo not in tipos_validos:
        return JsonResponse({"erro": f"tipo inválido. Opções: {tipos_validos}"}, status=400)

    try:
        valor_apresentado = Decimal(str(data.get("valor_apresentado", 0)))
    except InvalidOperation:
        return JsonResponse({"erro": "valor_apresentado inválido"}, status=400)

    procedimentos = data.get("procedimentos", [])
    if not isinstance(procedimentos, list):
        procedimentos = []

    guia = GuiaTISS.objects.create(
        empresa=empresa,
        numero_guia=data.get("numero_guia", ""),
        tipo=tipo,
        operadora_codigo=data.get("operadora_codigo", ""),
        operadora_nome=data.get("operadora_nome", ""),
        beneficiario_nome=beneficiario_nome,
        beneficiario_carteirinha=data.get("beneficiario_carteirinha", ""),
        cid10=data.get("cid10", ""),
        procedimentos=procedimentos,
        valor_apresentado=valor_apresentado,
        valor_aprovado=Decimal("0"),
        status="elaborada",
    )
    return JsonResponse({"ok": True, "guia": _guia_to_dict(guia)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_tiss(request):
    if request.method == "POST":
        return api_tiss_nova_guia(request)
    return api_tiss_guias(request)


# ─── API: Atualizar status ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_tiss_atualizar_status(request, guia_id):
    empresa = _empresa(request)
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

    status_validos = [s[0] for s in GuiaTISS.STATUS_CHOICES]
    novo_status = data.get("status", guia.status)
    if novo_status not in status_validos:
        return JsonResponse({"erro": f"status inválido. Opções: {status_validos}"}, status=400)

    guia.status = novo_status

    if "valor_aprovado" in data:
        try:
            guia.valor_aprovado = Decimal(str(data["valor_aprovado"]))
        except InvalidOperation:
            return JsonResponse({"erro": "valor_aprovado inválido"}, status=400)

    if "valor_apresentado" in data:
        try:
            guia.valor_apresentado = Decimal(str(data["valor_apresentado"]))
        except InvalidOperation:
            return JsonResponse({"erro": "valor_apresentado inválido"}, status=400)

    if novo_status == "enviada" and not guia.data_autorizacao:
        guia.data_autorizacao = timezone.now()

    guia.save()
    return JsonResponse({"ok": True, "guia": _guia_to_dict(guia)})


# ─── API: KPIs TISS ───────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_tiss_kpis(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = timezone.now().date()
    mes_inicio = hoje.replace(day=1)

    qs_mes = GuiaTISS.objects.filter(empresa=empresa, criado_em__date__gte=mes_inicio)
    qs_all = GuiaTISS.objects.filter(empresa=empresa)

    agg_mes = qs_mes.aggregate(
        apresentado=Sum("valor_apresentado"),
        aprovado=Sum("valor_aprovado"),
    )
    apresentado_mes = float(agg_mes["apresentado"] or 0)
    aprovado_mes = float(agg_mes["aprovado"] or 0)
    glosa_mes = round(apresentado_mes - aprovado_mes, 2)
    perc_glosa = round(glosa_mes / apresentado_mes * 100, 1) if apresentado_mes else 0

    elaboradas = qs_all.filter(status="elaborada").count()
    enviadas = qs_all.filter(status="enviada").count()
    glosadas = qs_all.filter(status="glosada").count()
    pagas = qs_all.filter(status="paga").count()

    return JsonResponse({
        "apresentado_mes": apresentado_mes,
        "aprovado_mes": aprovado_mes,
        "glosa_mes": glosa_mes,
        "perc_glosa": perc_glosa,
        "elaboradas": elaboradas,
        "enviadas": enviadas,
        "glosadas": glosadas,
        "pagas": pagas,
    })


# ─── API: Gerar XML TISS (stub) ───────────────────────────────────────────────

@require_http_methods(["GET"])
def api_tiss_gerar_xml(request, guia_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        guia = GuiaTISS.objects.get(pk=guia_id, empresa=empresa)
    except GuiaTISS.DoesNotExist:
        return JsonResponse({"erro": "Guia não encontrada"}, status=404)

    # Build a minimal TISS 3.05 XML stub
    root = ET.Element("ans:mensagemTISS")
    root.set("xmlns:ans", "http://www.ans.gov.br/padroes/tiss/schemas")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

    cabecalho = ET.SubElement(root, "ans:cabecalho")
    ET.SubElement(cabecalho, "ans:identificacaoTransacao").text = str(guia.id)
    ET.SubElement(cabecalho, "ans:dataRegistroTransacao").text = guia.criado_em.strftime("%Y-%m-%d")
    ET.SubElement(cabecalho, "ans:tipoTransacao").text = guia.tipo.upper()

    prestador = ET.SubElement(cabecalho, "ans:prestadorSolicitante")
    ET.SubElement(prestador, "ans:codigoPrestadorNaOperadora").text = getattr(empresa, "codigo_ans", "")
    ET.SubElement(prestador, "ans:nomeContratado").text = getattr(empresa, "nome", "")

    operadora = ET.SubElement(cabecalho, "ans:operadoraSaude")
    ET.SubElement(operadora, "ans:registro").text = guia.operadora_codigo
    ET.SubElement(operadora, "ans:nomeFantasia").text = guia.operadora_nome

    corpo = ET.SubElement(root, "ans:prestadorParaOperadora")
    guia_elem = ET.SubElement(corpo, "ans:guia")
    ET.SubElement(guia_elem, "ans:numeroGuiaPrestador").text = guia.numero_guia or str(guia.id)
    ET.SubElement(guia_elem, "ans:nomeBeneficiario").text = guia.beneficiario_nome
    ET.SubElement(guia_elem, "ans:numeroCNS").text = guia.beneficiario_carteirinha
    ET.SubElement(guia_elem, "ans:codigoCID").text = guia.cid10
    ET.SubElement(guia_elem, "ans:valorApresentado").text = str(guia.valor_apresentado)
    ET.SubElement(guia_elem, "ans:valorAprovado").text = str(guia.valor_aprovado)

    for proc in (guia.procedimentos or []):
        pe = ET.SubElement(guia_elem, "ans:procedimento")
        ET.SubElement(pe, "ans:codigoTabela").text = str(proc.get("tabela", "22"))
        ET.SubElement(pe, "ans:codigoProcedimento").text = str(proc.get("codigo", ""))
        ET.SubElement(pe, "ans:descricao").text = str(proc.get("descricao", ""))
        ET.SubElement(pe, "ans:quantidade").text = str(proc.get("quantidade", 1))
        ET.SubElement(pe, "ans:valorUnitario").text = str(proc.get("valor_unitario", 0))

    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
    xml_out = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    # Persist XML on guia
    guia.xml_tiss = xml_out
    guia.save(update_fields=["xml_tiss"])

    response = HttpResponse(xml_out, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="guia_tiss_{guia.id}.xml"'
    return response
