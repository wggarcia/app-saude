"""
Hemoterapia — Banco de Sangue
Rastreabilidade de bolsas, solicitações de transfusão, registro de reações adversas
e notificação ANVISA (RDC 34/2014).

Notificação de Reação Transfusional:
  O sistema NOTIVISA/ANVISA NÃO disponibiliza REST API pública para integração
  direta. A notificação é realizada via:
    1. Geração de arquivo XML no padrão NOTIVISA (eSNVS — Esquema XML de Notificação
       de Vigilância Sanitária, publicado por ANVISA)
    2. Download do XML pelo operador
    3. Importação manual em https://notivisa.anvisa.gov.br (perfil "Notificador")
  O status "notificado_anvisa" é marcado True somente após confirmação manual.
  Ref: ANVISA — Manual NOTIVISA Hemovigilância (RDC 34/2014, art. 83)
"""
import base64
import json
import logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _get_hemo_models():
    from .models import BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, ReacaoTransfusional
    return BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, ReacaoTransfusional


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.hemoterapia", "Hemoterapia")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_hemoterapia_page(request):
    return render(request, "hospital_hemoterapia.html")


# ── Bolsas ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_bolsas(request):
    """GET/POST /api/hospital/hemoterapia/bolsas/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, *_ = _get_hemo_models()

    if request.method == "GET":
        qs = BolsaSangue.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        tipo_f   = request.GET.get("tipo")
        q        = request.GET.get("q")
        vencendo = request.GET.get("vencendo_dias")

        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        if q:
            qs = qs.filter(
                Q(codigo_bolsa__icontains=q) | Q(isbt128__icontains=q)
                | Q(doador_codigo__icontains=q)
            )
        if vencendo:
            try:
                limite = date.today() + timedelta(days=int(vencendo))
                qs = qs.filter(validade__lte=limite, validade__gte=date.today(),
                               status="disponivel")
            except ValueError:
                pass

        hoje = date.today()
        return JsonResponse({
            "total": qs.count(),
            "bolsas": [
                {
                    "id": b.id,
                    "codigo_bolsa": b.codigo_bolsa,
                    "tipo": b.tipo,
                    "tipo_display": b.get_tipo_display(),
                    "tipo_abo": b.tipo_abo,
                    "fator_rh": b.fator_rh,
                    "grupo_sanguineo": f"{b.tipo_abo}{b.fator_rh}",
                    "volume_ml": b.volume_ml,
                    "validade": b.validade.isoformat(),
                    "vencida": b.validade < hoje,
                    "dias_validade": (b.validade - hoje).days,
                    "status": b.status,
                    "status_display": b.get_status_display(),
                    "isbt128": b.isbt128,
                    "coletada_em": b.coletada_em.isoformat() if b.coletada_em else None,
                }
                for b in qs.order_by("validade")[:300]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        bolsa = BolsaSangue.objects.create(
            empresa=empresa,
            codigo_bolsa=data["codigo_bolsa"],
            tipo=data["tipo"],
            tipo_abo=data.get("tipo_abo", ""),
            fator_rh=data.get("fator_rh", ""),
            volume_ml=data.get("volume_ml"),
            doador_codigo=data.get("doador_codigo", ""),
            coletada_em=data.get("coletada_em"),
            processada_em=data.get("processada_em"),
            validade=data["validade"],
            isbt128=data.get("isbt128", ""),
            obs=data.get("obs", ""),
        )
    return JsonResponse({"id": bolsa.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_bolsa_detalhe(request, bolsa_id):
    """GET/PUT /api/hospital/hemoterapia/bolsas/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, *_ = _get_hemo_models()
    try:
        bolsa = BolsaSangue.objects.get(id=bolsa_id, empresa=empresa)
    except BolsaSangue.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": bolsa.id,
            "codigo_bolsa": bolsa.codigo_bolsa,
            "tipo": bolsa.tipo,
            "tipo_display": bolsa.get_tipo_display(),
            "tipo_abo": bolsa.tipo_abo,
            "fator_rh": bolsa.fator_rh,
            "volume_ml": bolsa.volume_ml,
            "doador_codigo": bolsa.doador_codigo,
            "coletada_em": bolsa.coletada_em.isoformat() if bolsa.coletada_em else None,
            "processada_em": bolsa.processada_em.isoformat() if bolsa.processada_em else None,
            "validade": bolsa.validade.isoformat(),
            "status": bolsa.status,
            "status_display": bolsa.get_status_display(),
            "isbt128": bolsa.isbt128,
            "obs": bolsa.obs,
        })

    data = json.loads(request.body)
    campos = ["status", "tipo_abo", "fator_rh", "volume_ml", "isbt128", "obs"]
    for c in campos:
        if c in data:
            setattr(bolsa, c, data[c])
    bolsa.save()
    return JsonResponse({"ok": True})


