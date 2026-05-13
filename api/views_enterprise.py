from datetime import timedelta

from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone

from .access_control import get_setor
from .models import (
    ASOOcupacional,
    AcaoCorporativa,
    AfastamentoSST,
    AgendamentoSST,
    CheckinDiarioCorporativo,
    CheckinSemanalCorporativo,
    ColaboradorAliasCorporativo,
    ConfiguracaoSST,
    DepartamentoHospital,
    DescarteItemFarmacia,
    Dispensacao,
    DispensacaoMedicamento,
    DocumentoSST,
    EmpresaSetor,
    EmpresaTurno,
    EmpresaUnidade,
    EstoqueMovimento,
    FornecedorFarmacia,
    FornecedorFarmaciaGestao,
    FuncionarioSST,
    InternacaoHospital,
    InventarioFarmacia,
    ItemFarmacia,
    LeitoHospital,
    LeitoHospitalar,
    LoteMedicamento,
    MedicamentoFarmacia,
    PacienteFarmacia,
    PacienteHospital,
    PacienteInternado,
    PedidoApoioCorporativo,
    PedidoCompraFarmacia,
    PedidoFarmacia,
    PrescricaoHospitalar,
    PrescricaoMedica,
    ProgramaCorporativo,
    ReceitaMedica,
    RegistroSintoma,
    TreinamentoNR,
    TriagemHospital,
    TriagemManchester,
    eSocialEventoSST,
)


SETOR_LABELS = {
    "empresa": "Saude Ocupacional / Empresa",
    "farmacia": "Farmacia",
    "hospital": "Hospital",
    "governo": "Governo",
    "rede": "Rede",
    "plano_saude": "Plano de Saude",
}


def _status(score):
    if score >= 80:
        return "operacional"
    if score >= 45:
        return "atencao"
    if score > 0:
        return "implantacao"
    return "sem_dados"


def _card(codigo, nome, score, metricas=None, riscos=None, proximas_acoes=None):
    metricas = metricas or {}
    riscos = riscos or []
    proximas_acoes = proximas_acoes or []
    return {
        "codigo": codigo,
        "nome": nome,
        "score": max(0, min(100, int(score))),
        "status": _status(score),
        "metricas": metricas,
        "riscos": riscos,
        "proximas_acoes": proximas_acoes,
    }


def _prioridade(titulo, severidade="media", acao="", modulo=""):
    return {
        "modulo": modulo,
        "titulo": titulo,
        "severidade": severidade,
        "acao": acao,
    }


def _media(cards):
    if not cards:
        return 0
    return round(sum(c["score"] for c in cards) / len(cards))


