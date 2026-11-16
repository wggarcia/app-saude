"""
ACS — Agente Comunitário de Saúde + Visitas Domiciliares + Fichas de Acompanhamento
e-SUS Atenção Básica / CDS — Portaria MS 1.412/2013.

Transmissão ao SISAB:
  O SISAB não tem API REST pública. Sistemas de terceiros entregam ao PEC
  arquivos LEDI APS (Thrift ou XML), que o PEC sincroniza com o nacional.
  Este módulo gera um .zip de arquivos .esus no modelo LEDI APS 8.7 para o
  operador importar no PEC (ver serializar_ficha_ledi para a ressalva do XSD).
  No sentido inverso, visitas já registradas no PEC entram pela ingestão
  (api_ingestao_visitas_pec) e nunca são reexportadas.
"""
import json
import logging
import time
import uuid
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import api_requer_permissao_modulo
from .utils import validar_cpf_cadastro

logger = logging.getLogger(__name__)


def _get_acs_models():
    from .models import AgenteComunidadeSaude, VisitaDomiciliar, FichaAcompanhamento
    return AgenteComunidadeSaude, VisitaDomiciliar, FichaAcompanhamento


# ── Cadastro de ACS ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_acs_lista(request):
    """GET/POST /api/governo/acs/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgenteComunidadeSaude, *_ = _get_acs_models()

    if request.method == "GET":
        qs = AgenteComunidadeSaude.objects.filter(empresa=empresa)
        ativo_f = request.GET.get("ativo")
        microarea_f = request.GET.get("microarea")
        q = request.GET.get("q")

        if ativo_f == "true":
            qs = qs.filter(ativo=True)
        elif ativo_f == "false":
            qs = qs.filter(ativo=False)
        if microarea_f:
            qs = qs.filter(microarea=microarea_f)
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(cpf=q) | Q(cns=q))

        return JsonResponse({
            "total": qs.count(),
            "ativos": qs.filter(ativo=True).count(),
            "agentes": [
                {
                    "id": a.id,
                    "nome": a.nome,
                    "cpf": a.cpf,
                    "cns": a.cns,
                    "cnes_usf": a.cnes_usf,
                    "ine_equipe": a.ine_equipe,
                    "microarea": a.microarea,
                    "municipio_ibge": a.municipio_ibge,
                    "ativo": a.ativo,
                    "data_admissao": a.data_admissao.isoformat() if a.data_admissao else None,
                }
                for a in qs.order_by("microarea", "nome")
            ],
        })

    data = json.loads(request.body)
    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf", ""), empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    with transaction.atomic():
        acs = AgenteComunidadeSaude.objects.create(
            empresa=empresa,
            nome=data["nome"],
            cpf=data.get("cpf", ""),
            cns=data.get("cns", ""),
            registro=data.get("registro", ""),
            cnes_usf=data.get("cnes_usf", ""),
            ine_equipe=data.get("ine_equipe", ""),
            microarea=data.get("microarea", ""),
            municipio_ibge=data.get("municipio_ibge", ""),
            data_admissao=data.get("data_admissao"),
            obs=data.get("obs", ""),
        )
    return JsonResponse({"id": acs.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_acs_detalhe(request, acs_id):
    """GET/PUT /api/governo/acs/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgenteComunidadeSaude, *_ = _get_acs_models()
    try:
        acs = AgenteComunidadeSaude.objects.get(id=acs_id, empresa=empresa)
    except AgenteComunidadeSaude.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": acs.id,
            "nome": acs.nome,
            "cpf": acs.cpf,
            "cns": acs.cns,
            "registro": acs.registro,
            "cnes_usf": acs.cnes_usf,
            "ine_equipe": acs.ine_equipe,
            "microarea": acs.microarea,
            "municipio_ibge": acs.municipio_ibge,
            "ativo": acs.ativo,
            "data_admissao": acs.data_admissao.isoformat() if acs.data_admissao else None,
            "obs": acs.obs,
        })

    data = json.loads(request.body)
    campos = ["nome", "cnes_usf", "ine_equipe", "microarea", "municipio_ibge", "ativo", "obs"]
    for c in campos:
        if c in data:
            setattr(acs, c, data[c])
    acs.save()
    return JsonResponse({"ok": True})


