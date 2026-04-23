import json
import os
import unicodedata
from django.conf import settings

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:  # pragma: no cover
    firebase_admin = None
    credentials = None
    messaging = None

from .models import DispositivoPushPublico

STATE_ALIASES = {
    "RJ": "Rio de Janeiro",
    "SP": "São Paulo",
    "MG": "Minas Gerais",
    "BA": "Bahia",
    "PR": "Parana",
    "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina",
    "GO": "Goias",
    "DF": "Distrito Federal",
    "ES": "Espirito Santo",
    "PE": "Pernambuco",
    "CE": "Ceara",
    "AM": "Amazonas",
}


def _state_terms(value):
    raw = (value or "").strip()
    if not raw:
        return []
    terms = {raw, raw.upper()}
    alias = STATE_ALIASES.get(raw.upper())
    if alias:
        terms.add(alias)
    for uf, name in STATE_ALIASES.items():
        if raw.lower() == name.lower():
            terms.add(uf)
            terms.add(name)
    return list(terms)


def _normalize_text(value):
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    return unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")


def _state_term_set(value):
    return {_normalize_text(term) for term in _state_terms(value)}


def _matches_direct_scope(token, alerta):
    estado_alerta = _state_term_set(alerta.estado) if alerta.estado else set()
    cidade_alerta = _normalize_text(alerta.cidade)
    bairro_alerta = _normalize_text(alerta.bairro)

    estado_token = _normalize_text(token.estado)
    cidade_token = _normalize_text(token.cidade)
    bairro_token = _normalize_text(token.bairro)

    if estado_alerta and estado_token and estado_token not in estado_alerta:
        return False
    if cidade_alerta and cidade_token and cidade_token != cidade_alerta:
        return False
    if bairro_alerta and bairro_token and bairro_token != bairro_alerta:
        return False
    return True


def _tokens_para_alerta(alerta):
    tokens = list(DispositivoPushPublico.objects.filter(ativo=True))
    total = len(tokens)
    if not tokens:
        return [], total, "sem_tokens"

    diretos = [token for token in tokens if _matches_direct_scope(token, alerta)]
    if diretos:
        return diretos, total, "recorte_direto"

    estado_alerta = _state_term_set(alerta.estado) if alerta.estado else set()
    if estado_alerta:
        estaduais = [
            token
            for token in tokens
            if not _normalize_text(token.estado)
            or _normalize_text(token.estado) in estado_alerta
        ]
        if estaduais:
            return estaduais, total, "fallback_estado"

    gerais = [
        token
        for token in tokens
        if not _normalize_text(token.estado)
        and not _normalize_text(token.cidade)
        and not _normalize_text(token.bairro)
    ]
    if gerais:
        return gerais, total, "fallback_geral"

    return [], total, "sem_destinatarios"


def _firebase_app():
    if firebase_admin is None or credentials is None:
        return None

    if firebase_admin._apps:
        return firebase_admin.get_app()

    raw_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH") or settings.FIREBASE_SERVICE_ACCOUNT_PATH

    try:
        if raw_json:
            info = json.loads(raw_json)
            return firebase_admin.initialize_app(credentials.Certificate(info))
        if path and os.path.exists(path):
            return firebase_admin.initialize_app(credentials.Certificate(path))
    except Exception:
        return None

    return None


def push_disponivel():
    return _firebase_app() is not None and messaging is not None


def enviar_alerta_governamental(alerta):
    app = _firebase_app()
    if app is None or messaging is None:
        return {"status": "push_indisponivel", "enviados": 0, "destinatarios": 0, "tokens_ativos": 0}

    tokens_filtrados, tokens_ativos, estrategia = _tokens_para_alerta(alerta)
    tokens = [item.token for item in tokens_filtrados[:500]]
    if not tokens:
        return {
            "status": "sem_destinatarios",
            "enviados": 0,
            "destinatarios": 0,
            "tokens_ativos": tokens_ativos,
            "estrategia": estrategia,
        }

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=alerta.titulo,
            body=alerta.mensagem[:180],
        ),
        data={
            "tipo": "alerta_governamental",
            "alerta_id": str(alerta.id),
            "nivel": alerta.nivel,
            "estado": alerta.estado or "",
            "cidade": alerta.cidade or "",
            "bairro": alerta.bairro or "",
        },
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message, app=app)
        return {
            "status": "ok",
            "enviados": response.success_count,
            "falhas": response.failure_count,
            "destinatarios": len(tokens),
            "tokens_ativos": tokens_ativos,
            "estrategia": estrategia,
        }
    except Exception as exc:
        return {
            "status": "erro_push",
            "erro": str(exc),
            "enviados": 0,
            "destinatarios": len(tokens),
            "tokens_ativos": tokens_ativos,
            "estrategia": estrategia,
        }