def _empresa_cards(empresa):
    hoje = timezone.localdate()
    proximos_60 = hoje + timedelta(days=60)

    unidades = EmpresaUnidade.objects.filter(empresa=empresa, ativo=True).count()
    setores = EmpresaSetor.objects.filter(empresa=empresa, ativo=True).count()
    turnos = EmpresaTurno.objects.filter(empresa=empresa, ativo=True).count()
    aliases = ColaboradorAliasCorporativo.objects.filter(empresa=empresa, ativo=True).count()
    base_score = 0
    base_score += 25 if unidades else 0
    base_score += 25 if setores else 0
    base_score += 20 if turnos else 0
    base_score += 30 if aliases else 0

    checkins_diarios = CheckinDiarioCorporativo.objects.filter(empresa=empresa).count()
    checkins_semanais = CheckinSemanalCorporativo.objects.filter(empresa=empresa).count()
    pedidos_abertos = PedidoApoioCorporativo.objects.filter(
        empresa=empresa,
        status__in=[
            PedidoApoioCorporativo.STATUS_NOVO,
            PedidoApoioCorporativo.STATUS_EM_ANALISE,
            PedidoApoioCorporativo.STATUS_ENCAMINHADO,
        ],
    ).count()
    escuta_score = 0
    escuta_score += 45 if checkins_diarios else 0
    escuta_score += 25 if checkins_semanais else 0
    escuta_score += 20 if pedidos_abertos else 0
    escuta_score += 10 if aliases else 0

    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
    asos_vencidos = ASOOcupacional.objects.filter(
        empresa=empresa, data_validade__lt=hoje
    ).count()
    asos_vencendo = ASOOcupacional.objects.filter(
        empresa=empresa, data_validade__range=(hoje, proximos_60)
    ).count()
    docs_obrigatorios = DocumentoSST.objects.filter(
        empresa=empresa, tipo__in=["PGR", "PCMSO"], status="vigente"
    ).values("tipo").distinct().count()
    treinamentos_pendentes = TreinamentoNR.objects.filter(
        empresa=empresa, status__in=["pendente", "vencido"]
    ).count()
    cfg_ok = ConfiguracaoSST.objects.filter(empresa=empresa).exists()
    sst_score = 0
    sst_score += 20 if funcionarios else 0
    sst_score += 25 if docs_obrigatorios >= 2 else docs_obrigatorios * 10
    sst_score += 20 if cfg_ok else 0
    sst_score += 20 if ASOOcupacional.objects.filter(empresa=empresa).exists() else 0
    sst_score += 15 if treinamentos_pendentes == 0 and funcionarios else 0
    if asos_vencidos:
        sst_score -= min(30, asos_vencidos * 5)

    esocial_erros = eSocialEventoSST.objects.filter(empresa=empresa, status="erro").count()
    esocial_pendentes = eSocialEventoSST.objects.filter(
        empresa=empresa, status__in=["pendente", "retificacao"]
    ).count()
    afastamentos_ativos = AfastamentoSST.objects.filter(empresa=empresa, status="ativo").count()
    agendamentos_abertos = AgendamentoSST.objects.filter(
        empresa=empresa, status__in=["agendado", "confirmado"]
    ).count()
    conformidade_score = 45 if eSocialEventoSST.objects.filter(empresa=empresa).exists() else 0
    conformidade_score += 20 if esocial_erros == 0 else 0
    conformidade_score += 15 if agendamentos_abertos else 0
    conformidade_score += 20 if afastamentos_ativos or funcionarios else 0
    conformidade_score -= min(25, esocial_erros * 10)

    programas = ProgramaCorporativo.objects.filter(empresa=empresa).count()
    acoes_abertas = AcaoCorporativa.objects.filter(
        empresa=empresa,
        status__in=[
            AcaoCorporativa.STATUS_ABERTA,
            AcaoCorporativa.STATUS_EM_ANDAMENTO,
        ],
    ).count()
    acoes_atrasadas = AcaoCorporativa.objects.filter(
        empresa=empresa,
        prazo__lt=hoje,
        status__in=[
            AcaoCorporativa.STATUS_ABERTA,
            AcaoCorporativa.STATUS_EM_ANDAMENTO,
        ],
    ).count()
    acao_score = 35 if programas else 0
    acao_score += 35 if acoes_abertas else 0
    acao_score += 30 if acoes_atrasadas == 0 and (programas or acoes_abertas) else 0
    acao_score -= min(30, acoes_atrasadas * 8)

    return [
        _card(
            "estrutura_pessoas",
            "Estrutura, unidades e pessoas",
            base_score,
            {"unidades": unidades, "setores": setores, "turnos": turnos, "colaboradores": aliases},
            proximas_acoes=["Cadastrar unidades, setores, turnos e colaboradores ativos."] if base_score < 80 else [],
        ),
        _card(
            "escuta_operacional",
            "Escuta operacional e apoio",
            escuta_score,
            {"checkins_diarios": checkins_diarios, "checkins_semanais": checkins_semanais, "pedidos_abertos": pedidos_abertos},
            riscos=[_prioridade("Pedidos de apoio aguardando tratativa", "media", "Triar fila e criar plano de acao.", "Empresa")] if pedidos_abertos else [],
            proximas_acoes=["Ativar check-ins e fluxo de apoio para deixar de ser apenas cadastro."] if escuta_score < 45 else [],
        ),
        _card(
            "sst_legal",
            "SST legal: PGR, PCMSO, ASO e treinamentos",
            sst_score,
            {"funcionarios": funcionarios, "documentos_obrigatorios_vigentes": docs_obrigatorios, "asos_vencidos": asos_vencidos, "asos_60_dias": asos_vencendo, "treinamentos_pendentes": treinamentos_pendentes},
            riscos=[
                r for r in [
                    _prioridade("ASOs vencidos detectados", "alta", "Convocar exames e regularizar ASO.", "SST") if asos_vencidos else None,
                    _prioridade("Treinamentos NR pendentes ou vencidos", "alta", "Planejar turma e registrar certificado.", "SST") if treinamentos_pendentes else None,
                    _prioridade("PGR/PCMSO nao estao ambos vigentes", "alta", "Publicar documentos obrigatorios vigentes.", "SST") if docs_obrigatorios < 2 else None,
                ] if r
            ],
        ),
        _card(
            "esocial_absenteismo",
            "eSocial, agenda e absenteismo",
            conformidade_score,
            {"eventos_erro": esocial_erros, "eventos_pendentes": esocial_pendentes, "afastamentos_ativos": afastamentos_ativos, "agendamentos_abertos": agendamentos_abertos},
            riscos=[_prioridade("Eventos SST com erro no eSocial", "alta", "Corrigir XML/retorno antes do vencimento legal.", "eSocial")] if esocial_erros else [],
        ),
        _card(
            "planos_acao",
            "Programas e planos de acao",
            acao_score,
            {"programas": programas, "acoes_abertas": acoes_abertas, "acoes_atrasadas": acoes_atrasadas},
            riscos=[_prioridade("Planos de acao atrasados", "media", "Repriorizar responsaveis e prazos.", "Gestao")] if acoes_atrasadas else [],
        ),
    ]


