import json
import logging
from datetime import date

from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import api_requer_permissao_modulo, get_setor, principal_pode_operacao_setorial
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)


def _assoc(request):
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "assistencia_social":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ─── HELPERS ────────────────────────────────────────────────────────────────

def _creas_dict(u):
    return {
        "id": u.id,
        "nome": u.nome,
        "codigo_creas": u.codigo_creas,
        "cnes": u.cnes,
        "endereco": u.endereco,
        "bairro": u.bairro,
        "municipio": u.municipio,
        "uf": u.uf,
        "cep": u.cep,
        "telefone": u.telefone,
        "responsavel_tecnico": u.responsavel_tecnico,
        "ativo": u.ativo,
        "criado_em": u.criado_em.isoformat(),
    }


def _atendimento_creas_dict(a):
    return {
        "id": a.id,
        "unidade_creas_id": a.unidade_creas_id,
        "unidade_creas_nome": a.unidade_creas.nome if a.unidade_creas else None,
        "beneficiario_nome": a.beneficiario_nome,
        "beneficiario_cpf": a.beneficiario_cpf,
        "beneficiario_nis": a.beneficiario_nis,
        "responsavel_familiar": a.responsavel_familiar,
        "tecnico_nome": a.tecnico_nome,
        "data_atendimento": str(a.data_atendimento),
        "tipo_violacao": a.tipo_violacao,
        "descricao": a.descricao,
        "encaminhamentos": a.encaminhamentos,
        "situacao": a.situacao,
        "criado_em": a.criado_em.isoformat(),
    }


