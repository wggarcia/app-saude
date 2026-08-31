"""
SIM — Sistema de Informação sobre Mortalidade (consolidação municipal).
Registra óbitos da rede de UnidadeSaude do município/estado e controla o
status de transmissão ao SIM/DATASUS — mesmo padrão do SIPNI (IA #9), só que
para mortalidade em vez de imunização.

GET/POST  /api/governo/sim/obitos
GET/PATCH /api/governo/sim/obitos/<id>
POST      /api/governo/sim/obitos/<id>/transmitir
GET       /api/governo/sim/kpis
"""
import json
import logging
from datetime import date

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial, api_requer_permissao_modulo,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .views_dashboard import contexto_navegacao_setorial

logger = logging.getLogger(__name__)


def _gov(request):
    emp = get_empresa(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica", "governo.epidemiologia")
def governo_sim_page(request):
    return render(request, "governo_sim.html", contexto_navegacao_setorial(request, "governo"))


# ── Óbitos ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.atencao_clinica", "governo.epidemiologia")
def api_sim_obitos(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import RegistroObitoMunicipal, UnidadeSaude

    if request.method == "GET":
        qs = RegistroObitoMunicipal.objects.filter(empresa=empresa).select_related("unidade_saude")
        status_f = request.GET.get("status_transmissao")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status_transmissao=status_f)
        if q:
            qs = qs.filter(falecido_nome__icontains=q)

        return JsonResponse({
            "total": qs.count(),
            "obitos": [
                {
                    "id": o.id,
                    "falecido_nome": o.falecido_nome,
                    "unidade_saude": o.unidade_saude.nome if o.unidade_saude else None,
                    "data_obito": o.data_obito.isoformat(),
                    "tipo_morte": o.tipo_morte, "tipo_morte_display": o.get_tipo_morte_display(),
                    "causa_basica_cid": o.causa_basica_cid,
                    "status_transmissao": o.status_transmissao,
                    "status_transmissao_display": o.get_status_transmissao_display(),
                    "numero_do": o.numero_do,
                }
                for o in qs.order_by("-data_obito")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not data.get("falecido_nome") or not data.get("data_obito") or not data.get("causa_basica_cid"):
        return JsonResponse({"erro": "Nome do falecido, data do óbito e CID da causa básica são obrigatórios"}, status=400)

    unidade = None
    if data.get("unidade_saude_id"):
        unidade = UnidadeSaude.objects.filter(id=data["unidade_saude_id"], empresa=empresa).first()

    o = RegistroObitoMunicipal.objects.create(
        empresa=empresa,
        unidade_saude=unidade,
        falecido_nome=data["falecido_nome"],
        falecido_cpf=data.get("falecido_cpf", ""),
        falecido_data_nascimento=data.get("falecido_data_nascimento") or None,
        data_obito=data["data_obito"],
        tipo_morte=data.get("tipo_morte", "natural"),
        causa_basica_cid=data["causa_basica_cid"],
        causa_basica_descricao=data.get("causa_basica_descricao", ""),
        medico_atestante=data.get("medico_atestante", ""),
        medico_crm=data.get("medico_crm", ""),
        numero_do=data.get("numero_do", ""),
    )
    return JsonResponse({"id": o.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("governo.atencao_clinica", "governo.epidemiologia")
def api_sim_obito_detalhe(request, obito_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import RegistroObitoMunicipal
    try:
        o = RegistroObitoMunicipal.objects.get(id=obito_id, empresa=empresa)
    except RegistroObitoMunicipal.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": o.id, "falecido_nome": o.falecido_nome, "falecido_cpf": o.falecido_cpf,
            "falecido_data_nascimento": o.falecido_data_nascimento.isoformat() if o.falecido_data_nascimento else None,
            "unidade_saude_id": o.unidade_saude_id,
            "data_obito": o.data_obito.isoformat(),
            "tipo_morte": o.tipo_morte, "tipo_morte_display": o.get_tipo_morte_display(),
            "causa_basica_cid": o.causa_basica_cid, "causa_basica_descricao": o.causa_basica_descricao,
            "medico_atestante": o.medico_atestante, "medico_crm": o.medico_crm,
            "numero_do": o.numero_do,
            "status_transmissao": o.status_transmissao,
            "status_transmissao_display": o.get_status_transmissao_display(),
            "transmitido_em": o.transmitido_em.isoformat() if o.transmitido_em else None,
        })

    data = json.loads(request.body)
    for campo in ("causa_basica_cid", "causa_basica_descricao", "medico_atestante",
                  "medico_crm", "numero_do", "tipo_morte"):
        if campo in data:
            setattr(o, campo, data[campo])
    o.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica", "governo.epidemiologia")
def api_sim_obito_transmitir(request, obito_id):
    """POST /api/governo/sim/obitos/<id>/transmitir — finaliza a DO e a coloca em fila
    de transmissão ao SIM/DATASUS.

    O SIM (Sistema de Informação sobre Mortalidade) não expõe API pública de
    recepção — a transmissão oficial é feita via SCNS/transmissor DATASUS por
    upload de arquivo. Por isso NÃO marcamos "transmitido" aqui (seria falso):
    marcamos "aguardando_transmissao" e o município conclui o envio pelo SCNS.
    Quando existir integração automatizada configurada, este ponto passa a
    despachar de fato e marcar "transmitido".
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import RegistroObitoMunicipal
    try:
        o = RegistroObitoMunicipal.objects.get(id=obito_id, empresa=empresa)
    except RegistroObitoMunicipal.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    o.status_transmissao = "aguardando_transmissao"
    o.save(update_fields=["status_transmissao"])
    return JsonResponse({
        "ok": True,
        "status_transmissao": o.status_transmissao,
        "mensagem": "DO finalizada e em fila. Conclua a transmissão oficial pelo SCNS/DATASUS.",
    })


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica", "governo.epidemiologia")
def api_sim_kpis(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import RegistroObitoMunicipal

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    qs = RegistroObitoMunicipal.objects.filter(empresa=empresa)
    qs_mes = qs.filter(data_obito__date__gte=inicio_mes)
    por_causa = dict(
        qs_mes.values_list("causa_basica_cid").annotate(n=Count("id")).order_by("-n")[:10]
    )

    return JsonResponse({
        "total_obitos": qs.count(),
        "obitos_mes_atual": qs_mes.count(),
        "pendentes_transmissao": qs.filter(status_transmissao="pendente").count(),
        "transmitidos": qs.filter(status_transmissao="transmitido").count(),
        "principais_causas_mes": por_causa,
    })
