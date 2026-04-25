import datetime
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import mercadopago
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .models import Empresa

VALOR_ASSINATURA = 29.90
PACOTES_EMPRESA = {
    "empresa_starter": {
        "nome": "Empresa Starter",
        "segmento": "empresa",
        "descricao": "Saude ocupacional e radar territorial para pequenas equipes.",
        "sla": "Essencial",
        "usuarios": 5,
        "maquinas": 5,
        "precos": {"MONTHLY": 799.00, "YEARLY": 7990.00},
        "plano_codigo": {"MONTHLY": "emp_start_m", "YEARLY": "emp_start_a"},
    },
    "empresa_profissional": {
        "nome": "Empresa Profissional",
        "segmento": "empresa",
        "descricao": "Monitoramento B2B com dashboards, alertas e gestao de usuarios.",
        "sla": "Essencial",
        "usuarios": 25,
        "maquinas": 25,
        "precos": {"MONTHLY": 1990.00, "YEARLY": 19900.00},
        "plano_codigo": {"MONTHLY": "emp_prof_m", "YEARLY": "emp_prof_a"},
    },
    "empresa_enterprise": {
        "nome": "Empresa Enterprise",
        "segmento": "empresa",
        "descricao": "Operacao corporativa multiunidade com inteligencia epidemiologica.",
        "sla": "Profissional",
        "usuarios": 100,
        "maquinas": 100,
        "precos": {"MONTHLY": 4900.00, "YEARLY": 49000.00},
        "plano_codigo": {"MONTHLY": "emp_ent_m", "YEARLY": "emp_ent_a"},
    },
    "empresa_corporativo": {
        "nome": "Empresa Corporativo",
        "segmento": "empresa",
        "descricao": "Cobertura corporativa nacional com governanca de acesso.",
        "sla": "Profissional",
        "usuarios": 250,
        "maquinas": 250,
        "precos": {"MONTHLY": 9900.00, "YEARLY": 99000.00},
        "plano_codigo": {"MONTHLY": "emp_corp_m", "YEARLY": "emp_corp_a"},
    },
    "empresa_nacional": {
        "nome": "Empresa Nacional",
        "segmento": "empresa",
        "descricao": "Radar nacional para grupos empresariais com operacao em varios estados.",
        "sla": "Profissional",
        "usuarios": 500,
        "maquinas": 500,
        "precos": {"MONTHLY": 19900.00, "YEARLY": 199000.00},
        "plano_codigo": {"MONTHLY": "emp_nac_m", "YEARLY": "emp_nac_a"},
    },
    "empresa_nacional_1000": {
        "nome": "Empresa Nacional 1000",
        "segmento": "empresa",
        "descricao": "Operacao enterprise ampliada com ate 1000 usuarios e maquinas autorizadas.",
        "sla": "Critico",
        "usuarios": 1000,
        "maquinas": 1000,
        "precos": {"MONTHLY": 35000.00, "YEARLY": 350000.00},
        "plano_codigo": {"MONTHLY": "emp_n1000_m", "YEARLY": "emp_n1000_a"},
    },
    "farmacia_local": {
        "nome": "Farmacia Local",
        "segmento": "farmacia",
        "descricao": "Focos por bairro para abastecimento preventivo de prateleiras.",
        "sla": "Essencial",
        "usuarios": 5,
        "maquinas": 5,
        "precos": {"MONTHLY": 699.00, "YEARLY": 6990.00},
        "plano_codigo": {"MONTHLY": "farm_loc_m", "YEARLY": "farm_loc_a"},
    },
    "rede_farmaceutica_regional": {
        "nome": "Rede Farmaceutica Regional",
        "segmento": "farmacia",
        "descricao": "Inteligencia de demanda por regiao, sintomas e provaveis doencas.",
        "sla": "Profissional",
        "usuarios": 50,
        "maquinas": 50,
        "precos": {"MONTHLY": 6000.00, "YEARLY": 60000.00},
        "plano_codigo": {"MONTHLY": "farm_reg_m", "YEARLY": "farm_reg_a"},
    },
    "hospital_medio": {
        "nome": "Hospital Medio",
        "segmento": "hospital",
        "descricao": "Preparacao de pronto atendimento, leitos e pressao assistencial.",
        "sla": "Critico",
        "usuarios": 50,
        "maquinas": 50,
        "precos": {"MONTHLY": 18000.00, "YEARLY": 180000.00},
        "plano_codigo": {"MONTHLY": "hosp_med_m", "YEARLY": "hosp_med_a"},
        "faixa_negociacao": "R$ 15000 a R$ 25000 por mes",
    },
    "rede_hospitalar": {
        "nome": "Rede Hospitalar",
        "segmento": "hospital",
        "descricao": "Sala de situacao para rede hospitalar com risco territorial e SRAG.",
        "sla": "Critico",
        "usuarios": 250,
        "maquinas": 250,
        "precos": {"MONTHLY": 75000.00, "YEARLY": 750000.00},
        "plano_codigo": {"MONTHLY": "rede_hosp_m", "YEARLY": "rede_hosp_a"},
        "faixa_negociacao": "R$ 45000 a R$ 90000 por mes",
    },
}
PACKAGE_ID_ALIAS = {
    "farmacia_regional": "rede_farmaceutica_regional",
    "hospital_plus": "hospital_medio",
    "rede_nacional": "empresa_nacional",
    # aliases legados da tela de pagamento antiga
    "empresa_starter_5": "empresa_starter",
    "empresa_profissional_25": "empresa_profissional",
    "empresa_enterprise_100": "empresa_enterprise",
    "empresa_corporativo_250": "empresa_corporativo",
    "empresa_nacional_500": "empresa_nacional",
    "empresa_nacional_1000": "empresa_nacional_1000",
    "farmacia_local_5": "farmacia_local",
    "rede_farmaceutica_regional_50": "rede_farmaceutica_regional",
    "hospital_medio_50": "hospital_medio",
    "rede_hospitalar_250": "rede_hospitalar",
}
STATUS_APROVADOS_ASAAS = {
    "RECEIVED",
    "CONFIRMED",
    "RECEIVED_IN_CASH",
    "PAYMENT_RECEIVED",
    "PAYMENT_CONFIRMED",
    "PAYMENT_APPROVED",
}


