"""
Gestão SUAS — Dashboard consolidado, Censo SUAS e IA para inconsistências cadastrais.

Indicadores Censo SUAS (MDS):
  - Famílias referenciadas no CRAS
  - Atendimentos PAIF realizados no mês/ano
  - Visitas domiciliares realizadas
  - Famílias com condicionalidades descumpridas (SICON)
  - Casos CREAS em acompanhamento por tipo de violação

IA de inconsistências cadastrais:
  - Detecta famílias com NIS duplicado
  - Detecta famílias com renda acima do limite CadÚnico (R$ 218 per capita para PBF 2024)
  - Detecta integrantes declarados acima de limites plausíveis
  - Detecta beneficiários BPC sem marcador BPC no CadÚnico
"""
import logging
from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import api_requer_permissao_modulo, get_setor, principal_pode_operacao_setorial
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)

# Limite de renda per capita para CadÚnico / PBF 2024 (em R$)
_LIMITE_RENDA_CADUNICO = 218.0


def _gov(request):
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ─── DASHBOARD SUAS ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_suas_dashboard(request):
    """Dashboard consolidado CRAS + CREAS + CadÚnico + BPC."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo — Assistência Social"}, status=403)

    from .models import (
        UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial,
        UnidadeCREAS, AtendimentoCREAS,
        CadUnicoFamilia, BeneficiarioBPC, CondicionalidadeSICON, BeneficioEventual,
    )

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_ano = hoje.replace(month=1, day=1)

    # CRAS
    cras_unidades = UnidadeCRAS.objects.filter(empresa=empresa, ativo=True).count()
    familias_total = FamiliaCRAS.objects.filter(empresa=empresa).count()
    familias_acomp = FamiliaCRAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    atend_cras_mes = AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()
    atend_cras_ano = AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_ano).count()
    visitas_mes = VisitaDomiciliarSocial.objects.filter(empresa=empresa, data_visita__gte=inicio_mes).count()
    vulnerabilidades_mes = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__gte=inicio_mes, vulnerabilidade_identificada=True
    ).count()

    # CREAS
    creas_unidades = UnidadeCREAS.objects.filter(empresa=empresa, ativo=True).count()
    casos_creas_ativos = AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    novos_creas_mes = AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()

    por_violacao = list(
        AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento")
        .values("tipo_violacao")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # CadÚnico / BPC / SICON
    cadunico_total = CadUnicoFamilia.objects.filter(empresa=empresa).count()
    cadunico_pbf = CadUnicoFamilia.objects.filter(empresa=empresa, marcador_pbf=True).count()
    bpc_ativos = BeneficiarioBPC.objects.filter(empresa=empresa, ativo=True).count()
    sicon_descumpridas = CondicionalidadeSICON.objects.filter(empresa=empresa, status="descumprida").count()
    sicon_sem_info = CondicionalidadeSICON.objects.filter(empresa=empresa, status="sem_informacao").count()

    # Benefícios eventuais
    beneficios_mes = BeneficioEventual.objects.filter(empresa=empresa, data_concessao__gte=inicio_mes).count()

    return JsonResponse({
        "referencia_mes": str(inicio_mes),
        "cras": {
            "unidades": cras_unidades,
            "familias_total": familias_total,
            "familias_em_acompanhamento": familias_acomp,
            "atendimentos_mes": atend_cras_mes,
            "atendimentos_ano": atend_cras_ano,
            "visitas_domiciliares_mes": visitas_mes,
            "vulnerabilidades_identificadas_mes": vulnerabilidades_mes,
        },
        "creas": {
            "unidades": creas_unidades,
            "casos_ativos": casos_creas_ativos,
            "novos_mes": novos_creas_mes,
            "por_tipo_violacao": {p["tipo_violacao"]: p["total"] for p in por_violacao},
        },
        "cadunico": {
            "familias_importadas": cadunico_total,
            "titulares_pbf": cadunico_pbf,
        },
        "bpc": {
            "beneficiarios_ativos": bpc_ativos,
        },
        "sicon": {
            "descumpridas": sicon_descumpridas,
            "sem_informacao": sicon_sem_info,
        },
        "beneficios_eventuais_mes": beneficios_mes,
    })


# ─── CENSO SUAS ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_suas_censo(request):
    """
    Indicadores do Censo SUAS (MDS) para o período solicitado.
    Parâmetros: ?ano=2025&mes=6 (omitir mes = ano inteiro)
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import (
        FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial,
        AtendimentoCREAS, BeneficiarioBPC, CondicionalidadeSICON,
    )

    hoje = date.today()
    ano = int(request.GET.get("ano", hoje.year))
    mes = request.GET.get("mes")

    if mes:
        mes = int(mes)
        data_ini = date(ano, mes, 1)
        if mes == 12:
            data_fim = date(ano + 1, 1, 1) - timedelta(days=1)
        else:
            data_fim = date(ano, mes + 1, 1) - timedelta(days=1)
    else:
        data_ini = date(ano, 1, 1)
        data_fim = date(ano, 12, 31)

    # PAIF / CRAS
    familias_referenciadas = FamiliaCRAS.objects.filter(empresa=empresa).count()
    paif_individual = AtendimentoCRAS.objects.filter(
        empresa=empresa, data_atendimento__range=(data_ini, data_fim), tipo="individual"
    ).count()
    paif_familiar = AtendimentoCRAS.objects.filter(
        empresa=empresa, data_atendimento__range=(data_ini, data_fim), tipo="familiar"
    ).count()
    paif_grupo = AtendimentoCRAS.objects.filter(
        empresa=empresa, data_atendimento__range=(data_ini, data_fim), tipo="grupo"
    ).count()
    visitas_periodo = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__range=(data_ini, data_fim)
    ).count()

    # PAEFI / CREAS
    paefi_novos = AtendimentoCREAS.objects.filter(
        empresa=empresa, data_atendimento__range=(data_ini, data_fim)
    ).count()
    paefi_ativos = AtendimentoCREAS.objects.filter(
        empresa=empresa, situacao="em_acompanhamento"
    ).count()

    # BPC
    bpc_pcd = BeneficiarioBPC.objects.filter(
        empresa=empresa, tipo_bpc="pessoa_deficiencia", ativo=True
    ).count()
    bpc_idoso = BeneficiarioBPC.objects.filter(
        empresa=empresa, tipo_bpc="idoso_65", ativo=True
    ).count()

    # SICON descumprimento
    sicon_saude = CondicionalidadeSICON.objects.filter(
        empresa=empresa, area="saude", status="descumprida"
    ).count()
    sicon_educacao = CondicionalidadeSICON.objects.filter(
        empresa=empresa, area="educacao", status="descumprida"
    ).count()
    sicon_social = CondicionalidadeSICON.objects.filter(
        empresa=empresa, area="social", status="descumprida"
    ).count()

    return JsonResponse({
        "periodo": {"ano": ano, "mes": mes, "data_inicio": str(data_ini), "data_fim": str(data_fim)},
        "cras_paif": {
            "familias_referenciadas_total": familias_referenciadas,
            "atendimentos_individuais": paif_individual,
            "atendimentos_familiares": paif_familiar,
            "atendimentos_grupo": paif_grupo,
            "total_atendimentos": paif_individual + paif_familiar + paif_grupo,
            "visitas_domiciliares": visitas_periodo,
        },
        "creas_paefi": {
            "novos_acolhimentos": paefi_novos,
            "em_acompanhamento": paefi_ativos,
        },
        "bpc": {
            "pessoa_deficiencia": bpc_pcd,
            "idoso_65": bpc_idoso,
            "total": bpc_pcd + bpc_idoso,
        },
        "sicon_descumprimento": {
            "saude": sicon_saude,
            "educacao": sicon_educacao,
            "assistencia_social": sicon_social,
            "total": sicon_saude + sicon_educacao + sicon_social,
        },
    })


