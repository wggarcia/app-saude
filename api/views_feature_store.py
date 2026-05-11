"""
Feature Store & Data Dictionary — domínio de dados enterprise.
Armazena features computadas por colaborador/empresa com versionamento.
Mantém dicionário de eventos e SLA de qualidade de dados.

Endpoint: GET  /api/feature-store/features
          POST /api/feature-store/features
          GET  /api/feature-store/features/<entity_type>/<entity_id>
          GET  /api/feature-store/dicionario
          GET  /api/feature-store/qualidade
          GET  /api/feature-store/sla
Page:     GET  /feature-store/
"""
import json
from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .views_dashboard import _empresa_autenticada


# ─── Feature registry (in-memory, substituir por DB em prod) ─────────────────

FEATURE_REGISTRY = {
    "colaborador": {
        "score_burnout": {
            "descricao": "Score de risco de burnout (0-5, maior = mais risco)",
            "tipo": "float",
            "fonte": "CheckinSemanalCorporativo",
            "frequencia_atualizacao": "semanal",
            "sla_atraso_max_horas": 25,
            "owner": "Saúde Ocupacional",
            "tags": ["saude", "risco", "ml_feature"],
        },
        "media_humor_7d": {
            "descricao": "Média de humor dos últimos 7 dias (1-5)",
            "tipo": "float",
            "fonte": "CheckinDiarioCorporativo",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "Saúde Ocupacional",
            "tags": ["saude", "humor", "ml_feature"],
        },
        "media_energia_7d": {
            "descricao": "Média de energia dos últimos 7 dias (1-5)",
            "tipo": "float",
            "fonte": "CheckinDiarioCorporativo",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "Saúde Ocupacional",
            "tags": ["saude", "energia", "ml_feature"],
        },
        "exames_vencidos_count": {
            "descricao": "Número de exames médicos vencidos do funcionário",
            "tipo": "int",
            "fonte": "ExameMedico",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "SST",
            "tags": ["sst", "exames", "compliance"],
        },
        "dias_sem_afastamento": {
            "descricao": "Dias desde o último afastamento (ou desde admissão)",
            "tipo": "int",
            "fonte": "AfastamentoSST",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "SST",
            "tags": ["sst", "afastamento", "ml_feature"],
        },
        "epis_pendentes_count": {
            "descricao": "EPIs com entrega pendente para o funcionário",
            "tipo": "int",
            "fonte": "EntregaEPI",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "SST",
            "tags": ["sst", "epi", "compliance"],
        },
    },
    "empresa": {
        "nrr_estimado": {
            "descricao": "Net Revenue Retention estimado (%)",
            "tipo": "float",
            "fonte": "Empresa + PlanoEmpresa",
            "frequencia_atualizacao": "mensal",
            "sla_atraso_max_horas": 730,
            "owner": "Financial OS",
            "tags": ["financeiro", "saas_metrics"],
        },
        "score_sst_empresa": {
            "descricao": "Score consolidado de SST da empresa (0-100)",
            "tipo": "int",
            "fonte": "FuncionarioSST + ExameMedico + AfastamentoSST",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "SST",
            "tags": ["sst", "score", "ml_feature"],
        },
        "taxa_adimplencia_checkin": {
            "descricao": "% de colaboradores que fizeram check-in nos últimos 7 dias",
            "tipo": "float",
            "fonte": "CheckinDiarioCorporativo + FuncionarioSST",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "Saúde Ocupacional",
            "tags": ["engajamento", "ml_feature"],
        },
        "lotes_vencidos_count": {
            "descricao": "Lotes de medicamentos vencidos com estoque > 0",
            "tipo": "int",
            "fonte": "LoteMedicamento",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "Farmácia",
            "tags": ["farmacia", "compliance"],
        },
    },
    "unidade": {
        "score_bem_estar_unidade": {
            "descricao": "Score de bem-estar médio dos colaboradores da unidade (1-5)",
            "tipo": "float",
            "fonte": "CheckinDiarioCorporativo",
            "frequencia_atualizacao": "diaria",
            "sla_atraso_max_horas": 25,
            "owner": "Saúde Ocupacional",
            "tags": ["saude", "unidade", "ml_feature"],
        },
    },
}

