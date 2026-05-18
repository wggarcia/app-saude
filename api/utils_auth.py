from .services.auth_session import resolver_sessao_empresa_por_token


def validar_token(request):
    token = request.headers.get("Authorization")

    if not token:
        return None, "Token ausente"

    try:
        token = token.replace("Bearer ", "")
        _payload, empresa, _principal = resolver_sessao_empresa_por_token(token)
        return empresa, None

    except Exception as e:
        return None, str(e)
