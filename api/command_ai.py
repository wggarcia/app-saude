from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .epidemiologia import build_panorama_payload
from .models import AuditoriaInstitucional, Empresa
from .planos import detalhes_pacote, normalizar_codigo_pacote


SECTOR_CONFIG = {
    "governo": {
        "title": "Command AI Governo",
        "subtitle": "prioridade territorial, pressao de recursos e plano de resposta institucional",
        "recommendation_field": "government_recommendation",
        "impact_field": "resource_pressure",
        "impact_label": "pressao operacional publica",
        "primary_metric": "surveillance_index",
        "action_steps": [
            "Validar foco com equipe tecnica local antes de comunicacao publica.",
            "Priorizar vigilancia territorial e rede de atencao primaria na area indicada.",
            "Preparar alerta oficial se crescimento e contexto sustentarem risco real.",
        ],
    },
    "farmacia": {
        "title": "Command AI Farmacia",
        "subtitle": "previsao de demanda, janela de reposicao e prioridade de estoque preventivo",
        "recommendation_field": "market_recommendation",
        "impact_field": "stock_pressure",
        "impact_label": "pressao de estoque",
        "primary_metric": "stock_pressure",
        "action_steps": [
            "Revisar estoque dos itens associados ao grupo epidemiologico dominante.",
            "Remanejar produtos entre unidades proximas de areas com maior aceleracao.",
            "Preparar orientacao responsavel de encaminhamento sem diagnostico no balcao.",
        ],
    },
    "hospital": {
        "title": "Command AI Hospital",
        "subtitle": "pressao assistencial, triagem, prontidao de equipe e insumos criticos",
        "recommendation_field": "hospital_recommendation",
        "impact_field": "hospital_load_estimate",
        "impact_label": "pressao assistencial",
        "primary_metric": "hospital_load_estimate",
        "action_steps": [
            "Revisar escala de triagem e retaguarda para a janela de maior risco.",
            "Checar insumos criticos ligados ao sintoma dominante e ao grupo provavel.",
            "Preparar fluxo de observacao e encaminhamento para sinais de gravidade.",
        ],
    },
    "empresa": {
        "title": "Command AI Empresa",
        "subtitle": "risco territorial, absenteismo provavel e resposta preventiva corporativa",
        "recommendation_field": "public_recommendation",
        "impact_field": "resource_pressure",
        "impact_label": "pressao operacional",
        "primary_metric": "resource_pressure",
        "action_steps": [
            "Comunicar colaboradores em regioes de maior risco com linguagem preventiva.",
            "Reforcar medidas internas de cuidado, higiene, ventilacao e acompanhamento.",
            "Monitorar absenteismo e ajustar escala onde houver maior exposicao territorial.",
        ],
    },
}


def _company_sector(empresa):
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return "governo"
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return pacote.get("setor") or "empresa"


def _safe_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _urgency(area):
    level = area.get("risk_level")
    growth = _safe_number(area.get("growth_percent"))
    if level == "CRITICO" or growth >= 80:
        return {"label": "Agora", "level": "critico", "window": "0-24h"}
    if level == "ALTO" or growth >= 40:
        return {"label": "Prioritario", "level": "alto", "window": "24-48h"}
    if level == "MODERADO" or growth >= 12:
        return {"label": "Monitorar", "level": "moderado", "window": "3-7 dias"}
    return {"label": "Observacao", "level": "baixo", "window": "7-14 dias"}


def _projection(area):
    total = int(area.get("total_cases") or 0)
    growth = _safe_number(area.get("growth_percent"))
    growth_factor = max(min(growth, 120), -70) / 100
    if growth_factor >= 0:
        projected_7 = round(total * (1 + growth_factor * 0.16))
        projected_14 = round(total * (1 + growth_factor * 0.32))
        projected_30 = round(total * (1 + growth_factor * 0.55))
        tendency = "expansao"
    else:
        projected_7 = round(total * (1 + growth_factor * 0.08))
        projected_14 = round(total * (1 + growth_factor * 0.16))
        projected_30 = round(total * (1 + growth_factor * 0.28))
        tendency = "desaceleracao"
    return {
        "tendency": tendency,
        "horizons": [
            {"label": "7 dias", "estimated_signals": max(projected_7, 0)},
            {"label": "14 dias", "estimated_signals": max(projected_14, 0)},
            {"label": "30 dias", "estimated_signals": max(projected_30, 0)},
        ],
    }


