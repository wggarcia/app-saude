import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    ColaboradorAliasCorporativo,
    CompetenciaItemCorporativo,
    EmpresaCargoCorporativo,
    EmpresaSetor,
    EquipamentoCorporativo,
    EvidenciaCompetenciaCorporativa,
    FuncaoCriticaCorporativa,
    TrilhaCompetenciaCorporativa,
    ValidacaoCompetenciaCorporativa,
)
from .services.dashboard_core import setor_conta
from .views_corporativo import _resolver_empresa_por_codigo
from .views_dashboard import _empresa_autenticada


def _empresa_competencia(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    if setor_conta(empresa) != "empresa":
        return None
    return empresa


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def competencia_corporativa(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return redirect("/")
    return render(request, "competencia_corporativa.html", {"empresa_nome": empresa.nome})


# ── CARGOS ───────────────────────────────────────────────────────────────────

@csrf_exempt
def api_cargos(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = EmpresaCargoCorporativo.objects.filter(empresa=empresa, ativo=True).select_related("setor")
        return JsonResponse({"cargos": [
            {"id": c.id, "nome": c.nome, "codigo": c.codigo, "nivel_inicial": c.nivel_inicial,
             "setor_id": c.setor_id, "setor_nome": c.setor.nome if c.setor else None}
            for c in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatorio"}, status=400)
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None
        cargo, created = EmpresaCargoCorporativo.objects.get_or_create(
            empresa=empresa, setor=setor, nome=nome,
            defaults={
                "codigo": (dados.get("codigo") or "")[:40],
                "nivel_inicial": (dados.get("nivel_inicial") or "junior")[:40],
                "ativo": True,
            }
        )
        if not created and not cargo.ativo:
            cargo.ativo = True
            cargo.save(update_fields=["ativo"])
        return JsonResponse({"id": cargo.id, "nome": cargo.nome, "created": created})

    if request.method == "DELETE":
        EmpresaCargoCorporativo.objects.filter(id=request.GET.get("id"), empresa=empresa).update(ativo=False)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── FUNÇÕES CRÍTICAS ──────────────────────────────────────────────────────────

@csrf_exempt
def api_funcoes_criticas(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = FuncaoCriticaCorporativa.objects.filter(empresa=empresa, ativo=True).select_related("cargo", "setor")
        return JsonResponse({"funcoes": [
            {"id": f.id, "nome": f.nome, "descricao": f.descricao, "criticidade": f.criticidade,
             "cargo_id": f.cargo_id, "cargo_nome": f.cargo.nome if f.cargo else None,
             "setor_id": f.setor_id, "setor_nome": f.setor.nome if f.setor else None}
            for f in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatorio"}, status=400)
        cargo = EmpresaCargoCorporativo.objects.filter(id=dados.get("cargo_id"), empresa=empresa, ativo=True).first() if dados.get("cargo_id") else None
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None
        try:
            crit = max(1, min(5, int(dados.get("criticidade") or 3)))
        except (TypeError, ValueError):
            crit = 3
        funcao, created = FuncaoCriticaCorporativa.objects.get_or_create(
            empresa=empresa, cargo=cargo, nome=nome,
            defaults={"descricao": (dados.get("descricao") or "").strip(), "criticidade": crit, "setor": setor, "ativo": True}
        )
        if not created and not funcao.ativo:
            funcao.ativo = True
            funcao.save(update_fields=["ativo"])
        return JsonResponse({"id": funcao.id, "nome": funcao.nome, "created": created})

    if request.method == "DELETE":
        FuncaoCriticaCorporativa.objects.filter(id=request.GET.get("id"), empresa=empresa).update(ativo=False)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── EQUIPAMENTOS ──────────────────────────────────────────────────────────────

@csrf_exempt
def api_equipamentos(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = EquipamentoCorporativo.objects.filter(empresa=empresa, ativo=True).select_related("setor")
        return JsonResponse({"equipamentos": [
            {"id": e.id, "nome": e.nome, "codigo": e.codigo, "categoria": e.categoria,
             "criticidade": e.criticidade, "setor_id": e.setor_id, "setor_nome": e.setor.nome if e.setor else None}
            for e in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatorio"}, status=400)
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None
        try:
            crit = max(1, min(5, int(dados.get("criticidade") or 3)))
        except (TypeError, ValueError):
            crit = 3
        equip, created = EquipamentoCorporativo.objects.get_or_create(
            empresa=empresa, setor=setor, nome=nome,
            defaults={"codigo": (dados.get("codigo") or "")[:60], "categoria": (dados.get("categoria") or "")[:80], "criticidade": crit, "ativo": True}
        )
        if not created and not equip.ativo:
            equip.ativo = True
            equip.save(update_fields=["ativo"])
        return JsonResponse({"id": equip.id, "nome": equip.nome, "created": created})

    if request.method == "DELETE":
        EquipamentoCorporativo.objects.filter(id=request.GET.get("id"), empresa=empresa).update(ativo=False)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── TRILHAS ───────────────────────────────────────────────────────────────────

@csrf_exempt
def api_trilhas(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = TrilhaCompetenciaCorporativa.objects.filter(empresa=empresa, ativo=True).select_related("cargo", "funcao_critica")
        return JsonResponse({"trilhas": [
            {"id": t.id, "titulo": t.titulo, "descricao": t.descricao, "nivel_alvo": t.nivel_alvo,
             "ordem": t.ordem, "cargo_id": t.cargo_id, "cargo_nome": t.cargo.nome if t.cargo else None,
             "funcao_critica_id": t.funcao_critica_id,
             "funcao_critica_nome": t.funcao_critica.nome if t.funcao_critica else None,
             "total_itens": CompetenciaItemCorporativo.objects.filter(trilha=t, ativo=True).count()}
            for t in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        titulo = (dados.get("titulo") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)
        cargo = EmpresaCargoCorporativo.objects.filter(id=dados.get("cargo_id"), empresa=empresa, ativo=True).first() if dados.get("cargo_id") else None
        funcao = FuncaoCriticaCorporativa.objects.filter(id=dados.get("funcao_critica_id"), empresa=empresa, ativo=True).first() if dados.get("funcao_critica_id") else None
        try:
            ordem = int(dados.get("ordem") or 1)
        except (TypeError, ValueError):
            ordem = 1
        trilha, created = TrilhaCompetenciaCorporativa.objects.get_or_create(
            empresa=empresa, cargo=cargo, titulo=titulo,
            defaults={"descricao": (dados.get("descricao") or "").strip(),
                      "nivel_alvo": (dados.get("nivel_alvo") or "")[:40],
                      "ordem": ordem, "funcao_critica": funcao, "ativo": True}
        )
        if not created and not trilha.ativo:
            trilha.ativo = True
            trilha.save(update_fields=["ativo"])
        return JsonResponse({"id": trilha.id, "titulo": trilha.titulo, "created": created})

    if request.method == "DELETE":
        TrilhaCompetenciaCorporativa.objects.filter(id=request.GET.get("id"), empresa=empresa).update(ativo=False)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── ITENS DE TRILHA ───────────────────────────────────────────────────────────

@csrf_exempt
def api_itens(request, trilha_id):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    trilha = TrilhaCompetenciaCorporativa.objects.filter(id=trilha_id, empresa=empresa).first()
    if not trilha:
        return JsonResponse({"erro": "trilha nao encontrada"}, status=404)

    if request.method == "GET":
        qs = CompetenciaItemCorporativo.objects.filter(trilha=trilha, ativo=True).select_related("equipamento")
        return JsonResponse({"itens": [
            {"id": i.id, "titulo": i.titulo, "tipo": i.tipo, "descricao": i.descricao,
             "ordem": i.ordem, "peso": i.peso, "obrigatorio": i.obrigatorio,
             "equipamento_id": i.equipamento_id, "equipamento_nome": i.equipamento.nome if i.equipamento else None}
            for i in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        titulo = (dados.get("titulo") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)
        tipo = dados.get("tipo") or CompetenciaItemCorporativo.TIPO_CONHECIMENTO
        if tipo not in dict(CompetenciaItemCorporativo.TIPOS_ITEM):
            tipo = CompetenciaItemCorporativo.TIPO_CONHECIMENTO
        equip = EquipamentoCorporativo.objects.filter(id=dados.get("equipamento_id"), empresa=empresa, ativo=True).first() if dados.get("equipamento_id") else None
        try:
            peso = max(1, int(dados.get("peso") or 1))
            ordem = int(dados.get("ordem") or 1)
        except (TypeError, ValueError):
            peso, ordem = 1, 1
        item, created = CompetenciaItemCorporativo.objects.get_or_create(
            trilha=trilha, titulo=titulo,
            defaults={"empresa": empresa, "tipo": tipo, "descricao": (dados.get("descricao") or "").strip(),
                      "ordem": ordem, "peso": peso, "obrigatorio": bool(dados.get("obrigatorio", True)),
                      "equipamento": equip, "ativo": True}
        )
        if not created and not item.ativo:
            item.ativo = True
            item.save(update_fields=["ativo"])
        return JsonResponse({"id": item.id, "titulo": item.titulo, "created": created})

    if request.method == "DELETE":
        CompetenciaItemCorporativo.objects.filter(id=request.GET.get("id"), trilha=trilha).update(ativo=False)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── EVIDÊNCIAS (visão institucional) ─────────────────────────────────────────

def api_evidencias(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "GET":
        return JsonResponse({"erro": "metodo nao permitido"}, status=405)

    status_filter = request.GET.get("status")
    qs = (
        EvidenciaCompetenciaCorporativa.objects.filter(empresa=empresa)
        .select_related("alias", "item__trilha__cargo", "unidade", "setor")
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    qs = qs.order_by("-criado_em")[:120]

    resultado = []
    validacoes = {
        v.evidencia_id: v
        for v in ValidacaoCompetenciaCorporativa.objects.filter(evidencia__in=qs)
    }
    for e in qs:
        v = validacoes.get(e.id)
        resultado.append({
            "id": e.id,
            "alias": e.alias.alias_publico,
            "item_id": e.item_id,
            "item_titulo": e.item.titulo,
            "item_tipo": e.item.tipo,
            "trilha_titulo": e.item.trilha.titulo,
            "cargo_nome": e.item.trilha.cargo.nome if e.item.trilha.cargo else None,
            "unidade_nome": e.unidade.nome if e.unidade else None,
            "setor_nome": e.setor.nome if e.setor else None,
            "titulo": e.titulo,
            "descricao": e.descricao,
            "status": e.status,
            "pontuacao_autodeclarada": e.pontuacao_autodeclarada,
            "criado_em": e.criado_em.isoformat(),
            "validacao": {
                "resultado": v.resultado,
                "pontuacao_validador": v.pontuacao_validador,
                "comentario": v.comentario,
                "validado_em": v.validado_em.isoformat() if v.validado_em else None,
            } if v else None,
        })

    return JsonResponse({"evidencias": resultado})


# ── EVIDÊNCIA PELO COLABORADOR (alias-based) ──────────────────────────────────

@csrf_exempt
def api_evidencia_colaborador(request, codigo):
    try:
        empresa = _resolver_empresa_por_codigo(codigo)
    except ValueError:
        return JsonResponse({"erro": "codigo invalido"}, status=404)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    alias_code = (dados.get("alias_code") or "").strip()
    item_id = dados.get("item_id")
    if not alias_code:
        return JsonResponse({"erro": "alias_code obrigatorio"}, status=400)
    if not item_id:
        return JsonResponse({"erro": "item_id obrigatorio"}, status=400)

    alias = ColaboradorAliasCorporativo.objects.filter(empresa=empresa, alias_publico=alias_code).first()
    if not alias:
        return JsonResponse({"erro": "alias nao encontrado"}, status=404)

    item = CompetenciaItemCorporativo.objects.filter(id=item_id, empresa=empresa, ativo=True).first()
    if not item:
        return JsonResponse({"erro": "item nao encontrado"}, status=404)

    try:
        pontuacao = max(1, min(5, int(dados.get("pontuacao_autodeclarada") or dados.get("pontuacao") or 3)))
    except (TypeError, ValueError):
        pontuacao = 3

    # Não duplica: se já existe evidência pendente/enviada para este item+alias, atualiza
    evidencia_existente = EvidenciaCompetenciaCorporativa.objects.filter(
        empresa=empresa, alias=alias, item=item,
    ).exclude(status=EvidenciaCompetenciaCorporativa.STATUS_VALIDADA).first()

    if evidencia_existente:
        evidencia_existente.descricao = (dados.get("descricao") or "").strip()
        evidencia_existente.titulo = (dados.get("titulo") or "").strip()[:160]
        evidencia_existente.pontuacao_autodeclarada = pontuacao
        evidencia_existente.status = EvidenciaCompetenciaCorporativa.STATUS_ENVIADA
        evidencia_existente.save(update_fields=["descricao", "titulo", "pontuacao_autodeclarada", "status", "atualizado_em"])
        evidencia = evidencia_existente
        ValidacaoCompetenciaCorporativa.objects.filter(evidencia=evidencia).update(
            resultado=ValidacaoCompetenciaCorporativa.RESULTADO_PENDENTE
        )
    else:
        evidencia = EvidenciaCompetenciaCorporativa.objects.create(
            empresa=empresa, alias=alias, item=item,
            unidade=alias.unidade, setor=alias.setor,
            titulo=(dados.get("titulo") or "").strip()[:160],
            descricao=(dados.get("descricao") or "").strip(),
            status=EvidenciaCompetenciaCorporativa.STATUS_ENVIADA,
            pontuacao_autodeclarada=pontuacao,
        )
        ValidacaoCompetenciaCorporativa.objects.create(
            empresa=empresa, evidencia=evidencia,
            resultado=ValidacaoCompetenciaCorporativa.RESULTADO_PENDENTE,
        )

    return JsonResponse({"id": evidencia.id, "status": evidencia.status})


# ── VALIDAÇÃO POR SUPERVISOR ──────────────────────────────────────────────────

@csrf_exempt
def api_validar(request, evidencia_id):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    resultado = dados.get("resultado")
    if resultado not in (ValidacaoCompetenciaCorporativa.RESULTADO_APROVADA, ValidacaoCompetenciaCorporativa.RESULTADO_REPROVADA):
        return JsonResponse({"erro": "resultado invalido: use aprovada ou reprovada"}, status=400)

    evidencia = EvidenciaCompetenciaCorporativa.objects.filter(id=evidencia_id, empresa=empresa).first()
    if not evidencia:
        return JsonResponse({"erro": "evidencia nao encontrada"}, status=404)

    validacao, _ = ValidacaoCompetenciaCorporativa.objects.get_or_create(
        evidencia=evidencia, defaults={"empresa": empresa}
    )
    try:
        pontuacao = max(0, min(5, int(dados.get("pontuacao") or 0)))
    except (TypeError, ValueError):
        pontuacao = 0

    validacao.resultado = resultado
    validacao.pontuacao_validador = pontuacao
    validacao.comentario = (dados.get("comentario") or "").strip()[:500]
    validacao.validado_em = timezone.now()
    validacao.save(update_fields=["resultado", "pontuacao_validador", "comentario", "validado_em", "atualizado_em"])

    novo_status = (
        EvidenciaCompetenciaCorporativa.STATUS_VALIDADA
        if resultado == ValidacaoCompetenciaCorporativa.RESULTADO_APROVADA
        else EvidenciaCompetenciaCorporativa.STATUS_REVISAR
    )
    evidencia.status = novo_status
    evidencia.save(update_fields=["status", "atualizado_em"])

    return JsonResponse({"ok": True, "resultado": resultado, "evidencia_status": novo_status})


# ── PRONTIDÃO TÉCNICA ─────────────────────────────────────────────────────────

def api_prontidao(request):
    empresa = _empresa_competencia(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "GET":
        return JsonResponse({"erro": "metodo nao permitido"}, status=405)

    total_trilhas = TrilhaCompetenciaCorporativa.objects.filter(empresa=empresa, ativo=True).count()
    total_itens = CompetenciaItemCorporativo.objects.filter(empresa=empresa, ativo=True).count()
    total_ev = EvidenciaCompetenciaCorporativa.objects.filter(empresa=empresa).count()
    aprovadas = EvidenciaCompetenciaCorporativa.objects.filter(
        empresa=empresa, status=EvidenciaCompetenciaCorporativa.STATUS_VALIDADA
    ).count()
    pendentes = ValidacaoCompetenciaCorporativa.objects.filter(
        empresa=empresa, resultado=ValidacaoCompetenciaCorporativa.RESULTADO_PENDENTE
    ).count()
    readiness = round((aprovadas / max(1, total_ev)) * 100) if total_ev else 0

    por_cargo = list(
        EvidenciaCompetenciaCorporativa.objects.filter(empresa=empresa)
        .values("item__trilha__cargo__nome")
        .annotate(
            total=Count("id"),
            aprovadas=Count("id", filter=Q(status=EvidenciaCompetenciaCorporativa.STATUS_VALIDADA)),
        )
        .order_by("-total")[:12]
    )

    por_unidade = list(
        EvidenciaCompetenciaCorporativa.objects.filter(empresa=empresa, unidade__isnull=False)
        .values("unidade__nome")
        .annotate(
            total=Count("id"),
            aprovadas=Count("id", filter=Q(status=EvidenciaCompetenciaCorporativa.STATUS_VALIDADA)),
        )
        .order_by("-total")[:12]
    )

    return JsonResponse({
        "summary": {
            "trilhas": total_trilhas,
            "itens": total_itens,
            "evidencias": total_ev,
            "aprovadas": aprovadas,
            "pendentes_validacao": pendentes,
            "readiness": readiness,
        },
        "por_cargo": [
            {"cargo": r["item__trilha__cargo__nome"] or "Sem cargo",
             "total": r["total"], "aprovadas": r["aprovadas"],
             "readiness": round((r["aprovadas"] / max(1, r["total"])) * 100)}
            for r in por_cargo
        ],
        "por_unidade": [
            {"unidade": r["unidade__nome"], "total": r["total"], "aprovadas": r["aprovadas"],
             "readiness": round((r["aprovadas"] / max(1, r["total"])) * 100)}
            for r in por_unidade
        ],
    })
