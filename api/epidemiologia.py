from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import json
from time import time

from django.db.models import Avg, Count, Q
from django.http import JsonResponse, HttpResponse
from django.utils import timezone

from .models import RegistroSintoma
from .utils_cidades import carregar_base


SYMPTOM_LABELS = {
    "febre": "Febre",
    "tosse": "Tosse",
    "falta_ar": "Falta de Ar",
    "dor_corpo": "Dor no Corpo",
    "cansaco": "Cansaco",
}

DISEASE_WEIGHTS = {
    "Dengue": {
        "febre": 1.0,
        "dor_corpo": 0.95,
        "cansaco": 0.75,
        "tosse": -0.25,
        "falta_ar": -0.15,
    },
    "COVID": {
        "tosse": 1.0,
        "falta_ar": 0.95,
        "febre": 0.7,
        "cansaco": 0.45,
    },
    "Chikungunya": {
        "febre": 0.9,
        "dor_corpo": 1.0,
        "cansaco": 0.85,
    },
    "Gripe": {
        "tosse": 0.85,
        "febre": 0.75,
        "cansaco": 0.55,
        "dor_corpo": 0.35,
    },
    "Zika": {
        "febre": 0.68,
        "dor_corpo": 0.52,
        "cansaco": 0.48,
        "tosse": -0.18,
    },
    "Bronquite": {
        "tosse": 0.98,
        "falta_ar": 0.88,
        "cansaco": 0.4,
        "febre": -0.1,
    },
    "Virose": {
        "febre": 0.52,
        "cansaco": 0.5,
        "dor_corpo": 0.44,
        "tosse": 0.22,
    },
}

_PANORAMA_CACHE = {"created_at": 0.0, "payload": None}
_CACHE_TTL_SECONDS = 15
_CITY_TO_UF = None

UF_CODES = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}


def _city_to_uf_map():
    global _CITY_TO_UF

    if _CITY_TO_UF is not None:
        return _CITY_TO_UF

    mapping = {}

    for city in carregar_base():
        name = city.get("nome")
        uf = UF_CODES.get(city.get("codigo_uf"))

        if name and uf:
            mapping[str(name).strip().lower()] = uf

    _CITY_TO_UF = mapping
    return mapping


def _normalize_state(city, state):
    normalized = (state or "").strip().upper()

    if normalized and normalized not in {"BR", "BRASIL"}:
        return normalized

    if city:
        return _city_to_uf_map().get(str(city).strip().lower(), normalized or "BR")

    return normalized or "BR"


def _safe_pct(value, total):
    if not total:
        return 0.0
    return round((value / total) * 100, 2)


def _safe_growth(current, previous):
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _risk_score(total, max_total, recent_24h, max_recent, growth):
    total_score = (total / max_total) * 55 if max_total else 0
    recent_score = (recent_24h / max_recent) * 25 if max_recent else 0
    growth_score = min(max(growth, 0), 100) * 0.2
    return round(total_score + recent_score + growth_score, 2)


def _risk_level(score):
    if score >= 75:
        return "CRITICO"
    if score >= 55:
        return "ALTO"
    if score >= 35:
        return "MODERADO"
    return "BAIXO"


def _area_label(level, row):
    if level == "bairro":
        return f"{row['bairro']} - {row['cidade']}/{row['estado']}"
    if level == "municipio":
        return f"{row['cidade']}/{row['estado']}"
    return row["estado"]


def _focus_message(dominant_symptom, dominant_disease, risk_level):
    return (
        f"Foco predominante de {dominant_symptom.lower()} com padrao mais "
        f"proximo de {dominant_disease.lower()} ({risk_level.lower()})."
    )


def _alert_stage(risk_level, growth_percent, total_cases):
    if risk_level == "CRITICO" or (growth_percent >= 70 and total_cases >= 500):
        return "Resposta Imediata"
    if risk_level == "ALTO" or growth_percent >= 35:
        return "Contencao Acelerada"
    if risk_level == "MODERADO" or growth_percent >= 15:
        return "Monitoramento Reforcado"
    return "Vigilancia Ativa"


