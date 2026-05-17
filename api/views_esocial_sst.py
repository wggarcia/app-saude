"""
eSocial SST — geração de XML, fila de transmissão e portal de compartilhamento de ASO.

Eventos suportados:
  S-2210  Comunicação de Acidente do Trabalho (CAT)
  S-2220  Monitoramento da Saúde do Trabalhador (ASO)
  S-2230  Afastamento Temporário
  S-2240  Condições Ambientais do Trabalho

Compartilhamento de ASO:
  Clínica médica gera link/token → empresa contratante acessa PDF/dados via portal público.
"""
import json
import secrets
import hashlib
from datetime import date, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import (
    ASOOcupacional, CATOcupacional, AfastamentoSST, FuncionarioSST,
    eSocialEventoSST, ASOCompartilhamento, ConfiguracaoSST, Empresa,
    PostoTrabalho, AgenteNocivoPostoTrabalho, FuncionarioPostoTrabalho,
)
from .views_dashboard import _empresa_autenticada


def _e(req):
    return _empresa_autenticada(req)


def _cfg(empresa):
    try:
        return empresa.configuracao_sst
    except ConfiguracaoSST.DoesNotExist:
        return None


def _cnpj_limpo(cnpj):
    return "".join(c for c in (cnpj or "") if c.isdigit())[:14]


def _cpf_limpo(cpf):
    return "".join(c for c in (cpf or "") if c.isdigit())[:11]


def _evento_id(tipo, cnpj, seq):
    return f"ID_{tipo.replace('-','')}_{_cnpj_limpo(cnpj)}_{date.today().strftime('%Y%m%d')}_{seq:05d}"


def _xml_str(root):
    raw = tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding=None)
    return "\n".join(pretty.split("\n")[1:])  # remove XML declaration line (added manually)


# ─── S-2210 — CAT ─────────────────────────────────────────────────────────────

def _gerar_xml_s2210(cat, cfg):
    cnpj = _cnpj_limpo(cfg.cnpj if cfg else "")
    cpf  = _cpf_limpo(cat.funcionario.cpf)
    seq  = cat.pk

    NS = "http://www.esocial.gov.br/schema/evt/evtCAT/v_S_01_03_00"
    root = Element("eSocial", xmlns=NS)

    evt = SubElement(root, "evtCAT", Id=_evento_id("EVTCAT", cnpj, seq))

    # ideEvento
    ide = SubElement(evt, "ideEvento")
    SubElement(ide, "indRetif").text = "1"
    SubElement(ide, "tpAmb").text = "1"       # 1=produção, 2=homologação
    SubElement(ide, "procEmi").text = "1"
    SubElement(ide, "verProc").text = "SolusCRT_1.0"

    # ideEmpregador
    emp = SubElement(evt, "ideEmpregador")
    SubElement(emp, "tpInsc").text = "1"      # 1=CNPJ
    SubElement(emp, "nrInsc").text = cnpj or "00000000000000"

    # ideVinculo
    vin = SubElement(evt, "ideVinculo")
    SubElement(vin, "cpfTrab").text = cpf or "00000000000"
    if cat.funcionario.matricula:
        SubElement(vin, "matricula").text = cat.funcionario.matricula

    # cat
    c = SubElement(evt, "cat")
    SubElement(c, "dtAcid").text = cat.data_acidente.strftime("%Y-%m-%d")
    tipo_map = {"tipico": "1", "trajeto": "2", "doenca": "3"}
    SubElement(c, "tpAcid").text = tipo_map.get(cat.tipo, "1")
    if cat.hora_acidente:
        SubElement(c, "hrAcid").text = cat.hora_acidente.strftime("%H:%M")
    SubElement(c, "tpCat").text = getattr(cat, "tp_cat", "1") or "1"
    SubElement(c, "indCatObito").text = "S" if cat.gravidade == "fatal" else "N"
    SubElement(c, "dscLesao").text = (cat.parte_corpo or "Não informado")[:200]
    SubElement(c, "dscCat").text = (cat.descricao or "")[:999]
    SubElement(c, "houveAfast").text = "S" if cat.houve_afastamento else "N"

    # localAcidente
    loc = SubElement(c, "localAcidente")
    SubElement(loc, "tpLocal").text = "1"
    SubElement(loc, "dscLocal").text = (cat.local_acidente or "Não informado")[:255]
    ilt = SubElement(loc, "ideLocalTrab")
    SubElement(ilt, "tpInsc").text = "1"
    SubElement(ilt, "nrInsc").text = cnpj or "00000000000000"

    # parteAtingida — usa código eSocial real do campo cod_parte_corpo
    pa = SubElement(c, "parteAtingida")
    SubElement(pa, "codParteAting").text = getattr(cat, "cod_parte_corpo", None) or "730"
    SubElement(pa, "lateralidade").text = getattr(cat, "lateralidade", None) or "9"

    # agenteCausador — usa código eSocial real do campo cod_agente_causador
    ag = SubElement(c, "agenteCausador")
    SubElement(ag, "codAgntCausador").text = getattr(cat, "cod_agente_causador", None) or "0099"

    # atestado
    at = SubElement(c, "atestado")
    SubElement(at, "dtAtendimento").text = cat.data_acidente.strftime("%Y-%m-%d")
    SubElement(at, "indInternacao").text = "S" if cat.gravidade in ("grave", "fatal") else "N"
    SubElement(at, "indAfast").text = "S" if cat.houve_afastamento else "N"
    if cat.cid:
        SubElement(at, "codCID").text = cat.cid[:4]
    em = SubElement(at, "emitente")
    SubElement(em, "nmEmit").text = cfg.nome_medico_coordenador or "Médico do Trabalho" if cfg else "Médico do Trabalho"
    ideOC = SubElement(em, "ideOC")
    SubElement(ideOC, "tpOC").text = "1"   # CRM
    SubElement(ideOC, "nrOC").text = cfg.crm_medico or "000000" if cfg else "000000"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _xml_str(root)


