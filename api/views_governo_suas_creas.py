import json
import logging
from datetime import date

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import api_requer_permissao_modulo, get_setor, principal_pode_operacao_setorial
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)


def _gov(request):
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "governo":
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
    }


def _atendimento_dict(a):
    return {
        "id": a.id,
        "unidade_creas_id": a.unidade_creas_id,
        "unidade_creas_nome": a.unidade_creas.nome if a.unidade_creas else None,
        "usuario_nome": a.usuario_nome,
        "usuario_cpf": a.usuario_cpf,
        "usuario_cns": a.usuario_cns,
        "usuario_data_nascimento": str(a.usuario_data_nascimento) if a.usuario_data_nascimento else None,
        "usuario_telefone": a.usuario_telefone,
        "tecnico_nome": a.tecnico_nome,
        "tecnico_cargo": a.tecnico_cargo,
        "data_atendimento": str(a.data_atendimento),
        "tipo_violacao": a.tipo_violacao,
        "tipo_violacao_display": a.get_tipo_violacao_display(),
        "situacao": a.situacao,
        "situacao_display": a.get_situacao_display(),
        "descricao": a.descricao,
        "plano_atendimento": a.plano_atendimento,
        "encaminhamento": a.encaminhamento,
        "numero_prontuario": a.numero_prontuario,
        "criado_em": a.criado_em.isoformat(),
        "atualizado_em": a.atualizado_em.isoformat(),
    }


