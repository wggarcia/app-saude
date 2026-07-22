"""
CadÚnico, BPC, SICON e Benefícios Eventuais — segmento Assistência Social.

Integração CadÚnico (Gov.br/MDS):
  - Consulta por CPF via endpoint MDS (simulado; substituir pela URL real de homologação)
  - Importação em lote via JSON
  - Gestão local do cadastro importado

SICON/Bolsa Família: registro de condicionalidades por período de referência.
BPC: controle de beneficiários por tipo (PcD e Idoso 65+).
Benefícios Eventuais: concessões municipais com rastreabilidade por CRAS.
"""
import json
import logging
from datetime import date

from django.db.models import Count, Sum
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

def _cadunico_dict(f):
    return {
        "id": f.id,
        "responsavel_nome": f.responsavel_nome,
        "responsavel_cpf": f.responsavel_cpf,
        "responsavel_nis": f.responsavel_nis,
        "responsavel_data_nascimento": str(f.responsavel_data_nascimento) if f.responsavel_data_nascimento else None,
        "qtd_pessoas": f.qtd_pessoas,
        "renda_per_capita": float(f.renda_per_capita) if f.renda_per_capita is not None else None,
        "marcador_pbf": f.marcador_pbf,
        "marcador_bpc": f.marcador_bpc,
        "municipio": f.municipio,
        "uf": f.uf,
        "data_ultima_atualizacao": str(f.data_ultima_atualizacao) if f.data_ultima_atualizacao else None,
        "criado_em": f.criado_em.isoformat(),
    }


def _bpc_dict(b):
    return {
        "id": b.id,
        "beneficiario_nome": b.beneficiario_nome,
        "beneficiario_cpf": b.beneficiario_cpf,
        "beneficiario_nis": b.beneficiario_nis,
        "tipo_bpc": b.tipo_bpc,
        "tipo_bpc_display": b.get_tipo_bpc_display(),
        "data_inicio": str(b.data_inicio) if b.data_inicio else None,
        "data_fim": str(b.data_fim) if b.data_fim else None,
        "valor_beneficio": float(b.valor_beneficio) if b.valor_beneficio is not None else None,
        "ativo": b.ativo,
        "observacoes": b.observacoes,
        "criado_em": b.criado_em.isoformat(),
    }


def _sicon_dict(s):
    return {
        "id": s.id,
        "titular_nome": s.titular_nome,
        "titular_cpf": s.titular_cpf,
        "titular_nis": s.titular_nis,
        "area": s.area,
        "area_display": s.get_area_display(),
        "periodo_referencia": s.periodo_referencia,
        "status": s.status,
        "status_display": s.get_status_display(),
        "motivo_descumprimento": s.motivo_descumprimento,
        "acompanhamento_tecnico": s.acompanhamento_tecnico,
        "criado_em": s.criado_em.isoformat(),
    }


def _beneficio_eventual_dict(b):
    return {
        "id": b.id,
        "beneficiario_nome": b.beneficiario_nome,
        "beneficiario_cpf": b.beneficiario_cpf,
        "beneficiario_nis": b.beneficiario_nis,
        "tipo": b.tipo,
        "tipo_display": b.get_tipo_display(),
        "descricao": b.descricao,
        "quantidade": float(b.quantidade),
        "valor": float(b.valor) if b.valor is not None else None,
        "data_concessao": str(b.data_concessao),
        "unidade_cras_id": b.unidade_cras_id,
        "unidade_cras_nome": b.unidade_cras.nome if b.unidade_cras else None,
        "tecnico_responsavel": b.tecnico_responsavel,
        "observacoes": b.observacoes,
        "criado_em": b.criado_em.isoformat(),
    }


