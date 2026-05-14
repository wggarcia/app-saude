from datetime import timedelta
import unicodedata

from django.db.models import F, Sum
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
    BeneficiarioPlano,
    GuiaAutorizacao,
    IndicadorSaudeGov,
    OrcamentoSaudeGov,
    PlanoAcaoGov,
    PlanoSaude,
    PedidoApoioCorporativo,
    PedidoCompraFarmacia,
    PedidoFarmacia,
    PrescricaoHospitalar,
    PrescricaoMedica,
    ProgramaCorporativo,
    ProgramaSaudeGov,
    ReceitaMedica,
    Rede,
    RegistroSintoma,
    TreinamentoNR,
    TriagemHospital,
    TriagemManchester,
    TransferenciaEstoque,
    UnidadeRede,
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


def _normalizar_nome_medicamento(valor):
    texto = str(valor or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.replace("/", " ").replace("-", " ").split())


def _nomes_prescritos(medicamentos):
    nomes = []
    if isinstance(medicamentos, dict):
        medicamentos = [medicamentos]
    if not isinstance(medicamentos, list):
        return nomes
    for item in medicamentos:
        if isinstance(item, str):
            nome = item
        elif isinstance(item, dict):
            nome = (
                item.get("nome")
                or item.get("medicamento")
                or item.get("descricao")
                or item.get("item")
                or item.get("principio_ativo")
            )
        else:
            nome = ""
        nome = _normalizar_nome_medicamento(nome)
        if nome:
            nomes.append(nome)
    return nomes


def _catalogo_estoque_medicamentos(empresa):
    catalogo = []
    for med in MedicamentoFarmacia.objects.filter(empresa=empresa, ativo=True):
        nomes = {
            _normalizar_nome_medicamento(med.nome),
            _normalizar_nome_medicamento(med.principio_ativo),
        }
        nomes.discard("")
        catalogo.append({
            "nomes": nomes,
            "critico": med.quantidade_atual <= 0 or (
                med.quantidade_minima > 0 and med.quantidade_atual <= med.quantidade_minima
            ),
            "especial": med.controlado or med.refrigerado,
        })
    for item in ItemFarmacia.objects.filter(empresa=empresa, ativo=True):
        nome = _normalizar_nome_medicamento(item.nome)
        if nome:
            catalogo.append({
                "nomes": {nome},
                "critico": item.estoque_atual <= 0 or (
                    item.estoque_minimo > 0 and item.estoque_atual <= item.estoque_minimo
                ),
                "especial": False,
            })
    return catalogo


def _encontrar_no_catalogo(nome_prescrito, catalogo):
    for item in catalogo:
        for nome_estoque in item["nomes"]:
            if nome_prescrito == nome_estoque or nome_prescrito in nome_estoque or nome_estoque in nome_prescrito:
                return item
    return None


