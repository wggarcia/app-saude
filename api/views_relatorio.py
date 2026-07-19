"""
Relatório Executivo — relatório consolidado de saúde e segurança do período.
Endpoint: GET /api/relatorio/executivo?periodo=mes|trimestre|semana|custom&desde=&ate=
Page:     GET /relatorio-executivo/
"""
import logging
from datetime import date, timedelta
from django.http import JsonResponse
from django.db.models import Q, F, Sum, Count, Avg
from .views_dashboard import _empresa_autenticada

logger = logging.getLogger(__name__)


def _periodo_datas(periodo, desde_str=None, ate_str=None):
    hoje = date.today()
    if periodo == "semana":
        ini = hoje - timedelta(days=6)
    elif periodo == "trimestre":
        ini = hoje - timedelta(days=89)
    elif periodo == "custom" and desde_str and ate_str:
        ini = date.fromisoformat(desde_str)
        hoje = date.fromisoformat(ate_str)
    else:  # mes (default)
        ini = hoje.replace(day=1)
    return ini, hoje


def api_relatorio_executivo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    periodo = request.GET.get("periodo", "mes")
    desde_str = request.GET.get("desde", "")
    ate_str = request.GET.get("ate", "")
    ini, fim = _periodo_datas(periodo, desde_str, ate_str)

    data = {
        "empresa": empresa.nome,
        "pacote_codigo": empresa.pacote_codigo,
        "periodo": periodo,
        "desde": str(ini),
        "ate": str(fim),
        "gerado_em": str(date.today()),
        "sst": _relatorio_sst(empresa, ini, fim),
        "empresa_corp": _relatorio_empresa(empresa, ini, fim),
        "farmacia": _relatorio_farmacia(empresa, ini, fim),
        "hospital": _relatorio_hospital(empresa, ini, fim),
        "compliance": _relatorio_compliance(empresa, ini, fim),
        "recomendacoes": _gerar_recomendacoes(empresa, ini, fim),
    }
    return JsonResponse(data)


def _relatorio_sst(empresa, ini, fim):
    try:
        from .models import FuncionarioSST, ExameMedico, EntregaEPI, AgendamentoSST, AfastamentoSST
        from django.db.models import Count

        funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
        total = funcionarios.count()
        if total == 0:
            return {"disponivel": False}

        exames_vencidos = ExameMedico.objects.filter(
            funcionario__empresa=empresa, funcionario__ativo=True,
            data_vencimento__lt=fim
        ).count()
        exames_periodo = ExameMedico.objects.filter(
            funcionario__empresa=empresa,
            data_exame__gte=ini, data_exame__lte=fim
        ).count()

        afastamentos = AfastamentoSST.objects.filter(
            funcionario__empresa=empresa,
            data_inicio__gte=ini, data_inicio__lte=fim
        )
        total_afastamentos = afastamentos.count()

        agendamentos = AgendamentoSST.objects.filter(
            empresa=empresa, data_agendamento__gte=ini, data_agendamento__lte=fim
        )
        ag_realizados = agendamentos.filter(status="realizado").count()
        ag_total = agendamentos.count()

        epis_entregues = EntregaEPI.objects.filter(
            funcionario__empresa=empresa,
            data_entrega__gte=ini, data_entrega__lte=fim
        ).count()

        score = 100
        if total > 0:
            pct_exames_vencidos = exames_vencidos / total * 100
            score -= min(30, pct_exames_vencidos * 0.5)
            score -= min(20, total_afastamentos / total * 100)
        score = max(0, round(score))

        return {
            "disponivel": True,
            "total_funcionarios": total,
            "exames_periodo": exames_realizados if (exames_realizados := exames_periodo) else 0,
            "exames_vencidos": exames_vencidos,
            "afastamentos_periodo": total_afastamentos,
            "agendamentos_realizados": ag_realizados,
            "agendamentos_total": ag_total,
            "epis_entregues": epis_entregues,
            "score_sst": score,
        }
    except Exception:
        logger.error("Erro ao gerar relatório SST no relatório executivo", exc_info=True)
        return {"disponivel": False}


