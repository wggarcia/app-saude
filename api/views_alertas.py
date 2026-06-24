"""
Sistema de Alertas Inteligentes — hub cross-cutting.

Varre todos os módulos da empresa autenticada e retorna alertas categorizados:
  - SST: ASOs vencendo, exames vencidos, funcionários sem EPI, treinamentos expirados,
         afastamentos ativos, agendamentos atrasados
  - Farmácia: itens abaixo do estoque mínimo, pedidos de compra em aberto há muito tempo
  - Hospital: leitos em manutenção há muito tempo, internações longas sem evolução,
              triagens não atendidas hoje
  - Governo: indicadores fora da meta, planos de ação atrasados, orçamento com execução crítica

Cada alerta tem: modulo, severidade (critico/alerta/info), titulo, descricao, link, criado_em
"""

from datetime import date, timedelta, datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .views_dashboard import _empresa_autenticada
from .access_control import empresa_tem_feature


def _alerta(modulo, severidade, titulo, descricao, link=""):
    return {
        "modulo": modulo,
        "severidade": severidade,   # critico | alerta | info
        "titulo": titulo,
        "descricao": descricao,
        "link": link,
    }


def _alertas_sst(empresa, hoje):
    alertas = []
    try:
        from .models import FuncionarioSST, ExameMedico, EntregaEPI, TreinamentoNR, AgendamentoSST, DocumentoSST

        atencao = hoje + timedelta(days=30)
        urgente  = hoje + timedelta(days=7)

        funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).prefetch_related(
            "asos", "afastamentos"
        )

        sem_aso = 0
        aso_urgente = 0
        aso_atencao = 0
        for f in funcionarios:
            aso = f.asos.filter(valido=True).order_by("-data_validade").first()
            if not aso or not aso.data_validade or aso.data_validade < hoje:
                sem_aso += 1
            elif aso.data_validade <= urgente:
                aso_urgente += 1
            elif aso.data_validade <= atencao:
                aso_atencao += 1

        if sem_aso:
            alertas.append(_alerta("SST", "critico",
                f"{sem_aso} funcionário(s) sem ASO válido",
                "ASOs vencidos comprometem a conformidade SST. Agende imediatamente.",
                "/sst/asos/"))
        if aso_urgente:
            alertas.append(_alerta("SST", "critico",
                f"{aso_urgente} ASO(s) vencendo em até 7 dias",
                "Urgente: agende os exames admissionais/periódicos desta semana.",
                "/sst/asos/"))
        if aso_atencao:
            alertas.append(_alerta("SST", "alerta",
                f"{aso_atencao} ASO(s) vencendo em até 30 dias",
                "Planeje os agendamentos para evitar vencimentos.",
                "/sst/asos/"))

        # Exames vencidos
        vencidos = ExameMedico.objects.filter(
            funcionario__empresa=empresa,
            funcionario__ativo=True,
            data_validade__lt=hoje,
        ).count()
        if vencidos:
            alertas.append(_alerta("SST", "alerta",
                f"{vencidos} exame(s) vencido(s)",
                "Exames com prazo de validade expirado precisam ser renovados.",
                "/sst/exames/"))

        # Funcionários sem EPI ativo
        ids_com_epi = set(
            EntregaEPI.objects.filter(
                funcionario__empresa=empresa,
                data_devolucao__isnull=True
            ).values_list("funcionario_id", flat=True)
        )
        ids_ativos = set(funcionarios.values_list("id", flat=True))
        sem_epi = len(ids_ativos - ids_com_epi)
        if sem_epi:
            alertas.append(_alerta("SST", "alerta",
                f"{sem_epi} funcionário(s) sem EPI entregue",
                "Distribua os EPIs necessários para manter a conformidade.",
                "/sst/epis/"))

        # Treinamentos vencidos
        trein_vencidos = TreinamentoNR.objects.filter(
            funcionario__empresa=empresa,
            funcionario__ativo=True,
            data_validade__lt=hoje,
        ).count()
        if trein_vencidos:
            alertas.append(_alerta("SST", "alerta",
                f"{trein_vencidos} treinamento(s) NR vencido(s)",
                "Funcionários com treinamentos expirados estão em não-conformidade.",
                "/sst/treinamentos/"))

        # PGR/PCMSO vencido ou vencendo — exigência da NR-1 (PGR) e NR-7 (PCMSO)
        for tipo, label in (("PGR", "PGR"), ("PCMSO", "PCMSO")):
            doc = DocumentoSST.objects.filter(empresa=empresa, tipo=tipo).order_by("-data_emissao").first()
            if not doc or not doc.data_validade:
                alertas.append(_alerta("SST", "critico",
                    f"{label} não gerado",
                    f"Nenhum {label} encontrado para esta empresa. Documento obrigatório por norma.",
                    "/sst/pgr/"))
            elif doc.data_validade < hoje:
                alertas.append(_alerta("SST", "critico",
                    f"{label} vencido",
                    f"O {label} venceu em {doc.data_validade.strftime('%d/%m/%Y')} e precisa ser revisado e reemitido.",
                    "/sst/pgr/"))
            elif doc.data_validade <= urgente:
                alertas.append(_alerta("SST", "critico",
                    f"{label} vencendo em até 7 dias",
                    f"Revise e reemita o {label} antes de {doc.data_validade.strftime('%d/%m/%Y')}.",
                    "/sst/pgr/"))
            elif doc.data_validade <= atencao:
                alertas.append(_alerta("SST", "alerta",
                    f"{label} vencendo em até 30 dias",
                    f"Planeje a revisão do {label}, válido até {doc.data_validade.strftime('%d/%m/%Y')}.",
                    "/sst/pgr/"))

        # Agendamentos atrasados
        ag_atrasados = AgendamentoSST.objects.filter(
            empresa=empresa,
            status__in=["agendado", "confirmado"],
            data_hora__date__lt=hoje,
        ).count()
        if ag_atrasados:
            alertas.append(_alerta("SST", "critico",
                f"{ag_atrasados} agendamento(s) SST atrasado(s)",
                "Agendamentos passados ainda sem status de realização. Atualize.",
                "/sst/exames/agendar/"))

        # Afastamentos ativos
        afastados = 0
        for f in funcionarios:
            if f.afastamentos.filter(data_retorno__isnull=True).exists():
                afastados += 1
        if afastados:
            alertas.append(_alerta("SST", "info",
                f"{afastados} funcionário(s) afastado(s)",
                "Funcionários em afastamento ativo — acompanhe o retorno.",
                "/sst/afastamentos/"))

    except Exception:
        pass
    return alertas


