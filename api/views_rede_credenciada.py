"""
Rede Credenciada SolusCRT — Clínicas Parceiras
Mapa nacional de clínicas, SESI, SESC, AMEs, laboratórios parceiros.
Meta: superar a rede do SOC (3.000+ clínicas).

Endpoints:
  GET  /api/sst/rede-credenciada/                  — busca/lista clínicas
  POST /api/sst/rede-credenciada/credenciar/        — solicitar credenciamento
  GET  /api/sst/rede-credenciada/<id>/              — detalhe da clínica
  GET  /api/sst/rede-credenciada/kpis/              — painel de cobertura nacional
  GET  /api/sst/rede-credenciada/proximas/          — clínicas próximas (lat/lng)
  GET  /api/sst/rede-credenciada/por-estado/        — distribuição por UF
"""
from datetime import date, timedelta
from django.http import JsonResponse
import json


def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


ESPECIALIDADES = [
    "medicina_trabalho", "exames_laboratoriais", "audiometria",
    "espirometria", "acuidade_visual", "raio_x", "eletrocardiograma",
    "toxicologico", "psicossocial", "ergonomia",
]

UFS_BRASIL = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS",
    "MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC",
    "SP","SE","TO"
]


def _clinica_dict(c):
    return {
        "id": c.id,
        "nome": c.nome,
        "cnpj": c.cnpj,
        "tipo": c.tipo,
        "especialidades": c.especialidades,
        "endereco": c.endereco,
        "cidade": c.cidade,
        "uf": c.uf,
        "cep": c.cep,
        "telefone": c.telefone,
        "email": c.email,
        "responsavel_tecnico": c.responsavel_tecnico,
        "crm": c.crm,
        "horario_atendimento": c.horario_atendimento,
        "aceita_agendamento_online": c.aceita_agendamento_online,
        "tempo_medio_laudo_dias": c.tempo_medio_laudo_dias,
        "avaliacao_media": c.avaliacao_media,
        "total_avaliacoes": c.total_avaliacoes,
        "status_credenciamento": c.status_credenciamento,
        "ativa": c.ativa,
        "lat": c.lat,
        "lng": c.lng,
    }


