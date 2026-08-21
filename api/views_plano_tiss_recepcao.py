"""
views_plano_tiss_recepcao.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TISS OPERADORA — recepção de lote de guias (padrão ANS TISS 3.05.00) enviado
pelo prestador, análise automática de conta médica com GLOSA + IA de risco, e
geração do Demonstrativo de Análise de Conta (retorno ao prestador).

Lado OPERADORA (recebe). O gerador de XML do lado prestador está em
api/views_hospital_tiss.py — juntos fecham o ciclo TISS ponta a ponta.

Diferencial vs. legado (Tasy/TOTVS/SOC): a glosa não é só regra fixa — tem uma
IA de risco (0-100) que prioriza para a auditoria médica só o que realmente
importa, com parecer explicável. Regra + IA, não uma coisa OU outra.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    contexto_navegacao_setorial, requer_operacao_page, requer_permissao_modulo,
    requer_setor,
)
from .models import ItemContaTISS, LoteTISSRecebido, PrestadorPlanoSaude
from .views_dashboard import _empresa_autenticada
from .views_plano_saude import _ps_auth

_NS = "http://www.ans.gov.br/padroes/tiss/schemas"
_NSMAP = {"ans": _NS}


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _txt(el, path, default=""):
    """find com namespace ans:, tolerante a ausência."""
    if el is None:
        return default
    found = el.find(path, _NSMAP)
    return (found.text or default).strip() if (found is not None and found.text) else default


# ── Parser: lê o lote TISS recebido e cria LoteTISSRecebido + itens ──────────
def importar_lote_tiss(xml_str: str, empresa) -> LoteTISSRecebido:
    root = ET.fromstring(xml_str)

    cab = root.find("ans:cabecalho", _NSMAP)
    id_prest = cab.find("ans:origem/ans:identificacaoPrestador", _NSMAP) if cab is not None else None
    prest_codigo = _txt(id_prest, "ans:codigoPrestadorNaOperadora")
    prest_nome = _txt(id_prest, "ans:nomeContratado")
    prest_cnes = _txt(id_prest, "ans:CNES")
    seq = _txt(cab.find("ans:identificacaoTransacao", _NSMAP) if cab is not None else None,
               "ans:sequencialTransacao")
    versao = _txt(cab.find("ans:identificacaoTransacao", _NSMAP) if cab is not None else None,
                  "ans:versaoLeiaute", "3.05.00")

    # hash de integridade declarado no epílogo
    hash_declarado = _txt(root.find("ans:epilogo", _NSMAP), "ans:hash")

    corpo = root.find("ans:prestadorParaOperadora", _NSMAP)
    lote_el = None
    if corpo is not None:
        lote_el = corpo.find("ans:loteGuiasSP", _NSMAP)
        if lote_el is None:
            lote_el = corpo.find("ans:loteGuiasInternacao", _NSMAP)
    numero_lote = _txt(lote_el, "ans:numeroLote", seq)
    guia_el = None
    if lote_el is not None:
        guia_el = lote_el.find("ans:guiaSP", _NSMAP)
        if guia_el is None:
            guia_el = lote_el.find("ans:guiaInternacao", _NSMAP)

    ben = guia_el.find("ans:dadosBeneficiario", _NSMAP) if guia_el is not None else None
    carteirinha = _txt(ben, "ans:numeroCarteira") or _txt(ben, "ans:numeroCNS")
    ben_nome = _txt(ben, "ans:nomeBeneficiario")
    guia_num = _txt(guia_el.find("ans:cabecalhoGuia", _NSMAP) if guia_el is not None else None,
                    "ans:nrGuiaPrestador")
    cid = _txt(guia_el.find("ans:dadosSolicitacaoExame", _NSMAP) if guia_el is not None else None,
               "ans:codigoCID10")

    # casa o prestador pelo código na operadora (ou CNES) dentro do tenant
    prestador = (PrestadorPlanoSaude.objects.filter(empresa=empresa, codigo_rede=prest_codigo).first()
                 or (PrestadorPlanoSaude.objects.filter(empresa=empresa, registro_cnes=prest_cnes).first()
                     if prest_cnes else None))

    with transaction.atomic():
        lote = LoteTISSRecebido.objects.create(
            empresa=empresa, prestador=prestador, numero_lote=numero_lote,
            prestador_codigo=prest_codigo, prestador_nome=prest_nome, prestador_cnes=prest_cnes,
            beneficiario_carteirinha=carteirinha, beneficiario_nome=ben_nome,
            guia_numero=guia_num, cid10=cid, versao_tiss=versao,
            hash_tiss=hash_declarado, xml_original=xml_str, status="recebido",
        )
        # procedimentos executados
        atend = guia_el.find("ans:dadosAtendimento", _NSMAP) if guia_el is not None else None
        procs = atend.find("ans:procedimentosExecutados", _NSMAP) if atend is not None else None
        total = Decimal("0.00")
        if procs is not None:
            for i, pe in enumerate(procs.findall("ans:procedimentoExecutado", _NSMAP), 1):
                qtd = _dec(_txt(pe, "ans:quantidadeExecutada", "1"))
                vunit = _dec(_txt(pe, "ans:valorUnitario", "0"))
                vtot = _dec(_txt(pe, "ans:valorTotal", "0")) or (qtd * vunit)
                total += vtot
                ItemContaTISS.objects.create(
                    lote=lote, sequencial=int(_txt(pe, "ans:sequencialItem", str(i)) or i),
                    codigo_tabela=_txt(pe, "ans:codigoTabela"),
                    codigo_procedimento=_txt(pe, "ans:codigoProcedimento"),
                    descricao=_txt(pe, "ans:descricaoProcedimento")[:250],
                    quantidade=qtd, valor_unitario=vunit, valor_apresentado=vtot,
                    valor_liberado=vtot,
                )
        lote.valor_apresentado = total
        lote.valor_liberado = total
        lote.save(update_fields=["valor_apresentado", "valor_liberado"])
    return lote


# ── Motor de glosa (regra) + IA de risco ─────────────────────────────────────
def _regras_glosa(item: ItemContaTISS, prestador, vistos_codigos: set):
    """Retorna (glosado, codigo_glosa, motivo, valor_glosado)."""
    # 1. prestador não credenciado / suspenso → glosa total
    if prestador and prestador.status not in ("credenciado", ""):
        return True, "1401", "Prestador não credenciado/ativo na data do atendimento", item.valor_apresentado
    # 2. procedimento sem código válido
    if not item.codigo_procedimento or not item.codigo_procedimento.strip("0"):
        return True, "1707", "Código de procedimento ausente ou inválido", item.valor_apresentado
    # 3. quantidade inválida
    if item.quantidade <= 0:
        return True, "1704", "Quantidade executada inválida", item.valor_apresentado
    # 4. duplicidade dentro do lote
    if item.codigo_procedimento in vistos_codigos:
        return True, "1403", "Procedimento em duplicidade no mesmo lote/atendimento", item.valor_apresentado
    return False, "", "", Decimal("0.00")


def processar_lote(lote: LoteTISSRecebido) -> LoteTISSRecebido:
    prestador = lote.prestador
    itens = list(lote.itens.all())
    vistos = set()
    total_glosa = Decimal("0.00")
    flags = 0
    for item in itens:
        glosado, cod, motivo, vglosa = _regras_glosa(item, prestador, vistos)
        vistos.add(item.codigo_procedimento)
        item.glosado = glosado
        item.codigo_glosa = cod
        item.motivo_glosa = motivo
        item.valor_glosado = _dec(vglosa)
        item.valor_liberado = item.valor_apresentado - item.valor_glosado
        item.save(update_fields=["glosado", "codigo_glosa", "motivo_glosa",
                                 "valor_glosado", "valor_liberado"])
        total_glosa += item.valor_glosado
        if glosado:
            flags += 1

    # ── IA de risco de glosa (0-100), explicável ─────────────────────────────
    # Combina: proporção de itens com flag, qualidade do prestador e ticket.
    prop_flag = (flags / len(itens)) if itens else 0
    qual = (prestador.score_qualidade if prestador else 60)
    ticket = float(lote.valor_apresentado)
    score = int(min(100, prop_flag * 60 + (100 - qual) * 0.3 + (10 if ticket > 5000 else 0)))
    if flags == 0 and score < 20:
        parecer = "Baixo risco — nenhuma inconsistência detectada; liberação recomendada."
    elif flags:
        parecer = (f"{flags} item(ns) com glosa automática. "
                   f"Prestador com score {qual}. Recomenda-se auditoria médica dos itens sinalizados.")
    else:
        parecer = (f"Sem glosa de regra, mas risco {score}/100 pelo perfil do prestador/ticket — "
                   "amostragem de auditoria sugerida.")

    lote.valor_glosado = _dec(total_glosa)
    lote.valor_liberado = lote.valor_apresentado - lote.valor_glosado
    lote.ia_score_glosa = score
    lote.ia_parecer = parecer
    lote.status = "processado"
    lote.processado_em = timezone.now()
    lote.save(update_fields=["valor_glosado", "valor_liberado", "ia_score_glosa",
                             "ia_parecer", "status", "processado_em"])
    return lote


# ── Demonstrativo de Análise de Conta (retorno TISS ao prestador) ────────────
def _el(parent, tag, text=None):
    e = ET.SubElement(parent, f"ans:{tag}")
    if text is not None:
        e.text = str(text)
    return e


def gerar_demonstrativo_retorno(lote: LoteTISSRecebido) -> str:
    agora = timezone.now()
    root = ET.Element("ans:mensagemTISS")
    root.set("xmlns:ans", _NS)
    cab = _el(root, "cabecalho")
    idt = _el(cab, "identificacaoTransacao")
    _el(idt, "tipoTransacao", "DEMONSTRATIVO_ANALISE_CONTA")
    _el(idt, "sequencialTransacao", str(lote.pk).zfill(10))
    _el(idt, "dataRegistroTransacao", agora.strftime("%Y-%m-%d"))
    _el(idt, "horaRegistroTransacao", agora.strftime("%H:%M:%S"))
    _el(idt, "versaoLeiaute", lote.versao_tiss)

    corpo = _el(root, "operadoraParaPrestador")
    dem = _el(corpo, "demonstrativosAnaliseConta")
    _el(dem, "numeroLote", lote.numero_lote)
    _el(dem, "codigoPrestadorNaOperadora", lote.prestador_codigo)
    _el(dem, "nomeContratado", lote.prestador_nome)
    _el(dem, "nrGuia", lote.guia_numero)
    _el(dem, "beneficiario", lote.beneficiario_nome)
    for item in lote.itens.all():
        it = _el(dem, "itemAnalise")
        _el(it, "sequencialItem", str(item.sequencial))
        _el(it, "codigoProcedimento", item.codigo_procedimento)
        _el(it, "valorApresentado", f"{item.valor_apresentado:.2f}")
        _el(it, "valorGlosa", f"{item.valor_glosado:.2f}")
        _el(it, "valorLiberado", f"{item.valor_liberado:.2f}")
        if item.glosado:
            _el(it, "codigoGlosa", item.codigo_glosa)
            _el(it, "descricaoGlosa", item.motivo_glosa)
    tot = _el(dem, "valoresTotais")
    _el(tot, "valorApresentadoLote", f"{lote.valor_apresentado:.2f}")
    _el(tot, "valorGlosaLote", f"{lote.valor_glosado:.2f}")
    _el(tot, "valorLiberadoLote", f"{lote.valor_liberado:.2f}")

    conteudo = ET.tostring(root, encoding="unicode")
    sha1 = hashlib.sha1(conteudo.encode("utf-8")).hexdigest().upper()
    _el(_el(root, "epilogo"), "hash", sha1)
    xml_raw = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_raw}'


# ── APIs (autenticadas pelo dono/tenant via _ps_auth) ────────────────────────
def _lote_dict(l: LoteTISSRecebido) -> dict:
    return {
        "id": l.id, "numero_lote": l.numero_lote, "prestador": l.prestador_nome,
        "prestador_codigo": l.prestador_codigo, "beneficiario": l.beneficiario_nome,
        "guia": l.guia_numero, "status": l.status,
        "valor_apresentado": float(l.valor_apresentado), "valor_glosado": float(l.valor_glosado),
        "valor_liberado": float(l.valor_liberado), "ia_score_glosa": l.ia_score_glosa,
        "ia_parecer": l.ia_parecer, "itens": l.itens.count(),
        "recebido_em": l.recebido_em.isoformat(),
    }


@csrf_exempt
@require_http_methods(["POST"])
def api_tiss_recepcao_importar(request):
    """POST /api/plano-saude/tiss/recepcao/importar/ — corpo = XML TISS (text) do prestador."""
    empresa, err = _ps_auth(request)
    if err:
        return err
    xml_str = request.body.decode("utf-8", "ignore") if request.body else ""
    if "mensagemTISS" not in xml_str:
        return JsonResponse({"erro": "XML TISS inválido ou vazio"}, status=400)
    try:
        lote = importar_lote_tiss(xml_str, empresa)
        processar_lote(lote)
    except ET.ParseError as e:
        return JsonResponse({"erro": f"XML mal formado: {e}"}, status=400)
    except Exception as e:  # noqa: BLE001
        return JsonResponse({"erro": f"Falha ao importar: {e}"}, status=500)
    return JsonResponse({"ok": True, "lote": _lote_dict(lote)})


@require_http_methods(["GET"])
def api_tiss_recepcao_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    lotes = LoteTISSRecebido.objects.filter(empresa=empresa)[:200]
    return JsonResponse({"lotes": [_lote_dict(l) for l in lotes]})


@require_http_methods(["GET"])
def api_tiss_recepcao_detalhe(request, lote_id: int):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        lote = LoteTISSRecebido.objects.get(id=lote_id, empresa=empresa)
    except LoteTISSRecebido.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)
    itens = [{
        "sequencial": it.sequencial, "codigo": it.codigo_procedimento, "descricao": it.descricao,
        "quantidade": float(it.quantidade), "valor_apresentado": float(it.valor_apresentado),
        "valor_glosado": float(it.valor_glosado), "valor_liberado": float(it.valor_liberado),
        "glosado": it.glosado, "codigo_glosa": it.codigo_glosa, "motivo_glosa": it.motivo_glosa,
    } for it in lote.itens.all()]
    return JsonResponse({"lote": _lote_dict(lote), "itens": itens})


@require_http_methods(["GET"])
def api_tiss_recepcao_retorno(request, lote_id: int):
    """Baixa o Demonstrativo de Análise de Conta (XML de retorno ao prestador)."""
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        lote = LoteTISSRecebido.objects.get(id=lote_id, empresa=empresa)
    except LoteTISSRecebido.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)
    xml_out = gerar_demonstrativo_retorno(lote)
    if lote.status != "retornado":
        lote.xml_retorno = xml_out
        lote.status = "retornado"
        lote.save(update_fields=["xml_retorno", "status"])
    resp = HttpResponse(xml_out, content_type="application/xml; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="demonstrativo_lote_{lote.id}.xml"'
    return resp


# ── page (tela no dashboard da operadora) ────────────────────────────────────
@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.rede_credenciada")
def plano_tiss_recepcao_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_tiss_recepcao.html", ctx)
