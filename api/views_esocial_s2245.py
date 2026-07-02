"""
eSocial S-2245 — Treinamentos, Capacitações, Exercícios Simulados e Outras Anotações.

Implementação completa conforme leiaute eSocial S-1.3 (Nota Técnica 006/2023 MTE).

Referência: https://www.gov.br/esocial/pt-br/documentacao-tecnica/leiautes
Schema XSD: evtTreiCap — v_S_01_03_00

Fluxo:
  1. Usuário registra TreinamentoNR com dado de funcionário
  2. Sistema gera XML S-2245 conforme XSD oficial
  3. XML assinado com certificado A1/A3 (pkcs12) da empresa
  4. Envio ao webservice eSocial via HTTPS (Serpro)
  5. Retorno: protocolo de recibo ou mensagem de erro
"""

import hashlib
import json
import re
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import (
    TreinamentoNR, FuncionarioSST, Empresa, eSocialEventoSST, ConfiguracaoSST,
)
from .views_dashboard import _empresa_autenticada
from .access_control import api_requer_feature
from .esocial_transmissao import transmitir_evento

# ─── Mapeamento código de treinamento por NR ──────────────────────────────────
# Fonte: Anexo II do Leiaute eSocial S-1.3 — Tabela 25 (CodTrein)

NR_PARA_COD_TREIN = {
    "NR-5":  "001",  # CIPA
    "NR-6":  "002",  # EPI
    "NR-7":  "003",  # PCMSO / Saúde Ocupacional
    "NR-9":  "004",  # Agentes de Risco
    "NR-10": "005",  # Segurança em Eletricidade
    "NR-11": "006",  # Transporte, Movimentação, Armazenagem
    "NR-12": "007",  # Segurança em Máquinas e Equipamentos
    "NR-13": "008",  # Caldeiras, Vasos de Pressão e Tubulações
    "NR-15": "009",  # Atividades e Operações Insalubres
    "NR-16": "010",  # Atividades e Operações Perigosas
    "NR-17": "011",  # Ergonomia
    "NR-18": "012",  # Condições e Meio Ambiente — Construção Civil
    "NR-20": "013",  # Inflamáveis e Combustíveis
    "NR-23": "014",  # Proteção Contra Incêndios
    "NR-25": "015",  # Resíduos Industriais
    "NR-32": "016",  # Segurança e Saúde no Trabalho em Serviços de Saúde
    "NR-33": "017",  # Espaços Confinados
    "NR-34": "018",  # Construção Naval
    "NR-35": "019",  # Trabalho em Altura
    "NR-36": "020",  # Abatedouros e Indústrias de Carnes
    "outro": "999",  # Outros treinamentos
}

NS_S2245 = "http://www.esocial.gov.br/schema/evt/evtTreiCap/v_S_01_03_00"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cnpj(v):
    return re.sub(r"\D", "", v or "")[:14]

def _cpf(v):
    return re.sub(r"\D", "", v or "")[:11]

def _nis(v):
    return re.sub(r"\D", "", v or "")[:11]

def _tp_amb(cfg):
    amb = (getattr(cfg, "esocial_ambiente", "") or "").lower()
    return "1" if amb in {"producao", "produção", "prod"} else "2"

def _evt_id(cnpj, seq):
    return f"IDS2245{_cnpj(cnpj)}{date.today().strftime('%Y%m%d')}{seq:05d}"

def _xml_bonito(root):
    raw = tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    return "\n".join(pretty.split("\n")[1:])


# ─── Gerador XML S-2245 ───────────────────────────────────────────────────────