def _farmacia_cards(empresa):
    hoje = timezone.localdate()
    proximos_60 = hoje + timedelta(days=60)

    medicamentos = MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True)
    itens = ItemFarmacia.objects.filter(empresa=empresa, ativo=True)
    med_count = medicamentos.count()
    item_count = itens.count()
    estoque_critico = medicamentos.filter(quantidade_atual__lte=0).count()
    estoque_critico += medicamentos.filter(
        quantidade_minima__gt=0,
        quantidade_atual__gt=0,
        quantidade_atual__lte=F("quantidade_minima"),
    ).count()
    fornecedores = (
        FornecedorFarmaciaGestao.objects.filter(empresa=empresa, ativo=True).count()
        + FornecedorFarmacia.objects.filter(empresa=empresa, ativo=True).count()
    )
    estoque_score = 0
    estoque_score += 40 if med_count or item_count else 0
    estoque_score += 20 if fornecedores else 0
    estoque_score += 25 if EstoqueMovimento.objects.filter(empresa=empresa).exists() else 0
    estoque_score += 15 if estoque_critico == 0 and (med_count or item_count) else 0
    estoque_score -= min(30, estoque_critico * 5)

    dispensacoes = (
        Dispensacao.objects.filter(empresa=empresa).count()
        + DispensacaoMedicamento.objects.filter(empresa=empresa).count()
    )
    pacientes = PacienteFarmacia.objects.filter(empresa=empresa, ativo=True).count()
    receitas_pendentes = ReceitaMedica.objects.filter(empresa=empresa, status="pendente").count()
    assistencial_score = 0
    assistencial_score += 35 if pacientes else 0
    assistencial_score += 40 if dispensacoes else 0
    assistencial_score += 15 if ReceitaMedica.objects.filter(empresa=empresa).exists() else 0
    assistencial_score += 10 if receitas_pendentes == 0 and dispensacoes else 0

    lotes_vencidos = LoteMedicamento.objects.filter(empresa=empresa, data_validade__lt=hoje).count()
    lotes_vencendo = LoteMedicamento.objects.filter(
        empresa=empresa, data_validade__range=(hoje, proximos_60)
    ).count()
    descartes = DescarteItemFarmacia.objects.filter(empresa=empresa).count()
    inventarios_abertos = InventarioFarmacia.objects.filter(empresa=empresa, status="aberto").count()
    rastreio_score = 0
    rastreio_score += 45 if LoteMedicamento.objects.filter(empresa=empresa).exists() else 0
    rastreio_score += 20 if descartes else 0
    rastreio_score += 20 if InventarioFarmacia.objects.filter(empresa=empresa).exists() else 0
    rastreio_score += 15 if lotes_vencidos == 0 and lotes_vencendo == 0 and (med_count or item_count) else 0
    rastreio_score -= min(35, lotes_vencidos * 10)

    pedidos_abertos = (
        PedidoFarmacia.objects.filter(empresa=empresa).exclude(status__in=["recebido", "cancelado"]).count()
        + PedidoCompraFarmacia.objects.filter(empresa=empresa).exclude(status__in=["recebido", "cancelado"]).count()
    )
    compras_score = 35 if fornecedores else 0
    compras_score += 35 if pedidos_abertos else 0
    compras_score += 30 if estoque_critico == 0 and fornecedores else 0

    return [
        _card(
            "estoque_compras",
            "Estoque, fornecedores e compras",
            estoque_score,
            {"medicamentos": med_count, "itens": item_count, "fornecedores": fornecedores, "estoque_critico": estoque_critico},
            riscos=[_prioridade("Medicamentos em estoque critico", "alta", "Gerar pedido de compra e revisar minimo/maximo.", "Farmacia")] if estoque_critico else [],
        ),
        _card(
            "assistencia_farmaceutica",
            "Dispensacao e cuidado ao paciente",
            assistencial_score,
            {"pacientes": pacientes, "dispensacoes": dispensacoes, "receitas_pendentes": receitas_pendentes},
            proximas_acoes=["Ativar cadastro de pacientes, receitas e dispensacao assistida."] if assistencial_score < 45 else [],
        ),
        _card(
            "rastreabilidade_qualidade",
            "Lotes, validade e qualidade",
            rastreio_score,
            {"lotes_vencidos": lotes_vencidos, "lotes_60_dias": lotes_vencendo, "descartes": descartes, "inventarios_abertos": inventarios_abertos},
            riscos=[
                r for r in [
                    _prioridade("Lotes vencidos no estoque", "alta", "Bloquear dispensacao e registrar descarte.", "Qualidade") if lotes_vencidos else None,
                    _prioridade("Lotes vencendo em ate 60 dias", "media", "Aplicar FEFO e campanha de giro.", "Qualidade") if lotes_vencendo else None,
                ] if r
            ],
        ),
        _card(
            "suprimentos",
            "Suprimentos e ruptura",
            compras_score,
            {"pedidos_abertos": pedidos_abertos, "fornecedores": fornecedores, "estoque_critico": estoque_critico},
            proximas_acoes=["Conectar ruptura de estoque a pedidos automatizados por fornecedor."] if compras_score < 60 else [],
        ),
    ]


