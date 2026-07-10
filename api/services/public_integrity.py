from __future__ import annotations

import unicodedata

from django.db.models import Q


SYNTHETIC_MARKERS = (
    "demo",
    "test",
    "teste",
    "simulacao",
    "simulação",
    "stress",
    "placeholder",
    "fake",
)

SYNTHETIC_DEVICE_PREFIXES = (
    "stress-soluscrt-brasil",
    "sim-br-",
    "clf-br-",
    "pandemia-br-",
    "demo-",
    "test-",
    "fake-",
)

ALERTA_SYNTHETIC_FIELDS = (
    "titulo",
    "mensagem",
    "justificativa",
)

REGISTRO_SYNTHETIC_SOURCE_MARKERS = (
    "stress-test",
    "simulacao",
    "simulação",
    "demo",
)


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def texto_tem_marcador_sintetico(value: object) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    return any(marker in text for marker in SYNTHETIC_MARKERS)


def alerta_governamental_sintetico(alerta) -> bool:
    for field in ALERTA_SYNTHETIC_FIELDS:
        if texto_tem_marcador_sintetico(getattr(alerta, field, "")):
            return True
    return False


def q_alerta_governamental_sintetico() -> Q:
    query = Q()
    for field in ALERTA_SYNTHETIC_FIELDS:
        for marker in SYNTHETIC_MARKERS:
            query |= Q(**{f"{field}__icontains": marker})
    return query


def registro_sintoma_sintetico(registro) -> bool:
    device_id = _normalize_text(getattr(registro, "device_id", ""))
    if device_id:
        for prefix in SYNTHETIC_DEVICE_PREFIXES:
            if device_id.startswith(prefix):
                return True

    fonte_referencia = _normalize_text(getattr(registro, "fonte_referencia", ""))
    if fonte_referencia and any(marker in fonte_referencia for marker in REGISTRO_SYNTHETIC_SOURCE_MARKERS):
        return True

    return False


def q_registro_sintoma_sintetico() -> Q:
    query = Q()
    for prefix in SYNTHETIC_DEVICE_PREFIXES:
        query |= Q(device_id__istartswith=prefix)
    for marker in REGISTRO_SYNTHETIC_SOURCE_MARKERS:
        query |= Q(fonte_referencia__icontains=marker)
    return query