# ─── UNIDADES CREAS ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_creas_unidades(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Assistência Social — CREAS/PAEFI"}, status=403)

    from .models import UnidadeCREAS

    if request.method == "GET":
        qs = UnidadeCREAS.objects.filter(empresa=empresa).order_by("nome")
        ativo = request.GET.get("ativo")
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() == "true"))
        return JsonResponse({"unidades": [_creas_dict(u) for u in qs]})

    data = json.loads(request.body)
    u = UnidadeCREAS.objects.create(
        empresa=empresa,
        nome=data["nome"],
        codigo_creas=data.get("codigo_creas", ""),
        cnes=data.get("cnes", ""),
        endereco=data.get("endereco", ""),
        bairro=data.get("bairro", ""),
        municipio=data.get("municipio", ""),
        uf=data.get("uf", ""),
        cep=data.get("cep", ""),
        telefone=data.get("telefone", ""),
        responsavel_tecnico=data.get("responsavel_tecnico", ""),
    )
    return JsonResponse({"unidade": _creas_dict(u)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_creas_unidade_detalhe(request, creas_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCREAS

    try:
        u = UnidadeCREAS.objects.get(id=creas_id, empresa=empresa)
    except UnidadeCREAS.DoesNotExist:
        return JsonResponse({"erro": "Unidade não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"unidade": _creas_dict(u)})

    if request.method == "DELETE":
        u.ativo = False
        u.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    data = json.loads(request.body)
    campos = ["nome", "codigo_creas", "cnes", "endereco", "bairro", "municipio", "uf", "cep", "telefone", "responsavel_tecnico", "ativo"]
    for campo in campos:
        if campo in data:
            setattr(u, campo, data[campo])
    u.save()
    return JsonResponse({"unidade": _creas_dict(u)})


# ─── ATENDIMENTOS PAEFI ─────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_creas_atendimentos(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCREAS, UnidadeCREAS

    if request.method == "GET":
        qs = AtendimentoCREAS.objects.filter(empresa=empresa).select_related("unidade_creas").order_by("-data_atendimento")
        creas_id = request.GET.get("creas_id")
        situacao = request.GET.get("situacao")
        tipo_violacao = request.GET.get("tipo_violacao")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        busca = request.GET.get("q", "").strip()

        if creas_id:
            qs = qs.filter(unidade_creas_id=creas_id)
        if situacao:
            qs = qs.filter(situacao=situacao)
        if tipo_violacao:
            qs = qs.filter(tipo_violacao=tipo_violacao)
        if data_ini:
            qs = qs.filter(data_atendimento__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_atendimento__lte=data_fim)
        if busca:
            from django.db.models import Q
            qs = qs.filter(
                Q(beneficiario_nome__icontains=busca) |
                Q(beneficiario_cpf__icontains=busca) |
                Q(beneficiario_nis__icontains=busca)
            )
        return JsonResponse({"atendimentos": [_atendimento_creas_dict(a) for a in qs[:300]]})

    data = json.loads(request.body)
    unidade_creas = None
    if data.get("unidade_creas_id"):
        try:
            unidade_creas = UnidadeCREAS.objects.get(id=data["unidade_creas_id"], empresa=empresa)
        except UnidadeCREAS.DoesNotExist:
            return JsonResponse({"erro": "Unidade CREAS não encontrada"}, status=400)

    a = AtendimentoCREAS.objects.create(
        empresa=empresa,
        unidade_creas=unidade_creas,
        beneficiario_nome=data["beneficiario_nome"],
        beneficiario_cpf=data.get("beneficiario_cpf", ""),
        beneficiario_nis=data.get("beneficiario_nis", ""),
        responsavel_familiar=data.get("responsavel_familiar", ""),
        tecnico_nome=data.get("tecnico_nome", ""),
        data_atendimento=data.get("data_atendimento", str(date.today())),
        tipo_violacao=data.get("tipo_violacao", "outro"),
        descricao=data.get("descricao", ""),
        encaminhamentos=data.get("encaminhamentos", ""),
        situacao=data.get("situacao", "em_acompanhamento"),
    )
    return JsonResponse({"atendimento": _atendimento_creas_dict(a)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_creas_atendimento_detalhe(request, atendimento_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCREAS

    try:
        a = AtendimentoCREAS.objects.select_related("unidade_creas").get(id=atendimento_id, empresa=empresa)
    except AtendimentoCREAS.DoesNotExist:
        return JsonResponse({"erro": "Atendimento não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"atendimento": _atendimento_creas_dict(a)})

    if request.method == "DELETE":
        a.situacao = "encerrado"
        a.save(update_fields=["situacao"])
        return JsonResponse({"ok": True})

    data = json.loads(request.body)
    for campo in ["beneficiario_nome", "beneficiario_cpf", "beneficiario_nis", "responsavel_familiar",
                  "tecnico_nome", "data_atendimento", "tipo_violacao", "descricao", "encaminhamentos", "situacao"]:
        if campo in data:
            setattr(a, campo, data[campo])
    a.save()
    return JsonResponse({"atendimento": _atendimento_creas_dict(a)})


# ─── KPIs CREAS ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.creas_paefi")
def api_ass_creas_kpis(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCREAS, AtendimentoCREAS

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    unidades_ativas = UnidadeCREAS.objects.filter(empresa=empresa, ativo=True).count()
    casos_ativos = AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    novos_mes = AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()
    encerrados_mes = AtendimentoCREAS.objects.filter(empresa=empresa, situacao="encerrado", atualizado_em__date__gte=inicio_mes).count()

    por_tipo_violacao = dict(
        AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento")
        .values("tipo_violacao").annotate(total=Count("id"))
        .values_list("tipo_violacao", "total")
    )
    por_situacao = dict(
        AtendimentoCREAS.objects.filter(empresa=empresa)
        .values("situacao").annotate(total=Count("id"))
        .values_list("situacao", "total")
    )

    return JsonResponse({
        "referencia_mes": str(inicio_mes),
        "unidades_ativas": unidades_ativas,
        "casos_em_acompanhamento": casos_ativos,
        "novos_acolhimentos_mes": novos_mes,
        "encerrados_mes": encerrados_mes,
        "por_tipo_violacao": por_tipo_violacao,
        "por_situacao": por_situacao,
    })
