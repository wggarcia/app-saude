import requests
from math import cos, radians, sqrt


KNOWN_BRAZIL_POINTS = [
    (-23.5505, -46.6333, "Se", "São Paulo", "São Paulo"),
    (-22.9068, -43.1729, "Centro", "Rio de Janeiro", "Rio de Janeiro"),
    (-15.7939, -47.8828, "Plano Piloto", "Brasília", "Distrito Federal"),
    (-12.9777, -38.5016, "Centro", "Salvador", "Bahia"),
    (-8.0476, -34.8770, "Boa Vista", "Recife", "Pernambuco"),
    (-3.7319, -38.5267, "Centro", "Fortaleza", "Ceara"),
    (-19.9167, -43.9345, "Centro", "Belo Horizonte", "Minas Gerais"),
    (-30.0346, -51.2177, "Centro Historico", "Porto Alegre", "Rio Grande do Sul"),
    (-25.4284, -49.2733, "Centro", "Curitiba", "Parana"),
    (-3.1190, -60.0217, "Centro", "Manaus", "Amazonas"),
    (-1.4558, -48.4902, "Campina", "Belem", "Para"),
    (-16.6869, -49.2648, "Setor Central", "Goiânia", "Goias"),
]


def _fallback_local(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return {
            "bairro": "Centro",
            "cidade": "Rio de Janeiro",
            "estado": "Rio de Janeiro",
            "pais": "Brasil",
        }

    def distance(point):
        p_lat, p_lon = point[0], point[1]
        x = (lon - p_lon) * cos(radians((lat + p_lat) / 2))
        y = lat - p_lat
        return sqrt((x * x) + (y * y))

    nearest = min(KNOWN_BRAZIL_POINTS, key=distance)
    return {
        "bairro": nearest[2],
        "cidade": nearest[3],
        "estado": nearest[4],
        "pais": "Brasil",
    }

def obter_endereco(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"

        headers = {
            "User-Agent": "app-saude-profissional"
        }

        res = requests.get(url, headers=headers, timeout=2.5)
        res.raise_for_status()
        data = res.json()

        address = data.get("address", {})

        # 🔥 lógica forte (Brasil inteiro)
        bairro = (
    address.get("suburb")
    or address.get("neighbourhood")
    or address.get("city_district")
    or address.get("quarter")
    or address.get("hamlet")
    or address.get("borough")
    or address.get("residential")
    or address.get("county")  # 🔥 fallback forte
)

        cidade = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
        )

        if cidade and address.get("state"):
            return {
                "bairro": bairro or "Centro",
                "cidade": cidade,
                "estado": address.get("state"),
                "pais": address.get("country") or "Brasil"
            }
        return _fallback_local(lat, lon)

    except Exception as e:
        print("ERRO GEO:", e)
        return _fallback_local(lat, lon)
