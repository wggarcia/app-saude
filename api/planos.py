PACOTES_SAAS = {
    "empresa_starter_5": {
        "label": "Empresa Starter",
        "setor": "empresa",
        "descricao": "Saude ocupacional e radar territorial para pequenas equipes.",
        "usuarios": 5,
        "dispositivos": 5,
        "mensal": 799.00,
        "anual": 7990.00,
        "ciclos": ["mensal", "anual"],
    },
    "empresa_profissional_25": {
        "label": "Empresa Profissional",
        "setor": "empresa",
        "descricao": "Monitoramento B2B com dashboards, alertas e gestao de usuarios.",
        "usuarios": 25,
        "dispositivos": 25,
        "mensal": 1990.00,
        "anual": 19900.00,
        "ciclos": ["mensal", "anual"],
    },
    "empresa_enterprise_100": {
        "label": "Empresa Enterprise",
        "setor": "empresa",
        "descricao": "Operacao corporativa multiunidade com inteligencia epidemiologica.",
        "usuarios": 100,
        "dispositivos": 100,
        "mensal": 4900.00,
        "anual": 49000.00,
        "ciclos": ["mensal", "anual"],
    },
    "empresa_corporativo_250": {
        "label": "Empresa Corporativo",
        "setor": "empresa",
        "descricao": "Cobertura corporativa nacional com muitas unidades e governanca de acesso.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 9900.00,
        "anual": 99000.00,
        "ciclos": ["mensal", "anual"],
    },
    "empresa_nacional_500": {
        "label": "Empresa Nacional",
        "setor": "empresa",
        "descricao": "Radar nacional para grupos empresariais com operacao em varios estados.",
        "usuarios": 500,
        "dispositivos": 500,
        "mensal": 19900.00,
        "anual": 199000.00,
        "ciclos": ["mensal", "anual"],
    },
    "empresa_nacional_1000": {
        "label": "Empresa Nacional 1000",
        "setor": "empresa",
        "descricao": "Operacao enterprise ampliada com ate 1000 usuarios e maquinas autorizadas.",
        "usuarios": 1000,
        "dispositivos": 1000,
        "mensal": 35000.00,
        "anual": 350000.00,
        "ciclos": ["mensal", "anual"],
    },
    "farmacia_local": {
        "label": "Farmacia Local",
        "setor": "farmacia",
        "descricao": "Focos por bairro para abastecimento preventivo de prateleiras.",
        "usuarios": 5,
        "dispositivos": 5,
        "mensal": 699.00,
        "anual": 6990.00,
        "ciclos": ["mensal", "anual"],
    },
    "farmacia_rede_regional": {
        "label": "Rede Farmaceutica Regional",
        "setor": "farmacia",
        "descricao": "Inteligencia de demanda por regiao, sintomas e provaveis doencas.",
        "usuarios": 50,
        "dispositivos": 50,
        "mensal": 6000.00,
        "anual": 60000.00,
        "ciclos": ["mensal", "anual"],
    },
    "hospital_medio": {
        "label": "Hospital Medio",
        "setor": "hospital",
        "descricao": "Preparacao de pronto atendimento, leitos e pressao assistencial.",
        "usuarios": 50,
        "dispositivos": 50,
        "mensal": 12000.00,
        "anual": 120000.00,
        "ciclos": ["mensal", "anual"],
    },
    "hospital_rede": {
        "label": "Rede Hospitalar",
        "setor": "hospital",
        "descricao": "Sala de situacao para rede hospitalar com risco territorial e SRAG.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 60000.00,
        "anual": 600000.00,
        "ciclos": ["mensal", "anual"],
    },
    "governo_municipio_pequeno": {
        "label": "Governo Municipio Pequeno",
        "setor": "governo",
        "descricao": "Contrato anual fechado para vigilancia municipal e alertas oficiais.",
        "usuarios": 100,
        "dispositivos": 100,
        "mensal": 0.00,
        "anual": 120000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "ate 100 mil habitantes",
    },
    "governo_municipio_medio": {
        "label": "Governo Municipio Medio",
        "setor": "governo",
        "descricao": "Contrato anual fechado para centro municipal de inteligencia epidemiologica.",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 0.00,
        "anual": 360000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "100 mil a 800 mil habitantes",
    },
    "governo_capital_regiao": {
        "label": "Governo Capital / Regiao Metropolitana",
        "setor": "governo",
        "descricao": "Contrato anual fechado para sala de controle epidemiologica multi-regional.",
        "usuarios": 500,
        "dispositivos": 500,
        "mensal": 0.00,
        "anual": 1200000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "capitais e regioes metropolitanas",
    },
    "governo_estado": {
        "label": "Governo Estadual",
        "setor": "governo",
        "descricao": "Contrato anual fechado para vigilancia estadual integrada e governanca institucional.",
        "usuarios": 1000,
        "dispositivos": 1000,
        "mensal": 0.00,
        "anual": 3600000.00,
        "ciclos": ["anual"],
        "populacao_cobertura": "cobertura estadual",
    },
}

LEGACY_PACOTE_MAP = {
    "starter_5": "empresa_starter_5",
    "growth_10": "empresa_profissional_25",
    "scale_25": "empresa_profissional_25",
    "pro_50": "farmacia_rede_regional",
    "enterprise_100": "empresa_enterprise_100",
    "network_250": "empresa_corporativo_250",
    "grid_500": "empresa_nacional_500",
    "national_1000": "empresa_nacional_1000",
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
