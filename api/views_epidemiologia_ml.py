"""
Endpoint REST para projeções ML de surto epidemiológico.

GET /api/epidemiologia/projecao-ml/
  ?doenca=Dengue&uf=SP&horizonte=14

Chama projecao_surto() de epidemiologia_ml.py, que usa o VotingClassifier
RF+GB treinado nos dados oficiais SINAN/DATASUS para projetar risco de surto
nos próximos 7, 14 ou 30 dias por UF.

Público (mesma política de panorama_epidemiologico — dados de vigilância
são de saúde coletiva, não de um tenant específico).
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .epidemiologia_ml import DOENCAS_REGISTRADAS, projecao_surto


@require_http_methods(["GET"])
def api_epidemiologia_projecao_ml(request):
    """
    Projeção de surto via RF+GB para 7, 14 ou 30 dias à frente.

    Parâmetros (query string):
      doenca   — nome da doença (obrigatório). Exemplos: Dengue, Gripe, Zika
      uf       — sigla do estado (opcional). Omitir retorna todos os estados.
      horizonte — 7, 14 ou 30 (padrão 30).

    Resposta:
      { "ok": true, "doenca": "Dengue", "uf": "SP", "horizonte_dias": 14,
        "resultados": [ { "uf": "SP", "projecoes": [...] } ] }
    """
    doenca = (request.GET.get("doenca") or "").strip()
    uf = (request.GET.get("uf") or "").strip().upper() or None
    horizonte_raw = request.GET.get("horizonte", "30")

    if not doenca:
        nomes = [nome for _, _, nome in DOENCAS_REGISTRADAS]
        return JsonResponse(
            {"erro": "Parâmetro 'doenca' obrigatório.", "doencas_disponiveis": nomes},
            status=400,
        )

    try:
        horizonte = int(horizonte_raw)
        if horizonte not in (7, 14, 30):
            return JsonResponse(
                {"erro": "Parâmetro 'horizonte' deve ser 7, 14 ou 30."}, status=400
            )
    except ValueError:
        return JsonResponse({"erro": "Parâmetro 'horizonte' deve ser inteiro."}, status=400)

    resultado = projecao_surto(doenca=doenca, uf=uf, horizonte=horizonte)

    if isinstance(resultado, dict) and "erro" in resultado:
        return JsonResponse(resultado, status=404)

    if not resultado:
        return JsonResponse(
            {
                "ok": False,
                "aviso": "Nenhum dado disponível para a combinação doença/UF solicitada. "
                         "O modelo pode ainda não ter sido treinado para esse estado.",
                "doenca": doenca,
                "uf": uf,
                "horizonte_dias": horizonte,
                "resultados": [],
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "doenca": doenca,
            "uf": uf,
            "horizonte_dias": horizonte,
            "n_estados": len(resultado),
            "resultados": resultado,
        }
    )
