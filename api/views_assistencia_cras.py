import json
import logging
from datetime import date

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
        "descricao": a.descricao,
        "encaminhamentos": a.encaminhamentos,
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


def _prontuario_paif_dict(p):
    return {
        "id": p.id,
        "familia_id": p.familia_id,
        "familia_nome": p.familia.responsavel_nome,
        "unidade_cras_id": p.unidade_cras_id,
        "unidade_cras_nome": p.unidade_cras.nome if p.unidade_cras else None,
        "tecnico_responsavel": p.tecnico_responsavel,
        "data_abertura": str(p.data_abertura),
        "data_encerramento": str(p.data_encerramento) if p.data_encerramento else None,
        "modalidade": p.modalidade,
        "situacoes_vulnerabilidade": p.situacoes_vulnerabilidade,
        "objetivos": p.objetivos,
        "evolucao": p.evolucao,
        "encaminhamentos": p.encaminhamentos,
        "plano_acao_familiar": p.plano_acao_familiar,
        "ativo": p.ativo,
        "criado_em": p.criado_em.isoformat(),
    }


# ─── UNIDADES CRAS ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_unidades(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Assistência Social — CRAS/PAIF"}, status=403)

    from .models import UnidadeCRAS

    if request.method == "GET":
        qs = UnidadeCRAS.objects.filter(empresa=empresa).order_by("nome")
        ativo = request.GET.get("ativo")
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() == "true"))
        return JsonResponse({"unidades": [_cras_dict(u) for u in qs]})

    data = json.loads(request.body)
    u = UnidadeCRAS.objects.create(
        empresa=empresa,
        nome=data["nome"],
        codigo_cras=data.get("codigo_cras", ""),
        cnes=data.get("cnes", ""),
        endereco=data.get("endereco", ""),
        bairro=data.get("bairro", ""),
        municipio=data.get("municipio", ""),
        uf=data.get("uf", ""),
        cep=data.get("cep", ""),
        telefone=data.get("telefone", ""),
        email=data.get("email", ""),
        responsavel_tecnico=data.get("responsavel_tecnico", ""),
    )
    return JsonResponse({"unidade": _cras_dict(u)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_unidade_detalhe(request, cras_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCRAS

    try:
        u = UnidadeCRAS.objects.get(id=cras_id, empresa=empresa)
    except UnidadeCRAS.DoesNotExist:
        return JsonResponse({"erro": "Unidade não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"unidade": _cras_dict(u)})

    if request.method == "DELETE":
        u.ativo = False
        u.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    data = json.loads(request.body)
    campos = ["nome", "codigo_cras", "cnes", "endereco", "bairro", "municipio", "uf", "cep", "telefone", "email", "responsavel_tecnico", "ativo"]
    for campo in campos:
        if campo in data:
            setattr(u, campo, data[campo])
    u.save()
    return JsonResponse({"unidade": _cras_dict(u)})


# ─── FAMÍLIAS ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_familias(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import FamiliaCRAS, UnidadeCRAS

    if request.method == "GET":
        qs = FamiliaCRAS.objects.filter(empresa=empresa).select_related("unidade_cras").order_by("-data_cadastro")
        situacao = request.GET.get("situacao")
        cras_id = request.GET.get("cras_id")
        busca = request.GET.get("q", "").strip()
        if situacao:
            qs = qs.filter(situacao=situacao)
        if cras_id:
            qs = qs.filter(unidade_cras_id=cras_id)
        if busca:
            from django.db.models import Q
            qs = qs.filter(
                Q(responsavel_nome__icontains=busca) |
                Q(responsavel_cpf__icontains=busca) |
                Q(responsavel_nis__icontains=busca)
            )
        return JsonResponse({"familias": [_familia_dict(f) for f in qs[:200]]})

    data = json.loads(request.body)
    unidade_cras = None
    if data.get("unidade_cras_id"):
        try:
            unidade_cras = UnidadeCRAS.objects.get(id=data["unidade_cras_id"], empresa=empresa)
        except UnidadeCRAS.DoesNotExist:
            return JsonResponse({"erro": "Unidade CRAS não encontrada"}, status=400)

    # Pré-preenche com dados do CadÚnico quando NIS ou CPF é informado e os
    # campos correspondentes não vieram no payload (não sobrescreve intencional).
    nis = (data.get("responsavel_nis") or "").strip()
    cpf = (data.get("responsavel_cpf") or "").strip()
    if nis or cpf:
        from .models import CadUnicoFamilia
        from django.db.models import Q
        cad = CadUnicoFamilia.objects.filter(empresa=empresa).filter(
            Q(responsavel_nis=nis) if nis else Q() | Q(responsavel_cpf=cpf) if cpf else Q()
        ).first()
        if cad:
            if not data.get("renda_familiar_total") and cad.renda_per_capita:
                data["renda_familiar_total"] = float(cad.renda_per_capita) * cad.qtd_pessoas
            if not data.get("num_integrantes"):
                data["num_integrantes"] = cad.qtd_pessoas
            if not data.get("cadUnico_numero_seq") and cad.numero_seq:
                data["cadUnico_numero_seq"] = cad.numero_seq
            if not data.get("marcador_pbf"):
                data["marcador_pbf"] = cad.marcador_pbf
            if not data.get("marcador_bpc"):
                data["marcador_bpc"] = cad.marcador_bpc

    f = FamiliaCRAS.objects.create(
        empresa=empresa,
        unidade_cras=unidade_cras,
        responsavel_nome=data["responsavel_nome"],
        responsavel_cpf=data.get("responsavel_cpf", ""),
        responsavel_nis=data.get("responsavel_nis", ""),
        responsavel_cns=data.get("responsavel_cns", ""),
        responsavel_data_nascimento=data.get("responsavel_data_nascimento") or None,
        responsavel_telefone=data.get("responsavel_telefone", ""),
        num_integrantes=data.get("num_integrantes", 1),
        renda_familiar_total=data.get("renda_familiar_total"),
        endereco=data.get("endereco", ""),
        bairro=data.get("bairro", ""),
        cadUnico_numero_seq=data.get("cadUnico_numero_seq", ""),
        marcador_pbf=data.get("marcador_pbf", False),
        marcador_bpc=data.get("marcador_bpc", False),
        situacao=data.get("situacao", "ativo"),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"familia": _familia_dict(f)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_familia_detalhe(request, familia_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import FamiliaCRAS

    try:
        f = FamiliaCRAS.objects.select_related("unidade_cras").get(id=familia_id, empresa=empresa)
    except FamiliaCRAS.DoesNotExist:
        return JsonResponse({"erro": "Família não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"familia": _familia_dict(f)})

    if request.method == "DELETE":
        f.situacao = "encerrado"
        f.save(update_fields=["situacao"])
        return JsonResponse({"ok": True})

    data = json.loads(request.body)
    campos = [
        "responsavel_nome", "responsavel_cpf", "responsavel_nis", "responsavel_cns",
        "responsavel_data_nascimento", "responsavel_telefone", "num_integrantes",
        "renda_familiar_total", "endereco", "bairro", "cadUnico_numero_seq",
        "marcador_pbf", "marcador_bpc", "situacao", "observacoes",
    ]
    for campo in campos:
        if campo in data:
            setattr(f, campo, data[campo] if data[campo] != "" else None if campo in ("responsavel_data_nascimento", "renda_familiar_total") else data[campo])
    if "unidade_cras_id" in data:
        from .models import UnidadeCRAS
        try:
            f.unidade_cras = UnidadeCRAS.objects.get(id=data["unidade_cras_id"], empresa=empresa) if data["unidade_cras_id"] else None
        except UnidadeCRAS.DoesNotExist:
            return JsonResponse({"erro": "Unidade CRAS não encontrada"}, status=400)
    f.save()
    return JsonResponse({"familia": _familia_dict(f)})


# ─── ATENDIMENTOS PAIF ──────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_atendimentos(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCRAS, FamiliaCRAS, UnidadeCRAS

    if request.method == "GET":
        qs = AtendimentoCRAS.objects.filter(empresa=empresa).select_related("familia", "unidade_cras").order_by("-data_atendimento")
        familia_id = request.GET.get("familia_id")
        cras_id = request.GET.get("cras_id")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        if familia_id:
            qs = qs.filter(familia_id=familia_id)
        if cras_id:
            qs = qs.filter(unidade_cras_id=cras_id)
        if data_ini:
            qs = qs.filter(data_atendimento__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_atendimento__lte=data_fim)
        return JsonResponse({"atendimentos": [_atendimento_dict(a) for a in qs[:300]]})

    data = json.loads(request.body)
    try:
        familia = FamiliaCRAS.objects.get(id=data["familia_id"], empresa=empresa)
    except FamiliaCRAS.DoesNotExist:
        return JsonResponse({"erro": "Família não encontrada"}, status=400)

    unidade_cras = None
    if data.get("unidade_cras_id"):
        try:
            unidade_cras = UnidadeCRAS.objects.get(id=data["unidade_cras_id"], empresa=empresa)
        except UnidadeCRAS.DoesNotExist:
            pass

    a = AtendimentoCRAS.objects.create(
        empresa=empresa,
        familia=familia,
        unidade_cras=unidade_cras,
        tecnico_nome=data.get("tecnico_nome", ""),
        tecnico_cargo=data.get("tecnico_cargo", ""),
        data_atendimento=data.get("data_atendimento", str(date.today())),
        tipo=data.get("tipo", "individual"),
        descricao=data.get("descricao", ""),
        encaminhamentos=data.get("encaminhamentos", ""),
    )
    return JsonResponse({"atendimento": _atendimento_dict(a)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_atendimento_detalhe(request, atendimento_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import AtendimentoCRAS

    try:
        a = AtendimentoCRAS.objects.select_related("familia", "unidade_cras").get(id=atendimento_id, empresa=empresa)
    except AtendimentoCRAS.DoesNotExist:
        return JsonResponse({"erro": "Atendimento não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"atendimento": _atendimento_dict(a)})

    if request.method == "DELETE":
        a.delete()
        return JsonResponse({"ok": True})

    data = json.loads(request.body)
    for campo in ["tecnico_nome", "tecnico_cargo", "data_atendimento", "tipo", "descricao", "encaminhamentos"]:
        if campo in data:
            setattr(a, campo, data[campo])
    a.save()
    return JsonResponse({"atendimento": _atendimento_dict(a)})


# ─── VISITAS DOMICILIARES ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_visitas(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import VisitaDomiciliarSocial, FamiliaCRAS

    if request.method == "GET":
        qs = VisitaDomiciliarSocial.objects.filter(empresa=empresa).select_related("familia").order_by("-data_visita")
        familia_id = request.GET.get("familia_id")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        vulneravel = request.GET.get("vulnerabilidade")
        if familia_id:
            qs = qs.filter(familia_id=familia_id)
        if data_ini:
            qs = qs.filter(data_visita__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_visita__lte=data_fim)
        if vulneravel is not None:
            qs = qs.filter(vulnerabilidade_identificada=(vulneravel.lower() == "true"))
        return JsonResponse({"visitas": [_visita_dict(v) for v in qs[:300]]})

    data = json.loads(request.body)
    try:
        familia = FamiliaCRAS.objects.get(id=data["familia_id"], empresa=empresa)
    except FamiliaCRAS.DoesNotExist:
        return JsonResponse({"erro": "Família não encontrada"}, status=400)

    v = VisitaDomiciliarSocial.objects.create(
        empresa=empresa,
        familia=familia,
        tecnico_nome=data.get("tecnico_nome", ""),
        data_visita=data.get("data_visita", str(date.today())),
        objetivo=data.get("objetivo", ""),
        relato=data.get("relato", ""),
        resultado=data.get("resultado", ""),
        vulnerabilidade_identificada=data.get("vulnerabilidade_identificada", False),
    )
    return JsonResponse({"visita": _visita_dict(v)}, status=201)


# ─── PRONTUÁRIOS PAIF ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_prontuarios_paif(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import ProntuarioSocialPAIF, FamiliaCRAS, UnidadeCRAS

    if request.method == "GET":
        qs = ProntuarioSocialPAIF.objects.filter(empresa=empresa).select_related("familia", "unidade_cras").order_by("-data_abertura")
        familia_id = request.GET.get("familia_id")
        ativo = request.GET.get("ativo")
        if familia_id:
            qs = qs.filter(familia_id=familia_id)
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() == "true"))
        return JsonResponse({"prontuarios": [_prontuario_paif_dict(p) for p in qs[:200]]})

    data = json.loads(request.body)
    try:
        familia = FamiliaCRAS.objects.get(id=data["familia_id"], empresa=empresa)
    except FamiliaCRAS.DoesNotExist:
        return JsonResponse({"erro": "Família não encontrada"}, status=400)

    unidade_cras = None
    if data.get("unidade_cras_id"):
        try:
            unidade_cras = UnidadeCRAS.objects.get(id=data["unidade_cras_id"], empresa=empresa)
        except UnidadeCRAS.DoesNotExist:
            pass

    p = ProntuarioSocialPAIF.objects.create(
        empresa=empresa,
        familia=familia,
        unidade_cras=unidade_cras,
        tecnico_responsavel=data.get("tecnico_responsavel", ""),
        data_abertura=data.get("data_abertura", str(date.today())),
        data_encerramento=data.get("data_encerramento") or None,
        modalidade=data.get("modalidade", "acompanhamento_paif"),
        situacoes_vulnerabilidade=data.get("situacoes_vulnerabilidade", []),
        objetivos=data.get("objetivos", ""),
        evolucao=data.get("evolucao", ""),
        encaminhamentos=data.get("encaminhamentos", ""),
        plano_acao_familiar=data.get("plano_acao_familiar", ""),
    )
    return JsonResponse({"prontuario": _prontuario_paif_dict(p)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_prontuario_paif_detalhe(request, prontuario_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import ProntuarioSocialPAIF

    try:
        p = ProntuarioSocialPAIF.objects.select_related("familia", "unidade_cras").get(id=prontuario_id, empresa=empresa)
    except ProntuarioSocialPAIF.DoesNotExist:
        return JsonResponse({"erro": "Prontuário não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"prontuario": _prontuario_paif_dict(p)})

    data = json.loads(request.body)
    for campo in ["tecnico_responsavel", "data_abertura", "data_encerramento", "modalidade",
                  "situacoes_vulnerabilidade", "objetivos", "evolucao", "encaminhamentos",
                  "plano_acao_familiar", "ativo"]:
        if campo in data:
            setattr(p, campo, data[campo] if data[campo] != "" or campo not in ("data_encerramento",) else None)
    p.save()
    return JsonResponse({"prontuario": _prontuario_paif_dict(p)})


# ─── KPIs CRAS ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.cras_paif")
def api_ass_cras_kpis(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial, ProntuarioSocialPAIF
    from django.db.models import Count

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    unidades_ativas = UnidadeCRAS.objects.filter(empresa=empresa, ativo=True).count()
    familias_total = FamiliaCRAS.objects.filter(empresa=empresa).count()
    familias_acomp = FamiliaCRAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    atend_mes = AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()
    visitas_mes = VisitaDomiciliarSocial.objects.filter(empresa=empresa, data_visita__gte=inicio_mes).count()
    vulnerabilidades_mes = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__gte=inicio_mes, vulnerabilidade_identificada=True
    ).count()
    prontuarios_abertos = ProntuarioSocialPAIF.objects.filter(empresa=empresa, ativo=True).count()
    por_situacao = dict(
        FamiliaCRAS.objects.filter(empresa=empresa)
        .values("situacao").annotate(total=Count("id"))
        .values_list("situacao", "total")
    )

    return JsonResponse({
        "referencia_mes": str(inicio_mes),
        "unidades_ativas": unidades_ativas,
        "familias_total": familias_total,
        "familias_em_acompanhamento": familias_acomp,
        "atendimentos_mes": atend_mes,
        "visitas_domiciliares_mes": visitas_mes,
        "vulnerabilidades_identificadas_mes": vulnerabilidades_mes,
        "prontuarios_paif_abertos": prontuarios_abertos,
        "familias_por_situacao": por_situacao,
    })
