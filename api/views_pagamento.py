import datetime
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
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
from .services.auth_session import dono_autenticado_from_request, empresa_autenticada_from_request

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


def _public_url(path):
    return f"{settings.PUBLIC_BASE_URL}{path}"


def _destino_empresa(empresa):
    from .planos import detalhes_pacote as _dp
    setor = _dp(empresa.pacote_codigo).get("setor")
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return "/dashboard-governo/"
    if setor == "farmacia":
        return "/dashboard-farmacia/"
    if setor == "hospital":
        return "/dashboard-hospital/"
    return "/dashboard-empresa/"


def _redirect_com_empresa(destino, empresa_id):
    response = redirect(destino)
    response.set_cookie("empresa_id", str(empresa_id), samesite="Lax")
    return response


def _registrar_evento_financeiro(empresa, tipo_evento, status, valor=0, observacao=""):
    return FinanceiroEventoSaaS.objects.create(
        empresa=empresa,
        tipo_evento=tipo_evento,
        pacote_codigo=empresa.pacote_codigo,
        ciclo=empresa.plano,
        valor=valor,
        status=status,
        observacao=observacao,
    )


def _normalizar_pacote(codigo):
    return normalizar_codigo_pacote((codigo or pacote_padrao()).strip())


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
    empresa.data_expiracao = now() + datetime.timedelta(days=dias)
    empresa.save(update_fields=["ativo", "data_pagamento", "data_expiracao"])


def _status_assinatura(empresa):
    agora = now()
    pacote_codigo = normalizar_codigo_pacote(empresa.pacote_codigo)
    pacote = detalhes_pacote(pacote_codigo)
    ciclo = normalizar_ciclo(pacote_codigo, empresa.plano or "mensal")
    dias_restantes = None
    status = "inativo"

    if empresa.data_expiracao:
        dias_restantes = (empresa.data_expiracao - agora).days
    if empresa.ativo:
        if empresa.data_expiracao and empresa.data_expiracao < agora:
            status = "expirado"
        elif dias_restantes is not None and dias_restantes <= 7:
            status = "renovacao_urgente"
        elif dias_restantes is not None and dias_restantes <= 30:
            status = "renovacao_proxima"
        else:
            status = "ativo"
    elif empresa.data_expiracao and empresa.data_expiracao < agora:
        status = "expirado"

    return {
        "status": status,
        "ativo": bool(empresa.ativo and status != "expirado"),
        "pacote_codigo": pacote_codigo,
        "pacote_label": pacote["label"],
        "setor": pacote["setor"],
        "plano": ciclo,
        "valor_atual": preco_pacote(pacote_codigo, ciclo),
        "max_usuarios": empresa.max_usuarios,
        "max_dispositivos": empresa.max_dispositivos,
        "data_pagamento": empresa.data_pagamento.isoformat() if empresa.data_pagamento else None,
        "data_expiracao": empresa.data_expiracao.isoformat() if empresa.data_expiracao else None,
        "dias_restantes": dias_restantes,
    }


def _pagamento_ja_processado(empresa, payment_id):
    if not payment_id:
        return False
    return FinanceiroEventoSaaS.objects.filter(
        empresa=empresa,
        status="aprovado",
        observacao__contains=f"payment_id={payment_id}",
    ).exists()


def _processar_pagamento_aprovado(empresa, origem, payment_id="", valor=None):
    if _pagamento_ja_processado(empresa, payment_id):
        return False
    _ativar_empresa(empresa)
    valor_evento = valor
    if valor_evento is None:
        valor_evento = preco_pacote(empresa.pacote_codigo or pacote_padrao(), empresa.plano or "mensal")
    sufixo = f" payment_id={payment_id}" if payment_id else ""
    _registrar_evento_financeiro(
        empresa,
        "pagamento_aprovado",
        "aprovado",
        valor_evento,
        f"{origem}{sufixo}".strip(),
    )
    return True


# ── ASAAS ─────────────────────────────────────────────────────────────────────