# ── Solicitações de Hemoterapia ────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_solicitacoes(request):
    """GET/POST /api/hospital/hemoterapia/solicitacoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, SolicitacaoHemoterapia, *_ = _get_hemo_models()

    if request.method == "GET":
        qs = SolicitacaoHemoterapia.objects.filter(empresa=empresa)
        status_f   = request.GET.get("status")
        urgencia_f = request.GET.get("urgencia")
        q          = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if urgencia_f:
            qs = qs.filter(urgencia=urgencia_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        return JsonResponse({
            "total": qs.count(),
            "solicitacoes": [
                {
                    "id": s.id,
                    "paciente_nome": s.paciente_nome,
                    "cpf_paciente": s.cpf_paciente,
                    "tipo_hemocomponente": s.tipo_hemocomponente,
                    "tipo_hemocomponente_display": s.get_tipo_hemocomponente_display(),
                    "tipo_abo": s.tipo_abo,
                    "fator_rh": s.fator_rh,
                    "quantidade": s.quantidade,
                    "urgencia": s.urgencia,
                    "urgencia_display": s.get_urgencia_display(),
                    "status": s.status,
                    "status_display": s.get_status_display(),
                    "data_solicitacao": s.data_solicitacao.isoformat(),
                    "leito": s.leito,
                    "medico_solicitante": s.medico_solicitante,
                }
                for s in qs.order_by("-criado_em")[:200]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        sol = SolicitacaoHemoterapia.objects.create(
            empresa=empresa,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            tipo_abo=data.get("tipo_abo", ""),
            fator_rh=data.get("fator_rh", ""),
            tipo_hemocomponente=data["tipo_hemocomponente"],
            quantidade=data.get("quantidade", 1),
            urgencia=data.get("urgencia", "eletiva"),
            cid10=data.get("cid10", ""),
            medico_solicitante=data.get("medico_solicitante", ""),
            crm_medico=data.get("crm_medico", ""),
            leito=data.get("leito", ""),
            justificativa=data.get("justificativa", ""),
        )
    return JsonResponse({"id": sol.id}, status=201)


# ── Transfusões ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_transfusoes(request):
    """GET/POST /api/hospital/hemoterapia/transfusoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, _ = _get_hemo_models()

    if request.method == "GET":
        qs = TransfusaoPaciente.objects.filter(empresa=empresa).select_related("bolsa")
        q  = request.GET.get("q")
        reacao = request.GET.get("com_reacao")

        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))
        if reacao == "true":
            qs = qs.filter(houve_reacao=True)

        return JsonResponse({
            "total": qs.count(),
            "transfusoes": [
                {
                    "id": t.id,
                    "paciente_nome": t.paciente_nome,
                    "cpf_paciente": t.cpf_paciente,
                    "bolsa_codigo": t.bolsa.codigo_bolsa,
                    "bolsa_tipo": t.bolsa.get_tipo_display(),
                    "data_inicio": t.data_inicio.isoformat(),
                    "data_fim": t.data_fim.isoformat() if t.data_fim else None,
                    "houve_reacao": t.houve_reacao,
                    "enfermeiro": t.enfermeiro,
                }
                for t in qs.order_by("-data_inicio")[:200]
            ],
        })

    data = json.loads(request.body)
    try:
        bolsa = BolsaSangue.objects.get(id=data["bolsa_id"], empresa=empresa)
    except BolsaSangue.DoesNotExist:
        return JsonResponse({"erro": "Bolsa não encontrada"}, status=404)

    if bolsa.status not in ("disponivel", "reservada"):
        return JsonResponse({"erro": f"Bolsa não disponível — status: {bolsa.status}"}, status=400)

    if bolsa.validade < date.today():
        return JsonResponse({"erro": "Bolsa vencida — descarte obrigatório (RDC 34/2014)"}, status=400)

    with transaction.atomic():
        transf = TransfusaoPaciente.objects.create(
            empresa=empresa,
            bolsa=bolsa,
            solicitacao_id=data.get("solicitacao_id"),
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            data_inicio=data.get("data_inicio", timezone.now().isoformat()),
            volume_ml=data.get("volume_ml"),
            enfermeiro=data.get("enfermeiro", ""),
            coren=data.get("coren", ""),
            medico_responsavel=data.get("medico_responsavel", ""),
            obs=data.get("obs", ""),
        )
        bolsa.status = "transfundida"
        bolsa.save()
        if data.get("solicitacao_id"):
            SolicitacaoHemoterapia.objects.filter(
                id=data["solicitacao_id"], empresa=empresa
            ).update(status="transfundida")

    return JsonResponse({"id": transf.id}, status=201)


