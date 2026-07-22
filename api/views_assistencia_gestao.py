"""
Gestão SUAS — Dashboard consolidado, Censo SUAS, IA de inconsistências e relatório MDS.
Segmento Assistência Social (setor "assistencia_social").

IA heurística de inconsistências cadastrais (com persistência):
  - NIS duplicado no CadÚnico local
  - PBF com renda per capita acima do limite (R$ 218/pessoa — valor PBF 2024)
  - Número de integrantes implausível (> 15)
  - Beneficiário BPC sem marcador BPC no CadÚnico local
  - Família CRAS em acompanhamento sem vínculo CadÚnico
  - CREAS em acompanhamento sem tipo de violação definido

Inconsistências detectadas são armazenadas em InconsistenciaCadastral e podem ser
resolvidas ou descartadas individualmente pelo técnico responsável.
"""
import json
import logging
from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_permissao_modulo, contexto_navegacao_setorial,
    get_setor, principal_pode_operacao_setorial,
)
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)

_LIMITE_RENDA_CADUNICO = 218.0  # R$ per capita — PBF 2024


def _assoc(request):
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "assistencia_social":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ─── PÁGINAS HTML ────────────────────────────────────────────────────────────

def assistencia_social_dashboard_page(request):
    return render(request, "assistencia_social_dashboard.html",
                  contexto_navegacao_setorial(request, "assistencia_social"))


def assistencia_social_gestao_page(request):
    return render(request, "assistencia_social_gestao.html",
                  contexto_navegacao_setorial(request, "assistencia_social"))


# ─── DASHBOARD SUAS ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_suas_dashboard(request):
    """Dashboard consolidado CRAS/PAIF + CREAS/PAEFI + CadÚnico + BPC + IA."""
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Assistência Social — Gestão SUAS"}, status=403)

    from .models import (
        UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial, ProntuarioSocialPAIF,
        UnidadeCREAS, AtendimentoCREAS,
        CadUnicoFamilia, BeneficiarioBPC, CondicionalidadeSICON, BeneficioEventual,
        InconsistenciaCadastral,
    )

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_ano = hoje.replace(month=1, day=1)

    # CRAS / PAIF
    cras_unidades = UnidadeCRAS.objects.filter(empresa=empresa, ativo=True).count()
    familias_total = FamiliaCRAS.objects.filter(empresa=empresa).count()
    familias_acomp = FamiliaCRAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    atend_cras_mes = AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()
    atend_cras_ano = AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_ano).count()
    visitas_mes = VisitaDomiciliarSocial.objects.filter(empresa=empresa, data_visita__gte=inicio_mes).count()
    vulnerabilidades_mes = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__gte=inicio_mes, vulnerabilidade_identificada=True
    ).count()
    prontuarios_abertos = ProntuarioSocialPAIF.objects.filter(empresa=empresa, ativo=True).count()

    # CREAS / PAEFI
    creas_unidades = UnidadeCREAS.objects.filter(empresa=empresa, ativo=True).count()
    casos_creas_ativos = AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    novos_creas_mes = AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__gte=inicio_mes).count()
    por_violacao = list(
        AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento")
        .values("tipo_violacao").annotate(total=Count("id")).order_by("-total")[:5]
    )

    # CadÚnico / BPC / SICON
    cadunico_total = CadUnicoFamilia.objects.filter(empresa=empresa).count()
    cadunico_pbf = CadUnicoFamilia.objects.filter(empresa=empresa, marcador_pbf=True).count()
    bpc_ativos = BeneficiarioBPC.objects.filter(empresa=empresa, ativo=True).count()
    sicon_descumpridas = CondicionalidadeSICON.objects.filter(empresa=empresa, status="descumprida").count()

    # Benefícios eventuais
    beneficios_mes = BeneficioEventual.objects.filter(empresa=empresa, data_concessao__gte=inicio_mes).count()
    valor_beneficios_mes = BeneficioEventual.objects.filter(
        empresa=empresa, data_concessao__gte=inicio_mes
    ).aggregate(v=Sum("valor"))["v"] or 0

    # IA: inconsistências pendentes
    inconsistencias_alta = InconsistenciaCadastral.objects.filter(empresa=empresa, status="pendente", severidade="alta").count()
    inconsistencias_total_pendentes = InconsistenciaCadastral.objects.filter(empresa=empresa, status="pendente").count()

    return JsonResponse({
        "referencia_mes": str(inicio_mes),
        "cras_paif": {
            "unidades": cras_unidades,
            "familias_total": familias_total,
            "familias_em_acompanhamento": familias_acomp,
            "atendimentos_mes": atend_cras_mes,
            "atendimentos_ano": atend_cras_ano,
            "visitas_domiciliares_mes": visitas_mes,
            "vulnerabilidades_identificadas_mes": vulnerabilidades_mes,
            "prontuarios_paif_abertos": prontuarios_abertos,
        },
        "creas_paefi": {
            "unidades": creas_unidades,
            "casos_ativos": casos_creas_ativos,
            "novos_mes": novos_creas_mes,
            "por_tipo_violacao": {p["tipo_violacao"]: p["total"] for p in por_violacao},
        },
        "cadunico": {
            "familias_importadas": cadunico_total,
            "titulares_pbf": cadunico_pbf,
        },
        "bpc": {"beneficiarios_ativos": bpc_ativos},
        "sicon": {"descumpridas": sicon_descumpridas},
        "beneficios_eventuais": {
            "quantidade_mes": beneficios_mes,
            "valor_mes": float(valor_beneficios_mes),
        },
        "ia": {
            "inconsistencias_alta_pendentes": inconsistencias_alta,
            "inconsistencias_total_pendentes": inconsistencias_total_pendentes,
        },
    })


