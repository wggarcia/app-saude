# ─── Feature sets por segmento ─────────────────────────────────────────────────
# Cada feature identifica uma capacidade do produto que pode ser habilitada ou
# bloqueada por plano. O formato é "segmento.funcionalidade".
#
# Regra geral: planos superiores incluem todas as features dos inferiores.
# Limites (max_usuarios, max_unidades, etc.) são verificados separadamente.
#
# Para adicionar um novo gate numa view:
#   from .access_control import api_requer_feature
#   @api_requer_feature("segmento.funcionalidade")
#   def minha_view(request): ...

# ── SST / Empresa ────────────────────────────────────────────────────────────
_SST_BASE = [
    "sst.aso",              # ASO — Atestado de Saúde Ocupacional
    "sst.epi",              # Controle de EPIs
    "sst.treinamentos",     # Treinamentos NR básicos
    "sst.dashboard",        # Dashboard SST
    "sst.relatorios",       # Relatórios básicos exportáveis
    "sst.funcionarios",     # Cadastro de funcionários
    "sst.esocial",          # eSocial S-2220, S-2240, S-2245 (disponível desde Starter)
    "sst.psicossocial",     # Avaliação Psicossocial NR-01 (liberado para todos os planos SST)
]
_SST_PROFISSIONAL = _SST_BASE + [
    "sst.afastamentos",     # Gestão de afastamentos
    "sst.agenda_medica",    # Agenda médica e exames
    "sst.painel_rh",        # Painel de RH
    "sst.alertas",          # Alertas automáticos de prazo
    "sst.cipa",             # CIPA — Comissão Interna de Prevenção de Acidentes
    "sst.biometria",        # Biometria Facial para confirmação de entrega de EPI
    "sst.pgr_ppra",         # PGR / PPRA / PCMSO automático
]
_SST_ENTERPRISE = _SST_PROFISSIONAL + [
    "sst.multi_unidade",    # Múltiplas unidades/filiais
    "sst.laudos_tecnicos",  # Laudos técnicos (LTCat, LTIP)
    "sst.rbac",             # Governança RBAC de usuários
    "sst.assistente_ia",    # Assistente IA (RAG) — perguntas em linguagem natural
]
_SST_CORPORATIVO = _SST_ENTERPRISE + [
    "sst.turnos",                   # Gestão de turnos
    "sst.relatorio_consolidado",    # Relatórios consolidados multi-unidade
]
_SST_NACIONAL = _SST_CORPORATIVO + [
    "sst.benchmarking",     # Benchmarking entre unidades
    "sst.multi_estado",     # Presença multi-estado/regional
]

# ── Farmácia ─────────────────────────────────────────────────────────────────
_FARMACIA_LOCAL = [
    "farmacia.estoque",             # Controle de estoque
    "farmacia.dispensacoes",        # Dispensações com rastreabilidade de lote
    "farmacia.controlados",         # Registro conforme Portaria ANVISA 344
    "farmacia.lotes",               # Alertas de vencimento de lotes
    "farmacia.pedidos",             # Pedidos de compra integrados
    "farmacia.epidemiologia",       # Alertas epidemiológicos regionais (App Cidadão)
    "farmacia.pdv",                 # PDV / Caixa com TEF, Pix, Convênio
    "farmacia.pbm",                 # PBM (convênios de medicamentos)
    "farmacia.farmacia_popular",    # Farmácia Popular (convênio governo)
    "farmacia.dre",                 # DRE / DFC / Conciliação financeira
    "farmacia.delivery",            # E-commerce / Delivery integrado
]
_FARMACIA_REDE = _FARMACIA_LOCAL + [
    "farmacia.multi_unidade",       # Visão consolidada multi-unidade (EXCLUSIVO REDE)
    "farmacia.painel_central",      # Painel central de rede (EXCLUSIVO REDE)
    "farmacia.transferencias",      # Transferências de estoque entre filiais (EXCLUSIVO REDE)
    "farmacia.rastreabilidade_rede",# Rastreabilidade de lote por unidade (EXCLUSIVO REDE)
]

