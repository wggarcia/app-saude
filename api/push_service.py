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

from .models import DispositivoPushPublico, CredencialAppFuncionario, Empresa

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


_STATE_NAME_TO_UF = {_normalize_text(nome): uf for uf, nome in STATE_ALIASES.items()}


def _to_uf(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) == 2:
        return raw.upper()
    return _STATE_NAME_TO_UF.get(_normalize_text(raw), "")


def resolver_empresa_governo_por_geo(estado, cidade):
    """
    Resolve o tenant (Empresa governo) responsável por um device do app público
    a partir da cidade/estado informados no cadastro anônimo (sem login).
    Só resolve quando há exatamente um município cliente correspondente —
    ambiguidade ou ausência de match mantém o device sem tenant, fora do
    alcance de qualquer alerta municipal (AlertaCidadao) até revisão manual.
    """
    cidade_norm = _normalize_text(cidade)
    if not cidade_norm:
        return None
    uf_norm = _normalize_text(_to_uf(estado))

    candidatos = Empresa.objects.filter(
        tipo_conta=Empresa.TIPO_GOVERNO,
        acesso_governo=True,
        ativo=True,
    ).exclude(cidade="")
    encontrados = [
        e for e in candidatos
        if _normalize_text(e.cidade) == cidade_norm
        and (not uf_norm or _normalize_text(e.uf) == uf_norm)
    ]
    if len(encontrados) == 1:
        return encontrados[0]
    return None


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

    raw_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH") or getattr(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "")

    # If there are no credentials configured at all, report unavailable
    # even if a previous initialization exists (catches override_settings in tests)
    if not raw_json and not (path and os.path.exists(path)):
        return None

    if firebase_admin._apps:
        return firebase_admin.get_app()

    _opts = {"httpTimeout": 15}  # 15s cap — push nunca deve travar o request
    try:
        if raw_json:
            info = json.loads(raw_json)
            return firebase_admin.initialize_app(credentials.Certificate(info), options=_opts)
        if path and os.path.exists(path):
            return firebase_admin.initialize_app(credentials.Certificate(path), options=_opts)
    except Exception:
        return None

    return None


def push_disponivel():
    return _firebase_app() is not None and messaging is not None


def enviar_push_funcionario(notificacao):
    """
    Envia push FCM para um funcionário específico quando uma NotificacaoFuncionario é criada.
    Requer que CredencialAppFuncionario.fcm_token esteja preenchido.
    """
    app = _firebase_app()
    if app is None or messaging is None:
        return {"status": "push_indisponivel"}

    try:
        cred = CredencialAppFuncionario.objects.get(
            funcionario_id=notificacao.funcionario_id,
            ativo=True,
        )
    except CredencialAppFuncionario.DoesNotExist:
        return {"status": "sem_credencial"}

    token = (cred.fcm_token or "").strip()
    if not token:
        return {"status": "sem_token"}

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=notificacao.titulo,
                body=(notificacao.mensagem or "")[:180],
            ),
            data={
                "tipo": notificacao.tipo or "geral",
                "notificacao_id": str(notificacao.id),
                "referencia_id": str(notificacao.referencia_id or ""),
            },
            token=token,
        )
        response = messaging.send(message, app=app)
        return {"status": "ok", "message_id": response}
    except Exception as exc:
        code = getattr(exc, "code", None) or exc.__class__.__name__
        # Token inválido → limpar para evitar tentativas futuras
        if str(code) in {
            "unregistered",
            "registration-token-not-registered",
            "invalid-argument",
            "invalid-registration-token",
            "sender-id-mismatch",
            "UnregisteredError",
            "SenderIdMismatchError",
        }:
            CredencialAppFuncionario.objects.filter(
                funcionario_id=notificacao.funcionario_id
            ).update(fcm_token="")
        return {"status": "erro_push", "erro": str(exc)}


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


def enviar_push_alerta_cidadao(alerta):
    """
    Envia push FCM para os devices ativos do app da população pertencentes ao
    município/tenant do alerta (DispositivoPushPublico.empresa=alerta.empresa)
    quando um AlertaCidadao é publicado pelo governo. Nunca alcança devices de
    outro município — isolamento exigido por LGPD entre clientes.
    Retorna resumo de entrega para exibir na UI do gestor.
    """
    app = _firebase_app()
    if app is None or messaging is None:
        return {"status": "push_indisponivel", "enviados": 0, "destinatarios": 0}

    tokens = list(
        DispositivoPushPublico.objects.filter(ativo=True, empresa=alerta.empresa)
        .values_list("token", flat=True)
        .distinct()
    )
    if not tokens:
        return {"status": "sem_tokens", "enviados": 0, "destinatarios": 0}

    nivel = {
        "alerta_sanitario": "critico",
        "epidemiologico": "alerta",
        "campanha_vacinacao": "alerta",
    }.get(alerta.tipo, "informativo")

    total_sucesso = 0
    total_falha = 0
    invalid_tokens = []

    for start in range(0, len(tokens), 500):
        lote = tokens[start:start + 500]
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=alerta.titulo,
                body=(alerta.mensagem or "")[:180],
            ),
            data={
                "tipo": "alerta_cidadao",
                "alerta_id": str(alerta.id),
                "nivel": nivel,
            },
            tokens=lote,
        )
        try:
            response = messaging.send_each_for_multicast(message, app=app)
            total_sucesso += response.success_count
            total_falha += response.failure_count
            for i, resp in enumerate(response.responses):
                if not resp.success:
                    code = getattr(resp.exception, "code", None) or resp.exception.__class__.__name__
                    if str(code) in {
                        "unregistered", "registration-token-not-registered",
                        "invalid-argument", "invalid-registration-token",
                        "UnregisteredError", "SenderIdMismatchError",
                    }:
                        invalid_tokens.append(lote[i])
        except Exception:
            total_falha += len(lote)

    if invalid_tokens:
        DispositivoPushPublico.objects.filter(token__in=invalid_tokens).update(ativo=False)

    return {
        "status": "ok" if total_sucesso > 0 else ("falha_total" if total_falha > 0 else "sem_tokens"),
        "enviados": total_sucesso,
        "falhas": total_falha,
        "destinatarios": len(tokens),
        "tokens_invalidados": len(invalid_tokens),
    }