# ─── S-2220 — Monitoramento Saúde (ASO) ───────────────────────────────────────

def _gerar_xml_s2220(aso, cfg):
    cnpj = _cnpj_limpo(cfg.cnpj if cfg else "")
    cpf  = _cpf_limpo(aso.funcionario.cpf)
    seq  = aso.pk

    NS = "http://www.esocial.gov.br/schema/evt/evtMonit/v_S_01_03_00"
    root = Element("eSocial", xmlns=NS)

    evt = SubElement(root, "evtMonit", Id=_evento_id("EVTMONIT", cnpj, seq))

    ide = SubElement(evt, "ideEvento")
    SubElement(ide, "indRetif").text = "1"
    SubElement(ide, "tpAmb").text = "1"
    SubElement(ide, "procEmi").text = "1"
    SubElement(ide, "verProc").text = "SolusCRT_1.0"

    emp = SubElement(evt, "ideEmpregador")
    SubElement(emp, "tpInsc").text = "1"
    SubElement(emp, "nrInsc").text = cnpj or "00000000000000"

    vin = SubElement(evt, "ideVinculo")
    SubElement(vin, "cpfTrab").text = cpf or "00000000000"
    if aso.funcionario.matricula:
        SubElement(vin, "matricula").text = aso.funcionario.matricula

    ex = SubElement(evt, "exMedOcup")
    tipo_map = {
        "admissional": "1", "periodico": "2", "retorno_trabalho": "3",
        "mudanca_risco": "4", "demissional": "9",
    }
    SubElement(ex, "tpExameOcup").text = tipo_map.get(aso.tipo, "2")

    aso_el = SubElement(ex, "aso")
    SubElement(aso_el, "dtAso").text = aso.data_emissao.strftime("%Y-%m-%d")
    res_map = {"apto": "1", "inapto": "2", "apto_restricao": "3"}
    SubElement(aso_el, "resAso").text = res_map.get(aso.resultado, "1")

    # CID obrigatório quando inapto ou apto com restrição
    cid_inapto = getattr(aso, "cid_inapto", "") or ""
    if aso.resultado in ("inapto", "apto_restricao") and cid_inapto:
        SubElement(aso_el, "codCID").text = cid_inapto[:4]

    med = SubElement(aso_el, "medico")
    SubElement(med, "nmMed").text = aso.medico_responsavel or (cfg.nome_medico_coordenador if cfg else "Médico")
    SubElement(med, "nrCRM").text = aso.crm or (cfg.crm_medico if cfg else "000000")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _xml_str(root)


