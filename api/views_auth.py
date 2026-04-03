# api/views_auth.py

from django.views.decorators.csrf import csrf_exempt
import json
import jwt
from django.http import JsonResponse
from django.contrib.auth.hashers import check_password
from .models import Empresa

SECRET_KEY = "chave_super_segura_123456789_abc"


@csrf_exempt
def login_empresa(request):
    if request.method == "POST":

        dados = json.loads(request.body)

        try:
            empresa = Empresa.objects.get(email=dados.get("email"))

            if check_password(dados.get("senha"), empresa.senha):

                token = jwt.encode({
                    "empresa_id": empresa.id
                }, SECRET_KEY, algorithm="HS256")

                return JsonResponse({
                    "status": "ok",
                    "token": token
                })

            return JsonResponse({"status": "erro"})

        except Empresa.DoesNotExist:
            return JsonResponse({"status": "erro"})

    return JsonResponse({"erro": "Use POST"})

@csrf_exempt
def registrar_empresa(request):

    if request.method == "POST":

        dados = json.loads(request.body)

        empresa = Empresa.objects.create(
            nome=dados["nome"],
            email=dados["email"],
            senha=make_password(dados["senha"])
        )

        return JsonResponse({"status": "ok"})

    return JsonResponse({"erro": "Use POST"})