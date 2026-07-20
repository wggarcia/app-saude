from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone

from .corporativo_ai import build_empresa_corporativo_payload
from .epidemiologia import build_panorama_payload
from .models import AuditoriaInstitucional, Empresa
from .planos import detalhes_pacote, normalizar_codigo_pacote
from .views_enterprise import build_enterprise_command_center_payload


PRODUCT_NAME = "Sala de Decisão IA"


SECTOR_CONFIG = {
    "plano_saude": {
        "title": "Sala de Decisão IA — Plano de Saúde",
        "subtitle": "sinistralidade, risco de beneficiários, programas crônicos, epidemiologia e guias de autorização",
        "audience": "operadoras de plano de saúde, gestores de saúde suplementar",
        "eyebrow": "Inteligência de saúde suplementar",
        "panel_title": "Plano de saúde gerenciada e prevenção",
        "recommendation_field": "market_recommendation",
        "impact_field": "stock_pressure",
        "impact_label": "impacto em sinistralidade",
        "primary_metric": "stock_pressure",
        "action_steps": [
            "Acionar programas de saúde gerenciada para beneficiários de alto risco identificados pela IA.",
            "Revisar filas de autorização de guias para doenças com pressão epidemiológica crescente.",
            "Antecipar abertura de sinistros e reembolsos para doenças dominantes na área de risco.",
        ],
    },
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
        "title": "Sala de Decisão IA - Saúde Corporativa",
        "subtitle": "absenteísmo provável, risco psicossocial, pressão sobre equipes e continuidade operacional",
        "audience": "empresas, operações distribuídas e saúde ocupacional",
        "eyebrow": "Sala de decisão corporativa",
        "panel_title": "Plano corporativo de cuidado e continuidade",
        "recommendation_field": "public_recommendation",
        "impact_field": "resource_pressure",
        "impact_label": "pressão sobre equipes",
        "primary_metric": "resource_pressure",
        "action_steps": [
            "Acionar líderes e RH com comunicação curta, objetiva e preventiva para as equipes mais expostas.",
            "Reforçar pausas, ventilação, higiene, acolhimento e orientação de autocuidado nas áreas priorizadas.",
            "Monitorar absenteísmo, pedidos de apoio e ajuste de escala antes de surgirem afastamentos em cascata.",
        ],
    },
}


def _company_sector(empresa):
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return "governo"
    pacote = detalhes_pacote(empresa.pacote_codigo)
    setor = pacote.get("setor") or "empresa"
    # Mapeamento canônico — garante que cada setor caia na config correta
    _mapa = {
        "plano_saude": "plano_saude",
        "farmacia": "farmacia",
        "hospital": "hospital",
        "governo": "governo",
        "rede": "farmacia",   # rede usa config farmácia (abastecimento/demanda)
        "sst": "empresa",
        "empresa": "empresa",
    }
    return _mapa.get(setor, "empresa")


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
    return f"Possível aumento de fadiga, absenteísmo e pressão sobre líderes e equipes por {disease}."


