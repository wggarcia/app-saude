import datetime
import hashlib
import hmac
import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import mercadopago
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt

from .models import Empresa, FinanceiroEventoSaaS
from .planos import (
    detalhes_pacote,
    normalizar_ciclo,
    normalizar_codigo_pacote,
    pacote_padrao,
    pacotes_por_setor,
    preco_pacote,
)

PACOTE_ALIAS = {
    # aliases do checkout mais novo
    "empresa_starter": "empresa_starter_5",
    "empresa_profissional": "empresa_profissional_25",
    "empresa_enterprise": "empresa_enterprise_100",
    "empresa_corporativo": "empresa_corporativo_250",
    "empresa_nacional": "empresa_nacional_500",
    "farmacia_local_5": "farmacia_local",
    "rede_farmaceutica_regional": "farmacia_rede_regional",
    "rede_farmaceutica_regional_50": "farmacia_rede_regional",
    "hospital_medio_50": "hospital_medio",
    "rede_hospitalar": "hospital_rede",
    "rede_hospitalar_250": "hospital_rede",
}

STATUS_APROVADOS_ASAAS = {
    "RECEIVED",
    "CONFIRMED",
    "RECEIVED_IN_CASH",
    "PAYMENT_RECEIVED",
    "PAYMENT_CONFIRMED",
    "PAYMENT_APPROVED",
}


def _somente_digitos(valor):
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _cpf_cnpj_valido(valor):
    return len(_somente_digitos(valor)) in {11, 14}


def _provider():
    return (getattr(settings, "PAYMENT_PROVIDER", "mercado_pago") or "mercado_pago").strip().lower()


def _sdk():
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADO_PAGO_ACCESS_TOKEN nao configurado.")
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


def _normalizar_pacote(codigo):
    codigo = (codigo or pacote_padrao()).strip()
    codigo = PACOTE_ALIAS.get(codigo, codigo)
    return normalizar_codigo_pacote(codigo)


def _payload_pagamento(request):
    payload = {}
    try:
        payload = json.loads(request.body or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}

    if not payload:
        payload = {
            "package_id": request.POST.get("package_id") or request.POST.get("pacote"),
            "cycle": request.POST.get("cycle") or request.POST.get("plano"),
        }

    package_id = request.GET.get("package_id") or request.GET.get("pacote")
    cycle = request.GET.get("cycle") or request.GET.get("plano")
    cpf_cnpj = request.GET.get("cpf_cnpj") or request.GET.get("cpfCnpj")
    if package_id and not payload.get("package_id"):
        payload["package_id"] = package_id
    if cycle and not payload.get("cycle"):
        payload["cycle"] = cycle
    if cpf_cnpj and not payload.get("cpf_cnpj"):
        payload["cpf_cnpj"] = cpf_cnpj

    return payload


def _resolver_pacote_ciclo(payload):
    pacote_codigo = _normalizar_pacote(payload.get("package_id") or payload.get("pacote") or pacote_padrao())
    ciclo = normalizar_ciclo(pacote_codigo, payload.get("cycle") or payload.get("plano") or "mensal")
    pacote = detalhes_pacote(pacote_codigo)
    valor = preco_pacote(pacote_codigo, ciclo)
    return pacote_codigo, ciclo, pacote, valor


def _atualizar_contrato_empresa(empresa, pacote_codigo, ciclo, pacote):
    empresa.plano = ciclo
    empresa.pacote_codigo = pacote_codigo
    empresa.max_dispositivos = pacote["dispositivos"]
    empresa.max_usuarios = pacote["usuarios"]
    empresa.save(update_fields=["plano", "pacote_codigo", "max_dispositivos", "max_usuarios"])


def _ativar_empresa(empresa):
    dias = 365 if empresa.plano == "anual" else 30
    empresa.ativo = True
    empresa.data_pagamento = now().date()
    empresa.data_expiracao = now() + timedelta(days=dias)
    empresa.save(update_fields=["ativo", "data_pagamento", "data_expiracao"])


