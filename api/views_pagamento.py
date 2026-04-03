from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import datetime
from .models import Empresa
import mercadopago


SDK = mercadopago.SDK("APP_USR-610cd28b-180f-4d89-8a91-703f0bf40d48")

def criar_pagamento(request):

    token = request.headers.get("Authorization").replace("Bearer ", "")
    dados = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

    empresa_id = dados["empresa_id"]

    preference_data = {
        "items": [
            {
                "title": "Plataforma Vigilância Saúde AI",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 29.90
            }
        ],
        "external_reference": str(empresa_id),  # 🔥 ESSENCIAL
        "notification_url": "https://lissette-congestus-will.ngrok-free.dev/api/webhook"
    }

    response = SDK.preference().create(preference_data)

    return JsonResponse({
        "init_point": response["response"]["init_point"]
    })

def ativar_plano(request, empresa_id):

    empresa = Empresa.objects.get(id=empresa_id)

    empresa.plano = "premium"
    empresa.data_pagamento = datetime.date.today()
    empresa.ativo = True
    empresa.save()

    return JsonResponse({"status": "premium_ativado"})

def sucesso(request):
    # aqui você ativa plano
    # (depois vamos ligar com Stripe)
    return HttpResponse("Pagamento aprovado ✅")

from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def webhook(request):

    print("🔥 WEBHOOK CHAMADO")

    # aceita GET sem quebrar
    if request.method != "POST":
        print("⚠️ Não é POST")
        return JsonResponse({"status": "ok"})

    # tenta ler JSON com segurança
    try:
        if not request.body:
            print("⚠️ Body vazio")
            return JsonResponse({"status": "vazio"})

        data = json.loads(request.body)

    except Exception as e:
        print("❌ Erro JSON:", e)
        return JsonResponse({"status": "erro_json"})

    print("📦 Dados recebidos:", data)

    if data.get("type") == "payment":

        payment_id = data.get("data", {}).get("id")

        if not payment_id:
            print("⚠️ Sem payment_id")
            return JsonResponse({"status": "sem_id"})

        pagamento = SDK.payment().get(payment_id)
        pagamento_info = pagamento["response"]

        print("💰 Pagamento:", pagamento_info)

        if pagamento_info.get("status") == "approved":

            empresa_id = pagamento_info.get("external_reference")

            if empresa_id:
                empresa = Empresa.objects.get(id=empresa_id)

                empresa.plano = "premium"
                empresa.ativo = True
                empresa.data_pagamento = datetime.date.today()
                empresa.save()

                print(f"✅ Empresa {empresa_id} ativada")

    return JsonResponse({"status": "ok"})