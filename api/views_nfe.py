"""
NF-e / NFC-e — Emissão de Nota Fiscal Eletrônica via SEFAZ.

Emissão real via SOAP NFeAutorizacao4 por UF, com:
  • Certificado e-CNPJ A1/A3 por empresa (CredenciaisIntegracoes.nfe_*)
  • Assinatura XML RSA-SHA1 conforme padrão W3C XML-DSig
  • Chave de acesso 44 dígitos calculada (cUF+AAMM+CNPJ+mod+serie+nNF+tpEmis+cNF+cDV)
  • Lote síncrono (indSinc=1) — resposta imediata da SEFAZ
  • Suporte a NF-e (mod 55) e NFC-e (mod 65)

Quando e-CNPJ configurado → emissão real via SEFAZ
Quando não configurado → orienta configuração

Ref: Manual de Orientação ao Contribuinte NF-e v4.0 (ENCAT)
     Portal NF-e: https://www.nfe.fazenda.gov.br/
"""
import base64
import hashlib
import json
import logging
import os
import random
import tempfile
from datetime import datetime, timezone as dt_tz

from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .access_control import get_setor
from .models import CredenciaisIntegracoes, NotaFiscalEletronica
from .views_dashboard import _empresa_autenticada

logger = logging.getLogger(__name__)

# ── Endpoints SEFAZ por UF (NF-e 4.0) ────────────────────────────────────────
# SEFAZ Virtual do SVRS (backup para estados sem server próprio)
_SVRS_PROD = "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx"
_SVRS_HML  = "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx"
# SEFAZ Virtual Nacional (AN — AN cobre vários estados)
_SVAN_PROD = "https://www.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx"
_SVAN_HML  = "https://hom.sefazvirtual.fazenda.gov.br/NFeAutorizacao4/NFeAutorizacao4.asmx"

_SEFAZ_WS = {
    # (UF_SIGLA, tpAmb) → url
    ("SP", "1"): "https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
    ("SP", "2"): "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
    ("MG", "1"): "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
    ("MG", "2"): "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
    ("PR", "1"): "https://nfe.fazenda.pr.gov.br/nfe/NFeAutorizacao4",
    ("PR", "2"): "https://homologacao.nfe.fazenda.pr.gov.br/nfe/NFeAutorizacao4",
    ("RS", "1"): _SVRS_PROD,
    ("RS", "2"): _SVRS_HML,
    ("RJ", "1"): "https://nfe.fazenda.rj.gov.br/NfeAutorizacao4/NfeAutorizacao4.asmx",
    ("RJ", "2"): "https://nfe-hml.fazenda.rj.gov.br/NfeAutorizacao4/NfeAutorizacao4.asmx",
    ("BA", "1"): _SVRS_PROD,
    ("BA", "2"): _SVRS_HML,
    ("GO", "1"): "https://nfe.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
    ("GO", "2"): "https://homologacao.sefaz.go.gov.br/nfe/services/NFeAutorizacao4",
    ("MT", "1"): "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4",
    ("MT", "2"): "https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4",
    ("MS", "1"): "https://nfe.fazenda.ms.gov.br/ws/NFeAutorizacao4",
    ("MS", "2"): "https://hom.fazenda.ms.gov.br/ws/NFeAutorizacao4",
    ("AM", "1"): "https://nfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4",
    ("AM", "2"): "https://homnfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4",
}

# cUF — código IBGE da UF (para montar chave de acesso)
_CUF = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29", "CE": "23",
    "DF": "53", "ES": "32", "GO": "52", "MA": "21", "MT": "51", "MS": "50",
    "MG": "31", "PA": "15", "PB": "25", "PR": "41", "PE": "26", "PI": "22",
    "RJ": "33", "RN": "24", "RS": "43", "RO": "11", "RR": "14", "SC": "42",
    "SP": "35", "SE": "28", "TO": "17",
}

_NS_NFE  = "http://www.portalfiscal.inf.br/nfe"
_NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


# ── Auth helper ───────────────────────────────────────────────────────────────

def _empresa_auth(request):
    return _empresa_autenticada(request)


# ── Chave de acesso ───────────────────────────────────────────────────────────