def _asaas_request(method, path, payload=None, query=None):
    api_key = (getattr(settings, "ASAAS_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("ASAAS_API_KEY nao configurada.")

    base_url = (getattr(settings, "ASAAS_BASE_URL", "https://api.asaas.com/v3") or "").strip().rstrip("/")
    if " " in base_url:
        raise RuntimeError("ASAAS_BASE_URL invalida. Use ex: https://api.asaas.com/v3")

    user_agent = (getattr(settings, "ASAAS_USER_AGENT", "") or "").strip() or "SolusCRT-Saude/1.0"
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    body = None
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "User-Agent": user_agent,
        "access_token": api_key,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = Request(url=url, method=method.upper(), data=body, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Asaas HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Asaas indisponivel: {exc}") from exc


def _asaas_cliente_id(empresa, cpf_cnpj):
    referencia = f"empresa-{empresa.id}"
    cpf_cnpj = _somente_digitos(cpf_cnpj)
    consulta = _asaas_request("GET", "/customers", query={"externalReference": referencia})
    clientes = consulta.get("data") or []
    if clientes:
        cliente = clientes[0]
        customer_id = cliente.get("id")
        documento_atual = _somente_digitos(cliente.get("cpfCnpj"))
        if customer_id and cpf_cnpj and documento_atual != cpf_cnpj:
            payload_update = {
                "name": empresa.nome,
                "email": empresa.email,
                "cpfCnpj": cpf_cnpj,
                "externalReference": referencia,
            }
            try:
                _asaas_request("POST", f"/customers/{customer_id}", payload=payload_update)
            except RuntimeError:
                try:
                    _asaas_request("PUT", f"/customers/{customer_id}", payload=payload_update)
                except RuntimeError:
                    pass
        return customer_id

    criado = _asaas_request(
        "POST",
        "/customers",
        payload={
            "name": empresa.nome,
            "email": empresa.email,
            "externalReference": referencia,
            "notificationDisabled": False,
            "cpfCnpj": cpf_cnpj,
        },
    )
    return criado.get("id")


def _asaas_status_aprovado(status):
    if not status:
        return False
    return str(status).strip().upper() in STATUS_APROVADOS_ASAAS


def _asaas_pagamento_por_id(payment_id):
    if not payment_id:
        return {}
    return _asaas_request("GET", f"/payments/{payment_id}")


def _asaas_criar_pagamento(request, empresa, valor, descricao, cpf_cnpj):
    customer_id = _asaas_cliente_id(empresa, cpf_cnpj)
    if not customer_id:
        raise RuntimeError("Nao foi possivel criar cliente no Asaas.")

    vencimento = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    pagamento = _asaas_request(
        "POST",
        "/payments",
        payload={
            "customer": customer_id,
            "billingType": "UNDEFINED",
            "value": valor,
            "dueDate": vencimento,
            "description": descricao,
            "externalReference": str(empresa.id),
            "callback": {
                "successUrl": f"{_public_url('/sucesso/')}?empresa_id={empresa.id}",
                "autoRedirect": True,
            },
        },
    )
    checkout_url = pagamento.get("invoiceUrl") or pagamento.get("bankSlipUrl")
    if not checkout_url:
        raise RuntimeError("Asaas nao retornou URL de checkout.")
    return pagamento.get("id"), checkout_url


@csrf_exempt
def planos_publicos(request):
    pacotes = pacotes_por_setor(incluir_governo=False)
    retorno = []
    for codigo, pacote in pacotes.items():
        retorno.append(
            {
                "codigo": codigo,
                "label": pacote["label"],
                "setor": pacote["setor"],
                "descricao": pacote.get("descricao", ""),
                "usuarios": pacote["usuarios"],
                "dispositivos": pacote["dispositivos"],
                "mensal": pacote["mensal"],
                "anual": pacote["anual"],
                "ciclos": pacote["ciclos"],
            }
        )
    return JsonResponse({"pacotes": retorno})


# =====================================================
# 💳 CRIAR PAGAMENTO (MERCADO PAGO + ASAAS)
# =====================================================
@csrf_exempt
def criar_pagamento(request, empresa_id=None):
    if request.method != "POST":
        return JsonResponse({"erro": "metodo invalido"}, status=405)

    if not empresa_id:
        return JsonResponse({"erro": "empresa nao identificada"}, status=400)

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except ObjectDoesNotExist:
        return JsonResponse({"erro": "Conta empresarial nao encontrada. Entre novamente pelo login empresarial."}, status=404)

    payload = _payload_pagamento(request)
    pacote_codigo, plano, pacote, valor = _resolver_pacote_ciclo(payload)

    if empresa.tipo_conta == Empresa.TIPO_GOVERNO or pacote["setor"] == "governo":
        return JsonResponse(
            {
                "erro": "Contratos governamentais sao anuais e fechados por proposta institucional. Use o ambiente de contrato governamental.",
                "redirect": "/contrato-governo/",
            },
            status=403,
        )

    if not valor or valor <= 0:
        return JsonResponse({"erro": "Pacote sem valor de checkout configurado."}, status=400)

    _atualizar_contrato_empresa(empresa, pacote_codigo, plano, pacote)
    _registrar_evento_financeiro(
        empresa,
        "checkout_iniciado",
        "pendente",
        valor,
        f"Pacote {pacote['label']} no ciclo {plano}",
    )

    provider = _provider()

    if provider == "asaas":
        cpf_cnpj = payload.get("cpf_cnpj") or payload.get("cpfCnpj")
        if not _cpf_cnpj_valido(cpf_cnpj):
            return JsonResponse(
                {
                    "erro": "Para pagamento via Asaas, informe CPF ou CNPJ valido do responsavel financeiro (11 ou 14 digitos).",
                },
                status=400,
            )
        try:
            payment_id, checkout_url = _asaas_criar_pagamento(
                request,
                empresa,
                valor,
                f"{pacote['label']} - {plano.upper()} SaaS Saude",
                cpf_cnpj,
            )
            return JsonResponse(
                {
                    "status": "ok",
                    "provider": "asaas",
                    "payment_id": payment_id,
                    "init_point": checkout_url,
                }
            )
        except Exception as exc:
            return JsonResponse({"erro": f"Asaas: {exc}"}, status=500)

    preference_data = {
        "items": [
            {
                "title": f"{pacote['label']} - {plano.upper()} SaaS Saude",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": valor,
            }
        ],
        "external_reference": str(empresa_id),
        "back_urls": {
            "success": _public_url("/sucesso/"),
            "failure": _public_url("/erro/"),
            "pending": _public_url("/pendente/"),
        },
        "auto_return": "approved",
        "notification_url": _public_url("/api/webhook"),
    }

    try:
        response = _sdk().preference().create(preference_data)
        preference = response.get("response", {})
        init_point = preference.get("init_point") or preference.get("sandbox_init_point")

        if not init_point:
            return JsonResponse(
                {
                    "erro": "Mercado Pago nao retornou link de checkout. Confira o token e a conta no painel de pagamento.",
                    "detalhes": preference.get("message") or response.get("status"),
                },
                status=502,
            )

        return JsonResponse(
            {
                "status": "ok",
                "provider": "mercado_pago",
                "init_point": init_point,
            }
        )
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


# =====================================================
# 🔔 WEBHOOK (MERCADO PAGO + ASAAS)
# =====================================================
@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"status": "erro_json"})

    # Asaas webhook
    if "event" in data and isinstance(data.get("payment"), dict):
        expected_token = (getattr(settings, "ASAAS_WEBHOOK_TOKEN", "") or "").strip()
        received_token = (request.headers.get("asaas-access-token") or "").strip()
        if expected_token and expected_token != received_token:
            return JsonResponse({"status": "token_invalido"}, status=403)

        payment = data.get("payment") or {}
        evento = str(data.get("event") or "").strip().upper()
        status_pagamento = str(payment.get("status") or "").strip().upper()
        empresa_id = str(payment.get("externalReference") or "").strip()

        if empresa_id and (_asaas_status_aprovado(status_pagamento) or _asaas_status_aprovado(evento)):
            empresa = Empresa.objects.filter(id=empresa_id).first()
            if empresa:
                _ativar_empresa(empresa)
                _registrar_evento_financeiro(
                    empresa,
                    "pagamento_aprovado",
                    "aprovado",
                    preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal"),
                    "Webhook Asaas",
                )
        return JsonResponse({"status": "ok_asaas"})

    # Mercado Pago webhook
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
                    empresa = Empresa.objects.filter(id=empresa_id).first()
                    if empresa:
                        _ativar_empresa(empresa)
                        _registrar_evento_financeiro(
                            empresa,
                            "pagamento_aprovado",
                            "aprovado",
                            preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal"),
                            "Webhook Mercado Pago",
                        )
        except Exception:
            return JsonResponse({"status": "erro_webhook"}, status=500)
        return JsonResponse({"status": "ok_mp"})

    return JsonResponse({"status": "ignorado"})


# =====================================================
# 💳 PAGAMENTO DIRETO (APENAS MERCADO PAGO)
# =====================================================
@csrf_exempt
def pagar_direto(request):
    if _provider() == "asaas":
        return JsonResponse(
            {"erro": "No Asaas, use o checkout de assinatura."},
            status=400,
        )

    if request.method != "POST":
        return JsonResponse({"erro": "metodo invalido"}, status=400)

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
        "description": f"{pacote['label']} SaaS Saude",
        "installments": 1,
        "payment_method_id": "visa",
        "payer": {
            "email": email
        },
    }

    try:
        result = _sdk().payment().create(payment_data)
        response = result["response"]

        if response.get("status") == "approved":
            _ativar_empresa(empresa)
            _registrar_evento_financeiro(
                empresa,
                "pagamento_direto",
                "aprovado",
                valor,
                "Pagamento direto aprovado",
            )
            return JsonResponse({"status": "aprovado"})

        return JsonResponse({"status": "recusado"})

    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


