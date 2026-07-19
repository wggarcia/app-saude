from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Sum, Avg, Q
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


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.administrativo")
def bi_producao_mensal(request):
    emp = _gov(request)
    if emp is None:
        return JsonResponse({"erro": "Acesso negado"}, status=403)

    hoje = date.today()
    inicio = date(hoje.year if hoje.month > 12 else (hoje.year - 1 if hoje.month == 1 else hoje.year),
                  (hoje.month - 12) % 12 or 12, 1)
    # Calcula o inicio como 12 meses atras
    ano_inicio = hoje.year - 1 if hoje.month == 1 else hoje.year
    mes_inicio = hoje.month - 1 if hoje.month > 1 else 12
    if hoje.month == 1:
        ano_inicio = hoje.year - 1
        mes_inicio = 1
    else:
        ano_inicio = hoje.year - 1
        mes_inicio = hoje.month

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
        consultas = qs.filter(tipo_atendimento="consulta").count()
        procedimentos = qs.filter(tipo_atendimento="procedimento").count()

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
        meta = 100
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
        cid_10__startswith="I10",
    )
    total_has = qs_has.count()
    controlados_has = qs_has.filter(situacao="controlado").count()
    pct_has = round((controlados_has / total_has) * 100, 1) if total_has else 0.0

    resultado_has = {
        "total": total_has,
        "controlados": controlados_has,
        "pct_controle": pct_has,
    }

    qs_dm = AtendimentoUBS.objects.filter(
        empresa=emp,
        cid_10__startswith="E11",
    )
    total_dm = qs_dm.count()
    controlados_dm = qs_dm.filter(situacao="controlado").count()
    pct_dm = round((controlados_dm / total_dm) * 100, 1) if total_dm else 0.0

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

    qs = (
        AtendimentoUBS.objects.filter(
            empresa=emp,
            data_atendimento__year=hoje.year,
            data_atendimento__month=hoje.month,
        )
        .values("unidade__nome")
        .annotate(
            atendimentos_mes=Count("id"),
            profissionais=Count("profissional", distinct=True),
        )
        .order_by("unidade__nome")
    )

    for item in qs:
        unidades.append({
            "nome": item.get("unidade__nome") or "Sem unidade",
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

    qs = (
        AgendamentoUBS.objects.filter(empresa=emp)
        .values("especialidade__nome")
        .annotate(
            media_dias=Avg("tempo_espera_dias"),
            agendados=Count("id"),
        )
        .order_by("especialidade__nome")
    )

    for item in qs:
        media = item.get("media_dias")
        especialidades.append({
            "nome": item.get("especialidade__nome") or "Sem especialidade",
            "media_dias": round(float(media), 1) if media is not None else 0,
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
    cobertura_acs = 0.0
    producao_bpa = 0

    if AtendimentoUBS is not None:
        qs_mes = AtendimentoUBS.objects.filter(
            empresa=emp,
            data_atendimento__year=hoje.year,
            data_atendimento__month=hoje.month,
        )
        atendimentos_mes = qs_mes.count()
        consultas_realizadas = qs_mes.filter(tipo_atendimento="consulta").count()
        producao_bpa = qs_mes.filter(bpa=True).count()

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
    emp = empresa_autenticada_from_request(request)
    ctx = contexto_navegacao_setorial(request, emp)
    ctx["titulo"] = "Business Intelligence - Governo / APS"
    return render(request, "governo_bi.html", ctx)