# ── Hospital ─────────────────────────────────────────────────────────────────
_HOSPITAL_MEDIO = [
    "hospital.leitos",              # Painel de leitos em tempo real
    "hospital.internacoes",         # Internações ativas e altas
    "hospital.triagem",             # Triagem Manchester digitalizada
    "hospital.taxa_ocupacao",       # Taxa de ocupação por departamento
    "hospital.epidemiologia",       # Alertas epidemiológicos (App Cidadão)
    "hospital.emr",                 # Prontuário Eletrônico (EMR)
]
_HOSPITAL_REDE = _HOSPITAL_MEDIO + [
    "hospital.lis",                 # Laboratório integrado (LIS) — EXCLUSIVO REDE/GRUPO
    "hospital.ris_pacs",            # Imagem médica RIS/PACS — EXCLUSIVO REDE/GRUPO
    "hospital.cirurgia",            # Bloco cirúrgico — EXCLUSIVO REDE/GRUPO
    "hospital.farmacia_hospitalar", # Farmácia hospitalar — EXCLUSIVO REDE/GRUPO
    "hospital.tiss",                # Faturamento SUS/TISS — EXCLUSIVO REDE/GRUPO
    "hospital.ia_autorizacao",      # IA para autorização clínica — EXCLUSIVO REDE/GRUPO
    "hospital.multi_unidade",       # Gestão multi-unidade (EXCLUSIVO REDE/GRUPO)
    "hospital.benchmarking",        # Benchmarking entre unidades (EXCLUSIVO REDE/GRUPO)
    "hospital.painel_executivo",    # Painel executivo consolidado de rede (EXCLUSIVO REDE/GRUPO)
]

# ── Governo ──────────────────────────────────────────────────────────────────
# Todos os planos de governo têm o mesmo conjunto de features.
# Diferenças são apenas de escala (usuarios, municipios).
_GOVERNO_TODOS = [
    "governo.programas",        # Programas de saúde
    "governo.indicadores",      # Indicadores com meta × resultado
    "governo.planos_acao",      # Planos de ação com responsável e prazo
    "governo.orcamento",        # Orçamento previsto × executado
    "governo.sala_situacao",    # Sala de Situação Epidemiológica
    "governo.app_cidadao",      # App Cidadão — envio exclusivo de alertas à população
    "governo.pec",              # Prontuário Eletrônico do Cidadão (PEC)
    "governo.esus_rnds",        # Integração e-SUS / RNDS
    "governo.faturamento_sus",  # Faturamento SUS (APAC / AIH / BPA)
    "governo.farmacia_basica",  # Farmácia Básica UBS / RENAME
    "governo.regulacao",        # Regulação Assistencial (SISREG)
    "governo.teleconsulta",     # Teleconsulta para cidadão
    "governo.rag_rdqa",         # Relatórios RAG / RDQA / PAS
]

# ── Plano de Saúde ───────────────────────────────────────────────────────────
_PLANO_OPERADORA = [
    "plano.beneficiarios",      # Gestão de beneficiários
    "plano.guias",              # Guias de autorização com prazo ANS
    "plano.sinistros",          # Sinistros — abertura, análise, encerramento
    "plano.reembolsos",         # Reembolsos com prazo ANS rastreado
    "plano.contratos",          # Contratos com histórico de utilização
    "plano.ans_relatorios",     # Relatórios ANS-compatíveis
    "plano.epidemiologia",      # Alertas de risco territorial por município (App Cidadão)
    "plano.corretores",         # Gestão de corretoras e comissões
    "plano.rede_credenciada",   # Rede credenciada — gestão e negociação
    "plano.diops_sib",          # DIOPS + SIB (obrigações ANS)
    "plano.ia_autorizacao",     # IA para autorização de guias
    "plano.portal_beneficiario",# Portal web do beneficiário
]
_PLANO_ENTERPRISE = _PLANO_OPERADORA + [
    "plano.coparticipacao",         # Regras de coparticipação por contrato (EXCLUSIVO ENTERPRISE)
    "plano.faturamento",            # Faturamento integrado (EXCLUSIVO ENTERPRISE)
    "plano.sinistralidade_avancada",# Sinistralidade por segmento/produto (EXCLUSIVO ENTERPRISE)
    "plano.api_integracao",         # API de integração com sistemas legados (EXCLUSIVO ENTERPRISE)
]

# ── Rede de Saúde (setor independente) ──────────────────────────────────────
_REDE_TODOS = [
    "rede.multi_unidade",
    "rede.benchmarking",
    "rede.kpis_consolidados",
    "rede.transferencias",
    "rede.sala_situacao",
]

# ─── Definição dos planos ────────────────────────────────────────────────────