# ─── S-2230 — Afastamento Temporário ──────────────────────────────────────────

def _gerar_xml_s2230(afastamento, cfg):
    cnpj = _cnpj_limpo(cfg.cnpj if cfg else "")
    cpf  = _cpf_limpo(afastamento.funcionario.cpf)
    seq  = afastamento.pk

    motivo_map = {
        "acidente_trabalho": "01",
        "doenca_ocupacional": "02",
        "doenca_comum": "03",
        "licenca_maternidade": "18",
        "licenca_paternidade": "19",
        "outro": "99",
    }

    NS = "http://www.esocial.gov.br/schema/evt/evtAfastTemp/v_S_01_03_00"
    root = Element("eSocial", xmlns=NS)

    evt = SubElement(root, "evtAfastTemp", Id=_evento_id("EVTAFASTTEMP", cnpj, seq))

    ide = SubElement(evt, "ideEvento")
    SubElement(ide, "indRetif").text = "1"
    SubElement(ide, "tpAmb").text = "1"
    SubElement(ide, "procEmi").text = "1"
    SubElement(ide, "verProc").text = "SolusCRT_1.0"

    emp = SubElement(evt, "ideEmpregador")
    SubElement(emp, "tpInsc").text = "1"
    SubElement(emp, "nrInsc").text = cnpj or "00000000000000"

    vin = SubElement(evt, "ideVinculo")
    SubElement(vin, "cpfTrab").text = cpf or "00000000000"
    if afastamento.funcionario.matricula:
        SubElement(vin, "matricula").text = afastamento.funcionario.matricula

    inf = SubElement(evt, "infoAfastamento")

    ini = SubElement(inf, "iniAfastamento")
    SubElement(ini, "dtIniAfast").text = afastamento.data_inicio.strftime("%Y-%m-%d")
    SubElement(ini, "codMotAfast").text = motivo_map.get(afastamento.motivo, "99")
    if afastamento.cid:
        SubElement(ini, "codCID").text = afastamento.cid[:4]

    if afastamento.data_retorno_real or afastamento.data_prevista_retorno:
        fim = SubElement(inf, "fimAfastamento")
        dt = afastamento.data_retorno_real or afastamento.data_prevista_retorno
        SubElement(fim, "dtTermAfast").text = dt.strftime("%Y-%m-%d")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _xml_str(root)


# ─── S-2240 — Condições Ambientais ────────────────────────────────────────────