def _card_circuito_medicamento(empresa):
    catalogo = _catalogo_estoque_medicamentos(empresa)
    prescritos = []

    prescricoes_hospitalares = PrescricaoHospitalar.objects.filter(
        empresa=empresa, status="ativa"
    ).only("medicamentos")
    for prescricao in prescricoes_hospitalares[:120]:
        prescritos.extend(_nomes_prescritos(prescricao.medicamentos))

    prescricoes_medicas = PrescricaoMedica.objects.filter(
        internacao__empresa=empresa, status="ativa"
    ).only("medicamento")
    for prescricao in prescricoes_medicas[:120]:
        nome = _normalizar_nome_medicamento(prescricao.medicamento)
        if nome:
            prescritos.append(nome)

    total_prescricoes = prescricoes_hospitalares.count() + prescricoes_medicas.count()
    prescritos_unicos = sorted(set(prescritos))
    sem_estoque = 0
    criticos = 0
    especiais = 0
    encontrados = 0

    for nome in prescritos_unicos:
        item = _encontrar_no_catalogo(nome, catalogo)
        if not item:
            sem_estoque += 1
            continue
        encontrados += 1
        if item["critico"]:
            criticos += 1
        if item["especial"]:
            especiais += 1

    score = 0
    score += 25 if catalogo else 0
    score += 25 if total_prescricoes else 0
    score += 30 if total_prescricoes and sem_estoque == 0 else 0
    score += 20 if total_prescricoes and criticos == 0 else 0
    score -= min(40, sem_estoque * 12)
    score -= min(25, criticos * 8)

    riscos = [
        r for r in [
            _prioridade(
                "Prescricoes com medicamento fora do estoque",
                "alta",
                "Vincular prescricao ao cadastro de estoque antes da dispensacao.",
                "Circuito de Medicamento",
            ) if sem_estoque else None,
            _prioridade(
                "Medicamento prescrito em estoque critico",
                "alta",
                "Gerar compra/transferencia e bloquear ruptura assistencial.",
                "Circuito de Medicamento",
            ) if criticos else None,
            _prioridade(
                "Medicamento controlado ou refrigerado exige dupla checagem",
                "media",
                "Confirmar lote, validade, armazenamento e responsavel.",
                "Seguranca Medicamentosa",
            ) if especiais else None,
        ] if r
    ]

    return _card(
        "circuito_fechado_medicamento",
        "Circuito fechado de medicamento",
        score,
        {
            "prescricoes_ativas": total_prescricoes,
            "itens_prescritos": len(prescritos_unicos),
            "itens_com_estoque": encontrados,
            "itens_sem_estoque": sem_estoque,
            "itens_criticos": criticos,
            "controlados_ou_refrigerados": especiais,
        },
        riscos=riscos,
        proximas_acoes=[
            "Conectar prescricao, estoque, lote e dispensacao para fechar o ciclo do medicamento."
        ] if score < 70 else [],
    )


def _sum_valor(qs):
    return float(qs.aggregate(total=Sum("valor_estimado"))["total"] or 0)


