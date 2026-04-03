# api/middleware.py

import jwt
from django.http import JsonResponse
from .models import Empresa

SECRET_KEY = "chave_super_segura_123456789_abc"

class EmpresaMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        auth = request.headers.get("Authorization")

        if auth and "Bearer" in auth:
            try:
                token = auth.split(" ")[1]
                data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

                request.empresa = Empresa.objects.get(id=data["empresa_id"])

            except:
                return JsonResponse({"erro": "Token inválido"}, status=401)

        return self.get_response(request)