def _public_recommendation(dominant_disease, dominant_symptom, risk_level):
    base = {
        "COVID": "reforcar etiqueta respiratoria, mascara em ambientes fechados e triagem imediata",
        "Gripe": "reforcar etiqueta respiratoria, hidratacao e avaliacao rapida de sintomaticos",
        "Dengue": "eliminar agua parada, acelerar vigilancia vetorial e orientar hidratacao",
        "Chikungunya": "orientar dor articular persistente, hidratar e rastrear aumento de vetores",
    }
    action = base.get(dominant_disease, f"priorizar monitoramento de {dominant_symptom.lower()} e orientacao local")

    if risk_level == "CRITICO":
        return f"Acionar resposta rapida e {action}."
    if risk_level == "ALTO":
        return f"Intensificar vigilancia de campo e {action}."
    return f"Manter vigilancia ativa e {action}."


def _market_recommendation(dominant_disease, dominant_symptom):
    if dominant_disease == "COVID":
        return "reforcar estoque de mascaras, antitermicos, testes e antigripais"
    if dominant_disease == "Gripe":
        return "reforcar antigripais, xaropes, vitamina C e analgesicos"
    if dominant_disease in {"Dengue", "Chikungunya"}:
        return "reforcar analgesicos, hidratacao oral, repelentes e materiais de orientacao"
    if dominant_symptom == "Falta de Ar":
        return "priorizar itens respiratorios e protocolos de encaminhamento"
    return "acompanhar demanda de sintomaticos e ajustar estoque de suporte"


def _hospital_recommendation(dominant_disease, dominant_symptom, risk_level):
    if dominant_symptom == "Falta de Ar" or dominant_disease == "COVID":
        action = "preparar leitos respiratorios, triagem rapida, oxigenio e retaguarda de UTI"
    elif dominant_disease in {"Dengue", "Chikungunya"}:
        action = "preparar hidratacao venosa, analgesia, observacao e fluxo para sinais de alarme"
    elif dominant_disease == "Gripe":
        action = "reforcar triagem sindromica, observacao e acolhimento de demanda espontanea"
    else:
        action = "ajustar escala, triagem e retaguarda assistencial para pico local"

    if risk_level == "CRITICO":
        return f"Acionar plano hospitalar de contingencia e {action}."
    if risk_level == "ALTO":
        return f"Ampliar capacidade de atendimento e {action}."
    return f"Manter prontidao assistencial e {action}."


def _government_recommendation(dominant_disease, dominant_symptom, risk_level, growth_percent, total_cases):
    if dominant_disease in {"Dengue", "Chikungunya"}:
        action = "intensificar vigilancia vetorial, bloqueio territorial, comunicacao comunitaria e mutirao de campo"
    elif dominant_symptom == "Falta de Ar" or dominant_disease == "COVID":
        action = "acionar vigilancia sindromica respiratoria, campanha de protecao e retaguarda regional"
    elif dominant_disease == "Gripe":
        action = "reforcar sentinelas, testagem estrategica e comunicacao de sazonalidade"
    else:
        action = "reforcar inteligencia territorial, campo e comunicacao de risco"

    if risk_level == "CRITICO" or (growth_percent >= 80 and total_cases >= 1000):
        return f"Executar resposta integrada intersetorial e {action}."
    if risk_level == "ALTO":
        return f"Ativar gabinete tatico regional e {action}."
    return f"Manter vigilancia governamental ativa e {action}."


def _response_priority(risk_level, growth_percent):
    if risk_level == "CRITICO" or growth_percent >= 80:
        return 1
    if risk_level == "ALTO" or growth_percent >= 40:
        return 2
    if risk_level == "MODERADO":
        return 3
    return 4


def _surveillance_index(total_cases, recent_24h, growth_percent, max_total, max_recent):
    density_score = (total_cases / max_total) * 45 if max_total else 0
    velocity_score = (recent_24h / max_recent) * 35 if max_recent else 0
    acceleration_score = min(max(growth_percent, 0), 100) * 0.2
    return round(density_score + velocity_score + acceleration_score, 2)