# ── Visitas Domiciliares ───────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_visitas_lista(request):
    """GET/POST /api/governo/acs/visitas/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgenteComunidadeSaude, VisitaDomiciliar, _ = _get_acs_models()

    if request.method == "GET":
        qs = VisitaDomiciliar.objects.filter(empresa=empresa).select_related("acs")
        acs_f    = request.GET.get("acs_id")
        motivo_f = request.GET.get("motivo")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        nao_transm = request.GET.get("nao_transmitido")
        q        = request.GET.get("q")

        if acs_f:
            qs = qs.filter(acs_id=acs_f)
        if motivo_f:
            qs = qs.filter(motivo=motivo_f)
        if data_ini:
            qs = qs.filter(data_visita__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_visita__lte=data_fim)
        if nao_transm == "true":
            qs = qs.filter(transmitido_esus=False)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "visitas": [
                {
                    "id": v.id,
                    "acs_nome": v.acs.nome,
                    "acs_microarea": v.acs.microarea,
                    "paciente_nome": v.paciente_nome,
                    "cpf_paciente": v.cpf_paciente,
                    "data_visita": v.data_visita.isoformat(),
                    "turno": v.turno,
                    "turno_display": v.get_turno_display(),
                    "motivo": v.motivo,
                    "motivo_display": v.get_motivo_display(),
                    "desfecho": v.desfecho,
                    "desfecho_display": v.get_desfecho_display(),
                    "gestante": v.gestante,
                    "transmitido_esus": v.transmitido_esus,
                    "uuid_esus": v.uuid_esus,
                    "origem": v.origem,
                }
                for v in qs.order_by("-data_visita")[:300]
            ],
        })

    data = json.loads(request.body)
    try:
        acs = AgenteComunidadeSaude.objects.get(id=data["acs_id"], empresa=empresa)
    except AgenteComunidadeSaude.DoesNotExist:
        return JsonResponse({"erro": "ACS não encontrado"}, status=404)

    # UUID e-SUS gerado automaticamente
    uuid_esus = str(uuid.uuid4())

    with transaction.atomic():
        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        visita = VisitaDomiciliar.objects.create(
            empresa=empresa,
            acs=acs,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            data_visita=data.get("data_visita", date.today().isoformat()),
            turno=data.get("turno", "M"),
            motivo=data["motivo"],
            desfecho=data.get("desfecho", "visita_realizada"),
            peso_kg=data.get("peso_kg"),
            pa_sistolica=data.get("pa_sistolica"),
            pa_diastolica=data.get("pa_diastolica"),
            glicemia=data.get("glicemia"),
            gestante=data.get("gestante", False),
            ig_semanas=data.get("ig_semanas"),
            uuid_esus=uuid_esus,
            obs=data.get("obs", ""),
        )
    return JsonResponse({"id": visita.id, "uuid_esus": uuid_esus}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_visita_detalhe(request, visita_id):
    """GET/PUT /api/governo/acs/visitas/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, VisitaDomiciliar, _ = _get_acs_models()
    try:
        visita = VisitaDomiciliar.objects.get(id=visita_id, empresa=empresa)
    except VisitaDomiciliar.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": visita.id,
            "acs_id": visita.acs_id,
            "acs_nome": visita.acs.nome,
            "paciente_nome": visita.paciente_nome,
            "cpf_paciente": visita.cpf_paciente,
            "cns_paciente": visita.cns_paciente,
            "data_visita": visita.data_visita.isoformat(),
            "turno": visita.turno,
            "motivo": visita.motivo,
            "motivo_display": visita.get_motivo_display(),
            "desfecho": visita.desfecho,
            "desfecho_display": visita.get_desfecho_display(),
            "peso_kg": float(visita.peso_kg) if visita.peso_kg else None,
            "pa_sistolica": visita.pa_sistolica,
            "pa_diastolica": visita.pa_diastolica,
            "glicemia": float(visita.glicemia) if visita.glicemia else None,
            "gestante": visita.gestante,
            "ig_semanas": visita.ig_semanas,
            "uuid_esus": visita.uuid_esus,
            "transmitido_esus": visita.transmitido_esus,
            "obs": visita.obs,
        })

    data = json.loads(request.body)
    campos = ["desfecho", "peso_kg", "pa_sistolica", "pa_diastolica",
              "glicemia", "gestante", "ig_semanas", "obs", "transmitido_esus"]
    for c in campos:
        if c in data:
            setattr(visita, c, data[c])
    visita.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_visitas_transmitir_esus(request):
    """
    POST /api/governo/acs/visitas/transmitir-esus/

    Prévia da exportação LEDI APS das visitas pendentes: quantas fichas sairão,
    quais visitas ficam de fora por falta de dado obrigatório. O arquivo em si
    é baixado em GET /api/governo/acs/visitas/exportar-cds/ (.zip de .esus).
    """
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    body = json.loads(request.body) if request.body else {}
    visitas = _visitas_exportaveis(empresa, body.get("data_inicio"))
    if not visitas:
        return JsonResponse({"ok": True, "fichas": 0, "visitas": 0,
                             "mensagem": "Nenhuma visita pendente para exportação"})

    pacotes, pendencias = montar_fichas_visita_ledi(visitas, empresa)
    return JsonResponse({
        "ok": True,
        "visitas": sum(len(p["ficha"]["visitasDomiciliares"]) for p in pacotes),
        "fichas": len(pacotes),
        "visitas_com_pendencia": pendencias,
        "status": "arquivo_gerado_pendente_importacao_pec",
        "aviso": AVISO_FORMATO_LEDI,
        "instrucoes": [
            "1. Baixe o arquivo .zip (botão Exportar).",
            "2. No PEC da UBS, importe os arquivos .esus do pacote.",
            "3. Confira no PEC se as fichas foram aceitas.",
            "4. Só depois confirme a transmissão das visitas aqui.",
        ],
        "referencia": "LEDI APS 8.7 — Ficha de Visita Domiciliar e Territorial",
    })


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_visitas_exportar_cds(request):
    """GET /api/governo/acs/visitas/exportar-cds/ — baixa o .zip com um .esus por ficha."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    visitas = _visitas_exportaveis(empresa, request.GET.get("data_inicio"))
    pacotes, _ = montar_fichas_visita_ledi(visitas, empresa)
    if not pacotes:
        return JsonResponse({"erro": "Nenhuma visita pendente com os dados obrigatórios do e-SUS "
                                     "(CNS do ACS, CNES e código IBGE)."}, status=404)

    response = HttpResponse(empacotar_zip_esus(pacotes), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="esus_visitas_{date.today().isoformat()}.zip"'
    return response


def _visitas_exportaveis(empresa, data_ini=None):
    """Pendentes de envio, criadas no SoloCRT. Visita que veio do PEC já está no
    e-SUS — reexportar duplicaria a produção no SISAB."""
    _, VisitaDomiciliar, _ = _get_acs_models()
    qs = (VisitaDomiciliar.objects
          .filter(empresa=empresa, transmitido_esus=False)
          .exclude(origem="pec")
          .select_related("acs"))
    if data_ini:
        qs = qs.filter(data_visita__gte=data_ini)
    return list(qs.order_by("acs_id", "data_visita", "id")[:2000])


# ── LEDI APS 8.7 — Ficha de Visita Domiciliar e Territorial ───────────────────
# Dicionário oficial: integracao.esusaps.bridge.ufsc.tech (dicionario-fvd.html,
# dicionario.html, camada-transporte.html, header-transport.html, versao.html).

LEDI_VERSAO = {"major": 8, "minor": 7, "revision": 0}
LEDI_TIPO_DADO_VISITA_DOMICILIAR = 8
LEDI_TP_CDS_ORIGEM = 3
LEDI_MAX_VISITAS_POR_FICHA = 99
CBO_ACS = "515105"
SOFTWARE_NOME = "SoloCRT"
SOFTWARE_VERSAO = "2.0"
LEDI_TIPO_IMOVEL_DOMICILIO = 1
LEDI_MOTIVO_GESTANTE = 5
LEDI_MOTIVO_OUTROS = 28
AVISO_FORMATO_LEDI = (
    "Arquivo montado segundo o modelo de dados LEDI APS 8.7 (Ficha de Visita "
    "Domiciliar e Territorial). Os arquivos XSD oficiais não são públicos, então "
    "o formato precisa ser validado na primeira importação num PEC antes de uso "
    "em produção."
)

_TURNO_CDS = {"M": 1, "T": 2, "N": 3}
_DESFECHO_CDS = {"visita_realizada": 1, "recusou": 2, "ausente": 3}
_MOTIVO_CDS = {
    "cadastramento":           [1],
    "visita_rotineira":        [29],
    "acompanhamento":          [30],   # rotulado "Acompanhamento de Condicionalidades" (Bolsa Família)
    "busca_ativa":             [LEDI_MOTIVO_OUTROS],  # LEDI não tem código de busca ativa
    "pre_natal":               [LEDI_MOTIVO_GESTANTE],
    "puericultura":            [8],
    "pessoa_idosa":            [38],
    "portador_doenca_cronica": [16],
    "saude_mental":            [22],
    "domiciliado":             [19],
    "egresso_internacao":      [25],
    "obito":                   [LEDI_MOTIVO_OUTROS],  # LEDI não tem código de verificação de óbito
    "outro":                   [LEDI_MOTIVO_OUTROS],
}


def _epoch_ms(d):
    from datetime import datetime, time as dtime
    from zoneinfo import ZoneInfo
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return int(datetime.combine(d, dtime.min, tzinfo=ZoneInfo("America/Sao_Paulo")).timestamp() * 1000)


def _so_digitos(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())


def _ibge_fallback(empresa):
    try:
        from .models import CredenciaisIntegracoes
        cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
        return (getattr(cred, "sus_ibge", "") or getattr(cred, "rnds_ibge", "")) if cred else ""
    except Exception:
        return ""


def _dado_instalacao(empresa):
    return {
        "contraChave": f"{SOFTWARE_NOME} - {SOFTWARE_VERSAO}",
        "uuidInstalacao": str(uuid.uuid5(uuid.NAMESPACE_URL, f"solocrt:empresa:{empresa.id}")),
        "cpfOuCnpj": _so_digitos(getattr(empresa, "cnpj", "")),
        "nomeOuRazaoSocial": empresa.nome,
    }


def _visita_child(v):
    motivos = list(_MOTIVO_CDS.get(v.motivo, [LEDI_MOTIVO_OUTROS]))
    if v.gestante and LEDI_MOTIVO_GESTANTE not in motivos:
        motivos.append(LEDI_MOTIVO_GESTANTE)
    child = {
        "turno": _TURNO_CDS.get(v.turno, 1),
        "motivosVisita": motivos,
        "desfecho": _DESFECHO_CDS.get(v.desfecho, 1),
        "stForaArea": False,
        "tipoDeImovel": LEDI_TIPO_IMOVEL_DOMICILIO,
    }
    if v.acs.microarea:
        child["microarea"] = v.acs.microarea
    if v.cns_paciente:
        child["cnsCidadao"] = _so_digitos(v.cns_paciente)
    if v.cpf_paciente:
        child["cpfCidadao"] = _so_digitos(v.cpf_paciente)
    if v.peso_kg is not None:
        child["pesoAcompanhamentoNutricional"] = float(v.peso_kg)
    if v.pa_sistolica:
        child["pressaoSistolica"] = int(v.pa_sistolica)
    if v.pa_diastolica:
        child["pressaoDiastolica"] = int(v.pa_diastolica)
    if v.glicemia is not None:
        child["glicemia"] = float(v.glicemia)
    return child


def montar_fichas_visita_ledi(visitas, empresa):
    """Agrupa por profissional + dia (o header LEDI é de lotação única) e quebra
    em fichas de até 99 visitas. Visita sem CNS do ACS, CNES ou IBGE não entra:
    o PEC rejeitaria a ficha inteira. Devolve (pacotes, pendencias)."""
    ibge_padrao = _ibge_fallback(empresa)
    instalacao = _dado_instalacao(empresa)
    grupos, pendencias = {}, []

    for v in visitas:
        acs = v.acs
        cns = _so_digitos(acs.cns)
        cnes = _so_digitos(acs.cnes_usf)
        ibge = _so_digitos(acs.municipio_ibge) or _so_digitos(ibge_padrao)
        faltando = [n for n, val, tam in (("CNS do ACS", cns, 15), ("CNES", cnes, 7), ("código IBGE", ibge, 7))
                    if len(val) != tam]
        if faltando:
            pendencias.append({"visita_id": v.id, "acs": acs.nome, "faltando": faltando})
            continue
        chave = (acs.id, v.data_visita)
        grupos.setdefault(chave, {"acs": acs, "cns": cns, "cnes": cnes, "ibge": ibge,
                                  "data": v.data_visita, "visitas": []})["visitas"].append(v)

    pacotes = []
    for g in grupos.values():
        ine = _so_digitos(g["acs"].ine_equipe)
        for i in range(0, len(g["visitas"]), LEDI_MAX_VISITAS_POR_FICHA):
            lote = g["visitas"][i:i + LEDI_MAX_VISITAS_POR_FICHA]
            uuid_ficha = str(uuid.uuid4())
            header = {
                "profissionalCNS": g["cns"],
                "cboCodigo_2002": CBO_ACS,
                "cnes": g["cnes"],
                "dataAtendimento": _epoch_ms(g["data"]),
                "codigoIbgeMunicipio": g["ibge"],
            }
            if ine:
                header["ine"] = ine
            ficha = {
                "uuidFicha": uuid_ficha,
                "tpCdsOrigem": LEDI_TP_CDS_ORIGEM,
                "headerTransport": header,
                "visitasDomiciliares": [_visita_child(v) for v in lote],
            }
            envelope = {
                "uuidDadoSerializado": uuid_ficha,
                "tipoDadoSerializado": LEDI_TIPO_DADO_VISITA_DOMICILIAR,
                "cnesDadoSerializado": g["cnes"],
                "codIbge": g["ibge"],
                "remetente": instalacao,
                "originadora": instalacao,
                "versao": LEDI_VERSAO,
            }
            if ine:
                envelope["ineDadoSerializado"] = ine
            pacotes.append({"envelope": envelope, "ficha": ficha,
                            "visita_ids": [v.id for v in lote]})
    return pacotes, pendencias


def _xml_valor(el, nome, valor):
    from xml.etree.ElementTree import SubElement
    if isinstance(valor, dict):
        filho = SubElement(el, nome)
        for k, val in valor.items():
            _xml_valor(filho, k, val)
    elif isinstance(valor, list):
        for item in valor:
            _xml_valor(el, nome, item)
    else:
        SubElement(el, nome).text = ("true" if valor else "false") if isinstance(valor, bool) else str(valor)


def serializar_ficha_ledi(pacote) -> bytes:
    """ÚNICO ponto de serialização. Sem os XSD oficiais, os elementos levam o nome
    exato dos campos do dicionário LEDI, sem namespace. Trocar só esta função
    quando o formato for validado num PEC real."""
    from xml.etree.ElementTree import Element, tostring
    raiz = Element("DadoTransporte")
    for k, val in pacote["envelope"].items():
        _xml_valor(raiz, k, val)
    _xml_valor(raiz, "dadoSerializado", {"FichaVisitaDomiciliarMaster": pacote["ficha"]})
    return tostring(raiz, encoding="utf-8", xml_declaration=True)


def empacotar_zip_esus(pacotes) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pacotes:
            zf.writestr(f"{p['envelope']['uuidDadoSerializado']}.esus", serializar_ficha_ledi(p))
    return buf.getvalue()


# ── Fichas de Acompanhamento ───────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_fichas_acompanhamento(request):
    """GET/POST /api/governo/acs/fichas/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgenteComunidadeSaude, _, FichaAcompanhamento = _get_acs_models()

    if request.method == "GET":
        qs = FichaAcompanhamento.objects.filter(empresa=empresa)
        condicao_f = request.GET.get("condicao")
        microarea_f = request.GET.get("microarea")
        ativo_f    = request.GET.get("em_acompanhamento")
        q          = request.GET.get("q")

        if condicao_f:
            qs = qs.filter(condicao_saude=condicao_f)
        if microarea_f:
            qs = qs.filter(microarea=microarea_f)
        if ativo_f == "true":
            qs = qs.filter(em_acompanhamento=True)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "em_acompanhamento": qs.filter(em_acompanhamento=True).count(),
            "fichas": [
                {
                    "id": f.id,
                    "paciente_nome": f.paciente_nome,
                    "cpf_paciente": f.cpf_paciente,
                    "condicao_saude": f.condicao_saude,
                    "condicao_saude_display": f.get_condicao_saude_display(),
                    "microarea": f.microarea,
                    "em_acompanhamento": f.em_acompanhamento,
                    "data_inicio_acomp": f.data_inicio_acomp.isoformat() if f.data_inicio_acomp else None,
                    "acs_nome": f.acs.nome if f.acs else None,
                }
                for f in qs.order_by("condicao_saude", "paciente_nome")[:300]
            ],
        })

    data = json.loads(request.body)
    acs = None
    if data.get("acs_id"):
        try:
            acs = AgenteComunidadeSaude.objects.get(id=data["acs_id"], empresa=empresa)
        except AgenteComunidadeSaude.DoesNotExist:
            return JsonResponse({"erro": "ACS não encontrado"}, status=404)

    with transaction.atomic():
        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        ficha = FichaAcompanhamento.objects.create(
            empresa=empresa,
            acs=acs,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            data_nascimento=data.get("data_nascimento"),
            condicao_saude=data["condicao_saude"],
            logradouro=data.get("logradouro", ""),
            numero=data.get("numero", ""),
            bairro=data.get("bairro", ""),
            municipio_ibge=data.get("municipio_ibge", ""),
            microarea=data.get("microarea", acs.microarea if acs else ""),
            em_acompanhamento=True,
            data_inicio_acomp=date.today(),
            obs=data.get("obs", ""),
        )
    return JsonResponse({"id": ficha.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_ficha_detalhe(request, ficha_id):
    """GET/PUT /api/governo/acs/fichas/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, FichaAcompanhamento = _get_acs_models()
    try:
        ficha = FichaAcompanhamento.objects.get(id=ficha_id, empresa=empresa)
    except FichaAcompanhamento.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": ficha.id,
            "paciente_nome": ficha.paciente_nome,
            "cpf_paciente": ficha.cpf_paciente,
            "cns_paciente": ficha.cns_paciente,
            "data_nascimento": ficha.data_nascimento.isoformat() if ficha.data_nascimento else None,
            "condicao_saude": ficha.condicao_saude,
            "condicao_saude_display": ficha.get_condicao_saude_display(),
            "logradouro": ficha.logradouro,
            "numero": ficha.numero,
            "bairro": ficha.bairro,
            "municipio_ibge": ficha.municipio_ibge,
            "microarea": ficha.microarea,
            "em_acompanhamento": ficha.em_acompanhamento,
            "data_inicio_acomp": ficha.data_inicio_acomp.isoformat() if ficha.data_inicio_acomp else None,
            "data_fim_acomp": ficha.data_fim_acomp.isoformat() if ficha.data_fim_acomp else None,
            "acs": {"id": ficha.acs.id, "nome": ficha.acs.nome} if ficha.acs else None,
            "obs": ficha.obs,
        })

    data = json.loads(request.body)
    campos = ["condicao_saude", "em_acompanhamento", "data_fim_acomp", "obs",
              "logradouro", "bairro", "microarea"]
    for c in campos:
        if c in data:
            setattr(ficha, c, data[c])
    ficha.save()
    return JsonResponse({"ok": True})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_acs_kpis(request):
    """GET /api/governo/acs/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgenteComunidadeSaude, VisitaDomiciliar, FichaAcompanhamento = _get_acs_models()

    hoje    = date.today()
    mes_ini = hoje.replace(day=1)
    semana_ini = hoje - timedelta(days=hoje.weekday())

    acs_total  = AgenteComunidadeSaude.objects.filter(empresa=empresa, ativo=True).count()
    visitas_mes = VisitaDomiciliar.objects.filter(empresa=empresa, data_visita__gte=mes_ini)
    por_motivo  = dict(
        visitas_mes.values_list("motivo").annotate(n=Count("id")).order_by()
    )
    por_desfecho = dict(
        visitas_mes.values_list("desfecho").annotate(n=Count("id")).order_by()
    )
    pendentes_esus = VisitaDomiciliar.objects.filter(
        empresa=empresa, transmitido_esus=False,
        desfecho="visita_realizada",
    ).count()
    gestantes_acomp = FichaAcompanhamento.objects.filter(
        empresa=empresa, condicao_saude="gestante", em_acompanhamento=True
    ).count()
    por_condicao = dict(
        FichaAcompanhamento.objects.filter(empresa=empresa, em_acompanhamento=True)
        .values_list("condicao_saude").annotate(n=Count("id")).order_by()
    )

    return JsonResponse({
        "acs_ativos": acs_total,
        "visitas_mes": visitas_mes.count(),
        "visitas_por_motivo_mes": por_motivo,
        "visitas_por_desfecho_mes": por_desfecho,
        "pendentes_transmissao_esus": pendentes_esus,
        "gestantes_em_acompanhamento": gestantes_acomp,
        "acompanhamentos_por_condicao": por_condicao,
    })