def _hospital_cards(empresa):
    hoje = timezone.localdate()
    departamentos = DepartamentoHospital.objects.filter(empresa=empresa, ativo=True).count()
    leitos_total = (
        LeitoHospital.objects.filter(empresa=empresa).count()
        + LeitoHospitalar.objects.filter(empresa=empresa).count()
    )
    leitos_ocupados = (
        LeitoHospital.objects.filter(empresa=empresa, status="ocupado").count()
        + LeitoHospitalar.objects.filter(empresa=empresa, status="ocupado").count()
    )
    ocupacao = round((leitos_ocupados / leitos_total) * 100) if leitos_total else 0
    leitos_score = 0
    leitos_score += 25 if departamentos else 0
    leitos_score += 35 if leitos_total else 0
    leitos_score += 25 if leitos_ocupados or leitos_total else 0
    leitos_score += 15 if ocupacao < 95 and leitos_total else 0
    if ocupacao >= 95:
        leitos_score -= 20

    pacientes = (
        PacienteHospital.objects.filter(empresa=empresa).count()
        + PacienteInternado.objects.filter(empresa=empresa).count()
    )
    triagens_hoje = (
        TriagemHospital.objects.filter(empresa=empresa, triado_em__date=hoje).count()
        + TriagemManchester.objects.filter(empresa=empresa, data_hora__date=hoje).count()
    )
    triagens_criticas = (
        TriagemHospital.objects.filter(empresa=empresa, prioridade__in=["vermelho", "laranja"]).count()
        + TriagemManchester.objects.filter(empresa=empresa, nivel__in=["vermelho", "laranja"], status__in=["aguardando", "em_atendimento"]).count()
    )
    porta_score = 30 if pacientes else 0
    porta_score += 45 if triagens_hoje else 0
    porta_score += 15 if triagens_criticas == 0 and pacientes else 0
    porta_score += 10 if TriagemManchester.objects.filter(empresa=empresa).exists() else 0

    internacoes_ativas = (
        InternacaoHospital.objects.filter(empresa=empresa, status="ativa").count()
        + PacienteInternado.objects.filter(empresa=empresa, status="internado").count()
    )
    prescricoes_ativas = (
        PrescricaoHospitalar.objects.filter(empresa=empresa, status="ativa").count()
        + PrescricaoMedica.objects.filter(internacao__empresa=empresa, status="ativa").count()
    )
    cuidado_score = 35 if internacoes_ativas else 0
    cuidado_score += 35 if prescricoes_ativas else 0
    cuidado_score += 20 if pacientes else 0
    cuidado_score += 10 if leitos_ocupados <= leitos_total and leitos_total else 0

    return [
        _card(
            "leitos_ocupacao",
            "Leitos, alas e ocupacao",
            leitos_score,
            {"departamentos": departamentos, "leitos_total": leitos_total, "leitos_ocupados": leitos_ocupados, "ocupacao_pct": ocupacao},
            riscos=[_prioridade("Ocupacao hospitalar acima de 95%", "alta", "Abrir plano de contingencia de leitos.", "Hospital")] if ocupacao >= 95 else [],
        ),
        _card(
            "porta_entrada",
            "Triagem e porta de entrada",
            porta_score,
            {"pacientes": pacientes, "triagens_hoje": triagens_hoje, "triagens_criticas": triagens_criticas},
            riscos=[_prioridade("Triagens vermelha/laranja aguardando", "alta", "Priorizar atendimento medico imediato.", "Hospital")] if triagens_criticas else [],
        ),
        _card(
            "internacao_prescricao",
            "Internacao, prescricao e continuidade do cuidado",
            cuidado_score,
            {"internacoes_ativas": internacoes_ativas, "prescricoes_ativas": prescricoes_ativas, "pacientes": pacientes},
            proximas_acoes=["Vincular internacao, leito e prescricao para rastrear cuidado completo."] if cuidado_score < 60 else [],
        ),
    ]