def _resource_pressure(total_cases, growth_percent, dominant_symptom):
    base = total_cases * 0.015
    growth_component = max(growth_percent, 0) * 0.35
    respiratory_bonus = 12 if dominant_symptom == "Falta de Ar" else 0
    return round(min(base + growth_component + respiratory_bonus, 100), 2)


def _trend_status(growth_percent, recent_24h, previous_24h):
    if recent_24h == 0 and previous_24h == 0:
        return "Sem atividade recente"
    if recent_24h == 0 and previous_24h > 0:
        return "Desaceleracao forte"
    if growth_percent >= 70:
        return "Explosao"
    if growth_percent >= 30:
        return "Alta acelerada"
    if growth_percent >= 8:
        return "Alta moderada"
    if growth_percent <= -45:
        return "Queda intensa"
    if growth_percent <= -12:
        return "Queda"
    return "Estavel"


def _activity_percent(total_cases, recent_24h):
    if total_cases <= 0:
        return 0.0
    return round(min((recent_24h / total_cases) * 100, 100), 2)


def _decay_percent(recent_24h, previous_24h):
    if previous_24h <= 0:
        return 0.0
    if recent_24h >= previous_24h:
        return 0.0
    return round(((previous_24h - recent_24h) / previous_24h) * 100, 2)


def _strategic_tags(dominant_disease, dominant_symptom, growth_percent, risk_level):
    tags = [dominant_disease, dominant_symptom]

    if growth_percent >= 50:
        tags.append("Aceleracao")
    if risk_level in {"CRITICO", "ALTO"}:
        tags.append("Prioridade Alta")
    if dominant_symptom == "Falta de Ar":
        tags.append("Respiratorio")
    if dominant_disease in {"Dengue", "Chikungunya"}:
        tags.append("Vetorial")

    return tags[:4]


def _government_tags(dominant_disease, dominant_symptom, growth_percent, risk_level):
    tags = ["Governanca", dominant_disease]

    if dominant_symptom == "Falta de Ar":
        tags.append("Resposta Respiratoria")
    if dominant_disease in {"Dengue", "Chikungunya"}:
        tags.append("Campo Vetorial")
    if growth_percent >= 50:
        tags.append("Escalada")
    if risk_level == "CRITICO":
        tags.append("Emergencia")

    return tags[:5]


def _stock_pressure(total_cases, growth_percent, risk_level):
    pressure = (total_cases * 0.02) + max(growth_percent, 0) * 0.45
    if risk_level == "CRITICO":
        pressure += 16
    elif risk_level == "ALTO":
        pressure += 8
    return round(min(pressure, 100), 2)


def _market_signal(dominant_disease, dominant_symptom, stock_pressure):
    if dominant_disease in {"Dengue", "Chikungunya"}:
        category = "hidratacao, analgesia e repelentes"
    elif dominant_disease in {"COVID", "Gripe"} or dominant_symptom == "Tosse":
        category = "antigripais, testes, mascaras e suporte respiratorio leve"
    elif dominant_symptom == "Falta de Ar":
        category = "oximetria, suporte respiratorio e itens de encaminhamento"
    else:
        category = "sintomaticos de alta rotacao"

    if stock_pressure >= 80:
        urgency = "ruptura provavel"
    elif stock_pressure >= 55:
        urgency = "reabastecimento prioritario"
    else:
        urgency = "monitoramento comercial"

    return f"{urgency} para {category}"


def _restock_window(growth_percent, risk_level):
    if risk_level == "CRITICO" or growth_percent >= 70:
        return "12-24h"
    if risk_level == "ALTO" or growth_percent >= 35:
        return "24-48h"
    return "48-72h"


def _hospital_load_estimate(total_cases, growth_percent, dominant_symptom):
    load = (total_cases * 0.018) + max(growth_percent, 0) * 0.32
    if dominant_symptom == "Falta de Ar":
        load += 15
    return round(min(load, 100), 2)


def _triage_priority(dominant_symptom, risk_level, growth_percent):
    if dominant_symptom == "Falta de Ar" or risk_level == "CRITICO":
        return "Ativacao imediata de triagem critica"
    if risk_level == "ALTO" or growth_percent >= 35:
        return "Triagem acelerada e observacao expandida"
    return "Triagem monitorada"


