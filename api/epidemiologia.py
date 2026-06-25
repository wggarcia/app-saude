from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import json
from time import time

from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpResponse
from django.utils import timezone

from .models import Empresa, RegistroSintoma
from .services.public_integrity import q_registro_sintoma_sintetico
from .utils_cidades import carregar_base
from .epidemiologia_ml import mapa_risco_oficial_por_estado, mapa_risco_oficial_por_doenca


SYMPTOM_LABELS = {
    # Sintomas originais
    "febre": "Febre",
    "tosse": "Tosse",
    "falta_ar": "Falta de Ar",
    "dor_corpo": "Dor no Corpo",
    "cansaco": "Cansaco",
    # Sintomas expandidos (IA 2.0)
    "dor_cabeca": "Dor de Cabeça",
    "dor_articular": "Dor Articular",
    "exantema": "Exantema / Manchas na Pele",
    "conjuntivite": "Conjuntivite",
    "vomito_nausea": "Vomito / Nausea",
    "diarreia": "Diarreia",
    "dor_abdominal": "Dor Abdominal",
    "rigidez_nuca": "Rigidez de Nuca",
    "ictericia": "Ictericia (Amarelamento)",
    "manchas_hemorragicas": "Manchas Hemorragicas / Petequias",
    "perda_olfato_paladar": "Perda de Olfato / Paladar",
    "dor_garganta": "Dor de Garganta",
    "coriza": "Coriza / Nariz Escorrendo",
    "calafrios": "Calafrios",
}

