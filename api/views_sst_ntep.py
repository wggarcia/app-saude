"""
NTEP — Nexo Técnico Epidemiológico
Identificação automática de nexo presumido CID-10 × CNAE (Decreto 6.042/2007).
Integra com CAT, afastamentos B91 e ASO para alertas proativos de risco jurídico.
INSS | DATAPREV | Decreto 6.042/2007 | Lei 8.213/91
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)

# ── Tabela NTEP seed — principais pares CID × CNAE (Decreto 6.042/2007 Anexo II)
# Fonte: Portaria MPS/MF 1.339/1999 + atualizações DOU
_NTEP_SEEDS = [
    # (CID, CNAE-subclasse, descricao_cid, descricao_cnae)
    ("M75",  "8121400",  "Lesões do ombro",                       "Limpeza em prédios e domicílios"),
    ("M65",  "4329103",  "Sinovites e tenossinovites",            "Instalação de portas, janelas etc."),
    ("M54",  "4120400",  "Dorsalgia",                             "Construção de edifícios"),
    ("F32",  "6499501",  "Episódios depressivos",                 "Outras atividades de serviços financeiros"),
    ("F41",  "8411600",  "Outros transtornos ansiosos",           "Adm. pública e política econômica"),
    ("Z73",  "6420000",  "Problemas relacionados ao estilo vida", "Holdings de instituições não-financeiras"),
    ("M16",  "4711302",  "Coxartrose",                            "Comércio varejista supermercados"),
    ("M17",  "4711302",  "Gonartrose",                            "Comércio varejista supermercados"),
    ("H90",  "2399101",  "Perda de audição condutiva e neurosens.","Aparelhamento e outros trabalhos em pedras"),
    ("H91",  "2410100",  "Outras perdas de audição",              "Fabricação de gusa e de ligas de ferro"),
    ("J45",  "2330301",  "Asma",                                  "Fabricação de cimento"),
    ("J68",  "2091600",  "Afecções respiratórias por agentes químicos", "Fabricação de adesivos"),
    ("L25",  "2240199",  "Dermatite de contato, NE",              "Fabricação de outros produtos farmoquímicos"),
    ("M50",  "5229099",  "Transtornos dos discos cervicais",      "Outras atividades de apoio ao transporte"),
    ("T14",  "4120400",  "Traumatismo de região NE do corpo",     "Construção de edifícios"),
    ("S61",  "0111301",  "Ferimento do punho e da mão",           "Cultivo de arroz"),
    ("M77",  "4744099",  "Entesopatias",                          "Comércio de material de construção"),
    ("F43",  "8411600",  "Reação ao stress grave",                "Adm. pública e política econômica"),
    ("G54",  "5111100",  "Transtornos de raízes nervosas",        "Transporte aéreo de passageiros"),
    ("R42",  "8011101",  "Tontura e enjoo",                       "Vigilância e segurança privada"),
]


def _get_ntep_models():
    from .models import TabelaNTEP, AlertaNTEP
    return TabelaNTEP, AlertaNTEP


def _seed_ntep():
    """Popula tabela NTEP com os pares canônicos se vazia."""
    TabelaNTEP, _ = _get_ntep_models()
    if TabelaNTEP.objects.count() == 0:
        objs = [
            TabelaNTEP(
                cid10=cid,
                cnae=cnae,
                descricao_cid=dcid,
                descricao_cnae=dcnae,
                grupo_cnae=cnae[:2],
                nexo_presumido=True,
                ativo=True,
            )
            for cid, cnae, dcid, dcnae in _NTEP_SEEDS
        ]
        TabelaNTEP.objects.bulk_create(objs, ignore_conflicts=True)
    return TabelaNTEP.objects.count()


# ── tabela NTEP ───────────────────────────────────────────────────────────────

def api_ntep_tabela(request):
    """GET /api/sst/ntep/tabela/ — consulta tabela NTEP com paginação."""
    if not get_empresa(request):
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    TabelaNTEP, _ = _get_ntep_models()

    # Auto-seed
    _seed_ntep()

    q = request.GET.get("q")
    cid = request.GET.get("cid")
    cnae = request.GET.get("cnae")

    qs = TabelaNTEP.objects.filter(ativo=True)
    if q:
        qs = qs.filter(Q(cid10__icontains=q) | Q(descricao_cid__icontains=q)
                       | Q(cnae__icontains=q) | Q(descricao_cnae__icontains=q))
    if cid:
        qs = qs.filter(cid10__istartswith=cid)
    if cnae:
        qs = qs.filter(Q(cnae__istartswith=cnae) | Q(grupo_cnae=cnae[:2]))

    return JsonResponse({
        "total": qs.count(),
        "pares": [
            {
                "id": t.id,
                "cid10": t.cid10,
                "descricao_cid": t.descricao_cid,
                "cnae": t.cnae,
                "descricao_cnae": t.descricao_cnae,
                "grupo_cnae": t.grupo_cnae,
                "nexo_presumido": t.nexo_presumido,
            }
            for t in qs.order_by("cid10")[:200]
        ],
    })


def api_ntep_verificar(request):
    """GET /api/sst/ntep/verificar/?cid=M75&cnae=8121400 — verifica nexo."""
    if not get_empresa(request):
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    TabelaNTEP, _ = _get_ntep_models()
    _seed_ntep()

    cid = request.GET.get("cid", "").upper().strip()
    cnae = request.GET.get("cnae", "").strip()

    if not cid or not cnae:
        return JsonResponse({"erro": "Parâmetros cid e cnae obrigatórios"}, status=400)

    # Busca exata ou por grupo CNAE
    match = TabelaNTEP.objects.filter(
        ativo=True, nexo_presumido=True
    ).filter(
        Q(cid10=cid, cnae=cnae)
        | Q(cid10=cid, grupo_cnae=cnae[:2])
        | Q(cid10=cid[:3], cnae=cnae)
        | Q(cid10=cid[:3], grupo_cnae=cnae[:2])
    ).first()

    if match:
        return JsonResponse({
            "nexo_presumido": True,
            "cid10": cid,
            "cnae": cnae,
            "par_ntep": {
                "cid_tabela": match.cid10,
                "cnae_tabela": match.cnae,
                "descricao_cid": match.descricao_cid,
                "descricao_cnae": match.descricao_cnae,
            },
            "alerta": (
                "⚠️ NEXO TÉCNICO PRESUMIDO — Este CID está listado na Tabela NTEP para este CNAE. "
                "O INSS pode reconhecer automaticamente como doença do trabalho (B91). "
                "Risco de ação regressiva. Consulte sua assessoria jurídica trabalhista."
            ),
            "base_legal": "Decreto 6.042/2007 | Lei 8.213/91 art. 21-A",
        })
    else:
        return JsonResponse({
            "nexo_presumido": False,
            "cid10": cid,
            "cnae": cnae,
            "mensagem": "Par CID × CNAE não encontrado na Tabela NTEP — nexo não presumido.",
        })


# ── alertas NTEP ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ntep_alertas(request):
    """GET/POST /api/sst/ntep/alertas/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    TabelaNTEP, AlertaNTEP = _get_ntep_models()

    if request.method == "GET":
        qs = AlertaNTEP.objects.filter(empresa=empresa).select_related("ntep")
        status_f = request.GET.get("status")
        origem_f = request.GET.get("origem")
        if status_f:
            qs = qs.filter(status=status_f)
        if origem_f:
            qs = qs.filter(origem=origem_f)

        return JsonResponse({
            "total": qs.count(),
            "novos": qs.filter(status="novo").count(),
            "alertas": [
                {
                    "id": a.id,
                    "funcionario_nome": a.funcionario_nome,
                    "cpf_funcionario": a.cpf_funcionario,
                    "cid10": a.cid10,
                    "cnae_empresa": a.cnae_empresa,
                    "descricao_cid": a.ntep.descricao_cid,
                    "descricao_cnae": a.ntep.descricao_cnae,
                    "origem": a.origem,
                    "origem_display": a.get_origem_display(),
                    "status": a.status,
                    "status_display": a.get_status_display(),
                    "risco_acao_regressiva": a.risco_acao_regressiva,
                    "valor_estimado_risco": float(a.valor_estimado_risco) if a.valor_estimado_risco else None,
                    "criado_em": a.criado_em.isoformat(),
                }
                for a in qs.order_by("-criado_em")[:200]
            ],
        })

    # POST — cria alerta manualmente ou via CAT/afastamento
    data = json.loads(request.body)
    _seed_ntep()

    cid = data.get("cid10", "").upper().strip()
    cnae = data.get("cnae", empresa.cnae if hasattr(empresa, "cnae") else "").strip()

    # Verifica nexo na tabela
    ntep_match = TabelaNTEP.objects.filter(
        ativo=True, nexo_presumido=True
    ).filter(
        Q(cid10=cid, cnae=cnae)
        | Q(cid10=cid[:3], cnae=cnae)
        | Q(cid10=cid, grupo_cnae=cnae[:2])
        | Q(cid10=cid[:3], grupo_cnae=cnae[:2])
    ).first()

    if not ntep_match:
        return JsonResponse({
            "alerta_criado": False,
            "mensagem": "Par CID × CNAE não encontra nexo na Tabela NTEP.",
        })

    alerta = AlertaNTEP.objects.create(
        empresa=empresa,
        ntep=ntep_match,
        origem=data.get("origem", "cat"),
        origem_id=data.get("origem_id", 0),
        funcionario_nome=data["funcionario_nome"],
        cpf_funcionario=data.get("cpf_funcionario", ""),
        cid10=cid,
        cnae_empresa=cnae,
        status="novo",
        risco_acao_regressiva=True,
        valor_estimado_risco=data.get("valor_estimado_risco"),
    )
    return JsonResponse({
        "alerta_criado": True,
        "id": alerta.id,
        "aviso": "Nexo presumido identificado — risco de B91 e ação regressiva INSS.",
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_ntep_alerta_detalhe(request, alerta_id):
    """GET/PUT /api/sst/ntep/alertas/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, AlertaNTEP = _get_ntep_models()
    try:
        alerta = AlertaNTEP.objects.get(id=alerta_id, empresa=empresa)
    except AlertaNTEP.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": alerta.id,
            "funcionario_nome": alerta.funcionario_nome,
            "cpf_funcionario": alerta.cpf_funcionario,
            "cid10": alerta.cid10,
            "cnae_empresa": alerta.cnae_empresa,
            "ntep_descricao_cid": alerta.ntep.descricao_cid,
            "ntep_descricao_cnae": alerta.ntep.descricao_cnae,
            "origem": alerta.origem,
            "origem_display": alerta.get_origem_display(),
            "origem_id": alerta.origem_id,
            "status": alerta.status,
            "status_display": alerta.get_status_display(),
            "risco_acao_regressiva": alerta.risco_acao_regressiva,
            "valor_estimado_risco": float(alerta.valor_estimado_risco) if alerta.valor_estimado_risco else None,
            "justificativa_contestacao": alerta.justificativa_contestacao,
            "pericias_realizadas": alerta.pericias_realizadas,
            "base_legal": "Decreto 6.042/2007 | Lei 8.213/91 art. 21-A",
            "criado_em": alerta.criado_em.isoformat(),
        })

    data = json.loads(request.body)
    campos = ["status", "justificativa_contestacao", "pericias_realizadas",
              "valor_estimado_risco", "risco_acao_regressiva"]
    for c in campos:
        if c in data:
            setattr(alerta, c, data[c])
    alerta.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def api_ntep_scan_cats(request):
    """POST /api/sst/ntep/scan-cats/ — varre CATs recentes e gera alertas automáticos."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import CATRegistro
    TabelaNTEP, AlertaNTEP = _get_ntep_models()
    _seed_ntep()

    # Busca CATs dos últimos 90 dias sem alerta NTEP
    dias = int(request.GET.get("dias", 90))
    desde = date.today() - timedelta(days=dias)
    cats = CATRegistro.objects.filter(
        empresa=empresa,
        data_acidente__gte=desde,
    ).exclude(
        cid10=""
    )

    cnae_empresa = getattr(empresa, "cnae", "") or ""
    novos_alertas = 0
    verificados = 0

    for cat in cats:
        verificados += 1
        cid = cat.cid10.upper().strip()

        # Já tem alerta?
        if AlertaNTEP.objects.filter(empresa=empresa, origem="cat", origem_id=cat.id).exists():
            continue

        ntep = TabelaNTEP.objects.filter(
            ativo=True, nexo_presumido=True
        ).filter(
            Q(cid10=cid, cnae=cnae_empresa)
            | Q(cid10=cid[:3], cnae=cnae_empresa)
            | Q(cid10=cid, grupo_cnae=cnae_empresa[:2])
            | Q(cid10=cid[:3], grupo_cnae=cnae_empresa[:2])
        ).first()

        if ntep:
            AlertaNTEP.objects.create(
                empresa=empresa,
                ntep=ntep,
                origem="cat",
                origem_id=cat.id,
                funcionario_nome=cat.funcionario.nome if hasattr(cat, "funcionario") else str(cat.funcionario_id),
                cpf_funcionario="",
                cid10=cid,
                cnae_empresa=cnae_empresa,
                status="novo",
                risco_acao_regressiva=True,
            )
            novos_alertas += 1

    return JsonResponse({
        "cats_verificados": verificados,
        "alertas_gerados": novos_alertas,
        "periodo_dias": dias,
        "cnae_empresa": cnae_empresa,
    })


# ── KPIs ───────────────────────────────────────────────────────────────────────

def api_ntep_kpis(request):
    """GET /api/sst/ntep/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, AlertaNTEP = _get_ntep_models()
    _seed_ntep()

    qs = AlertaNTEP.objects.filter(empresa=empresa)
    por_status = dict(qs.values_list("status").annotate(n=Count("id")).order_by())
    por_origem = dict(qs.values_list("origem").annotate(n=Count("id")).order_by())
    top_cids = list(
        qs.values_list("cid10").annotate(n=Count("id")).order_by("-n")[:10]
    )
    total_risco = qs.filter(risco_acao_regressiva=True).aggregate(
        soma=Sum("valor_estimado_risco")
    )["soma"] or 0

    return JsonResponse({
        "alertas_por_status": por_status,
        "alertas_por_origem": por_origem,
        "top_cids_ntep": [{"cid": c, "alertas": n} for c, n in top_cids],
        "alertas_novos": por_status.get("novo", 0),
        "risco_financeiro_total": float(total_risco),
        "tabela_ntep_registros": _get_ntep_models()[0].objects.filter(ativo=True).count(),
    })