def _pharmacy_items(area):
    disease = area.get("dominant_disease")
    symptom = area.get("dominant_symptom")
    if disease in {"COVID", "Gripe", "Hantavirose"} or symptom in {"Tosse", "Falta de Ar"}:
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
    if symptom == "Falta de Ar" or disease in {"COVID", "Gripe", "Bronquite", "Hantavirose"}:
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
        "risco psicossocial",
        "absenteísmo provável",
        "continuidade operacional",
        "apoio às lideranças",
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
            "label": "Pressão sobre equipes",
            "value": _score_label(area.get("resource_pressure")),
            "detail": "impacto potencial em energia, escala, continuidade e presença",
        },
        {
            "label": "Absenteísmo provável",
            "value": _percent_label(max(_safe_number(area.get("growth_percent")) * 0.38, 4)),
            "detail": "estimativa de pressão sobre faltas e revezamento se o avanço persistir",
        },
        {
            "label": "Área prioritária",
            "value": area.get("label") or "sem foco definido",
            "detail": "região para cuidado, comunicação gerencial e acompanhamento de times",
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
            "title": "Pessoas e liderança",
            "items": [
                f"Orientar líderes com mensagem curta para equipes expostas em {territory}.",
                "Reforçar acolhimento, pausas e checagem de carga sem expor dado individual.",
                "Priorizar áreas onde sinais podem virar ausência e queda de energia operacional.",
            ],
        },
        {
            "title": "Saúde ocupacional",
            "items": [
                f"Preparar comunicação preventiva ligada a {disease} e {symptom}.",
                "Monitorar pedidos de apoio, fadiga e necessidade de ajuste de escala na semana.",
                "Ativar RH ou SESMT antes de transformar o avanço territorial em afastamento recorrente.",
            ],
        },
        {
            "title": "Continuidade do trabalho",
            "items": [
                "Reforçar ventilação, higiene, flexibilidade operacional e cobertura entre equipes.",
                "Evitar decisões disciplinares baseadas em dado sensível ou inferência individual.",
                "Registrar feedback da gestão para calibrar a leitura corporativa da IA.",
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
                f"A IA está lendo {top['territory']} como prioridade para saúde ocupacional, prevenção e continuidade do trabalho. "
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
        "mode": "human_feedback_registered",
        "feedback_30d": total_feedback,
        "message": (
            "O feedback humano autorizado é registrado para auditoria e revisão da "
            "equipe, sem expor dado individual da população. As recomendações seguem "
            "regras clínicas e epidemiológicas fixas — o feedback não recalibra o motor "
            "automaticamente."
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
                "label": "Áreas expostas",
                "value": str(overview.get("active_areas", 0)),
                "detail": "frentes territoriais que podem impactar equipes e rotina",
            },
            {
                "label": "Risco de ausência",
                "value": _percent_label(max(_safe_number(overview.get("growth_percent")) * 0.34, 4)),
                "detail": "estimativa de pressão sobre presença e cobertura operacional",
            },
        ])
    return cards


def _company_urgency(label):
    normalized = str(label or "baixo").lower()
    if normalized == "critico":
        return {"label": "Agora", "level": "critico", "window": "0-24h"}
    if normalized == "alto":
        return {"label": "Prioritario", "level": "alto", "window": "24-72h"}
    if normalized == "moderado":
        return {"label": "Planejar", "level": "moderado", "window": "7 dias"}
    return {"label": "Estruturar", "level": "baixo", "window": "14 dias"}


def _company_priority_items(action_title):
    title = str(action_title or "").lower()
    if "psicossocial" in title:
        return ["escuta de líderes", "segurança psicológica", "carga emocional", "apoio do gestor"]
    if "fisic" in title:
        return ["ergonomia", "fadiga operacional", "dor corporal", "pausas curtas"]
    if "apoio" in title:
        return ["fila de apoio", "acolhimento", "rota RH/SESMT", "retorno assistido"]
    return ["adesão aos check-ins", "saúde ocupacional", "continuidade operacional", "bem-estar"]


def _company_playbook(action_title, action_summary, company_payload):
    top_signal = company_payload["summary"]["top_signal"]
    return [
        {
            "title": "Liderança imediata",
            "items": [
                "Fazer uma leitura curta de carga, energia e ritmo com a equipe da frente mais exposta.",
                "Reforçar pausas, cobertura entre pares e orientação simples de autocuidado no turno.",
                f"Usar o sinal dominante '{top_signal}' para orientar a conversa sem expor respostas individuais.",
            ],
        },
        {
            "title": "RH e SESMT",
            "items": [
                f"Converter o alerta '{action_title}' em plano semanal com owner claro e prazo curto.",
                "Acionar fluxo de acolhimento, apoio emocional ou ergonomia conforme a natureza do risco.",
                "Registrar se houve necessidade de retorno assistido, cobertura de equipe ou ajuste de escala.",
            ],
        },
        {
            "title": "Continuidade operacional",
            "items": [
                action_summary,
                "Priorizar áreas com energia baixa, fadiga em alta ou pedidos de apoio em crescimento.",
                "Evitar qualquer uso disciplinar dos check-ins ou inferência individual.",
            ],
        },
    ]