def _asaas_request(method, path, payload=None, query=None):
    api_key = (getattr(settings, "ASAAS_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("ASAAS_API_KEY nao configurada.")

    base_url = (getattr(settings, "ASAAS_BASE_URL", "https://api.asaas.com/v3") or "").strip().rstrip("/")
    user_agent = (getattr(settings, "ASAAS_USER_AGENT", "") or "SolusCRT-Saude/1.0").strip()
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "User-Agent": user_agent,
        "access_token": api_key,
    }
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url=url, method=method.upper(), data=body, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
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
            payload_update = {"name": empresa.nome, "email": empresa.email,
                              "cpfCnpj": cpf_cnpj, "externalReference": referencia}
            try:
                _asaas_request("PUT", f"/customers/{customer_id}", payload=payload_update)
            except RuntimeError:
                pass
        return customer_id

    criado = _asaas_request("POST", "/customers", payload={
        "name": empresa.nome,
        "email": empresa.email,
        "externalReference": referencia,
        "notificationDisabled": False,
        "cpfCnpj": cpf_cnpj,
    })
    return criado.get("id")


def _asaas_status_aprovado(status):
    return bool(status) and str(status).strip().upper() in STATUS_APROVADOS_ASAAS


def _asaas_pagamento_por_id(payment_id):
    if not payment_id:
        return {}
    return _asaas_request("GET", f"/payments/{payment_id}")


def _asaas_criar_pagamento(empresa, valor, descricao, cpf_cnpj):
    customer_id = _asaas_cliente_id(empresa, cpf_cnpj)
    if not customer_id:
        raise RuntimeError("Nao foi possivel criar cliente no Asaas.")

    vencimento = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    pagamento = _asaas_request("POST", "/payments", payload={
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
    })
    checkout_url = pagamento.get("invoiceUrl") or pagamento.get("bankSlipUrl")
    if not checkout_url:
        raise RuntimeError("Asaas nao retornou URL de checkout.")
    return pagamento.get("id"), checkout_url


# ── WEBHOOK — verifica token obrigatório ──────────────────────────────────────

def _asaas_token_valido(request):
    expected = (getattr(settings, "ASAAS_WEBHOOK_TOKEN", "") or "").strip()
    if not expected:
        # Token não configurado = rejeitar tudo por segurança
        return False
    received = (request.headers.get("asaas-access-token") or "").strip()
    return hmac.compare_digest(expected, received)


# ── VIEWS ─────────────────────────────────────────────────────────────────────

def api_plano_features(request):
    """
    GET /api/plano/features
    Retorna o plano ativo, as features habilitadas e os limites da empresa autenticada.
    Usado pelo frontend para habilitar/desabilitar elementos de UI por plano.
    Resposta:
    {
      "plano": "empresa_enterprise_100",
      "label": "Empresa Enterprise",
      "setor": "empresa",
      "features": ["sst.aso", "sst.esocial", ...],
      "limites": {"max_usuarios": 100, "max_funcionarios": 1000, "max_unidades": 5}
    }
    """
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .access_control import get_features, get_limites
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return JsonResponse({
        "plano": empresa.pacote_codigo,
        "label": pacote.get("label", empresa.pacote_codigo),
        "setor": pacote.get("setor", ""),
        "features": sorted(get_features(empresa)),
        "limites": get_limites(empresa),
    })


@csrf_exempt
def planos_publicos(request):
    pacotes = pacotes_por_setor(incluir_governo=False)
    retorno = [
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
        for codigo, pacote in pacotes.items()
    ]
    return JsonResponse({"pacotes": retorno})


@csrf_exempt
def criar_pagamento(request, empresa_id=None):
    if request.method != "POST":
        return JsonResponse({"erro": "metodo invalido"}, status=405)

    if not empresa_id:
        return JsonResponse({"erro": "empresa nao identificada"}, status=400)

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except ObjectDoesNotExist:
        return JsonResponse({"erro": "Conta empresarial nao encontrada."}, status=404)

    payload = _payload_pagamento(request)
    pacote_codigo, plano, pacote, valor = _resolver_pacote_ciclo(payload)
    cpf_cnpj = payload.get("cpf_cnpj") or payload.get("cpfCnpj")

    if empresa.tipo_conta == Empresa.TIPO_GOVERNO or pacote["setor"] == "governo":
        return JsonResponse({
            "erro": "Contratos governamentais sao fechados por proposta institucional.",
            "redirect": "/contrato-governo/",
        }, status=403)

    if not valor or valor <= 0:
        return JsonResponse({"erro": "Pacote sem valor de checkout configurado."}, status=400)

    if not _cpf_cnpj_valido(cpf_cnpj):
        return JsonResponse({
            "erro": "Informe CPF ou CNPJ valido do responsavel financeiro (11 ou 14 digitos).",
        }, status=400)

    _atualizar_contrato_empresa(empresa, pacote_codigo, plano, pacote)
    _registrar_evento_financeiro(empresa, "checkout_iniciado", "pendente", valor,
                                 f"Pacote {pacote['label']} no ciclo {plano}")

    try:
        payment_id, checkout_url = _asaas_criar_pagamento(
            empresa, valor,
            f"{pacote['label']} - {plano.upper()} SolusCRT",
            cpf_cnpj,
        )
        _registrar_evento_financeiro(
            empresa,
            "checkout_criado",
            "pendente",
            valor,
            f"Asaas payment_id={payment_id}",
        )
        return JsonResponse({
            "status": "ok",
            "payment_id": payment_id,
            "init_point": checkout_url,
        })
    except Exception as exc:
        _registrar_evento_financeiro(
            empresa,
            "checkout_erro",
            "erro",
            valor,
            f"Asaas: {str(exc)[:800]}",
        )
        return JsonResponse({"erro": f"Asaas: {exc}"}, status=500)


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse({"status": "ok"})

    if not _asaas_token_valido(request):
        return JsonResponse({"status": "token_invalido"}, status=403)

    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"status": "erro_json"}, status=400)

    payment = data.get("payment") or {}
    evento = str(data.get("event") or "").strip().upper()
    status_pag = str(payment.get("status") or "").strip().upper()
    empresa_id = str(payment.get("externalReference") or "").strip()
    payment_id = str(payment.get("id") or "").strip()

    if empresa_id and (_asaas_status_aprovado(status_pag) or _asaas_status_aprovado(evento)):
        empresa = Empresa.objects.filter(id=empresa_id).first()
        if empresa:
            _processar_pagamento_aprovado(
                empresa,
                "Webhook Asaas",
                payment_id=payment_id,
                valor=payment.get("value"),
            )

    return JsonResponse({"status": "ok"})