# Pesos sincronizados com classificador_doencas.py (versão resumida para scoring epidemiológico)
DISEASE_WEIGHTS = {
    "Dengue": {
        "febre": 1.0, "dor_corpo": 0.95, "dor_cabeca": 0.90, "cansaco": 0.80,
        "vomito_nausea": 0.72, "exantema": 0.68, "dor_abdominal": 0.65,
        "manchas_hemorragicas": 0.55, "calafrios": 0.40,
        "tosse": -0.40, "falta_ar": -0.35, "coriza": -0.45,
        "perda_olfato_paladar": -0.60, "conjuntivite": -0.30, "dor_garganta": -0.35,
    },
    "Zika": {
        "exantema": 0.98, "conjuntivite": 0.95, "febre": 0.68,
        "dor_articular": 0.72, "dor_corpo": 0.52, "cansaco": 0.48, "dor_cabeca": 0.55,
        "tosse": -0.25, "falta_ar": -0.20, "coriza": -0.25,
        "manchas_hemorragicas": -0.30, "perda_olfato_paladar": -0.60,
    },
    "Chikungunya": {
        "dor_articular": 1.0, "febre": 0.92, "exantema": 0.75,
        "dor_corpo": 0.85, "cansaco": 0.80, "dor_cabeca": 0.72,
        "tosse": -0.35, "falta_ar": -0.30, "coriza": -0.40,
        "perda_olfato_paladar": -0.60,
    },
    "COVID-19": {
        "perda_olfato_paladar": 1.0, "tosse": 0.90, "falta_ar": 0.88,
        "febre": 0.82, "cansaco": 0.85, "dor_corpo": 0.70,
        "dor_cabeca": 0.72, "dor_garganta": 0.65, "calafrios": 0.50,
        "rigidez_nuca": -0.60, "ictericia": -0.50, "manchas_hemorragicas": -0.40,
    },
    "Gripe": {
        "febre": 0.92, "tosse": 0.90, "dor_corpo": 0.88, "dor_cabeca": 0.85,
        "cansaco": 0.82, "dor_garganta": 0.70, "calafrios": 0.72, "coriza": 0.60,
        "exantema": -0.35, "ictericia": -0.70, "rigidez_nuca": -0.50,
    },
    "Resfriado Viral": {
        "coriza": 1.0, "dor_garganta": 0.90, "tosse": 0.78, "cansaco": 0.55,
        "febre": 0.20, "dor_corpo": 0.25,
        "falta_ar": -0.50, "exantema": -0.70, "ictericia": -0.90,
    },
    "Febre Amarela": {
        "febre": 0.95, "ictericia": 0.90, "vomito_nausea": 0.85,
        "dor_corpo": 0.80, "cansaco": 0.82, "manchas_hemorragicas": 0.70,
        "dor_abdominal": 0.75, "dor_cabeca": 0.72, "calafrios": 0.65,
        "tosse": -0.20, "coriza": -0.50, "perda_olfato_paladar": -0.70,
    },
    "Leptospirose": {
        "febre": 0.90, "dor_corpo": 0.92, "cansaco": 0.80, "dor_cabeca": 0.82,
        "vomito_nausea": 0.75, "ictericia": 0.78, "dor_abdominal": 0.72, "calafrios": 0.70,
        "coriza": -0.45, "exantema": -0.20, "perda_olfato_paladar": -0.70,
    },
    "Malaria": {
        "febre": 0.95, "calafrios": 0.95, "cansaco": 0.88, "dor_corpo": 0.72,
        "dor_cabeca": 0.78, "vomito_nausea": 0.68,
        "coriza": -0.50, "exantema": -0.25, "conjuntivite": -0.40,
        "perda_olfato_paladar": -0.70,
    },
    "Sarampo": {
        "febre": 0.95, "exantema": 1.0, "conjuntivite": 0.88, "tosse": 0.85,
        "coriza": 0.80, "dor_cabeca": 0.60, "dor_garganta": 0.50,
        "perda_olfato_paladar": -0.60, "ictericia": -0.50,
    },
    "Meningite": {
        "rigidez_nuca": 1.0, "febre": 0.92, "dor_cabeca": 0.95,
        "manchas_hemorragicas": 0.88, "vomito_nausea": 0.78, "cansaco": 0.72,
        "coriza": -0.30, "perda_olfato_paladar": -0.70,
    },
    "Hantavirose": {
        "falta_ar": 1.0, "febre": 0.92, "cansaco": 0.88, "dor_corpo": 0.75,
        "tosse": 0.72, "calafrios": 0.62,
        "coriza": -0.20, "exantema": -0.30, "perda_olfato_paladar": -0.60,
    },
    "Bronquite": {
        "tosse": 1.0, "falta_ar": 0.92, "cansaco": 0.60, "coriza": 0.30,
        "febre": -0.15, "exantema": -0.80, "ictericia": -0.80,
    },
    "Gastroenterite Viral": {
        "vomito_nausea": 1.0, "diarreia": 0.95, "dor_abdominal": 0.88,
        "febre": 0.55, "cansaco": 0.60,
        "tosse": -0.50, "falta_ar": -0.60, "exantema": -0.50,
    },
    "Hepatite A/B": {
        "ictericia": 1.0, "vomito_nausea": 0.85, "cansaco": 0.88,
        "dor_abdominal": 0.82, "febre": 0.65,
        "tosse": -0.60, "coriza": -0.60, "perda_olfato_paladar": -0.70,
    },
    # Compatibilidade com nomes antigos
    "Virose": {
        "febre": 0.52, "cansaco": 0.5, "dor_corpo": 0.44, "tosse": 0.22,
    },
}

_PANORAMA_CACHE = {"created_at": 0.0, "payload": None, "version": None}
# TTL maior que o intervalo de polling dos painéis (15s) para que os requests
# concorrentes reaproveitem o payload já calculado em vez de refazer as 4
# agregações pesadas a cada ciclo. O cache é invalidado em tempo real por
# clear_panorama_cache() quando um novo registro chega.
_CACHE_TTL_SECONDS = 45
_PANORAMA_CACHE_VERSION_KEY = "epidemiologia:panorama:version"
PUBLIC_APP_EMAIL = "populacao@soluscrt.com"


def _current_panorama_cache_version():
    try:
        return int(cache.get(_PANORAMA_CACHE_VERSION_KEY, 0) or 0)
    except Exception:
        return 0


def clear_panorama_cache():
    try:
        cache.set(_PANORAMA_CACHE_VERSION_KEY, _current_panorama_cache_version() + 1, None)
    except Exception:
        pass
    _PANORAMA_CACHE["created_at"] = 0.0
    _PANORAMA_CACHE["payload"] = None
    _PANORAMA_CACHE["version"] = _current_panorama_cache_version()