def _company_sector_metrics(company_payload, unit, action, support_count):
    risk_score = unit["risk_score"] if unit else {"baixo": 28, "moderado": 48, "alto": 72, "critico": 90}.get(action["urgency"], 28)
    respondents = unit["respondents"] if unit else company_payload["summary"]["respondents"]
    weekly_respondents = company_payload["summary"]["weekly_respondents"]
    return [
        {
            "label": "Risco agregado",
            "value": f"{risk_score}/100",
            "detail": "intensidade combinada de fadiga, pressão emocional, burnout e sinais físicos",
        },
        {
            "label": "Base válida",
            "value": str(respondents),
            "detail": f"respondentes do grupo com leitura anônima válida; semanal {weekly_respondents}",
        },
        {
            "label": "Pedidos de apoio",
            "value": str(support_count),
            "detail": "fila de acolhimento aberta para RH, SESMT ou saúde ocupacional",
        },
    ]


def _build_company_command_ai_payload(empresa, pacote_codigo, pacote, limit=6):
    company_payload = build_empresa_corporativo_payload(empresa)
    respondents = company_payload["summary"]["respondents"]
    support_count = int(next((card["value"] for card in company_payload["executive_cards"] if card["label"] == "Pedidos de apoio"), "0"))
    top_signal = company_payload["summary"]["top_signal"]
    actions = company_payload.get("recommendations") or []
    units = company_payload.get("top_units") or []

    if not actions:
        actions = [{
            "title": "Adesão corporativa insuficiente",
            "urgency": "baixo",
            "summary": "Ainda não há respostas suficientes para leitura confiável de saúde ocupacional.",
            "action": "Abrir campanha de adesão aos check-ins e orientar líderes sobre privacidade e confiança.",
        }]

    recommendations = []
    for index, action in enumerate(actions[:limit]):
        unit = units[index] if index < len(units) else (units[0] if units else None)
        urgency = _company_urgency(action["urgency"])
        risk_score = unit["risk_score"] if unit else {"baixo": 28, "moderado": 48, "alto": 72, "critico": 90}.get(action["urgency"], 28)
        projected_7 = max(1, round(respondents * (risk_score / 100) * 0.22)) if respondents else 0
        projected_14 = max(projected_7, round(projected_7 * 1.2)) if projected_7 else 0
        projected_30 = max(projected_14, round(projected_14 * 1.3)) if projected_14 else 0
        recommendations.append({
            "id": f"empresa:{index}",
            "title": action["title"] if not unit else f"{action['title']} em {unit['name']}",
            "territory": unit["name"] if unit else "Leitura corporativa geral",
            "level": "unidade_corporativa" if unit else "empresa",
            "city": "",
            "state": "",
            "risk_level": (unit["risk_band"].upper() if unit else action["urgency"].upper()),
            "trend_status": "monitorado",
            "dominant_symptom": top_signal,
            "dominant_disease": "Saúde ocupacional",
            "impact_label": "pressão sobre equipes",
            "impact_score": risk_score,
            "decision_score": risk_score,
            "urgency": urgency,
            "projection": {
                "tendency": "pressao_interna",
                "horizons": [
                    {"label": "7 dias", "estimated_signals": projected_7},
                    {"label": "14 dias", "estimated_signals": projected_14},
                    {"label": "30 dias", "estimated_signals": projected_30},
                ],
            },
            "impact": action["summary"],
            "recommended_action": action["action"],
            "action_steps": [
                "Acionar líder direto e RH com leitura curta e objetiva do risco.",
                "Priorizar as equipes com queda de energia, estresse alto ou pedidos de apoio em aberto.",
                "Registrar a resposta e revisar impacto da ação na próxima semana.",
            ],
            "priority_items": _company_priority_items(action["title"]),
            "sector_metrics": _company_sector_metrics(company_payload, unit, action, support_count),
            "sector_playbook": _company_playbook(action["title"], action["summary"], company_payload),
            "confidence": 82 if company_payload["privacy"]["ready"] else 61,
            "evidence": [
                f"Sinal dominante atual: {top_signal}.",
                f"Risco psicossocial e físico lidos a partir de {respondents} check-ins válidos.",
                f"Pedidos de apoio em aberto: {support_count}.",
            ],
            "safeguard": "Apoio à decisão de saúde ocupacional. Não usa dado individual e não substitui validação humana, RH, SESMT ou cuidado profissional.",
        })

    return {
        "generated_at": timezone.now().isoformat(),
        "mode": "occupational_health_decision_layer",
        "feature_status": "corporate_command_center",
        "package": {
            "code": pacote_codigo,
            "label": pacote.get("label"),
            "setor": pacote.get("setor"),
        },
        "summary": {
            "title": "Sala de Decisão Saúde Corporativa",
            "subtitle": "absenteísmo provável, risco psicossocial, pedidos de apoio e continuidade do trabalho",
            "company": empresa.nome,
            "setor": "empresa",
            "product_name": PRODUCT_NAME,
            "audience": "RH, SESMT, liderança e saúde ocupacional",
            "eyebrow": "Centro de decisão para saúde ocupacional",
            "panel_title": "Plano corporativo de cuidado e continuidade",
            "risk_level": next((card["value"] for card in company_payload["executive_cards"] if card["label"] == "Risco psicossocial"), "BAIXO"),
            "total_cases": respondents,
            "active_areas": len(units),
            "growth_percent": support_count,
            "top_decision": company_payload["summary"]["headline"],
        },
        "recommendations": recommendations,
        "executive_cards": [
            {"label": card["label"], "value": card["value"], "detail": card["detail"]}
            for card in company_payload["executive_cards"]
        ],
        "learning": {
            "mode": "corporate_feedback_registered",
            "feedback_30d": AuditoriaInstitucional.objects.filter(
                empresa=empresa,
                acao="command_ai_feedback",
                criado_em__gte=timezone.now() - timedelta(days=30),
            ).count(),
            "message": "A IA corporativa lê check-ins anônimos, fila de apoio e validação institucional para orientar prioridades de saúde ocupacional. O feedback é registrado para revisão da equipe e não recalibra o motor automaticamente.",
        },
        "safeguards": [
            "Não usa dado individual do colaborador no painel institucional.",
            "Não reutiliza bairros, surtos ou mapas do panorama epidemiológico para a conta empresa.",
            "Usa check-ins diários, semanais, pedidos de apoio e grupos mínimos para orientar ação corporativa.",
            "A leitura serve para prevenção, apoio e continuidade, não para disciplina ou vigilância individual.",
        ],
        "source": {
            "engine": "SolusCRT corporativo",
            "generated_from": "check-ins diários, check-ins semanais, pedidos de apoio, unidades, setores e sinais de saúde ocupacional",
        },
    }


def build_command_ai_payload(empresa, limit=6):
    setor = _company_sector(empresa)
    config = SECTOR_CONFIG.get(setor, SECTOR_CONFIG["empresa"])
    pacote_codigo = normalizar_codigo_pacote(empresa.pacote_codigo)
    pacote = detalhes_pacote(pacote_codigo)
    if setor == "empresa":
        payload = _build_company_command_ai_payload(empresa, pacote_codigo, pacote, limit=limit)
        payload["enterprise_command_center"] = build_enterprise_command_center_payload(empresa)
        return payload
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
        "enterprise_command_center": build_enterprise_command_center_payload(empresa),
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
