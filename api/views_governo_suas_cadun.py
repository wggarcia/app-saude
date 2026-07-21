"""
CadÚnico · BPC · SICON · Benefícios Eventuais

CadÚnico (Cadastro Único para Programas Sociais do Governo Federal):
  - Consulta via API Gov.br/MDS (requer credencial do município)
  - Endpoint: https://apigateway.conectagov.estaleiro.serpro.gov.br/api-cadunico/v2/
  - Autenticação OAuth2 com client_id/client_secret do município
  - As famílias importadas ficam em CadUnicoFamilia (cache local)
"""
import json
import logging
from datetime import date

from django.conf import settings
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

def _cadunico_dict(f):
    return {
        "id": f.id,
        "numero_seq": f.numero_seq,
        "cod_familiar_fam": f.cod_familiar_fam,
        "responsavel_nome": f.responsavel_nome,
        "responsavel_cpf": f.responsavel_cpf,
        "responsavel_nis": f.responsavel_nis,
        "qtd_pessoas": f.qtd_pessoas,
        "renda_per_capita": float(f.renda_per_capita) if f.renda_per_capita is not None else None,
        "data_cadastramento": str(f.data_cadastramento) if f.data_cadastramento else None,
        "data_ultima_atualizacao": str(f.data_ultima_atualizacao) if f.data_ultima_atualizacao else None,
        "marcador_pbf": f.marcador_pbf,
        "marcador_bpc": f.marcador_bpc,
        "municipio": f.municipio,
        "uf": f.uf,
        "importado_em": f.importado_em.isoformat(),
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


def _beneficio_dict(b):
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


# ─── CadÚnico ────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_cadunico_familias(request):
    """Lista/busca famílias do CadÚnico (cache local após importação)."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CadUnicoFamilia

    if request.method == "GET":
        qs = CadUnicoFamilia.objects.filter(empresa=empresa)
        q = request.GET.get("q", "").strip()
        pbf = request.GET.get("pbf")
        bpc = request.GET.get("bpc")
        if q:
            qs = (
                qs.filter(responsavel_nome__icontains=q) |
                qs.filter(responsavel_cpf__icontains=q) |
                qs.filter(responsavel_nis__icontains=q)
            )
        if pbf is not None:
            qs = qs.filter(marcador_pbf=(pbf.lower() != "false"))
        if bpc is not None:
            qs = qs.filter(marcador_bpc=(bpc.lower() != "false"))
        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        familias = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({
            "total": total,
            "page": page,
            "paginas": (total + per_page - 1) // per_page,
            "familias": [_cadunico_dict(f) for f in familias],
        })

    if request.method == "POST":
        # Importação manual de uma família (para municípios sem API conectada)
        body = json.loads(request.body)
        cpf = body.get("responsavel_cpf", "").replace(".", "").replace("-", "").strip()
        f, criado = CadUnicoFamilia.objects.update_or_create(
            empresa=empresa,
            responsavel_cpf=cpf,
            defaults={
                "numero_seq": body.get("numero_seq", "").strip(),
                "cod_familiar_fam": body.get("cod_familiar_fam", "").strip(),
                "responsavel_nome": body.get("responsavel_nome", "").strip(),
                "responsavel_nis": body.get("responsavel_nis", "").strip(),
                "qtd_pessoas": int(body.get("qtd_pessoas", 1)),
                "renda_per_capita": body.get("renda_per_capita") or None,
                "data_cadastramento": body.get("data_cadastramento") or None,
                "data_ultima_atualizacao": body.get("data_ultima_atualizacao") or None,
                "marcador_pbf": bool(body.get("marcador_pbf", False)),
                "marcador_bpc": bool(body.get("marcador_bpc", False)),
                "municipio": body.get("municipio", "").strip(),
                "uf": body.get("uf", "").strip().upper(),
            },
        )
        status_code = 201 if criado else 200
        return JsonResponse(
            {"status": "criado" if criado else "atualizado", "id": f.id, **_cadunico_dict(f)},
            status=status_code,
        )

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_cadunico_consultar_cpf(request, cpf):
    """Consulta família pelo CPF do responsável no cache local."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CadUnicoFamilia
    cpf_limpo = cpf.replace(".", "").replace("-", "").strip()
    try:
        f = CadUnicoFamilia.objects.get(empresa=empresa, responsavel_cpf=cpf_limpo)
        return JsonResponse(_cadunico_dict(f))
    except CadUnicoFamilia.DoesNotExist:
        return JsonResponse({"erro": "Família não encontrada no CadÚnico local", "cpf": cpf_limpo}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.suas")
def api_cadunico_importar_lote(request):
    """
    Importação em lote de famílias via JSON (ex: exportação do CECAD/SAGI).
    Aceita lista de objetos com os campos da CadUnicoFamilia.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CadUnicoFamilia
    body = json.loads(request.body)
    familias = body if isinstance(body, list) else body.get("familias", [])

    criados = 0
    atualizados = 0
    erros = []

    for idx, item in enumerate(familias):
        try:
            cpf = item.get("responsavel_cpf", "").replace(".", "").replace("-", "").strip()
            _, criado = CadUnicoFamilia.objects.update_or_create(
                empresa=empresa,
                responsavel_cpf=cpf,
                defaults={
                    "numero_seq": item.get("numero_seq", ""),
                    "cod_familiar_fam": item.get("cod_familiar_fam", ""),
                    "responsavel_nome": item.get("responsavel_nome", ""),
                    "responsavel_nis": item.get("responsavel_nis", ""),
                    "qtd_pessoas": int(item.get("qtd_pessoas", 1)),
                    "renda_per_capita": item.get("renda_per_capita") or None,
                    "data_cadastramento": item.get("data_cadastramento") or None,
                    "data_ultima_atualizacao": item.get("data_ultima_atualizacao") or None,
                    "marcador_pbf": bool(item.get("marcador_pbf", False)),
                    "marcador_bpc": bool(item.get("marcador_bpc", False)),
                    "municipio": item.get("municipio", ""),
                    "uf": item.get("uf", ""),
                },
            )
            if criado:
                criados += 1
            else:
                atualizados += 1
        except Exception as e:
            erros.append({"linha": idx + 1, "erro": str(e)})

    return JsonResponse({
        "status": "concluido",
        "criados": criados,
        "atualizados": atualizados,
        "erros": erros,
        "total_processado": criados + atualizados,
    })


# ─── BPC ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_bpc_beneficiarios(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficiarioBPC

    if request.method == "GET":
        qs = BeneficiarioBPC.objects.filter(empresa=empresa)
        tipo = request.GET.get("tipo_bpc")
        ativo = request.GET.get("ativo")
        q = request.GET.get("q", "").strip()
        if tipo:
            qs = qs.filter(tipo_bpc=tipo)
        if ativo is not None:
            qs = qs.filter(ativo=(ativo.lower() != "false"))
        if q:
            qs = qs.filter(beneficiario_nome__icontains=q) | qs.filter(beneficiario_cpf__icontains=q)
        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        itens = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({"total": total, "page": page, "beneficiarios": [_bpc_dict(b) for b in itens]})

    if request.method == "POST":
        from .utils import validar_cpf_cadastro
        body = json.loads(request.body)
        cpf = body.get("beneficiario_cpf", "").replace(".", "").replace("-", "").strip()
        ok, erro = validar_cpf_cadastro(cpf, empresa)
        if not ok:
            return JsonResponse({"erro": erro}, status=400)

        b = BeneficiarioBPC.objects.create(
            empresa=empresa,
            beneficiario_nome=body.get("beneficiario_nome", "").strip(),
            beneficiario_cpf=cpf,
            beneficiario_nis=body.get("beneficiario_nis", "").strip(),
            tipo_bpc=body.get("tipo_bpc", "pessoa_deficiencia"),
            data_inicio=body.get("data_inicio") or None,
            data_fim=body.get("data_fim") or None,
            valor_beneficio=body.get("valor_beneficio") or None,
            ativo=bool(body.get("ativo", True)),
            observacoes=body.get("observacoes", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": b.id, **_bpc_dict(b)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_bpc_beneficiario_detalhe(request, bpc_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficiarioBPC
    try:
        b = BeneficiarioBPC.objects.get(id=bpc_id, empresa=empresa)
    except BeneficiarioBPC.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário BPC não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_bpc_dict(b))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        for c in ["beneficiario_nome", "beneficiario_nis", "tipo_bpc", "observacoes"]:
            if c in body:
                setattr(b, c, body[c].strip() if isinstance(body[c], str) else body[c])
        for c in ["data_inicio", "data_fim"]:
            if c in body:
                setattr(b, c, body[c] or None)
        if "valor_beneficio" in body:
            b.valor_beneficio = body["valor_beneficio"] or None
        if "ativo" in body:
            b.ativo = bool(body["ativo"])
        b.save()
        return JsonResponse({"status": "atualizado", **_bpc_dict(b)})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── SICON (Condicionalidades Bolsa Família) ─────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_sicon_condicionalidades(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CondicionalidadeSICON

    if request.method == "GET":
        qs = CondicionalidadeSICON.objects.filter(empresa=empresa)
        status = request.GET.get("status")
        area = request.GET.get("area")
        periodo = request.GET.get("periodo_referencia")
        q = request.GET.get("q", "").strip()
        if status:
            qs = qs.filter(status=status)
        if area:
            qs = qs.filter(area=area)
        if periodo:
            qs = qs.filter(periodo_referencia=periodo)
        if q:
            qs = qs.filter(titular_nome__icontains=q) | qs.filter(titular_nis__icontains=q)
        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        itens = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({"total": total, "page": page, "condicionalidades": [_sicon_dict(s) for s in itens]})

    if request.method == "POST":
        body = json.loads(request.body)
        s = CondicionalidadeSICON.objects.create(
            empresa=empresa,
            titular_nome=body.get("titular_nome", "").strip(),
            titular_cpf=body.get("titular_cpf", "").replace(".", "").replace("-", "").strip(),
            titular_nis=body.get("titular_nis", "").strip(),
            area=body.get("area", "social"),
            periodo_referencia=body.get("periodo_referencia", "").strip(),
            status=body.get("status", "sem_informacao"),
            motivo_descumprimento=body.get("motivo_descumprimento", "").strip(),
            acompanhamento_tecnico=body.get("acompanhamento_tecnico", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": s.id, **_sicon_dict(s)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── BENEFÍCIOS EVENTUAIS ────────────────────────────────────────────────────

@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_beneficios_eventuais(request):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficioEventual

    if request.method == "GET":
        qs = BeneficioEventual.objects.filter(empresa=empresa).select_related("unidade_cras")
        tipo = request.GET.get("tipo")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        q = request.GET.get("q", "").strip()
        if tipo:
            qs = qs.filter(tipo=tipo)
        if data_ini:
            qs = qs.filter(data_concessao__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_concessao__lte=data_fim)
        if q:
            qs = qs.filter(beneficiario_nome__icontains=q) | qs.filter(beneficiario_cpf__icontains=q)
        page = max(1, int(request.GET.get("page", 1)))
        per_page = 50
        total = qs.count()
        itens = list(qs[(page - 1) * per_page: page * per_page])
        return JsonResponse({"total": total, "page": page, "beneficios": [_beneficio_dict(b) for b in itens]})

    if request.method == "POST":
        body = json.loads(request.body)
        b = BeneficioEventual.objects.create(
            empresa=empresa,
            beneficiario_nome=body.get("beneficiario_nome", "").strip(),
            beneficiario_cpf=body.get("beneficiario_cpf", "").replace(".", "").replace("-", "").strip(),
            beneficiario_nis=body.get("beneficiario_nis", "").strip(),
            tipo=body.get("tipo", "cesta_basica"),
            descricao=body.get("descricao", "").strip(),
            quantidade=body.get("quantidade", 1),
            valor=body.get("valor") or None,
            data_concessao=body.get("data_concessao", str(date.today())),
            unidade_cras_id=body.get("unidade_cras_id") or None,
            tecnico_responsavel=body.get("tecnico_responsavel", "").strip(),
            observacoes=body.get("observacoes", "").strip(),
        )
        return JsonResponse({"status": "criado", "id": b.id, **_beneficio_dict(b)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_permissao_modulo("governo.suas")
def api_beneficio_eventual_detalhe(request, beneficio_id):
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import BeneficioEventual
    try:
        b = BeneficioEventual.objects.select_related("unidade_cras").get(
            id=beneficio_id, empresa=empresa
        )
    except BeneficioEventual.DoesNotExist:
        return JsonResponse({"erro": "Benefício eventual não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_beneficio_dict(b))

    if request.method in ("PUT", "PATCH"):
        body = json.loads(request.body)
        for c in ["beneficiario_nome", "beneficiario_nis", "tipo", "descricao",
                  "tecnico_responsavel", "observacoes"]:
            if c in body:
                setattr(b, c, body[c].strip() if isinstance(body[c], str) else body[c])
        if "data_concessao" in body:
            b.data_concessao = body["data_concessao"]
        if "quantidade" in body:
            b.quantidade = body["quantidade"]
        if "valor" in body:
            b.valor = body["valor"] or None
        if "unidade_cras_id" in body:
            b.unidade_cras_id = body["unidade_cras_id"] or None
        b.save()
        return JsonResponse({"status": "atualizado", **_beneficio_dict(b)})

    if request.method == "DELETE":
        b.delete()
        return JsonResponse({"status": "removido", "id": beneficio_id})

    return JsonResponse({"erro": "Método não permitido"}, status=405)
