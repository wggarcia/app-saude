import requests

def obter_regiao(lat, lng):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
        headers = {"User-Agent": "app-saude-inteligente"}

        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()

        addr = data.get("address", {})

        return {
            "pais": addr.get("country"),
            "estado": addr.get("state"),
            "cidade": addr.get("city") or addr.get("town") or addr.get("village"),
            "bairro": addr.get("suburb") or addr.get("neighbourhood"),
            "condado": addr.get("county")
        }

    except Exception as e:
        print("Erro geolocalização:", e)
        return {}