def _card_ciclo_receita(empresa, contexto="prestador"):
    if contexto == "operadora":
        guias = GuiaAutorizacao.objects.filter(plano__empresa=empresa)
        nome = "Ciclo de receita, autorizacoes e glosas"
        modulo = "Plano de Saude"
    else:
        guias = GuiaAutorizacao.objects.filter(unidade__empresa=empresa)
        nome = "Receita assistencial e glosas"
        modulo = "Receita"

    limite_sla = timezone.now() - timedelta(hours=72)
    pendentes_qs = guias.filter(
        status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE]
    )
    pendentes_sla_qs = pendentes_qs.filter(solicitada_em__lt=limite_sla)

    total = guias.count()
    pendentes = pendentes_qs.count()
    pendentes_sla = pendentes_sla_qs.count()
    autorizadas_qs = guias.filter(status=GuiaAutorizacao.STATUS_AUTORIZADA)
    negadas_qs = guias.filter(status=GuiaAutorizacao.STATUS_NEGADA)
    autorizadas = autorizadas_qs.count()
    negadas = negadas_qs.count()
    valor_solicitado = _sum_valor(guias)
    valor_autorizado = _sum_valor(autorizadas_qs)
    valor_glosado = _sum_valor(negadas_qs)
    valor_pendente = _sum_valor(pendentes_qs)
    valor_sla_vencido = _sum_valor(pendentes_sla_qs)
    taxa_glosa = round((negadas / total) * 100, 1) if total else 0

    score = 0
    score += 25 if total else 0
    score += 25 if valor_solicitado > 0 else 0
    score += 25 if total and pendentes == 0 else 0
    score += 25 if total and taxa_glosa < 10 else 0
    score -= min(30, pendentes * 4)
    score -= min(35, pendentes_sla * 10)
    if taxa_glosa >= 20:
        score -= 25

    riscos = [
        r for r in [
            _prioridade(
                "Guias aguardando autorizacao",
                "media",
                "Atacar fila para reduzir atraso de atendimento e receita parada.",
                modulo,
            ) if pendentes else None,
            _prioridade(
                "SLA de autorizacao vencido",
                "alta",
                "Escalar guias acima de 72h para evitar perda assistencial e receita parada.",
                modulo,
            ) if pendentes_sla else None,
            _prioridade(
                "Taxa de glosa elevada",
                "alta",
                "Auditar motivo das negativas, documentos e regras contratuais.",
                modulo,
            ) if taxa_glosa >= 20 else None,
            _prioridade(
                "Valor glosado impactando receita",
                "alta",
                "Criar recurso de glosa e revisar elegibilidade antes da execucao.",
                modulo,
            ) if valor_glosado > 0 else None,
        ] if r
    ]

    return _card(
        "ciclo_receita_glosas",
        nome,
        score,
        {
            "guias_total": total,
            "guias_pendentes": pendentes,
            "guias_sla_vencido": pendentes_sla,
            "guias_autorizadas": autorizadas,
            "guias_negadas": negadas,
            "taxa_glosa_pct": taxa_glosa,
            "valor_solicitado": round(valor_solicitado, 2),
            "valor_autorizado": round(valor_autorizado, 2),
            "valor_glosado": round(valor_glosado, 2),
            "valor_pendente": round(valor_pendente, 2),
            "valor_sla_vencido": round(valor_sla_vencido, 2),
        },
        riscos=riscos,
        proximas_acoes=[
            "Conectar guia, autorizacao, execucao e recurso de glosa para fechar o ciclo financeiro."
        ] if score < 70 else [],
    )


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
        _card_circuito_medicamento(empresa),
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
        _card_ciclo_receita(empresa),
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

    triagens_abertas = TriagemManchester.objects.filter(
        empresa=empresa,
        status__in=["aguardando", "em_atendimento"],
    )
    alvos_manchester = {
        "vermelho": 0,
        "laranja": 10,
        "amarelo": 60,
        "verde": 120,
        "azul": 240,
    }
    sla_estourado = 0
    sla_critico = 0
    for triagem in triagens_abertas.only("nivel", "tempo_espera_minutos"):
        alvo = alvos_manchester.get(triagem.nivel, 120)
        if triagem.tempo_espera_minutos > alvo:
            sla_estourado += 1
            if triagem.nivel in ["vermelho", "laranja"]:
                sla_critico += 1
    sla_score = 30 if triagens_abertas.exists() else 0
    sla_score += 45 if sla_estourado == 0 and triagens_abertas.exists() else 0
    sla_score += 25 if sla_critico == 0 and triagens_abertas.exists() else 0
    sla_score -= min(40, sla_estourado * 8)
    sla_score -= min(30, sla_critico * 12)

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
        _card(
            "sla_manchester",
            "SLA Manchester e fila critica",
            sla_score,
            {"triagens_abertas": triagens_abertas.count(), "sla_estourado": sla_estourado, "sla_critico": sla_critico},
            riscos=[
                r for r in [
                    _prioridade(
                        "SLA Manchester estourado",
                        "alta",
                        "Reordenar fila por risco e acionar equipe assistencial.",
                        "Hospital",
                    ) if sla_estourado else None,
                    _prioridade(
                        "Paciente vermelho/laranja acima do alvo",
                        "alta",
                        "Atendimento imediato e registro de justificativa clinica.",
                        "Hospital",
                    ) if sla_critico else None,
                ] if r
            ],
            proximas_acoes=["Registrar Manchester com tempo de espera para controlar SLA clinico."] if sla_score < 45 else [],
        ),
        _card_circuito_medicamento(empresa),
        _card_ciclo_receita(empresa),
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