# ─── IA: INCONSISTÊNCIAS CADASTRAIS ──────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_suas_ia_inconsistencias(request):
    """
    IA heurística para detecção de inconsistências cadastrais no CadÚnico local.
    Analisa: NIS duplicado, renda acima do limite, integrantes implausíveis,
    BPC sem marcador, PBF com renda acima do limite.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import CadUnicoFamilia, BeneficiarioBPC, FamiliaCRAS
    from django.db.models import Count

    alertas = []

    # 1. NIS duplicado no CadÚnico local
    nis_duplicados = (
        CadUnicoFamilia.objects.filter(empresa=empresa)
        .exclude(responsavel_nis="")
        .values("responsavel_nis")
        .annotate(qtd=Count("id"))
        .filter(qtd__gt=1)
    )
    for entry in nis_duplicados:
        alertas.append({
            "tipo": "nis_duplicado",
            "severidade": "alta",
            "descricao": f"NIS {entry['responsavel_nis']} aparece em {entry['qtd']} registros distintos.",
            "nis": entry["responsavel_nis"],
            "ocorrencias": entry["qtd"],
        })

    # 2. Família com PBF marcado e renda acima do limite (R$ 218 per capita)
    pbf_renda_alta = CadUnicoFamilia.objects.filter(
        empresa=empresa,
        marcador_pbf=True,
        renda_per_capita__gt=_LIMITE_RENDA_CADUNICO,
    )
    for f in pbf_renda_alta[:50]:
        alertas.append({
            "tipo": "pbf_renda_acima_limite",
            "severidade": "alta",
            "descricao": (
                f"Família '{f.responsavel_nome}' (NIS {f.responsavel_nis}) marcada como PBF "
                f"mas renda per capita R$ {f.renda_per_capita:.2f} acima do limite de "
                f"R$ {_LIMITE_RENDA_CADUNICO:.2f}."
            ),
            "familia_id": f.id,
            "responsavel_nome": f.responsavel_nome,
            "responsavel_nis": f.responsavel_nis,
            "renda_per_capita": float(f.renda_per_capita),
        })

    # 3. Número de integrantes implausível (> 15)
    integrantes_alto = CadUnicoFamilia.objects.filter(empresa=empresa, qtd_pessoas__gt=15)
    for f in integrantes_alto[:20]:
        alertas.append({
            "tipo": "integrantes_implausivel",
            "severidade": "media",
            "descricao": f"Família '{f.responsavel_nome}' declarada com {f.qtd_pessoas} integrantes.",
            "familia_id": f.id,
            "responsavel_nome": f.responsavel_nome,
            "qtd_pessoas": f.qtd_pessoas,
        })

    # 4. Beneficiário BPC sem marcador BPC no CadÚnico
    bpc_sem_marcador = []
    bpc_ativos = BeneficiarioBPC.objects.filter(empresa=empresa, ativo=True).exclude(beneficiario_nis="")
    nis_com_bpc = set(bpc_ativos.values_list("beneficiario_nis", flat=True))
    cadunico_com_marcador = set(
        CadUnicoFamilia.objects.filter(empresa=empresa, marcador_bpc=True)
        .values_list("responsavel_nis", flat=True)
    )
    for nis in nis_com_bpc:
        if nis not in cadunico_com_marcador:
            try:
                b = BeneficiarioBPC.objects.get(empresa=empresa, beneficiario_nis=nis, ativo=True)
                alertas.append({
                    "tipo": "bpc_sem_marcador_cadunico",
                    "severidade": "media",
                    "descricao": (
                        f"Beneficiário BPC '{b.beneficiario_nome}' (NIS {nis}) "
                        f"não possui marcador BPC no CadÚnico local."
                    ),
                    "bpc_id": b.id,
                    "beneficiario_nome": b.beneficiario_nome,
                    "nis": nis,
                })
            except BeneficiarioBPC.DoesNotExist:
                pass

    # 5. Famílias CRAS sem vínculo com CadÚnico
    familias_sem_cadunico = FamiliaCRAS.objects.filter(
        empresa=empresa,
        situacao="em_acompanhamento",
        cadUnico_numero_seq="",
        responsavel_nis="",
    ).count()
    if familias_sem_cadunico > 0:
        alertas.append({
            "tipo": "familias_cras_sem_cadunico",
            "severidade": "baixa",
            "descricao": (
                f"{familias_sem_cadunico} família(s) em acompanhamento no CRAS "
                f"sem número de NIS ou referência ao CadÚnico registrada."
            ),
            "quantidade": familias_sem_cadunico,
        })

    alta = sum(1 for a in alertas if a["severidade"] == "alta")
    media = sum(1 for a in alertas if a["severidade"] == "media")
    baixa = sum(1 for a in alertas if a["severidade"] == "baixa")

    return JsonResponse({
        "total_alertas": len(alertas),
        "resumo": {"alta": alta, "media": media, "baixa": baixa},
        "alertas": alertas,
        "gerado_em": date.today().isoformat(),
    })


# ─── RELATÓRIO SUAS ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.suas")
def api_suas_relatorio_mensal(request):
    """
    Relatório mensal consolidado SUAS para prestação de contas ao MDS.
    Parâmetros: ?ano=2025&mes=6
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import (
        UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial,
        UnidadeCREAS, AtendimentoCREAS,
        BeneficioEventual, CondicionalidadeSICON,
    )

    hoje = date.today()
    ano = int(request.GET.get("ano", hoje.year))
    mes = int(request.GET.get("mes", hoje.month))
    data_ini = date(ano, mes, 1)
    data_fim = date(ano, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(ano, 12, 31)

    # CRAS
    unidades_cras = list(
        UnidadeCRAS.objects.filter(empresa=empresa, ativo=True).values("id", "nome", "municipio")
    )
    familias_mes = FamiliaCRAS.objects.filter(empresa=empresa, data_cadastro__range=(data_ini, data_fim)).count()
    atendimentos_por_tipo = dict(
        AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__range=(data_ini, data_fim))
        .values("tipo")
        .annotate(total=Count("id"))
        .values_list("tipo", "total")
    )
    visitas = VisitaDomiciliarSocial.objects.filter(empresa=empresa, data_visita__range=(data_ini, data_fim)).count()
    vulnerabilidades = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__range=(data_ini, data_fim), vulnerabilidade_identificada=True
    ).count()

    # CREAS
    unidades_creas = list(
        UnidadeCREAS.objects.filter(empresa=empresa, ativo=True).values("id", "nome", "municipio")
    )
    creas_por_tipo = dict(
        AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__range=(data_ini, data_fim))
        .values("tipo_violacao")
        .annotate(total=Count("id"))
        .values_list("tipo_violacao", "total")
    )

    # Benefícios eventuais
    beneficios_por_tipo = dict(
        BeneficioEventual.objects.filter(empresa=empresa, data_concessao__range=(data_ini, data_fim))
        .values("tipo")
        .annotate(total=Count("id"))
        .values_list("tipo", "total")
    )
    valor_total_beneficios = (
        BeneficioEventual.objects.filter(empresa=empresa, data_concessao__range=(data_ini, data_fim))
        .aggregate(total=Sum("valor"))["total"] or 0
    )

    # SICON
    sicon_resumo = dict(
        CondicionalidadeSICON.objects.filter(
            empresa=empresa,
            periodo_referencia=f"{ano}/{mes:02d}",
        )
        .values("status")
        .annotate(total=Count("id"))
        .values_list("status", "total")
    )

    return JsonResponse({
        "municipio": empresa.nome_fantasia if hasattr(empresa, "nome_fantasia") else str(empresa),
        "periodo": {"ano": ano, "mes": mes, "data_inicio": str(data_ini), "data_fim": str(data_fim)},
        "cras": {
            "unidades": unidades_cras,
            "novas_familias_cadastradas": familias_mes,
            "atendimentos_por_tipo": atendimentos_por_tipo,
            "visitas_domiciliares": visitas,
            "vulnerabilidades_identificadas": vulnerabilidades,
        },
        "creas": {
            "unidades": unidades_creas,
            "atendimentos_por_tipo_violacao": creas_por_tipo,
        },
        "beneficios_eventuais": {
            "por_tipo": beneficios_por_tipo,
            "valor_total": float(valor_total_beneficios),
        },
        "sicon": {
            "por_status": sicon_resumo,
        },
    })
