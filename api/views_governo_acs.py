"""
ACS — Agente Comunitário de Saúde + Visitas Domiciliares + Fichas de Acompanhamento
e-SUS Atenção Básica / CDS — Portaria MS 1.412/2013.
Integração SISAB (transmissão de fichas de visita).
"""
import json
import logging
import uuid
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)


def _get_acs_models():
    from .models import AgenteComunidadeSaude, VisitaDomiciliar, FichaAcompanhamento
    return AgenteComunidadeSaude, VisitaDomiciliar, FichaAcompanhamento


# ── Cadastro de ACS ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
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
              "glicemia", "gestante", "ig_semanas", "obs"]
    for c in campos:
        if c in data:
            setattr(visita, c, data[c])
    visita.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def api_visitas_transmitir_esus(request):
    """POST /api/governo/acs/visitas/transmitir-esus/ — envia fichas pendentes ao SISAB."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, VisitaDomiciliar, _ = _get_acs_models()

    pendentes = VisitaDomiciliar.objects.filter(
        empresa=empresa,
        transmitido_esus=False,
        desfecho="visita_realizada",
    )

    # Opcional: filtro de data_inicio
    data_ini = (request.body and json.loads(request.body) or {}).get("data_inicio")
    if data_ini:
        pendentes = pendentes.filter(data_visita__gte=data_ini)

    count = pendentes.count()
    if count == 0:
        return JsonResponse({"ok": True, "transmitidas": 0, "mensagem": "Nenhuma ficha pendente"})

    fichas = [
        {
            "uuid": v.uuid_esus,
            "cns_acs": v.acs.cns,
            "cnes": v.acs.cnes_usf,
            "ine": v.acs.ine_equipe,
            "data": v.data_visita.isoformat(),
            "turno": v.turno,
            "motivo": v.motivo,
            "desfecho": v.desfecho,
            "cns_paciente": v.cns_paciente,
        }
        for v in pendentes.select_related("acs")[:500]
    ]

    try:
        import requests as req
        payload = {
            "municipio_ibge": empresa.municipio_ibge if hasattr(empresa, "municipio_ibge") else "",
            "fichas_visita": fichas,
        }
        resp = req.post(
            "https://sisab.saude.gov.br/api/v1/transmissao/ficha-visita",
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            protocolo = resp.json().get("protocolo", f"SISAB-{date.today().isoformat()}")
            ids = list(pendentes.values_list("id", flat=True)[:500])
            VisitaDomiciliar.objects.filter(id__in=ids).update(transmitido_esus=True)
            return JsonResponse({"ok": True, "transmitidas": len(ids), "protocolo": protocolo})
        else:
            return JsonResponse({"erro": f"SISAB HTTP {resp.status_code}"}, status=502)
    except Exception as e:
        logger.error("Erro SISAB transmissão ACS: %s", e)
        return JsonResponse({"erro": str(e)}, status=502)


# ── Fichas de Acompanhamento ───────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
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