def _gerar_xml_s2240(empresa, cfg, periodo=None, posto=None):
    """Gera S-2240 para um posto de trabalho específico com agentes nocivos reais."""
    from django.utils import timezone
    if not periodo:
        periodo = timezone.now().strftime("%Y-%m")

    cnpj = _cnpj_limpo(cfg.cnpj if cfg else "")
    seq  = posto.pk if posto else 1

    NS = "http://www.esocial.gov.br/schema/evt/evtCondicAmb/v_S_01_03_00"
    root = Element("eSocial", xmlns=NS)

    evt = SubElement(root, "evtCondicAmb", Id=_evento_id("EVTCONDICAMB", cnpj, seq))

    ide = SubElement(evt, "ideEvento")
    SubElement(ide, "indRetif").text = "1"
    SubElement(ide, "tpAmb").text = "2"   # 2 = homologação | trocar para "1" em produção real
    SubElement(ide, "procEmi").text = "1"
    SubElement(ide, "verProc").text = "SolusCRT_1.0"
    SubElement(ide, "perApur").text = periodo

    emp = SubElement(evt, "ideEmpregador")
    SubElement(emp, "tpInsc").text = "1"
    SubElement(emp, "nrInsc").text = cnpj or "00000000000000"

    amb = SubElement(evt, "infoCondicAmb")
    SubElement(amb, "tpAmb").text = "1"
    SubElement(amb, "localAmb").text = "1"

    validade = SubElement(amb, "novaValidade")
    vigencia = (posto.vigencia_inicio or periodo) if posto else periodo
    SubElement(validade, "iniValid").text = vigencia

    set_el = SubElement(amb, "setor")
    setor_nome = (posto.setor or cfg.cnae_principal or "Atividades gerais") if posto else (cfg.cnae_principal if cfg else "Atividades gerais")
    SubElement(set_el, "dscSetor").text = setor_nome[:999]

    if posto:
        # Responsável técnico
        resp = SubElement(amb, "responsavel")
        SubElement(resp, "nmResp").text = (posto.responsavel_tecnico or (cfg.nome_medico_coordenador if cfg else "Responsável SST"))[:70]
        SubElement(resp, "cpfResp").text = "00000000000"  # CPF do responsável — campo a ser adicionado futuramente
        SubElement(resp, "ideOC").text = posto.responsavel_registro or "000000"

        # Trabalhadores expostos
        vinculos_ativos = FuncionarioPostoTrabalho.objects.filter(
            posto=posto, data_fim__isnull=True
        ).select_related("funcionario")

        agentes = list(AgenteNocivoPostoTrabalho.objects.filter(posto=posto))

        for vinculo in vinculos_ativos:
            func = vinculo.funcionario
            trab = SubElement(amb, "trabExposto")
            vin_el = SubElement(trab, "ideVinculo")
            SubElement(vin_el, "cpfTrab").text = _cpf_limpo(func.cpf) or "00000000000"
            if func.matricula:
                SubElement(vin_el, "matricula").text = func.matricula

            for ag in agentes:
                ag_el = SubElement(trab, "agentesNocivos")
                SubElement(ag_el, "codAgente").text = ag.cod_agente
                dsc = ag.dsc_agente or ag.get_cod_agente_display()
                SubElement(ag_el, "dscAgente").text = dsc[:300]

                if ag.tec_medicao:
                    SubElement(ag_el, "tecMedicao").text = ag.tec_medicao[:200]
                if ag.intensidade:
                    SubElement(ag_el, "intConc").text = ag.intensidade[:20]
                if ag.limite_tolerancia:
                    SubElement(ag_el, "limTol").text = ag.limite_tolerancia[:20]

                if ag.epc_descricao:
                    epc_el = SubElement(ag_el, "epc")
                    SubElement(epc_el, "dscEpc").text = ag.epc_descricao[:300]
                    SubElement(epc_el, "eficEpc").text = "S" if ag.epc_eficaz else "N"

                if ag.epi_descricao:
                    epi_el = SubElement(ag_el, "epi")
                    SubElement(epi_el, "dscEpi").text = ag.epi_descricao[:300]
                    if ag.epi_ca:
                        SubElement(epi_el, "nrCA").text = ag.epi_ca[:20]
                    SubElement(epi_el, "eficEpi").text = "S" if ag.epi_eficaz else "N"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + _xml_str(root)


# ─── API endpoints ─────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_esocial_eventos(request):
    """Lista eventos ou registra novo evento manualmente."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        tipo = request.GET.get("tipo", "")
        status = request.GET.get("status", "")
        qs = eSocialEventoSST.objects.filter(empresa=e)
        if tipo:
            qs = qs.filter(tipo_evento=tipo)
        if status:
            qs = qs.filter(status=status)
        return JsonResponse({"eventos": [_evt_dict(ev) for ev in qs[:100]]})

    data = json.loads(request.body or "{}")
    ev = eSocialEventoSST.objects.create(
        empresa=e,
        tipo_evento=data.get("tipo_evento", "S-2210"),
        referencia=data.get("referencia", ""),
    )
    return JsonResponse(_evt_dict(ev), status=201)


def api_esocial_gerar_xml(request, evento_id):
    """Gera (ou regenera) o XML do evento e retorna para download."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ev = eSocialEventoSST.objects.get(pk=evento_id, empresa=e)
    except eSocialEventoSST.DoesNotExist:
        return JsonResponse({"erro": "Evento não encontrado"}, status=404)

    cfg = _cfg(e)
    xml = ""

    try:
        if ev.tipo_evento == "S-2210":
            ref_id = int(ev.referencia) if ev.referencia.isdigit() else None
            if ref_id:
                cat = CATOcupacional.objects.get(pk=ref_id, empresa=e)
                xml = _gerar_xml_s2210(cat, cfg)
        elif ev.tipo_evento == "S-2220":
            ref_id = int(ev.referencia) if ev.referencia.isdigit() else None
            if ref_id:
                aso = ASOOcupacional.objects.get(pk=ref_id, empresa=e)
                xml = _gerar_xml_s2220(aso, cfg)
        elif ev.tipo_evento == "S-2230":
            ref_id = int(ev.referencia) if ev.referencia.isdigit() else None
            if ref_id:
                af = AfastamentoSST.objects.get(pk=ref_id, empresa=e)
                xml = _gerar_xml_s2230(af, cfg)
        elif ev.tipo_evento == "S-2240":
            periodo = request.GET.get("periodo", date.today().strftime("%Y-%m"))
            xml = _gerar_xml_s2240(e, cfg, periodo)
    except Exception as ex:
        return JsonResponse({"erro": f"Erro ao gerar XML: {ex}"}, status=500)

    if not xml:
        return JsonResponse({"erro": "Referência inválida ou não encontrada"}, status=400)

    # persiste XML
    ev.xml_gerado = xml
    ev.save(update_fields=["xml_gerado"])

    download = request.GET.get("download", "0") == "1"
    if download:
        resp = HttpResponse(xml, content_type="application/xml; charset=utf-8")
        nome = f"esocial_{ev.tipo_evento.replace('-','_')}_{ev.pk}.xml"
        resp["Content-Disposition"] = f'attachment; filename="{nome}"'
        return resp

    return JsonResponse({"xml": xml, "evento_id": ev.pk})


