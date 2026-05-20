import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .access_control import get_setor
from .models import ProgramaSaudeGov, IndicadorSaudeGov, OrcamentoSaudeGov, PlanoAcaoGov
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    return empresa


def _e(req):
    return _empresa_autenticada(req)


# ── Programas ──────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
def api_programas_gov(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = ProgramaSaudeGov.objects.filter(empresa=e)
        return JsonResponse({"programas": [
            {"id": p.id, "nome": p.nome, "descricao": p.descricao,
             "status": p.status, "populacao_alvo": p.populacao_alvo,
             "responsavel": p.responsavel,
             "orcamento_previsto": str(p.orcamento_previsto) if p.orcamento_previsto else "",
             "orcamento_executado": str(p.orcamento_executado),
             "data_inicio": str(p.data_inicio) if p.data_inicio else "",
             "data_fim_prevista": str(p.data_fim_prevista) if p.data_fim_prevista else "",
             "criado_em": p.criado_em.isoformat()}
            for p in qs
        ]})
    data = json.loads(request.body or "{}")
    p = ProgramaSaudeGov.objects.create(
        empresa=e,
        nome=data.get("nome", ""),
        descricao=data.get("descricao", ""),
        status=data.get("status", "planejamento"),
        populacao_alvo=data.get("populacao_alvo", ""),
        responsavel=data.get("responsavel", ""),
        orcamento_previsto=data.get("orcamento_previsto") or None,
        data_inicio=data.get("data_inicio") or None,
        data_fim_prevista=data.get("data_fim_prevista") or None,
    )
    return JsonResponse({"id": p.id, "nome": p.nome}, status=201)


@require_http_methods(["PUT", "DELETE"])
def api_programa_gov_detalhe(request, programa_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        p = ProgramaSaudeGov.objects.get(pk=programa_id, empresa=e)
    except ProgramaSaudeGov.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        p.delete()
        return JsonResponse({"ok": True})
    data = json.loads(request.body or "{}")
    nullable = {"orcamento_previsto", "data_inicio", "data_fim_prevista"}
    for campo in ["nome", "descricao", "status", "populacao_alvo", "responsavel",
                  "orcamento_previsto", "orcamento_executado", "data_inicio", "data_fim_prevista"]:
        if campo in data:
            setattr(p, campo, data[campo] or None if campo in nullable else data[campo])
    p.save()
    return JsonResponse({"ok": True})


# ── Indicadores ────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
def api_indicadores_gov(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = IndicadorSaudeGov.objects.filter(empresa=e).select_related("programa")
        return JsonResponse({"indicadores": [
            {"id": i.id, "nome": i.nome, "descricao": i.descricao,
             "tipo": i.tipo,
             "meta": str(i.meta) if i.meta is not None else "",
             "valor_atual": str(i.valor_atual) if i.valor_atual is not None else "",
             "unidade": i.unidade,
             "periodo_referencia": i.periodo_referencia,
             "programa_id": i.programa_id,
             "programa_nome": i.programa.nome if i.programa else "",
             "atingiu_meta": (i.valor_atual is not None and i.meta is not None and i.valor_atual >= i.meta)}
            for i in qs
        ]})
    data = json.loads(request.body or "{}")
    prog = None
    if data.get("programa_id"):
        try:
            prog = ProgramaSaudeGov.objects.get(pk=data["programa_id"], empresa=e)
        except ProgramaSaudeGov.DoesNotExist:
            pass
    i = IndicadorSaudeGov.objects.create(
        empresa=e, programa=prog,
        nome=data.get("nome", ""),
        descricao=data.get("descricao", ""),
        tipo=data.get("tipo", "quantitativo"),
        meta=data.get("meta") or None,
        valor_atual=data.get("valor_atual") or None,
        unidade=data.get("unidade", ""),
        periodo_referencia=data.get("periodo_referencia", ""),
    )
    return JsonResponse({"id": i.id}, status=201)


@require_http_methods(["PUT", "DELETE"])
def api_indicador_gov_detalhe(request, indicador_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        i = IndicadorSaudeGov.objects.get(pk=indicador_id, empresa=e)
    except IndicadorSaudeGov.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        i.delete()
        return JsonResponse({"ok": True})
    data = json.loads(request.body or "{}")
    nullable = {"meta", "valor_atual"}
    for campo in ["nome", "descricao", "tipo", "meta", "valor_atual", "unidade", "periodo_referencia"]:
        if campo in data:
            setattr(i, campo, data[campo] or None if campo in nullable else data[campo])
    i.save()
    return JsonResponse({"ok": True})


# ── Orçamento ──────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
def api_orcamentos_gov(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = OrcamentoSaudeGov.objects.filter(empresa=e)
        return JsonResponse({"orcamentos": [
            {"id": o.id, "ano": o.ano,
             "total_previsto": str(o.total_previsto),
             "total_executado": str(o.total_executado),
             "execucao_pct": round(float(o.total_executado) / float(o.total_previsto) * 100, 1) if o.total_previsto else 0,
             "fonte_recurso": o.fonte_recurso,
             "observacoes": o.observacoes}
            for o in qs
        ]})
    data = json.loads(request.body or "{}")
    o, created = OrcamentoSaudeGov.objects.get_or_create(
        empresa=e, ano=int(data.get("ano", timezone.now().year)),
        defaults={
            "total_previsto": data.get("total_previsto", 0),
            "fonte_recurso": data.get("fonte_recurso", ""),
            "observacoes": data.get("observacoes", ""),
        },
    )
    if not created:
        o.total_previsto = data.get("total_previsto", o.total_previsto)
        o.total_executado = data.get("total_executado", o.total_executado)
        o.fonte_recurso = data.get("fonte_recurso", o.fonte_recurso)
        o.observacoes = data.get("observacoes", o.observacoes)
        o.save()
    return JsonResponse({"id": o.id, "created": created}, status=201 if created else 200)


# ── Planos de Ação ─────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
def api_planos_acao_gov(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = PlanoAcaoGov.objects.filter(empresa=e).select_related("programa")
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({"planos": [
            {"id": p.id, "titulo": p.titulo, "descricao": p.descricao,
             "responsavel": p.responsavel, "prioridade": p.prioridade,
             "status": p.status, "prazo": str(p.prazo) if p.prazo else "",
             "progresso": p.progresso,
             "programa_id": p.programa_id,
             "programa_nome": p.programa.nome if p.programa else "",
             "criado_em": p.criado_em.isoformat()}
            for p in qs
        ]})
    data = json.loads(request.body or "{}")
    prog = None
    if data.get("programa_id"):
        try:
            prog = ProgramaSaudeGov.objects.get(pk=data["programa_id"], empresa=e)
        except ProgramaSaudeGov.DoesNotExist:
            pass
    p = PlanoAcaoGov.objects.create(
        empresa=e, programa=prog,
        titulo=data.get("titulo", ""),
        descricao=data.get("descricao", ""),
        responsavel=data.get("responsavel", ""),
        prioridade=data.get("prioridade", "media"),
        prazo=data.get("prazo") or None,
    )
    return JsonResponse({"id": p.id}, status=201)


@require_http_methods(["PUT", "DELETE"])
def api_plano_acao_gov_detalhe(request, plano_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        p = PlanoAcaoGov.objects.get(pk=plano_id, empresa=e)
    except PlanoAcaoGov.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        p.delete()
        return JsonResponse({"ok": True})
    data = json.loads(request.body or "{}")
    for campo in ["titulo", "descricao", "responsavel", "prioridade", "status", "prazo", "progresso"]:
        if campo in data:
            setattr(p, campo, data[campo] or None if campo == "prazo" else data[campo])
    p.save()
    return JsonResponse({"ok": True})


# ── KPIs ───────────────────────────────────────────────────────────────────────
def api_governo_ops_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    programas_ativos = ProgramaSaudeGov.objects.filter(empresa=e, status="ativo").count()
    total_programas = ProgramaSaudeGov.objects.filter(empresa=e).count()
    indicadores = list(IndicadorSaudeGov.objects.filter(empresa=e))
    indicadores_ok = sum(
        1 for i in indicadores
        if i.valor_atual is not None and i.meta is not None and i.valor_atual >= i.meta
    )
    planos_pendentes = PlanoAcaoGov.objects.filter(empresa=e, status="pendente").count()
    planos_andamento = PlanoAcaoGov.objects.filter(empresa=e, status="em_andamento").count()
    orcamento_ano = OrcamentoSaudeGov.objects.filter(empresa=e, ano=timezone.now().year).first()
    return JsonResponse({
        "programas_ativos": programas_ativos,
        "total_programas": total_programas,
        "indicadores_total": len(indicadores),
        "indicadores_meta_atingida": indicadores_ok,
        "planos_pendentes": planos_pendentes,
        "planos_andamento": planos_andamento,
        "orcamento_previsto": str(orcamento_ano.total_previsto) if orcamento_ano else "0",
        "orcamento_executado": str(orcamento_ano.total_executado) if orcamento_ano else "0",
    })


# ── PDF ────────────────────────────────────────────────────────────────────────
def api_governo_pdf_relatorio(request):
    from django.http import HttpResponse
    from .pdf_ops import gerar_pdf_programas_gov
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    programas = list(ProgramaSaudeGov.objects.filter(empresa=e))
    indicadores = list(IndicadorSaudeGov.objects.filter(empresa=e).select_related("programa"))
    planos = list(PlanoAcaoGov.objects.filter(empresa=e).select_related("programa"))
    buf = gerar_pdf_programas_gov(e, programas, indicadores, planos)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="relatorio_gestao_saude.pdf"'
    return resp
