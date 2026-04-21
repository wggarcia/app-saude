import mercadopago
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
import json
import hashlib
import hmac
from .models import Empresa, FinanceiroEventoSaaS
from django.shortcuts import redirect, render
from django.utils.timezone import now
from datetime import timedelta
from .planos import detalhes_pacote, preco_pacote, pacote_padrao, normalizar_ciclo, normalizar_codigo_pacote
from django.conf import settings


def _sdk():
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADO_PAGO_ACCESS_TOKEN não configurado.")
    return mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)


def _public_url(path):
    return f"{settings.PUBLIC_BASE_URL}{path}"


def _webhook_assinatura_valida(request, payment_id):
    secret = settings.MERCADO_PAGO_WEBHOOK_SECRET
    if not secret:
        return True

    signature = request.headers.get("x-signature", "")
    request_id = request.headers.get("x-request-id", "")
    ts = None
    v1 = None
    for part in signature.split(","):
        key, _, value = part.strip().partition("=")
        if key == "ts":
            ts = value
        elif key == "v1":
            v1 = value

    if not ts or not v1 or not request_id or not payment_id:
        return False

    manifest = f"id:{payment_id};request-id:{request_id};ts:{ts};"
    digest = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, v1)


def _redirect_com_empresa(destino, empresa_id):
    response = redirect(f"{destino}?empresa_id={empresa_id}")
    response.set_cookie("empresa_id", str(empresa_id), samesite="Lax")
    return response


def _registrar_evento_financeiro(empresa, tipo_evento, status, valor=0, observacao=""):
    FinanceiroEventoSaaS.objects.create(
        empresa=empresa,
        tipo_evento=tipo_evento,
        pacote_codigo=empresa.pacote_codigo,
        ciclo=empresa.plano,
        valor=valor,
        status=status,
        observacao=observacao,
    )


# =====================================================
# 💳 CRIAR PAGAMENTO (COM PLANO)
# =====================================================
@csrf_exempt
def criar_pagamento(request, empresa_id=None):

    if not empresa_id:
        return JsonResponse({"erro": "empresa não identificada"}, status=400)

    empresa = Empresa.objects.get(id=empresa_id)
    pacote_codigo = normalizar_codigo_pacote(request.GET.get("pacote", pacote_padrao()))
    plano = normalizar_ciclo(pacote_codigo, request.GET.get("plano", "mensal"))
    pacote = detalhes_pacote(pacote_codigo)
    valor = preco_pacote(pacote_codigo, plano)

    if empresa.tipo_conta == Empresa.TIPO_GOVERNO or pacote["setor"] == "governo":
        return JsonResponse({
            "erro": "Contratos governamentais sao anuais e fechados por proposta institucional. Use o ambiente de contrato governamental.",
            "redirect": "/contrato-governo/",
        }, status=403)

    empresa.plano = plano
    empresa.pacote_codigo = pacote_codigo
    empresa.max_dispositivos = pacote["dispositivos"]
    empresa.max_usuarios = pacote["usuarios"]
    empresa.save()
    _registrar_evento_financeiro(
        empresa,
        "checkout_iniciado",
        "pendente",
        valor,
        f"Pacote {pacote['label']} no ciclo {plano}",
    )

    preference_data = {
        "items": [
            {
                "title": f"{pacote['label']} - {plano.upper()} SaaS Saúde",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": valor
            }
        ],
        "external_reference": str(empresa_id),
        "back_urls": {
            "success": _public_url("/sucesso/"),
            "failure": _public_url("/erro/"),
            "pending": _public_url("/pendente/")
        },
        "auto_return": "approved",
        "notification_url": _public_url("/api/webhook")
    }

    try:
        response = _sdk().preference().create(preference_data)

        return JsonResponse({
            "status": "ok",
            "init_point": response["response"]["init_point"]
        })

    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# =====================================================
