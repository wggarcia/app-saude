import jwt
from django.conf import settings
from api.models import Empresa

def validar_token(request):
    token = request.headers.get("Authorization")

    if not token:
        return None, "Token ausente"

    try:
        token = token.replace("Bearer ", "")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

        empresa = Empresa.objects.get(id=payload["empresa_id"])

        return empresa, None

    except Exception as e:
        return None, str(e)