# ─── UNIDADES CREAS ──────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_creas_unidades(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo — Assistência Social"}, status=403)

    from .models import UnidadeCREAS

    if request.method == "GET":
        qs = UnidadeCREAS.objects.filter(empresa=empresa)
        ativo = request.GET.get("ativo")
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() != "false"))
        return JsonResponse({"total": qs.count(), "unidades": [_creas_dict(u) for u in qs]})

    if request.method == "POST":
        body = json.loads(request.body)
        u = UnidadeCREAS.objects.create(
            empresa=empresa,
            nome=body.get("nome", "").strip(),
            codigo_creas=body.get("codigo_creas", "").strip(),
            cnes=body.get("cnes", "").strip(),
            endereco=body.get("endereco", "").strip(),
            bairro=body.get("bairro", "").strip(),
            municipio=body.get("municipio", "").strip(),
            uf=body.get("uf", "").strip().upper(),
            cep=body.get("cep", "").strip(),
            telefone=body.get("telefone", "").strip(),
            responsavel_tecnico=body.get("responsavel_tecnico", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": u.id, "nome": u.nome}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_creas_unidade_detalhe(request, creas_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCREAS
    try:
        u = UnidadeCREAS.objects.get(id=creas_id, empresa=empresa)
    except UnidadeCREAS.DoesNotExist:
        return JsonResponse({"erro": "Unidade CREAS não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_creas_dict(u))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        for c in ["nome", "codigo_creas", "cnes", "endereco", "bairro", "municipio",
                  "cep", "telefone", "responsavel_tecnico", "ativo"]:
            if c in body:
                val = body[c].strip() if isinstance(body[c], str) else body[c]
                if c == "uf":
                    val = val.upper()
                setattr(u, c, val)
        u.save()
        return JsonResponse({"status": "atualizado", **_creas_dict(u)})

    if request.method == "DELETE":
        u.ativo = False
        u.save()
        return JsonResponse({"status": "desativado", "id": u.id})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── ATENDIMENTOS CREAS ──────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_creas_atendimentos(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCREAS

    if request.method == "GET":
        qs = AtendimentoCREAS.objects.filter(empresa=empresa).select_related("unidade_creas")
        situacao = request.GET.get("situacao")
        tipo_violacao = request.GET.get("tipo_violacao")
        unidade_id = request.GET.get("unidade_creas_id")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        q = request.GET.get("q", "").strip()

        if situacao:
            qs = qs.filter(situacao=situacao)
        if tipo_violacao:
            qs = qs.filter(tipo_violacao=tipo_violacao)
        if unidade_id:
            qs = qs.filter(unidade_creas_id=unidade_id)
        if data_ini:
            qs = qs.filter(data_atendimento__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_atendimento__lte=data_fim)
        if q:
            qs = qs.filter(usuario_nome__icontains=q) | qs.filter(usuario_cpf__icontains=q)

        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        atendimentos = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({
            "total": total,
            "page": page,
            "paginas": (total + per_page - 1) // per_page,
            "atendimentos": [_atendimento_dict(a) for a in atendimentos],
        })

    if request.method == "POST":
        from .utils import validar_cpf_cadastro
        body = json.loads(request.body)
        cpf = body.get("usuario_cpf", "").replace(".", "").replace("-", "").strip()
        ok, erro = validar_cpf_cadastro(cpf, empresa)
        if not ok:
            return JsonResponse({"erro": erro}, status=400)

        a = AtendimentoCREAS.objects.create(
            empresa=empresa,
            unidade_creas_id=body.get("unidade_creas_id") or None,
            usuario_nome=body.get("usuario_nome", "").strip(),
            usuario_cpf=cpf,
            usuario_cns=body.get("usuario_cns", "").strip(),
            usuario_data_nascimento=body.get("usuario_data_nascimento") or None,
            usuario_telefone=body.get("usuario_telefone", "").strip(),
            tecnico_nome=body.get("tecnico_nome", "").strip(),
            tecnico_cargo=body.get("tecnico_cargo", "").strip(),
            data_atendimento=body.get("data_atendimento", str(date.today())),
            tipo_violacao=body.get("tipo_violacao", "outros"),
            situacao=body.get("situacao", "em_acompanhamento"),
            descricao=body.get("descricao", "").strip(),
            plano_atendimento=body.get("plano_atendimento", "").strip(),
            encaminhamento=body.get("encaminhamento", "").strip(),
            numero_prontuario=body.get("numero_prontuario", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": a.id, **_atendimento_dict(a)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_creas_atendimento_detalhe(request, atendimento_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCREAS
    try:
        a = AtendimentoCREAS.objects.select_related("unidade_creas").get(
            id=atendimento_id, empresa=empresa
        )
    except AtendimentoCREAS.DoesNotExist:
        return JsonResponse({"erro": "Atendimento CREAS não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_atendimento_dict(a))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        for c in ["tecnico_nome", "tecnico_cargo", "tipo_violacao", "situacao",
                  "descricao", "plano_atendimento", "encaminhamento", "numero_prontuario",
                  "usuario_telefone"]:
            if c in body:
                setattr(a, c, body[c].strip() if isinstance(body[c], str) else body[c])
        if "data_atendimento" in body:
            a.data_atendimento = body["data_atendimento"]
        if "unidade_creas_id" in body:
            a.unidade_creas_id = body["unidade_creas_id"] or None
        a.save()
        return JsonResponse({"status": "atualizado", **_atendimento_dict(a)})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── KPIs CREAS ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_creas_kpis(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCREAS, AtendimentoCREAS
    from django.db.models import Count

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_ano = hoje.replace(month=1, day=1)

    total_creas = UnidadeCREAS.objects.filter(empresa=empresa, ativo=True).count()
    total_casos = AtendimentoCREAS.objects.filter(empresa=empresa).count()
    casos_ativos = AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    novos_mes = AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()
    novos_ano = AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_ano).count()

    por_violacao = (
        AtendimentoCREAS.objects.filter(empresa=empresa)
        .values("tipo_violacao")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    por_situacao = (
        AtendimentoCREAS.objects.filter(empresa=empresa)
        .values("situacao")
        .annotate(total=Count("id"))
    )

    return JsonResponse({
        "total_creas": total_creas,
        "total_casos": total_casos,
        "casos_ativos": casos_ativos,
        "novos_mes": novos_mes,
        "novos_ano": novos_ano,
        "por_tipo_violacao": {p["tipo_violacao"]: p["total"] for p in por_violacao},
        "por_situacao": {p["situacao"]: p["total"] for p in por_situacao},
        "referencia_mes": str(inicio_mes),
    })