def _public_population_empresa():
    return Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()


def _scope_public_population_queryset(queryset):
    empresa = _public_population_empresa()
    if not empresa:
        return queryset
    try:
        from api.middleware import _rls_set_empresa
        _rls_set_empresa(empresa.id)
    except Exception:
        pass
    if not RegistroSintoma.objects.filter(empresa=empresa).exists():
        return queryset
    return queryset.filter(empresa=empresa)
_CITY_TO_UF = None
FOCUS_STABILITY_DAYS = 10
FOCUS_DECAY_WINDOW_DAYS = 30
FOCUS_MIN_WEIGHT = 0.1
FOCUS_VISIBILITY_THRESHOLD = 0.01

UF_CODES = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}

NOME_ESTADO_PARA_UF = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE",
    "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def _estado_para_uf(estado):
    """Normaliza nome-completo OU sigla de estado para a sigla UF (chave usada
    em FonteOficialAgregado/epidemiologia_ml). Sem acento/maiusculo para tolerar
    variacoes do dado de entrada."""
    valor = (estado or "").strip().upper()
    if len(valor) == 2:
        return valor
    sem_acento = (
        valor.replace("Á", "A").replace("Â", "A").replace("Ã", "A")
        .replace("É", "E").replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O").replace("Ô", "O").replace("Õ", "O")
        .replace("Ú", "U").replace("Ç", "C")
    )
    return NOME_ESTADO_PARA_UF.get(sem_acento, valor)


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


def _temporal_focus_weight(day, now=None):
    now = now or timezone.now()
    if not day:
        return 1.0
    if hasattr(day, "date"):
        day = day.date()
    days = max((now.date() - day).days, 0)
    if days <= FOCUS_STABILITY_DAYS:
        return 1.0
    if days >= FOCUS_DECAY_WINDOW_DAYS:
        return FOCUS_MIN_WEIGHT
    decay_span = FOCUS_DECAY_WINDOW_DAYS - FOCUS_STABILITY_DAYS
    days_decaying = days - FOCUS_STABILITY_DAYS
    decay = days_decaying / decay_span
    return round(max(FOCUS_MIN_WEIGHT, 1 - (decay * (1 - FOCUS_MIN_WEIGHT))), 3)


def _active_case_value(value):
    return round(float(value or 0), 2)


def _risco_oficial_map_seguro():
    """Mapa {estado: probabilidade_ml} treinado em dado oficial real (DATASUS/SINAN).
    Nunca derruba o panorama: cai em dict vazio (heuristica pura) em qualquer erro."""
    try:
        return mapa_risco_oficial_por_estado()
    except Exception:
        return {}


def _risco_oficial_doenca_map_seguro():
    """Mapa {doenca: {estado: probabilidade_ml}} para todas as doencas com
    modelo treinado (ver epidemiologia_ml.DOENCAS_REGISTRADAS). Nunca derruba
    o panorama: cai em dict vazio em qualquer erro."""
    try:
        return mapa_risco_oficial_por_doenca()
    except Exception:
        return {}


def _risk_score(total, max_total, recent_24h, max_recent, growth, temporal_retention_percent, oficial_probability=None):
    total_score = (total / max_total) * 55 if max_total else 0
    recent_score = (recent_24h / max_recent) * 25 if max_recent else 0
    growth_score = min(max(growth, 0), 100) * 0.2
    retention_factor = max(min(float(temporal_retention_percent or 0) / 100, 1.0), 0.0)
    # Resfria o foco conforme os casos envelhecem, sem zerar surtos realmente recentes.
    temporal_factor = 0.25 + (0.75 * (retention_factor ** 2))
    score = (total_score + recent_score + growth_score) * temporal_factor
    if oficial_probability is not None:
        # Calibra o score relativo (ranking entre areas no momento) com o padrao
        # sazonal real do estado, aprendido por ML em series oficiais do DATASUS/SINAN
        # (api/epidemiologia_ml.py). Fator entre 0.85x e 1.25x — ajusta sem dominar
        # o sinal de autorrelato ao vivo.
        score *= 0.85 + (0.40 * max(min(oficial_probability, 1.0), 0.0))
    return round(score, 2)


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