def _relatorio_empresa(empresa, ini, fim):
    try:
        from .models import CheckinDiarioCorporativo, CheckinSemanalCorporativo, PedidoApoioCorporativo

        checkins = CheckinDiarioCorporativo.objects.filter(
            empresa=empresa,
            data_referencia__gte=ini, data_referencia__lte=fim,
        )
        total_checkins = checkins.count()
        if total_checkins == 0:
            return {"disponivel": False}

        avgs = checkins.aggregate(
            humor=Avg("humor"), energia=Avg("energia"),
            estresse=Avg("estresse"), sono=Avg("sono"),
            apoio=Count("id", filter=Q(apoio_solicitado=True)),
        )

        semanais = CheckinSemanalCorporativo.objects.filter(
            empresa=empresa,
            semana_referencia__gte=ini, semana_referencia__lte=fim,
        )
        avg_semanal = semanais.aggregate(
            bem_estar=Avg("bem_estar_geral"),
            burnout=Avg("risco_burnout"),
            pressao=Avg("pressao_trabalho"),
            seguranca_ps=Avg("seguranca_psicologica"),
        )

        apoios = PedidoApoioCorporativo.objects.filter(
            empresa=empresa,
            criado_em__date__gte=ini, criado_em__date__lte=fim,
        )
        apoios_total = apoios.count()
        apoios_resolvidos = apoios.filter(status="concluido").count()

        score_bem_estar = round(
            ((avgs["humor"] or 0) + (avgs["energia"] or 0)
             + (avgs["sono"] or 0) + (5 - (avgs["estresse"] or 3))) / 4, 1
        )

        return {
            "disponivel": True,
            "total_checkins": total_checkins,
            "score_bem_estar": score_bem_estar,
            "media_humor": round(avgs["humor"] or 0, 1),
            "media_energia": round(avgs["energia"] or 0, 1),
            "media_estresse": round(avgs["estresse"] or 0, 1),
            "media_sono": round(avgs["sono"] or 0, 1),
            "media_bem_estar_semanal": round(avg_semanal["bem_estar"] or 0, 1),
            "media_risco_burnout": round(avg_semanal["burnout"] or 0, 1),
            "apoios_total": apoios_total,
            "apoios_resolvidos": apoios_resolvidos,
        }
    except Exception:
        logger.error("Erro ao gerar relatório de empresa/corporativo no relatório executivo", exc_info=True)
        return {"disponivel": False}


def _relatorio_farmacia(empresa, ini, fim):
    try:
        from .models import LoteMedicamento, MovimentoEstoque, ItemFarmacia

        lotes = LoteMedicamento.objects.filter(empresa=empresa)
        vencidos = lotes.filter(data_validade__lt=fim, quantidade_atual__gt=0).count()
        vencendo_30 = lotes.filter(
            data_validade__gte=fim, data_validade__lte=fim + timedelta(days=30),
            quantidade_atual__gt=0
        ).count()
        total_lotes = lotes.filter(quantidade_atual__gt=0).count()

        movimentos = MovimentoEstoque.objects.filter(
            empresa=empresa,
            criado_em__date__gte=ini, criado_em__date__lte=fim,
        )
        entradas = movimentos.filter(tipo="entrada").aggregate(total=Sum("quantidade"))["total"] or 0
        saidas = movimentos.filter(tipo="saida").aggregate(total=Sum("quantidade"))["total"] or 0

        itens_criticos = ItemFarmacia.objects.filter(
            empresa=empresa, ativo=True,
            estoque_atual__lte=F("estoque_minimo")
        ).count()

        return {
            "disponivel": True,
            "total_lotes_ativos": total_lotes,
            "lotes_vencidos": vencidos,
            "lotes_vencendo_30": vencendo_30,
            "movimentos_entradas": round(float(entradas)),
            "movimentos_saidas": round(float(saidas)),
            "itens_estoque_critico": itens_criticos,
        }
    except Exception:
        logger.error("Erro ao gerar relatório de farmácia no relatório executivo", exc_info=True)
        return {"disponivel": False}


def _relatorio_hospital(empresa, ini, fim):
    try:
        from .models import LeitoHospitalar, InternacaoHospital

        leitos = LeitoHospitalar.objects.filter(empresa=empresa)
        ocupados = leitos.filter(status="ocupado").count()
        total_leitos = leitos.count()

        internacoes = InternacaoHospital.objects.filter(
            empresa=empresa,
            data_entrada__gte=ini, data_entrada__lte=fim,
        )
        total_int = internacoes.count()
        altas = internacoes.filter(data_saida__isnull=False).count()

        taxa_ocupacao = round(ocupados / total_leitos * 100) if total_leitos > 0 else 0

        return {
            "disponivel": True,
            "total_leitos": total_leitos,
            "leitos_ocupados": ocupados,
            "taxa_ocupacao_pct": taxa_ocupacao,
            "internacoes_periodo": total_int,
            "altas_periodo": altas,
        }
    except Exception:
        logger.error("Erro ao gerar relatório hospitalar no relatório executivo", exc_info=True)
        return {"disponivel": False}