def api_esocial_registrar_cat(request, cat_id):
    """Cria automaticamente um evento S-2210 para uma CAT e gera XML."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        cat = CATOcupacional.objects.get(pk=cat_id, empresa=e)
    except CATOcupacional.DoesNotExist:
        return JsonResponse({"erro": "CAT não encontrada"}, status=404)

    cfg = _cfg(e)
    xml = _gerar_xml_s2210(cat, cfg)

    ev = eSocialEventoSST.objects.create(
        empresa=e,
        tipo_evento="S-2210",
        referencia=str(cat.pk),
        xml_gerado=xml,
    )
    cat.status_esocial = "pendente"
    cat.save(update_fields=["status_esocial"])

    return JsonResponse({"evento_id": ev.pk, "xml_tamanho": len(xml), "status": "pendente"}, status=201)


def api_esocial_registrar_aso(request, aso_id):
    """Cria evento S-2220 para um ASO e gera XML."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        aso = ASOOcupacional.objects.get(pk=aso_id, empresa=e)
    except ASOOcupacional.DoesNotExist:
        return JsonResponse({"erro": "ASO não encontrado"}, status=404)

    cfg = _cfg(e)
    xml = _gerar_xml_s2220(aso, cfg)

    ev = eSocialEventoSST.objects.create(
        empresa=e,
        tipo_evento="S-2220",
        referencia=str(aso.pk),
        xml_gerado=xml,
    )
    return JsonResponse({"evento_id": ev.pk, "xml_tamanho": len(xml), "status": "pendente"}, status=201)


def api_esocial_registrar_afastamento(request, afastamento_id):
    """Cria evento S-2230 para um afastamento."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        af = AfastamentoSST.objects.get(pk=afastamento_id, empresa=e)
    except AfastamentoSST.DoesNotExist:
        return JsonResponse({"erro": "Afastamento não encontrado"}, status=404)

    cfg = _cfg(e)
    xml = _gerar_xml_s2230(af, cfg)

    ev = eSocialEventoSST.objects.create(
        empresa=e,
        tipo_evento="S-2230",
        referencia=str(af.pk),
        xml_gerado=xml,
    )
    return JsonResponse({"evento_id": ev.pk, "xml_tamanho": len(xml), "status": "pendente"}, status=201)


def api_esocial_marcar_transmitido(request, evento_id):
    """Marca evento como transmitido e registra protocolo."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        ev = eSocialEventoSST.objects.get(pk=evento_id, empresa=e)
    except eSocialEventoSST.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    data = json.loads(request.body or "{}")
    ev.status = data.get("status", "transmitido")
    ev.protocolo = data.get("protocolo", "")
    ev.mensagem_erro = data.get("mensagem_erro", "")
    ev.data_envio = timezone.now()
    ev.save()

    # atualiza CAT se for S-2210
    if ev.tipo_evento == "S-2210" and ev.referencia.isdigit():
        CATOcupacional.objects.filter(pk=int(ev.referencia), empresa=e).update(
            status_esocial=ev.status,
            protocolo_esocial=ev.protocolo,
        )

    return JsonResponse({"ok": True, "status": ev.status})