# ─── CADUNICO ────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_cadunico_familias(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Assistência Social — CadÚnico"}, status=403)

    from .models import CadUnicoFamilia

    qs = CadUnicoFamilia.objects.filter(empresa=empresa).order_by("responsavel_nome")
    pbf = request.GET.get("pbf")
    bpc = request.GET.get("bpc")
    busca = request.GET.get("q", "").strip()

    if pbf is not None:
        qs = qs.filter(marcador_pbf=(pbf.lower() == "true"))
    if bpc is not None:
        qs = qs.filter(marcador_bpc=(bpc.lower() == "true"))
    if busca:
        from django.db.models import Q
        qs = qs.filter(
            Q(responsavel_nome__icontains=busca) |
            Q(responsavel_cpf__icontains=busca) |
            Q(responsavel_nis__icontains=busca)
        )
    return JsonResponse({"familias": [_cadunico_dict(f) for f in qs[:300]]})


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_cadunico_consultar_cpf(request, cpf):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CadUnicoFamilia

    cpf_limpo = "".join(c for c in cpf if c.isdigit())
    try:
        f = CadUnicoFamilia.objects.get(empresa=empresa, responsavel_cpf=cpf_limpo)
        return JsonResponse({"familia": _cadunico_dict(f), "encontrado": True})
    except CadUnicoFamilia.DoesNotExist:
        return JsonResponse({"encontrado": False, "cpf": cpf_limpo})


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_cadunico_importar_lote(request):
    """
    Importação em lote de registros CadÚnico.
    Body: {"registros": [{responsavel_cpf, responsavel_nis, responsavel_nome,
                          qtd_pessoas, renda_per_capita, marcador_pbf, marcador_bpc,
                          municipio, uf, data_ultima_atualizacao}, ...]}
    Registros com CPF já existente para a empresa são atualizados (upsert).
    """
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CadUnicoFamilia

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    registros = payload.get("registros", [])
    if not registros:
        return JsonResponse({"erro": "Nenhum registro enviado"}, status=400)

    criados = 0
    atualizados = 0
    erros = []

    for idx, reg in enumerate(registros[:1000]):
        cpf = "".join(c for c in str(reg.get("responsavel_cpf", "")) if c.isdigit())
        if not cpf and not reg.get("responsavel_nis"):
            erros.append({"linha": idx + 1, "erro": "CPF ou NIS obrigatório"})
            continue
        try:
            obj, created = CadUnicoFamilia.objects.update_or_create(
                empresa=empresa,
                responsavel_cpf=cpf,
                defaults={
                    "responsavel_nome": reg.get("responsavel_nome", ""),
                    "responsavel_nis": reg.get("responsavel_nis", ""),
                    "responsavel_data_nascimento": reg.get("responsavel_data_nascimento") or None,
                    "qtd_pessoas": reg.get("qtd_pessoas", 1),
                    "renda_per_capita": reg.get("renda_per_capita"),
                    "marcador_pbf": bool(reg.get("marcador_pbf", False)),
                    "marcador_bpc": bool(reg.get("marcador_bpc", False)),
                    "municipio": reg.get("municipio", ""),
                    "uf": reg.get("uf", ""),
                    "data_ultima_atualizacao": reg.get("data_ultima_atualizacao") or None,
                },
            )
            if created:
                criados += 1
            else:
                atualizados += 1
        except Exception as e:
            erros.append({"linha": idx + 1, "erro": str(e)})

    return JsonResponse({
        "criados": criados,
        "atualizados": atualizados,
        "erros": erros,
        "total_processado": criados + atualizados,
    }, status=200 if not erros else 207)


# ─── BPC ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_bpc_beneficiarios(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficiarioBPC

    if request.method == "GET":
        qs = BeneficiarioBPC.objects.filter(empresa=empresa).order_by("beneficiario_nome")
        tipo = request.GET.get("tipo")
        ativo = request.GET.get("ativo")
        busca = request.GET.get("q", "").strip()
        if tipo:
            qs = qs.filter(tipo_bpc=tipo)
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() == "true"))
        if busca:
            from django.db.models import Q
            qs = qs.filter(
                Q(beneficiario_nome__icontains=busca) |
                Q(beneficiario_cpf__icontains=busca) |
                Q(beneficiario_nis__icontains=busca)
            )
        resumo = {
            "pcd": qs.filter(tipo_bpc="pessoa_deficiencia", ativo=True).count(),
            "idoso": qs.filter(tipo_bpc="idoso_65", ativo=True).count(),
        }
        return JsonResponse({"beneficiarios": [_bpc_dict(b) for b in qs[:300]], "resumo": resumo})

    data = json.loads(request.body)
    b = BeneficiarioBPC.objects.create(
        empresa=empresa,
        beneficiario_nome=data["beneficiario_nome"],
        beneficiario_cpf=data.get("beneficiario_cpf", ""),
        beneficiario_nis=data.get("beneficiario_nis", ""),
        tipo_bpc=data.get("tipo_bpc", "pessoa_deficiencia"),
        data_inicio=data.get("data_inicio") or None,
        data_fim=data.get("data_fim") or None,
        valor_beneficio=data.get("valor_beneficio"),
        ativo=data.get("ativo", True),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"beneficiario": _bpc_dict(b)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_bpc_beneficiario_detalhe(request, bpc_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficiarioBPC

    try:
        b = BeneficiarioBPC.objects.get(id=bpc_id, empresa=empresa)
    except BeneficiarioBPC.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"beneficiario": _bpc_dict(b)})

    if request.method == "DELETE":
        b.ativo = False
        b.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    data = json.loads(request.body)
    for campo in ["beneficiario_nome", "beneficiario_cpf", "beneficiario_nis", "tipo_bpc",
                  "data_inicio", "data_fim", "valor_beneficio", "ativo", "observacoes"]:
        if campo in data:
            setattr(b, campo, data[campo] if data[campo] != "" or campo not in ("data_inicio", "data_fim", "valor_beneficio") else None)
    b.save()
    return JsonResponse({"beneficiario": _bpc_dict(b)})