def sucesso(request):
    """
    Retorno do Asaas após checkout. Sempre verificamos o status via API Asaas
    — nunca confiamos em query params do GET para ativar a conta.
    """
    payment_id = request.GET.get("payment_id") or request.GET.get("payment")
    empresa_id_param = request.GET.get("empresa_id") or request.GET.get("external_reference")

    empresa = None

    if payment_id:
        try:
            pagamento = _asaas_pagamento_por_id(payment_id)
            ref = str(pagamento.get("externalReference") or "").strip()
            if ref and _asaas_status_aprovado(pagamento.get("status")):
                empresa = Empresa.objects.filter(id=ref).first()
                if empresa:
                    _processar_pagamento_aprovado(
                        empresa,
                        "Retorno Asaas verificado",
                        payment_id=str(pagamento.get("id") or payment_id or "").strip(),
                        valor=pagamento.get("value"),
                    )
        except Exception:
            pass

    if empresa:
        destino = _destino_empresa(empresa)
        return _redirect_com_empresa(destino, empresa.id)

    # Pagamento pendente ou não confirmado ainda
    if empresa_id_param:
        return _redirect_com_empresa("/pagamento/", empresa_id_param)

    return redirect("/pagamento/")


def pendente(request):
    empresa_id = request.GET.get("external_reference") or request.GET.get("empresa_id")
    response = render(request, "pendente.html", {"empresa_id": empresa_id or ""})
    if empresa_id:
        response.set_cookie("empresa_id", str(empresa_id), samesite="Lax")
    return response


def erro(request):
    return render(request, "erro.html", {})


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
            return JsonResponse({
                "status": "aprovado",
                "plano": empresa.plano,
                "pacote_codigo": empresa.pacote_codigo,
                "max_usuarios": empresa.max_usuarios,
                "max_dispositivos": empresa.max_dispositivos,
                "expira_em": empresa.data_expiracao,
            })

        return JsonResponse({"status": "pendente"})
    except Exception:
        return JsonResponse({"status": "erro"})