# =====================================================
# 📄 SUCESSO / PENDENTE / ERRO
# =====================================================
def sucesso(request):
    status = request.GET.get("status") or request.GET.get("collection_status")
    empresa_id = request.GET.get("external_reference") or request.GET.get("empresa_id")

    if status == "approved" and empresa_id:
        empresa = Empresa.objects.filter(id=empresa_id).first()
        if empresa:
            _ativar_empresa(empresa)
            _registrar_evento_financeiro(
                empresa,
                "retorno_sucesso",
                "aprovado",
                preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal"),
                "Retorno de aprovacao",
            )
            return _redirect_com_empresa("/dashboard/", empresa.id)

    # fluxo Asaas: retorno pode vir sem status, entao consulta payment_id
    payment_id = request.GET.get("payment_id") or request.GET.get("payment")
    if _provider() == "asaas" and payment_id:
        try:
            pagamento = _asaas_pagamento_por_id(payment_id)
            empresa_id = str(pagamento.get("externalReference") or empresa_id or "").strip()
            if empresa_id and _asaas_status_aprovado(pagamento.get("status")):
                empresa = Empresa.objects.filter(id=empresa_id).first()
                if empresa:
                    _ativar_empresa(empresa)
                    _registrar_evento_financeiro(
                        empresa,
                        "retorno_sucesso",
                        "aprovado",
                        preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal"),
                        "Retorno Asaas",
                    )
                    return _redirect_com_empresa("/dashboard/", empresa.id)
        except Exception:
            pass

    if empresa_id:
        return _redirect_com_empresa("/pagamento/", empresa_id)

    return redirect("/pagamento/")


def pendente(request):
    empresa_id = request.GET.get("external_reference") or request.GET.get("empresa_id")
    response = render(
        request,
        "pendente.html",
        {
            "empresa_id": empresa_id or "",
        },
    )

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

        if empresa.data_expiracao and empresa.data_expiracao < now():
            empresa.ativo = False
            empresa.save(update_fields=["ativo"])

        if empresa.ativo:
            return JsonResponse(
                {
                    "status": "aprovado",
                    "plano": empresa.plano,
                    "pacote_codigo": empresa.pacote_codigo,
                    "max_usuarios": empresa.max_usuarios,
                    "max_dispositivos": empresa.max_dispositivos,
                    "expira_em": empresa.data_expiracao,
                }
            )

        return JsonResponse({"status": "pendente"})
    except Exception:
        return JsonResponse({"status": "erro"})