def api_esocial_kpis(request):
    """KPIs da fila eSocial."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    qs = eSocialEventoSST.objects.filter(empresa=e)
    return JsonResponse({
        "pendentes": qs.filter(status="pendente").count(),
        "transmitidos": qs.filter(status="transmitido").count(),
        "erros": qs.filter(status="erro").count(),
        "total": qs.count(),
        "por_tipo": {
            "S-2210": qs.filter(tipo_evento="S-2210").count(),
            "S-2220": qs.filter(tipo_evento="S-2220").count(),
            "S-2230": qs.filter(tipo_evento="S-2230").count(),
            "S-2240": qs.filter(tipo_evento="S-2240").count(),
        },
        "cats_nao_enviadas": CATOcupacional.objects.filter(empresa=e, status_esocial="nao_enviado").count(),
    })


def _evt_dict(ev):
    return {
        "id": ev.pk,
        "tipo_evento": ev.tipo_evento,
        "tipo_label": ev.get_tipo_evento_display(),
        "status": ev.status,
        "status_label": ev.get_status_display(),
        "referencia": ev.referencia,
        "protocolo": ev.protocolo,
        "mensagem_erro": ev.mensagem_erro,
        "tem_xml": bool(ev.xml_gerado),
        "data_envio": ev.data_envio.isoformat() if ev.data_envio else None,
        "criado_em": ev.criado_em.isoformat(),
    }


# ─── Portal de Compartilhamento de ASO ─────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_aso_compartilhamentos(request, aso_id):
    """Lista ou cria compartilhamentos para um ASO."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        aso = ASOOcupacional.objects.get(pk=aso_id, empresa=e)
    except ASOOcupacional.DoesNotExist:
        return JsonResponse({"erro": "ASO não encontrado"}, status=404)

    if request.method == "GET":
        comps = ASOCompartilhamento.objects.filter(aso=aso, empresa_origem=e)
        return JsonResponse({"compartilhamentos": [_comp_dict(c) for c in comps]})

    data = json.loads(request.body or "{}")
    dias = int(data.get("dias_validade", 30))
    token = secrets.token_urlsafe(48)

    comp = ASOCompartilhamento.objects.create(
        aso=aso,
        empresa_origem=e,
        token=token,
        empresa_destino_cnpj=data.get("empresa_destino_cnpj", ""),
        empresa_destino_nome=data.get("empresa_destino_nome", ""),
        email_destino=data.get("email_destino", ""),
        max_acessos=int(data.get("max_acessos", 20)),
        expira_em=timezone.now() + timedelta(days=dias),
    )
    return JsonResponse({**_comp_dict(comp), "url_acesso": f"/sst/aso/portal/{token}/"}, status=201)