def _provider():
    return (getattr(settings, "PAYMENT_PROVIDER", "mercado_pago") or "mercado_pago").strip().lower()


def _mercado_pago_sdk():
    token = getattr(settings, "MERCADO_PAGO_ACCESS_TOKEN", "").strip()
    return mercadopago.SDK(token)


def _public_base_url(request):
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip()
    if base:
        return base.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def _redirect_com_empresa(destino, empresa_id):
    response = redirect(f"{destino}?empresa_id={empresa_id}")
    response.set_cookie("empresa_id", str(empresa_id), samesite="Lax")
    return response


def _normalizar_ciclo(ciclo):
    valor = str(ciclo or "MONTHLY").strip().upper()
    mapa = {
        "MENSAL": "MONTHLY",
        "MONTHLY": "MONTHLY",
        "ANUAL": "YEARLY",
        "YEARLY": "YEARLY",
    }
    return mapa.get(valor, "MONTHLY")


def _dados_pacote_publico(package_id, pacote):
    return {
        "id": package_id,
        "nome": pacote["nome"],
        "segmento": pacote["segmento"],
        "descricao": pacote.get("descricao", ""),
        "sla": pacote.get("sla", "Essencial"),
        "faixa_negociacao": pacote.get("faixa_negociacao"),
        "usuarios": pacote["usuarios"],
        "maquinas": pacote["maquinas"],
        "precos": pacote["precos"],
    }