def _readiness_level(hospital_load_estimate):
    if hospital_load_estimate >= 80:
        return "Resposta hospitalar maxima"
    if hospital_load_estimate >= 55:
        return "Prontidao reforcada"
    return "Prontidao monitorada"


def _normalize_probabilities(raw_scores):
    total = sum(raw_scores.values()) or 1.0
    normalized = []

    for disease, score in sorted(raw_scores.items(), key=lambda item: item[1], reverse=True):
        probability = round((score / total) * 100, 2)
        normalized.append({
            "name": disease,
            "probability": probability,
        })

    return normalized


def _build_disease_probabilities(symptom_counts, total_cases):
    rates = {
        name: (count / total_cases) if total_cases else 0.0
        for name, count in symptom_counts.items()
    }
    raw_scores = {}

    for disease, weights in DISEASE_WEIGHTS.items():
        score = 0.08

        for symptom, weight in weights.items():
            rate = rates.get(symptom, 0.0)
            if weight >= 0:
                score += rate * weight
            else:
                score += (1 - rate) * abs(weight) * 0.25

        raw_scores[disease] = max(score, 0.01)

    probabilities = _normalize_probabilities(raw_scores)

    for item in probabilities:
        item["estimated_cases"] = int(round(total_cases * item["probability"] / 100))

    return probabilities


def _attach_active_probabilities(probabilities, activity_percent):
    activity_factor = max(min(activity_percent / 100, 1.0), 0.0)

    for item in probabilities:
        item["active_probability"] = round(item["probability"] * activity_factor, 2)

    return probabilities


def _serialize_symptoms(symptom_counts, total_cases):
    payload = []

    for key, label in SYMPTOM_LABELS.items():
        count = int(symptom_counts.get(key, 0) or 0)
        payload.append({
            "key": key,
            "label": label,
            "count": count,
            "percentage": _safe_pct(count, total_cases),
        })

    payload.sort(key=lambda item: item["count"], reverse=True)
    return payload


def _build_layer_queryset(group_fields):
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    previous_24h = now - timedelta(hours=48)

    queryset = RegistroSintoma.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    for field in group_fields:
        queryset = queryset.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""})

    return list(
        queryset.values(*group_fields)
        .annotate(
            total=Count("id"),
            latitude=Avg("latitude"),
            longitude=Avg("longitude"),
            recent_24h=Count("id", filter=Q(data_registro__gte=last_24h)),
            previous_24h=Count(
                "id",
                filter=Q(data_registro__gte=previous_24h, data_registro__lt=last_24h),
            ),
            febre=Count("id", filter=Q(febre=True)),
            tosse=Count("id", filter=Q(tosse=True)),
            falta_ar=Count("id", filter=Q(falta_ar=True)),
            dor_corpo=Count("id", filter=Q(dor_corpo=True)),
            cansaco=Count("id", filter=Q(cansaco=True)),
        )
        .order_by("-total")
    )


