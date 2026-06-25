from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from api.models import NoticiaEpidemiologica


@login_required
@require_GET
def api_noticias_epidemiologicas(request):
    """Retorna as últimas notícias epidemiológicas da empresa do usuário logado."""
    empresa = getattr(request.user, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Empresa não associada ao usuário."}, status=403)

    nivel    = request.GET.get("nivel")       # informativo | alerta | critico
    status   = request.GET.get("status")      # novo | lido | arquivado
    doenca   = request.GET.get("doenca")      # nome da doença, ex: dengue
    limite   = min(int(request.GET.get("limite", 50)), 200)

    qs = NoticiaEpidemiologica.objects.filter(empresa=empresa)
    if nivel:
        qs = qs.filter(nivel_alerta=nivel)
    if status:
        qs = qs.filter(status=status)
    if doenca:
        qs = qs.filter(doencas_detectadas__contains=doenca)

    noticias = list(
        qs.values(
            "id", "titulo", "fonte", "url", "resumo",
            "doencas_detectadas", "nivel_alerta", "status",
            "publicado_em", "criado_em",
        )[:limite]
    )

    resumo = {
        "total":       qs.count(),
        "novos":       qs.filter(status="novo").count(),
        "alertas":     qs.filter(nivel_alerta="alerta").count(),
        "criticos":    qs.filter(nivel_alerta="critico").count(),
    }

    return JsonResponse({"resumo": resumo, "noticias": noticias})


@csrf_exempt
@login_required
@require_POST
def api_noticia_status(request, noticia_id):
    """Atualiza o status de uma notícia (novo → lido → arquivado)."""
    import json
    empresa = getattr(request.user, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Empresa não associada."}, status=403)

    try:
        noticia = NoticiaEpidemiologica.objects.get(pk=noticia_id, empresa=empresa)
    except NoticiaEpidemiologica.DoesNotExist:
        return JsonResponse({"erro": "Notícia não encontrada."}, status=404)

    body  = json.loads(request.body or "{}")
    novo_status = body.get("status")
    if novo_status not in ("novo", "lido", "arquivado"):
        return JsonResponse({"erro": "Status inválido."}, status=400)

    noticia.status = novo_status
    noticia.save(update_fields=["status"])
    return JsonResponse({"ok": True, "status": noticia.status})