def api_billing_status(request):
    empresa = empresa_autenticada_from_request(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    usuarios_ativos = empresa.usuarios.filter(ativo=True).count()
    dispositivos_ativos = empresa.dispositivos.filter(ativo=True).count()
    eventos = FinanceiroEventoSaaS.objects.filter(empresa=empresa).order_by("-criado_em")[:10]
    assinatura = _status_assinatura(empresa)

    return JsonResponse({
        "assinatura": assinatura,
        "uso": {
            "usuarios_ativos": usuarios_ativos,
            "usuarios_limite": empresa.max_usuarios,
            "usuarios_pct": round((usuarios_ativos / max(empresa.max_usuarios, 1)) * 100, 2),
            "dispositivos_ativos": dispositivos_ativos,
            "dispositivos_limite": empresa.max_dispositivos,
            "dispositivos_pct": round((dispositivos_ativos / max(empresa.max_dispositivos, 1)) * 100, 2),
        },
        "financeiro_recente": [
            {
                "tipo_evento": evento.tipo_evento,
                "status": evento.status,
                "valor": float(evento.valor or 0),
                "pacote_codigo": evento.pacote_codigo,
                "ciclo": evento.ciclo,
                "criado_em": evento.criado_em.isoformat(),
            }
            for evento in eventos
        ],
    })


def _readiness_item(codigo, ok, titulo, detalhe, severidade="alta"):
    return {
        "codigo": codigo,
        "ok": bool(ok),
        "titulo": titulo,
        "detalhe": detalhe,
        "severidade": "ok" if ok else severidade,
    }


def api_enterprise_readiness(request):
    dono = getattr(request, "dono_saas", None) or dono_autenticado_from_request(request)
    if not dono:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    secret_key = getattr(settings, "SECRET_KEY", "") or ""
    jwt_key = getattr(settings, "JWT_SECRET_KEY", "") or ""
    db_engine = connection.settings_dict.get("ENGINE", "")
    allowed_hosts = [host for host in getattr(settings, "ALLOWED_HOSTS", []) if host]
    csrf_origins = [origin for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", []) if origin]
    email_user = (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    email_backend = getattr(settings, "EMAIL_BACKEND", "")
    asaas_key = (getattr(settings, "ASAAS_API_KEY", "") or "").strip()
    webhook_token = (getattr(settings, "ASAAS_WEBHOOK_TOKEN", "") or "").strip()
    cache_backend = str(getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", "") or "")
    shared_cache_ok = ("RedisCache" in cache_backend) or not getattr(settings, "IS_PRODUCTION", False)
    demo_mutations_locked = not bool(getattr(settings, "ALLOW_ENTERPRISE_DEMO_MUTATIONS", True))

    checks = [
        _readiness_item(
            "debug_off",
            not settings.DEBUG,
            "DEBUG desligado",
            "DJANGO_DEBUG deve ficar false em producao.",
            "critica",
        ),
        _readiness_item(
            "secret_keys",
            len(secret_key) >= 50 and len(jwt_key) >= 50 and not secret_key.startswith("dev-only-"),
            "Chaves fortes configuradas",
            "DJANGO_SECRET_KEY e JWT_SECRET_KEY precisam ser longas e diferentes.",
            "critica",
        ),
        _readiness_item(
            "postgres",
            "postgresql" in db_engine,
            "Banco PostgreSQL gerenciado",
            f"Engine atual: {db_engine or 'nao identificada'}.",
            "critica",
        ),
        _readiness_item(
            "hosts",
            bool(allowed_hosts and csrf_origins),
            "Dominios e CSRF configurados",
            "ALLOWED_HOSTS e CSRF_TRUSTED_ORIGINS devem conter dominio oficial e Render.",
            "alta",
        ),
        _readiness_item(
            "secure_cookies",
            bool(settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE and settings.SECURE_SSL_REDIRECT),
            "Cookies e HTTPS protegidos",
            "SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE e SECURE_SSL_REDIRECT devem estar ativos.",
            "critica",
        ),
        _readiness_item(
            "asaas",
            bool(asaas_key and webhook_token),
            "Asaas e webhook configurados",
            "ASAAS_API_KEY e ASAAS_WEBHOOK_TOKEN precisam estar definidos.",
            "critica",
        ),
        _readiness_item(
            "shared_cache",
            shared_cache_ok,
            "Cache compartilhado para auth e rate limit",
            f"Backend atual: {cache_backend or 'nao identificado'}. Produção deve usar Redis compartilhado.",
            "critica",
        ),
        _readiness_item(
            "demo_mutations_locked",
            demo_mutations_locked or not getattr(settings, "IS_PRODUCTION", False),
            "Seeds e resets demo bloqueados em producao",
            "ALLOW_ENTERPRISE_DEMO_MUTATIONS deve ficar desligado em producao.",
            "alta",
        ),
        _readiness_item(
            "email",
            bool(email_user or "console" in email_backend),
            "Canal de e-mail configurado",
            "SMTP real deve estar configurado para reset, alertas e onboarding.",
            "media",
        ),
        _readiness_item(
            "pacotes",
            bool(pacotes_por_setor(incluir_governo=True)),
            "Catalogo de planos disponivel",
            "Planos comerciais precisam estar carregados.",
            "alta",
        ),
    ]

    total = len(checks)
    ok_total = sum(1 for item in checks if item["ok"])
    score = round((ok_total / max(total, 1)) * 100)
    bloqueios = [item for item in checks if not item["ok"] and item["severidade"] == "critica"]
    status = "pronto_enterprise" if score >= 90 and not bloqueios else "precisa_ajuste"

    return JsonResponse({
        "status": status,
        "score": score,
        "checks": checks,
        "bloqueios_criticos": bloqueios,
        "metricas": {
            "clientes_total": Empresa.objects.count(),
            "clientes_ativos": Empresa.objects.filter(ativo=True).count(),
            "eventos_financeiros_30d": FinanceiroEventoSaaS.objects.filter(
                criado_em__gte=now() - datetime.timedelta(days=30)
            ).count(),
        },
    })