# Dicionário de eventos da plataforma
EVENTO_DICIONARIO = [
    {
        "tipo": "sst.exame.vencido",
        "descricao": "Exame médico ocupacional venceu sem renovação",
        "dominio": "SST",
        "produtor": "api/views_relatorio.py:_gerar_recomendacoes",
        "consumidores": ["notification-service", "compliance-audit"],
        "schema_contrato": "sst.exame.vencido",
        "sla_entrega_ms": 5000,
        "criticidade": "alta",
        "tags": ["sst", "compliance", "nr-07"],
    },
    {
        "tipo": "farmacia.lote.vencendo",
        "descricao": "Lote de medicamento vence em menos de 30 dias",
        "dominio": "Farmácia",
        "produtor": "api/views_relatorio.py:_gerar_recomendacoes",
        "consumidores": ["farmacia-manager", "compliance-audit"],
        "schema_contrato": "farmacia.lote.vencendo",
        "sla_entrega_ms": 5000,
        "criticidade": "media",
        "tags": ["farmacia", "fefo", "estoque"],
    },
    {
        "tipo": "saude.burnout.alerta",
        "descricao": "Score de burnout acima de 3.5 detectado pela IA",
        "dominio": "Saúde Ocupacional",
        "produtor": "api/views_mlops.py:api_mlops_snapshot",
        "consumidores": ["rh-manager", "psicologo", "lider-direto"],
        "schema_contrato": "saude.burnout.alerta",
        "sla_entrega_ms": 10000,
        "criticidade": "alta",
        "tags": ["saude", "burnout", "ml"],
    },
    {
        "tipo": "mlops.modelo.drift",
        "descricao": "Drift detectado em modelo de ML em produção",
        "dominio": "MLOps",
        "produtor": "api/views_mlops.py:api_mlops_snapshot",
        "consumidores": ["mlops-team", "data-engineering"],
        "schema_contrato": None,
        "sla_entrega_ms": 30000,
        "criticidade": "media",
        "tags": ["mlops", "monitoramento", "ia"],
    },
    {
        "tipo": "mlops.modelo.degradacao",
        "descricao": "Performance abaixo do SLO mínimo em modelo de ML",
        "dominio": "MLOps",
        "produtor": "api/views_mlops.py:api_mlops_snapshot",
        "consumidores": ["mlops-team"],
        "schema_contrato": None,
        "sla_entrega_ms": 30000,
        "criticidade": "alta",
        "tags": ["mlops", "monitoramento", "ia"],
    },
    {
        "tipo": "hospital.leito.ocupacao_critica",
        "descricao": "Taxa de ocupação hospitalar acima de 85%",
        "dominio": "Hospital",
        "produtor": "api/views_relatorio.py",
        "consumidores": ["hospital-manager", "compliance-audit"],
        "schema_contrato": "hospital.leito.ocupacao_critica",
        "sla_entrega_ms": 5000,
        "criticidade": "critica",
        "tags": ["hospital", "leitos", "urgencia"],
    },
]


def _computar_features_colaborador(funcionario, empresa):
    """Computa features de ML para um colaborador em tempo real."""
    from datetime import date, timedelta
    feats = {}

    try:
        from .models import CheckinDiarioCorporativo, CheckinSemanalCorporativo
        from django.db.models import Avg
        hoje = date.today()
        janela_7 = hoje - timedelta(days=7)

        checkins = CheckinDiarioCorporativo.objects.filter(
            colaborador_alias=funcionario,
            data_referencia__gte=janela_7,
        )
        avgs = checkins.aggregate(h=Avg("humor"), e=Avg("energia"), s=Avg("estresse"))
        feats["media_humor_7d"] = round(avgs["h"] or 0, 2)
        feats["media_energia_7d"] = round(avgs["e"] or 0, 2)
        feats["media_estresse_7d"] = round(avgs["s"] or 0, 2)

        semanais = CheckinSemanalCorporativo.objects.filter(
            colaborador_alias=funcionario,
            semana_referencia__gte=janela_7,
        )
        avg_burnout = semanais.aggregate(b=Avg("risco_burnout"))["b"] or 0
        feats["score_burnout"] = round(avg_burnout, 2)
    except Exception:
        feats["score_burnout"] = None
        feats["media_humor_7d"] = None

    try:
        from .models import ExameMedico, AfastamentoSST
        feats["exames_vencidos_count"] = ExameMedico.objects.filter(
            funcionario=funcionario,
            data_vencimento__lt=date.today(),
        ).count()

        ultimo_afastamento = AfastamentoSST.objects.filter(funcionario=funcionario).order_by("-data_inicio").first()
        if ultimo_afastamento:
            feats["dias_sem_afastamento"] = (date.today() - ultimo_afastamento.data_inicio).days
        else:
            feats["dias_sem_afastamento"] = 9999
    except Exception:
        feats["exames_vencidos_count"] = None
        feats["dias_sem_afastamento"] = None

    return feats