PACOTES_SAAS = {
    # ── SST / Empresa ──────────────────────────────────────────────────────────
    "empresa_starter_5": {
        "label": "Empresa Starter",
        "setor": "empresa",
        "descricao": "Compliance SST para pequenas empresas: ASOs, EPIs, treinamentos NR e avaliacao psicossocial NR-01.",
        "usuarios": 5,
        "dispositivos": 5,
        "mensal": 990.00,
        "anual": 9900.00,
        "ciclos": ["mensal", "anual"],
        "features": _SST_BASE,
        "limites": {"max_usuarios": 5, "max_funcionarios": 50, "max_unidades": 1},
    },
    "empresa_profissional_25": {
        "label": "Empresa Profissional",
        "setor": "empresa",
        "descricao": "Gestao SST profissional com painel RH, afastamentos, agenda medica, alertas e biometria facial.",
        "usuarios": 25,
        "dispositivos": 25,
        "mensal": 2490.00,
        "anual": 24900.00,
        "ciclos": ["mensal", "anual"],
        "features": _SST_PROFISSIONAL,
        "limites": {"max_usuarios": 25, "max_funcionarios": 250, "max_unidades": 1},
    },
    "empresa_enterprise_100": {
        "label": "Empresa Enterprise",
        "setor": "empresa",
        "descricao": "SST corporativo multiunidade com eSocial, conformidade NR, laudos tecnicos e governanca de acesso.",
        "usuarios": 100,
        "dispositivos": 100,
        "mensal": 7990.00,
        "anual": 79900.00,
        "ciclos": ["mensal", "anual"],
        "features": _SST_ENTERPRISE,
        "limites": {"max_usuarios": 100, "max_funcionarios": 1000, "max_unidades": 5},
    },
    "empresa_corporativo_250": {
        "label": "Empresa Corporativo",
        "setor": "empresa",
        "descricao": "SST para grandes grupos: multiplas unidades, turnos, setores e relatorios consolidados.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 14900.00,
        "anual": 149000.00,
        "ciclos": ["mensal", "anual"],
        "features": _SST_CORPORATIVO,
        "limites": {"max_usuarios": 250, "max_funcionarios": 5000, "max_unidades": 20},
    },
    "empresa_nacional_500": {
        "label": "Empresa Nacional",
        "setor": "empresa",
        "descricao": "Operacao SST nacional para grupos empresariais com presenca em varios estados.",
        "usuarios": 500,
        "dispositivos": 500,
        "mensal": 21900.00,
        "anual": 219000.00,
        "ciclos": ["mensal", "anual"],
        "features": _SST_NACIONAL,
        "limites": {"max_usuarios": 500, "max_funcionarios": 10000, "max_unidades": 50},
    },
    "empresa_nacional_1000": {
        "label": "Empresa Nacional 1000",
        "setor": "empresa",
        "descricao": "SST enterprise para grandes corporacoes com ate 1000 usuarios e governanca total.",
        "usuarios": 1000,
        "dispositivos": 1000,
        "mensal": 35900.00,
        "anual": 359000.00,
        "ciclos": ["mensal", "anual"],
        "features": _SST_NACIONAL,
        "limites": {"max_usuarios": 1000, "max_funcionarios": 999999, "max_unidades": 999},
    },
    # ── Farmácia ───────────────────────────────────────────────────────────────
    "farmacia_local": {
        "label": "Farmacia Local",
        "setor": "farmacia",
        "descricao": "Estoque, dispensacoes, PDV/TEF, PBM, Farmacia Popular, DRE e delivery integrado para farmacia local.",
        "usuarios": 5,
        "dispositivos": 5,
        "mensal": 799.00,
        "anual": 7990.00,
        "ciclos": ["mensal", "anual"],
        "features": _FARMACIA_LOCAL,
        "limites": {"max_usuarios": 5, "max_unidades": 1},
    },
    "farmacia_rede_regional": {
        "label": "Rede Farmaceutica Regional",
        "setor": "farmacia",
        "descricao": "Rastreabilidade de lotes, transferencias entre filiais, painel central e gestao de controlados por rede, para redes de até 25 unidades.",
        "usuarios": 50,
        "dispositivos": 50,
        "mensal": 4990.00,
        "anual": 49900.00,
        "ciclos": ["mensal", "anual"],
        "features": _FARMACIA_REDE,
        "limites": {"max_usuarios": 50, "max_unidades": 25},
    },
    "farmacia_rede_nacional": {
        "label": "Rede Farmaceutica Nacional",
        "setor": "farmacia",
        "descricao": "Tudo do Rede Regional, dimensionado para redes nacionais de até 100 unidades.",
        "usuarios": 200,
        "dispositivos": 200,
        "mensal": 17900.00,
        "anual": 179000.00,
        "ciclos": ["mensal", "anual"],
        "features": _FARMACIA_REDE,
        "limites": {"max_usuarios": 200, "max_unidades": 100},
    },
    # ── Hospital ───────────────────────────────────────────────────────────────
    "hospital_medio": {
        "label": "Hospital Medio",
        "setor": "hospital",
        "descricao": "Leitos, internacoes, triagem Manchester, taxa de ocupacao, epidemiologia e prontuario eletronico (EMR).",
        "usuarios": 50,
        "dispositivos": 50,
        "mensal": 9900.00,
        "anual": 99000.00,
        "ciclos": ["mensal", "anual"],
        "features": _HOSPITAL_MEDIO,
        "limites": {"max_usuarios": 50, "max_unidades": 1},
    },
    "hospital_rede": {
        "label": "Rede Hospitalar",
        "setor": "hospital",
        "descricao": "Tudo do Hospital Medio + LIS, RIS/PACS, bloco cirurgico, farmacia hospitalar, TISS, IA de autorizacao, gestao multi-unidade hospitalar, benchmarking e painel executivo.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 19900.00,
        "anual": 199000.00,
        "ciclos": ["mensal", "anual"],
        "features": _HOSPITAL_REDE,
        "limites": {"max_usuarios": 250, "max_unidades": 999},
    },
    "hospital_grupo": {
        "label": "Grupo Hospitalar",
        "setor": "hospital",
        "descricao": "Tudo do Rede Hospitalar, dimensionado para grupos com varios hospitais e maior volume de usuarios (600 usuarios).",
        "usuarios": 600,
        "dispositivos": 600,
        "mensal": 42900.00,
        "anual": 429000.00,
        "ciclos": ["mensal", "anual"],
        "features": _HOSPITAL_REDE,
        "limites": {"max_usuarios": 600, "max_unidades": 999},
    },
    # ── Governo (contratos anuais via licitação) ───────────────────────────────
    "governo_municipio_pequeno": {
        "label": "Governo Municipio Pequeno",
        "setor": "governo",
        "descricao": "Contratacao via licitacao publica. PEC, e-SUS/RNDS, faturamento SUS, farmacia basica, regulacao, teleconsulta e RAG. Proposta tecnica sob demanda.",
        "usuarios": 100,
        "dispositivos": 100,
        "mensal": 0.00,
        "anual": 220000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "ate 100 mil habitantes",
        "features": _GOVERNO_TODOS,
        "limites": {"max_usuarios": 100, "max_municipios": 1},
    },
    "governo_municipio_medio": {
        "label": "Governo Municipio Medio",
        "setor": "governo",
        "descricao": "Contratacao via licitacao publica. Gestao municipal de saude com PEC, faturamento SUS, regulacao assistencial e relatorios RDQA. Proposta tecnica sob demanda.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 0.00,
        "anual": 516000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "100 mil a 800 mil habitantes",
        "features": _GOVERNO_TODOS,
        "limites": {"max_usuarios": 250, "max_municipios": 1},
    },
    "governo_capital_regiao": {
        "label": "Governo Capital / Regiao Metropolitana",
        "setor": "governo",
        "descricao": "Contratacao via licitacao publica. Gestao multi-regional de saude publica com PEC, sala de situacao e governanca orcamentaria. Proposta tecnica sob demanda.",
        "usuarios": 500,
        "dispositivos": 500,
        "mensal": 0.00,
        "anual": 1590000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "capitais e regioes metropolitanas",
        "features": _GOVERNO_TODOS,
        "limites": {"max_usuarios": 500, "max_municipios": 50},
    },
    "governo_estado": {
        "label": "Governo Estadual",
        "setor": "governo",
        "descricao": "Contratacao via licitacao publica. Gestao estadual integrada: PEC, e-SUS/RNDS, faturamento SUS, regulacao e governanca por municipio. Proposta tecnica sob demanda.",
        "usuarios": 1000,
        "dispositivos": 1000,
        "mensal": 0.00,
        "anual": 5200000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "cobertura estadual",
        "features": _GOVERNO_TODOS,
        "limites": {"max_usuarios": 1000, "max_municipios": 999},
    },
    # ── Rede de Saúde ──────────────────────────────────────────────────────────
    "rede_regional": {
        "label": "Rede de Saúde Regional",
        "setor": "rede",
        "descricao": "Gestao multi-unidades com benchmarking, consolidacao de KPIs, transferencias e mapa de rede.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 9900.00,
        "anual": 99000.00,
        "ciclos": ["mensal", "anual"],
        "features": _REDE_TODOS,
        "limites": {"max_usuarios": 250, "max_unidades": 50},
    },
    "rede_nacional": {
        "label": "Rede de Saúde Nacional",
        "setor": "rede",
        "descricao": "Operacao de rede nacional com governanca, analytics avancado e sala de situacao epidemiologica.",
        "usuarios": 1000,
        "dispositivos": 1000,
        "mensal": 25900.00,
        "anual": 259000.00,
        "ciclos": ["mensal", "anual"],
        "features": _REDE_TODOS,
        "limites": {"max_usuarios": 1000, "max_unidades": 999},
    },
    # ── Plano de Saúde ─────────────────────────────────────────────────────────
    "plano_saude_operadora": {
        "label": "Operadora de Plano de Saúde",
        "setor": "plano_saude",
        "descricao": "Beneficiarios, guias ANS, sinistros, reembolsos, corretoras, rede credenciada, DIOPS/SIB, IA para autorizacao e portal do beneficiario.",
        "usuarios": 100,
        "dispositivos": 100,
        "mensal": 14900.00,
        "anual": 149000.00,
        "ciclos": ["mensal", "anual"],
        "features": _PLANO_OPERADORA,
        "limites": {"max_usuarios": 100},
    },
    "plano_saude_enterprise": {
        "label": "Operadora Enterprise",
        "setor": "plano_saude",
        "descricao": "Plataforma enterprise para grandes operadoras: coparticipacao, faturamento, sinistralidade avancada e integracao via API com sistemas legados.",
        "usuarios": 500,
        "dispositivos": 500,
        "mensal": 29900.00,
        "anual": 299000.00,
        "ciclos": ["mensal", "anual"],
        "features": _PLANO_ENTERPRISE,
        "limites": {"max_usuarios": 500},
    },
}

