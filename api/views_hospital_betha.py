"""
Integração com Betha Sistemas (compras públicas).
"""
import hashlib
import hmac
import json
import logging
import os
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo, api_requer_feature, api_requer_permissao_modulo
from .services.modulo_operavel import render_modulo_operavel

try:
    from .models import IntegracaoBetha, CredenciaisIntegracoes
except ImportError:
    IntegracaoBetha = CredenciaisIntegracoes = None

logger = logging.getLogger(__name__)

_BETHA_API_BASE = "https://cloud.betha.com.br/almoxarifado/api/v1"


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.administrativo", "Betha")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_betha_page(request):
    return render_modulo_operavel(request, {
        "modulo_nome": "Betha — Integração ERP", "modulo_icon": "🔗",
        "modulo_sub": "Sincronização de almoxarifado e compras públicas",
        "kpis": {"url": "/api/hospital/betha/kpis", "campos": [
            {"key": "pendentes", "label": "Pendentes", "cor": "warn"},
            {"key": "sincronizados_hoje", "label": "Sincronizados hoje", "cor": "ok"},
            {"key": "erros", "label": "Com erro", "cor": "danger"},
        ]},
        "credenciais": {"url": "/api/integracoes/credenciais/betha/", "chave_status": "betha",
                        "titulo": "Credenciais Betha",
                        "ajuda": "URL e token fornecidos pelo suporte Betha do seu município. O token é criptografado e nunca é exibido."},
        "status": {"url": "/api/hospital/betha/status", "titulo": "Status da integração", "campos": [
            {"key": "credencial_configurada", "label": "Credencial", "tipo": "bool"},
            {"key": "ultima_sync", "label": "Última sincronização", "tipo": "data"},
            {"key": "endpoint_base", "label": "Endpoint"},
        ]},
        "lista": {
            "url": "/api/hospital/betha/fila", "envelope": "integracoes", "id_field": "id",
            "titulo": "Fila de sincronização (pendentes/erro)",
            "colunas": [
                {"key": "tipo", "label": "Tipo"},
                {"key": "status", "label": "Status", "tipo": "chip",
                 "labels": {"pendente": "Pendente", "sincronizado": "Sincronizado", "erro": "Erro"},
                 "chip_cores": {"pendente": "warn", "sincronizado": "ok", "erro": "danger"}},
                {"key": "criado_em", "label": "Criado em", "tipo": "data"},
            ],
        },
        "acoes_modulo": [
            {"key": "sync_almox", "label": "🔄 Sincronizar Almoxarifado", "url": "/api/hospital/betha/sincronizar-almoxarifado", "metodo": "POST",
             "confirm": "Disparar sincronização de almoxarifado com o Betha?"},
            {"key": "sync_compras", "label": "🔄 Sincronizar Compras", "url": "/api/hospital/betha/sincronizar-compras", "metodo": "POST",
             "confirm": "Disparar sincronização de compras com o Betha?"},
        ],
    })