# 🔔 WEBHOOK (ATIVA + EXPIRAÇÃO)
# =====================================================
@csrf_exempt
def webhook(request):

    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    try:
        data = json.loads(request.body or "{}")
    except:
        return JsonResponse({"status": "erro_json"})

    if data.get("type") == "payment":

        payment_id = data.get("data", {}).get("id")

        if not payment_id:
            return JsonResponse({"status": "sem_id"})
        if not _webhook_assinatura_valida(request, payment_id):
            return JsonResponse({"status": "assinatura_invalida"}, status=401)

        try:
            pagamento = _sdk().payment().get(payment_id)
            info = pagamento["response"]

            if info.get("status") == "approved":

                empresa_id = info.get("external_reference")

                if empresa_id:
                    empresa = Empresa.objects.get(id=empresa_id)

                    # 🔥 define duração do plano
                    if empresa.plano == "anual":
                        dias = 365
                    else:
                        dias = 30

                    empresa.ativo = True
                    empresa.data_pagamento = now().date()
                    empresa.data_expiracao = now() + timedelta(days=dias)

                    empresa.save()
                    _registrar_evento_financeiro(
                        empresa,
                        "pagamento_aprovado",
                        "aprovado",
                        preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal"),
                        "Webhook Mercado Pago",
                    )

        except Exception as e:
            return JsonResponse({"status": "erro_webhook"}, status=500)

    return JsonResponse({"status": "ok"})


# =====================================================
# 💳 PAGAMENTO DIRETO (CORRIGIDO)
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

    empresa = Empresa.objects.get(id=empresa_id)
    pacote = detalhes_pacote(empresa.pacote_codigo or pacote_padrao())
    valor = preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal")

    payment_data = {
        "transaction_amount": valor,
        "token": token,
        "description": f"{pacote['label']} SaaS Saúde",
        "installments": 1,
        "payment_method_id": "visa",
        "payer": {
            "email": email
        }
    }

    try:
        result = _sdk().payment().create(payment_data)
        response = result["response"]

        if response.get("status") == "approved":

            if empresa.plano == "anual":
                dias = 365
            else:
                dias = 30

            empresa.ativo = True
            empresa.data_pagamento = now().date()
            empresa.data_expiracao = now() + timedelta(days=dias)

            empresa.save()
            _registrar_evento_financeiro(
                empresa,
                "pagamento_direto",
                "aprovado",
                valor,
                "Pagamento direto aprovado",
            )

            return JsonResponse({"status": "aprovado"})

        else:
            return JsonResponse({"status": "recusado"})

    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# =====================================================
# 📄 SUCESSO
# =====================================================
def sucesso(request):

    status = request.GET.get("status") or request.GET.get("collection_status")
    empresa_id = request.GET.get("external_reference")

    if status == "approved" and empresa_id:

        empresa = Empresa.objects.filter(id=empresa_id).first()

        if empresa:

            if empresa.plano == "anual":
                dias = 365
            else:
                dias = 30

            empresa.ativo = True
            empresa.data_pagamento = now().date()
            empresa.data_expiracao = now() + timedelta(days=dias)

            empresa.save()
            _registrar_evento_financeiro(
                empresa,
                "retorno_sucesso",
                "aprovado",
                preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal"),
                "Retorno de aprovação",
            )

            return _redirect_com_empresa("/dashboard/", empresa.id)

    if empresa_id:
        return _redirect_com_empresa("/pagamento/", empresa_id)

    return redirect("/pagamento/")


def pendente(request):
    empresa_id = request.GET.get("external_reference") or request.GET.get("empresa_id")
    response = render(request, "pendente.html", {
        "empresa_id": empresa_id or ""
    })

    if empresa_id:
        response.set_cookie("empresa_id", str(empresa_id), samesite="Lax")

    return response


def erro(request):
    return HttpResponse("Pagamento falhou ❌")


# =====================================================
# 🔐 STATUS PAGAMENTO
# =====================================================
def status_pagamento(request):

    empresa_id = request.GET.get("empresa_id")

    if not empresa_id:
        return JsonResponse({"status": "erro"})

    try:
        empresa = Empresa.objects.get(id=empresa_id)

        # 🔥 expiração automática
        if empresa.data_expiracao and empresa.data_expiracao < now():
            empresa.ativo = False
            empresa.save()

        if empresa.ativo:
            return JsonResponse({
                "status": "aprovado",
                "plano": empresa.plano,
                "pacote_codigo": empresa.pacote_codigo,
                "max_usuarios": empresa.max_usuarios,
                "max_dispositivos": empresa.max_dispositivos,
                "expira_em": empresa.data_expiracao
            })

        return JsonResponse({"status": "pendente"})

    except:
        return JsonResponse({"status": "erro"})