# ─── CENSO SUAS ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_suas_censo(request):
    """
    Indicadores do Censo SUAS (MDS) para o período solicitado.
    Parâmetros: ?ano=2025&mes=6 (omitir mes = ano inteiro)
    """
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import (
        FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial,
        AtendimentoCREAS, BeneficiarioBPC, CondicionalidadeSICON, ProntuarioSocialPAIF,
    )

    hoje = date.today()
    ano = int(request.GET.get("ano", hoje.year))
    mes = request.GET.get("mes")

    if mes:
        mes = int(mes)
        data_ini = date(ano, mes, 1)
        data_fim = date(ano, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(ano, 12, 31)
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
    prontuarios_abertos_periodo = ProntuarioSocialPAIF.objects.filter(
        empresa=empresa, data_abertura__range=(data_ini, data_fim)
    ).count()

    # PAEFI / CREAS
    paefi_novos = AtendimentoCREAS.objects.filter(
        empresa=empresa, data_atendimento__range=(data_ini, data_fim)
    ).count()
    paefi_ativos = AtendimentoCREAS.objects.filter(empresa=empresa, situacao="em_acompanhamento").count()
    por_violacao_paefi = dict(
        AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__range=(data_ini, data_fim))
        .values("tipo_violacao").annotate(total=Count("id")).values_list("tipo_violacao", "total")
    )

    # BPC
    bpc_pcd = BeneficiarioBPC.objects.filter(empresa=empresa, tipo_bpc="pessoa_deficiencia", ativo=True).count()
    bpc_idoso = BeneficiarioBPC.objects.filter(empresa=empresa, tipo_bpc="idoso_65", ativo=True).count()

    # SICON
    sicon_saude = CondicionalidadeSICON.objects.filter(empresa=empresa, area="saude", status="descumprida").count()
    sicon_educacao = CondicionalidadeSICON.objects.filter(empresa=empresa, area="educacao", status="descumprida").count()
    sicon_social = CondicionalidadeSICON.objects.filter(empresa=empresa, area="social", status="descumprida").count()

    return JsonResponse({
        "periodo": {"ano": ano, "mes": mes, "data_inicio": str(data_ini), "data_fim": str(data_fim)},
        "cras_paif": {
            "familias_referenciadas_total": familias_referenciadas,
            "atendimentos_individuais": paif_individual,
            "atendimentos_familiares": paif_familiar,
            "atendimentos_grupo": paif_grupo,
            "total_atendimentos": paif_individual + paif_familiar + paif_grupo,
            "visitas_domiciliares": visitas_periodo,
            "prontuarios_abertos": prontuarios_abertos_periodo,
        },
        "creas_paefi": {
            "novos_acolhimentos": paefi_novos,
            "em_acompanhamento": paefi_ativos,
            "por_tipo_violacao": por_violacao_paefi,
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


# ─── IA: INCONSISTÊNCIAS CADASTRAIS (com persistência) ───────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_ia_inconsistencias(request):
    """
    GET  — Lista inconsistências já detectadas + resumo por severidade/status.
           Parâmetros: ?status=pendente&severidade=alta
    POST — Executa nova varredura IA, persiste novos achados (deduplicados por tipo+descrição).
           Body: {} (sem parâmetros)
    """
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import InconsistenciaCadastral

    if request.method == "GET":
        qs = InconsistenciaCadastral.objects.filter(empresa=empresa).order_by("-criado_em")
        status_f = request.GET.get("status")
        sev_f = request.GET.get("severidade")
        if status_f:
            qs = qs.filter(status=status_f)
        if sev_f:
            qs = qs.filter(severidade=sev_f)

        resumo = dict(qs.values("severidade").annotate(total=Count("id")).values_list("severidade", "total"))
        resumo_status = dict(qs.values("status").annotate(total=Count("id")).values_list("status", "total"))

        def _inc_dict(i):
            return {
                "id": i.id,
                "tipo": i.tipo,
                "tipo_display": i.get_tipo_display(),
                "severidade": i.severidade,
                "descricao": i.descricao,
                "dados_extras": i.dados_extras,
                "status": i.status,
                "resolvida_por": i.resolvida_por,
                "resolvida_em": i.resolvida_em.isoformat() if i.resolvida_em else None,
                "observacao": i.observacao,
                "criado_em": i.criado_em.isoformat(),
            }

        return JsonResponse({
            "inconsistencias": [_inc_dict(i) for i in qs[:200]],
            "resumo_severidade": resumo,
            "resumo_status": resumo_status,
        })

    # POST — executa varredura IA
    _executar_varredura_ia(empresa)
    total_pendentes = InconsistenciaCadastral.objects.filter(empresa=empresa, status="pendente").count()
    return JsonResponse({"ok": True, "total_pendentes": total_pendentes})


def _executar_varredura_ia(empresa):
    """Detecta inconsistências no CadÚnico/BPC/CRAS e persiste em InconsistenciaCadastral."""
    from .models import (
        CadUnicoFamilia, BeneficiarioBPC, FamiliaCRAS, AtendimentoCREAS,
        InconsistenciaCadastral,
    )

    novos = []

    # 1. NIS duplicado no CadÚnico local
    nis_duplicados = (
        CadUnicoFamilia.objects.filter(empresa=empresa)
        .exclude(responsavel_nis="")
        .values("responsavel_nis")
        .annotate(qtd=Count("id"))
        .filter(qtd__gt=1)
    )
    for entry in nis_duplicados:
        desc = f"NIS {entry['responsavel_nis']} aparece em {entry['qtd']} registros distintos."
        if not InconsistenciaCadastral.objects.filter(empresa=empresa, tipo="nis_duplicado", descricao=desc, status="pendente").exists():
            novos.append(InconsistenciaCadastral(
                empresa=empresa, tipo="nis_duplicado", severidade="alta",
                descricao=desc,
                dados_extras={"nis": entry["responsavel_nis"], "ocorrencias": entry["qtd"]},
            ))

    # 2. PBF com renda per capita acima do limite
    pbf_renda_alta = CadUnicoFamilia.objects.filter(
        empresa=empresa, marcador_pbf=True, renda_per_capita__gt=_LIMITE_RENDA_CADUNICO
    )
    for f in pbf_renda_alta[:50]:
        desc = (
            f"Família '{f.responsavel_nome}' (NIS {f.responsavel_nis}) marcada como PBF "
            f"mas renda per capita R$ {f.renda_per_capita:.2f} acima do limite "
            f"R$ {_LIMITE_RENDA_CADUNICO:.2f}."
        )
        if not InconsistenciaCadastral.objects.filter(empresa=empresa, tipo="pbf_renda_acima_limite",
                                                       dados_extras__familia_id=f.id, status="pendente").exists():
            novos.append(InconsistenciaCadastral(
                empresa=empresa, tipo="pbf_renda_acima_limite", severidade="alta",
                descricao=desc,
                dados_extras={"familia_id": f.id, "responsavel_nome": f.responsavel_nome,
                              "responsavel_nis": f.responsavel_nis, "renda_per_capita": float(f.renda_per_capita)},
            ))

    # 3. Número de integrantes implausível (> 15)
    integrantes_alto = CadUnicoFamilia.objects.filter(empresa=empresa, qtd_pessoas__gt=15)
    for f in integrantes_alto[:20]:
        desc = f"Família '{f.responsavel_nome}' declarada com {f.qtd_pessoas} integrantes."
        if not InconsistenciaCadastral.objects.filter(empresa=empresa, tipo="integrantes_implausivel",
                                                       dados_extras__familia_id=f.id, status="pendente").exists():
            novos.append(InconsistenciaCadastral(
                empresa=empresa, tipo="integrantes_implausivel", severidade="media",
                descricao=desc,
                dados_extras={"familia_id": f.id, "responsavel_nome": f.responsavel_nome,
                              "qtd_pessoas": f.qtd_pessoas},
            ))

    # 4. Beneficiário BPC sem marcador BPC no CadÚnico
    bpc_ativos = BeneficiarioBPC.objects.filter(empresa=empresa, ativo=True).exclude(beneficiario_nis="")
    nis_com_bpc = set(bpc_ativos.values_list("beneficiario_nis", flat=True))
    nis_com_marcador = set(
        CadUnicoFamilia.objects.filter(empresa=empresa, marcador_bpc=True)
        .values_list("responsavel_nis", flat=True)
    )
    for b in bpc_ativos:
        if b.beneficiario_nis and b.beneficiario_nis not in nis_com_marcador:
            desc = (
                f"Beneficiário BPC '{b.beneficiario_nome}' (NIS {b.beneficiario_nis}) "
                f"não possui marcador BPC no CadÚnico local."
            )
            if not InconsistenciaCadastral.objects.filter(empresa=empresa, tipo="bpc_sem_marcador",
                                                           dados_extras__bpc_id=b.id, status="pendente").exists():
                novos.append(InconsistenciaCadastral(
                    empresa=empresa, tipo="bpc_sem_marcador", severidade="media",
                    descricao=desc,
                    dados_extras={"bpc_id": b.id, "beneficiario_nome": b.beneficiario_nome,
                                  "nis": b.beneficiario_nis},
                ))

    # 5. Famílias CRAS em acompanhamento sem NIS/CadÚnico
    sem_cadunico = FamiliaCRAS.objects.filter(
        empresa=empresa, situacao="em_acompanhamento",
        cadUnico_numero_seq="", responsavel_nis=""
    ).count()
    if sem_cadunico > 0:
        desc = (
            f"{sem_cadunico} família(s) em acompanhamento no CRAS sem NIS "
            f"ou referência ao CadÚnico registrada."
        )
        if not InconsistenciaCadastral.objects.filter(empresa=empresa, tipo="familias_sem_cadunico",
                                                       status="pendente").exists():
            novos.append(InconsistenciaCadastral(
                empresa=empresa, tipo="familias_sem_cadunico", severidade="baixa",
                descricao=desc,
                dados_extras={"quantidade": sem_cadunico},
            ))

    # 6. CREAS em acompanhamento sem tipo de violação definido
    creas_sem_violacao = AtendimentoCREAS.objects.filter(
        empresa=empresa, situacao="em_acompanhamento", tipo_violacao="outro"
    ).count()
    if creas_sem_violacao > 0:
        desc = f"{creas_sem_violacao} caso(s) CREAS em acompanhamento com tipo de violação indefinido ('outro')."
        if not InconsistenciaCadastral.objects.filter(empresa=empresa, tipo="creas_sem_vulnerabilidade",
                                                       status="pendente").exists():
            novos.append(InconsistenciaCadastral(
                empresa=empresa, tipo="creas_sem_vulnerabilidade", severidade="baixa",
                descricao=desc,
                dados_extras={"quantidade": creas_sem_violacao},
            ))

    if novos:
        InconsistenciaCadastral.objects.bulk_create(novos)


@csrf_exempt
@require_http_methods(["PATCH"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_ia_inconsistencia_resolver(request, inconsistencia_id):
    """
    PATCH — Resolve ou descarta uma inconsistência.
    Body: {"status": "resolvida"|"descartada", "observacao": "...", "resolvida_por": "..."}
    """
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import InconsistenciaCadastral
    from django.utils import timezone

    try:
        inc = InconsistenciaCadastral.objects.get(id=inconsistencia_id, empresa=empresa)
    except InconsistenciaCadastral.DoesNotExist:
        return JsonResponse({"erro": "Inconsistência não encontrada"}, status=404)

    data = json.loads(request.body)
    novo_status = data.get("status")
    if novo_status not in ("resolvida", "descartada"):
        return JsonResponse({"erro": "Status deve ser 'resolvida' ou 'descartada'"}, status=400)

    inc.status = novo_status
    inc.observacao = data.get("observacao", "")
    inc.resolvida_por = data.get("resolvida_por", "")
    inc.resolvida_em = timezone.now()
    inc.save()
    return JsonResponse({"ok": True, "status": inc.status})


# ─── RELATÓRIO MENSAL MDS ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
@api_requer_permissao_modulo("assistencia.gestao_suas")
def api_ass_suas_relatorio_mensal(request):
    """
    Relatório mensal consolidado SUAS para prestação de contas ao MDS.
    Parâmetros: ?ano=2025&mes=6
    """
    empresa = _assoc(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito"}, status=403)

    from .models import (
        UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial,
        UnidadeCREAS, AtendimentoCREAS,
        BeneficioEventual, CondicionalidadeSICON, ProntuarioSocialPAIF,
    )

    hoje = date.today()
    ano = int(request.GET.get("ano", hoje.year))
    mes = int(request.GET.get("mes", hoje.month))
    data_ini = date(ano, mes, 1)
    data_fim = date(ano, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(ano, 12, 31)

    # CRAS / PAIF
    unidades_cras = list(
        UnidadeCRAS.objects.filter(empresa=empresa, ativo=True).values("id", "nome", "municipio")
    )
    novas_familias = FamiliaCRAS.objects.filter(empresa=empresa, data_cadastro__range=(data_ini, data_fim)).count()
    atend_por_tipo = dict(
        AtendimentoCRAS.objects.filter(empresa=empresa, data_atendimento__range=(data_ini, data_fim))
        .values("tipo").annotate(total=Count("id")).values_list("tipo", "total")
    )
    visitas = VisitaDomiciliarSocial.objects.filter(empresa=empresa, data_visita__range=(data_ini, data_fim)).count()
    vulnerabilidades = VisitaDomiciliarSocial.objects.filter(
        empresa=empresa, data_visita__range=(data_ini, data_fim), vulnerabilidade_identificada=True
    ).count()
    prontuarios_novos = ProntuarioSocialPAIF.objects.filter(
        empresa=empresa, data_abertura__range=(data_ini, data_fim)
    ).count()

    # CREAS / PAEFI
    unidades_creas = list(
        UnidadeCREAS.objects.filter(empresa=empresa, ativo=True).values("id", "nome", "municipio")
    )
    creas_por_violacao = dict(
        AtendimentoCREAS.objects.filter(empresa=empresa, data_atendimento__range=(data_ini, data_fim))
        .values("tipo_violacao").annotate(total=Count("id")).values_list("tipo_violacao", "total")
    )

    # Benefícios eventuais
    beneficios_por_tipo = dict(
        BeneficioEventual.objects.filter(empresa=empresa, data_concessao__range=(data_ini, data_fim))
        .values("tipo").annotate(total=Count("id")).values_list("tipo", "total")
    )
    valor_total_beneficios = (
        BeneficioEventual.objects.filter(empresa=empresa, data_concessao__range=(data_ini, data_fim))
        .aggregate(total=Sum("valor"))["total"] or 0
    )

    # SICON
    sicon_resumo = dict(
        CondicionalidadeSICON.objects.filter(
            empresa=empresa, periodo_referencia=f"{ano}/{mes:02d}"
        ).values("status").annotate(total=Count("id")).values_list("status", "total")
    )

    municipio = getattr(empresa, "nome_fantasia", None) or str(empresa)

    return JsonResponse({
        "municipio": municipio,
        "periodo": {"ano": ano, "mes": mes, "data_inicio": str(data_ini), "data_fim": str(data_fim)},
        "cras_paif": {
            "unidades": unidades_cras,
            "novas_familias_cadastradas": novas_familias,
            "atendimentos_por_tipo": atend_por_tipo,
            "visitas_domiciliares": visitas,
            "vulnerabilidades_identificadas": vulnerabilidades,
            "prontuarios_paif_novos": prontuarios_novos,
        },
        "creas_paefi": {
            "unidades": unidades_creas,
            "atendimentos_por_tipo_violacao": creas_por_violacao,
        },
        "beneficios_eventuais": {
            "por_tipo": beneficios_por_tipo,
            "valor_total": float(valor_total_beneficios),
        },
        "sicon": {"por_status": sicon_resumo},
    })