def _alertas_farmacia(empresa, hoje):
    alertas = []
    try:
        from .models import ItemFarmacia, PedidoCompraFarmacia

        # Estoque abaixo do mínimo
        abaixo = ItemFarmacia.objects.filter(empresa=empresa, ativo=True).values_list(
            "nome", "estoque_atual", "estoque_minimo"
        )
        criticos_f = [(n, a, m) for n, a, m in abaixo if m and a <= 0]
        alerta_f   = [(n, a, m) for n, a, m in abaixo if m and 0 < a <= m]

        if criticos_f:
            alertas.append(_alerta("Farmácia", "critico",
                f"{len(criticos_f)} item(ns) com estoque ZERADO",
                "Itens sem estoque: " + ", ".join(n for n,_,_ in criticos_f[:5]) + ("…" if len(criticos_f)>5 else ""),
                "/farmacia/gestao/"))
        if alerta_f:
            alertas.append(_alerta("Farmácia", "alerta",
                f"{len(alerta_f)} item(ns) abaixo do estoque mínimo",
                "Repor: " + ", ".join(n for n,_,_ in alerta_f[:5]) + ("…" if len(alerta_f)>5 else ""),
                "/farmacia/gestao/"))

        # Pedidos abertos há mais de 15 dias
        limite = hoje - timedelta(days=15)
        pedidos_antigos = PedidoCompraFarmacia.objects.filter(
            empresa=empresa,
            status__in=["rascunho", "enviado", "aprovado"],
            criado_em__date__lt=limite,
        ).count()
        if pedidos_antigos:
            alertas.append(_alerta("Farmácia", "alerta",
                f"{pedidos_antigos} pedido(s) de compra sem movimentação há 15+ dias",
                "Pedidos parados podem indicar falha no processo de abastecimento.",
                "/farmacia/gestao/"))

    except Exception:
        pass
    return alertas