def _stable_area_id(level, *parts):
    normalized_parts = []

    for part in parts:
        value = " ".join(str(part or "").strip().lower().split())
        normalized_parts.append(value or "_")

    return "|".join([level, *normalized_parts])


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
        "Febre Amarela": "reforcar vigilancia de febre aguda, orientacao vacinal e comunicacao de risco em areas indicadas",
        "Leptospirose": "orientar risco apos enchentes ou agua contaminada e encaminhamento de sinais de gravidade",
        "Malaria": "priorizar investigacao em areas de transmissao e encaminhamento para testagem conforme protocolo local",
        "Sarampo": "reforcar alerta para febre com tosse, isolamento orientado e verificacao de cobertura vacinal",
        "Meningite": "orientar busca imediata de atendimento diante de febre intensa, rigidez ou piora rapida",
        "Hantavirose": "priorizar casos com febre e sintomas respiratorios agudos, reforcar alerta para exposicao a roedores e encaminhar avaliacao urgente",
    }
    action = base.get(dominant_disease, f"priorizar monitoramento de {dominant_symptom.lower()} e orientacao local")

    if risk_level == "CRITICO":
        return f"Acionar resposta rapida e {action}."
    if risk_level == "ALTO":
        return f"Intensificar vigilancia de campo e {action}."
    return f"Manter vigilancia ativa e {action}."


def _market_recommendation(dominant_disease, dominant_symptom):
    if dominant_disease in {"COVID", "Hantavirose"}:
        return "reforcar estoque de mascaras, antitermicos, testes e antigripais"
    if dominant_disease == "Gripe":
        return "reforcar antigripais, xaropes, vitamina C e analgesicos"
    if dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        return "reforcar analgesicos, hidratacao oral, repelentes e materiais de orientacao"
    if dominant_disease in {"Leptospirose", "Malaria"}:
        return "reforcar hidratacao, antitermicos seguros, orientacao de encaminhamento e materiais educativos"
    if dominant_disease in {"Sarampo", "Meningite"}:
        return "reforcar mascaras, antitermicos, orientacao de isolamento/encaminhamento e comunicacao de risco"
    if dominant_disease == "Hantavirus":
        return "reforcar mascaras PFF2/N95, materiais de desinfeccao, orientacao de risco ambiental e encaminhamento urgente"
    if dominant_symptom == "Falta de Ar":
        return "priorizar itens respiratorios e protocolos de encaminhamento"
    return "acompanhar demanda de sintomaticos e ajustar estoque de suporte"


def _hospital_recommendation(dominant_disease, dominant_symptom, risk_level):
    if dominant_symptom == "Falta de Ar" or dominant_disease in {"COVID", "Hantavirose"}:
        action = "preparar leitos respiratorios, triagem rapida, oxigenio e retaguarda de UTI"
    elif dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela", "Leptospirose", "Malaria"}:
        action = "preparar hidratacao venosa, analgesia, observacao e fluxo para sinais de alarme"
    elif dominant_disease == "Meningite":
        action = "preparar triagem de emergencia, isolamento quando indicado, coleta diagnostica e protocolo de notificação"
    elif dominant_disease == "Hantavirus":
        action = "preparar UTI com suporte ventilatório mecanico, isolamento de contato/respiratorio e protocolo de notificacao imediata"
    elif dominant_disease == "Sarampo":
        action = "reforcar triagem respiratoria, isolamento orientado, vigilancia de contatos e verificacao vacinal"
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
    if dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        action = "intensificar vigilancia vetorial, bloqueio territorial, comunicacao comunitaria e mutirao de campo"
    elif dominant_disease in {"Leptospirose", "Malaria"}:
        action = "acionar vigilancia territorial, investigacao ambiental, comunicacao de risco e rede de testagem/encaminhamento"
    elif dominant_disease == "Hantavirus":
        action = "acionar notificacao compulsoria imediata, investigacao de foco de roedores, interdição de area contaminada e articulacao com CIEVS/SVS"
    elif dominant_disease in {"Sarampo", "Meningite"}:
        action = "acionar notificacao imediata, investigacao de contatos, comunicacao de risco e articulacao da rede assistencial"
    elif dominant_symptom == "Falta de Ar" or dominant_disease in {"COVID", "Hantavirose"}:
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
    if dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        tags.append("Vetorial")
    if dominant_disease in {"Leptospirose", "Malaria"}:
        tags.append("Territorial")
    if dominant_disease in {"Sarampo", "Meningite"}:
        tags.append("Notificacao Rapida")
    if dominant_disease == "Hantavirose":
        tags.append("Risco Cardiopulmonar")

    return tags[:4]


