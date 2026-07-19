"""
Views para Séries Epidemiológicas com dados temporais — análise de tendências.
Usadas tanto pela Farmácia epidemiológica quanto pelo Governo.
"""
import json
from datetime import date, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import SerieEpidemiologica, PontoSerie
from .views_dashboard import _empresa_autenticada
from .access_control import api_requer_feature


def _serie_to_dict(s, incluir_pontos=False):
    d = {
        "id": s.id,
        "nome": s.nome,
        "descricao": s.descricao,
        "unidade": s.unidade,
        "granularidade": s.granularidade,
        "granularidade_label": s.get_granularidade_display(),
        "ativo": s.ativo,
        "total_pontos": s.pontos.count(),
        "criado_em": s.criado_em.strftime("%d/%m/%Y"),
    }
    if incluir_pontos:
        pontos = s.pontos.order_by("data_referencia")
        vals = [float(p.valor) for p in pontos]
        # Cálculo de tendência simples (regressão linear nos últimos 6 pontos)
        tendencia = None
        if len(vals) >= 2:
            recentes = vals[-6:]
            n = len(recentes)
            sx = sum(range(n))
            sy = sum(recentes)
            sxy = sum(i * v for i, v in enumerate(recentes))
            sx2 = sum(i * i for i in range(n))
            try:
                slope = (n * sxy - sx * sy) / (n * sx2 - sx * sx)
                tendencia = "alta" if slope > 0.01 else "queda" if slope < -0.01 else "estavel"
            except ZeroDivisionError:
                tendencia = "estavel"

        d["pontos"] = [
            {
                "data": str(p.data_referencia),
                "valor": float(p.valor),
                "fonte": p.fonte,
                "obs": p.observacoes,
            }
            for p in pontos
        ]
        d["tendencia"] = tendencia
        d["ultimo_valor"] = float(pontos.last().valor) if pontos.exists() else None
        d["variacao_pct"] = None
        if len(vals) >= 2:
            ant = vals[-2]
            ult = vals[-1]
            d["variacao_pct"] = round((ult - ant) / max(abs(ant), 0.001) * 100, 1)
    return d


@csrf_exempt
@api_requer_feature("sst.saude_ocupacional")
def api_series_epidemiologicas(request):
    """GET list / POST create séries."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = SerieEpidemiologica.objects.filter(empresa=empresa)
        ativo_f = request.GET.get("ativo")
        if ativo_f is not None:
            qs = qs.filter(ativo=ativo_f.lower() == "true")
        incluir = request.GET.get("pontos") == "1"
        return JsonResponse({"series": [_serie_to_dict(s, incluir_pontos=incluir) for s in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        if not data.get("nome"):
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        s = SerieEpidemiologica.objects.create(
            empresa=empresa,
            nome=data["nome"],
            descricao=data.get("descricao", ""),
            unidade=data.get("unidade", "casos"),
            granularidade=data.get("granularidade", "mensal"),
            ativo=True,
        )
        return JsonResponse({"serie": _serie_to_dict(s)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
@api_requer_feature("sst.saude_ocupacional")
def api_serie_epidemiologica_detalhe(request, serie_id):
    """GET (com pontos) / PUT / DELETE série."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        s = SerieEpidemiologica.objects.get(id=serie_id, empresa=empresa)
    except SerieEpidemiologica.DoesNotExist:
        return JsonResponse({"erro": "Série não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"serie": _serie_to_dict(s, incluir_pontos=True)})

    elif request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        for f in ("nome", "descricao", "unidade", "granularidade"):
            if f in data:
                setattr(s, f, data[f])
        if "ativo" in data:
            s.ativo = bool(data["ativo"])
        s.save()
        return JsonResponse({"serie": _serie_to_dict(s)})

    elif request.method == "DELETE":
        s.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
@api_requer_feature("sst.saude_ocupacional")
def api_pontos_serie(request, serie_id):
    """GET pontos da série / POST adicionar ponto / DELETE todos."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        s = SerieEpidemiologica.objects.get(id=serie_id, empresa=empresa)
    except SerieEpidemiologica.DoesNotExist:
        return JsonResponse({"erro": "Série não encontrada"}, status=404)

    if request.method == "GET":
        ini = request.GET.get("data_ini")
        fim = request.GET.get("data_fim")
        qs = s.pontos.order_by("data_referencia")
        if ini: qs = qs.filter(data_referencia__gte=ini)
        if fim: qs = qs.filter(data_referencia__lte=fim)
        return JsonResponse({"pontos": [
            {"id": p.id, "data": str(p.data_referencia), "valor": float(p.valor),
             "fonte": p.fonte, "obs": p.observacoes}
            for p in qs
        ]})

    elif request.method == "POST":
        data = json.loads(request.body)
        # Suporte a inserção em lote: {"pontos": [{data, valor, fonte}, ...]}
        if "pontos" in data:
            criados = []
            for pt in data["pontos"]:
                p, _ = PontoSerie.objects.update_or_create(
                    serie=s,
                    data_referencia=pt["data"],
                    defaults={
                        "valor": pt["valor"],
                        "fonte": pt.get("fonte", ""),
                        "observacoes": pt.get("obs", ""),
                    }
                )
                criados.append(p)
            return JsonResponse({"criados": len(criados)}, status=201)

        # Inserção simples
        data_ref = data.get("data")
        valor = data.get("valor")
        if not data_ref or valor is None:
            return JsonResponse({"erro": "data e valor obrigatórios"}, status=400)

        p, _ = PontoSerie.objects.update_or_create(
            serie=s,
            data_referencia=data_ref,
            defaults={
                "valor": float(valor),
                "fonte": data.get("fonte", ""),
                "observacoes": data.get("obs", ""),
            }
        )
        return JsonResponse({
            "ponto": {"id": p.id, "data": str(p.data_referencia), "valor": float(p.valor)}
        }, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
@api_requer_feature("sst.saude_ocupacional")
def api_ponto_serie_detalhe(request, ponto_id):
    """PUT / DELETE ponto individual."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        p = PontoSerie.objects.get(id=ponto_id, serie__empresa=empresa)
    except PontoSerie.DoesNotExist:
        return JsonResponse({"erro": "Ponto não encontrado"}, status=404)

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        if "valor" in data: p.valor = float(data["valor"])
        if "fonte" in data: p.fonte = data["fonte"]
        if "obs" in data: p.observacoes = data["obs"]
        p.save()
        return JsonResponse({"ponto": {"id": p.id, "data": str(p.data_referencia), "valor": float(p.valor)}})

    elif request.method == "DELETE":
        p.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


def api_series_dashboard(request):
    """
    Dashboard de séries epidemiológicas com análise de tendências.
    Retorna todas as séries ativas com último valor, variação e tendência.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    series = SerieEpidemiologica.objects.filter(empresa=empresa, ativo=True)
    resultado = [_serie_to_dict(s, incluir_pontos=True) for s in series]

    # Resumo
    em_alta  = sum(1 for s in resultado if s.get("tendencia") == "alta")
    em_queda = sum(1 for s in resultado if s.get("tendencia") == "queda")
    estaveis = sum(1 for s in resultado if s.get("tendencia") == "estavel")

    return JsonResponse({
        "resumo": {
            "total_series": len(resultado),
            "em_alta": em_alta,
            "em_queda": em_queda,
            "estaveis": estaveis,
        },
        "series": resultado,
    })


def series_epi_page(request):
    from django.shortcuts import render
    return render(request, "series_epidemiologicas.html")
