import json
import logging
from datetime import date, timedelta

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

def _cras_dict(u):
    return {
        "id": u.id,
        "nome": u.nome,
        "codigo_cras": u.codigo_cras,
        "cnes": u.cnes,
        "endereco": u.endereco,
        "bairro": u.bairro,
        "municipio": u.municipio,
        "uf": u.uf,
        "cep": u.cep,
        "telefone": u.telefone,
        "email": u.email,
        "responsavel_tecnico": u.responsavel_tecnico,
        "ativo": u.ativo,
    }


def _familia_dict(f):
    return {
        "id": f.id,
        "numero_prontuario": f.numero_prontuario,
        "responsavel_nome": f.responsavel_nome,
        "responsavel_cpf": f.responsavel_cpf,
        "responsavel_nis": f.responsavel_nis,
        "responsavel_cns": f.responsavel_cns,
        "responsavel_data_nascimento": str(f.responsavel_data_nascimento) if f.responsavel_data_nascimento else None,
        "responsavel_telefone": f.responsavel_telefone,
        "num_integrantes": f.num_integrantes,
        "renda_familiar_total": float(f.renda_familiar_total) if f.renda_familiar_total is not None else None,
        "endereco": f.endereco,
        "bairro": f.bairro,
        "cadUnico_numero_seq": f.cadUnico_numero_seq,
        "marcador_pbf": f.marcador_pbf,
        "marcador_bpc": f.marcador_bpc,
        "situacao": f.situacao,
        "unidade_cras_id": f.unidade_cras_id,
        "unidade_cras_nome": f.unidade_cras.nome if f.unidade_cras else None,
        "data_cadastro": str(f.data_cadastro),
        "observacoes": f.observacoes,
        "criado_em": f.criado_em.isoformat(),
    }


def _atendimento_dict(a):
    return {
        "id": a.id,
        "familia_id": a.familia_id,
        "familia_nome": a.familia.responsavel_nome,
        "unidade_cras_id": a.unidade_cras_id,
        "unidade_cras_nome": a.unidade_cras.nome if a.unidade_cras else None,
        "tecnico_nome": a.tecnico_nome,
        "tecnico_cargo": a.tecnico_cargo,
        "data_atendimento": str(a.data_atendimento),
        "tipo": a.tipo,
        "tipo_display": a.get_tipo_display(),
        "objetivo": a.objetivo,
        "descricao": a.descricao,
        "encaminhamento": a.encaminhamento,
        "criado_em": a.criado_em.isoformat(),
    }


def _visita_dict(v):
    return {
        "id": v.id,
        "familia_id": v.familia_id,
        "familia_nome": v.familia.responsavel_nome,
        "tecnico_nome": v.tecnico_nome,
        "data_visita": str(v.data_visita),
        "objetivo": v.objetivo,
        "relato": v.relato,
        "resultado": v.resultado,
        "vulnerabilidade_identificada": v.vulnerabilidade_identificada,
        "criado_em": v.criado_em.isoformat(),
    }