def _government_tags(dominant_disease, dominant_symptom, growth_percent, risk_level):
    tags = ["Governanca", dominant_disease]

    if dominant_symptom == "Falta de Ar":
        tags.append("Resposta Respiratoria")
    if dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        tags.append("Campo Vetorial")
    if dominant_disease in {"Leptospirose", "Malaria"}:
        tags.append("Investigacao Territorial")
    if dominant_disease in {"Sarampo", "Meningite"}:
        tags.append("Notificacao Imediata")
    if dominant_disease == "Hantavirose":
        tags.append("Vigilancia de Roedores")
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
    if dominant_disease in {"Dengue", "Chikungunya", "Zika", "Febre Amarela"}:
        category = "hidratacao, analgesia e repelentes"
    elif dominant_disease in {"Leptospirose", "Malaria"}:
        category = "hidratacao, antitermicos seguros e orientacao de encaminhamento"
    elif dominant_disease in {"Sarampo", "Meningite"}:
        category = "mascaras, antitermicos e comunicacao de risco"
    elif dominant_disease in {"COVID", "Gripe", "Hantavirose"} or dominant_symptom == "Tosse":
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


def _build_disease_probabilities(symptom_counts, total_cases, risco_oficial_doenca_map=None, estado_uf=None):
    rates = {
        name: (count / total_cases) if total_cases else 0.0
        for name, count in symptom_counts.items()
    }
    raw_scores = {}
    calculo_ml_oficial_doencas = []

    for disease, weights in DISEASE_WEIGHTS.items():
        score = 0.08

        for symptom, weight in weights.items():
            rate = rates.get(symptom, 0.0)
            if weight >= 0:
                score += rate * weight
            else:
                # Ausencia do sintoma contrario e neutra.
                # Penalidade so deve existir quando o sintoma que aponta contra
                # a doenca aparece de fato no conjunto observado.
                score += rate * weight

        score = max(score, 0.01)

        # Calibra com ML real treinado em notificacao oficial (DATASUS/SINAN)
        # quando essa doenca e esse estado tem modelo treinado disponivel —
        # ver api/epidemiologia_ml.py DOENCAS_REGISTRADAS. Mesmo fator
        # 0.85x-1.25x do blend de risk_score: ajusta sem dominar o sinal de
        # sintomas autorrelatados.
        oficial_probability = (risco_oficial_doenca_map or {}).get(disease, {}).get(estado_uf) if estado_uf else None
        if oficial_probability is not None:
            score *= 0.85 + (0.40 * max(min(oficial_probability, 1.0), 0.0))
            calculo_ml_oficial_doencas.append(disease)

        raw_scores[disease] = score

    probabilities = _normalize_probabilities(raw_scores)

    for item in probabilities:
        item["estimated_cases"] = int(round(total_cases * item["probability"] / 100))
        item["calculo_ml_oficial"] = item["name"] in calculo_ml_oficial_doencas

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
    window_start = now - timedelta(days=FOCUS_DECAY_WINDOW_DAYS)

    queryset = (
        RegistroSintoma.objects
        .filter(data_registro__gte=window_start)
        .exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
        .exclude(q_registro_sintoma_sintetico())
    )
    queryset = _scope_public_population_queryset(queryset)

    for field in group_fields:
        queryset = queryset.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""})

    rows = list(
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
            # Sintomas expandidos (IA 2.0)
            dor_cabeca=Count("id", filter=Q(dor_cabeca=True)),
            dor_articular=Count("id", filter=Q(dor_articular=True)),
            exantema=Count("id", filter=Q(exantema=True)),
            conjuntivite=Count("id", filter=Q(conjuntivite=True)),
            vomito_nausea=Count("id", filter=Q(vomito_nausea=True)),
            diarreia=Count("id", filter=Q(diarreia=True)),
            dor_abdominal=Count("id", filter=Q(dor_abdominal=True)),
            rigidez_nuca=Count("id", filter=Q(rigidez_nuca=True)),
            ictericia=Count("id", filter=Q(ictericia=True)),
            manchas_hemorragicas=Count("id", filter=Q(manchas_hemorragicas=True)),
            perda_olfato_paladar=Count("id", filter=Q(perda_olfato_paladar=True)),
            dor_garganta=Count("id", filter=Q(dor_garganta=True)),
            coriza=Count("id", filter=Q(coriza=True)),
            calafrios=Count("id", filter=Q(calafrios=True)),
        )
        .order_by("-total")
    )
    active_by_group = defaultdict(float)
    daily_rows = (
        queryset.annotate(day=TruncDate("data_registro"))
        .values(*group_fields, "day")
        .annotate(total=Count("id"))
    )

    for item in daily_rows:
        key = tuple(item[field] for field in group_fields)
        active_by_group[key] += int(item["total"] or 0) * _temporal_focus_weight(item["day"], now)

    for row in rows:
        key = tuple(row[field] for field in group_fields)
        row["raw_total_cases"] = int(row["total"] or 0)
        row["active_cases"] = _active_case_value(active_by_group.get(key, row["total"] or 0))
        row["temporal_retention_percent"] = _safe_pct(row["active_cases"], row["raw_total_cases"])

    visible_rows = [
        row for row in rows
        if float(row.get("active_cases") or 0) > FOCUS_VISIBILITY_THRESHOLD
    ]
    return sorted(visible_rows, key=lambda item: item["active_cases"], reverse=True)