def _serialize_layer(level, group_fields):
    rows = _build_layer_queryset(group_fields)
    max_total = max((row["total"] for row in rows), default=1)
    max_recent = max((row["recent_24h"] for row in rows), default=1)
    areas = []

    for index, row in enumerate(rows, start=1):
        total_cases = int(row["total"] or 0)
        normalized_state = _normalize_state(row.get("cidade"), row.get("estado"))
        symptom_counts = {
            key: int(row.get(key, 0) or 0)
            for key in SYMPTOM_LABELS
        }
        symptom_breakdown = _serialize_symptoms(symptom_counts, total_cases)
        dominant_symptom = symptom_breakdown[0]["label"] if symptom_breakdown else "Sem dados"
        disease_probabilities = _build_disease_probabilities(symptom_counts, total_cases)
        activity_percent = _activity_percent(total_cases, int(row["recent_24h"] or 0))
        disease_probabilities = _attach_active_probabilities(disease_probabilities, activity_percent)
        dominant_disease = disease_probabilities[0]["name"] if disease_probabilities else "Indefinido"
        growth = _safe_growth(int(row["recent_24h"] or 0), int(row["previous_24h"] or 0))
        risk_score = _risk_score(
            total_cases,
            max_total,
            int(row["recent_24h"] or 0),
            max_recent,
            growth,
        )
        risk_level = _risk_level(risk_score)
        surveillance_index = _surveillance_index(total_cases, int(row["recent_24h"] or 0), growth, max_total, max_recent)
        resource_pressure = _resource_pressure(total_cases, growth, dominant_symptom)
        stock_pressure = _stock_pressure(total_cases, growth, risk_level)
        hospital_load_estimate = _hospital_load_estimate(total_cases, growth, dominant_symptom)

        area = {
            "id": f"{level}-{index}",
            "level": level,
            "nome": row[group_fields[-1]],
            "cidade": row.get("cidade"),
            "estado": normalized_state,
            "label": _area_label(level, {**row, "estado": normalized_state}),
            "latitude": round(float(row["latitude"]), 6) if row["latitude"] is not None else None,
            "longitude": round(float(row["longitude"]), 6) if row["longitude"] is not None else None,
            "total_cases": total_cases,
            "recent_24h": int(row["recent_24h"] or 0),
            "previous_24h": int(row["previous_24h"] or 0),
            "growth_percent": growth,
            "activity_percent": activity_percent,
            "decay_percent": _decay_percent(int(row["recent_24h"] or 0), int(row["previous_24h"] or 0)),
            "trend_status": _trend_status(growth, int(row["recent_24h"] or 0), int(row["previous_24h"] or 0)),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "surveillance_index": surveillance_index,
            "resource_pressure": resource_pressure,
            "stock_pressure": stock_pressure,
            "market_signal": _market_signal(dominant_disease, dominant_symptom, stock_pressure),
            "restock_window": _restock_window(growth, risk_level),
            "hospital_load_estimate": hospital_load_estimate,
            "triage_priority": _triage_priority(dominant_symptom, risk_level, growth),
            "readiness_level": _readiness_level(hospital_load_estimate),
            "response_priority": _response_priority(risk_level, growth),
            "symptoms": symptom_breakdown,
            "probable_diseases": disease_probabilities,
            "dominant_symptom": dominant_symptom,
            "dominant_disease": dominant_disease,
            "radius": int(1200 + ((total_cases / max_total) * 52000)) if max_total else 1200,
            "focus_message": _focus_message(dominant_symptom, dominant_disease, risk_level),
            "alert_stage": _alert_stage(risk_level, growth, total_cases),
            "public_recommendation": _public_recommendation(dominant_disease, dominant_symptom, risk_level),
            "market_recommendation": _market_recommendation(dominant_disease, dominant_symptom),
            "hospital_recommendation": _hospital_recommendation(dominant_disease, dominant_symptom, risk_level),
            "government_recommendation": _government_recommendation(dominant_disease, dominant_symptom, risk_level, growth, total_cases),
            "strategic_tags": _strategic_tags(dominant_disease, dominant_symptom, growth, risk_level),
            "government_tags": _government_tags(dominant_disease, dominant_symptom, growth, risk_level),
        }
        areas.append(area)

    return areas