def api_feature_store_features(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    entity_type = request.GET.get("tipo", "empresa")
    entity_id = request.GET.get("id", "")

    if entity_type == "colaborador" and entity_id:
        try:
            from .models import FuncionarioSST
            func = FuncionarioSST.objects.get(id=entity_id, empresa=empresa)
            feats = _computar_features_colaborador(func, empresa)
            return JsonResponse({
                "entity_type": "colaborador",
                "entity_id": entity_id,
                "entity_nome": func.nome,
                "computado_em": datetime.utcnow().isoformat() + "Z",
                "features": feats,
                "registry": FEATURE_REGISTRY.get("colaborador", {}),
            })
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=404)

    # Features agregadas da empresa
    feats_empresa = {}
    try:
        from .models import ExameMedico, CheckinDiarioCorporativo, FuncionarioSST, LoteMedicamento
        from django.db.models import Avg, Count
        hoje = date.today()

        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        checkins_7d = CheckinDiarioCorporativo.objects.filter(
            empresa=empresa,
            data_referencia__gte=hoje - timedelta(days=7),
        ).values("colaborador_alias").distinct().count()

        feats_empresa["taxa_adimplencia_checkin"] = round(checkins_7d / total_func * 100, 1) if total_func > 0 else 0
        feats_empresa["lotes_vencidos_count"] = LoteMedicamento.objects.filter(
            empresa=empresa, data_validade__lt=hoje, quantidade_atual__gt=0
        ).count()

        exames_venc = ExameMedico.objects.filter(
            funcionario__empresa=empresa, funcionario__ativo=True,
            data_vencimento__lt=hoje,
        ).count()
        score_sst = max(0, round(100 - (exames_venc / max(total_func, 1)) * 50))
        feats_empresa["score_sst_empresa"] = score_sst
    except Exception:
        pass

    return JsonResponse({
        "entity_type": "empresa",
        "entity_id": str(empresa.id),
        "entity_nome": empresa.nome,
        "computado_em": datetime.utcnow().isoformat() + "Z",
        "features": feats_empresa,
        "registry": FEATURE_REGISTRY.get("empresa", {}),
    })


def _registry_do_db():
    """Lê o catálogo de features do DB; cai de volta no dict estático se vazio."""
    try:
        from .models import FeatureRegistro
        qs = FeatureRegistro.objects.filter(ativo=True).values(
            "entidade", "nome", "descricao", "tipo", "fonte",
            "frequencia_atualizacao", "sla_atraso_max_horas", "owner", "tags",
        )
        if not qs.exists():
            _seed_feature_registry()
            qs = FeatureRegistro.objects.filter(ativo=True).values(
                "entidade", "nome", "descricao", "tipo", "fonte",
                "frequencia_atualizacao", "sla_atraso_max_horas", "owner", "tags",
            )
        registry = {}
        for row in qs:
            entidade = row.pop("entidade")
            nome = row.pop("nome")
            registry.setdefault(entidade, {})[nome] = row
        return registry
    except Exception:
        return FEATURE_REGISTRY


def _seed_feature_registry():
    """Popula FeatureRegistro a partir do dict estático FEATURE_REGISTRY."""
    try:
        from .models import FeatureRegistro
        objs = []
        for entidade, features in FEATURE_REGISTRY.items():
            for nome, meta in features.items():
                if not FeatureRegistro.objects.filter(entidade=entidade, nome=nome).exists():
                    objs.append(FeatureRegistro(
                        entidade=entidade, nome=nome,
                        descricao=meta.get("descricao", ""),
                        tipo=meta.get("tipo", "float"),
                        fonte=meta.get("fonte", ""),
                        frequencia_atualizacao=meta.get("frequencia_atualizacao", "diaria"),
                        sla_atraso_max_horas=meta.get("sla_atraso_max_horas", 25),
                        owner=meta.get("owner", ""),
                        tags=meta.get("tags", []),
                    ))
        if objs:
            FeatureRegistro.objects.bulk_create(objs, ignore_conflicts=True)
    except Exception:
        pass


