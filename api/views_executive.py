"""
Dashboard executivo — agrega KPIs de todos os módulos em uma única visão estratégica.
Endpoint: GET /api/executive/dashboard/
"""
from datetime import date, timedelta
from django.http import JsonResponse
from .access_control import api_requer_gerencia
from .services.auth_session import empresa_autenticada_from_request


@api_requer_gerencia
def api_executive_dashboard(request):
    empresa = empresa_autenticada_from_request(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .access_control import get_setor
    setor = get_setor(empresa)
    hoje = date.today()
    mes_ini = hoje.replace(day=1)
    mes_ant = (mes_ini - timedelta(days=1)).replace(day=1)

    # ─── Retorna APENAS dados do setor desta empresa ──────────────────────────
    # Um hospital não recebe dados de SST. Uma farmácia não recebe dados de
    # governo. Cada ambiente é totalmente isolado.
    data: dict = {"empresa": empresa.nome, "setor": setor, "data": str(hoje)}

    if setor == "empresa":
        data["sst"] = _sst_kpis(empresa, hoje)
        data["alertas"] = _alertas_resumo_setor(empresa, hoje, setor)
    elif setor == "farmacia":
        data["farmacia"] = _farmacia_kpis(empresa, hoje, mes_ini, mes_ant)
        data["alertas"] = _alertas_resumo_setor(empresa, hoje, setor)
    elif setor == "hospital":
        data["hospital"] = _hospital_kpis(empresa, hoje)
        data["alertas"] = _alertas_resumo_setor(empresa, hoje, setor)
    elif setor == "governo":
        data["governo"] = _governo_kpis(empresa, hoje)
        data["alertas"] = _alertas_resumo_setor(empresa, hoje, setor)
    elif setor == "plano_saude":
        data["plano_saude"] = _plano_saude_kpis(empresa, hoje, mes_ini, mes_ant)
        data["alertas"] = _alertas_resumo_setor(empresa, hoje, setor)
    else:
        # fallback seguro — nunca mistura setores
        data["alertas"] = {"total": 0, "criticos": 0, "alertas": 0, "infos": 0}

    return JsonResponse(data)


def _sst_kpis(empresa, hoje):
    try:
        from .models import FuncionarioSST, ExameMedico, EntregaEPI, TreinamentoNR, AgendamentoSST
        from datetime import timedelta

        funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
        total_func = funcionarios.count()

        atencao = hoje + timedelta(days=30)
        aso_alertas = 0
        afastados = 0
        for f in funcionarios.prefetch_related("asos", "afastamentos"):
            aso = f.asos.filter(resultado__in=["apto", "apto_restricao"]).order_by("-data_validade").first()
            if aso and aso.data_validade and aso.data_validade <= atencao:
                aso_alertas += 1
            if f.afastamentos.filter(data_retorno_real__isnull=True).exists():
                afastados += 1

        exames_vencidos = ExameMedico.objects.filter(
            funcionario__empresa=empresa, funcionario__ativo=True,
            data_validade__lt=hoje
        ).count()

        treinamentos_vencidos = TreinamentoNR.objects.filter(
            funcionario__empresa=empresa, funcionario__ativo=True,
            data_validade__lt=hoje
        ).count()

        ag_semana = AgendamentoSST.objects.filter(
            empresa=empresa,
            status__in=["agendado", "confirmado"],
            data_hora__date__gte=hoje,
            data_hora__date__lte=hoje + timedelta(days=7),
        ).count()

        return {
            "total_funcionarios": total_func,
            "afastados": afastados,
            "aso_alertas": aso_alertas,
            "exames_vencidos": exames_vencidos,
            "treinamentos_vencidos": treinamentos_vencidos,
            "agendamentos_semana": ag_semana,
        }
    except Exception:
        return {}


def _farmacia_kpis(empresa, hoje, mes_ini, mes_ant):
    try:
        from .models import ItemFarmacia, DispensacaoMedicamento, PedidoCompraFarmacia, LoteMedicamento

        total_itens = ItemFarmacia.objects.filter(empresa=empresa, ativo=True).count()
        abaixo_min = ItemFarmacia.objects.filter(empresa=empresa, ativo=True).values_list(
            "estoque_atual", "estoque_minimo"
        )
        criticos = sum(1 for a, m in abaixo_min if m and a is not None and float(a) <= 0)
        alertas_est = sum(1 for a, m in abaixo_min if m and a is not None and 0 < float(a) <= float(m))

        disp_mes = DispensacaoMedicamento.objects.filter(
            empresa=empresa, data_dispensacao__date__gte=mes_ini
        ).count()
        disp_mes_ant = DispensacaoMedicamento.objects.filter(
            empresa=empresa,
            data_dispensacao__date__gte=mes_ant,
            data_dispensacao__date__lt=mes_ini,
        ).count()

        pedidos_abertos = PedidoCompraFarmacia.objects.filter(
            empresa=empresa, status__in=["rascunho", "enviado", "aprovado"]
        ).count()

        lotes_vencendo = LoteMedicamento.objects.filter(
            empresa=empresa,
            quantidade_atual__gt=0,
            data_validade__gte=hoje,
            data_validade__lte=hoje + timedelta(days=30),
        ).count()

        # Dispensações últimos 7 dias (histórico)
        hist = []
        for i in range(6, -1, -1):
            d = hoje - timedelta(days=i)
            cnt = DispensacaoMedicamento.objects.filter(
                empresa=empresa, data_dispensacao__date=d
            ).count()
            hist.append({"data": str(d), "valor": cnt})

        return {
            "total_itens": total_itens,
            "estoque_critico": criticos,
            "estoque_alerta": alertas_est,
            "dispensacoes_mes": disp_mes,
            "dispensacoes_mes_anterior": disp_mes_ant,
            "pedidos_abertos": pedidos_abertos,
            "lotes_vencendo_30d": lotes_vencendo,
            "historico_dispensacoes": hist,
        }
    except Exception:
        return {}


def _hospital_kpis(empresa, hoje):
    try:
        from .models import LeitoHospital, InternacaoHospital, TriagemHospital

        total_leitos = LeitoHospital.objects.filter(departamento__empresa=empresa).count()
        ocupados = LeitoHospital.objects.filter(departamento__empresa=empresa, status="ocupado").count()
        disponiveis = LeitoHospital.objects.filter(departamento__empresa=empresa, status="disponivel").count()
        manutencao = LeitoHospital.objects.filter(departamento__empresa=empresa, status="manutencao").count()
        taxa = round(ocupados / max(total_leitos, 1) * 100, 1)

        internacoes_ativas = InternacaoHospital.objects.filter(
            leito__departamento__empresa=empresa, status="ativo"
        ).count()

        altas_mes = InternacaoHospital.objects.filter(
            leito__departamento__empresa=empresa,
            status="alta",
            data_saida__date__gte=hoje.replace(day=1),
        ).count()

        triagens_hoje = TriagemHospital.objects.filter(
            internacao__leito__departamento__empresa=empresa,
            criado_em__date=hoje,
        ).count()

        # Ocupação últimos 7 dias
        hist_ocup = []
        for i in range(6, -1, -1):
            d = hoje - timedelta(days=i)
            # Contar internações que estavam ativas naquele dia
            cnt = InternacaoHospital.objects.filter(
                leito__departamento__empresa=empresa,
                data_entrada__date__lte=d,
            ).filter(
                data_saida__isnull=True
            ).count() + InternacaoHospital.objects.filter(
                leito__departamento__empresa=empresa,
                data_entrada__date__lte=d,
                data_saida__date__gte=d,
            ).count()
            hist_ocup.append({"data": str(d), "valor": cnt})

        return {
            "total_leitos": total_leitos,
            "leitos_ocupados": ocupados,
            "leitos_disponiveis": disponiveis,
            "leitos_manutencao": manutencao,
            "taxa_ocupacao": taxa,
            "internacoes_ativas": internacoes_ativas,
            "altas_mes": altas_mes,
            "triagens_hoje": triagens_hoje,
            "historico_ocupacao": hist_ocup,
        }
    except Exception:
        return {}


def _governo_kpis(empresa, hoje):
    try:
        from .models import ProgramaSaudeGov, IndicadorSaudeGov, PlanoAcaoGov, OrcamentoSaudeGov

        programas_ativos = ProgramaSaudeGov.objects.filter(empresa=empresa, status="ativo").count()
        programas_total = ProgramaSaudeGov.objects.filter(empresa=empresa).count()

        indicadores = IndicadorSaudeGov.objects.filter(empresa=empresa)
        total_ind = indicadores.count()
        metas_atingidas = sum(
            1 for i in indicadores
            if i.meta is not None and i.valor_atual is not None
            and float(i.valor_atual) >= float(i.meta)
        )

        planos_pendentes = PlanoAcaoGov.objects.filter(empresa=empresa, status="pendente").count()
        planos_andamento = PlanoAcaoGov.objects.filter(empresa=empresa, status="em_andamento").count()
        planos_atrasados = PlanoAcaoGov.objects.filter(
            empresa=empresa, status__in=["pendente", "em_andamento"], prazo__lt=hoje
        ).count()

        orcamento = {}
        try:
            orc = OrcamentoSaudeGov.objects.get(empresa=empresa, ano=hoje.year)
            prev = float(orc.orcamento_previsto) if orc.orcamento_previsto else 0
            exec_ = float(orc.orcamento_executado) if orc.orcamento_executado else 0
            orcamento = {
                "ano": orc.ano,
                "previsto": prev,
                "executado": exec_,
                "pct": round(exec_ / max(prev, 1) * 100, 1),
            }
        except OrcamentoSaudeGov.DoesNotExist:
            orcamento = {"ano": hoje.year, "previsto": 0, "executado": 0, "pct": 0}

        return {
            "programas_ativos": programas_ativos,
            "programas_total": programas_total,
            "metas_atingidas": metas_atingidas,
            "total_indicadores": total_ind,
            "planos_pendentes": planos_pendentes,
            "planos_andamento": planos_andamento,
            "planos_atrasados": planos_atrasados,
            "orcamento": orcamento,
        }
    except Exception:
        return {}


def _alertas_resumo(empresa, hoje):
    try:
        from .views_alertas import (
            _alertas_sst, _alertas_farmacia, _alertas_hospital, _alertas_governo
        )
        todos = (
            _alertas_sst(empresa, hoje)
            + _alertas_farmacia(empresa, hoje)
            + _alertas_hospital(empresa, hoje)
            + _alertas_governo(empresa, hoje)
        )
        return {
            "total": len(todos),
            "criticos": sum(1 for a in todos if a["severidade"] == "critico"),
            "alertas": sum(1 for a in todos if a["severidade"] == "alerta"),
            "infos": sum(1 for a in todos if a["severidade"] == "info"),
        }
    except Exception:
        return {"total": 0, "criticos": 0, "alertas": 0, "infos": 0}


def _plano_saude_kpis(empresa, hoje, mes_ini, mes_ant):
    """KPIs exclusivos do ambiente Plano de Saúde."""
    try:
        from .models import (
            BeneficiarioPlano, GuiaAutorizacao, SinistroPlano,
            ReembolsoPlano, ContratoPlano,
        )
        from django.db.models import Avg

        beneficiarios_ativos = BeneficiarioPlano.objects.filter(
            empresa=empresa, ativo=True
        ).count()
        guias_pendentes = GuiaAutorizacao.objects.filter(
            empresa=empresa, status__in=["pendente", "em_analise"]
        ).count()
        sinistros_analise = SinistroPlano.objects.filter(
            empresa=empresa, status__in=["aberto", "em_analise"]
        ).count() if hasattr(SinistroPlano, "objects") else 0

        # Sinistralidade simples: sinistros/mês vs contratos
        total_contratos = ContratoPlano.objects.filter(empresa=empresa, ativo=True).count()

        reembolsos_pendentes = ReembolsoPlano.objects.filter(
            empresa=empresa, status="pendente"
        ).count() if hasattr(ReembolsoPlano, "objects") else 0

        return {
            "beneficiarios_ativos": beneficiarios_ativos,
            "guias_pendentes": guias_pendentes,
            "sinistros_analise": sinistros_analise,
            "total_contratos": total_contratos,
            "reembolsos_pendentes": reembolsos_pendentes,
        }
    except Exception:
        return {}


def _alertas_resumo_setor(empresa, hoje, setor):
    """Retorna resumo de alertas APENAS do setor da empresa."""
    try:
        from .views_alertas import (
            _alertas_sst, _alertas_farmacia, _alertas_hospital, _alertas_governo,
        )
        mapa = {
            "empresa": _alertas_sst,
            "farmacia": _alertas_farmacia,
            "hospital": _alertas_hospital,
            "governo": _alertas_governo,
        }
        fn = mapa.get(setor)
        todos = fn(empresa, hoje) if fn else []
        return {
            "total": len(todos),
            "criticos": sum(1 for a in todos if a.get("severidade") == "critico"),
            "alertas": sum(1 for a in todos if a.get("severidade") == "alerta"),
            "infos": sum(1 for a in todos if a.get("severidade") == "info"),
        }
    except Exception:
        return {"total": 0, "criticos": 0, "alertas": 0, "infos": 0}


def executive_dashboard_page(request):
    from django.shortcuts import render, redirect
    dono = dono_autenticado_from_request(request)
    if not dono:
        empresa = getattr(request, "empresa", None)
        if empresa:
            from .access_control import get_setor, _destino_correto
            return redirect(_destino_correto(get_setor(empresa)))
        return redirect("/operacao-central/")
    return render(request, "executive_dashboard.html")