# ─── Status ──────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.administrativo")
@api_requer_permissao_modulo("hospital.administrativo")
def api_betha_status(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    credencial_ok = False
    ultima_sync = None

    cred = CredenciaisIntegracoes.objects.filter(empresa=emp).first() if CredenciaisIntegracoes else None
    credencial_ok = bool(cred and cred.betha_ativo and cred.get_betha_token())

    if IntegracaoBetha:
        ultimo = IntegracaoBetha.objects.filter(
            empresa=emp, status="sincronizado"
        ).order_by("-criado_em").first()
        if ultimo:
            ultima_sync = ultimo.criado_em.isoformat()

    return JsonResponse({
        "credencial_configurada": credencial_ok,
        "ultima_sync": ultima_sync,
        "endpoint_base": _BETHA_API_BASE,
    })


# ─── Helper de sincronização ─────────────────────────────────────────────────

def _sincronizar(emp, tipo):
    if IntegracaoBetha is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    comp = timezone.now().strftime("%Y-%m")
    integracao = IntegracaoBetha.objects.create(
        empresa=emp,
        tipo=tipo,
        payload={"competencia": comp},
        status="pendente",
    )

    cred = CredenciaisIntegracoes.objects.filter(empresa=emp).first() if CredenciaisIntegracoes else None
    token = cred.get_betha_token() if (cred and cred.betha_ativo) else None

    if not token:
        return JsonResponse({
            "status": "pendente",
            "integracao_id": integracao.id,
            "mensagem": "Cadastre URL e token nas Credenciais Betha, no topo desta tela.",
        })

    # Envio real à API Betha (placeholder)
    try:
        import urllib.request
        url = f"{(cred.betha_url or _BETHA_API_BASE).rstrip('/')}/sincronizar/{tipo}"
        payload_json = json.dumps({"competencia": comp, "empresa_id": emp.id}).encode()
        req = urllib.request.Request(
            url,
            data=payload_json,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resposta = json.loads(resp.read())
        integracao.status = "sincronizado"
        integracao.resposta = resposta
        integracao.save()
        return JsonResponse({"status": "sincronizado", "integracao_id": integracao.id})
    except Exception as exc:
        integracao.status = "erro"
        integracao.resposta = {"erro": str(exc)}
        integracao.save()
        logger.warning("Erro Betha sync %s: %s", tipo, exc)
        return JsonResponse({"status": "erro", "mensagem": str(exc), "integracao_id": integracao.id}, status=502)


# ─── Sincronizar Almoxarifado ─────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.administrativo")
@api_requer_permissao_modulo("hospital.administrativo")
def api_betha_sincronizar_almoxarifado(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    return _sincronizar(emp, "almoxarifado")


# ─── Sincronizar Compras ──────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.administrativo")
@api_requer_permissao_modulo("hospital.administrativo")
def api_betha_sincronizar_compras(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    return _sincronizar(emp, "compras")


# ─── Webhook Betha ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_betha_webhook(request):
    """Recebe callback do Betha Cloud e atualiza o registro de integração."""
    webhook_secret = os.environ.get("BETHA_WEBHOOK_SECRET")
    if webhook_secret:
        assinatura_recebida = (
            request.headers.get("X-Betha-Signature")
            or request.headers.get("X-Betha-Signature-256")
            or ""
        ).strip()
        assinatura_esperada = hmac.new(
            webhook_secret.encode("utf-8"), request.body or b"", hashlib.sha256
        ).hexdigest()
        if not assinatura_recebida or not hmac.compare_digest(assinatura_esperada, assinatura_recebida):
            logger.warning(
                "Webhook Betha rejeitado: assinatura HMAC ausente ou inválida (header X-Betha-Signature)."
            )
            return JsonResponse({"erro": "Assinatura inválida"}, status=401)
    else:
        logger.warning("Webhook Betha recusado: BETHA_WEBHOOK_SECRET não configurado.")
        return JsonResponse(
            {"erro": "Webhook não configurado — defina BETHA_WEBHOOK_SECRET."},
            status=503,
        )

    try:
        body = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    referencia = body.get("referencia") or body.get("id")
    status_betha = body.get("status", "")

    if IntegracaoBetha and referencia:
        integracao = IntegracaoBetha.objects.filter(
            referencia_betha=str(referencia)
        ).first()
        if integracao:
            integracao.resposta = body
            if status_betha in ("sucesso", "ok", "concluido"):
                integracao.status = "sincronizado"
            elif status_betha in ("erro", "falha"):
                integracao.status = "erro"
            integracao.save()

    return JsonResponse({"recebido": True})


# ─── Fila de Integrações ─────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.administrativo")
@api_requer_permissao_modulo("hospital.administrativo")
def api_betha_fila(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if IntegracaoBetha is None:
        return JsonResponse({"integracoes": [], "total": 0})

    qs = IntegracaoBetha.objects.filter(
        empresa=emp, status__in=["pendente", "erro"]
    ).order_by("-criado_em")[:100]

    data = [
        {
            "id": i.id,
            "tipo": i.tipo,
            "status": i.status,
            "payload": i.payload,
            "resposta": i.resposta,
            "criado_em": i.criado_em.isoformat(),
        }
        for i in qs
    ]
    return JsonResponse({"integracoes": data, "total": len(data)})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.administrativo")
@api_requer_permissao_modulo("hospital.administrativo")
def api_betha_kpis(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    pendentes = 0
    sincronizados_hoje = 0
    erros = 0

    if IntegracaoBetha:
        pendentes = IntegracaoBetha.objects.filter(empresa=emp, status="pendente").count()
        erros = IntegracaoBetha.objects.filter(empresa=emp, status="erro").count()
        hoje = timezone.now().date()
        sincronizados_hoje = IntegracaoBetha.objects.filter(
            empresa=emp,
            status="sincronizado",
            criado_em__date=hoje,
        ).count()

    return JsonResponse({
        "pendentes": pendentes,
        "sincronizados_hoje": sincronizados_hoje,
        "erros": erros,
    })