def gerar_xml_s2245(treinamento: TreinamentoNR, cfg) -> str:
    """
    Gera o XML do evento S-2245 conforme leiaute eSocial S-1.3.
    
    Estrutura:
      eSocial
        evtTreiCap (Id="...")
          ideEvento
          ideEmpregador
          trabalhador
          infoTreiCap
            iniValid / fimValid
            treinamento (1..N)
              codTrein
              obsComp
    """
    func = treinamento.funcionario
    empresa = treinamento.empresa
    cnpj = _cnpj(cfg.cnpj if cfg else getattr(empresa, "cnpj", ""))
    cpf  = _cpf(getattr(func, "cpf", ""))
    nis  = _nis(getattr(func, "pis", getattr(func, "nis", "")))

    evt_id = _evt_id(cnpj, treinamento.pk)
    
    # Data realização: AAAA-MM-DD
    dt_realiz = treinamento.data_realizacao
    ano_mes_ini = dt_realiz.strftime("%Y-%m") if dt_realiz else date.today().strftime("%Y-%m")
    # Validade: AAAA-MM (fim da validade)
    dt_valid = treinamento.data_validade
    ano_mes_fim = dt_valid.strftime("%Y-%m") if dt_valid else ""

    root = Element("eSocial", xmlns=NS_S2245,
                   **{"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"})
    evt  = SubElement(root, "evtTreiCap", Id=evt_id)

    # ideEvento
    ide_evt = SubElement(evt, "ideEvento")
    SubElement(ide_evt, "indRetif").text = "1"        # 1=original, 2=retificação
    SubElement(ide_evt, "tpAmb").text    = _tp_amb(cfg)
    SubElement(ide_evt, "procEmi").text  = "1"        # 1=aplicativo do empregador
    SubElement(ide_evt, "verProc").text  = "SolusCRT-1.0"

    # ideEmpregador
    ide_emp = SubElement(evt, "ideEmpregador")
    SubElement(ide_emp, "tpInsc").text = "1"          # 1=CNPJ
    SubElement(ide_emp, "nrInsc").text = cnpj[:8]     # raiz do CNPJ (8 dígitos)

    # trabalhador
    trab = SubElement(evt, "trabalhador")
    SubElement(trab, "cpfTrab").text = cpf
    if nis:
        SubElement(trab, "nisTrab").text = nis

    # infoTreiCap
    info = SubElement(evt, "infoTreiCap")
    SubElement(info, "iniValid").text = ano_mes_ini

    if ano_mes_fim:
        SubElement(info, "fimValid").text = ano_mes_fim

    # treinamento (item principal)
    trein_el = SubElement(info, "treinamento")
    cod = NR_PARA_COD_TREIN.get(treinamento.nr, "999")
    SubElement(trein_el, "codTrein").text = cod

    # Observação complementar — inclui detalhes ricos
    obs_parts = []
    if treinamento.titulo:
        obs_parts.append(f"Título: {treinamento.titulo}")
    if treinamento.instrutor:
        obs_parts.append(f"Instrutor: {treinamento.instrutor}")
    if treinamento.carga_horaria:
        obs_parts.append(f"Carga horária: {treinamento.carga_horaria}h")
    if treinamento.certificado:
        obs_parts.append(f"Certificado: {treinamento.certificado}")
    obs_text = " | ".join(obs_parts) or treinamento.nr
    # Campo obsComp: máx 999 chars
    SubElement(trein_el, "obsComp").text = obs_text[:999]

    return _xml_bonito(root)


