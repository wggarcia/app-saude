import mercadopago
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
import json
from .models import Empresa
import datetime
from django.shortcuts import redirect


# 🔥 SEU TOKEN DE TESTE
SDK = mercadopago.SDK("APP_USR-6311717538175038-040823-5a46ef16617f80bcc8641773b8313c57-57115072")


# =====================================================
# 💳 CHECKOUT REDIRECT (RECOMENDADO)
# =====================================================
@csrf_exempt
def criar_pagamento(request, empresa_id=None):

    print("🔥 NOVA REQUISIÇÃO PAGAMENTO")

    if not empresa_id:
        return JsonResponse({"erro": "empresa não identificada"}, status=400)

    preference_data = {
    "items": [
        {
            "title": "Plano SaaS Saúde",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": 29.90
        }
    ],

    "external_reference": str(empresa_id),

    "back_urls": {
        "success": "https://app-saude-p9n8.onrender.com/sucesso/",
        "failure": "https://app-saude-p9n8.onrender.com/erro/",
        "pending": "https://app-saude-p9n8.onrender.com/pendente/"
    },

    "auto_return": "approved",

    # 🔥 AGORA PODE USAR (PRODUÇÃO REAL)
    "notification_url": "https://app-saude-p9n8.onrender.com/api/webhook"
}

    try:
        response = SDK.preference().create(preference_data)
        print("MP RESPONSE:", response)

        return JsonResponse({
         "status": "ok",
         "init_point": response["response"]["init_point"]
   })

    except Exception as e:
        print("ERRO MP:", e)
        return JsonResponse({"erro": str(e)}, status=500)


# =====================================================
# 🔔 WEBHOOK (ATIVA AUTOMATICAMENTE)
# =====================================================
@csrf_exempt
def webhook(request):

    print("🔥 WEBHOOK CHAMADO")

    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    try:
        data = json.loads(request.body or "{}")
    except:
        return JsonResponse({"status": "erro_json"})

    print("📦 DATA:", data)

    if data.get("type") == "payment":

        payment_id = data.get("data", {}).get("id")

        if not payment_id:
            return JsonResponse({"status": "sem_id"})

        try:
            pagamento = SDK.payment().get(payment_id)
            info = pagamento["response"]

            print("💰 INFO:", info)

            if info.get("status") == "approved":

                empresa_id = info.get("external_reference")

                if empresa_id:
                    empresa = Empresa.objects.get(id=empresa_id)

                    empresa.plano = "premium"
                    empresa.ativo = True
                    empresa.data_pagamento = datetime.date.today()
                    empresa.save()

                    print(f"✅ Empresa {empresa_id} ativada")

        except Exception as e:
            print("ERRO WEBHOOK:", e)

    return JsonResponse({"status": "ok"})


# =====================================================
# 💳 PAGAMENTO DIRETO (OPCIONAL - MAIS AVANÇADO)
# =====================================================
@csrf_exempt
def pagar_direto(request):

    if request.method != "POST":
        return JsonResponse({"erro": "método inválido"}, status=400)

    data = json.loads(request.body or "{}")

    token = data.get("token")
    email = data.get("email")
    empresa_id = data.get("empresa_id")

    if not token or not email or not empresa_id:
        return JsonResponse({"erro": "dados incompletos"}, status=400)

    payment_data = {
        "transaction_amount": 29.90,
        "token": token,
        "description": "Plano SaaS Saúde",
        "installments": 1,
        "payment_method_id": "visa",
        "payer": {
            "email": email
        }
    }

    try:
        result = SDK.payment().create(payment_data)
        response = result["response"]

        print("MP RESPONSE:", response)

        if response.get("status") == "approved":

            empresa = Empresa.objects.get(id=empresa_id)
            empresa.plano = "premium"
            empresa.ativo = True
            empresa.data_pagamento = datetime.date.today()
            empresa.save()

            return JsonResponse({"status": "aprovado"})

        else:
            return JsonResponse({
                "status": "recusado",
                "detalhe": response
            })

    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# =====================================================
# 📄 PÁGINAS DE RETORNO
# =====================================================


def sucesso(request):

    status = request.GET.get("status") or request.GET.get("collection_status")
    empresa_id = request.GET.get("external_reference")

    print("STATUS:", status)
    print("EMPRESA ID:", empresa_id)

    if status == "approved" and empresa_id:

        empresa = Empresa.objects.filter(id=empresa_id).first()

        if empresa:
            empresa.plano = "premium"
            empresa.ativo = True
            empresa.save()

            print("✅ EMPRESA ATIVADA")

            return redirect("/dashboard/")  # 🔥 AQUI

        return redirect("/pagamento/")

    return redirect("/pagamento/")


def pendente(request):
    return HttpResponse("Pagamento pendente ⏳")

def erro(request):
    return HttpResponse("Pagamento falhou ❌")


def status_pagamento(request):
    empresa_id = request.GET.get("empresa_id")

    if not empresa_id:
        return JsonResponse({"status": "erro"})

    try:
        empresa = Empresa.objects.get(id=empresa_id)

        if empresa.ativo:
            return JsonResponse({"status": "aprovado"})

        return JsonResponse({"status": "pendente"})

    except:
        return JsonResponse({"status": "erro"})