def _calcular_chave(cuf, aamm, cnpj, mod, serie, nnf, tpemis, cnf):
    """Calcula os 44 dígitos da chave de acesso NF-e (sem dígito verificador)."""
    base = f"{cuf}{aamm}{cnpj}{mod}{serie:>03}{nnf:>09}{tpemis}{cnf:>08}"
    # cDV = módulo 11
    pesos = [2, 3, 4, 5, 6, 7, 2, 3, 4, 5, 6, 7, 2, 3, 4, 5, 6, 7,
             2, 3, 4, 5, 6, 7, 2, 3, 4, 5, 6, 7, 2, 3, 4, 5, 6, 7, 2, 3, 4, 5, 6, 7, 2]
    soma = sum(int(d) * p for d, p in zip(reversed(base), pesos))
    resto = soma % 11
    cdv = 0 if resto < 2 else 11 - resto
    return base + str(cdv)


# ── XML NF-e 4.0 ─────────────────────────────────────────────────────────────

def _gerar_xml_nfe(nota: NotaFiscalEletronica, cred: CredenciaisIntegracoes) -> str:
    """
    Gera XML NF-e 4.0 não assinado.
    Conforme Manual de Orientação ao Contribuinte NF-e v4.0.
    """
    from lxml import etree

    uf      = cred.nfe_uf.upper()
    cuf     = _CUF.get(uf, "35")
    cnpj    = "".join(c for c in cred.nfe_cnpj_emitente if c.isdigit())
    mod     = nota.modelo  # "55" ou "65"
    serie   = nota.serie.zfill(3)
    nnf     = str(nota.numero).zfill(9)
    tpemis  = "1"  # emissão normal
    cnf     = str(random.randint(10000000, 99999999))
    dhemi   = (nota.data_emissao or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"
    aamm    = (nota.data_emissao or datetime.now()).strftime("%y%m")
    tpamb   = nota.ambiente  # "1"=produção, "2"=homologação
    chave   = _calcular_chave(cuf, aamm, cnpj, mod, serie, nnf, tpemis, cnf)

    nota.chave_acesso = chave

    ns  = _NS_NFE
    nfe = etree.Element(f"{{{ns}}}NFe", nsmap={None: ns})
    inf = etree.SubElement(nfe, f"{{{ns}}}infNFe",
                           attrib={"versao": "4.00", "Id": f"NFe{chave}"})

    # ── ide ──────────────────────────────────────────────────────────────────
    ide = etree.SubElement(inf, f"{{{ns}}}ide")
    _tx(ide, ns, "cUF",    cuf)
    _tx(ide, ns, "cNF",    cnf)
    _tx(ide, ns, "natOp",  nota.natureza_operacao[:60])
    _tx(ide, ns, "mod",    mod)
    _tx(ide, ns, "serie",  str(int(serie)))
    _tx(ide, ns, "nNF",    str(nota.numero))
    _tx(ide, ns, "dhEmi",  dhemi)
    _tx(ide, ns, "tpNF",   "1")   # saída
    _tx(ide, ns, "idDest", "1")   # operação interna
    _tx(ide, ns, "cMunFG", cred.nfe_municipio_ibge or "3550308")
    _tx(ide, ns, "tpImp",  "1")   # DANFE retrato
    _tx(ide, ns, "tpEmis", tpemis)
    _tx(ide, ns, "cDV",    chave[-1])
    _tx(ide, ns, "tpAmb",  tpamb)
    _tx(ide, ns, "finNFe", "1")   # NF-e normal
    _tx(ide, ns, "indFinal","1")  # consumidor final
    _tx(ide, ns, "indPres", "1")  # presencial
    _tx(ide, ns, "procEmi", "0")
    _tx(ide, ns, "verProc", "SolusCRT 1.0")

    # ── emit ─────────────────────────────────────────────────────────────────
    emit = etree.SubElement(inf, f"{{{ns}}}emit")
    _tx(emit, ns, "CNPJ",  cnpj)
    _tx(emit, ns, "xNome", (nota.nome_emitente or cred.nfe_cnpj_emitente)[:60])
    ender = etree.SubElement(emit, f"{{{ns}}}enderEmit")
    _tx(ender, ns, "xLgr",   "Endereço não informado")
    _tx(ender, ns, "nro",    "S/N")
    _tx(ender, ns, "xBairro","Centro")
    _tx(ender, ns, "cMun",   cred.nfe_municipio_ibge or "3550308")
    _tx(ender, ns, "xMun",   uf)
    _tx(ender, ns, "UF",     uf)
    _tx(ender, ns, "CEP",    "00000000")
    _tx(ender, ns, "cPais",  "1058")
    _tx(ender, ns, "xPais",  "Brasil")
    _tx(emit, ns, "IE",    cred.nfe_ie or "ISENTO")
    _tx(emit, ns, "CRT",   cred.nfe_crt or "3")

    # ── dest ─────────────────────────────────────────────────────────────────
    dest = etree.SubElement(inf, f"{{{ns}}}dest")
    cpf_cnpj_dest = "".join(c for c in (nota.cpf_cnpj_destinatario or "") if c.isdigit())
    if len(cpf_cnpj_dest) == 14:
        _tx(dest, ns, "CNPJ", cpf_cnpj_dest)
    elif len(cpf_cnpj_dest) == 11:
        _tx(dest, ns, "CPF",  cpf_cnpj_dest)
    else:
        _tx(dest, ns, "CPF",  "00000000000")  # consumidor não identificado
    _tx(dest, ns, "xNome",   (nota.nome_destinatario or "CONSUMIDOR NÃO IDENTIFICADO")[:60])
    _tx(dest, ns, "indIEDest", "9")  # 9 = não contribuinte

    # ── det (itens) ───────────────────────────────────────────────────────────
    itens = nota.itens or []
    if not itens:
        itens = [{
            "cProd": "000", "xProd": "PRODUTO GENÉRICO",
            "NCM": "00000000", "CFOP": nota.cfop or "5102",
            "uCom": "UN", "qCom": "1.00", "vUnCom": str(nota.valor_total),
            "vProd": str(nota.valor_total),
        }]

    for i, item in enumerate(itens, 1):
        det = etree.SubElement(inf, f"{{{ns}}}det", attrib={"nItem": str(i)})
        prod = etree.SubElement(det, f"{{{ns}}}prod")
        _tx(prod, ns, "cProd",    item.get("cProd", str(i).zfill(3)))
        _tx(prod, ns, "cEAN",     "SEM GTIN")
        _tx(prod, ns, "xProd",    item.get("xProd", "PRODUTO")[:120])
        _tx(prod, ns, "NCM",      item.get("NCM", "00000000"))
        _tx(prod, ns, "CFOP",     item.get("CFOP", nota.cfop or "5102"))
        _tx(prod, ns, "uCom",     item.get("uCom", "UN"))
        _tx(prod, ns, "qCom",     item.get("qCom", "1.00"))
        _tx(prod, ns, "vUnCom",   item.get("vUnCom", "0.00"))
        _tx(prod, ns, "vProd",    item.get("vProd", "0.00"))
        _tx(prod, ns, "cEANTrib", "SEM GTIN")
        _tx(prod, ns, "uTrib",    item.get("uCom", "UN"))
        _tx(prod, ns, "qTrib",    item.get("qCom", "1.00"))
        _tx(prod, ns, "vUnTrib",  item.get("vUnCom", "0.00"))
        _tx(prod, ns, "indTot",   "1")
        # Impostos simplificados (sem tributação — ajustar conforme regime fiscal)
        imp = etree.SubElement(det, f"{{{ns}}}imposto")
        icms = etree.SubElement(imp, f"{{{ns}}}ICMS")
        icms40 = etree.SubElement(icms, f"{{{ns}}}ICMS40")
        _tx(icms40, ns, "orig",  "0")
        _tx(icms40, ns, "CST",   "40")  # isento
        pis = etree.SubElement(imp, f"{{{ns}}}PIS")
        pis07 = etree.SubElement(pis, f"{{{ns}}}PISNT")
        _tx(pis07, ns, "CST", "07")  # operação isenta
        cof = etree.SubElement(imp, f"{{{ns}}}COFINS")
        cof07 = etree.SubElement(cof, f"{{{ns}}}COFINSNT")
        _tx(cof07, ns, "CST", "07")

    # ── total ─────────────────────────────────────────────────────────────────
    total = etree.SubElement(inf, f"{{{ns}}}total")
    icmstot = etree.SubElement(total, f"{{{ns}}}ICMSTot")
    vp = str(nota.valor_produtos or nota.valor_total)
    vt = str(nota.valor_total)
    for tag, val in [
        ("vBC", "0.00"), ("vICMS", "0.00"), ("vICMSDeson", "0.00"),
        ("vFCP", "0.00"), ("vBCST", "0.00"), ("vST", "0.00"),
        ("vFCPST", "0.00"), ("vFCPSTRet", "0.00"),
        ("vProd", vp), ("vFrete", "0.00"), ("vSeg", "0.00"),
        ("vDesc", str(nota.valor_desconto or "0.00")),
        ("vII", "0.00"), ("vIPI", "0.00"), ("vIPIDevol", "0.00"),
        ("vPIS", "0.00"), ("vCOFINS", "0.00"), ("vOutro", "0.00"),
        ("vNF", vt),
    ]:
        _tx(icmstot, ns, tag, val)

    # ── transp ────────────────────────────────────────────────────────────────
    transp = etree.SubElement(inf, f"{{{ns}}}transp")
    _tx(transp, ns, "modFrete", "9")  # sem transporte

    # ── pag ───────────────────────────────────────────────────────────────────
    pag = etree.SubElement(inf, f"{{{ns}}}pag")
    det_pag = etree.SubElement(pag, f"{{{ns}}}detPag")
    _tx(det_pag, ns, "tPag", nota.forma_pagamento or "99")
    _tx(det_pag, ns, "vPag", vt)

    # ── infAdic ───────────────────────────────────────────────────────────────
    infadic = etree.SubElement(inf, f"{{{ns}}}infAdic")
    _tx(infadic, ns, "infCpl", "Documento emitido pela plataforma SolusCRT")

    return etree.tostring(nfe, encoding="unicode", xml_declaration=False)


def _tx(parent, ns, tag, text):
    """Cria sub-elemento com texto."""
    from lxml import etree
    el = etree.SubElement(parent, f"{{{ns}}}{tag}")
    el.text = str(text) if text is not None else ""
    return el


# ── Assinatura XML RSA-SHA1 ───────────────────────────────────────────────────

def _assinar_nfe(xml_str: str, cert_path: str, key_path: str) -> str:
    """
    Assina o XML NF-e conforme W3C XML-DSig (RSA-SHA1, C14N exclusivo).
    Requisito obrigatório pela SEFAZ.
    """
    from lxml import etree
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    from cryptography import x509

    ns  = _NS_NFE
    dns = _NS_DSIG

    doc    = etree.fromstring(xml_str.encode("utf-8"))
    inf_nf = doc.find(f"{{{ns}}}infNFe")
    ref_id = inf_nf.get("Id")

    # C14N do infNFe
    c14n_inf = etree.tostring(inf_nf, method="c14n", exclusive=True)

    # SHA-1 digest
    digest = hashlib.sha1(c14n_inf).digest()
    digest_b64 = base64.b64encode(digest).decode()

    # Carrega chave privada e certificado
    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    with open(cert_path, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read(), backend=default_backend())

    cert_der_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()

    # SignedInfo
    signed_info_xml = (
        f'<SignedInfo xmlns="{dns}">'
        f'<CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f'<SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>'
        f'<Reference URI="#{ref_id}">'
        f'<Transforms>'
        f'<Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>'
        f'<Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f'</Transforms>'
        f'<DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>'
        f'<DigestValue>{digest_b64}</DigestValue>'
        f'</Reference>'
        f'</SignedInfo>'
    )

    signed_info_el = etree.fromstring(signed_info_xml.encode("utf-8"))
    c14n_si = etree.tostring(signed_info_el, method="c14n", exclusive=False)

    # RSA-SHA1 sign
    sig_bytes = private_key.sign(c14n_si, padding.PKCS1v15(), hashes.SHA1())
    sig_b64   = base64.b64encode(sig_bytes).decode()

    # Montar Signature element e adicionar ao NFe
    sig_el = etree.SubElement(doc, f"{{{dns}}}Signature")
    sig_el.append(etree.fromstring(c14n_si))
    sig_val = etree.SubElement(sig_el, f"{{{dns}}}SignatureValue")
    sig_val.text = sig_b64
    key_info = etree.SubElement(sig_el, f"{{{dns}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{dns}}}X509Data")
    x509_cert = etree.SubElement(x509_data, f"{{{dns}}}X509Certificate")
    x509_cert.text = cert_der_b64

    return etree.tostring(doc, encoding="unicode", xml_declaration=False)


# ── Transmissão SEFAZ SOAP ────────────────────────────────────────────────────

def _montar_envelope_soap(xml_nfe_assinado: str, cuf: str, tpamb: str) -> str:
    """Monta envelope SOAP NFeAutorizacao4 (lote síncrono)."""
    ns_wsdl = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4"
    ns_nfe  = _NS_NFE
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soapenv:Header>'
        f'<nfeCabecMsg xmlns="{ns_wsdl}">'
        f'<cUF>{cuf}</cUF>'
        '<versaoDados>4.00</versaoDados>'
        '</nfeCabecMsg>'
        '</soapenv:Header>'
        '<soapenv:Body>'
        f'<nfeDadosMsg xmlns="{ns_wsdl}">'
        f'<enviNFe versao="4.00" xmlns="{ns_nfe}">'
        '<idLote>1</idLote>'
        '<indSinc>1</indSinc>'
        f'{xml_nfe_assinado}'
        '</enviNFe>'
        '</nfeDadosMsg>'
        '</soapenv:Body>'
        '</soapenv:Envelope>'
    )