def api_rede_credenciada_busca(request):
    """Busca clínicas credenciadas com filtros."""
    try:
        from .models import ClinicaCredenciada

        qs = ClinicaCredenciada.objects.filter(ativa=True, status_credenciamento="ativo")

        uf = request.GET.get("uf")
        if uf:
            qs = qs.filter(uf=uf.upper())

        cidade = request.GET.get("cidade")
        if cidade:
            qs = qs.filter(cidade__icontains=cidade)

        especialidade = request.GET.get("especialidade")
        if especialidade:
            qs = qs.filter(especialidades__contains=especialidade)

        tipo = request.GET.get("tipo")
        if tipo:
            qs = qs.filter(tipo=tipo)

        busca = request.GET.get("q")
        if busca:
            qs = qs.filter(nome__icontains=busca)

        total = qs.count()
        clinicas = [_clinica_dict(c) for c in qs.order_by("-avaliacao_media", "nome")[:100]]

        return JsonResponse({
            "total": total,
            "clinicas": clinicas,
            "filtros_ativos": {
                "uf": uf, "cidade": cidade,
                "especialidade": especialidade, "tipo": tipo, "q": busca,
            },
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_rede_credenciada_proximas(request):
    """Retorna clínicas mais próximas dado lat/lng (cálculo Haversine simples)."""
    try:
        from .models import ClinicaCredenciada
        import math

        lat = float(request.GET.get("lat", 0))
        lng = float(request.GET.get("lng", 0))
        raio_km = float(request.GET.get("raio_km", 50))

        if not lat or not lng:
            return JsonResponse({"erro": "lat e lng obrigatórios"}, status=400)

        def haversine(lat1, lon1, lat2, lon2):
            R = 6371
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return R * 2 * math.asin(math.sqrt(a))

        clinicas = ClinicaCredenciada.objects.filter(
            ativa=True, status_credenciamento="ativo",
            lat__isnull=False, lng__isnull=False
        )
        resultado = []
        for c in clinicas:
            dist = haversine(lat, lng, float(c.lat), float(c.lng))
            if dist <= raio_km:
                d = _clinica_dict(c)
                d["distancia_km"] = round(dist, 2)
                resultado.append(d)

        resultado.sort(key=lambda x: x["distancia_km"])
        return JsonResponse({"total": len(resultado), "clinicas": resultado[:20]})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_rede_credenciada_detalhe(request, clinica_id):
    try:
        from .models import ClinicaCredenciada
        c = ClinicaCredenciada.objects.get(id=clinica_id, ativa=True)
        return JsonResponse(_clinica_dict(c))
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_rede_credenciar(request):
    """Clínica solicita credenciamento na rede SolusCRT."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    data = _json(request)
    campos_obrig = ["nome", "cnpj", "cidade", "uf", "email", "responsavel_tecnico"]
    for c in campos_obrig:
        if not data.get(c):
            return JsonResponse({"erro": f"Campo obrigatório: {c}"}, status=400)
    try:
        from .models import ClinicaCredenciada
        clinica, criado = ClinicaCredenciada.objects.get_or_create(
            cnpj=data["cnpj"],
            defaults={
                "nome": data["nome"],
                "tipo": data.get("tipo", "clinica_ocupacional"),
                "especialidades": data.get("especialidades", ["medicina_trabalho"]),
                "cidade": data["cidade"],
                "uf": data["uf"].upper(),
                "cep": data.get("cep", ""),
                "endereco": data.get("endereco", ""),
                "telefone": data.get("telefone", ""),
                "email": data["email"],
                "responsavel_tecnico": data["responsavel_tecnico"],
                "crm": data.get("crm", ""),
                "horario_atendimento": data.get("horario_atendimento", "Seg–Sex 08h–18h"),
                "aceita_agendamento_online": data.get("aceita_agendamento_online", True),
                "tempo_medio_laudo_dias": data.get("tempo_medio_laudo_dias", 3),
                "lat": data.get("lat"),
                "lng": data.get("lng"),
                "status_credenciamento": "pendente",
                "ativa": False,
            }
        )
        if not criado:
            return JsonResponse({"aviso": "CNPJ já cadastrado", "id": clinica.id})
        return JsonResponse({"sucesso": True, "id": clinica.id,
                             "mensagem": "Solicitação recebida. Análise em até 5 dias úteis."}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_rede_kpis_credenciada(request):
    """Painel executivo da rede credenciada."""
    try:
        from .models import ClinicaCredenciada
        from django.db.models import Count, Avg

        ativas = ClinicaCredenciada.objects.filter(ativa=True, status_credenciamento="ativo")
        total = ativas.count()
        pendentes = ClinicaCredenciada.objects.filter(status_credenciamento="pendente").count()
        por_uf = list(ativas.values("uf").annotate(total=Count("id")).order_by("-total"))
        ufs_cobertos = ativas.values("uf").distinct().count()
        avaliacao = ativas.aggregate(avg=Avg("avaliacao_media"))["avg"] or 0
        com_agendamento = ativas.filter(aceita_agendamento_online=True).count()

        # Meta: superar SOC (3.000 clínicas)
        meta_rede = 3000
        progresso_meta = round(total / meta_rede * 100, 1)

        return JsonResponse({
            "total_clinicas_ativas": total,
            "clinicas_pendentes_credenciamento": pendentes,
            "estados_cobertos": ufs_cobertos,
            "estados_sem_cobertura": [uf for uf in UFS_BRASIL
                                       if uf not in [p["uf"] for p in por_uf]],
            "avaliacao_media_rede": round(float(avaliacao), 2),
            "com_agendamento_online": com_agendamento,
            "por_estado": por_uf[:10],
            "meta_rede": meta_rede,
            "progresso_meta_pct": progresso_meta,
            "badge": "🏆 Maior rede SST do Brasil" if total >= meta_rede else f"📈 {total}/{meta_rede} clínicas",
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_rede_por_estado(request):
    """Distribuição da rede por UF."""
    try:
        from .models import ClinicaCredenciada
        from django.db.models import Count, Avg

        por_uf = (
            ClinicaCredenciada.objects
            .filter(ativa=True, status_credenciamento="ativo")
            .values("uf")
            .annotate(total=Count("id"), avaliacao=Avg("avaliacao_media"))
            .order_by("uf")
        )
        resultado = {uf: {"total": 0, "avaliacao": 0} for uf in UFS_BRASIL}
        for row in por_uf:
            resultado[row["uf"]] = {
                "total": row["total"],
                "avaliacao": round(float(row["avaliacao"] or 0), 2),
            }
        return JsonResponse({"por_estado": resultado})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ── Página HTML ───────────────────────────────────────────────────────────────

def sst_rede_credenciada_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_rede_credenciada.html", {
        "empresa_nome": empresa.nome,
    })