def _extrair_pacote_e_ciclo(payload):
    package_id_raw = str((payload or {}).get("package_id") or "empresa_starter").strip().lower()
    package_id = PACKAGE_ID_ALIAS.get(package_id_raw, package_id_raw)
    cycle = _normalizar_ciclo((payload or {}).get("cycle"))

    pacote = PACOTES_EMPRESA.get(package_id)
    if not pacote:
        raise ValueError("Pacote inválido")

    valor = pacote["precos"].get(cycle)
    if valor is None:
        raise ValueError("Ciclo inválido para o pacote")

    return package_id, cycle, pacote, float(valor)


def _payload_pagamento(request):
    payload = {}

    # 1) JSON body (fluxo novo)
    try:
        payload = json.loads(request.body or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}

    # 2) fallback para form-data legado
    if not payload:
        payload = {
            "package_id": request.POST.get("package_id") or request.POST.get("pacote"),
            "cycle": request.POST.get("cycle") or request.POST.get("plano"),
        }

    # 3) fallback para query-string legado
    qs_package = request.GET.get("package_id") or request.GET.get("pacote")
    qs_cycle = request.GET.get("cycle") or request.GET.get("plano")

    if qs_package and not payload.get("package_id"):
        payload["package_id"] = qs_package
    if qs_cycle and not payload.get("cycle"):
        payload["cycle"] = qs_cycle

    return payload


def _build_external_reference(empresa_id, package_id, cycle):
    return f"{empresa_id}|{package_id}|{cycle}"


def _parse_external_reference(reference):
    valor = str(reference or "").strip()
    if not valor:
        return None, None, None

    partes = valor.split("|")
    empresa_id = partes[0].strip() if partes else None
    package_id = partes[1].strip() if len(partes) > 1 else None
    cycle = _normalizar_ciclo(partes[2]) if len(partes) > 2 else None
    return empresa_id, package_id, cycle


def _plano_codigo(package_id, cycle):
    pacote = PACOTES_EMPRESA.get(package_id) or {}
    return ((pacote.get("plano_codigo") or {}).get(cycle) or "premium")[:20]


def _ativar_empresa(empresa, package_id=None, cycle=None):
    empresa.plano = _plano_codigo(package_id, cycle)
    empresa.ativo = True
    empresa.data_pagamento = datetime.date.today()
    empresa.save(update_fields=["plano", "ativo", "data_pagamento"])