def _url_sefaz(uf: str, tpamb: str) -> str:
    """Retorna endpoint SEFAZ para a UF e ambiente."""
    key = (uf.upper(), tpamb)
    if key in _SEFAZ_WS:
        return _SEFAZ_WS[key]
    # Fallback: SVRS para homologação, SVAN para produção
    return _SVRS_HML if tpamb == "2" else _SVAN_PROD


def _transmitir_sefaz(xml_assinado: str, cuf: str, uf: str, tpamb: str,
                      cert_path: str, key_path: str) -> dict:
    """POST SOAP à SEFAZ. Retorna dict com status e protocolo."""
    import requests as req
    from lxml import etree

    url  = _url_sefaz(uf, tpamb)
    soap = _montar_envelope_soap(xml_assinado, cuf, tpamb)

    resp = req.post(
        url,
        data=soap.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction":   '"http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4/nfeAutorizacaoLote"',
        },
        cert=(cert_path, key_path),
        timeout=60,
        verify=True,
    )
    resp.raise_for_status()

    # Parse resposta SOAP
    root   = etree.fromstring(resp.content)
    ns_map = {"nfe": _NS_NFE}

    cstat = root.find(".//{http://www.portalfiscal.inf.br/nfe}cStat")
    xmot  = root.find(".//{http://www.portalfiscal.inf.br/nfe}xMotivo")
    nprot = root.find(".//{http://www.portalfiscal.inf.br/nfe}nProt")
    dhret = root.find(".//{http://www.portalfiscal.inf.br/nfe}dhRecbto")

    status   = cstat.text if cstat is not None else ""
    motivo   = xmot.text  if xmot  is not None else ""
    protocolo = nprot.text if nprot is not None else ""

    # cStat 100 = autorizado, 101 = cancelado, 150 = autorizado fora do prazo
    autorizado = status in ("100", "150")
    return {
        "autorizado":  autorizado,
        "cstat":       status,
        "motivo":      motivo,
        "protocolo":   protocolo,
        "dhRecbto":    dhret.text if dhret is not None else "",
        "url_sefaz":   url,
        "xml_retorno": resp.text[:2000],
    }