def _governo_cards(empresa):
    ano = timezone.localdate().year
    programas_ativos = ProgramaSaudeGov.objects.filter(empresa=empresa, status="ativo").count()
    programas_total = ProgramaSaudeGov.objects.filter(empresa=empresa).count()
    indicadores = IndicadorSaudeGov.objects.filter(empresa=empresa)
    indicadores_total = indicadores.count()
    metas_atingidas = 0
    for indicador in indicadores:
        if indicador.meta is not None and indicador.valor_atual is not None and indicador.valor_atual >= indicador.meta:
            metas_atingidas += 1
    planos_pendentes = PlanoAcaoGov.objects.filter(empresa=empresa, status="pendente").count()
    planos_andamento = PlanoAcaoGov.objects.filter(empresa=empresa, status="em_andamento").count()
    orcamento = OrcamentoSaudeGov.objects.filter(empresa=empresa, ano=ano).first()

    programas_score = 0
    programas_score += 45 if programas_ativos else 0
    programas_score += 30 if indicadores_total else 0
    programas_score += 25 if indicadores_total and metas_atingidas >= max(1, indicadores_total // 2) else 0

    execucao_pct = 0
    if orcamento and orcamento.total_previsto:
        execucao_pct = round((orcamento.total_executado / orcamento.total_previsto) * 100)
    orcamento_score = 0
    orcamento_score += 50 if orcamento else 0
    orcamento_score += 30 if 40 <= execucao_pct <= 100 else 0
    orcamento_score += 20 if execucao_pct <= 100 and orcamento else 0
    if execucao_pct > 100:
        orcamento_score -= 30

    acoes_score = 30 if planos_pendentes or planos_andamento else 0
    acoes_score += 45 if planos_andamento else 0
    acoes_score += 25 if planos_pendentes == 0 and (planos_andamento or programas_total) else 0

    sinais = RegistroSintoma.objects.filter(empresa=empresa).count()
    vigilancia_score = 60 if sinais else 20
    vigilancia_score += 20 if programas_ativos else 0
    vigilancia_score += 20 if indicadores_total else 0

    return [
        _card(
            "programas_indicadores",
            "Programas publicos e indicadores",
            programas_score,
            {"programas_total": programas_total, "programas_ativos": programas_ativos, "indicadores": indicadores_total, "metas_atingidas": metas_atingidas},
            proximas_acoes=["Cadastrar programas, indicadores e metas para sair de monitoramento passivo."] if programas_score < 50 else [],
        ),
        _card(
            "orcamento_saude",
            "Orcamento e execucao financeira",
            orcamento_score,
            {"ano": ano, "execucao_pct": execucao_pct},
            riscos=[_prioridade("Orcamento executado acima do previsto", "alta", "Revisar rubricas e aprovar suplementacao.", "Governo")] if execucao_pct > 100 else [],
            proximas_acoes=["Cadastrar orcamento anual para medir execucao real."] if not orcamento else [],
        ),
        _card(
            "planos_acao_gov",
            "Planos de acao intersetoriais",
            acoes_score,
            {"planos_pendentes": planos_pendentes, "planos_em_andamento": planos_andamento},
            riscos=[_prioridade("Planos pendentes aguardando dono", "media", "Atribuir responsavel e prazo.", "Governo")] if planos_pendentes else [],
        ),
        _card(
            "vigilancia_territorial",
            "Vigilancia e sinais territoriais",
            vigilancia_score,
            {"registros_epidemiologicos": sinais},
            proximas_acoes=["Conectar registros territoriais aos programas de resposta."] if sinais == 0 else [],
        ),
    ]


def _rede_cards(empresa):
    unidade = UnidadeRede.objects.filter(empresa=empresa).select_related("rede").first()
    rede = unidade.rede if unidade else None
    unidades = UnidadeRede.objects.filter(rede=rede, ativa=True).count() if rede else 0
    transferencias_abertas = TransferenciaEstoque.objects.filter(
        rede=rede,
        status__in=[
            TransferenciaEstoque.STATUS_PENDENTE,
            TransferenciaEstoque.STATUS_APROVADA,
            TransferenciaEstoque.STATUS_ENVIADA,
        ],
    ).count() if rede else 0
    urgentes = TransferenciaEstoque.objects.filter(rede=rede, urgente=True).exclude(
        status__in=[TransferenciaEstoque.STATUS_RECEBIDA, TransferenciaEstoque.STATUS_CANCELADA]
    ).count() if rede else 0

    estrutura_score = 0
    estrutura_score += 45 if rede else 0
    estrutura_score += 35 if unidades >= 2 else unidades * 15
    estrutura_score += 20 if unidade and unidade.codigo_unidade else 0

    fluxo_score = 30 if transferencias_abertas else 0
    fluxo_score += 35 if unidades >= 2 else 0
    fluxo_score += 20 if urgentes == 0 and rede else 0
    fluxo_score += 15 if rede else 0

    return [
        _card(
            "rede_unidades",
            "Rede, unidades e governanca",
            estrutura_score,
            {"rede": rede.nome if rede else "", "unidades_ativas": unidades},
            proximas_acoes=["Criar rede e vincular unidades para coordenar estoque e atendimento."] if not rede else [],
        ),
        _card(
            "transferencias_estoque",
            "Transferencias e apoio entre unidades",
            fluxo_score,
            {"transferencias_abertas": transferencias_abertas, "transferencias_urgentes": urgentes},
            riscos=[_prioridade("Transferencias urgentes em aberto", "alta", "Priorizar aprovacao e envio entre unidades.", "Rede")] if urgentes else [],
        ),
    ]


def _plano_saude_cards(empresa):
    planos = PlanoSaude.objects.filter(empresa=empresa)
    planos_ativos = planos.filter(status=PlanoSaude.STATUS_ATIVO).count()
    beneficiarios = BeneficiarioPlano.objects.filter(plano__empresa=empresa)
    beneficiarios_ativos = beneficiarios.filter(situacao=BeneficiarioPlano.SITUACAO_ATIVO).count()
    guias = GuiaAutorizacao.objects.filter(plano__empresa=empresa)
    guias_pendentes = guias.filter(status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE]).count()
    guias_negadas = guias.filter(status=GuiaAutorizacao.STATUS_NEGADA).count()

    carteira_score = 0
    carteira_score += 35 if planos_ativos else 0
    carteira_score += 40 if beneficiarios_ativos else 0
    carteira_score += 25 if planos_ativos and beneficiarios_ativos else 0

    autorizacao_score = 0
    autorizacao_score += 45 if guias.exists() else 0
    autorizacao_score += 30 if guias_pendentes == 0 and guias.exists() else 0
    autorizacao_score += 25 if guias_negadas == 0 and guias.exists() else 0
    autorizacao_score -= min(30, guias_pendentes * 5)

    return [
        _card(
            "carteira_beneficiarios",
            "Carteira e beneficiarios",
            carteira_score,
            {"planos_ativos": planos_ativos, "beneficiarios_ativos": beneficiarios_ativos},
            proximas_acoes=["Cadastrar planos e beneficiarios para habilitar gestao assistencial."] if carteira_score < 50 else [],
        ),
        _card(
            "guias_autorizacao",
            "Guias, autorizacoes e auditoria",
            autorizacao_score,
            {"guias_pendentes": guias_pendentes, "guias_negadas": guias_negadas},
            riscos=[_prioridade("Guias aguardando analise", "media", "Criar fila de autorizacao com SLA.", "Plano de Saude")] if guias_pendentes else [],
        ),
        _card_ciclo_receita(empresa, contexto="operadora"),
    ]


def _cards_por_setor(empresa, setor):
    if setor == "farmacia":
        return _farmacia_cards(empresa)
    if setor == "hospital":
        return _hospital_cards(empresa)
    if setor == "empresa":
        return _empresa_cards(empresa)
    if setor == "governo":
        return _governo_cards(empresa)
    if setor == "rede":
        return _rede_cards(empresa)
    if setor == "plano_saude":
        return _plano_saude_cards(empresa)
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
