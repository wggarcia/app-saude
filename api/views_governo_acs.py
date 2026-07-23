"""
ACS — Agente Comunitário de Saúde + Visitas Domiciliares + Fichas de Acompanhamento
e-SUS Atenção Básica / CDS — Portaria MS 1.412/2013.

Transmissão ao SISAB:
  O SISAB NÃO disponibiliza REST API pública para sistemas externos.
  A integração oficial é feita pelo software PEC (Prontuário Eletrônico do Cidadão)
  através do protocolo Thrift / envio local → sincronização nacional.

  Este módulo implementa a abordagem oficial para sistemas externos:
    1. Geração do arquivo CDS JSON (FichaVisitaDomiciliarMestre) no padrão
       e-SUS AB — Documentação Técnica UFSC/DAB/MS
    2. Download do arquivo JSON pelo operador
    3. Importação no PEC via: Configurações → Importar CDS
  Ref: https://integracao.esusab.ufsc.br/ledi/documentacao/
       Portaria GM/MS 1.412/2013 | Manual e-SUS AB v3.x
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

    Gera arquivo CDS JSON (FichaVisitaDomiciliarMestre) no padrão oficial
    e-SUS AB para importação no PEC (Prontuário Eletrônico do Cidadão).

    Retorna JSON com:
      - cds_json_b64: arquivo CDS em base64 (para download)
      - instrucoes: passo a passo de importação no PEC

    Para download direto: GET /api/governo/acs/visitas/exportar-cds/
    """
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, VisitaDomiciliar, _ = _get_acs_models()

    body     = json.loads(request.body) if request.body else {}
    data_ini = body.get("data_inicio")

    pendentes = VisitaDomiciliar.objects.filter(
        empresa=empresa,
        transmitido_esus=False,
    ).select_related("acs")

    if data_ini:
        pendentes = pendentes.filter(data_visita__gte=data_ini)

    total = pendentes.count()
    if total == 0:
        return JsonResponse({"ok": True, "fichas": 0, "mensagem": "Nenhuma ficha pendente para exportação"})

    cds = _gerar_cds_fichas_visita(list(pendentes[:500]), empresa)
    cds_bytes = json.dumps(cds, ensure_ascii=False, indent=2).encode("utf-8")
    cds_b64   = __import__("base64").b64encode(cds_bytes).decode()

    # Marca como "cds_gerado" — não marcamos transmitido_esus=True até importação confirmada
    return JsonResponse({
        "ok": True,
        "fichas": total,
        "uuid_lote": cds["uuidLoteOrigem"],
        "cds_json_b64": cds_b64,
        "status": "cds_gerado_pendente_importacao_pec",
        "instrucoes": [
            "1. Baixe o arquivo CDS via GET /api/governo/acs/visitas/exportar-cds/",
            "2. No PEC da sua UBS: Configurações → Transmissão de Dados → Importar CDS",
            "3. Selecione o arquivo JSON exportado",
            "4. Aguarde confirmação de importação no PEC",
            "5. Após importação, confirme via PATCH das visitas com {\"transmitido_esus\": true}",
        ],
        "referencia": "e-SUS AB — FichaVisitaDomiciliarMestre | https://integracao.esusab.ufsc.br/",
    })


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.vigilancia_acs")
def api_visitas_exportar_cds(request):
    """GET /api/governo/acs/visitas/exportar-cds/ — baixa arquivo CDS JSON para importação no PEC."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, VisitaDomiciliar, _ = _get_acs_models()

    data_ini = request.GET.get("data_inicio")
    qs = VisitaDomiciliar.objects.filter(
        empresa=empresa, transmitido_esus=False
    ).select_related("acs")
    if data_ini:
        qs = qs.filter(data_visita__gte=data_ini)

    visitas = list(qs[:500])
    cds = _gerar_cds_fichas_visita(visitas, empresa)

    filename = f"esus_cds_visitas_{date.today().isoformat()}.json"
    response = HttpResponse(
        json.dumps(cds, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# Mapeamentos e-SUS CDS — turno, motivo, desfecho
_TURNO_CDS    = {"M": 1, "T": 2, "N": 3}
_MOTIVO_CDS   = {
    "cadastramento":        [1],   # Cadastramento/Atualização
    "visita_rotineira":     [2],   # Visita de Rotina
    "acompanhamento":       [3],   # Acompanhamento
    "busca_ativa":          [4],   # Busca Ativa
    "pre_natal":            [5],   # Pré-natal
    "puericultura":         [6],   # Puericultura
    "pessoa_idosa":         [7],   # Atenção à Pessoa Idosa
    "portador_doenca_cronica": [8],
    "saude_mental":         [9],
    "domiciliado":          [10],
    "egresso_internacao":   [11],
    "obito":                [12],  # Verificação de Óbito
    "outro":                [13],
}
_DESFECHO_CDS = {
    "visita_realizada": 1,
    "ausente":          2,
    "recusou":          3,
}


def _gerar_cds_fichas_visita(visitas, empresa):
    """
    Gera estrutura FichaVisitaDomiciliarMestre conforme documentação técnica
    e-SUS AB (UFSC/DAB/MS) para importação no PEC.

    Formato: https://integracao.esusab.ufsc.br/ledi/documentacao/
    """
    # Pega info do primeiro ACS para cabeçalho (lote por UBS/equipe)
    cnes_usf  = visitas[0].acs.cnes_usf  if visitas else ""
    ine_equipe = visitas[0].acs.ine_equipe if visitas else ""
    try:
        from .models import CredenciaisIntegracoes
        cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
        ibge = (getattr(cred, "sus_ibge", "") or getattr(cred, "rnds_ibge", "")) if cred else ""
    except Exception:
        ibge = ""

    filhos = []
    for v in visitas:
        motivos_raw = _MOTIVO_CDS.get(v.motivo, [13])
        filhos.append({
            "uuid":          v.uuid_esus or str(uuid.uuid4()),
            "turno":         _TURNO_CDS.get(v.turno, 1),
            # statusVisita: 1=Visita Realizada, 2=Fora da Microárea, 3=Busca Ativa
            "statusVisita":  _DESFECHO_CDS.get(v.desfecho, 1),
            "motivoVisita": {
                "motivoVisita": motivos_raw,
            },
            # Dados do cidadão
            "cnsCidadao":         v.cns_paciente or "",
            "cpfCidadao":         v.cpf_paciente or "",
            "nomeCidadao":        v.paciente_nome,
            # Gestante
            **({"gestantePuerperaFlag": True} if v.gestante else {}),
            # Dados clínicos opcionais
            **({"pesoAcompanhamentoNutricional": float(v.peso_kg)} if v.peso_kg else {}),
            **({"pressaoArterialMmHg": f"{v.pa_sistolica}x{v.pa_diastolica}"} if v.pa_sistolica else {}),
            # Profissional / ACS
            "profissionalCNS":   v.acs.cns or "",
            "profissionalNome":  v.acs.nome,
            "microArea":         v.acs.microarea or "",
            "dataVisita":        v.data_visita.isoformat(),
        })

    return {
        # Cabeçalho do lote CDS
        "uuidLoteOrigem":       str(uuid.uuid4()),
        "cnesUnidadeSaude":     cnes_usf,
        "codigoIbgeMunicipio":  ibge,
        "ineEquipeSaude":       ine_equipe,
        # dataEnvio em ms (timestamp Unix)
        "dataEnvio":            int(time.time() * 1000),
        "versaoEsusab":         "3.2",
        "sistemaOrigem":        "SoloCRT",
        "fichasVisitaDomiciliarChild": filhos,
    }


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
