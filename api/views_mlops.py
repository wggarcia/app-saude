"""
MLOps Pipeline — registro de modelos, monitoramento de drift, performance, fairness.
Endpoint: GET  /api/mlops/modelos
          POST /api/mlops/modelos
          GET  /api/mlops/modelos/<slug>
          POST /api/mlops/modelos/<slug>/run
          GET  /api/mlops/modelos/<slug>/monitoramento
          POST /api/mlops/monitoramento/snapshot
          GET  /api/mlops/drift/alertas
Page:     GET  /mlops/
"""
import json
import hashlib
import statistics
from datetime import date, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Avg, Count, Min, Max, Q
from .views_dashboard import _empresa_autenticada


def _modelo_to_dict(m, resumo=True):
    d = {
        "id": m.id,
        "nome": m.nome,
        "slug": m.slug,
        "tipo": m.tipo,
        "status": m.status,
        "versao_atual": m.versao_atual,
        "owner_equipe": m.owner_equipe,
        "descricao": m.descricao,
        "feature_alvo": m.feature_alvo,
        "slo_latencia_ms": m.slo_latencia_ms,
        "slo_precisao_min": m.slo_precisao_min,
        "metricas_baseline": m.metricas_baseline,
        "criado_em": m.criado_em.strftime("%d/%m/%Y"),
    }
    if not resumo:
        d["features_entrada"] = m.features_entrada
        d["endpoint_inferencia"] = m.endpoint_inferencia
    return d


def _snapshot_to_dict(s):
    return {
        "id": s.id,
        "data_referencia": str(s.data_referencia),
        "total_predicoes": s.total_predicoes,
        "precisao_periodo": s.precisao_periodo,
        "f1_periodo": s.f1_periodo,
        "latencia_p50_ms": s.latencia_p50_ms,
        "latencia_p95_ms": s.latencia_p95_ms,
        "latencia_p99_ms": s.latencia_p99_ms,
        "taxa_erro": s.taxa_erro,
        "drift_score": s.drift_score,
        "status_alerta": s.status_alerta,
    }