def _alertas_hospital(empresa, hoje):
    alertas = []
    try:
        from .models import LeitoHospital, InternacaoHospital, TriagemHospital, EvolucaoClinica

        # Leitos em manutenção há mais de 3 dias
        limite_manut = hoje - timedelta(days=3)
        leitos_manut = LeitoHospital.objects.filter(
            departamento__empresa=empresa,
            status="manutencao",
            atualizado_em__date__lt=limite_manut,
        ).count()
        if leitos_manut:
            alertas.append(_alerta("Hospital", "alerta",
                f"{leitos_manut} leito(s) em manutenção há 3+ dias",
                "Leitos indisponíveis reduzem a capacidade de atendimento.",
                "/hospital/gestao/"))

        # Internações ativas há mais de 30 dias sem evolução recente
        limite_evolucao = datetime.now() - timedelta(days=2)
        internacoes_ativas = InternacaoHospital.objects.filter(
            leito__departamento__empresa=empresa,
            status="ativo",
        ).prefetch_related("evolucoes")

        sem_evolucao = 0
        internacoes_longas = 0
        for internacao in internacoes_ativas:
            # Sem evolução nos últimos 2 dias
            ultima = internacao.evolucoes.order_by("-criado_em").first()
            if not ultima or ultima.criado_em < limite_evolucao:
                sem_evolucao += 1
            # Internações longas (>30 dias)
            if internacao.data_entrada and (hoje - internacao.data_entrada).days > 30:
                internacoes_longas += 1

        if sem_evolucao:
            alertas.append(_alerta("Hospital", "alerta",
                f"{sem_evolucao} paciente(s) sem evolução clínica há 48h",
                "Pacientes internados sem registro de evolução recente.",
                "/hospital/gestao/"))
        if internacoes_longas:
            alertas.append(_alerta("Hospital", "info",
                f"{internacoes_longas} internação(ões) com mais de 30 dias",
                "Pacientes de longa permanência — revisar plano terapêutico.",
                "/hospital/gestao/"))

        # Taxa de ocupação crítica (>90%)
        total_leitos = LeitoHospital.objects.filter(
            departamento__empresa=empresa
        ).count()
        ocupados = LeitoHospital.objects.filter(
            departamento__empresa=empresa, status="ocupado"
        ).count()
        if total_leitos > 0:
            taxa = ocupados / total_leitos * 100
            if taxa >= 90:
                alertas.append(_alerta("Hospital", "critico",
                    f"Taxa de ocupação crítica: {taxa:.0f}%",
                    f"{ocupados} de {total_leitos} leitos ocupados. Risco de superlotação.",
                    "/hospital/gestao/"))
            elif taxa >= 75:
                alertas.append(_alerta("Hospital", "alerta",
                    f"Alta ocupação hospitalar: {taxa:.0f}%",
                    f"{ocupados} de {total_leitos} leitos em uso. Monitorar capacidade.",
                    "/hospital/gestao/"))

    except Exception:
        pass
    return alertas


