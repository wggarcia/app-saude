from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json
import jwt
from django.http import JsonResponse
from django.contrib.auth.hashers import check_password, make_password
from .models import Empresa
from django.conf import settings


# 🔐 LOGIN
@csrf_exempt
def login_empresa(request):

    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    try:
        dados = json.loads(request.body)
    except:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    email = dados.get("email")
    senha = dados.get("senha")

    if not email or not senha:
        return JsonResponse({"erro": "Email e senha obrigatórios"}, status=400)

    try:
        empresa = Empresa.objects.get(email=email)

        if check_password(senha, empresa.senha):

            token = jwt.encode({
                "empresa_id": empresa.id
            }, settings.JWT_SECRET_KEY, algorithm="HS256")

            return JsonResponse({
                "status": "ok",
                "token": token,
                "empresa_id": empresa.id  # 🔥 AQUI
            })

        return JsonResponse({"status": "erro", "mensagem": "Senha incorreta"}, status=401)

    except Empresa.DoesNotExist:
        return JsonResponse({"status": "erro", "mensagem": "Empresa não encontrada"}, status=404)


# 🚀 CADASTRO
@csrf_exempt
def registrar_empresa(request):

    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    try:
        dados = json.loads(request.body)
    except:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = dados.get("nome")
    email = dados.get("email")
    senha = dados.get("senha")

    # 🔥 validação
    if not nome or not email or not senha:
        return JsonResponse({"erro": "Preencha todos os campos"}, status=400)

    if Empresa.objects.filter(email=email).exists():
        return JsonResponse({"erro": "Email já existe"}, status=400)

    # 🔐 salva empresa
    empresa = Empresa.objects.create(
        nome=nome,
        email=email,
        senha=make_password(senha)
    )

    # 🔑 gera token AUTOMÁTICO
    token = jwt.encode({
        "empresa_id": empresa.id
    }, settings.JWT_SECRET_KEY, algorithm="HS256")

    return JsonResponse({
        "status": "ok",
        "token": token
    })