# ─── Views ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("sst.esocial")
def api_esocial_s2245_listar(request):
    """Lista eventos S-2245 da empresa com status de transmissão."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    eventos = eSocialEventoSST.objects.filter(
        empresa=empresa, tipo_evento="S-2245"
    ).order_by("-criado_em")[:100]

    data = []
    for ev in eventos:
        data.append({
            "id": ev.pk,
            "tipo": ev.tipo_evento,
            "status": ev.status,
            "referencia": ev.referencia,
            "protocolo": ev.protocolo,
            "mensagem_erro": ev.mensagem_erro,
            "data_envio": ev.data_envio.isoformat() if ev.data_envio else None,
            "criado_em": ev.criado_em.isoformat(),
        })

    return JsonResponse({"eventos": data, "total": len(data)})


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("sst.esocial")
def api_esocial_s2245_gerar(request, treinamento_id):
    """
    Gera o XML S-2245 para um treinamento e cria o evento na fila.
    POST /api/esocial/s2245/<treinamento_id>/gerar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    trein = TreinamentoNR.objects.filter(pk=treinamento_id, empresa=empresa).first()
    if not trein:
        return JsonResponse({"erro": "Treinamento não encontrado."}, status=404)

    if not trein.data_realizacao:
        return JsonResponse({"erro": "Treinamento sem data de realização — não pode gerar S-2245."}, status=400)

    if not trein.funcionario.cpf:
        return JsonResponse({"erro": "Funcionário sem CPF cadastrado — obrigatório para eSocial."}, status=400)

    try:
        cfg = empresa.configuracao_sst
    except Exception:
        cfg = None

    xml = gerar_xml_s2245(trein, cfg)

    # Cria/atualiza evento na fila
    evento, criado = eSocialEventoSST.objects.update_or_create(
        empresa=empresa,
        tipo_evento="S-2245",
        referencia=f"TreinamentoNR-{trein.pk}",
        defaults={
            "status": "pendente",
            "xml_gerado": xml,
            "mensagem_erro": "",
            "protocolo": "",
        }
    )

    return JsonResponse({
        "ok": True,
        "evento_id": evento.pk,
        "criado": criado,
        "xml_preview": xml[:800] + "..." if len(xml) > 800 else xml,
        "treinamento": {
            "id": trein.pk,
            "funcionario": trein.funcionario.nome,
            "nr": trein.nr,
            "data": trein.data_realizacao.isoformat() if trein.data_realizacao else None,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("sst.esocial")
def api_esocial_s2245_transmitir(request, evento_id):
    """
    Transmite evento S-2245 ao webservice eSocial (Serpro).
    POST /api/esocial/s2245/<evento_id>/transmitir/
    
    Requer certificado digital A1/A3 configurado em ConfiguracaoSST.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    evento = eSocialEventoSST.objects.filter(
        pk=evento_id, empresa=empresa, tipo_evento="S-2245"
    ).first()
    if not evento:
        return JsonResponse({"erro": "Evento S-2245 não encontrado."}, status=404)

    if not evento.xml_gerado:
        return JsonResponse({"erro": "XML não gerado. Chame /gerar/ primeiro."}, status=400)

    # Transmite via módulo esocial_transmissao (com certificado A1/A3)
    ok, msg = transmitir_evento(evento)
    return JsonResponse({"ok": ok, "mensagem": msg})


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("sst.esocial")
def api_esocial_s2245_xml(request, evento_id):
    """Download do XML S-2245 gerado."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    evento = eSocialEventoSST.objects.filter(
        pk=evento_id, empresa=empresa, tipo_evento="S-2245"
    ).first()
    if not evento or not evento.xml_gerado:
        return JsonResponse({"erro": "XML não encontrado."}, status=404)

    resp = HttpResponse(evento.xml_gerado, content_type="application/xml; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="S-2245-evento-{evento_id}.xml"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("sst.esocial")
def api_esocial_s2245_lote(request):
    """
    Gera e enfileira S-2245 para TODOS os treinamentos com status 'valido'
    que ainda não possuem evento gerado.
    POST /api/esocial/s2245/lote/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        cfg = empresa.configuracao_sst
    except Exception:
        cfg = None

    # Treinamentos válidos sem evento ainda
    referencia_existentes = set(
        eSocialEventoSST.objects.filter(
            empresa=empresa, tipo_evento="S-2245"
        ).values_list("referencia", flat=True)
    )

    treinamentos = TreinamentoNR.objects.filter(
        empresa=empresa, status="valido", data_realizacao__isnull=False
    ).select_related("funcionario")

    gerados = []
    erros = []

    for t in treinamentos:
        ref = f"TreinamentoNR-{t.pk}"
        if ref in referencia_existentes:
            continue
        if not t.funcionario.cpf:
            erros.append({"id": t.pk, "erro": "Funcionário sem CPF"})
            continue
        try:
            xml = gerar_xml_s2245(t, cfg)
            ev = eSocialEventoSST.objects.create(
                empresa=empresa,
                tipo_evento="S-2245",
                referencia=ref,
                status="pendente",
                xml_gerado=xml,
            )
            gerados.append({"treinamento_id": t.pk, "evento_id": ev.pk, "funcionario": t.funcionario.nome})
        except Exception as e:
            erros.append({"id": t.pk, "erro": str(e)})

    return JsonResponse({
        "ok": True,
        "gerados": len(gerados),
        "erros": len(erros),
        "detalhes_gerados": gerados,
        "detalhes_erros": erros,
    })