def _alertas_governo(empresa, hoje):
    alertas = []
    try:
        from .models import IndicadorSaudeGov, PlanoAcaoGov, OrcamentoSaudeGov

        # Indicadores fora da meta
        indicadores = IndicadorSaudeGov.objects.filter(empresa=empresa)
        fora_meta = []
        for ind in indicadores:
            if ind.meta is not None and ind.valor_atual is not None:
                if float(ind.valor_atual) < float(ind.meta):
                    fora_meta.append(ind.nome)

        if fora_meta:
            alertas.append(_alerta("Governo", "alerta",
                f"{len(fora_meta)} indicador(es) abaixo da meta",
                "Indicadores: " + ", ".join(fora_meta[:4]) + ("…" if len(fora_meta)>4 else ""),
                "/governo/gestao/"))

        # Planos de ação atrasados
        planos_atrasados = PlanoAcaoGov.objects.filter(
            empresa=empresa,
            status__in=["pendente", "em_andamento"],
            prazo__lt=hoje,
        ).count()
        if planos_atrasados:
            alertas.append(_alerta("Governo", "critico",
                f"{planos_atrasados} plano(s) de ação com prazo vencido",
                "Planos de ação governamental atrasados comprometem metas do programa.",
                "/governo/gestao/"))

        # Orçamento com execução > 90% no corrente ano
        try:
            orc = OrcamentoSaudeGov.objects.get(empresa=empresa, ano=hoje.year)
            if orc.orcamento_previsto and float(orc.orcamento_previsto) > 0:
                exec_pct = float(orc.orcamento_executado) / float(orc.orcamento_previsto) * 100
                if exec_pct >= 95:
                    alertas.append(_alerta("Governo", "critico",
                        f"Orçamento {hoje.year} quase esgotado: {exec_pct:.0f}% executado",
                        "O orçamento anual de saúde está próximo do limite. Revise as despesas.",
                        "/governo/gestao/"))
                elif exec_pct >= 80:
                    alertas.append(_alerta("Governo", "alerta",
                        f"Orçamento {hoje.year} com {exec_pct:.0f}% executado",
                        "Alto nível de execução orçamentária — planeje reajustes se necessário.",
                        "/governo/gestao/"))
        except OrcamentoSaudeGov.DoesNotExist:
            alertas.append(_alerta("Governo", "info",
                f"Orçamento {hoje.year} não cadastrado",
                "Cadastre o orçamento anual de saúde para acompanhamento.",
                "/governo/gestao/"))

    except Exception:
        pass
    return alertas


def api_alertas(request):
    """
    GET /api/alertas/
    Retorna todos os alertas ativos da empresa agrupados por módulo e severidade.
    Suporte: ?modulo=SST|Farmácia|Hospital|Governo&severidade=critico|alerta|info
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()

    todos = (
        (_alertas_sst(empresa, hoje) if empresa_tem_feature(empresa, "sst.alertas") else [])
        + _alertas_farmacia(empresa, hoje)
        + _alertas_hospital(empresa, hoje)
        + _alertas_governo(empresa, hoje)
    )

    # Filtros opcionais
    modulo_f    = request.GET.get("modulo")
    severidade_f = request.GET.get("severidade")
    if modulo_f:
        todos = [a for a in todos if a["modulo"] == modulo_f]
    if severidade_f:
        todos = [a for a in todos if a["severidade"] == severidade_f]

    # Ordenar: critico → alerta → info
    ordem = {"critico": 0, "alerta": 1, "info": 2}
    todos.sort(key=lambda a: ordem.get(a["severidade"], 9))

    # Resumo
    criticos = sum(1 for a in todos if a["severidade"] == "critico")
    alertas_  = sum(1 for a in todos if a["severidade"] == "alerta")
    infos     = sum(1 for a in todos if a["severidade"] == "info")

    return JsonResponse({
        "resumo": {
            "total": len(todos),
            "criticos": criticos,
            "alertas": alertas_,
            "infos": infos,
        },
        "alertas": todos,
    })


def alertas_page(request):
    from django.shortcuts import render
    return render(request, "alertas.html")
