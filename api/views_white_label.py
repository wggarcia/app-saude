"""
White Label (Marca Branca) — API views.

GET  /api/gestao/marca/         → retorna configuração atual
POST /api/gestao/marca/         → salva configuração
GET  /api/gestao/marca/publica/ → endpoint público (sem auth) para o topbar JS
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from api.access_control import api_requer_gerencia
from api.models import ConfiguracaoMarca


@csrf_exempt
@api_requer_gerencia
def api_marca(request):
    """GET retorna configuração; POST salva configuração."""
    empresa = request.empresa

    if request.method == "GET":
        return _get_marca(empresa)

    if request.method == "POST":
        return _post_marca(request, empresa)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


def _get_marca(empresa):
    try:
        cfg = empresa.configuracao_marca
    except ConfiguracaoMarca.DoesNotExist:
        # Retorna defaults sem criar registro
        return JsonResponse({
            "logo_url": "",
            "cor_primaria": "#00c9a7",
            "cor_secundaria": "#1f6ff2",
            "nome_marca": "",
            "mostrar_powered_by": True,
        })

    return JsonResponse({
        "logo_url": cfg.logo_url,
        "cor_primaria": cfg.cor_primaria,
        "cor_secundaria": cfg.cor_secundaria,
        "nome_marca": cfg.nome_marca,
        "mostrar_powered_by": cfg.mostrar_powered_by,
    })


def _post_marca(request, empresa):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cfg, _ = ConfiguracaoMarca.objects.get_or_create(empresa=empresa)

    logo_url = (body.get("logo_url") or "").strip()
    cor_primaria = (body.get("cor_primaria") or "#00c9a7").strip()
    cor_secundaria = (body.get("cor_secundaria") or "#1f6ff2").strip()
    nome_marca = (body.get("nome_marca") or "").strip()
    mostrar_powered_by = bool(body.get("mostrar_powered_by", True))

    # Validações básicas de cor HEX
    for cor, campo in [(cor_primaria, "cor_primaria"), (cor_secundaria, "cor_secundaria")]:
        if cor and (len(cor) not in (4, 7) or not cor.startswith("#")):
            return JsonResponse({"erro": f"{campo} deve ser um código HEX (#rrggbb ou #rgb)"}, status=400)

    cfg.logo_url = logo_url
    cfg.cor_primaria = cor_primaria
    cfg.cor_secundaria = cor_secundaria
    cfg.nome_marca = nome_marca
    cfg.mostrar_powered_by = mostrar_powered_by
    cfg.save()

    return JsonResponse({"status": "ok", "mensagem": "Configuração de marca salva com sucesso."})


@require_http_methods(["GET"])
def api_marca_publica(request):
    """
    Endpoint público — retorna branding da empresa a partir do empresa_id passado
    como query param. Usado pelo topbar JS sem autenticação completa.
    """
    empresa_id = request.GET.get("empresa_id") or request.headers.get("X-Empresa-Id")
    if not empresa_id:
        return JsonResponse({"erro": "empresa_id obrigatório"}, status=400)

    try:
        cfg = ConfiguracaoMarca.objects.select_related("empresa").get(
            empresa_id=int(empresa_id)
        )
    except (ConfiguracaoMarca.DoesNotExist, ValueError, TypeError):
        # Sem customização — retorna defaults
        return JsonResponse({
            "logo_url": "",
            "cor_primaria": "#00c9a7",
            "cor_secundaria": "#1f6ff2",
            "nome_marca": "",
            "mostrar_powered_by": True,
        })

    return JsonResponse({
        "logo_url": cfg.logo_url,
        "cor_primaria": cfg.cor_primaria,
        "cor_secundaria": cfg.cor_secundaria,
        "nome_marca": cfg.nome_marca,
        "mostrar_powered_by": cfg.mostrar_powered_by,
    })