def _build_state_layer(municipios):
    grouped = defaultdict(lambda: {
        "estado": None,
        "total_cases": 0,
        "recent_24h": 0,
        "previous_24h": 0,
        "lat_sum": 0.0,
        "lng_sum": 0.0,
        "weight": 0,
        "symptom_counts": defaultdict(int),
    })

    for area in municipios:
        state_key = area["estado"] or "BR"
        entry = grouped[state_key]
        entry["estado"] = state_key
        entry["total_cases"] += area["total_cases"]
        entry["recent_24h"] += area["recent_24h"]
        entry["previous_24h"] += area["previous_24h"]

        if area["latitude"] is not None and area["longitude"] is not None:
            entry["lat_sum"] += area["latitude"] * area["total_cases"]
            entry["lng_sum"] += area["longitude"] * area["total_cases"]
            entry["weight"] += area["total_cases"]

        for symptom in area["symptoms"]:
            entry["symptom_counts"][symptom["key"]] += symptom["count"]

    rows = list(grouped.values())
    max_total = max((row["total_cases"] for row in rows), default=1)
    max_recent = max((row["recent_24h"] for row in rows), default=1)
    states = []

    for index, row in enumerate(sorted(rows, key=lambda item: item["total_cases"], reverse=True), start=1):
        total_cases = row["total_cases"]
        symptom_breakdown = _serialize_symptoms(row["symptom_counts"], total_cases)
        dominant_symptom = symptom_breakdown[0]["label"] if symptom_breakdown else "Sem dados"
        probable_diseases = _build_disease_probabilities(row["symptom_counts"], total_cases)
        activity_percent = _activity_percent(total_cases, row["recent_24h"])
        probable_diseases = _attach_active_probabilities(probable_diseases, activity_percent)
        dominant_disease = probable_diseases[0]["name"] if probable_diseases else "Indefinido"
        growth = _safe_growth(row["recent_24h"], row["previous_24h"])
        risk_score = _risk_score(total_cases, max_total, row["recent_24h"], max_recent, growth)
        weight = row["weight"] or 1
        risk_level = _risk_level(risk_score)
        surveillance_index = _surveillance_index(total_cases, row["recent_24h"], growth, max_total, max_recent)
        resource_pressure = _resource_pressure(total_cases, growth, dominant_symptom)
        stock_pressure = _stock_pressure(total_cases, growth, risk_level)
        hospital_load_estimate = _hospital_load_estimate(total_cases, growth, dominant_symptom)

        states.append({
            "id": f"estado-{index}",
            "level": "estado",
            "nome": row["estado"],
            "cidade": None,
            "estado": row["estado"],
            "label": row["estado"],
            "latitude": round(row["lat_sum"] / weight, 6),
            "longitude": round(row["lng_sum"] / weight, 6),
            "total_cases": total_cases,
            "recent_24h": row["recent_24h"],
            "previous_24h": row["previous_24h"],
            "growth_percent": growth,
            "activity_percent": activity_percent,
            "decay_percent": _decay_percent(row["recent_24h"], row["previous_24h"]),
            "trend_status": _trend_status(growth, row["recent_24h"], row["previous_24h"]),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "surveillance_index": surveillance_index,
            "resource_pressure": resource_pressure,
            "stock_pressure": stock_pressure,
            "market_signal": _market_signal(dominant_disease, dominant_symptom, stock_pressure),
            "restock_window": _restock_window(growth, risk_level),
            "hospital_load_estimate": hospital_load_estimate,
            "triage_priority": _triage_priority(dominant_symptom, risk_level, growth),
            "readiness_level": _readiness_level(hospital_load_estimate),
            "response_priority": _response_priority(risk_level, growth),
            "symptoms": symptom_breakdown,
            "probable_diseases": probable_diseases,
            "dominant_symptom": dominant_symptom,
            "dominant_disease": dominant_disease,
            "radius": int(28000 + ((total_cases / max_total) * 90000)) if max_total else 28000,
            "focus_message": _focus_message(dominant_symptom, dominant_disease, risk_level),
            "alert_stage": _alert_stage(risk_level, growth, total_cases),
            "public_recommendation": _public_recommendation(dominant_disease, dominant_symptom, risk_level),
            "market_recommendation": _market_recommendation(dominant_disease, dominant_symptom),
            "hospital_recommendation": _hospital_recommendation(dominant_disease, dominant_symptom, risk_level),
            "government_recommendation": _government_recommendation(dominant_disease, dominant_symptom, risk_level, growth, total_cases),
            "strategic_tags": _strategic_tags(dominant_disease, dominant_symptom, growth, risk_level),
            "government_tags": _government_tags(dominant_disease, dominant_symptom, growth, risk_level),
        })

    return states


def _build_timeline():
    now = timezone.now()
    start = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        RegistroSintoma.objects.filter(data_registro__gte=start)
        .extra(select={"day": "date(data_registro)"})
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    totals_by_day = {str(row["day"]): int(row["total"]) for row in rows}
    timeline = []

    for offset in range(14):
        day = (start + timedelta(days=offset)).date().isoformat()
        timeline.append({
            "date": day,
            "total": totals_by_day.get(day, 0),
        })

    recent_window = timeline[-7:]
    baseline_window = timeline[:-7] or timeline[-7:]
    baseline_average = sum(item["total"] for item in baseline_window) / max(len(baseline_window), 1)
    current_total = recent_window[-1]["total"] if recent_window else 0

    return {
        "series": timeline,
        "today_total": current_total,
        "epidemic_threshold": round(baseline_average * 1.35, 2),
        "baseline_average": round(baseline_average, 2),
        "above_threshold": current_total > (baseline_average * 1.35),
    }