def api_feature_store_dicionario(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    dominio_q = request.GET.get("dominio", "").strip().lower()
    eventos = EVENTO_DICIONARIO
    if dominio_q:
        eventos = [e for e in eventos if dominio_q in e["dominio"].lower() or dominio_q in " ".join(e.get("tags", []))]

    registry = _registry_do_db()
    total_features = sum(len(v) for v in registry.values())

    return JsonResponse({
        "empresa": empresa.nome,
        "total_eventos": len(eventos),
        "total_features": total_features,
        "feature_registry": registry,
        "eventos": eventos,
        "dominios": sorted(set(e["dominio"] for e in EVENTO_DICIONARIO)),
        "fonte_registry": "db",
    })


def api_feature_store_qualidade(request):
    """SLA de qualidade de dados por fonte."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    relatorios = []

    # CheckinDiario — espera dados todo dia
    try:
        from .models import CheckinDiarioCorporativo
        ultimo = CheckinDiarioCorporativo.objects.filter(empresa=empresa).order_by("-data_referencia").first()
        dias_atraso = (hoje - ultimo.data_referencia).days if ultimo else 999
        relatorios.append({
            "fonte": "CheckinDiarioCorporativo",
            "dominio": "Saúde Ocupacional",
            "sla_horas": 25,
            "ultimo_registro": str(ultimo.data_referencia) if ultimo else None,
            "atraso_dias": dias_atraso,
            "status": "ok" if dias_atraso <= 1 else ("atencao" if dias_atraso <= 3 else "violado"),
        })
    except Exception:
        relatorios.append({"fonte": "CheckinDiarioCorporativo", "status": "indisponivel"})

    try:
        from .models import ExameMedico
        ultimo = ExameMedico.objects.filter(funcionario__empresa=empresa).order_by("-criado_em").first()
        dias_atraso = (hoje - ultimo.criado_em.date()).days if ultimo else 999
        relatorios.append({
            "fonte": "ExameMedico",
            "dominio": "SST",
            "sla_horas": 72,
            "ultimo_registro": ultimo.criado_em.strftime("%Y-%m-%d") if ultimo else None,
            "atraso_dias": dias_atraso,
            "status": "ok" if dias_atraso <= 3 else ("atencao" if dias_atraso <= 7 else "violado"),
        })
    except Exception:
        relatorios.append({"fonte": "ExameMedico", "status": "indisponivel"})

    try:
        from .models import MovimentoEstoque
        ultimo = MovimentoEstoque.objects.filter(empresa=empresa).order_by("-criado_em").first()
        dias_atraso = (hoje - ultimo.criado_em.date()).days if ultimo else 999
        relatorios.append({
            "fonte": "MovimentoEstoque",
            "dominio": "Farmácia",
            "sla_horas": 25,
            "ultimo_registro": ultimo.criado_em.strftime("%Y-%m-%d") if ultimo else None,
            "atraso_dias": dias_atraso,
            "status": "ok" if dias_atraso <= 1 else ("atencao" if dias_atraso <= 3 else "violado"),
        })
    except Exception:
        relatorios.append({"fonte": "MovimentoEstoque", "status": "indisponivel"})

    try:
        from .models import AuditoriaInstitucional
        ultimo = AuditoriaInstitucional.objects.filter(empresa=empresa).order_by("-criado_em").first()
        dias_atraso = 0 if ultimo and (timezone.now() - ultimo.criado_em).total_seconds() < 86400 else 1
        relatorios.append({
            "fonte": "AuditoriaInstitucional",
            "dominio": "Compliance",
            "sla_horas": 1,
            "ultimo_registro": ultimo.criado_em.isoformat() if ultimo else None,
            "atraso_dias": dias_atraso,
            "status": "ok" if dias_atraso == 0 else "atencao",
        })
    except Exception:
        relatorios.append({"fonte": "AuditoriaInstitucional", "status": "indisponivel"})

    violacoes = sum(1 for r in relatorios if r.get("status") == "violado")
    atencoes = sum(1 for r in relatorios if r.get("status") == "atencao")
    score = max(0, round(100 - violacoes * 30 - atencoes * 10))

    return JsonResponse({
        "empresa": empresa.nome,
        "score_qualidade_dados": score,
        "total_fontes": len(relatorios),
        "violacoes_sla": violacoes,
        "atencoes_sla": atencoes,
        "fontes": relatorios,
    })


def feature_store_page(request):
    from django.shortcuts import render, redirect
    from .access_control import get_setor, _destino_correto
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return redirect("/login-empresa/")
    if get_setor(empresa) != "empresa":
        return redirect(_destino_correto(get_setor(empresa)))
    return render(request, "feature_store.html")