def _generic_cards(empresa):
    sinais = RegistroSintoma.objects.filter(empresa=empresa).count()
    return [
        _card(
            "inteligencia_sanitaria",
            "Inteligencia sanitaria e sinais populacionais",
            70 if sinais else 20,
            {"registros_epidemiologicos": sinais},
            proximas_acoes=["Conectar fontes operacionais para virar sala de decisao real."] if not sinais else [],
        )
    ]


def _cards_por_setor(empresa, setor):
    if setor == "farmacia":
        return _farmacia_cards(empresa)
    if setor == "hospital":
        return _hospital_cards(empresa)
    if setor == "empresa":
        return _empresa_cards(empresa)
    return _generic_cards(empresa)


def api_enterprise_command_center(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    setor = get_setor(empresa)
    cards = _cards_por_setor(empresa, setor)
    riscos = []
    proximas_acoes = []
    for card in cards:
        riscos.extend(card.get("riscos", []))
        proximas_acoes.extend(
            {
                "modulo": card["nome"],
                "acao": acao,
            }
            for acao in card.get("proximas_acoes", [])
        )

    score = _media(cards)
    return JsonResponse({
        "empresa": {"id": empresa.id, "nome": empresa.nome},
        "setor": setor,
        "setor_label": SETOR_LABELS.get(setor, setor.title()),
        "maturidade_operacional": {
            "score": score,
            "status": _status(score),
            "leitura": "gestao_real" if score >= 70 else "implantacao_incompleta",
        },
        "modulos": cards,
        "riscos_prioritarios": sorted(
            riscos,
            key=lambda item: {"alta": 0, "media": 1, "baixa": 2}.get(item["severidade"], 3),
        )[:8],
        "proximas_acoes": proximas_acoes[:8],
        "benchmark_base": [
            "integracao_operacional",
            "rastreabilidade",
            "indicadores_em_tempo_real",
            "automacao_de_fluxo",
            "conformidade_e_auditoria",
        ],
        "atualizado_em": timezone.now().isoformat(),
    })