# ── Reações Transfusionais ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_reacoes(request):
    """GET/POST /api/hospital/hemoterapia/reacoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, ReacaoTransfusional = _get_hemo_models()

    if request.method == "GET":
        qs = ReacaoTransfusional.objects.filter(empresa=empresa)
        gravidade_f = request.GET.get("gravidade")
        nao_notif   = request.GET.get("nao_notificado")

        if gravidade_f:
            qs = qs.filter(gravidade=gravidade_f)
        if nao_notif == "true":
            qs = qs.filter(notificado_anvisa=False)

        return JsonResponse({
            "total": qs.count(),
            "reacoes": [
                {
                    "id": r.id,
                    "paciente_nome": r.paciente_nome,
                    "tipo_reacao": r.tipo_reacao,
                    "tipo_reacao_display": r.get_tipo_reacao_display(),
                    "gravidade": r.gravidade,
                    "gravidade_display": r.get_gravidade_display(),
                    "data_reacao": r.data_reacao.isoformat(),
                    "notificado_anvisa": r.notificado_anvisa,
                    "protocolo_notivisa": r.protocolo_notivisa,
                }
                for r in qs.order_by("-data_reacao")[:200]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        reacao = ReacaoTransfusional.objects.create(
            empresa=empresa,
            transfusao_id=data.get("transfusao_id"),
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            tipo_reacao=data["tipo_reacao"],
            gravidade=data["gravidade"],
            data_reacao=data.get("data_reacao", timezone.now().isoformat()),
            descricao=data["descricao"],
            conduta=data.get("conduta", ""),
        )
    return JsonResponse({"id": reacao.id}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_notificar_anvisa(request, reacao_id):
    """
    POST /api/hospital/hemoterapia/reacoes/<id>/notificar-anvisa/

    Gera XML de notificação no padrão NOTIVISA/eSNVS (ANVISA) para
    Hemovigilância (RDC 34/2014, art. 83).

    IMPORTANTE: O NOTIVISA não disponibiliza REST API pública.
    Este endpoint gera o arquivo XML e retorna as instruções para
    importação manual em https://notivisa.anvisa.gov.br.
    O operador deve baixar o XML em /notificar-anvisa/download/<id>/
    e importar no portal NOTIVISA com seu login de notificador.
    """
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, ReacaoTransfusional = _get_hemo_models()
    try:
        reacao = ReacaoTransfusional.objects.get(id=reacao_id, empresa=empresa)
    except ReacaoTransfusional.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if reacao.notificado_anvisa:
        return JsonResponse({
            "ok": True,
            "protocolo": reacao.protocolo_notivisa,
            "mensagem": "Notificação já registrada.",
        })

    # Gera XML NOTIVISA (eSNVS — Hemovigilância RDC 34/2014)
    xml_bytes = _gerar_xml_notivisa(reacao, empresa)
    xml_b64   = base64.b64encode(xml_bytes).decode()

    # Armazena o XML gerado no campo protocolo como marcador (sem REST)
    reacao.protocolo_notivisa = f"NOTIVISA-PENDENTE-{reacao.id}"
    # Nota: notificado_anvisa permanece False até confirmação manual
    reacao.save()

    return JsonResponse({
        "ok": True,
        "status": "xml_gerado_pendente_importacao",
        "protocolo_provisorio": reacao.protocolo_notivisa,
        "xml_base64": xml_b64,
        "instrucoes": [
            "1. Baixe o XML via GET /api/hospital/hemoterapia/reacoes/<id>/notificar-anvisa/download/",
            "2. Acesse https://notivisa.anvisa.gov.br com seu login de notificador habilitado",
            "3. Menu: Notificação → Hemovigilância → Importar Arquivo XML",
            "4. Após importação bem-sucedida, registre o protocolo NOTIVISA aqui via PATCH "
            "   com {\"notificado_anvisa\": true, \"protocolo_notivisa\": \"PROTOCOLO_NOTIVISA\"}",
        ],
        "portal_notivisa": "https://notivisa.anvisa.gov.br",
        "referencia": "RDC ANVISA 34/2014 art. 83 — Hemovigilância",
    })


@require_http_methods(["GET"])
@api_requer_feature("hospital.hemoterapia")
def api_hemo_notivisa_download(request, reacao_id):
    """GET /api/hospital/hemoterapia/reacoes/<id>/notificar-anvisa/download/ — baixa XML NOTIVISA."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, ReacaoTransfusional = _get_hemo_models()
    try:
        reacao = ReacaoTransfusional.objects.get(id=reacao_id, empresa=empresa)
    except ReacaoTransfusional.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    xml_bytes = _gerar_xml_notivisa(reacao, empresa)
    filename  = f"notivisa_hemovigilancia_{reacao.id}_{date.today().isoformat()}.xml"
    response  = HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _gerar_xml_notivisa(reacao, empresa):
    """
    Gera XML de Notificação de Reação Transfusional no padrão eSNVS/NOTIVISA.
    Esquema: ANVISA eSNVS — Hemovigilância (RDC 34/2014)
    Referência de campos: Manual NOTIVISA Hemovigilância v2.0 (ANVISA/GGTES)
    """
    # Mapeamento tipo_reacao → código NOTIVISA
    _TIPO_NOTIVISA = {
        "febre":            "1",   # Reação Febril Não Hemolítica
        "alergica_leve":    "2",   # Reação Alérgica Leve
        "alergica_grave":   "3",   # Reação Alérgica Grave / Anafilaxia
        "hemolitica_aguda": "4",   # Hemólise Aguda Intravascular
        "hemolitica_tardia":"5",   # Hemólise Tardia Extravascular
        "sobrecarga":       "6",   # Sobrecarga Circulatória Associada à Transfusão (TACO)
        "trali":            "7",   # Lesão Pulmonar Aguda Relacionada à Transfusão (TRALI)
        "contaminacao":     "8",   # Contaminação Bacteriana
        "outro":            "99",
    }
    _GRAV_NOTIVISA = {"leve": "1", "moderada": "2", "grave": "3", "fatal": "4"}

    cnes = ""
    try:
        from .models import CredenciaisIntegracoes
        cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
        cnes = getattr(cred, "sus_cnes", "") or getattr(cred, "rnds_cnes", "") if cred else ""
    except Exception:
        pass

    root = ET.Element("notificacao", attrib={
        "xmlns":   "http://anvisa.gov.br/esnvs/hemovigilancia",
        "versao":  "2.0",
        "sistema": "SolusCRT",
    })

    # Cabeçalho
    cab = ET.SubElement(root, "cabecalho")
    ET.SubElement(cab, "dataNotificacao").text = date.today().isoformat()
    ET.SubElement(cab, "tipoNotificacao").text  = "hemovigilancia"
    ET.SubElement(cab, "cnesEstabelecimento").text = cnes
    ET.SubElement(cab, "nomeEstabelecimento").text  = empresa.nome

    # Paciente
    pac = ET.SubElement(root, "paciente")
    ET.SubElement(pac, "nome").text  = reacao.paciente_nome
    ET.SubElement(pac, "cpf").text   = reacao.cpf_paciente or ""

    # Reação transfusional
    rt = ET.SubElement(root, "reacaoTransfusional")
    ET.SubElement(rt, "dataReacao").text       = (
        reacao.data_reacao.date().isoformat()
        if hasattr(reacao.data_reacao, "date")
        else str(reacao.data_reacao)
    )
    ET.SubElement(rt, "tipoReacao").text        = _TIPO_NOTIVISA.get(reacao.tipo_reacao, "99")
    ET.SubElement(rt, "tipoReacaoDescricao").text = reacao.get_tipo_reacao_display()
    ET.SubElement(rt, "gravidade").text          = _GRAV_NOTIVISA.get(reacao.gravidade, "1")
    ET.SubElement(rt, "gravidadeDescricao").text  = reacao.get_gravidade_display()
    ET.SubElement(rt, "descricaoClinica").text     = reacao.descricao
    ET.SubElement(rt, "condutaTomada").text        = reacao.conduta or ""

    # Bolsa (se vinculada)
    if reacao.transfusao:
        bolsa = ET.SubElement(root, "hemocomponente")
        b = reacao.transfusao.bolsa
        ET.SubElement(bolsa, "codigoBolsa").text = b.codigo_bolsa
        ET.SubElement(bolsa, "isbt128").text      = b.isbt128 or ""
        ET.SubElement(bolsa, "tipo").text          = b.tipo
        ET.SubElement(bolsa, "grupoABO").text      = b.tipo_abo
        ET.SubElement(bolsa, "fatorRh").text        = b.fator_rh
        ET.SubElement(bolsa, "dataColetaBolsa").text = b.coletada_em.isoformat() if b.coletada_em else ""
        ET.SubElement(bolsa, "validadeBolsa").text   = b.validade.isoformat()

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.hemoterapia")
def api_hemo_kpis(request):
    """GET /api/hospital/hemoterapia/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    BolsaSangue, SolicitacaoHemoterapia, TransfusaoPaciente, ReacaoTransfusional = _get_hemo_models()

    hoje     = date.today()
    mes_ini  = hoje.replace(day=1)
    sete_dias = hoje + timedelta(days=7)

    # Estoque
    por_tipo = dict(
        BolsaSangue.objects.filter(empresa=empresa, status="disponivel")
        .values_list("tipo").annotate(n=Count("id")).order_by()
    )
    vencendo_7d = BolsaSangue.objects.filter(
        empresa=empresa, status="disponivel",
        validade__gte=hoje, validade__lte=sete_dias,
    ).count()
    vencidas = BolsaSangue.objects.filter(
        empresa=empresa, status="disponivel", validade__lt=hoje
    ).count()

    # Transfusões no mês
    transf_mes = TransfusaoPaciente.objects.filter(
        empresa=empresa, data_inicio__date__gte=mes_ini
    ).count()
    reacoes_mes = ReacaoTransfusional.objects.filter(
        empresa=empresa, data_reacao__gte=mes_ini
    ).count()
    graves_nao_notif = ReacaoTransfusional.objects.filter(
        empresa=empresa,
        gravidade__in=["grave", "fatal"],
        notificado_anvisa=False,
    ).count()

    return JsonResponse({
        "estoque_por_tipo": por_tipo,
        "vencendo_7_dias": vencendo_7d,
        "bolsas_vencidas_estoque": vencidas,
        "transfusoes_mes": transf_mes,
        "reacoes_mes": reacoes_mes,
        "graves_nao_notificadas_anvisa": graves_nao_notif,
        "alerta_estoque_critico": vencendo_7d > 0 or vencidas > 0 or graves_nao_notif > 0,
    })
