from django.http import JsonResponse
from django.shortcuts import render, redirect
from .models import RegistroSintoma
from .inteligencia import nivel_risco
from .models import Empresa



# API (JSON)
def dados_dashboard(request):
    total = RegistroSintoma.objects.count()

    return JsonResponse({
        "total_casos": total,
        "risco": nivel_risco()
    })

# HTML (dashboard)
def dashboard(request):
    empresa_id = request.GET.get("empresa_id") or request.COOKIES.get("empresa_id")

    if not empresa_id:
        return redirect("/")

    empresa = Empresa.objects.filter(id=empresa_id).first()

    if not empresa:
        return redirect("/")

    # 🔥 BLOQUEIO CORRETO
    if not empresa.ativo:
        return redirect("/pagamento/")

    response = render(request, "dashboard.html", {
        "empresa_id": str(empresa.id)
    })
    response.set_cookie("empresa_id", str(empresa.id), samesite="Lax")
    return response

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


def dashboard_farmacia(request):
    return render(request, "dashboard_farmacia.html")