def _asaas_request(method, path, payload=None, query=None):
    api_key = (getattr(settings, "ASAAS_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("ASAAS_API_KEY não configurada")

    base_url = (getattr(settings, "ASAAS_BASE_URL", "https://api.asaas.com/v3") or "").strip().rstrip("/")
    if " " in base_url:
        raise RuntimeError("ASAAS_BASE_URL inválida. Use apenas a URL, ex: https://api.asaas.com/v3")

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
        with urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Asaas HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Asaas indisponível: {exc}") from exc


def _asaas_cliente_id(empresa):
    referencia = f"empresa-{empresa.id}"
    consulta = _asaas_request("GET", "/customers", query={"externalReference": referencia})
    clientes = consulta.get("data") or []
    if clientes:
        return clientes[0].get("id")

    criado = _asaas_request(
        "POST",
        "/customers",
        payload={
            "name": empresa.nome,
            "email": empresa.email,
            "externalReference": referencia,
            "notificationDisabled": False,
        },
    )
    return criado.get("id")


def _asaas_criar_pagamento(empresa, request, package_id, cycle, valor):
    customer_id = _asaas_cliente_id(empresa)
    if not customer_id:
        raise RuntimeError("Não foi possível criar cliente no Asaas")

    base_url = _public_base_url(request)
    vencimento = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    external_reference = _build_external_reference(empresa.id, package_id, cycle)
    descricao = f"Assinatura SaaS Saúde - {package_id} ({cycle})"

    pagamento = _asaas_request(
        "POST",
        "/payments",
        payload={
            "customer": customer_id,
            "billingType": "UNDEFINED",
            "value": valor,
            "dueDate": vencimento,
            "description": descricao,
            "externalReference": external_reference,
            "callback": {
                "successUrl": f"{base_url}/sucesso/?empresa_id={empresa.id}",
                "autoRedirect": True,
            },
        },
    )

    checkout_url = pagamento.get("invoiceUrl") or pagamento.get("bankSlipUrl")
    if not checkout_url:
        raise RuntimeError("Asaas não retornou URL de checkout")

    return {
        "id": pagamento.get("id"),
        "url": checkout_url,
    }


def _asaas_pagamento_por_id(payment_id):
    if not payment_id:
        return {}
    return _asaas_request("GET", f"/payments/{payment_id}")


def _asaas_status_aprovado(status):
    if not status:
        return False
    return str(status).strip().upper() in STATUS_APROVADOS_ASAAS


def planos_publicos(request):
    catalogo = [
        _dados_pacote_publico(package_id, pacote)
        for package_id, pacote in PACOTES_EMPRESA.items()
    ]
    return JsonResponse({"packages": catalogo})


@csrf_exempt
def criar_pagamento(request, empresa_id=None):
    if request.method != "POST":
        return JsonResponse({"erro": "método inválido"}, status=405)

    if not empresa_id:
        return JsonResponse({"erro": "empresa não identificada"}, status=400)

    empresa = Empresa.objects.filter(id=empresa_id).first()
    if not empresa:
        return JsonResponse({"erro": "empresa não encontrada"}, status=404)

    payload = _payload_pagamento(request)

    try:
        package_id, cycle, pacote, valor = _extrair_pacote_e_ciclo(payload)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=400)

    provider = _provider()

    if provider == "asaas":
        try:
            cobranca = _asaas_criar_pagamento(empresa, request, package_id, cycle, valor)
            return JsonResponse(
                {
                    "status": "ok",
                    "provider": "asaas",
                    "package_id": package_id,
                    "cycle": cycle,
                    "value": valor,
                    "payment_id": cobranca["id"],
                    "init_point": cobranca["url"],
                }
            )
        except Exception as exc:
            return JsonResponse({"erro": f"Asaas: {exc}"}, status=500)

    preference_data = {
        "items": [
            {
                "title": f"{pacote['nome']} - {cycle}",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": valor,
            }
        ],
        "external_reference": _build_external_reference(empresa_id, package_id, cycle),
        "back_urls": {
            "success": f"{_public_base_url(request)}/sucesso/",
            "failure": f"{_public_base_url(request)}/erro/",
            "pending": f"{_public_base_url(request)}/pendente/",
        },
        "auto_return": "approved",
        "notification_url": f"{_public_base_url(request)}/api/webhook",
    }

    try:
        response = _mercado_pago_sdk().preference().create(preference_data)
        return JsonResponse(
            {
                "status": "ok",
                "provider": "mercado_pago",
                "package_id": package_id,
                "cycle": cycle,
                "value": valor,
                "init_point": response["response"]["init_point"],
            }
        )
    except Exception as exc:
        return JsonResponse({"erro": f"Mercado Pago: {exc}"}, status=500)


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"status": "erro_json"}, status=400)

    if "event" in data and isinstance(data.get("payment"), dict):
        expected_token = (getattr(settings, "ASAAS_WEBHOOK_TOKEN", "") or "").strip()
        received_token = (request.headers.get("asaas-access-token") or "").strip()
        if expected_token and expected_token != received_token:
            return JsonResponse({"status": "token_invalido"}, status=403)

        payment = data.get("payment") or {}
        evento = str(data.get("event") or "").strip().upper()
        status_pagamento = str(payment.get("status") or "").strip().upper()
        empresa_id, package_id, cycle = _parse_external_reference(payment.get("externalReference"))

        if empresa_id and (_asaas_status_aprovado(status_pagamento) or _asaas_status_aprovado(evento)):
            empresa = Empresa.objects.filter(id=empresa_id).first()
            if empresa:
                _ativar_empresa(empresa, package_id, cycle)

        return JsonResponse({"status": "ok_asaas"})

    if data.get("type") == "payment":
        payment_id = data.get("data", {}).get("id")
        if not payment_id:
            return JsonResponse({"status": "sem_id"})
        try:
            pagamento = _mercado_pago_sdk().payment().get(payment_id)
            info = pagamento["response"]
            if info.get("status") == "approved":
                empresa_id, package_id, cycle = _parse_external_reference(info.get("external_reference"))
                empresa = Empresa.objects.filter(id=empresa_id).first()
                if empresa:
                    _ativar_empresa(empresa, package_id, cycle)
        except Exception as exc:
            return JsonResponse({"status": "erro_mp", "detalhe": str(exc)}, status=500)

        return JsonResponse({"status": "ok_mp"})

    return JsonResponse({"status": "ignorado"})