def _relatorio_compliance(empresa, ini, fim):
    try:
        from .models import AuditoriaInstitucional, DispositivoAutorizado, BiometriaFuncionario

        eventos = AuditoriaInstitucional.objects.filter(
            empresa=empresa,
            criado_em__date__gte=ini, criado_em__date__lte=fim,
        ).count()

        devs_ativos = DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).count()

        # Consentimento LGPD (Art. 11) para coleta de dado biométrico de funcionários
        # (BiometriaFuncionario.consentimento_confirmado_em) é, hoje, o único sinal de
        # conformidade LGPD que já existe de fato no sistema por empresa — por isso é
        # a única base real usada abaixo para status_lgpd.
        biometrias_ativas_qs = BiometriaFuncionario.objects.filter(
            funcionario__empresa=empresa, ativo=True
        )
        biometrias_ativas = biometrias_ativas_qs.count()
        consentimentos_biometricos_pendentes = biometrias_ativas_qs.filter(
            consentimento_confirmado_em__isnull=True
        ).count()

        # TODO: não existem hoje em api/models.py: (1) campo/relação indicando o DPO
        # (encarregado de dados) cadastrado por empresa; (2) registro de aceite/versão
        # de política de privacidade vigente por empresa; (3) um model genérico de
        # "ConsentimentoLGPD" cobrindo outras bases de tratamento além da biometria
        # facial. Sem isso, o cálculo de status_lgpd abaixo é parcial: cobre apenas a
        # pendência de consentimento biométrico já existente no sistema. Um cálculo
        # completo exigiria adicionar esses campos/models (decisão de schema fora do
        # escopo desta correção).
        if consentimentos_biometricos_pendentes > 0:
            status_lgpd = "pendente"
        elif biometrias_ativas > 0:
            status_lgpd = "conforme_parcial"
        else:
            status_lgpd = "sem_dados_para_avaliar"

        return {
            "disponivel": True,
            "eventos_auditoria_periodo": eventos,
            "dispositivos_ativos": devs_ativos,
            "biometrias_ativas": biometrias_ativas,
            "consentimentos_biometricos_pendentes": consentimentos_biometricos_pendentes,
            "status_lgpd": status_lgpd,
        }
    except Exception:
        logger.error("Erro ao gerar relatório de compliance no relatório executivo", exc_info=True)
        return {"disponivel": False}


def _gerar_recomendacoes(empresa, ini, fim):
    recomendacoes = []
    try:
        from .models import FuncionarioSST, ExameMedico, LoteMedicamento, CheckinSemanalCorporativo
        from django.db.models import Avg

        # SST check
        exames_vencidos = ExameMedico.objects.filter(
            funcionario__empresa=empresa, funcionario__ativo=True,
            data_vencimento__lt=fim
        ).count()
        if exames_vencidos > 0:
            recomendacoes.append({
                "tipo": "alerta",
                "modulo": "SST",
                "titulo": f"{exames_vencidos} exame(s) médico(s) vencido(s)",
                "acao": "Agendar renovação imediata para manter conformidade NR-07",
            })

        # Burnout check
        semanais = CheckinSemanalCorporativo.objects.filter(
            empresa=empresa, semana_referencia__gte=ini, semana_referencia__lte=fim
        )
        if semanais.exists():
            avg_burnout = semanais.aggregate(avg=Avg("risco_burnout"))["avg"] or 0
            if avg_burnout >= 3.5:
                recomendacoes.append({
                    "tipo": "critico",
                    "modulo": "Saúde Ocupacional",
                    "titulo": "Risco elevado de burnout detectado",
                    "acao": "Implementar programa de suporte psicológico e revisar cargas de trabalho",
                })

        # Farmácia check
        lotes_vencidos = LoteMedicamento.objects.filter(
            empresa=empresa, data_validade__lt=fim, quantidade_atual__gt=0
        ).count()
        if lotes_vencidos > 0:
            recomendacoes.append({
                "tipo": "alerta",
                "modulo": "Farmácia",
                "titulo": f"{lotes_vencidos} lote(s) vencido(s) com estoque",
                "acao": "Retirar lotes vencidos de circulação e atualizar FEFO",
            })

    except Exception:
        pass

    if not recomendacoes:
        recomendacoes.append({
            "tipo": "ok",
            "modulo": "Geral",
            "titulo": "Todos os indicadores dentro do esperado",
            "acao": "Manter o monitoramento contínuo e regularidade dos check-ins",
        })

    return recomendacoes


def relatorio_page(request):
    from django.shortcuts import render, redirect
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "relatorio_executivo.html")