def _build_data_quality():
    summary = RegistroSintoma.objects.aggregate(
        total=Count("id"),
        suspected=Count("id", filter=Q(suspeito=True)),
        avg_confidence=Avg("confianca"),
    )
    total = int(summary["total"] or 0)
    suspected = int(summary["suspected"] or 0)
    avg_confidence = float(summary["avg_confidence"] or 0.0)

    return {
        "total_reports": total,
        "suspected_reports": suspected,
        "suspected_rate": _safe_pct(suspected, total),
        "avg_confidence": round(avg_confidence, 2),
        "validated_reports": max(total - suspected, 0),
    }


def _top_value_counts(field_name, label, limit=5):
    rows = (
        RegistroSintoma.objects.exclude(**{f"{field_name}__isnull": True})
        .exclude(**{field_name: ""})
        .values(field_name)
        .annotate(total=Count("id"))
        .order_by("-total")[:limit]
    )
    return [
        {"label": row[field_name], "total": int(row["total"]), "type": label}
        for row in rows
    ]


def _build_operational_profiles():
    return {
        "groups": _top_value_counts("grupo", "grupo"),
        "classifications": _top_value_counts("classificacao", "classificacao"),
        "confirmed_diseases": _top_value_counts("doenca_confirmada", "doenca"),
    }