@csrf_exempt
def pagar_direto(request):
    if _provider() == "asaas":
        return JsonResponse(
            {"erro": "No Asaas use checkout (api/assinatura) em vez de cartão direto."},
            status=400,
        )

    if request.method != "POST":
        return JsonResponse({"erro": "método inválido"}, status=400)

    data = json.loads(request.body or "{}")
    token = data.get("token")
    email = data.get("email")
    empresa_id = data.get("empresa_id")

    if not token or not email or not empresa_id:
        return JsonResponse({"erro": "dados incompletos"}, status=400)

    payment_data = {
        "transaction_amount": VALOR_ASSINATURA,
        "token": token,
        "description": "Plano SaaS Saúde",
        "installments": 1,
        "payment_method_id": "visa",
        "payer": {
            "email": email,
        },
    }

    try:
        result = _mercado_pago_sdk().payment().create(payment_data)
        response = result["response"]
        if response.get("status") == "approved":
            empresa = Empresa.objects.filter(id=empresa_id).first()
            if not empresa:
                return JsonResponse({"erro": "empresa não encontrada"}, status=404)
            _ativar_empresa(empresa, "farmacia_regional", "MONTHLY")
            return JsonResponse({"status": "aprovado"})
        return JsonResponse({"status": "recusado", "detalhe": response})
    except Exception as exc:
        return JsonResponse({"erro": str(exc)}, status=500)


def sucesso(request):
    status = request.GET.get("status") or request.GET.get("collection_status") or ""
    empresa_id = request.GET.get("external_reference") or request.GET.get("empresa_id")

    if empresa_id and str(status).strip().lower() == "approved":
        empresa = Empresa.objects.filter(id=empresa_id).first()
        if empresa:
            ref = request.GET.get("external_reference")
            _, package_id, cycle = _parse_external_reference(ref)
            _ativar_empresa(empresa, package_id, cycle)
            return _redirect_com_empresa("/dashboard/", empresa.id)

    if empresa_id:
        return _redirect_com_empresa("/pendente/", empresa_id)

    payment_id = request.GET.get("payment_id") or request.GET.get("payment")
    if _provider() == "asaas" and payment_id:
        try:
            pagamento = _asaas_pagamento_por_id(payment_id)
            empresa_id, package_id, cycle = _parse_external_reference(pagamento.get("externalReference"))
            if empresa_id and _asaas_status_aprovado(pagamento.get("status")):
                empresa = Empresa.objects.filter(id=empresa_id).first()
                if empresa:
                    _ativar_empresa(empresa, package_id, cycle)
                    return _redirect_com_empresa("/dashboard/", empresa.id)
            if empresa_id:
                return _redirect_com_empresa("/pendente/", empresa_id)
        except Exception:
            pass

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


def status_pagamento(request):
    empresa_id = request.GET.get("empresa_id")
    if not empresa_id:
        return JsonResponse({"status": "erro"})

    empresa = Empresa.objects.filter(id=empresa_id).first()
    if not empresa:
        return JsonResponse({"status": "erro"})
    if empresa.ativo:
        return JsonResponse({"status": "aprovado"})
    return JsonResponse({"status": "pendente"})