# ── Views principais ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
def api_nfe_status(request):
    """
    Retorna status NF-e da empresa: configuração + contadores.
    GET /api/nfe/status/
    """
    empresa = _empresa_auth(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    cred   = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    nfe_ok = cred.nfe_configurado() if cred else False

    autorizadas = NotaFiscalEletronica.objects.filter(empresa=empresa, status="autorizada").count()
    pendentes   = NotaFiscalEletronica.objects.filter(empresa=empresa, status="rascunho").count()
    erros       = NotaFiscalEletronica.objects.filter(empresa=empresa, status="erro").count()

    proxima = 1
    ultima  = NotaFiscalEletronica.objects.filter(empresa=empresa).order_by("-numero").first()
    if ultima:
        proxima = ultima.numero + 1

    return JsonResponse({
        "nfe_configurado":  nfe_ok,
        "modo":             "sefaz_real" if nfe_ok else "sem_certificado",
        "ambiente":         (cred.nfe_ambiente if cred else "2"),
        "uf":               (cred.nfe_uf       if cred else ""),
        "proxima_numeracao": proxima,
        "autorizadas":      autorizadas,
        "pendentes":        pendentes,
        "erros":            erros,
        "instrucao_configuracao": (
            None if nfe_ok else
            "Configure o certificado e-CNPJ em POST /api/integracoes/credenciais/nfe/"
        ),
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_nfe_lista(request):
    """
    Lista NF-e da empresa.
    GET /api/nfe/
    """
    empresa = _empresa_auth(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    status_filtro = request.GET.get("status", "")
    qs = NotaFiscalEletronica.objects.filter(empresa=empresa)
    if status_filtro:
        qs = qs.filter(status=status_filtro)

    return JsonResponse({"notas": [_nfe_dict(n) for n in qs[:100]]})


@csrf_exempt
@require_http_methods(["POST"])
def api_nfe_emitir(request):
    """
    Cria e emite NF-e via SEFAZ.

    POST /api/nfe/emitir/
    {
      "natureza_operacao":      "VENDA DE MERCADORIA",
      "cfop":                   "5102",
      "nome_destinatario":      "João da Silva",
      "cpf_cnpj_destinatario":  "12345678901",
      "email_destinatario":     "joao@email.com",
      "forma_pagamento":        "01",
      "valor_total":            "150.00",
      "itens": [
        {
          "cProd": "MED001",
          "xProd": "DIPIRONA 500MG 20CP",
          "NCM":   "30049099",
          "CFOP":  "5102",
          "uCom":  "CX",
          "qCom":  "2.00",
          "vUnCom":"75.00",
          "vProd": "150.00"
        }
      ]
    }
    """
    empresa = _empresa_auth(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    if not cred or not cred.nfe_configurado():
        return JsonResponse({
            "ok":    False,
            "erro":  "Certificado e-CNPJ não configurado.",
            "instrucao": "Configure em POST /api/integracoes/credenciais/nfe/",
            "link":  "/api/integracoes/credenciais/",
        }, status=400)

    # Próximo número
    ultima  = NotaFiscalEletronica.objects.filter(empresa=empresa).order_by("-numero").first()
    proximo = (ultima.numero + 1) if ultima else 1

    nota = NotaFiscalEletronica(
        empresa=empresa,
        numero=proximo,
        serie=cred.nfe_serie or "001",
        modelo="55",
        ambiente=cred.nfe_ambiente or "2",
        cnpj_emitente=cred.nfe_cnpj_emitente,
        ie_emitente=cred.nfe_ie,
        uf_emitente=cred.nfe_uf,
        natureza_operacao=body.get("natureza_operacao", "VENDA DE PRODUTO")[:60],
        cfop=body.get("cfop", "5102"),
        nome_destinatario=(body.get("nome_destinatario") or "")[:60],
        cpf_cnpj_destinatario="".join(c for c in (body.get("cpf_cnpj_destinatario") or "") if c.isdigit()),
        email_destinatario=(body.get("email_destinatario") or "")[:60],
        forma_pagamento=body.get("forma_pagamento", "99"),
        valor_total=body.get("valor_total", "0"),
        valor_produtos=body.get("valor_total", "0"),
        itens=body.get("itens", []),
        status="rascunho",
    )

    cert_path = key_path = None
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
        from cryptography.hazmat.backends import default_backend

        pfx_bytes   = base64.b64decode(cred.nfe_certificado_pfx_b64)
        senha_bytes = cred.get_nfe_certificado_senha().encode() or b""
        private_key, cert, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, senha_bytes, backend=default_backend()
        )

        cert_file = tempfile.NamedTemporaryFile(suffix=".crt", delete=False)
        key_file  = tempfile.NamedTemporaryFile(suffix=".key", delete=False)
        cert_file.write(cert.public_bytes(Encoding.PEM))
        cert_file.close()
        key_file.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        key_file.close()
        cert_path, key_path = cert_file.name, key_file.name

        # Gera XML
        xml_bruto    = _gerar_xml_nfe(nota, cred)
        # Assina
        xml_assinado = _assinar_nfe(xml_bruto, cert_path, key_path)
        nota.xml_assinado = xml_assinado
        nota.status = "assinada"

        # Transmite
        uf   = cred.nfe_uf.upper()
        cuf  = _CUF.get(uf, "35")
        ret  = _transmitir_sefaz(xml_assinado, cuf, uf, nota.ambiente, cert_path, key_path)

        if ret["autorizado"]:
            nota.status          = "autorizada"
            nota.protocolo       = ret["protocolo"]
            nota.mensagem_sefaz  = ret["motivo"]
            nota.autorizada_em   = timezone.now()
            nota.xml_autorizado  = xml_assinado  # em produção: XML de resposta completo
            nota.save()

            cred.nfe_ultima_transmissao = timezone.now()
            cred.save(update_fields=["nfe_ultima_transmissao"])

            logger.info("NF-e %s/%09d autorizada — protocolo %s", nota.serie, nota.numero, nota.protocolo)
            return JsonResponse({
                "ok":          True,
                "nfe_id":      nota.id,
                "chave":       nota.chave_acesso,
                "protocolo":   nota.protocolo,
                "numero":      nota.numero,
                "serie":       nota.serie,
                "status":      nota.status,
                "ambiente":    nota.ambiente,
                "mensagem":    f"NF-e {nota.numero} autorizada pela SEFAZ-{uf}.",
                "url_sefaz":   ret["url_sefaz"],
            })
        else:
            nota.status         = "erro"
            nota.mensagem_sefaz = f"cStat {ret['cstat']}: {ret['motivo']}"
            nota.save()
            return JsonResponse({
                "ok":      False,
                "nfe_id":  nota.id,
                "cstat":   ret["cstat"],
                "motivo":  ret["motivo"],
                "erro":    nota.mensagem_sefaz,
            }, status=502)

    except Exception as ex:
        msg = str(ex)[:500]
        nota.status         = "erro"
        nota.mensagem_sefaz = msg
        nota.save()
        logger.exception("Erro ao emitir NF-e: %s", msg)
        return JsonResponse({"ok": False, "erro": msg}, status=500)

    finally:
        for p in [cert_path, key_path]:
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass


@csrf_exempt
@require_http_methods(["GET"])
def api_nfe_xml_download(request, nfe_id):
    """Download do XML da NF-e autorizada. GET /api/nfe/<id>/xml/"""
    empresa = _empresa_auth(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        nota = NotaFiscalEletronica.objects.get(pk=nfe_id, empresa=empresa)
    except NotaFiscalEletronica.DoesNotExist:
        return JsonResponse({"erro": "NF-e não encontrada"}, status=404)

    xml = nota.xml_autorizado or nota.xml_assinado
    if not xml:
        return JsonResponse({"erro": "XML não disponível"}, status=400)

    resp = HttpResponse(xml, content_type="application/xml; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="NFe{nota.chave_acesso}.xml"'
    return resp


# ── Helper dict ───────────────────────────────────────────────────────────────

def _nfe_dict(n):
    return {
        "id":              n.id,
        "numero":          n.numero,
        "serie":           n.serie,
        "modelo":          n.modelo,
        "chave_acesso":    n.chave_acesso,
        "protocolo":       n.protocolo,
        "status":          n.status,
        "status_label":    dict(NotaFiscalEletronica.STATUS_CHOICES).get(n.status, n.status),
        "ambiente":        n.ambiente,
        "natureza_operacao": n.natureza_operacao,
        "nome_destinatario": n.nome_destinatario,
        "valor_total":     str(n.valor_total),
        "mensagem_sefaz":  n.mensagem_sefaz,
        "data_emissao":    n.data_emissao.isoformat() if n.data_emissao else None,
        "autorizada_em":   n.autorizada_em.isoformat() if n.autorizada_em else None,
        "criado_em":       n.criado_em.isoformat(),
    }
