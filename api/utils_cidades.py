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

    with open(caminho, "r", encoding="utf-8-sig") as f:
        BASE = json.load(f)

    return BASE


def buscar_coordenada(cidade, estado):
    base = carregar_base()

    # 🔒 proteção mínima (sem quebrar)
    if not cidade:
        return None, None

    cidade = str(cidade).strip().lower()

    for c in base:
        try:
            nome = c["nome"].strip().lower()

            # comparação exata (igual ao seu original)
            if nome == cidade:
                return c["latitude"], c["longitude"]

        except:
            continue

    return None, None