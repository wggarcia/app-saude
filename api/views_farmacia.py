from django.http import JsonResponse
from .epidemiologia import build_panorama_payload


def api_farmacia_painel(request):
    if not hasattr(request, "empresa"):
        return JsonResponse({"erro": "não autenticado"}, status=401)

    try:
        payload = build_panorama_payload()
    except Exception:
        return JsonResponse({"erro": "dados indisponíveis"}, status=503)

    overview = payload.get("overview", {})
    bairros = payload.get("layers", {}).get("bairros", [])

    top_pressure = sorted(
        bairros,
        key=lambda a: (a.get("stock_pressure", 0), a.get("growth_percent", 0)),
        reverse=True,
    )[:6]

    market_overview = overview.get("market_overview", {})
    priority_zones = market_overview.get("priority_zones", [])

    dominant_disease = ""
    dominant_symptom = ""
    probable_diseases = overview.get("probable_diseases", [])
    symptoms = overview.get("symptoms", [])
    if probable_diseases:
        dominant_disease = probable_diseases[0].get("name", "")
    if symptoms:
        dominant_symptom = symptoms[0].get("label", "")

    growth_percent = overview.get("growth_percent", 0)
    risk_level = overview.get("risk_level", "BAIXO")
    total_cases = overview.get("total_cases", 0)

    from .epidemiologia import _stock_pressure, _market_signal, _restock_window
    global_stock_pressure = _stock_pressure(total_cases, growth_percent, risk_level)
    market_signal = _market_signal(dominant_disease, dominant_symptom, global_stock_pressure)
    restock_window = _restock_window(growth_percent, risk_level)

    medicamentos_alta = []
    if dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        medicamentos_alta = ["Dipirona", "Paracetamol", "Soro de reidratação", "Repelente", "Vitamina C"]
    elif dominant_disease in {"COVID", "Gripe"}:
        medicamentos_alta = ["Antigripal", "Ibuprofeno", "Azitromicina", "Paracetamol", "Máscara PFF2"]
    elif dominant_disease in {"Leptospirose", "Malaria"}:
        medicamentos_alta = ["Doxiciclina", "Penicilina", "Antitérmico", "Soro", "Amoxicilina"]
    elif dominant_disease in {"Sarampo", "Meningite"}:
        medicamentos_alta = ["Paracetamol", "Máscara cirúrgica", "Ibuprofen", "Vitamina A", "Soro"]
    else:
        medicamentos_alta = ["Antitérmico", "Analgésico", "Soro", "Vitamina C", "Antigripal"]

    zonas_criticas = [
        {
            "zona": z.get("label", "—"),
            "pressao": z.get("stock_pressure", 0),
            "janela": z.get("restock_window", "—"),
            "sinal": z.get("signal", "—"),
        }
        for z in priority_zones[:5]
    ]

    from datetime import date, timedelta
    today = date.today()
    series = (overview.get("timeline") or {}).get("series", [])
    previsao_7d = []
    if series:
        base = series[-1].get("total", 0)
        taxa = max(growth_percent / 100, 0)
        for i in range(1, 8):
            dia = today + timedelta(days=i)
            est = int(base * (1 + taxa * i * 0.15))
            previsao_7d.append({"dia": dia.strftime("%d/%m"), "estimado": est})

    return JsonResponse({
        "status": "ok",
        "painel": {
            "pressao_estoque_global": global_stock_pressure,
            "sinal_mercado": market_signal,
            "janela_reabastecimento": restock_window,
            "risco": risk_level,
            "crescimento_percent": growth_percent,
            "casos_total": total_cases,
            "doenca_dominante": dominant_disease,
            "sintoma_dominante": dominant_symptom,
            "medicamentos_alta": medicamentos_alta,
            "zonas_criticas": zonas_criticas,
            "previsao_demanda_7d": previsao_7d,
        },
    })
