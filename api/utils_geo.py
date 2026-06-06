import requests
from math import cos, radians, sqrt


# ── Mapa de referência abrangente do Brasil ────────────────────────────────
# Cobertura: todas as capitais + principais cidades + bairros do RJ e SP
# Garante que o fallback local seja preciso mesmo sem Nominatim
KNOWN_BRAZIL_POINTS = [
    # ── RIO DE JANEIRO — bairros e municípios ──────────────────────────────
    (-22.9711, -43.1835, "Copacabana",        "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9839, -43.1970, "Ipanema",           "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9842, -43.2247, "Leblon",            "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9519, -43.1869, "Botafogo",          "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9425, -43.1739, "Flamengo",          "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9068, -43.1729, "Centro",            "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9218, -43.2358, "Tijuca",            "Rio de Janeiro", "Rio de Janeiro"),
    (-22.8981, -43.2797, "Méier",             "Rio de Janeiro", "Rio de Janeiro"),
    (-22.8762, -43.3340, "Madureira",         "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9999, -43.3645, "Barra da Tijuca",   "Rio de Janeiro", "Rio de Janeiro"),
    (-22.8740, -43.4580, "Campo Grande",      "Rio de Janeiro", "Rio de Janeiro"),
    (-22.9273, -43.6819, "Santa Cruz",        "Rio de Janeiro", "Rio de Janeiro"),
    (-22.8650, -43.2980, "Engenho Novo",      "Rio de Janeiro", "Rio de Janeiro"),
    (-22.8560, -43.3450, "Realengo",          "Rio de Janeiro", "Rio de Janeiro"),
    (-23.0024, -43.3050, "Jacarepaguá",       "Rio de Janeiro", "Rio de Janeiro"),
    # Niterói
    (-22.8993, -43.1163, "Icaraí",            "Niterói",        "Rio de Janeiro"),
    (-22.8836, -43.1037, "Centro",            "Niterói",        "Rio de Janeiro"),
    (-22.8782, -43.0750, "Fonseca",           "Niterói",        "Rio de Janeiro"),
    # Municípios RJ
    (-22.7596, -43.4505, "Centro",            "Nova Iguaçu",    "Rio de Janeiro"),
    (-22.7853, -43.3115, "Centro",            "Duque de Caxias","Rio de Janeiro"),
    (-22.8267, -43.0539, "Centro",            "São Gonçalo",    "Rio de Janeiro"),
    (-22.5043, -43.1820, "Centro",            "Petrópolis",     "Rio de Janeiro"),
    (-22.5233, -44.1044, "Centro",            "Volta Redonda",  "Rio de Janeiro"),
    (-21.7542, -41.3244, "Centro",            "Campos dos Goytacazes", "Rio de Janeiro"),
    (-22.9682, -44.3178, "Centro",            "Angra dos Reis", "Rio de Janeiro"),
    (-22.4018, -42.9829, "Centro",            "Nova Friburgo",  "Rio de Janeiro"),
    (-22.5178, -43.8782, "Centro",            "Barra do Piraí", "Rio de Janeiro"),

    # ── SÃO PAULO — capital e municípios ──────────────────────────────────
    (-23.5505, -46.6333, "Centro",            "São Paulo",      "São Paulo"),
    (-23.5629, -46.6898, "Pinheiros",         "São Paulo",      "São Paulo"),
    (-23.4948, -46.6387, "Santana",           "São Paulo",      "São Paulo"),
    (-23.5947, -46.6878, "Vila Mariana",      "São Paulo",      "São Paulo"),
    (-23.6082, -46.6977, "Santo André",       "Santo André",    "São Paulo"),
    (-23.5440, -46.4422, "Centro",            "Guarulhos",      "São Paulo"),
    (-23.6614, -46.5392, "Centro",            "São Bernardo do Campo", "São Paulo"),
    (-22.9058, -47.0609, "Centro",            "Campinas",       "São Paulo"),
    (-21.1775, -47.8103, "Centro",            "Ribeirão Preto", "São Paulo"),
    (-23.1896, -45.8841, "Centro",            "São José dos Campos", "São Paulo"),
    (-23.5015, -47.4526, "Centro",            "Sorocaba",       "São Paulo"),
    (-22.8956, -48.4457, "Centro",            "Bauru",          "São Paulo"),
    (-20.8197, -49.3795, "Centro",            "São José do Rio Preto", "São Paulo"),
    (-22.3154, -49.0595, "Centro",            "Marília",        "São Paulo"),
    (-21.7851, -48.5601, "Centro",            "Araraquara",     "São Paulo"),
    (-22.0169, -47.8908, "Centro",            "São Carlos",     "São Paulo"),
    (-23.9608, -46.3336, "Centro",            "Santos",         "São Paulo"),

    # ── MINAS GERAIS ──────────────────────────────────────────────────────
    (-19.9167, -43.9345, "Centro",            "Belo Horizonte", "Minas Gerais"),
    (-19.9385, -43.9385, "Savassi",           "Belo Horizonte", "Minas Gerais"),
    (-19.8945, -44.0178, "Contagem",          "Contagem",       "Minas Gerais"),
    (-18.9186, -48.2772, "Centro",            "Uberlândia",     "Minas Gerais"),
    (-21.7625, -43.3496, "Centro",            "Juiz de Fora",   "Minas Gerais"),
    (-19.4592, -44.1986, "Centro",            "Sete Lagoas",    "Minas Gerais"),
    (-16.7183, -43.8647, "Centro",            "Montes Claros",  "Minas Gerais"),
    (-22.4253, -45.9521, "Centro",            "Poços de Caldas","Minas Gerais"),

    # ── NORDESTE ──────────────────────────────────────────────────────────
    # Bahia
    (-12.9777, -38.5016, "Centro",            "Salvador",       "Bahia"),
    (-12.9718, -38.5102, "Pelourinho",        "Salvador",       "Bahia"),
    (-13.0176, -38.4826, "Barra",             "Salvador",       "Bahia"),
    (-12.2539, -38.9661, "Centro",            "Feira de Santana","Bahia"),
    (-14.8619, -40.8444, "Centro",            "Vitória da Conquista","Bahia"),
    (-10.9131, -37.0747, "Centro",            "Aracaju",        "Sergipe"),
    # Pernambuco
    (-8.0476,  -34.8770, "Boa Vista",         "Recife",         "Pernambuco"),
    (-8.1167,  -34.8993, "Boa Viagem",        "Recife",         "Pernambuco"),
    (-8.0522,  -34.9286, "Centro",            "Olinda",         "Pernambuco"),
    (-7.9172,  -38.3542, "Centro",            "Caruaru",        "Pernambuco"),
    # Ceará
    (-3.7319,  -38.5267, "Centro",            "Fortaleza",      "Ceará"),
    (-3.7327,  -38.5024, "Aldeota",           "Fortaleza",      "Ceará"),
    (-3.8754,  -38.4968, "Centro",            "Caucaia",        "Ceará"),
    # Paraíba
    (-7.1150,  -34.8633, "Centro",            "João Pessoa",    "Paraíba"),
    (-7.2306,  -35.8811, "Centro",            "Campina Grande", "Paraíba"),
    # Rio Grande do Norte
    (-5.7945,  -35.2110, "Centro",            "Natal",          "Rio Grande do Norte"),
    (-5.1944,  -37.3444, "Centro",            "Mossoró",        "Rio Grande do Norte"),
    # Maranhão
    (-2.5283,  -44.3068, "Centro",            "São Luís",       "Maranhão"),
    (-4.2500,  -42.3333, "Centro",            "Teresina",       "Piauí"),
    (-9.6658,  -35.7350, "Centro",            "Maceió",         "Alagoas"),

    # ── NORTE ─────────────────────────────────────────────────────────────
    (-3.1190,  -60.0217, "Centro",            "Manaus",         "Amazonas"),
    (-3.0560,  -60.0139, "Adrianópolis",      "Manaus",         "Amazonas"),
    (-1.4558,  -48.4902, "Campina",           "Belém",          "Pará"),
    (-1.4760,  -48.5044, "Marco",             "Belém",          "Pará"),
    (-8.7612,  -63.9004, "Centro",            "Porto Velho",    "Rondônia"),
    (-9.9749,  -67.8090, "Centro",            "Rio Branco",     "Acre"),
    (-2.5307,  -44.3068, "Centro",            "Imperatriz",     "Maranhão"),
    (-5.3683,  -49.1183, "Centro",            "Marabá",         "Pará"),
    (2.8235,   -60.6753, "Centro",            "Boa Vista",      "Roraima"),
    (-0.0349,  -51.0694, "Centro",            "Macapá",         "Amapá"),
    (-10.9195, -61.9565, "Centro",            "Ji-Paraná",      "Rondônia"),

    # ── CENTRO-OESTE ──────────────────────────────────────────────────────
    (-15.7939, -47.8828, "Asa Sul",           "Brasília",       "Distrito Federal"),
    (-15.8050, -47.8900, "Plano Piloto",      "Brasília",       "Distrito Federal"),
    (-16.6869, -49.2648, "Setor Central",     "Goiânia",        "Goiás"),
    (-16.7000, -49.2700, "Jardim Goiás",      "Goiânia",        "Goiás"),
    (-16.4600, -54.6278, "Centro",            "Rondonópolis",   "Mato Grosso"),
    (-15.5961, -56.0967, "Centro",            "Cuiabá",         "Mato Grosso"),
    (-20.4428, -54.6460, "Centro",            "Campo Grande",   "Mato Grosso do Sul"),
    (-22.2290, -54.8083, "Centro",            "Dourados",       "Mato Grosso do Sul"),
    (-18.0122, -47.7963, "Centro",            "Uberlândia",     "Goiás"),
    (-17.3294, -48.2832, "Centro",            "Anápolis",       "Goiás"),

    # ── SUL ───────────────────────────────────────────────────────────────
    (-25.4284, -49.2733, "Centro",            "Curitiba",       "Paraná"),
    (-25.4380, -49.2700, "Batel",             "Curitiba",       "Paraná"),
    (-23.3045, -51.1696, "Centro",            "Londrina",       "Paraná"),
    (-23.4273, -51.9375, "Centro",            "Maringá",        "Paraná"),
    (-25.5163, -54.5854, "Centro",            "Foz do Iguaçu",  "Paraná"),
    (-27.5954, -48.5480, "Centro",            "Florianópolis",  "Santa Catarina"),
    (-26.9194, -49.0661, "Centro",            "Blumenau",       "Santa Catarina"),
    (-26.3045, -48.8487, "Centro",            "Joinville",      "Santa Catarina"),
    (-29.6840, -53.8069, "Centro",            "Santa Maria",    "Rio Grande do Sul"),
    (-30.0277, -51.2086, "Moinhos de Vento",  "Porto Alegre",   "Rio Grande do Sul"),
    (-30.0346, -51.2177, "Centro Histórico",  "Porto Alegre",   "Rio Grande do Sul"),
    (-29.1680, -51.1794, "Centro",            "Caxias do Sul",  "Rio Grande do Sul"),
    (-31.3311, -54.1074, "Centro",            "Pelotas",        "Rio Grande do Sul"),

    # ── ESPÍRITO SANTO ────────────────────────────────────────────────────
    (-20.3222, -40.3381, "Centro",            "Vitória",        "Espírito Santo"),
    (-20.2791, -40.3078, "Praia do Canto",    "Vitória",        "Espírito Santo"),

    # ── OUTROS ESTADOS ────────────────────────────────────────────────────
    (-10.9472, -37.0731, "Centro",            "Aracaju",        "Sergipe"),
    (-5.0892,  -42.8019, "Centro",            "Teresina",       "Piauí"),
]


def _fallback_local(lat, lon):
    """Retorna o município/bairro mais próximo da lista de referência."""
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return {"bairro": "Centro", "cidade": "Rio de Janeiro",
                "estado": "Rio de Janeiro", "pais": "Brasil"}

    def distance(point):
        p_lat, p_lon = point[0], point[1]
        x = (lon - p_lon) * cos(radians((lat + p_lat) / 2))
        y = lat - p_lat
        return sqrt(x * x + y * y)

    nearest = min(KNOWN_BRAZIL_POINTS, key=distance)
    return {
        "bairro": nearest[2],
        "cidade": nearest[3],
        "estado": nearest[4],
        "pais": "Brasil",
    }


def obter_endereco(lat, lon):
    """
    Geocodificação reversa: lat/lon → bairro, cidade, estado.
    Tenta Nominatim primeiro; usa fallback de referência se falhar.
    """
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lon}&format=json&accept-language=pt-BR"
        )
        headers = {"User-Agent": "SolusCRT-Saude/2.0 (contato@soluscrt.com.br)"}
        res = requests.get(url, headers=headers, timeout=4)
        res.raise_for_status()
        data = res.json()
        address = data.get("address", {})

        bairro = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("city_district")
            or address.get("quarter")
            or address.get("hamlet")
            or address.get("borough")
            or address.get("residential")
            or address.get("village")
            or address.get("town")
        )

        cidade = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("county")
        )

        estado = address.get("state")

        if cidade and estado:
            return {
                "bairro": bairro or "Centro",
                "cidade": cidade,
                "estado": estado,
                "pais": address.get("country") or "Brasil",
            }

        # Nominatim respondeu mas sem cidade/estado: usa fallback
        return _fallback_local(lat, lon)

    except Exception as exc:
        # Timeout, erro de rede, JSON inválido — usa fallback local
        print(f"[geo] fallback para ({lat},{lon}): {exc}")
        return _fallback_local(lat, lon)