LEGACY_PACOTE_MAP = {
    # codes from before the new naming scheme (v1 era)
    "starter_5": "empresa_starter_5",
    "growth_10": "empresa_profissional_25",
    "scale_25": "empresa_profissional_25",
    # Demo SST legacy code kept by older bootstrap scripts.
    "sst_enterprise_10": "empresa_nacional_1000",
    "pro_50": "farmacia_rede_regional",
    "enterprise_100": "empresa_enterprise_100",
    "network_250": "empresa_corporativo_250",
    "grid_500": "empresa_nacional_500",
    "national_1000": "empresa_nacional_1000",
    # short-name legacy codes present in production DB
    "basico": "empresa_starter_5",
    "profissional": "empresa_profissional_25",
    "enterprise": "empresa_enterprise_100",
    "hospital": "hospital_medio",
    "governo": "governo_municipio_pequeno",
    "farmacia": "farmacia_local",
    "rede": "rede_regional",
    "plano_saude": "plano_saude_operadora",
}


def pacote_padrao():
    return "empresa_starter_5"


def pacote_governo_padrao():
    return "governo_estado"


def normalizar_codigo_pacote(codigo):
    return LEGACY_PACOTE_MAP.get(codigo or "", codigo or pacote_padrao())


def detalhes_pacote(codigo):
    codigo_normalizado = normalizar_codigo_pacote(codigo)
    return PACOTES_SAAS.get(codigo_normalizado, PACOTES_SAAS[pacote_padrao()])


def ciclo_padrao_pacote(codigo):
    pacote = detalhes_pacote(codigo)
    return "anual" if pacote["ciclos"] == ["anual"] else "mensal"


def normalizar_ciclo(codigo, ciclo):
    pacote = detalhes_pacote(codigo)
    ciclo = ciclo or ciclo_padrao_pacote(codigo)
    return ciclo if ciclo in pacote["ciclos"] else ciclo_padrao_pacote(codigo)


def preco_pacote(codigo, ciclo=None):
    pacote = detalhes_pacote(codigo)
    ciclo = normalizar_ciclo(codigo, ciclo)
    return pacote["anual"] if ciclo == "anual" else pacote["mensal"]


def pacotes_por_setor(setor=None, incluir_governo=False):
    itens = {
        codigo: pacote
        for codigo, pacote in PACOTES_SAAS.items()
        if (not setor or pacote["setor"] == setor)
    }
    if not incluir_governo:
        itens = {codigo: pacote for codigo, pacote in itens.items() if pacote["setor"] != "governo"}
    return itens