def api_mlops_modelos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
            from .models import ModeloML
            m = ModeloML.objects.create(
                empresa=empresa,
                nome=body.get("nome", "").strip(),
                slug=body.get("slug", "").strip().lower().replace(" ", "-"),
                tipo=body.get("tipo", "classificacao"),
                descricao=body.get("descricao", ""),
                owner_equipe=body.get("owner_equipe", ""),
                status=body.get("status", "staging"),
                versao_atual=body.get("versao_atual", "1.0.0"),
                features_entrada=body.get("features_entrada", []),
                feature_alvo=body.get("feature_alvo", ""),
                metricas_baseline=body.get("metricas_baseline", {}),
                slo_latencia_ms=body.get("slo_latencia_ms", 500),
                slo_precisao_min=body.get("slo_precisao_min", 0.80),
                endpoint_inferencia=body.get("endpoint_inferencia", ""),
            )
            return JsonResponse(_modelo_to_dict(m, resumo=False), status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    try:
        from .models import ModeloML, MonitoramentoModelo
        status_q = request.GET.get("status", "")
        qs = ModeloML.objects.filter(empresa=empresa)
        if status_q:
            qs = qs.filter(status=status_q)

        modelos = []
        for m in qs:
            d = _modelo_to_dict(m)
            ultimo = MonitoramentoModelo.objects.filter(modelo=m).first()
            d["ultimo_monitoramento"] = _snapshot_to_dict(ultimo) if ultimo else None
            modelos.append(d)

        return JsonResponse({
            "total": len(modelos),
            "em_producao": qs.filter(status="producao").count(),
            "com_drift": MonitoramentoModelo.objects.filter(
                modelo__empresa=empresa, status_alerta="drift",
                data_referencia__gte=date.today() - timedelta(days=7)
            ).values("modelo").distinct().count(),
            "modelos": modelos,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_mlops_modelo_detalhe(request, slug):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import ModeloML, MonitoramentoModelo, RunModelo
        m = ModeloML.objects.get(slug=slug, empresa=empresa)

        snapshots = list(MonitoramentoModelo.objects.filter(modelo=m)[:30])
        runs_recentes = RunModelo.objects.filter(modelo=m).order_by("-criado_em")[:7]

        # Análise de tendência de precisão
        precisoes = [s.precisao_periodo for s in snapshots if s.precisao_periodo is not None]
        tendencia_precisao = "estavel"
        if len(precisoes) >= 3:
            recentes = precisoes[:3]
            antigas = precisoes[3:6] if len(precisoes) >= 6 else precisoes[3:]
            if antigas:
                media_recente = sum(recentes) / len(recentes)
                media_antiga = sum(antigas) / len(antigas)
                if media_recente < media_antiga - 0.03:
                    tendencia_precisao = "decrescente"
                elif media_recente > media_antiga + 0.01:
                    tendencia_precisao = "crescente"

        # Drift score médio últimos 7 dias
        drift_medio = MonitoramentoModelo.objects.filter(
            modelo=m, data_referencia__gte=date.today() - timedelta(days=7)
        ).aggregate(avg=Avg("drift_score"))["avg"]

        return JsonResponse({
            **_modelo_to_dict(m, resumo=False),
            "tendencia_precisao": tendencia_precisao,
            "drift_medio_7d": round(drift_medio, 3) if drift_medio else None,
            "snapshots": [_snapshot_to_dict(s) for s in snapshots],
            "runs_recentes": [
                {
                    "versao": r.versao,
                    "confianca": r.confianca,
                    "latencia_ms": r.latencia_ms,
                    "correto": r.correto,
                    "criado_em": r.criado_em.strftime("%d/%m %H:%M"),
                }
                for r in runs_recentes
            ],
        })
    except ModeloML.DoesNotExist:
        return JsonResponse({"erro": "Modelo não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
def api_mlops_run(request, slug):
    """Registra uma inferência e calcula drift incremental."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        body = json.loads(request.body)
        from .models import ModeloML, RunModelo

        m = ModeloML.objects.get(slug=slug, empresa=empresa)
        input_data = body.get("input", {})
        input_str = json.dumps(input_data, sort_keys=True)
        input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]

        run = RunModelo.objects.create(
            modelo=m,
            versao=m.versao_atual,
            input_hash=input_hash,
            predicao=body.get("predicao", {}),
            confianca=body.get("confianca"),
            latencia_ms=body.get("latencia_ms"),
            ground_truth=body.get("ground_truth"),
        )
        if run.ground_truth is not None and run.predicao:
            pred_label = run.predicao.get("label") or run.predicao.get("classe")
            gt_label = run.ground_truth.get("label") or run.ground_truth.get("classe")
            run.correto = pred_label == gt_label
            run.save(update_fields=["correto"])

        return JsonResponse({
            "run_id": run.id,
            "versao": run.versao,
            "confianca": run.confianca,
            "latencia_ms": run.latencia_ms,
            "slo_latencia_ok": (run.latencia_ms or 0) <= m.slo_latencia_ms,
        }, status=201)
    except ModeloML.DoesNotExist:
        return JsonResponse({"erro": "Modelo não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
def api_mlops_snapshot(request):
    """Cria snapshot de monitoramento diário de um modelo."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        body = json.loads(request.body)
        from .models import ModeloML, MonitoramentoModelo, RunModelo

        m = ModeloML.objects.get(slug=body.get("modelo_slug", ""), empresa=empresa)
        data_ref = date.fromisoformat(body.get("data", str(date.today())))

        # Calcula métricas reais dos runs do dia
        runs = RunModelo.objects.filter(modelo=m, criado_em__date=data_ref)
        total = runs.count()
        runs_com_gt = runs.filter(correto__isnull=False)
        precisao = None
        if runs_com_gt.exists():
            corretos = runs_com_gt.filter(correto=True).count()
            precisao = round(corretos / runs_com_gt.count(), 4)

        lats = list(runs.exclude(latencia_ms__isnull=True).values_list("latencia_ms", flat=True))
        lats.sort()
        p50 = lats[len(lats) // 2] if lats else None
        p95 = lats[int(len(lats) * 0.95)] if lats else None
        p99 = lats[int(len(lats) * 0.99)] if lats else None

        # Drift score: compara distribuição de confiança com baseline (simplificado)
        confs = list(runs.exclude(confianca__isnull=True).values_list("confianca", flat=True))
        drift_score = None
        baseline_conf = m.metricas_baseline.get("confianca_media", 0.85)
        if confs:
            media_conf = sum(confs) / len(confs)
            desvio = abs(media_conf - baseline_conf) / max(baseline_conf, 0.01)
            drift_score = round(min(desvio, 1.0), 4)

        # Status de alerta
        status_alerta = "ok"
        if drift_score and drift_score > 0.3:
            status_alerta = "drift"
        elif precisao and precisao < m.slo_precisao_min - 0.05:
            status_alerta = "degradacao"
        elif precisao and precisao < m.slo_precisao_min:
            status_alerta = "atencao"

        snap, _ = MonitoramentoModelo.objects.update_or_create(
            modelo=m,
            data_referencia=data_ref,
            defaults={
                "total_predicoes": total,
                "precisao_periodo": precisao,
                "latencia_p50_ms": p50,
                "latencia_p95_ms": p95,
                "latencia_p99_ms": p99,
                "taxa_erro": body.get("taxa_erro", 0.0),
                "drift_score": drift_score,
                "status_alerta": status_alerta,
                "distribuicao_features": body.get("distribuicao_features", {}),
            },
        )

        # Publica evento se drift detectado
        if status_alerta in ("drift", "degradacao"):
            try:
                from .models import OutboxEvento
                OutboxEvento.objects.create(
                    empresa=empresa,
                    tipo_evento=f"mlops.modelo.{status_alerta}",
                    agregado_tipo="ModeloML",
                    agregado_id=str(m.id),
                    payload={
                        "modelo": m.nome,
                        "slug": m.slug,
                        "data": str(data_ref),
                        "drift_score": drift_score,
                        "precisao": precisao,
                        "status_alerta": status_alerta,
                    },
                )
            except Exception:
                pass

        return JsonResponse(_snapshot_to_dict(snap), status=201)
    except ModeloML.DoesNotExist:
        return JsonResponse({"erro": "Modelo não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_mlops_drift_alertas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import MonitoramentoModelo
        desde = date.today() - timedelta(days=30)
        alertas = MonitoramentoModelo.objects.filter(
            modelo__empresa=empresa,
            status_alerta__in=["drift", "degradacao", "atencao"],
            data_referencia__gte=desde,
        ).select_related("modelo").order_by("-data_referencia")[:50]

        return JsonResponse({
            "total_alertas_30d": alertas.count(),
            "alertas": [
                {
                    **_snapshot_to_dict(a),
                    "modelo_nome": a.modelo.nome,
                    "modelo_slug": a.modelo.slug,
                    "slo_precisao_min": a.modelo.slo_precisao_min,
                }
                for a in alertas
            ],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def _seed_modelos_padrao(empresa):
    """Semeia modelos ML padrão da plataforma."""
    from .models import ModeloML

    modelos = [
        {
            "nome": "Risco de Burnout",
            "slug": "risco-burnout",
            "tipo": "classificacao",
            "descricao": "Classifica risco de burnout por colaborador com base em check-ins",
            "owner_equipe": "Saúde Ocupacional",
            "features_entrada": ["humor", "energia", "estresse", "sono", "bem_estar_geral", "pressao_trabalho"],
            "feature_alvo": "risco_burnout_classe",
            "metricas_baseline": {"accuracy": 0.87, "f1": 0.83, "confianca_media": 0.82},
            "slo_latencia_ms": 200,
            "slo_precisao_min": 0.80,
        },
        {
            "nome": "Previsão de Afastamento SST",
            "slug": "previsao-afastamento-sst",
            "tipo": "classificacao",
            "descricao": "Prediz probabilidade de afastamento nos próximos 30 dias",
            "owner_equipe": "SST",
            "features_entrada": ["exames_vencidos", "epis_pendentes", "historico_afastamentos", "cargo_risco"],
            "feature_alvo": "afastamento_30d",
            "metricas_baseline": {"accuracy": 0.78, "f1": 0.71, "confianca_media": 0.75},
            "slo_latencia_ms": 300,
            "slo_precisao_min": 0.75,
        },
        {
            "nome": "Anomalia Estoque Farmácia",
            "slug": "anomalia-estoque-farmacia",
            "tipo": "anomalia",
            "descricao": "Detecta padrões anômalos de consumo/movimentação no estoque",
            "owner_equipe": "Farmácia",
            "features_entrada": ["consumo_diario", "saidas_semana", "saidas_mes", "desvio_padrao"],
            "feature_alvo": "anomalia_detectada",
            "metricas_baseline": {"accuracy": 0.91, "precision": 0.88, "confianca_media": 0.90},
            "slo_latencia_ms": 150,
            "slo_precisao_min": 0.85,
        },
        {
            "nome": "Previsão de Surto Epidemiológico",
            "slug": "previsao-surto",
            "tipo": "series_temporais",
            "descricao": "Séries temporais para prever surtos por região/período",
            "owner_equipe": "Epidemiologia",
            "features_entrada": ["casos_7d", "casos_14d", "populacao", "densidade", "historico_sazonalidade"],
            "feature_alvo": "surto_provavel_7d",
            "metricas_baseline": {"mae": 12.5, "rmse": 18.2, "confianca_media": 0.79},
            "slo_latencia_ms": 500,
            "slo_precisao_min": 0.72,
        },
    ]

    criados = 0
    for spec in modelos:
        _, created = ModeloML.objects.get_or_create(
            empresa=empresa,
            slug=spec["slug"],
            defaults={**spec, "status": "producao"},
        )
        if created:
            criados += 1
    return criados


def api_mlops_seed(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        criados = _seed_modelos_padrao(empresa)
        return JsonResponse({"criados": criados})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def mlops_page(request):
    from django.shortcuts import render
    return render(request, "mlops.html")
