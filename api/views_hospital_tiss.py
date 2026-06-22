"""
Hospital — Faturamento TISS (ANS)
  • GuiaTISS — guias TISS, valor apresentado vs aprovado, glosa
  • XML TISS 3.05.00 real (conforme padrão ANS — cabecalho, corpo, epilogo SHA-1)
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
    api_requer_feature,
    api_requer_gerencia,
    get_setor,
    principal_pode_operacao_setorial,
    requer_setor,
    requer_feature_pacote,
    requer_operacao_page,
    requer_permissao_modulo,
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
@requer_feature_pacote("hospital.tiss", "Faturamento TISS")
@requer_operacao_page
@requer_permissao_modulo("hospital.operacional")
def hospital_tiss_page(request):
    return render(request, "hospital_faturamento_tiss.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Lista guias ─────────────────────────────────────────────────────────

@api_requer_feature("hospital.tiss")
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

@api_requer_feature("hospital.tiss")
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


@api_requer_feature("hospital.tiss")
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_tiss(request):
    if request.method == "POST":
        return api_tiss_nova_guia(request)
    return api_tiss_guias(request)


# ─── API: Atualizar status ────────────────────────────────────────────────────

@api_requer_feature("hospital.tiss")
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

@api_requer_feature("hospital.tiss")
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


# ─── TISS 3.05.00 — Gerador XML completo ────────────────────────────────────

_NS_TISS = "http://www.ans.gov.br/padroes/tiss/schemas"
_VERSAO_TISS = "3.05.00"

# Mapa tipo da guia → tipoTransacao TISS
_TIPO_TRANSACAO = {
    "consulta":   "SOLICITACAO_PROCEDIMENTO_AMBULATORIAL",
    "sadt":       "SOLICITACAO_PROCEDIMENTO_AMBULATORIAL",
    "sp_sadt":    "SOLICITACAO_PROCEDIMENTO_AMBULATORIAL",
    "internacao": "SOLICITACAO_AUTORIZACAO_INTERNACAO",
    "resumo":     "ENVIO_LOTE_GUIAS",
}


def _tiss_elem(parent, tag, text=None):
    el = ET.SubElement(parent, f"ans:{tag}")
    if text is not None:
        el.text = str(text)
    return el


def _fmt_valor(v):
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "0.00"


def gerar_xml_tiss_3_05(guia: GuiaTISS, empresa) -> str:
    """
    Gera XML TISS 3.05.00 completo conforme Resolução Normativa ANS nº 305/2012
    e suas atualizações (Componente Organizacional — leiaute TISS 3.05.00).

    Estrutura:
      mensagemTISS
        cabecalho
          identificacaoTransacao (tipoTransacao, sequencialTransacao, dataHora, versao)
          origem (identificacaoPrestador)
          destino (registroANS)
          Padrao
        prestadorParaOperadora
          loteGuiasSP       (para ambulatorial/SP-SADT/consulta)
          ou
          loteGuiasInternacao (para internação)
        epilogo
          hash (SHA-1 do cabecalho+corpo)
    """
    import hashlib
    from datetime import date, datetime

    agora = datetime.now()
    data_str = agora.strftime("%Y-%m-%d")
    hora_str = agora.strftime("%H:%M:%S")
    seq = str(guia.pk).zfill(10)

    tipo_transacao = _TIPO_TRANSACAO.get(guia.tipo, "SOLICITACAO_PROCEDIMENTO_AMBULATORIAL")
    nome_empresa = (getattr(empresa, "nome", "") or "")[:80]
    codigo_prestador = (getattr(empresa, "codigo_prestador_tiss", "") or getattr(empresa, "cnpj", "") or "")
    cnes_prestador = (getattr(empresa, "cnes", "") or "")

    # ── Root ─────────────────────────────────────────────────────────────────
    root = ET.Element("ans:mensagemTISS")
    root.set("xmlns:ans", _NS_TISS)
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:schemaLocation", f"{_NS_TISS} tissV3_05_00.xsd")

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    cab = _tiss_elem(root, "cabecalho")
    id_trans = _tiss_elem(cab, "identificacaoTransacao")
    _tiss_elem(id_trans, "tipoTransacao", tipo_transacao)
    _tiss_elem(id_trans, "sequencialTransacao", seq)
    _tiss_elem(id_trans, "dataRegistroTransacao", data_str)
    _tiss_elem(id_trans, "horaRegistroTransacao", hora_str)
    _tiss_elem(id_trans, "versaoLeiaute", _VERSAO_TISS)

    origem = _tiss_elem(cab, "origem")
    id_prest = _tiss_elem(origem, "identificacaoPrestador")
    _tiss_elem(id_prest, "codigoPrestadorNaOperadora", codigo_prestador)
    _tiss_elem(id_prest, "nomeContratado", nome_empresa)
    if cnes_prestador:
        _tiss_elem(id_prest, "CNES", cnes_prestador)

    destino = _tiss_elem(cab, "destino")
    _tiss_elem(destino, "registroANS", guia.operadora_codigo or "000000")
    _tiss_elem(destino, "nomeOperadora", guia.operadora_nome or "")

    _tiss_elem(cab, "Padrao", "TISS")

    # ── Corpo ─────────────────────────────────────────────────────────────────
    corpo = _tiss_elem(root, "prestadorParaOperadora")

    if guia.tipo == "internacao":
        _gerar_guia_internacao(corpo, guia, codigo_prestador, nome_empresa, cnes_prestador, data_str)
    else:
        _gerar_guia_sp_sadt(corpo, guia, codigo_prestador, nome_empresa, cnes_prestador, data_str)

    # ── Epílogo com hash SHA-1 ────────────────────────────────────────────────
    # Hash calculado sobre o conteúdo serializado até este ponto (cabecalho + corpo)
    conteudo_para_hash = ET.tostring(root, encoding="unicode")
    sha1 = hashlib.sha1(conteudo_para_hash.encode("utf-8")).hexdigest().upper()

    epilogo = _tiss_elem(root, "epilogo")
    _tiss_elem(epilogo, "hash", sha1)

    xml_raw = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_raw}'


def _gerar_guia_sp_sadt(corpo, guia, codigo_prestador, nome_empresa, cnes_prestador, data_str):
    """Guia SP/SADT para ambulatorial (consultas, exames, terapias)."""
    lote = _tiss_elem(corpo, "loteGuiasSP")
    _tiss_elem(lote, "numeroLote", str(guia.pk).zfill(10))

    g = _tiss_elem(lote, "guiaSP")

    # Cabeçalho da guia
    cab = _tiss_elem(g, "cabecalhoGuia")
    _tiss_elem(cab, "registroANS", guia.operadora_codigo or "000000")
    _tiss_elem(cab, "nrGuiaPrestador", guia.numero_guia or str(guia.pk))
    if guia.data_autorizacao:
        _tiss_elem(cab, "nrGuiaOperadora", guia.numero_guia or str(guia.pk))

    # Dados do beneficiário
    ben = _tiss_elem(g, "dadosBeneficiario")
    _tiss_elem(ben, "numeroCNS", guia.beneficiario_carteirinha or "")
    _tiss_elem(ben, "nomeBeneficiario", guia.beneficiario_nome[:70])
    _tiss_elem(ben, "numeroCarteira", guia.beneficiario_carteirinha or "")

    # Dados do solicitante
    sol = _tiss_elem(g, "dadosSolicitante")
    cont = _tiss_elem(sol, "contratadoSolicitante")
    _tiss_elem(cont, "codigoPrestadorNaOperadora", codigo_prestador)
    _tiss_elem(cont, "nomeContratado", nome_empresa)
    if cnes_prestador:
        _tiss_elem(cont, "CNES", cnes_prestador)
    _tiss_elem(sol, "dataSolicitacao", data_str)

    # Dados da solicitação clínica
    sol_clin = _tiss_elem(g, "dadosSolicitacaoExame")
    _tiss_elem(sol_clin, "caraterAtendimento", "01")  # 01=Eletivo
    if guia.cid10:
        _tiss_elem(sol_clin, "codigoCID10", guia.cid10[:4])
    _tiss_elem(sol_clin, "indicacaoAcidente", "9")  # 9=Não acidente

    # Procedimentos solicitados
    procs_sol = _tiss_elem(sol_clin, "procedimentosSolicitados")
    for i, proc in enumerate((guia.procedimentos or []), 1):
        ps = _tiss_elem(procs_sol, "procedimentoSolicitado")
        _tiss_elem(ps, "codigoTabela", str(proc.get("tabela", "22")))
        _tiss_elem(ps, "codigoProcedimento", str(proc.get("codigo", "0")))
        _tiss_elem(ps, "descricaoProcedimento", str(proc.get("descricao", ""))[:200])
        _tiss_elem(ps, "quantidadeSolicitada", str(proc.get("quantidade", 1)))

    # Dados de atendimento (execução)
    atend = _tiss_elem(g, "dadosAtendimento")
    _tiss_elem(atend, "codigoTransacao", "1")
    _tiss_elem(atend, "tipoAtendimento", "01")  # 01=Consulta/SADT
    _tiss_elem(atend, "indicadorAcidente", "9")
    _tiss_elem(atend, "dataInicioFaturamento", data_str)
    _tiss_elem(atend, "dataFimFaturamento", data_str)
    _tiss_elem(atend, "tipoSaida", "3")  # 3=Alta

    procs_exec = _tiss_elem(atend, "procedimentosExecutados")
    valor_total = 0.0
    for i, proc in enumerate((guia.procedimentos or []), 1):
        pe = _tiss_elem(procs_exec, "procedimentoExecutado")
        _tiss_elem(pe, "sequencialItem", str(i))
        _tiss_elem(pe, "codigoTabela", str(proc.get("tabela", "22")))
        _tiss_elem(pe, "codigoProcedimento", str(proc.get("codigo", "0")))
        _tiss_elem(pe, "descricaoProcedimento", str(proc.get("descricao", ""))[:200])
        qtd = int(proc.get("quantidade", 1))
        val_unit = float(proc.get("valor_unitario", 0))
        val_total_item = qtd * val_unit
        _tiss_elem(pe, "quantidadeExecutada", str(qtd))
        _tiss_elem(pe, "valorUnitario", _fmt_valor(val_unit))
        _tiss_elem(pe, "valorTotal", _fmt_valor(val_total_item))
        valor_total += val_total_item

    # Usa valor_apresentado se existir; caso contrário usa soma dos procedimentos
    val_final = float(guia.valor_apresentado) if float(guia.valor_apresentado) > 0 else valor_total
    vt = _tiss_elem(g, "valorTotal")
    _tiss_elem(vt, "valorTotalGeral", _fmt_valor(val_final))


def _gerar_guia_internacao(corpo, guia, codigo_prestador, nome_empresa, cnes_prestador, data_str):
    """Guia de Internação (SOLICITACAO_AUTORIZACAO_INTERNACAO)."""
    lote = _tiss_elem(corpo, "loteGuiasInternacao")
    _tiss_elem(lote, "numeroLote", str(guia.pk).zfill(10))

    g = _tiss_elem(lote, "guiaInternacao")

    cab = _tiss_elem(g, "cabecalhoGuia")
    _tiss_elem(cab, "registroANS", guia.operadora_codigo or "000000")
    _tiss_elem(cab, "nrGuiaPrestador", guia.numero_guia or str(guia.pk))

    ben = _tiss_elem(g, "dadosBeneficiario")
    _tiss_elem(ben, "numeroCNS", guia.beneficiario_carteirinha or "")
    _tiss_elem(ben, "nomeBeneficiario", guia.beneficiario_nome[:70])
    _tiss_elem(ben, "numeroCarteira", guia.beneficiario_carteirinha or "")

    sol = _tiss_elem(g, "dadosSolicitante")
    cont = _tiss_elem(sol, "contratadoSolicitante")
    _tiss_elem(cont, "codigoPrestadorNaOperadora", codigo_prestador)
    _tiss_elem(cont, "nomeContratado", nome_empresa)
    if cnes_prestador:
        _tiss_elem(cont, "CNES", cnes_prestador)
    _tiss_elem(sol, "dataSolicitacao", data_str)

    dad_int = _tiss_elem(g, "dadosInternacao")
    _tiss_elem(dad_int, "caraterInternacao", "01")  # 01=Eletivo
    if guia.cid10:
        _tiss_elem(dad_int, "codigoCID10Principal", guia.cid10[:4])
    _tiss_elem(dad_int, "tipoInternacao", "01")  # 01=Clínica
    _tiss_elem(dad_int, "regimeInternacao", "01")  # 01=Enfermaria
    _tiss_elem(dad_int, "dataInicioFaturamento", data_str)

    procs = _tiss_elem(dad_int, "procedimentosSolicitados")
    for proc in (guia.procedimentos or []):
        ps = _tiss_elem(procs, "procedimentoSolicitado")
        _tiss_elem(ps, "codigoTabela", str(proc.get("tabela", "22")))
        _tiss_elem(ps, "codigoProcedimento", str(proc.get("codigo", "0")))
        _tiss_elem(ps, "descricaoProcedimento", str(proc.get("descricao", ""))[:200])
        _tiss_elem(ps, "quantidadeSolicitada", str(proc.get("quantidade", 1)))

    val_final = float(guia.valor_apresentado)
    vt = _tiss_elem(g, "valorTotal")
    _tiss_elem(vt, "valorTotalGeral", _fmt_valor(val_final))


# ─── API: Gerar XML TISS 3.05.00 ─────────────────────────────────────────────

@api_requer_feature("hospital.tiss")
@require_http_methods(["GET"])
def api_tiss_gerar_xml(request, guia_id):
    """
    Gera XML TISS 3.05.00 completo conforme Resolução Normativa ANS nº 305/2012.
    Suporta guias SP/SADT (ambulatorial), consultas e internações.
    GET /api/hospital/tiss/<guia_id>/xml/
    """
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        guia = GuiaTISS.objects.get(pk=guia_id, empresa=empresa)
    except GuiaTISS.DoesNotExist:
        return JsonResponse({"erro": "Guia não encontrada"}, status=404)

    xml_out = gerar_xml_tiss_3_05(guia, empresa)

    # Persiste XML na guia
    guia.xml_tiss = xml_out
    guia.save(update_fields=["xml_tiss"])

    response = HttpResponse(xml_out, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="TISS3_{guia.numero_guia or guia.id}.xml"'
    return response
