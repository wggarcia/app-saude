def detectar_surtos(registros):

    from collections import defaultdict
    from datetime import timedelta
    from django.utils import timezone
    from .utils_cidades import buscar_coordenada

    cidades = defaultdict(list)

    for r in registros:
        if r.cidade:
            cidades[(r.cidade, r.estado)].append(r)

    alertas = []

    agora = timezone.now()
    ultimos_7_dias = agora - timedelta(days=7)
    ultimas_24h = agora - timedelta(hours=24)

    for (cidade, estado), dados in cidades.items():

        semana = [d for d in dados if d.data_registro >= ultimos_7_dias]
        hoje = [d for d in dados if d.data_registro >= ultimas_24h]

        if len(semana) < 10:
            continue

        media = len(semana) / 7
        atual = len(hoje)

        if media == 0:
            continue

        crescimento = (atual - media) / media
        fator_volume = min(len(semana) / 100, 1)
        score = crescimento * fator_volume

        if score > 2:
            nivel = "🔴 SURTO FORTE"
        elif score > 1:
            nivel = "🟠 SURTO MODERADO"
        elif score > 0.5:
            nivel = "🟡 CRESCIMENTO"
        else:
            continue

        # 🔥 AQUI ESTÁ A CORREÇÃO
        lat, lon = buscar_coordenada(cidade, estado)

        alertas.append({
            "cidade": cidade,
            "estado": estado,
            "total": atual,
            "nivel": nivel,
            "latitude": lat,
            "longitude": lon,
            "score": round(score, 2)
        })

    return alertas

def prever_surtos(registros):

    from collections import defaultdict
    from datetime import timedelta
    from django.utils import timezone

    cidades = defaultdict(list)

    for r in registros:
        if r.cidade:
            cidades[(r.cidade, r.estado)].append(r)

    previsoes = []
    agora = timezone.now()

    for cidade, dados in cidades.items():

        dias = []

        for i in range(5):
            inicio = agora - timedelta(days=i+1)
            fim = agora - timedelta(days=i)

            total = len([
                d for d in dados
                if inicio <= d.data_registro < fim
            ])

            dias.append(total)

        dias.reverse()

        if sum(dias) < 10:
            continue

        crescimentos = []

        for i in range(1, len(dias)):
            anterior = dias[i-1]
            atual = dias[i]

            if anterior == 0:
                crescimento = 0  # 🔥 corrigido
            else:
                crescimento = (atual - anterior) / anterior

            crescimentos.append(crescimento)

        if len(crescimentos) < 2:
            continue

        tendencia = sum(crescimentos) / len(crescimentos)
        aceleracao = crescimentos[-1] - crescimentos[-2]

        # 🔥 NOVO: confiança
        confianca = min(sum(dias) / 100, 1)

        if tendencia > 1.5 and aceleracao > 0.5:
            nivel = "🔴 SURTO IMINENTE"
        elif tendencia > 1:
            nivel = "🟠 POSSÍVEL SURTO"
        elif tendencia > 0.5:
            nivel = "🟡 CRESCIMENTO"
        else:
            continue

        previsoes.append({
            "cidade": cidade,
            "dias": dias,
            "tendencia": round(tendencia, 2),
            "aceleracao": round(aceleracao, 2),
            "confianca": round(confianca, 2),
            "nivel": nivel
        })

    return previsoes

# ----------------------------------------
# 📍 GEOLOCALIZAÇÃO
# ----------------------------------------

cache_local = {}

def obter_localizacao(latitude, longitude):

    chave = f"{latitude},{longitude}"

    if chave in cache_local:
        return cache_local[chave]

    try:
        import requests

        url = f"https://nominatim.openstreetmap.org/reverse?lat={latitude}&lon={longitude}&format=json"

        res = requests.get(url, headers={"User-Agent": "app-saude"})
        data = res.json()

        endereco = data.get("address", {})

        resultado = {
            "pais": endereco.get("country"),
            "estado": endereco.get("state"),
            "cidade": endereco.get("city") or endereco.get("town"),
            "bairro": endereco.get("suburb"),
            "condado": endereco.get("county"),
        }

        cache_local[chave] = resultado

        return resultado

    except Exception as e:
        print("Erro localização:", e)
        return {
            "pais": None,
            "estado": None,
            "cidade": None,
            "bairro": None,
            "condado": None,
        }


