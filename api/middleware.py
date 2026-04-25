import jwt
from django.http import JsonResponse
from django.conf import settings
from .models import Empresa


class EmpresaMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # 🔓 ROTAS LIVRES (não precisam de pagamento)
        rotas_livres = [
            "/",
            "/api/login",
            "/api/assinatura/",
            "/api/planos-publicos",
            "/pagamento/",
            "/sucesso/",
            "/erro/",
            "/pendente/"
        ]

        for rota in rotas_livres:
            if request.path.startswith(rota):
                return self.get_response(request)

        # 🔐 AUTENTICAÇÃO JWT
        auth = request.headers.get("Authorization")

        if not auth or "Bearer" not in auth:
            return JsonResponse({"erro": "não autenticado"}, status=401)

        try:
            token = auth.split(" ")[1]

            data = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=["HS256"]
            )

            empresa = Empresa.objects.get(id=data["empresa_id"])
            request.empresa = empresa

        except Exception as e:
            print("ERRO TOKEN:", e)
            return JsonResponse({"erro": "Token inválido"}, status=401)

        # 💣 BLOQUEIO DE ACESSO SEM PAGAMENTO
        if not empresa.ativo:
            return JsonResponse({
                "erro": "plano não ativo",
                "redirect": "/pagamento/"
            }, status=403)

        return self.get_response(request)
