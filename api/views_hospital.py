from django.http import JsonResponse
from .epidemiologia import build_panorama_payload


def api_hospital_painel(request):
    if not hasattr(request, "empresa"):
        return JsonResponse({"erro": "não autenticado"}, status=401)

    try:
        payload = build_panorama_payload()
    except Exception:
        return JsonResponse({"erro": "dados indisponíveis"}, status=503)

    overview = payload.get("overview", {})
    bairros = payload.get("layers", {}).get("bairros", [])

    top_load = sorted(
        bairros,
        key=lambda a: (a.get("hospital_load_estimate", 0), a.get("growth_percent", 0)),
        reverse=True,
    )[:6]

    hospital_overview = overview.get("hospital_overview", {})
    priority_zones = hospital_overview.get("priority_zones", [])

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

    from .epidemiologia import _hospital_load_estimate, _triage_priority, _readiness_level
    global_load = _hospital_load_estimate(total_cases, growth_percent, dominant_symptom)
    triage_priority = _triage_priority(dominant_symptom, risk_level, growth_percent)
    readiness_level = _readiness_level(global_load)

    leitos_estimados = max(int(global_load * 0.8), 1)
    ocupacao_estimada = min(round(global_load, 1), 100.0)

    protocolo_triagem = []
    if dominant_symptom == "Falta de Ar" or risk_level == "CRITICO":
        protocolo_triagem = [
            {"cor": "Vermelho", "descricao": "Pacientes com falta de ar grave — atendimento imediato"},
            {"cor": "Laranja", "descricao": "Febre alta com dor no corpo — observação em até 15 min"},
            {"cor": "Amarelo", "descricao": "Sintomas gripais moderados — triagem em até 30 min"},
            {"cor": "Verde", "descricao": "Casos leves — encaminhamento para UBS"},
        ]
    elif risk_level == "ALTO":
        protocolo_triagem = [
            {"cor": "Laranja", "descricao": "Febre persistente e prostração — observação prioritária"},
            {"cor": "Amarelo", "descricao": "Sintomas moderados — avaliação em 30 min"},
            {"cor": "Verde", "descricao": "Casos leves — triagem padrão e orientação ambulatorial"},
        ]
    else:
        protocolo_triagem = [
            {"cor": "Amarelo", "descricao": "Monitoramento de sintomas respiratórios"},
            {"cor": "Verde", "descricao": "Atendimento padrão — sem sobrecarga imediata"},
        ]

    zonas_pressao = [
        {
            "zona": z.get("label", "—"),
            "carga": z.get("hospital_load_estimate", 0),
            "triagem": z.get("triage_priority", "—"),
            "prontidao": z.get("readiness_level", "—"),
        }
        for z in priority_zones[:5]
    ]

    previsao_internacoes_7d = []
    from datetime import date, timedelta
    today = date.today()
    taxa = max(growth_percent / 100, 0)
    base_internacoes = max(int(total_cases * 0.04), 1)
    for i in range(1, 8):
        dia = today + timedelta(days=i)
        est = int(base_internacoes * (1 + taxa * i * 0.12))
        previsao_internacoes_7d.append({"dia": dia.strftime("%d/%m"), "estimado": est})

    return JsonResponse({
        "status": "ok",
        "painel": {
            "carga_hospitalar_global": global_load,
            "ocupacao_estimada_percent": ocupacao_estimada,
            "leitos_adicionais_estimados": leitos_estimados,
            "triagem_prioridade": triage_priority,
            "nivel_prontidao": readiness_level,
            "risco": risk_level,
            "crescimento_percent": growth_percent,
            "casos_total": total_cases,
            "doenca_dominante": dominant_disease,
            "sintoma_dominante": dominant_symptom,
            "protocolo_triagem": protocolo_triagem,
            "zonas_pressao": zonas_pressao,
            "previsao_internacoes_7d": previsao_internacoes_7d,
        },
    })
