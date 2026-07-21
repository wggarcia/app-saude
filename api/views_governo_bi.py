from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Sum, Q
from datetime import date, timedelta

from .access_control import (
    requer_setor,
    requer_operacao_page,
    requer_permissao_modulo,
    get_setor,
    principal_pode_operacao_setorial,
    api_requer_permissao_modulo,
)
from .services.auth_session import empresa_autenticada_from_request

try:
    from .models import AtendimentoUBS, TransmissaoSIPNI, AgendamentoUBS
except ImportError:
    AtendimentoUBS = None
    TransmissaoSIPNI = None
    AgendamentoUBS = None

try:
    from .models import VacinacaoRegistro
except ImportError:
    VacinacaoRegistro = None

try:
    from .views_dashboard import contexto_navegacao_setorial
except ImportError:
    def contexto_navegacao_setorial(request, emp):
        return {}


def _gov(request):
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# Metas de cobertura vacinal do PNI (Programa Nacional de Imunizações) por
# imunobiológico. Usadas como denominador em `cobertura = realizado/meta*100`.
# Valores oficiais aproximados; "default" cobre imunobiológicos não listados.
METAS_COBERTURA_VACINAL = {
    "sarampo": 95,
    "poliomielite": 95,
    "polio": 95,
    "covid-19": 100,
    "covid19": 100,
    "covid": 100,
    "hepatite b": 95,
    "hepatite": 95,
    "febre amarela": 95,
}
META_COBERTURA_VACINAL_DEFAULT = 90


