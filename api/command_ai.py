from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .epidemiologia import build_panorama_payload
from .models import AuditoriaInstitucional, Empresa
from .planos import detalhes_pacote, normalizar_codigo_pacote


PRODUCT_NAME = "Sala de Decisão IA"


SECTOR_CONFIG = {
    "governo": {
        "title": "Sala de Decisão IA - Governo",
        "subtitle": "vigilância territorial, risco populacional, alertas oficiais e resposta institucional",
        "audience": "governo",
        "eyebrow": "Sala de situação governamental",
        "panel_title": "Plano público de resposta",
        "recommendation_field": "government_recommendation",
        "impact_field": "resource_pressure",
        "impact_label": "pressão operacional pública",
        "primary_metric": "surveillance_index",
        "action_steps": [
            "Validar foco com equipe técnica local antes de qualquer comunicação pública.",
            "Priorizar vigilância territorial e rede de atenção primária na área indicada.",
            "Preparar alerta oficial apenas se crescimento, contexto e revisão humana sustentarem risco real.",
        ],
    },
    "farmacia": {
        "title": "Sala de Decisão IA - Farmácias e Laboratórios",
        "subtitle": "abastecimento, demanda por sintomas, kits, testes, insumos e orientação responsável",
        "audience": "farmácias, drogarias, redes farmacêuticas e laboratórios",
        "eyebrow": "Inteligência de abastecimento",
        "panel_title": "Plano farmacêutico e laboratorial",
        "recommendation_field": "market_recommendation",
        "impact_field": "stock_pressure",
        "impact_label": "pressão de estoque",
        "primary_metric": "stock_pressure",
        "action_steps": [
            "Revisar estoque dos itens associados ao grupo epidemiológico dominante.",
            "Remanejar produtos entre unidades próximas de áreas com maior aceleração.",
            "Preparar orientação responsável de encaminhamento sem diagnóstico no balcão.",
        ],
    },
    "hospital": {
        "title": "Sala de Decisão IA - Hospitais",
        "subtitle": "triagem, pronto atendimento, leitos, escala, insumos críticos e risco assistencial",
        "audience": "hospitais, clínicas, pronto atendimento e redes assistenciais",
        "eyebrow": "Inteligência assistencial",
        "panel_title": "Plano hospitalar de prontidão",
        "recommendation_field": "hospital_recommendation",
        "impact_field": "hospital_load_estimate",
        "impact_label": "pressão assistencial",
        "primary_metric": "hospital_load_estimate",
        "action_steps": [
            "Revisar escala de triagem e retaguarda para a janela de maior risco.",
            "Checar insumos críticos ligados ao sintoma dominante e ao grupo provável.",
            "Preparar fluxo de observação e encaminhamento para sinais de gravidade.",
        ],
    },
    "empresa": {
        "title": "Sala de Decisão IA - Empresas",
        "subtitle": "risco territorial, absenteísmo provável, comunicação interna e continuidade operacional",
        "audience": "empresas, operações distribuídas e saúde ocupacional",
        "eyebrow": "Inteligência corporativa",
        "panel_title": "Plano corporativo de prevenção",
        "recommendation_field": "public_recommendation",
        "impact_field": "resource_pressure",
        "impact_label": "pressão operacional",
        "primary_metric": "resource_pressure",
        "action_steps": [
            "Comunicar colaboradores em regiões de maior risco com linguagem preventiva.",
            "Reforçar medidas internas de cuidado, higiene, ventilação e acompanhamento.",
            "Monitorar absenteísmo e ajustar escala onde houver maior exposição territorial.",
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


def _percent_label(value):
    return f"{round(_safe_number(value), 1)}%"


def _score_label(value):
    return f"{round(_safe_number(value), 1)}/100"


def _decision_title(area, setor):
    disease = area.get("dominant_disease") or "padrão indefinido"
    if setor == "governo":
        return f"Priorizar resposta em {area.get('label')} para {disease}"
    if setor == "farmacia":
        return f"Abastecer e preparar atendimento em {area.get('label')} para {disease}"
    if setor == "hospital":
        return f"Elevar prontidão assistencial em {area.get('label')} para {disease}"
    return f"Reduzir impacto operacional em {area.get('label')} para {disease}"


def _impact_phrase(area, setor):
    symptom = area.get("dominant_symptom") or "sintomas"
    disease = area.get("dominant_disease") or "padrão provável"
    if setor == "governo":
        return f"Risco de pressão sobre comunicação pública, atenção básica e vigilância local por {disease}."
    if setor == "farmacia":
        return f"Possível alta de procura por itens, testes, orientação farmacêutica e suporte laboratorial ligados a {symptom.lower()} e {disease}."
    if setor == "hospital":
        return f"Possível aumento de triagem, observação, insumos críticos e pressão assistencial associada a {symptom.lower()}."
    return f"Possível aumento de absenteísmo e necessidade de comunicação preventiva por {disease}."


def _pharmacy_items(area):
    disease = area.get("dominant_disease")
    symptom = area.get("dominant_symptom")
    if disease in {"COVID", "Gripe"} or symptom in {"Tosse", "Falta de Ar"}:
        return [
            "testes respiratórios quando aplicável",
            "máscaras e itens de proteção",
            "antitérmicos e suporte para sintomas respiratórios",
            "materiais de orientação e encaminhamento",
        ]
    if disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        return [
            "soro de reidratação e itens de hidratação",
            "repelentes e proteção contra vetores",
            "analgésicos conforme orientação farmacêutica",
            "materiais de orientação sobre sinais de alarme",
        ]
    if disease in {"Leptospirose", "Malaria"}:
        return [
            "hidratação oral",
            "antitérmicos seguros",
            "materiais de encaminhamento responsável",
            "triagem para procura de atendimento profissional",
        ]
    return [
        "itens ligados ao sintoma dominante",
        "materiais de orientação preventiva",
        "produtos de suporte à hidratação e cuidado básico",
        "fluxo de encaminhamento para casos de gravidade",
    ]


def _hospital_resources(area):
    disease = area.get("dominant_disease")
    symptom = area.get("dominant_symptom")
    if symptom == "Falta de Ar" or disease in {"COVID", "Gripe", "Bronquite"}:
        return ["triagem respiratória", "oxigênio", "observação", "retaguarda clínica"]
    if disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela", "Leptospirose", "Malaria"}:
        return ["hidratação", "analgesia", "observação", "fluxo para sinais de alarme"]
    if disease in {"Meningite", "Sarampo"}:
        return ["triagem imediata", "isolamento quando indicado", "protocolo clínico", "notificação responsável"]
    return ["triagem", "equipe de retaguarda", "insumos de pronto atendimento", "observação clínica"]


def _priority_items(area, setor):
    if setor == "farmacia":
        return _pharmacy_items(area)
    if setor == "hospital":
        return _hospital_resources(area)
    if setor == "governo":
        return [
            "vigilância territorial",
            "atenção primária",
            "comunicação pública revisada",
            "auditoria do alerta",
        ]
    return [
        "comunicação interna",
        "monitoramento de absenteísmo",
        "continuidade operacional",
        "orientação preventiva",
    ]


def _sector_metrics(area, setor):
    if setor == "farmacia":
        return [
            {
                "label": "Pressão de estoque",
                "value": _score_label(area.get("stock_pressure")),
                "detail": "prioridade de compra e remanejamento por área de procura",
            },
            {
                "label": "Janela de reposição",
                "value": area.get("restock_window") or "monitorar",
                "detail": "momento sugerido para antecipar abastecimento",
            },
            {
                "label": "Sinal de mercado",
                "value": area.get("market_signal") or "demanda em observação",
                "detail": "leitura de provável procura por balcão, testes e suporte",
            },
        ]
    if setor == "hospital":
        return [
            {
                "label": "Carga assistencial",
                "value": _score_label(area.get("hospital_load_estimate")),
                "detail": "pressão provável sobre PA, triagem e observação",
            },
            {
                "label": "Prioridade de triagem",
                "value": area.get("triage_priority") or "monitorar",
                "detail": "nível sugerido para organização de fluxo clínico",
            },
            {
                "label": "Prontidão",
                "value": area.get("readiness_level") or "vigilância",
                "detail": "estado operacional recomendado para equipe e insumos",
            },
        ]
    if setor == "governo":
        return [
            {
                "label": "Índice de vigilância",
                "value": _score_label(area.get("surveillance_index")),
                "detail": "prioridade territorial para investigação e ação pública",
            },
            {
                "label": "Estágio de alerta",
                "value": area.get("alert_stage") or "vigilância ativa",
                "detail": "nível sugerido antes de comunicação oficial",
            },
            {
                "label": "Resposta pública",
                "value": area.get("response_priority") or "monitorar",
                "detail": "ordem de prioridade para equipes de campo e gestão",
            },
        ]
    return [
        {
            "label": "Pressão operacional",
            "value": _score_label(area.get("resource_pressure")),
            "detail": "risco de impacto em equipe, escala e operação",
        },
        {
            "label": "Crescimento local",
            "value": _percent_label(area.get("growth_percent")),
            "detail": "variação recente dos sinais agregados na região",
        },
        {
            "label": "Foco territorial",
            "value": area.get("label") or "sem foco definido",
            "detail": "região para comunicação preventiva e acompanhamento",
        },
    ]


def _sector_playbook(area, setor):
    territory = area.get("label") or "área priorizada"
    disease = area.get("dominant_disease") or "padrão provável"
    symptom = str(area.get("dominant_symptom") or "sintomas").lower()
    recommendation = area.get("market_recommendation") or area.get("hospital_recommendation") or area.get("government_recommendation") or area.get("public_recommendation") or "manter vigilância ativa"
    if setor == "farmacia":
        return [
            {
                "title": "Abastecimento",
                "items": [
                    f"Priorizar {recommendation} nas unidades próximas a {territory}.",
                    f"Antecipar compra ou remanejamento conforme janela: {area.get('restock_window') or 'monitorar diariamente'}.",
                    "Separar itens críticos por unidade para evitar ruptura silenciosa de estoque.",
                ],
            },
            {
                "title": "Laboratórios e testes",
                "items": [
                    f"Preparar capacidade para procura associada a {disease} e {symptom}.",
                    "Sinalizar aumento de demanda por testes ou exames sem prometer diagnóstico pelo app.",
                    "Registrar feedback comercial e operacional para calibrar a próxima leitura da IA.",
                ],
            },
            {
                "title": "Balcão responsável",
                "items": [
                    "Orientar busca de atendimento profissional diante de sinais de gravidade.",
                    "Evitar mensagem comercial baseada em dado individual ou localização individual.",
                    "Usar comunicação educativa e preventiva, não diagnóstico.",
                ],
            },
        ]
    if setor == "hospital":
        return [
            {
                "title": "Triagem e pronto atendimento",
                "items": [
                    f"Reforçar fluxo de triagem para {symptom} em pacientes vindos de {territory}.",
                    f"Usar prioridade: {area.get('triage_priority') or 'monitorar'} para ajustar recepção e classificação.",
                    "Separar comunicação interna para equipe sem divulgar dado individual da população.",
                ],
            },
            {
                "title": "Leitos, equipe e retaguarda",
                "items": [
                    f"Avaliar escala e retaguarda clínica na janela { _urgency(area).get('window') }.",
                    f"Elevar prontidão operacional para {area.get('readiness_level') or 'vigilância'} se o crescimento persistir.",
                    "Preparar protocolo de observação e encaminhamento para sinais de gravidade.",
                ],
            },
            {
                "title": "Insumos críticos",
                "items": [
                    f"Checar disponibilidade de {', '.join(_hospital_resources(area)[:3])}.",
                    "Cruzar consumo interno com o avanço territorial antes de compra emergencial.",
                    "Registrar se a recomendação bateu com a pressão real do atendimento.",
                ],
            },
        ]
    if setor == "governo":
        return [
            {
                "title": "Vigilância territorial",
                "items": [
                    f"Priorizar equipe técnica em {territory} antes de ampliar alerta público.",
                    f"Conferir crescimento de {area.get('growth_percent', 0)}% com sinais oficiais ou equipe local.",
                    "Manter trilha de auditoria para toda decisão de comunicação institucional.",
                ],
            },
            {
                "title": "Comunicação pública",
                "items": [
                    f"Preparar mensagem preventiva sobre {disease} com linguagem de orientação, não diagnóstico.",
                    "Publicar alerta somente após revisão humana e contexto epidemiológico suficiente.",
                    "Definir responsável, validade do alerta e critério de encerramento.",
                ],
            },
            {
                "title": "Rede de atendimento",
                "items": [
                    "Avisar atenção primária e vigilância local sobre aumento de procura possível.",
                    "Monitorar redução sustentada antes de baixar nível de resposta.",
                    "Cruzar sinais populares, fontes oficiais e feedback de campo.",
                ],
            },
        ]
    return [
        {
            "title": "Operação e pessoas",
            "items": [
                f"Comunicar equipes em {territory} com orientação preventiva objetiva.",
                "Monitorar absenteísmo e sintomas reportados sem expor dado individual.",
                "Preparar ajuste de escala se o crescimento permanecer alto.",
            ],
        },
        {
            "title": "Continuidade",
            "items": [
                "Reforçar higiene, ventilação e canal de orientação interno.",
                "Evitar decisões disciplinares ou comerciais baseadas em dado sensível.",
                "Registrar feedback da gestão para calibrar a leitura da IA.",
            ],
        },
    ]


def _build_recommendation(area, setor, config, data_quality):
    urgency = _urgency(area)
    impact_score = _safe_number(area.get(config["impact_field"]))
    recommendation = area.get(config["recommendation_field"]) or area.get("public_recommendation") or "Manter vigilância ativa."
    evidence = [
        f"Risco {str(area.get('risk_level', 'BAIXO')).lower()} com score {area.get('risk_score', 0)}.",
        f"Crescimento recente de {area.get('growth_percent', 0)}% e {area.get('recent_24h', 0)} sinais nas últimas 24h.",
        f"Sintoma dominante: {area.get('dominant_symptom')}; padrão provável: {area.get('dominant_disease')}.",
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
        "priority_items": _priority_items(area, setor),
        "sector_metrics": _sector_metrics(area, setor),
        "sector_playbook": _sector_playbook(area, setor),
        "confidence": _confidence(area, data_quality),
        "evidence": evidence,
        "safeguard": "Apoio à decisão operacional. Não substitui diagnóstico médico, vigilância oficial ou validação humana.",
    }


def _build_summary(empresa, setor, config, overview, recommendations):
    top = recommendations[0] if recommendations else None
    if top:
        if setor == "farmacia":
            narrative = (
                f"A IA está lendo {top['territory']} como prioridade para abastecimento, balcão e laboratório. "
                f"Direção sugerida: {top['recommended_action']}"
            )
        elif setor == "hospital":
            narrative = (
                f"A IA está lendo {top['territory']} como prioridade para triagem, equipe, leitos e insumos. "
                f"Direção sugerida: {top['recommended_action']}"
            )
        elif setor == "governo":
            narrative = (
                f"A IA está lendo {top['territory']} como prioridade para vigilância territorial e resposta pública. "
                f"Direção sugerida: {top['recommended_action']}"
            )
        else:
            narrative = (
                f"A IA está lendo {top['territory']} como prioridade para prevenção corporativa e continuidade operacional. "
                f"Direção sugerida: {top['recommended_action']}"
            )
    else:
        narrative = "Sem sinais suficientes para recomendar resposta operacional prioritária neste momento."
    return {
        "title": config["title"],
        "subtitle": config["subtitle"],
        "company": empresa.nome,
        "setor": setor,
        "product_name": PRODUCT_NAME,
        "audience": config["audience"],
        "eyebrow": config["eyebrow"],
        "panel_title": config["panel_title"],
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
            "A IA registra feedback humano autorizado para calibrar recomendações, "
            "prioridades e confiança sem expor dado individual da população."
        ),
    }


def _first_sector_metric_value(recommendation):
    metrics = recommendation.get("sector_metrics") or []
    if not metrics:
        return "0/100"
    return metrics[0].get("value", "0/100")


def _executive_cards(setor, overview, data_quality, recommendations):
    top = recommendations[0] if recommendations else {}
    cards = [
        {
            "label": "Confiança média",
            "value": f"{round(_safe_number(data_quality.get('avg_confidence')) * 100)}%",
            "detail": "média dos sinais usados pelo motor atual",
        },
        {
            "label": "Sinais suspeitos",
            "value": f"{data_quality.get('suspected_rate', 0)}%",
            "detail": "taxa considerada na cautela da recomendação",
        },
    ]
    if setor == "farmacia":
        cards.extend([
            {
                "label": "Pressão de estoque",
                "value": _first_sector_metric_value(top) if top else "0/100",
                "detail": "força da demanda para compra, remanejamento e ruptura provável",
            },
            {
                "label": "Itens prioritários",
                "value": str(len(top.get("priority_items", []))) if top else "0",
                "detail": "categorias que a farmácia deve revisar primeiro",
            },
        ])
    elif setor == "hospital":
        cards.extend([
            {
                "label": "Carga assistencial",
                "value": _first_sector_metric_value(top) if top else "0/100",
                "detail": "pressão provável sobre pronto atendimento e triagem",
            },
            {
                "label": "Recursos críticos",
                "value": str(len(top.get("priority_items", []))) if top else "0",
                "detail": "insumos e fluxos que merecem checagem operacional",
            },
        ])
    elif setor == "governo":
        cards.extend([
            {
                "label": "Cobertura territorial",
                "value": str(overview.get("territorial_coverage", {}).get("cities", 0)),
                "detail": "municípios com sinais agregados",
            },
            {
                "label": "Áreas ativas",
                "value": str(overview.get("active_areas", 0)),
                "detail": "focos territoriais em leitura epidemiológica",
            },
        ])
    else:
        cards.extend([
            {
                "label": "Áreas ativas",
                "value": str(overview.get("active_areas", 0)),
                "detail": "territórios para prevenção e comunicação interna",
            },
            {
                "label": "Crescimento",
                "value": _percent_label(overview.get("growth_percent")),
                "detail": "velocidade recente dos sinais agregados",
            },
        ])
    return cards


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
        "executive_cards": _executive_cards(setor, overview, data_quality, recommendations),
        "learning": _learning_block(empresa),
        "safeguards": [
            "Não usa dado individual para propaganda ou targeting comercial.",
            "Não altera mapa, sintomas, alertas oficiais ou regras existentes.",
            "Não publica alerta público sem revisão humana e governança apropriada.",
            "Usa sinais agregados para priorização operacional e planejamento setorial.",
        ],
        "source": {
            "engine": "SolusCRT panorama epidemiológico",
            "generated_from": "sinais agregados, série temporal, sintomas dominantes e fontes oficiais quando disponíveis",
        },
    }