def api_aso_revogar_compartilhamento(request, token):
    """Revoga (desativa) um link de compartilhamento."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    updated = ASOCompartilhamento.objects.filter(token=token, empresa_origem=e).update(ativo=False)
    if not updated:
        return JsonResponse({"erro": "Compartilhamento não encontrado"}, status=404)
    return JsonResponse({"ok": True})


def portal_aso_publico(request, token):
    """Página pública para a empresa contratante visualizar o ASO."""
    try:
        comp = ASOCompartilhamento.objects.select_related(
            "aso__funcionario", "empresa_origem"
        ).get(token=token, ativo=True)
    except ASOCompartilhamento.DoesNotExist:
        return render(request, "sst_aso_portal.html", {"erro": "Link inválido ou expirado."})

    if timezone.now() > comp.expira_em:
        return render(request, "sst_aso_portal.html", {"erro": "Este link expirou."})

    if comp.acessos >= comp.max_acessos:
        return render(request, "sst_aso_portal.html", {"erro": "Limite de acessos atingido."})

    comp.acessos += 1
    comp.save(update_fields=["acessos"])

    aso = comp.aso
    func = aso.funcionario

    ctx = {
        "comp": comp,
        "aso": aso,
        "func": func,
        "empresa_origem": comp.empresa_origem,
        "exames": aso.exames.all(),
        "restantes": comp.max_acessos - comp.acessos,
    }
    return render(request, "sst_aso_portal.html", ctx)


def _comp_dict(c):
    return {
        "id": c.pk,
        "token": c.token,
        "empresa_destino_nome": c.empresa_destino_nome,
        "empresa_destino_cnpj": c.empresa_destino_cnpj,
        "email_destino": c.email_destino,
        "acessos": c.acessos,
        "max_acessos": c.max_acessos,
        "expira_em": c.expira_em.isoformat(),
        "ativo": c.ativo,
        "criado_em": c.criado_em.isoformat(),
        "url": f"/sst/aso/portal/{c.token}/",
    }


# ── eSocial Real Transmission ────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_esocial_transmitir(request, evento_id):
    """Transmits a single eSocial event to the government REST API."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ev = eSocialEventoSST.objects.get(pk=evento_id, empresa=e)
    except eSocialEventoSST.DoesNotExist:
        return JsonResponse({"erro": "Evento não encontrado"}, status=404)

    if ev.status == "transmitido":
        return JsonResponse({"erro": "Evento já transmitido", "protocolo": ev.protocolo}, status=400)

    from .esocial_transmissao import transmitir_evento
    ok, mensagem = transmitir_evento(ev)

    return JsonResponse({
        "ok": ok,
        "status": ev.status,
        "protocolo": ev.protocolo,
        "mensagem": mensagem,
    }, status=200 if ok else 422)


@csrf_exempt
@require_http_methods(["POST"])
def api_esocial_transmitir_pendentes(request):
    """Transmits all pending events for the empresa (up to 50 at once)."""
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .esocial_transmissao import transmitir_pendentes
    resultados = transmitir_pendentes(e)

    transmitidos = sum(1 for r in resultados if r["ok"])
    erros = len(resultados) - transmitidos

    return JsonResponse({
        "total": len(resultados),
        "transmitidos": transmitidos,
        "erros": erros,
        "resultados": resultados,
    })


@csrf_exempt
def api_esocial_certificado(request):
    """
    GET  — returns certificate status (name, expiry, environment).
    POST — uploads PKCS#12 certificate (multipart: file=.pfx, senha=str, ambiente=str).
    """
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    cfg = _cfg(e)
    if not cfg:
        from .models import ConfiguracaoSST
        cfg = ConfiguracaoSST.objects.create(empresa=e)

    if request.method == "GET":
        return JsonResponse({
            "configurado": bool(cfg.certificado_pfx_b64),
            "nome": cfg.certificado_nome,
            "validade": cfg.certificado_validade.isoformat() if cfg.certificado_validade else None,
            "ambiente": cfg.esocial_ambiente,
        })

    if request.method == "POST":
        import base64
        arquivo = request.FILES.get("certificado")
        senha = request.POST.get("senha", "")
        ambiente = request.POST.get("ambiente", "homologacao")

        if not arquivo:
            return JsonResponse({"erro": "Envie o arquivo .pfx"}, status=400)

        pfx_bytes = arquivo.read()

        # Validate certificate
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            from cryptography.hazmat.backends import default_backend
            senha_bytes = senha.encode() if senha else b""
            private_key, cert, _ = pkcs12.load_key_and_certificates(
                pfx_bytes, senha_bytes, backend=default_backend()
            )
            validade = cert.not_valid_after_utc.date() if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.date()
            nome_cert = cert.subject.rfc4514_string()
        except Exception as ex:
            return JsonResponse({"erro": f"Certificado inválido: {ex}"}, status=400)

        cfg.certificado_pfx_b64 = base64.b64encode(pfx_bytes).decode()
        cfg.certificado_senha = senha
        cfg.certificado_validade = validade
        cfg.certificado_nome = nome_cert[:200]
        cfg.esocial_ambiente = ambiente
        cfg.save(update_fields=[
            "certificado_pfx_b64", "certificado_senha",
            "certificado_validade", "certificado_nome", "esocial_ambiente",
        ])

        return JsonResponse({
            "ok": True,
            "nome": nome_cert[:200],
            "validade": validade.isoformat(),
            "ambiente": ambiente,
        })