def _meta_cobertura_vacinal(nome_imunobiologico):
    """Retorna a meta de cobertura (PNI) para o imunobiológico pelo nome, com
    correspondência por substring (case-insensitive, sem acentuação exata)."""
    nome_norm = (nome_imunobiologico or "").strip().lower()
    for chave, meta in METAS_COBERTURA_VACINAL.items():
        if chave in nome_norm:
            return meta
    return META_COBERTURA_VACINAL_DEFAULT


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_producao_mensal(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    hoje = date.today()

    meses = []

    if AtendimentoUBS is None:
        for i in range(11, -1, -1):
            mes_ref = hoje.month - i
            ano_ref = hoje.year
            while mes_ref <= 0:
                mes_ref += 12
                ano_ref -= 1
            meses.append({
                "mes": f"{ano_ref:04d}-{mes_ref:02d}",
                "total": 0,
                "consultas": 0,
                "procedimentos": 0,
            })
        return JsonResponse({"meses": meses})

    for i in range(11, -1, -1):
        mes_ref = hoje.month - i
        ano_ref = hoje.year
        while mes_ref <= 0:
            mes_ref += 12
            ano_ref -= 1

        qs = AtendimentoUBS.objects.filter(
            empresa=emp,
            data_atendimento__year=ano_ref,
            data_atendimento__month=mes_ref,
        )

        total = qs.count()
        # Proxy: CBO 225x = médico (consulta), procedimento_ab preenchido = procedimento
        consultas = qs.filter(cbo__startswith="225").count()
        procedimentos = qs.filter(
            procedimento_ab__isnull=False
        ).exclude(procedimento_ab="").count()

        meses.append({
            "mes": f"{ano_ref:04d}-{mes_ref:02d}",
            "total": total,
            "consultas": consultas,
            "procedimentos": procedimentos,
        })

    return JsonResponse({"meses": meses})


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_cobertura_vacinal(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    vacinas = []

    if TransmissaoSIPNI is None and VacinacaoRegistro is None:
        return JsonResponse({"vacinas": vacinas})

    imunobios = []

    if VacinacaoRegistro is not None:
        imunobios = (
            VacinacaoRegistro.objects.filter(empresa=emp)
            .values("imunobiologico__nome")
            .annotate(realizado=Count("id"))
            .order_by("imunobiologico__nome")
        )

    if not imunobios and TransmissaoSIPNI is not None:
        imunobios = (
            TransmissaoSIPNI.objects.filter(empresa=emp)
            .values("imunobiologico__nome")
            .annotate(realizado=Count("id"))
            .order_by("imunobiologico__nome")
        )

    for item in imunobios:
        nome = item.get("imunobiologico__nome") or "Desconhecido"
        realizado = item.get("realizado", 0)
        meta = _meta_cobertura_vacinal(nome)
        cobertura = round((realizado / meta) * 100, 1) if meta else 0.0
        vacinas.append({
            "nome": nome,
            "meta": meta,
            "realizado": realizado,
            "cobertura": cobertura,
        })

    return JsonResponse({"vacinas": vacinas})


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_cronicas(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    resultado_has = {"total": 0, "controlados": 0, "pct_controle": 0.0}
    resultado_dm = {"total": 0, "controlados": 0, "pct_controle": 0.0}

    if AtendimentoUBS is None:
        return JsonResponse({"has": resultado_has, "dm": resultado_dm})

    qs_has = AtendimentoUBS.objects.filter(
        empresa=emp,
        cid10__startswith="I10",
    )
    total_has = qs_has.count()
    # PAS < 140 = hipertensão controlada (referência SBC 2020)
    controlados_has = qs_has.filter(
        ultima_pa_sistolica__isnull=False,
        ultima_pa_sistolica__lt=140,
    ).count()
    pct_has = round(controlados_has / total_has * 100, 1) if total_has else 0.0

    resultado_has = {
        "total": total_has,
        "controlados": controlados_has,
        "pct_controle": pct_has,
    }

    qs_dm = AtendimentoUBS.objects.filter(
        empresa=emp,
        cid10__startswith="E11",
    )
    total_dm = qs_dm.count()
    # DM controlada: situacao_pressao 'controlado' (preenchida pelo profissional)
    controlados_dm = qs_dm.filter(situacao_pressao="controlado").count()
    pct_dm = round(controlados_dm / total_dm * 100, 1) if total_dm else 0.0

    resultado_dm = {
        "total": total_dm,
        "controlados": controlados_dm,
        "pct_controle": pct_dm,
    }

    return JsonResponse({"has": resultado_has, "dm": resultado_dm})


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_produtividade(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    unidades = []

    if AtendimentoUBS is None:
        return JsonResponse({"unidades": unidades})

    hoje = date.today()

    # unidade_saude é CharField (não FK) — usar o campo direto
    qs = (
        AtendimentoUBS.objects.filter(
            empresa=emp,
            data_atendimento__year=hoje.year,
            data_atendimento__month=hoje.month,
        )
        .values("unidade_saude")
        .annotate(
            atendimentos_mes=Count("id"),
            profissionais=Count("profissional", distinct=True),
        )
        .order_by("unidade_saude")
    )

    for item in qs:
        unidades.append({
            "nome": item.get("unidade_saude") or "Sem unidade",
            "atendimentos_mes": item.get("atendimentos_mes", 0),
            "profissionais": item.get("profissionais", 0),
        })

    return JsonResponse({"unidades": unidades})


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_fila_espera(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    especialidades = []

    if AgendamentoUBS is None:
        return JsonResponse({"especialidades": especialidades})

    from django.db.models import Avg, F, ExpressionWrapper, DurationField
    qs = (
        AgendamentoUBS.objects.filter(empresa=emp, data_solicitacao__isnull=False)
        .annotate(
            espera=ExpressionWrapper(
                F("data_consulta") - F("data_solicitacao"),
                output_field=DurationField(),
            )
        )
        .values("especialidade")
        .annotate(agendados=Count("id"), media_espera=Avg("espera"))
        .order_by("especialidade")
    )

    for item in qs:
        media_espera = item.get("media_espera")
        media_dias = round(media_espera.days, 1) if media_espera else 0
        especialidades.append({
            "nome": item.get("especialidade") or "Sem especialidade",
            "media_dias": media_dias,
            "agendados": item.get("agendados", 0),
        })

    return JsonResponse({"especialidades": especialidades})


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_kpis(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    hoje = date.today()

    atendimentos_mes = 0
    consultas_realizadas = 0
    # TODO: cobertura_acs não é calculada de verdade. O cálculo real seria
    # (famílias visitadas no mês pelos Agentes Comunitários de Saúde) / (total de
    # famílias ativas cadastradas na área) * 100. Isso exigiria models como
    # `VisitaACS` (registro de visita domiciliar do ACS, com data e família) e
    # `Familia` (cadastro de família ativa por área/microárea). Nenhum dos dois
    # existe hoje em api/models.py (existe `VisitaDomiciliar`, mas não representa
    # visita de ACS vinculada a cobertura de família cadastrada) — não foram
    # criados aqui por não caber a esta correção decidir sozinho sobre novo
    # model/migration. Mantido em 0.0 até que o model correto seja definido.
    cobertura_acs = 0.0
    producao_bpa = 0

    if AtendimentoUBS is not None:
        qs_mes = AtendimentoUBS.objects.filter(
            empresa=emp,
            data_atendimento__year=hoje.year,
            data_atendimento__month=hoje.month,
        )
        atendimentos_mes = qs_mes.count()
        # Proxy para consultas: CBO 225x = médico (generalista, especialista APS)
        consultas_realizadas = qs_mes.filter(cbo__startswith="225").count()
        # Proxy para produção BPA: atendimentos com procedimento_ab preenchido
        producao_bpa = qs_mes.filter(
            procedimento_ab__isnull=False
        ).exclude(procedimento_ab="").count()

    return JsonResponse({
        "atendimentos_mes": atendimentos_mes,
        "consultas_realizadas": consultas_realizadas,
        "cobertura_acs": cobertura_acs,
        "producao_bpa": producao_bpa,
    })


@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.administrativo")
def governo_bi_page(request):
    ctx = contexto_navegacao_setorial(request, "governo")
    ctx["titulo"] = "Business Intelligence - Governo / APS"
    return render(request, "governo_bi.html", ctx)