# ----------------------------------------
# 🔮 IA AVANÇADA (NÍVEL 2)
# ----------------------------------------

def prever_surtos_avancado(registros):

    from collections import defaultdict
    from datetime import timedelta
    from django.utils import timezone

    cidades = defaultdict(list)

    for r in registros:
        if r.cidade:
            cidades[(r.cidade, r.estado)].append(r)

    previsoes = []
    agora = timezone.now()

    for cidade, dados in cidades.items():

        dias = []

        for i in range(7):
            inicio = agora - timedelta(days=i+1)
            fim = agora - timedelta(days=i)

            total = len([
                d for d in dados
                if inicio <= d.data_registro < fim
            ])

            dias.append(total)

        dias.reverse()

        if sum(dias) < 15:
            continue

        crescimentos = []

        for i in range(1, len(dias)):
            anterior = dias[i-1]
            atual = dias[i]

            if anterior == 0:
                crescimento = 0
            else:
                crescimento = (atual - anterior) / anterior

            crescimentos.append(crescimento)

        tendencia = sum(crescimentos) / len(crescimentos)
        aceleracao = crescimentos[-1] - crescimentos[-2]

        volume = sum(dias)
        densidade = min(volume / 100, 1)

        score = (tendencia * 0.5) + (aceleracao * 0.3) + (densidade * 0.2)

        # 🔥 comportamento tipo surto (explosão)
        explosao = max(dias) - min(dias)

        score += explosao * 0.1

        if score > 1.5:
            nivel = "🔴 SURTO FORTE"
        elif score > 1:
            nivel = "🟠 SURTO MODERADO"
        elif score > 0.5:
            nivel = "🟡 CRESCIMENTO"
        else:
            continue

        previsoes.append({
            "cidade": cidade,
            "score": round(score, 2),
            "tendencia": round(tendencia, 2),
            "aceleracao": round(aceleracao, 2),
            "densidade": round(densidade, 2),
            "nivel": nivel
        })

    return previsoes

def detectar_clusters(registros):

    clusters = []

    for r in registros:

        if not r.latitude or not r.longitude:
            continue

        encontrou = False

        for c in clusters:

            dist = ((r.latitude - c["lat"])**2 + (r.longitude - c["lon"])**2) ** 0.5

            if dist < 0.01:  # 🔥 raio (ajustável)
                c["casos"] += 1
                c["lat"] = (c["lat"] + r.latitude) / 2
                c["lon"] = (c["lon"] + r.longitude) / 2
                encontrou = True
                break

        if not encontrou:
            clusters.append({
                "lat": r.latitude,
                "lon": r.longitude,
                "casos": 1
            })

    return clusters

import json
import os

BASE = None

def carregar_base():
    global BASE

    if BASE:
        return BASE

    caminho = os.path.join(os.path.dirname(__file__), "base_municipios.json")

    if not os.path.exists(caminho):
        print("⚠️ base_municipios.json não encontrado")
        return []

    with open(caminho, "r", encoding="utf-8") as f:
        BASE = json.load(f)

    return BASE



from collections import Counter


# =========================
# 📊 CLASSIFICAÇÃO DE VOLUME
# =========================
def classificar_volume(total):

    if total < 20:
        return "NORMAL"

    if total < 50:
        return "ATENCAO"

    if total < 100:
        return "ALERTA"

    return "CRITICO"


# =========================
# 📈 CRESCIMENTO
# =========================
def classificar_crescimento(atual, anterior):

    if anterior == 0:
        return "ESTAVEL"

    taxa = atual / anterior

    if taxa < 1.2:
        return "ESTAVEL"

    if taxa < 1.8:
        return "SUBINDO"

    return "EXPLOSAO"


