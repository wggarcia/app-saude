"""
Endpoint REST da projeção de DISPERSÃO epidemiológica (9º sistema de IA).

GET /api/epidemiologia/dispersao?doenca=Dengue&horizonte=14

Lê as projeções gravadas em ProjecaoDispersao (pelo command
projetar_dispersao_surtos, que roda o SEIR de api/modelo_dispersao.py) e
devolve um payload pronto para o mapa: para cada município em risco, as
coordenadas do destino e da origem provável, para desenhar o arco "para onde
o surto vai".

Público, pela mesma razão de api_epidemiologia_projecao_ml (IA #5): projeção
de vigilância é saúde coletiva sobre território público, não dado de tenant —
ProjecaoDispersao não tem FK para Empresa (ver models.py).
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import ProjecaoDispersao
from .pipeline_mobilidade import geo_municipio

_HORIZONTES = (7, 14, 30)


@require_http_methods(["GET"])
def api_epidemiologia_dispersao(request):
    """Projeção de para onde a doença vai, pronta para o mapa.

    Query string:
      doenca    — nome da doença (opcional; sem ela, lista as disponíveis).
      horizonte — 7, 14 ou 30 (padrão 14).
      uf        — filtra por UF de destino (opcional).
      min_prob  — probabilidade mínima (padrão 0.05).

    Resposta:
      { "ok": true, "doenca": ..., "horizonte_dias": 14,
        "resumo": {"municipios_em_risco": N, "prob_max": 0.87},
        "focos": [ {ibge, nome, uf, lat, lon} ],           # sementes (surto atual)
        "destinos": [ {ibge, nome, uf, lat, lon, probabilidade, casos_projetados,
                       origem:{ibge,nome,lat,lon}} ] }
    """
    doenca = (request.GET.get("doenca") or "").strip()
    uf = (request.GET.get("uf") or "").strip().upper() or None
    horizonte_raw = request.GET.get("horizonte", "14")
    try:
        min_prob = float(request.GET.get("min_prob", "0.05"))
    except ValueError:
        min_prob = 0.05

    if not doenca:
        # .order_by() limpa o ordering default do Meta (-probabilidade); sem isso o
        # Django injeta a coluna no SELECT DISTINCT e o distinct por doença falha.
        disponiveis = sorted(
            ProjecaoDispersao.objects.order_by().values_list("doenca", flat=True).distinct()
        )
        return JsonResponse(
            {"erro": "Parâmetro 'doenca' obrigatório.", "doencas_disponiveis": disponiveis},
            status=400,
        )

    try:
        horizonte = int(horizonte_raw)
        if horizonte not in _HORIZONTES:
            return JsonResponse({"erro": "Parâmetro 'horizonte' deve ser 7, 14 ou 30."}, status=400)
    except ValueError:
        return JsonResponse({"erro": "Parâmetro 'horizonte' deve ser inteiro."}, status=400)

    qs = ProjecaoDispersao.objects.filter(
        doenca__iexact=doenca, horizonte_dias=horizonte, probabilidade__gte=min_prob,
    )
    if uf:
        qs = qs.filter(uf=uf)
    qs = qs.order_by("-probabilidade")

    destinos = []
    focos_ibge = set()
    prob_max = 0.0
    for p in qs:
        gd = geo_municipio(p.municipio_ibge)
        if not gd:
            continue
        origem = None
        if p.origem_provavel_ibge:
            go = geo_municipio(p.origem_provavel_ibge)
            if go:
                origem = {"ibge": go["ibge"], "nome": go["nome"],
                          "lat": go["latitude"], "lon": go["longitude"]}
                focos_ibge.add(p.origem_provavel_ibge)
        prob_max = max(prob_max, p.probabilidade)
        destinos.append({
            "ibge": gd["ibge"], "nome": gd["nome"], "uf": gd["uf"],
            "lat": gd["latitude"], "lon": gd["longitude"],
            "probabilidade": round(p.probabilidade, 4),
            "casos_projetados": p.casos_projetados,
            "origem": origem,
        })

    # focos = origens prováveis (aproxima os municípios-semente do surto atual)
    focos = []
    for ibge in focos_ibge:
        g = geo_municipio(ibge)
        if g:
            focos.append({"ibge": g["ibge"], "nome": g["nome"], "uf": g["uf"],
                          "lat": g["latitude"], "lon": g["longitude"]})

    return JsonResponse({
        "ok": True,
        "doenca": doenca,
        "horizonte_dias": horizonte,
        "resumo": {
            "municipios_em_risco": len(destinos),
            "prob_max": round(prob_max, 4),
        },
        "focos": focos,
        "destinos": destinos,
    })