def _confidence(area, data_quality):
    total = int(area.get("total_cases") or 0)
    recent = int(area.get("recent_24h") or 0)
    avg_confidence = _safe_number(data_quality.get("avg_confidence"), 0.75)
    suspected_rate = _safe_number(data_quality.get("suspected_rate"))
    score = 56 + (avg_confidence * 24) - (suspected_rate * 0.18)
    if total >= 50:
        score += 8
    elif total >= 15:
        score += 4
    if recent > 0:
        score += 5
    if area.get("risk_level") in {"ALTO", "CRITICO"}:
        score += 4
    if total < 5:
        score = min(score, 64)
    return int(max(35, min(round(score), 94)))


def _score_area(area, config):
    risk = _safe_number(area.get("risk_score"))
    growth = max(_safe_number(area.get("growth_percent")), 0)
    impact = _safe_number(area.get(config["impact_field"]))
    recent = _safe_number(area.get("recent_24h"))
    return round((risk * 0.42) + (impact * 0.36) + (growth * 0.16) + (recent * 0.06), 2)


def _decision_title(area, setor):
    disease = area.get("dominant_disease") or "padrao indefinido"
    if setor == "governo":
        return f"Priorizar resposta em {area.get('label')} para {disease}"
    if setor == "farmacia":
        return f"Preparar demanda em {area.get('label')} para {disease}"
    if setor == "hospital":
        return f"Elevar prontidao em {area.get('label')} para {disease}"
    return f"Reduzir impacto operacional em {area.get('label')} para {disease}"


def _impact_phrase(area, setor):
    symptom = area.get("dominant_symptom") or "sintomas"
    disease = area.get("dominant_disease") or "padrao provavel"
    if setor == "governo":
        return f"Risco de pressao sobre comunicacao publica, atencao basica e vigilancia local por {disease}."
    if setor == "farmacia":
        return f"Possivel alta de procura por itens ligados a {symptom.lower()} e {disease}."
    if setor == "hospital":
        return f"Possivel aumento de triagem e demanda assistencial associada a {symptom.lower()}."
    return f"Possivel aumento de absenteismo e necessidade de comunicacao preventiva por {disease}."


def _build_recommendation(area, setor, config, data_quality):
    urgency = _urgency(area)
    impact_score = _safe_number(area.get(config["impact_field"]))
    recommendation = area.get(config["recommendation_field"]) or area.get("public_recommendation") or "Manter vigilancia ativa."
    evidence = [
        f"Risco {str(area.get('risk_level', 'BAIXO')).lower()} com score {area.get('risk_score', 0)}.",
        f"Crescimento recente de {area.get('growth_percent', 0)}% e {area.get('recent_24h', 0)} sinais nas ultimas 24h.",
        f"Sintoma dominante: {area.get('dominant_symptom')}; padrao provavel: {area.get('dominant_disease')}.",
    ]
    return {
        "id": f"{setor}:{area.get('id')}",
        "title": _decision_title(area, setor),
        "territory": area.get("label"),
        "level": area.get("level"),
        "city": area.get("cidade"),
        "state": area.get("estado"),
        "risk_level": area.get("risk_level"),
        "trend_status": area.get("trend_status"),
        "dominant_symptom": area.get("dominant_symptom"),
        "dominant_disease": area.get("dominant_disease"),
        "impact_label": config["impact_label"],
        "impact_score": round(impact_score, 2),
        "decision_score": _score_area(area, config),
        "urgency": urgency,
        "projection": _projection(area),
        "impact": _impact_phrase(area, setor),
        "recommended_action": recommendation,
        "action_steps": config["action_steps"],
        "confidence": _confidence(area, data_quality),
        "evidence": evidence,
        "safeguard": "Apoio a decisao operacional. Nao substitui diagnostico medico, vigilancia oficial ou validacao humana.",
    }


