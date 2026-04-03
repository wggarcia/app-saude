from django.http import JsonResponse
from django.shortcuts import render
from .models import RegistroSintoma
from .inteligencia import nivel_risco

# API (JSON)
def dados_dashboard(request):
    total = RegistroSintoma.objects.count()

    return JsonResponse({
        "total_casos": total,
        "risco": nivel_risco()
    })

# HTML (dashboard)
def dashboard(request):
    total = RegistroSintoma.objects.count()

    return render(request, 'dashboard.html', {
        'total': total,
        'risco': nivel_risco()
    })

from django.db.models import Count

def global_paises(request):

    dados = RegistroSintoma.objects.values("pais")\
        .annotate(total=Count("id"))\
        .order_by("-total")

    resultado = []

    for d in dados:
        if not d["pais"]:
            continue

        resultado.append({
            "pais": d["pais"],
            "total": d["total"]
        })

    return JsonResponse(resultado, safe=False)