def _serialize_layer(level, group_fields, risco_oficial_map=None, risco_oficial_doenca_map=None):
    risco_oficial_map = risco_oficial_map or {}
    risco_oficial_doenca_map = risco_oficial_doenca_map or {}
    rows = _build_layer_queryset(group_fields)
    max_total = max((float(row.get("active_cases") or 0) for row in rows), default=1)
    max_recent = max((row["recent_24h"] for row in rows), default=1)
    areas = []

    for row in rows:
        raw_total_cases = int(row.get("raw_total_cases", row["total"] or 0) or 0)
        total_cases = float(row.get("active_cases", raw_total_cases) or 0)
        normalized_state = _normalize_state(row.get("cidade"), row.get("estado"))
        symptom_counts = {
            key: int(row.get(key, 0) or 0)
            for key in SYMPTOM_LABELS
        }
        symptom_breakdown = _serialize_symptoms(symptom_counts, raw_total_cases)
        dominant_symptom = symptom_breakdown[0]["label"] if symptom_breakdown else "Sem dados"
        disease_probabilities = _build_disease_probabilities(
            symptom_counts, raw_total_cases,
            risco_oficial_doenca_map=risco_oficial_doenca_map,
            estado_uf=_estado_para_uf(normalized_state),
        )
        for disease in disease_probabilities:
            disease["active_estimated_cases"] = _active_case_value(total_cases * disease["probability"] / 100)
        activity_percent = _activity_percent(total_cases, int(row["recent_24h"] or 0))
        disease_probabilities = _attach_active_probabilities(disease_probabilities, activity_percent)
        dominant_disease = disease_probabilities[0]["name"] if disease_probabilities else "Indefinido"
        growth = _safe_growth(int(row["recent_24h"] or 0), int(row["previous_24h"] or 0))
        oficial_probability = risco_oficial_map.get(_estado_para_uf(normalized_state))
        risk_score = _risk_score(
            total_cases,
            max_total,
            int(row["recent_24h"] or 0),
            max_recent,
            growth,
            row.get("temporal_retention_percent", 100),
            oficial_probability=oficial_probability,
        )
        risk_level = _risk_level(risk_score)
        surveillance_index = _surveillance_index(total_cases, int(row["recent_24h"] or 0), growth, max_total, max_recent)
        resource_pressure = _resource_pressure(total_cases, growth, dominant_symptom)
        stock_pressure = _stock_pressure(total_cases, growth, risk_level)
        hospital_load_estimate = _hospital_load_estimate(total_cases, growth, dominant_symptom)

        area = {
            "id": _stable_area_id(
                level,
                *[
                    normalized_state if field == "estado" else row.get(field)
                    for field in group_fields
                ],
            ),
            "level": level,
            "nome": row[group_fields[-1]],
            "cidade": row.get("cidade"),
            "estado": normalized_state,
            "label": _area_label(level, {**row, "estado": normalized_state}),
            "latitude": round(float(row["latitude"]), 6) if row["latitude"] is not None else None,
            "longitude": round(float(row["longitude"]), 6) if row["longitude"] is not None else None,
            "total_cases": total_cases,
            "active_cases": total_cases,
            "raw_total_cases": raw_total_cases,
            "total_registros_30d": raw_total_cases,
            "temporal_retention_percent": row.get("temporal_retention_percent", 100),
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


def _build_state_layer(municipios, risco_oficial_map=None, risco_oficial_doenca_map=None):
    risco_oficial_map = risco_oficial_map or {}
    risco_oficial_doenca_map = risco_oficial_doenca_map or {}
    grouped = defaultdict(lambda: {
        "estado": None,
        "total_cases": 0,
        "raw_total_cases": 0,
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
        entry["raw_total_cases"] += area.get("raw_total_cases", area["total_cases"])
        entry["recent_24h"] += area["recent_24h"]
        entry["previous_24h"] += area["previous_24h"]

        if area["latitude"] is not None and area["longitude"] is not None:
            geo_weight = area["total_cases"] or area.get("raw_total_cases", 1) or 1
            entry["lat_sum"] += area["latitude"] * geo_weight
            entry["lng_sum"] += area["longitude"] * geo_weight
            entry["weight"] += geo_weight

        for symptom in area["symptoms"]:
            entry["symptom_counts"][symptom["key"]] += symptom["count"]

    rows = list(grouped.values())
    max_total = max((row["total_cases"] for row in rows), default=1)
    max_recent = max((row["recent_24h"] for row in rows), default=1)
    states = []

    for row in sorted(rows, key=lambda item: item["total_cases"], reverse=True):
        total_cases = row["total_cases"]
        raw_total_cases = int(row.get("raw_total_cases") or 0)
        temporal_retention_percent = _safe_pct(total_cases, raw_total_cases)
        symptom_breakdown = _serialize_symptoms(row["symptom_counts"], raw_total_cases)
        dominant_symptom = symptom_breakdown[0]["label"] if symptom_breakdown else "Sem dados"
        probable_diseases = _build_disease_probabilities(
            row["symptom_counts"], raw_total_cases,
            risco_oficial_doenca_map=risco_oficial_doenca_map,
            estado_uf=_estado_para_uf(row["estado"]),
        )
        for disease in probable_diseases:
            disease["active_estimated_cases"] = _active_case_value(total_cases * disease["probability"] / 100)
        activity_percent = _activity_percent(total_cases, row["recent_24h"])
        probable_diseases = _attach_active_probabilities(probable_diseases, activity_percent)
        dominant_disease = probable_diseases[0]["name"] if probable_diseases else "Indefinido"
        growth = _safe_growth(row["recent_24h"], row["previous_24h"])
        oficial_probability = risco_oficial_map.get(_estado_para_uf(row["estado"]))
        risk_score = _risk_score(
            total_cases,
            max_total,
            row["recent_24h"],
            max_recent,
            growth,
            temporal_retention_percent,
            oficial_probability=oficial_probability,
        )
        weight = row["weight"] or 1
        risk_level = _risk_level(risk_score)
        surveillance_index = _surveillance_index(total_cases, row["recent_24h"], growth, max_total, max_recent)
        resource_pressure = _resource_pressure(total_cases, growth, dominant_symptom)
        stock_pressure = _stock_pressure(total_cases, growth, risk_level)
        hospital_load_estimate = _hospital_load_estimate(total_cases, growth, dominant_symptom)

        states.append({
            "id": _stable_area_id("estado", row["estado"]),
            "level": "estado",
            "nome": row["estado"],
            "cidade": None,
            "estado": row["estado"],
            "label": row["estado"],
            "latitude": round(row["lat_sum"] / weight, 6),
            "longitude": round(row["lng_sum"] / weight, 6),
            "total_cases": _active_case_value(total_cases),
            "active_cases": _active_case_value(total_cases),
            "raw_total_cases": raw_total_cases,
            "total_registros_30d": raw_total_cases,
            "temporal_retention_percent": temporal_retention_percent,
            "recent_24h": row["recent_24h"],
            "previous_24h": row["previous_24h"],
            "growth_percent": growth,
            "activity_percent": activity_percent,
            "decay_percent": _decay_percent(row["recent_24h"], row["previous_24h"]),
            "trend_status": _trend_status(growth, row["recent_24h"], row["previous_24h"]),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "calculo_ml_oficial": oficial_probability is not None,
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
    raw_total_cases = sum(area.get("raw_total_cases", area["total_cases"]) for area in bairros)
    active_areas = len(bairros)
    symptoms = defaultdict(int)
    disease_totals = defaultdict(float)
    raw_disease_totals = defaultdict(int)
    active_disease_totals = defaultdict(float)
    growth_values = []
    highest_risk = 0.0

    for area in bairros:
        growth_values.append(area["growth_percent"])
        highest_risk = max(highest_risk, area["risk_score"])

        for symptom in area["symptoms"]:
            symptoms[symptom["key"]] += symptom["count"]

        for disease in area["probable_diseases"]:
            disease_totals[disease["name"]] += disease.get("active_estimated_cases", disease["estimated_cases"])
            raw_disease_totals[disease["name"]] += disease["estimated_cases"]
            recency_weight = 0.25 + min(area["activity_percent"] / 100, 1.0)
            active_disease_totals[disease["name"]] += disease.get("active_estimated_cases", disease["estimated_cases"]) * recency_weight

    symptom_breakdown = _serialize_symptoms(symptoms, raw_total_cases)
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
            "estimated_cases": _active_case_value(estimated_cases),
            "raw_estimated_cases": int(raw_disease_totals[disease_name]),
            "probability": _safe_pct(estimated_cases, disease_total_sum),
            "active_probability": round((active_disease_totals[disease_name] / active_disease_total_sum) * 100, 2),
        })

    timeline = _build_timeline()
    data_quality = _build_data_quality()
    operational_profiles = _build_operational_profiles()
    top_stock_pressure = sorted(bairros, key=lambda area: (area["stock_pressure"], area["growth_percent"]), reverse=True)[:5]
    top_hospital_load = sorted(bairros, key=lambda area: (area["hospital_load_estimate"], area["growth_percent"]), reverse=True)[:5]

    overview = {
        "total_cases": _active_case_value(total_cases),
        "active_cases": _active_case_value(total_cases),
        "raw_total_cases": int(raw_total_cases),
        "total_registros_30d": int(raw_total_cases),
        "temporal_retention_percent": _safe_pct(total_cases, raw_total_cases),
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
    current_version = _current_panorama_cache_version()

    if (
        _PANORAMA_CACHE["payload"] is not None
        and _PANORAMA_CACHE.get("version") == current_version
        and now - _PANORAMA_CACHE["created_at"] < _CACHE_TTL_SECONDS
    ):
        return _PANORAMA_CACHE["payload"]

    risco_oficial_map = _risco_oficial_map_seguro()
    risco_oficial_doenca_map = _risco_oficial_doenca_map_seguro()
    bairros = _serialize_layer(
        "bairro", ("estado", "cidade", "bairro"),
        risco_oficial_map=risco_oficial_map, risco_oficial_doenca_map=risco_oficial_doenca_map,
    )
    municipios = _serialize_layer(
        "municipio", ("estado", "cidade"),
        risco_oficial_map=risco_oficial_map, risco_oficial_doenca_map=risco_oficial_doenca_map,
    )
    estados = _build_state_layer(
        municipios, risco_oficial_map=risco_oficial_map, risco_oficial_doenca_map=risco_oficial_doenca_map,
    )
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
    _PANORAMA_CACHE["version"] = current_version
    return payload


def panorama_epidemiologico(request):
    response = JsonResponse(build_panorama_payload())
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


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
