import json
import os
from django.conf import settings
from django.db.models import Q

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

    tokens_qs = DispositivoPushPublico.objects.filter(ativo=True)
    tokens_ativos = tokens_qs.count()
    if alerta.estado:
        tokens_qs = tokens_qs.filter(Q(estado__in=_state_terms(alerta.estado)) | Q(estado__isnull=True) | Q(estado=""))
    if alerta.cidade:
        tokens_qs = tokens_qs.filter(cidade=alerta.cidade)
    if alerta.bairro:
        tokens_qs = tokens_qs.filter(bairro=alerta.bairro)

    tokens = list(tokens_qs.values_list("token", flat=True)[:500])
    if not tokens:
        return {"status": "sem_destinatarios", "enviados": 0, "destinatarios": 0, "tokens_ativos": tokens_ativos}

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
        }
    except Exception as exc:
        return {
            "status": "erro_push",
            "erro": str(exc),
            "enviados": 0,
            "destinatarios": len(tokens),
            "tokens_ativos": tokens_ativos,
        }