# =========================
# 🚨 RISCO FINAL
# =========================
def calcular_risco(total, crescimento):

    volume = classificar_volume(total)

    if crescimento == "EXPLOSAO":
        return "CRITICO"

    if volume == "CRITICO":
        return "CRITICO"

    if volume == "ALERTA":
        return "ALERTA"

    return "NORMAL"


# =========================
# 🧬 CLASSIFICAR DOENÇA
# =========================
def classificar_doenca(d):

    if d["febre"] and d["dor_corpo"] and d["cansaco"] and not d["tosse"]:
        return "Dengue"

    if d["tosse"] and d["falta_ar"]:
        return "COVID"

    if d["febre"] and d["dor_corpo"] and d["cansaco"]:
        return "Chikungunya"

    if d["tosse"] and d["febre"]:
        return "Gripe"

    return "Indefinido"


# =========================
# 📊 CONTAGEM POR DOENÇA
# =========================
def analisar_doencas(registros):

    contador = Counter()

    for r in registros:
        doenca = classificar_doenca({
            "febre": r.febre,
            "tosse": r.tosse,
            "dor_corpo": r.dor_corpo,
            "cansaco": r.cansaco,
            "falta_ar": r.falta_ar
        })

        contador[doenca] += 1

    return dict(contador)


# =========================
# 🚨 LIMITE POR DOENÇA
# =========================
def risco_por_doenca(doenca, total):

    limites = {
        "Gripe": (30, 80, 150),
        "Dengue": (20, 50, 100),
        "Chikungunya": (15, 40, 80),
        "COVID": (10, 30, 70)
    }

    if doenca not in limites:
        return "NORMAL"

    atencao, alerta, critico = limites[doenca]

    if total >= critico:
        return "CRITICO"

    if total >= alerta:
        return "ALERTA"

    if total >= atencao:
        return "ATENCAO"

    return "NORMAL"


import math

def probabilidade_doenca(sintomas):

    # pesos baseados em comportamento real
    pesos = {
        "Dengue": {
            "febre": 0.9,
            "dor_corpo": 0.8,
            "cansaco": 0.7,
            "tosse": -0.5
        },
        "COVID": {
            "tosse": 0.9,
            "falta_ar": 0.9,
            "febre": 0.6
        },
        "Chikungunya": {
            "febre": 0.8,
            "dor_corpo": 0.9,
            "cansaco": 0.8
        },
        "Gripe": {
            "tosse": 0.8,
            "febre": 0.7,
            "cansaco": 0.5
        }
    }

    resultado = {}

    for doenca, regras in pesos.items():

        score = 0

        for sintoma, peso in regras.items():
            if sintomas.get(sintoma):
                score += peso

        # 🔥 transforma em probabilidade (sigmoid)
        prob = 1 / (1 + math.exp(-score))

        resultado[doenca] = round(prob * 100, 2)

    return resultado

from collections import defaultdict

def treinar_modelo(registros):

    modelo = defaultdict(lambda: defaultdict(int))

    for r in registros:

        if not r.doenca_confirmada:
            continue

        sintomas = [
            ("febre", r.febre),
            ("tosse", r.tosse),
            ("dor_corpo", r.dor_corpo),
            ("cansaco", r.cansaco),
            ("falta_ar", r.falta_ar),
        ]

        for nome, valor in sintomas:
            if valor:
                modelo[r.doenca_confirmada][nome] += 1

    return modelo

def prever_com_aprendizado(sintomas, modelo):

    scores = {}

    for doenca, dados in modelo.items():

        score = 0

        for sintoma, valor in sintomas.items():
            if valor:
                score += dados.get(sintoma, 0)

        scores[doenca] = score

    if not scores:
        return {}

    total = sum(scores.values()) or 1

    probabilidades = {
        d: round((v / total) * 100, 2)
        for d, v in scores.items()
    }

    return probabilidades