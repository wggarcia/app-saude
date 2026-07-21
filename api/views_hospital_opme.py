"""
OPME — Órteses, Próteses e Materiais Especiais
Gestão de catálogo, autorizações prévias e rastreabilidade de implantáveis.
ANVISA RDC 27/2008 | CFM Resolução 2.307/2022
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .utils import validar_cpf_cadastro
from .access_control import (
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.opme", "OPME")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_opme_page(request):
    return render(request, "hospital_opme.html")


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_opme_models():
    from .models import CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, ImplantavelRegistro
    return CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, ImplantavelRegistro


# ── catálogo ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
def api_opme_catalogo(request):
    """GET/POST /api/hospital/opme/catalogo/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()

    if request.method == "GET":
        qs = CatalogoOPME.objects.filter(empresa=empresa)
        tipo = request.GET.get("tipo")
        q = request.GET.get("q")
        ativo = request.GET.get("ativo", "true")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if q:
            qs = qs.filter(Q(descricao__icontains=q) | Q(codigo_anvisa__icontains=q)
                           | Q(codigo_sigtap__icontains=q))
        if ativo == "true":
            qs = qs.filter(ativo=True)
        return JsonResponse({
            "total": qs.count(),
            "itens": [
                {
                    "id": o.id,
                    "descricao": o.descricao,
                    "tipo": o.tipo,
                    "tipo_display": o.get_tipo_display(),
                    "codigo_anvisa": o.codigo_anvisa,
                    "codigo_sigtap": o.codigo_sigtap,
                    "fabricante": o.fabricante,
                    "referencia": o.referencia,
                    "preco_maximo": float(o.preco_maximo) if o.preco_maximo else None,
                    "ativo": o.ativo,
                }
                for o in qs.order_by("tipo", "descricao")
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        item = CatalogoOPME.objects.create(
            empresa=empresa,
            descricao=data["descricao"],
            tipo=data.get("tipo", "material"),
            codigo_anvisa=data.get("codigo_anvisa", ""),
            codigo_sigtap=data.get("codigo_sigtap", ""),
            fabricante=data.get("fabricante", ""),
            referencia=data.get("referencia", ""),
            preco_maximo=data.get("preco_maximo"),
            ativo=data.get("ativo", True),
        )
    return JsonResponse({"id": item.id, "descricao": item.descricao}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_feature("hospital.opme")
def api_opme_catalogo_detalhe(request, item_id):
    """GET/PUT/DELETE /api/hospital/opme/catalogo/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()
    try:
        item = CatalogoOPME.objects.get(id=item_id, empresa=empresa)
    except CatalogoOPME.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": item.id,
            "descricao": item.descricao,
            "tipo": item.tipo,
            "tipo_display": item.get_tipo_display(),
            "codigo_anvisa": item.codigo_anvisa,
            "codigo_sigtap": item.codigo_sigtap,
            "fabricante": item.fabricante,
            "referencia": item.referencia,
            "preco_maximo": float(item.preco_maximo) if item.preco_maximo else None,
            "ativo": item.ativo,
        })

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        campos = ["descricao", "tipo", "codigo_anvisa", "codigo_sigtap",
                  "fabricante", "referencia", "preco_maximo", "ativo"]
        for c in campos:
            if c in data:
                setattr(item, c, data[c])
        item.save()
        return JsonResponse({"ok": True})

    # DELETE
    item.ativo = False
    item.save()
    return JsonResponse({"ok": True})


# ── autorizações ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
def api_opme_autorizacoes(request):
    """GET/POST /api/hospital/opme/autorizacoes/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, _ = _get_opme_models()

    if request.method == "GET":
        qs = AutorizacaoOPME.objects.filter(empresa=empresa).prefetch_related("itens__opme")
        status_f = request.GET.get("status")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(numero_protocolo__icontains=q)
                           | Q(cpf_paciente=q))
        return JsonResponse({
            "total": qs.count(),
            "autorizacoes": [
                {
                    "id": a.id,
                    "numero_protocolo": a.numero_protocolo,
                    "paciente_nome": a.paciente_nome,
                    "cpf_paciente": a.cpf_paciente,
                    "medico_solicitante": a.medico_solicitante,
                    "crm_medico": a.crm_medico,
                    "cid10": a.cid10,
                    "status": a.status,
                    "status_display": a.get_status_display(),
                    "solicitado_em": a.solicitado_em.isoformat(),
                    "respondido_em": a.respondido_em.isoformat() if a.respondido_em else None,
                    "validade_ate": a.validade_ate.isoformat() if a.validade_ate else None,
                    "itens": [
                        {
                            "id": it.id,
                            "opme_descricao": it.opme.descricao,
                            "opme_tipo": it.opme.get_tipo_display(),
                            "quantidade": it.quantidade,
                            "quantidade_aprovada": it.quantidade_aprovada,
                            "status": it.status,
                        }
                        for it in a.itens.all()
                    ],
                }
                for a in qs.order_by("-solicitado_em")
            ],
        })

    data = json.loads(request.body)
    itens_data = data.get("itens", [])
    if not itens_data:
        return JsonResponse({"erro": "Pelo menos 1 item OPME é obrigatório"}, status=400)

    # Gera protocolo sequencial
    total = AutorizacaoOPME.objects.filter(empresa=empresa).count() + 1
    protocolo = f"OPME-{date.today().year}-{total:05d}"

    # Prazo padrão: 10 dias corridos para resposta
    validade_padrao = date.today() + timedelta(days=90)

    with transaction.atomic():
        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        aut = AutorizacaoOPME.objects.create(
            empresa=empresa,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            medico_solicitante=data["medico_solicitante"],
            crm_medico=data.get("crm_medico", ""),
            cid10=data.get("cid10", ""),
            justificativa=data.get("justificativa", ""),
            numero_protocolo=protocolo,
            validade_ate=data.get("validade_ate") or validade_padrao.isoformat(),
        )
        for it in itens_data:
            try:
                opme_obj = CatalogoOPME.objects.get(id=it["opme_id"], empresa=empresa)
            except CatalogoOPME.DoesNotExist:
                continue
            ItemAutorizacaoOPME.objects.create(
                autorizacao=aut,
                opme=opme_obj,
                quantidade=it.get("quantidade", 1),
            )
    return JsonResponse({"id": aut.id, "numero_protocolo": protocolo}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
def api_opme_autorizacao_acao(request, aut_id):
    """POST /api/hospital/opme/autorizacoes/<id>/acao/ — aprovar/negar/cancelar."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, AutorizacaoOPME, ItemAutorizacaoOPME, _ = _get_opme_models()
    try:
        aut = AutorizacaoOPME.objects.get(id=aut_id, empresa=empresa)
    except AutorizacaoOPME.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"status": aut.status, "observacao": aut.observacao_auditoria})

    data = json.loads(request.body)
    nova_acao = data.get("acao")
    mapa_status = {
        "aprovar": "aprovada",
        "negar": "negada",
        "cancelar": "cancelada",
        "parcial": "parcial",
    }
    if nova_acao not in mapa_status:
        return JsonResponse({"erro": f"Ação inválida: {nova_acao}"}, status=400)

    with transaction.atomic():
        aut.status = mapa_status[nova_acao]
        aut.observacao_auditoria = data.get("observacao", "")
        aut.respondido_em = timezone.now()
        aut.save()

        # Atualiza itens se parcial
        if nova_acao == "parcial" and "itens" in data:
            for item_data in data["itens"]:
                try:
                    item = aut.itens.get(id=item_data["id"])
                    item.quantidade_aprovada = item_data.get("quantidade_aprovada", 0)
                    item.status = "aprovado" if item.quantidade_aprovada > 0 else "negado"
                    item.motivo_negativa = item_data.get("motivo_negativa", "")
                    item.save()
                except Exception:
                    pass
        elif nova_acao == "aprovar":
            aut.itens.all().update(status="aprovado")
            for it in aut.itens.all():
                it.quantidade_aprovada = it.quantidade
                it.save()
        elif nova_acao == "negar":
            aut.itens.all().update(status="negado")

    return JsonResponse({"ok": True, "novo_status": aut.status})


# ── implantáveis ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
def api_opme_implantaveis(request):
    """GET/POST /api/hospital/opme/implantaveis/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, AutorizacaoOPME, _, ImplantavelRegistro = _get_opme_models()

    if request.method == "GET":
        qs = ImplantavelRegistro.objects.filter(empresa=empresa).select_related("opme")
        q = request.GET.get("q")
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q)
                           | Q(numero_serie__icontains=q))
        return JsonResponse({
            "total": qs.count(),
            "implantaveis": [
                {
                    "id": i.id,
                    "opme_descricao": i.opme.descricao,
                    "opme_tipo": i.opme.get_tipo_display(),
                    "codigo_anvisa": i.opme.codigo_anvisa,
                    "paciente_nome": i.paciente_nome,
                    "cpf_paciente": i.cpf_paciente,
                    "numero_serie": i.numero_serie,
                    "lote_fabricante": i.lote_fabricante,
                    "data_implante": i.data_implante.isoformat(),
                    "medico_implantador": i.medico_implantador,
                    "hospital": i.hospital,
                }
                for i in qs.order_by("-data_implante")
            ],
        })

    data = json.loads(request.body)
    try:
        opme = CatalogoOPME.objects.get(id=data["opme_id"], empresa=empresa)
    except CatalogoOPME.DoesNotExist:
        return JsonResponse({"erro": "OPME não encontrado no catálogo"}, status=404)

    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    impl = ImplantavelRegistro.objects.create(
        empresa=empresa,
        opme=opme,
        autorizacao_id=data.get("autorizacao_id"),
        paciente_nome=data["paciente_nome"],
        cpf_paciente=data.get("cpf_paciente", ""),
        numero_serie=data.get("numero_serie", ""),
        lote_fabricante=data.get("lote_fabricante", ""),
        data_implante=data["data_implante"],
        medico_implantador=data.get("medico_implantador", ""),
        crm_medico=data.get("crm_medico", ""),
        hospital=data.get("hospital", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"id": impl.id}, status=201)


# ── KPIs ───────────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.opme")
def api_opme_kpis(request):
    """GET /api/hospital/opme/kpis/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, AutorizacaoOPME, _, ImplantavelRegistro = _get_opme_models()

    total_catalogo = CatalogoOPME.objects.filter(empresa=empresa, ativo=True).count()
    aut_qs = AutorizacaoOPME.objects.filter(empresa=empresa)
    por_status = dict(aut_qs.values_list("status").annotate(n=Count("id")).order_by())
    impl_30d = ImplantavelRegistro.objects.filter(
        empresa=empresa,
        data_implante__gte=date.today() - timedelta(days=30)
    ).count()
    taxa_aprovacao = 0
    total_resp = (por_status.get("aprovada", 0) + por_status.get("negada", 0)
                  + por_status.get("parcial", 0))
    if total_resp > 0:
        taxa_aprovacao = round(
            (por_status.get("aprovada", 0) + por_status.get("parcial", 0)) / total_resp * 100, 1
        )

    return JsonResponse({
        "catalogo_itens_ativos": total_catalogo,
        "autorizacoes_por_status": por_status,
        "autorizacoes_pendentes": por_status.get("solicitada", 0),
        "taxa_aprovacao_pct": taxa_aprovacao,
        "implantaveis_ultimos_30d": impl_30d,
    })
