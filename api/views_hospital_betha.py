"""
Integração com Betha Sistemas (compras públicas).
"""
import json
import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo

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
    return render(request, "hospital_betha.html")


# ─── Status ──────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_betha_status(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    credencial_ok = False
    ultima_sync = None

    if CredenciaisIntegracoes:
        cred = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="betha").first()
        credencial_ok = bool(cred)

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

    token = None
    if CredenciaisIntegracoes:
        cred = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="betha").first()
        if cred:
            token = getattr(cred, "token", None)

    if not token:
        return JsonResponse({
            "status": "pendente",
            "integracao_id": integracao.id,
            "mensagem": "Configure credenciais Betha em /configuracoes/integracoes",
        })

    # Envio real à API Betha (placeholder)
    try:
        import urllib.request
        url = f"{_BETHA_API_BASE}/sincronizar/{tipo}"
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
def api_betha_sincronizar_almoxarifado(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    return _sincronizar(emp, "almoxarifado")


# ─── Sincronizar Compras ──────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
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