# ─── UNIDADES CRAS ───────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_unidades(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo — Assistência Social"}, status=403)

    from .models import UnidadeCRAS

    if request.method == "GET":
        ativo = request.GET.get("ativo")
        qs = UnidadeCRAS.objects.filter(empresa=empresa)
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() != "false"))
        return JsonResponse({"total": qs.count(), "unidades": [_cras_dict(u) for u in qs]})

    if request.method == "POST":
        body = json.loads(request.body)
        u = UnidadeCRAS.objects.create(
            empresa=empresa,
            nome=body.get("nome", "").strip(),
            codigo_cras=body.get("codigo_cras", "").strip(),
            cnes=body.get("cnes", "").strip(),
            endereco=body.get("endereco", "").strip(),
            bairro=body.get("bairro", "").strip(),
            municipio=body.get("municipio", "").strip(),
            uf=body.get("uf", "").strip().upper(),
            cep=body.get("cep", "").strip(),
            telefone=body.get("telefone", "").strip(),
            email=body.get("email", "").strip(),
            responsavel_tecnico=body.get("responsavel_tecnico", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": u.id, "nome": u.nome}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_unidade_detalhe(request, cras_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCRAS
    try:
        u = UnidadeCRAS.objects.get(id=cras_id, empresa=empresa)
    except UnidadeCRAS.DoesNotExist:
        return JsonResponse({"erro": "Unidade CRAS não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_cras_dict(u))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        campos = ["nome", "codigo_cras", "cnes", "endereco", "bairro", "municipio",
                  "cep", "telefone", "email", "responsavel_tecnico", "ativo"]
        for c in campos:
            if c in body:
                val = body[c].strip() if isinstance(body[c], str) else body[c]
                if c == "uf":
                    val = val.upper()
                setattr(u, c, val)
        u.save()
        return JsonResponse({"status": "atualizado", **_cras_dict(u)})

    if request.method == "DELETE":
        u.ativo = False
        u.save()
        return JsonResponse({"status": "desativado", "id": u.id})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── FAMÍLIAS CRAS ───────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_familias(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import FamiliaCRAS

    if request.method == "GET":
        qs = FamiliaCRAS.objects.filter(empresa=empresa).select_related("unidade_cras")
        situacao = request.GET.get("situacao")
        unidade_id = request.GET.get("unidade_cras_id")
        q = request.GET.get("q", "").strip()
        if situacao:
            qs = qs.filter(situacao=situacao)
        if unidade_id:
            qs = qs.filter(unidade_cras_id=unidade_id)
        if q:
            qs = qs.filter(responsavel_nome__icontains=q) | qs.filter(responsavel_cpf__icontains=q)
        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        familias = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({
            "total": total,
            "page": page,
            "paginas": (total + per_page - 1) // per_page,
            "familias": [_familia_dict(f) for f in familias],
        })

    if request.method == "POST":
        from .utils import validar_cpf_cadastro
        body = json.loads(request.body)
        cpf = body.get("responsavel_cpf", "").replace(".", "").replace("-", "").strip()
        ok, erro = validar_cpf_cadastro(cpf, empresa)
        if not ok:
            return JsonResponse({"erro": erro}, status=400)

        f = FamiliaCRAS.objects.create(
            empresa=empresa,
            numero_prontuario=body.get("numero_prontuario", "").strip(),
            responsavel_nome=body.get("responsavel_nome", "").strip(),
            responsavel_cpf=cpf,
            responsavel_nis=body.get("responsavel_nis", "").strip(),
            responsavel_cns=body.get("responsavel_cns", "").strip(),
            responsavel_data_nascimento=body.get("responsavel_data_nascimento") or None,
            responsavel_telefone=body.get("responsavel_telefone", "").strip(),
            num_integrantes=int(body.get("num_integrantes", 1)),
            renda_familiar_total=body.get("renda_familiar_total") or None,
            endereco=body.get("endereco", "").strip(),
            bairro=body.get("bairro", "").strip(),
            cadUnico_numero_seq=body.get("cadUnico_numero_seq", "").strip(),
            marcador_pbf=bool(body.get("marcador_pbf", False)),
            marcador_bpc=bool(body.get("marcador_bpc", False)),
            situacao=body.get("situacao", "em_acompanhamento"),
            observacoes=body.get("observacoes", "").strip(),
            unidade_cras_id=body.get("unidade_cras_id") or None,
        )
        return JsonResponse({"status": "criado", "id": f.id, **_familia_dict(f)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_familia_detalhe(request, familia_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import FamiliaCRAS
    try:
        f = FamiliaCRAS.objects.select_related("unidade_cras").get(id=familia_id, empresa=empresa)
    except FamiliaCRAS.DoesNotExist:
        return JsonResponse({"erro": "Família não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_familia_dict(f))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        campos_str = ["numero_prontuario", "responsavel_nome", "responsavel_nis",
                      "responsavel_cns", "responsavel_telefone", "endereco", "bairro",
                      "cadUnico_numero_seq", "situacao", "observacoes"]
        for c in campos_str:
            if c in body:
                setattr(f, c, body[c].strip() if isinstance(body[c], str) else body[c])
        if "responsavel_data_nascimento" in body:
            f.responsavel_data_nascimento = body["responsavel_data_nascimento"] or None
        if "num_integrantes" in body:
            f.num_integrantes = int(body["num_integrantes"])
        if "renda_familiar_total" in body:
            f.renda_familiar_total = body["renda_familiar_total"] or None
        if "marcador_pbf" in body:
            f.marcador_pbf = bool(body["marcador_pbf"])
        if "marcador_bpc" in body:
            f.marcador_bpc = bool(body["marcador_bpc"])
        if "unidade_cras_id" in body:
            f.unidade_cras_id = body["unidade_cras_id"] or None
        f.save()
        return JsonResponse({"status": "atualizado", **_familia_dict(f)})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── ATENDIMENTOS CRAS ───────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_atendimentos(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCRAS

    if request.method == "GET":
        qs = AtendimentoCRAS.objects.filter(empresa=empresa).select_related("familia", "unidade_cras")
        familia_id = request.GET.get("familia_id")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        tipo = request.GET.get("tipo")
        if familia_id:
            qs = qs.filter(familia_id=familia_id)
        if data_ini:
            qs = qs.filter(data_atendimento__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_atendimento__lte=data_fim)
        if tipo:
            qs = qs.filter(tipo=tipo)
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
        body = json.loads(request.body)
        a = AtendimentoCRAS.objects.create(
            empresa=empresa,
            familia_id=body["familia_id"],
            unidade_cras_id=body.get("unidade_cras_id") or None,
            tecnico_nome=body.get("tecnico_nome", "").strip(),
            tecnico_cargo=body.get("tecnico_cargo", "").strip(),
            data_atendimento=body.get("data_atendimento", str(date.today())),
            tipo=body.get("tipo", "individual"),
            objetivo=body.get("objetivo", "").strip(),
            descricao=body.get("descricao", "").strip(),
            encaminhamento=body.get("encaminhamento", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": a.id, **_atendimento_dict(a)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_atendimento_detalhe(request, atendimento_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCRAS
    try:
        a = AtendimentoCRAS.objects.select_related("familia", "unidade_cras").get(
            id=atendimento_id, empresa=empresa
        )
    except AtendimentoCRAS.DoesNotExist:
        return JsonResponse({"erro": "Atendimento não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_atendimento_dict(a))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        for c in ["tecnico_nome", "tecnico_cargo", "objetivo", "descricao", "encaminhamento", "tipo"]:
            if c in body:
                setattr(a, c, body[c].strip() if isinstance(body[c], str) else body[c])
        if "data_atendimento" in body:
            a.data_atendimento = body["data_atendimento"]
        a.save()
        return JsonResponse({"status": "atualizado", **_atendimento_dict(a)})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── VISITAS DOMICILIARES SOCIAIS ────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cras_visitas(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import VisitaDomiciliarSocial

    if request.method == "GET":
        qs = VisitaDomiciliarSocial.objects.filter(empresa=empresa).select_related("familia")
        familia_id = request.GET.get("familia_id")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        vulnerabilidade = request.GET.get("vulnerabilidade")
        if familia_id:
            qs = qs.filter(familia_id=familia_id)
        if data_ini:
            qs = qs.filter(data_visita__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_visita__lte=data_fim)
        if vulnerabilidade is not None:
            qs = qs.filter(vulnerabilidade_identificada=(vulnerabilidade.lower() != "false"))
        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        visitas = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({
            "total": total,
            "page": page,
            "paginas": (total + per_page - 1) // per_page,
            "visitas": [_visita_dict(v) for v in visitas],
        })

    if request.method == "POST":
        body = json.loads(request.body)
        v = VisitaDomiciliarSocial.objects.create(
            empresa=empresa,
            familia_id=body["familia_id"],
            tecnico_nome=body.get("tecnico_nome", "").strip(),
            data_visita=body.get("data_visita", str(date.today())),
            objetivo=body.get("objetivo", "").strip(),
            relato=body.get("relato", "").strip(),
            resultado=body.get("resultado", "").strip(),
            vulnerabilidade_identificada=bool(body.get("vulnerabilidade_identificada", False)),
        )
        return JsonResponse({"status": "criado", "id": v.id, **_visita_dict(v)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── KPIs CRAS ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_cras_kpis(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial
    from django.db.models import Count, Q

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_ano = hoje.replace(month=1, day=1)

    total_cras = UnidadeCRAS.objects.filter(empresa=empresa, ativo=True).count()
    total_familias = FamiliaCRAS.objects.filter(empresa=empresa).count()
    familias_em_acomp = FamiliaCRAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    familias_pbf = FamiliaCRAS.objects.filter(empresa=empresa, marcador_pbf=True).count()
    familias_bpc = FamiliaCRAS.objects.filter(empresa=empresa, marcador_bpc=True).count()

    atendimentos_mes = AtendimentoCRAS.objects.filter(
        empresa=empresa, data_atendimento__gte=inicio_mes
    ).count()
    atendimentos_ano = AtendimentoCRAS.objects.filter(
        empresa=empresa, data_atendimento__gte=inicio_ano
    ).count()

    visitas_mes = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__gte=inicio_mes
    ).count()
    vulnerabilidades_mes = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__gte=inicio_mes, vulnerabilidade_identificada=True
    ).count()

    por_situacao = (
        FamiliaCRAS.objects.filter(empresa=empresa)
        .values("situacao")
        .annotate(total=Count("id"))
    )

    return JsonResponse({
        "total_cras": total_cras,
        "total_familias": total_familias,
        "familias_em_acompanhamento": familias_em_acomp,
        "familias_pbf": familias_pbf,
        "familias_bpc": familias_bpc,
        "atendimentos_mes": atendimentos_mes,
        "atendimentos_ano": atendimentos_ano,
        "visitas_domiciliares_mes": visitas_mes,
        "vulnerabilidades_identificadas_mes": vulnerabilidades_mes,
        "familias_por_situacao": {s["situacao"]: s["total"] for s in por_situacao},
        "referencia_mes": str(inicio_mes),
    })
