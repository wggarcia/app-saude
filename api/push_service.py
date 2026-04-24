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


def _alerta_tem_recorte(alerta):
    return bool(
        (alerta.estado and alerta.estado.strip())
        or (alerta.cidade and alerta.cidade.strip())
        or (alerta.bairro and alerta.bairro.strip())
    )


def _tokens_para_alerta(alerta):
    registros = (
        DispositivoPushPublico.objects.filter(ativo=True)
        .order_by("-atualizado_em", "-id")
    )
    vistos = set()
    tokens = []
    for registro in registros:
        chave = (registro.device_id or "").strip() or registro.token
        if chave in vistos:
            continue
        vistos.add(chave)
        tokens.append(registro)
    total = len(tokens)
    if not tokens:
        return [], total, "sem_tokens"

    if not _alerta_tem_recorte(alerta):
        return tokens, total, "nacional_total"

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
    registros_destino = tokens_filtrados
    tokens = [item.token for item in registros_destino]
    if not tokens:
        return {
            "status": "sem_destinatarios",
            "enviados": 0,
            "destinatarios": 0,
            "tokens_ativos": tokens_ativos,
            "estrategia": estrategia,
        }

    try:
        failure_codes = []
        invalid_tokens = []
        total_sucesso = 0
        total_falha = 0
        lotes = 0

        for start in range(0, len(tokens), 500):
            lote_tokens = tokens[start:start + 500]
            lotes += 1
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
                    "escopo": "nacional" if estrategia == "nacional_total" else "territorial",
                },
                tokens=lote_tokens,
            )
            response = messaging.send_each_for_multicast(message, app=app)
            total_sucesso += response.success_count
            total_falha += response.failure_count

            for index, send_response in enumerate(response.responses):
                if send_response.success:
                    continue
                exc = send_response.exception
                code = getattr(exc, "code", None) or exc.__class__.__name__
                failure_codes.append(str(code))
                if str(code) in {
                    "unregistered",
                    "registration-token-not-registered",
                    "invalid-argument",
                    "invalid-registration-token",
                    "sender-id-mismatch",
                    "UnregisteredError",
                    "SenderIdMismatchError",
                }:
                    invalid_tokens.append(lote_tokens[index])

        if invalid_tokens:
            DispositivoPushPublico.objects.filter(token__in=invalid_tokens).update(ativo=False)

        erro_resumido = None
        if failure_codes and total_sucesso == 0:
            resumo = {}
            for code in failure_codes:
                resumo[code] = resumo.get(code, 0) + 1
            erro_resumido = ", ".join(
                f"{code}: {count}" for code, count in sorted(resumo.items())
            )

        return {
            "status": "ok" if total_sucesso > 0 else "falha_total",
            "enviados": total_sucesso,
            "falhas": total_falha,
            "destinatarios": len(tokens),
            "tokens_ativos": tokens_ativos,
            "estrategia": estrategia,
            "lotes": lotes,
            "erro": erro_resumido,
            "falha_codigos": failure_codes[:8],
            "tokens_invalidados": len(invalid_tokens),
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