def _aggregate_overview(layers):
    bairros = layers["bairros"]
    total_cases = sum(area["total_cases"] for area in bairros)
    active_areas = len(bairros)
    symptoms = defaultdict(int)
    disease_totals = defaultdict(int)
    active_disease_totals = defaultdict(float)
    growth_values = []
    highest_risk = 0.0

    for area in bairros:
        growth_values.append(area["growth_percent"])
        highest_risk = max(highest_risk, area["risk_score"])

        for symptom in area["symptoms"]:
            symptoms[symptom["key"]] += symptom["count"]

        for disease in area["probable_diseases"]:
            disease_totals[disease["name"]] += disease["estimated_cases"]
            recency_weight = 0.25 + min(area["activity_percent"] / 100, 1.0)
            active_disease_totals[disease["name"]] += disease["estimated_cases"] * recency_weight

    symptom_breakdown = _serialize_symptoms(symptoms, total_cases)
    disease_breakdown = []
    disease_total_sum = sum(disease_totals.values()) or 1
    active_disease_total_sum = sum(active_disease_totals.values()) or 1

    for disease_name, estimated_cases in sorted(
        disease_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        disease_breakdown.append({
            "name": disease_name,
            "estimated_cases": int(estimated_cases),
            "probability": _safe_pct(estimated_cases, disease_total_sum),
            "active_probability": round((active_disease_totals[disease_name] / active_disease_total_sum) * 100, 2),
        })

    timeline = _build_timeline()
    data_quality = _build_data_quality()
    operational_profiles = _build_operational_profiles()
    top_stock_pressure = sorted(bairros, key=lambda area: (area["stock_pressure"], area["growth_percent"]), reverse=True)[:5]
    top_hospital_load = sorted(bairros, key=lambda area: (area["hospital_load_estimate"], area["growth_percent"]), reverse=True)[:5]

    overview = {
        "total_cases": total_cases,
        "active_areas": active_areas,
        "growth_percent": round(sum(growth_values) / len(growth_values), 2) if growth_values else 0.0,
        "risk_level": _risk_level(highest_risk),
        "symptoms": symptom_breakdown,
        "probable_diseases": disease_breakdown,
        "top_focuses": sorted(
            bairros,
            key=lambda area: (area["risk_score"], area["total_cases"]),
            reverse=True,
        )[:8],
        "operational_alerts": [
            {
                "title": area["label"],
                "stage": area["alert_stage"],
                "risk_level": area["risk_level"],
                "message": area["public_recommendation"],
            }
            for area in sorted(
                bairros,
                key=lambda area: (area["risk_score"], area["growth_percent"], area["total_cases"]),
                reverse=True,
            )[:5]
        ],
        "government_briefing": [
            {
                "title": area["label"],
                "priority": area["response_priority"],
                "surveillance_index": area["surveillance_index"],
                "resource_pressure": area["resource_pressure"],
                "message": area["government_recommendation"],
            }
            for area in sorted(
                bairros,
                key=lambda area: (area["response_priority"], -area["surveillance_index"], -area["resource_pressure"]),
            )[:5]
        ],
        "timeline": timeline,
        "data_quality": data_quality,
        "operational_profiles": operational_profiles,
        "market_overview": {
            "priority_zones": [
                {
                    "label": area["label"],
                    "stock_pressure": area["stock_pressure"],
                    "restock_window": area["restock_window"],
                    "signal": area["market_signal"],
                }
                for area in top_stock_pressure
            ],
        },
        "hospital_overview": {
            "priority_zones": [
                {
                    "label": area["label"],
                    "hospital_load_estimate": area["hospital_load_estimate"],
                    "triage_priority": area["triage_priority"],
                    "readiness_level": area["readiness_level"],
                }
                for area in top_hospital_load
            ],
        },
        "territorial_coverage": {
            "states": len({area["estado"] for area in bairros if area.get("estado")}),
            "cities": len({area["cidade"] for area in bairros if area.get("cidade")}),
            "neighborhoods": len({area["nome"] for area in bairros if area.get("nome")}),
        },
        "institutional_note": (
            "Indicadores sociodemograficos completos, mortalidade, letalidade e denominadores "
            "por 100 mil dependem de integracoes oficiais adicionais com bases populacionais e sistemas de saude."
        ),
    }

    return overview


def build_panorama_payload():
    now = time()

    if (
        _PANORAMA_CACHE["payload"] is not None
        and now - _PANORAMA_CACHE["created_at"] < _CACHE_TTL_SECONDS
    ):
        return _PANORAMA_CACHE["payload"]

    bairros = _serialize_layer("bairro", ("estado", "cidade", "bairro"))
    municipios = _serialize_layer("municipio", ("estado", "cidade"))
    estados = _build_state_layer(municipios)
    layers = {
        "bairros": bairros,
        "municipios": municipios,
        "estados": estados,
    }

    payload = {
        "generated_at": timezone.now().isoformat(),
        "overview": _aggregate_overview(layers),
        "layers": layers,
        "filters": {
            "estados": sorted({area["estado"] for area in layers["bairros"] if area.get("estado")}),
            "cidades": sorted({area["cidade"] for area in layers["bairros"] if area.get("cidade")}),
        },
    }

    _PANORAMA_CACHE["created_at"] = now
    _PANORAMA_CACHE["payload"] = payload
    return payload


def panorama_epidemiologico(request):
    return JsonResponse(build_panorama_payload())


def exportar_briefing_governo(request):
    payload = build_panorama_payload()
    briefing = payload.get("overview", {}).get("government_briefing", [])
    export_format = (request.GET.get("format") or "json").lower()

    if export_format == "csv":
        lines = ["titulo,prioridade,vigilancia,pressao,mensagem"]
        for item in briefing:
            row = [
                str(item.get("title", "")).replace(",", " "),
                str(item.get("priority", "")),
                str(item.get("surveillance_index", "")),
                str(item.get("resource_pressure", "")),
                str(item.get("message", "")).replace(",", " "),
            ]
            lines.append(",".join(row))

        response = HttpResponse("\n".join(lines), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="briefing_governo.csv"'
        return response

    response = HttpResponse(
        json.dumps(
            {
                "generated_at": payload.get("generated_at"),
                "institutional_note": payload.get("overview", {}).get("institutional_note"),
                "government_briefing": briefing,
                "timeline": payload.get("overview", {}).get("timeline", {}),
                "territorial_coverage": payload.get("overview", {}).get("territorial_coverage", {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = 'attachment; filename="briefing_governo.json"'
    return response