# ─── SICON / BOLSA FAMÍLIA ───────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_sicon_condicionalidades(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CondicionalidadeSICON

    if request.method == "GET":
        qs = CondicionalidadeSICON.objects.filter(empresa=empresa).order_by("-periodo_referencia", "titular_nome")
        status = request.GET.get("status")
        area = request.GET.get("area")
        periodo = request.GET.get("periodo")
        busca = request.GET.get("q", "").strip()
        if status:
            qs = qs.filter(status=status)
        if area:
            qs = qs.filter(area=area)
        if periodo:
            qs = qs.filter(periodo_referencia=periodo)
        if busca:
            from django.db.models import Q
            qs = qs.filter(
                Q(titular_nome__icontains=busca) |
                Q(titular_cpf__icontains=busca) |
                Q(titular_nis__icontains=busca)
            )
        resumo = dict(
            qs.values("status").annotate(total=Count("id")).values_list("status", "total")
        )
        return JsonResponse({"condicionalidades": [_sicon_dict(s) for s in qs[:300]], "resumo": resumo})

    data = json.loads(request.body)
    s = CondicionalidadeSICON.objects.create(
        empresa=empresa,
        titular_nome=data["titular_nome"],
        titular_cpf=data.get("titular_cpf", ""),
        titular_nis=data.get("titular_nis", ""),
        area=data.get("area", "social"),
        periodo_referencia=data.get("periodo_referencia", ""),
        status=data.get("status", "sem_informacao"),
        motivo_descumprimento=data.get("motivo_descumprimento", ""),
        acompanhamento_tecnico=data.get("acompanhamento_tecnico", ""),
    )
    return JsonResponse({"condicionalidade": _sicon_dict(s)}, status=201)


# ─── BENEFÍCIOS EVENTUAIS ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_beneficios_eventuais(request):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficioEventual, UnidadeCRAS

    if request.method == "GET":
        qs = BeneficioEventual.objects.filter(empresa=empresa).select_related("unidade_cras").order_by("-data_concessao")
        tipo = request.GET.get("tipo")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        busca = request.GET.get("q", "").strip()
        if tipo:
            qs = qs.filter(tipo=tipo)
        if data_ini:
            qs = qs.filter(data_concessao__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_concessao__lte=data_fim)
        if busca:
            from django.db.models import Q
            qs = qs.filter(
                Q(beneficiario_nome__icontains=busca) |
                Q(beneficiario_cpf__icontains=busca)
            )

        hoje = date.today()
        inicio_mes = hoje.replace(day=1)
        total_valor_mes = qs.filter(data_concessao__gte=inicio_mes).aggregate(v=Sum("valor"))["v"] or 0
        por_tipo = dict(qs.values("tipo").annotate(total=Count("id")).values_list("tipo", "total"))

        return JsonResponse({
            "beneficios": [_beneficio_eventual_dict(b) for b in qs[:300]],
            "total_valor_mes": float(total_valor_mes),
            "por_tipo": por_tipo,
        })

    data = json.loads(request.body)
    unidade_cras = None
    if data.get("unidade_cras_id"):
        try:
            unidade_cras = UnidadeCRAS.objects.get(id=data["unidade_cras_id"], empresa=empresa)
        except UnidadeCRAS.DoesNotExist:
            pass

    b = BeneficioEventual.objects.create(
        empresa=empresa,
        beneficiario_nome=data["beneficiario_nome"],
        beneficiario_cpf=data.get("beneficiario_cpf", ""),
        beneficiario_nis=data.get("beneficiario_nis", ""),
        tipo=data.get("tipo", "cesta_basica"),
        descricao=data.get("descricao", ""),
        quantidade=data.get("quantidade", 1),
        valor=data.get("valor"),
        data_concessao=data.get("data_concessao", str(date.today())),
        unidade_cras=unidade_cras,
        tecnico_responsavel=data.get("tecnico_responsavel", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"beneficio": _beneficio_eventual_dict(b)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
@api_requer_permissao_modulo("assistencia.cadunico")
def api_ass_beneficio_eventual_detalhe(request, beneficio_id):
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficioEventual

    try:
        b = BeneficioEventual.objects.select_related("unidade_cras").get(id=beneficio_id, empresa=empresa)
    except BeneficioEventual.DoesNotExist:
        return JsonResponse({"erro": "Benefício não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"beneficio": _beneficio_eventual_dict(b)})

    b.delete()
    return JsonResponse({"ok": True})