def _build_summary(empresa, setor, config, overview, recommendations):
    top = recommendations[0] if recommendations else None
    if top:
        narrative = (
            f"{config['title']} identificou {top['territory']} como prioridade atual. "
            f"Acao sugerida: {top['recommended_action']}"
        )
    else:
        narrative = "Sem sinais suficientes para recomendar resposta operacional prioritaria neste momento."
    return {
        "title": config["title"],
        "subtitle": config["subtitle"],
        "company": empresa.nome,
        "setor": setor,
        "risk_level": overview.get("risk_level", "BAIXO"),
        "total_cases": overview.get("total_cases", 0),
        "active_areas": overview.get("active_areas", 0),
        "growth_percent": overview.get("growth_percent", 0),
        "top_decision": narrative,
    }


def _learning_block(empresa):
    since = timezone.now() - timedelta(days=30)
    total_feedback = AuditoriaInstitucional.objects.filter(
        empresa=empresa,
        acao="command_ai_feedback",
        criado_em__gte=since,
    ).count()
    return {
        "mode": "human_feedback_loop",
        "feedback_30d": total_feedback,
        "message": (
            "A IA registra feedback humano autorizado para calibrar recomendacoes, "
            "prioridades e confianca sem expor dado individual da populacao."
        ),
    }


def build_command_ai_payload(empresa, limit=6):
    setor = _company_sector(empresa)
    config = SECTOR_CONFIG.get(setor, SECTOR_CONFIG["empresa"])
    pacote_codigo = normalizar_codigo_pacote(empresa.pacote_codigo)
    pacote = detalhes_pacote(pacote_codigo)
    panorama = build_panorama_payload()
    overview = panorama.get("overview", {})
    layers = panorama.get("layers", {})
    data_quality = overview.get("data_quality", {})
    candidates = list(layers.get("bairros") or layers.get("municipios") or layers.get("estados") or [])
    candidates.sort(key=lambda area: _score_area(area, config), reverse=True)
    recommendations = [
        _build_recommendation(area, setor, config, data_quality)
        for area in candidates[:limit]
    ]
    return {
        "generated_at": timezone.now().isoformat(),
        "mode": "read_only_decision_layer",
        "feature_status": "premium_preview",
        "package": {
            "code": pacote_codigo,
            "label": pacote.get("label"),
            "setor": pacote.get("setor"),
        },
        "summary": _build_summary(empresa, setor, config, overview, recommendations),
        "recommendations": recommendations,
        "executive_cards": [
            {
                "label": "Confianca media",
                "value": f"{round(_safe_number(data_quality.get('avg_confidence')) * 100)}%",
                "detail": "media dos sinais usados pelo motor atual",
            },
            {
                "label": "Sinais suspeitos",
                "value": f"{data_quality.get('suspected_rate', 0)}%",
                "detail": "taxa considerada na cautela da recomendacao",
            },
            {
                "label": "Cobertura territorial",
                "value": str(overview.get("territorial_coverage", {}).get("cities", 0)),
                "detail": "municipios com sinais agregados",
            },
        ],
        "learning": _learning_block(empresa),
        "safeguards": [
            "Nao usa dado individual para propaganda ou targeting comercial.",
            "Nao altera mapa, sintomas, alertas oficiais ou regras existentes.",
            "Nao publica alerta publico sem revisao humana e governanca apropriada.",
            "Usa sinais agregados para priorizacao operacional e planejamento.",
        ],
        "source": {
            "engine": "SolusCRT panorama epidemiologico",
            "generated_from": "sinais agregados, serie temporal, sintomas dominantes e fontes oficiais quando disponiveis",
        },
    }
