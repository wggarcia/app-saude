PACOTES_SAAS = {
    "starter_5": {
        "label": "Starter 5",
        "usuarios": 5,
        "dispositivos": 5,
        "mensal": 299.90,
        "anual": 2999.00,
    },
    "growth_10": {
        "label": "Growth 10",
        "usuarios": 10,
        "dispositivos": 10,
        "mensal": 499.90,
        "anual": 4999.00,
    },
    "scale_25": {
        "label": "Scale 25",
        "usuarios": 25,
        "dispositivos": 25,
        "mensal": 999.90,
        "anual": 9999.00,
    },
    "pro_50": {
        "label": "Pro 50",
        "usuarios": 50,
        "dispositivos": 50,
        "mensal": 1799.90,
        "anual": 17999.00,
    },
    "enterprise_100": {
        "label": "Enterprise 100",
        "usuarios": 100,
        "dispositivos": 100,
        "mensal": 3199.90,
        "anual": 31999.00,
    },
    "network_250": {
        "label": "Network 250",
        "usuarios": 250,
        "dispositivos": 250,
        "mensal": 6799.90,
        "anual": 67999.00,
    },
    "grid_500": {
        "label": "Grid 500",
        "usuarios": 500,
        "dispositivos": 500,
        "mensal": 11999.90,
        "anual": 119999.00,
    },
    "national_1000": {
        "label": "National 1000",
        "usuarios": 1000,
        "dispositivos": 1000,
        "mensal": 19999.90,
        "anual": 199999.00,
    },
}


def pacote_padrao():
    return "starter_5"


def detalhes_pacote(codigo):
    return PACOTES_SAAS.get(codigo or pacote_padrao(), PACOTES_SAAS[pacote_padrao()])


def preco_pacote(codigo, ciclo):
    pacote = detalhes_pacote(codigo)
    return pacote["anual"] if ciclo == "anual" else pacote["mensal"]
