"""
Observabilidade & SLO — health checks por domínio, latência, disponibilidade.
Endpoint: GET /api/saude          (health básico, sem auth)
          GET /api/slo/status     (SLO por domínio, auth)
          GET /api/slo/incidentes (histórico, auth)
Page:     GET /observabilidade/
"""
import time
from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.db import connection
from .views_dashboard import _empresa_autenticada


def _check_db():
    t0 = time.monotonic()
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        latencia = round((time.monotonic() - t0) * 1000, 1)
        return {"ok": True, "latencia_ms": latencia}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def _check_dominio(modelo_path, label):
    t0 = time.monotonic()
    try:
        parts = modelo_path.rsplit(".", 1)
        mod = __import__(parts[0], fromlist=[parts[1]])
        cls = getattr(mod, parts[1])
        cls.objects.first()
        latencia = round((time.monotonic() - t0) * 1000, 1)
        return {"dominio": label, "ok": True, "latencia_ms": latencia, "status": "operacional"}
    except Exception as e:
        return {"dominio": label, "ok": False, "erro": str(e)[:120], "status": "degradado"}


def api_health(request):
    """Endpoint público para load balancer / uptime monitor."""
    db = _check_db()
    ok = db["ok"]
    return JsonResponse(
        {
            "status": "ok" if ok else "degradado",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "versao": "2.0.0",
            "componentes": {
                "banco_dados": "ok" if db["ok"] else "erro",
                "db_latencia_ms": db.get("latencia_ms"),
            },
        },
        status=200 if ok else 503,
    )


def api_slo_status(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    db = _check_db()
    dominios = [
        _check_dominio("api.models.FuncionarioSST", "SST"),
        _check_dominio("api.models.CheckinDiarioCorporativo", "Saúde Ocupacional"),
        _check_dominio("api.models.LoteMedicamento", "Farmácia"),
        _check_dominio("api.models.LeitoHospitalar", "Hospital"),
        _check_dominio("api.models.AuditoriaInstitucional", "Compliance"),
        _check_dominio("api.models.Empresa", "Core/Auth"),
    ]

    # SLOs definidos por domínio
    SLO_LATENCIA_MS = 300  # p95 alvo
    total_ok = sum(1 for d in dominios if d["ok"])
    score = round(total_ok / len(dominios) * 100, 1)

    slos = []
    for d in dominios:
        lat = d.get("latencia_ms", 9999)
        cumpre_latencia = lat <= SLO_LATENCIA_MS
        slos.append({
            "dominio": d["dominio"],
            "status": d["status"],
            "latencia_ms": lat,
            "slo_latencia_ms": SLO_LATENCIA_MS,
            "cumpre_slo": d["ok"] and cumpre_latencia,
            "erro": d.get("erro"),
        })

    # Uptime simulado (sem infra de métricas real ainda — placeholder)
    uptime_30d = 99.9 if score == 100 else round(90 + score / 10, 2)

    return JsonResponse({
        "empresa": empresa.nome,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "score_disponibilidade": score,
        "uptime_30d_pct": uptime_30d,
        "banco_dados": {
            "ok": db["ok"],
            "latencia_ms": db.get("latencia_ms"),
        },
        "dominios": slos,
        "slo_definicoes": {
            "disponibilidade_alvo": "99.9%",
            "latencia_p95_alvo_ms": SLO_LATENCIA_MS,
            "janela_medicao": "30 dias",
        },
    })


def api_slo_incidentes(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import AuditoriaInstitucional
        # Eventos de sistema (erros, falhas) como proxy de incidentes
        desde = date.today() - timedelta(days=30)
        eventos_sistema = AuditoriaInstitucional.objects.filter(
            empresa=empresa,
            acao__icontains="erro",
            criado_em__date__gte=desde,
        ).order_by("-criado_em")[:20]

        incidentes = [
            {
                "id": e.id,
                "data": e.criado_em.strftime("%d/%m/%Y %H:%M"),
                "tipo": e.acao,
                "objeto": e.objeto_tipo or "sistema",
                "impacto": "baixo",
            }
            for e in eventos_sistema
        ]
    except Exception:
        incidentes = []

    return JsonResponse({
        "incidentes_30d": len(incidentes),
        "registros": incidentes,
        "mttr_estimado_min": 15,  # Mean Time To Recover placeholder
        "mttd_estimado_min": 5,   # Mean Time To Detect placeholder
    })


def observabilidade_page(request):
    from django.shortcuts import render
    return render(request, "observabilidade.html")
