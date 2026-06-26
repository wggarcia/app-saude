import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from api.models import NoticiaEpidemiologica

_NIVEIS_VALIDOS = {"informativo", "alerta", "critico"}
_STATUS_VALIDOS = {"novo", "lido", "arquivado"}


@require_GET
def api_noticias_epidemiologicas(request):
    """Retorna as últimas notícias epidemiológicas da empresa autenticada."""
    empresa = getattr(request, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    nivel  = request.GET.get("nivel", "").strip().lower()
    status = request.GET.get("status", "").strip().lower()
    doenca = request.GET.get("doenca", "").strip()
    try:
        limite = min(max(int(request.GET.get("limite", 50)), 1), 200)
    except (ValueError, TypeError):
        limite = 50

    qs = NoticiaEpidemiologica.objects.filter(empresa=empresa)
    if nivel:
        if nivel not in _NIVEIS_VALIDOS:
            return JsonResponse({"erro": f"nivel deve ser um de: {', '.join(sorted(_NIVEIS_VALIDOS))}"}, status=400)
        qs = qs.filter(nivel_alerta=nivel)
    if status:
        if status not in _STATUS_VALIDOS:
            return JsonResponse({"erro": f"status deve ser um de: {', '.join(sorted(_STATUS_VALIDOS))}"}, status=400)
        qs = qs.filter(status=status)
    if doenca:
        qs = qs.filter(doencas_detectadas__icontains=doenca[:100])

    noticias = list(
        qs.values(
            "id", "titulo", "fonte", "url", "resumo",
            "doencas_detectadas", "nivel_alerta", "status",
            "publicado_em", "criado_em",
        )[:limite]
    )

    resumo = {
        "total":    qs.count(),
        "novos":    qs.filter(status="novo").count(),
        "alertas":  qs.filter(nivel_alerta="alerta").count(),
        "criticos": qs.filter(nivel_alerta="critico").count(),
    }

    return JsonResponse({"resumo": resumo, "noticias": noticias})


@csrf_exempt
@require_POST
def api_noticia_status(request, noticia_id):
    """Atualiza o status de uma notícia (novo → lido → arquivado)."""
    empresa = getattr(request, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        noticia = NoticiaEpidemiologica.objects.get(pk=noticia_id, empresa=empresa)
    except NoticiaEpidemiologica.DoesNotExist:
        return JsonResponse({"erro": "Notícia não encontrada."}, status=404)

    body = json.loads(request.body or b"{}")
    novo_status = body.get("status")
    if novo_status not in _STATUS_VALIDOS:
        return JsonResponse({"erro": "Status inválido."}, status=400)

    noticia.status = novo_status
    noticia.save(update_fields=["status"])
    return JsonResponse({"ok": True, "status": noticia.status})
