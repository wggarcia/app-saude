import json
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    ColaboradorAliasCorporativo,
    ColaboradorEscalaCorporativa,
    EmpresaUnidade,
    EscalaCorporativa,
)
from .views_dashboard import _empresa_autenticada, _setor_conta


def _empresa_escalas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    if _setor_conta(empresa) != "empresa":
        return None
    return empresa


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _fase_atual(colaborador_escala):
    hoje = date.today()
    inicio = colaborador_escala.inicio_ciclo
    escala = colaborador_escala.escala
    dias_ciclo = escala.dias_embarcado + escala.dias_folga
    if dias_ciclo == 0:
        return ColaboradorEscalaCorporativa.FASE_EMBARCADO
    dias_passados = (hoje - inicio).days % dias_ciclo
    return (
        ColaboradorEscalaCorporativa.FASE_EMBARCADO
        if dias_passados < escala.dias_embarcado
        else ColaboradorEscalaCorporativa.FASE_FOLGA
    )


def escalas_corporativa(request):
    empresa = _empresa_escalas(request)
    if not empresa:
        return redirect("/")
    return render(request, "escalas_corporativa.html", {"empresa_nome": empresa.nome})


# ── DEFINIÇÕES DE ESCALA ───────────────────────────────────────────────────────

@csrf_exempt
def api_escalas(request):
    empresa = _empresa_escalas(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = EscalaCorporativa.objects.filter(empresa=empresa, ativo=True).select_related("unidade")
        return JsonResponse({"escalas": [
            {
                "id": e.id,
                "nome": e.nome,
                "tipo": e.tipo,
                "dias_embarcado": e.dias_embarcado,
                "dias_folga": e.dias_folga,
                "descricao": e.descricao,
                "unidade_nome": e.unidade.nome if e.unidade else None,
                "total_colaboradores": e.colaboradores.filter(ativo=True).count(),
            }
            for e in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatorio"}, status=400)
        tipo = dados.get("tipo") or EscalaCorporativa.TIPO_14x14
        if tipo not in dict(EscalaCorporativa.TIPOS):
            tipo = EscalaCorporativa.TIPO_14x14
        dias_e = max(1, int(dados.get("dias_embarcado") or 14))
        dias_f = max(1, int(dados.get("dias_folga") or 14))
        unidade = EmpresaUnidade.objects.filter(id=dados.get("unidade_id"), empresa=empresa).first() if dados.get("unidade_id") else None
        escala = EscalaCorporativa.objects.create(
            empresa=empresa,
            nome=nome,
            tipo=tipo,
            dias_embarcado=dias_e,
            dias_folga=dias_f,
            descricao=(dados.get("descricao") or "").strip(),
            unidade=unidade,
        )
        return JsonResponse({"id": escala.id, "nome": escala.nome})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


@csrf_exempt
def api_escala_detalhe(request, escala_id):
    empresa = _empresa_escalas(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    escala = EscalaCorporativa.objects.filter(id=escala_id, empresa=empresa).first()
    if not escala:
        return JsonResponse({"erro": "escala nao encontrada"}, status=404)

    if request.method == "DELETE":
        escala.ativo = False
        escala.save(update_fields=["ativo", "atualizado_em"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── CICLO ATUAL ────────────────────────────────────────────────────────────────

def api_escala_ciclo(request, escala_id):
    empresa = _empresa_escalas(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    escala = EscalaCorporativa.objects.filter(id=escala_id, empresa=empresa).first()
    if not escala:
        return JsonResponse({"erro": "escala nao encontrada"}, status=404)

    atribuicoes = ColaboradorEscalaCorporativa.objects.filter(
        escala=escala, ativo=True
    ).select_related("alias", "alias__unidade", "alias__setor")

    embarcados, em_folga = [], []
    for a in atribuicoes:
        fase = _fase_atual(a)
        item = {
            "alias": a.alias.alias_publico,
            "unidade": a.alias.unidade.nome if a.alias.unidade else None,
            "setor": a.alias.setor.nome if a.alias.setor else None,
            "inicio_ciclo": a.inicio_ciclo.isoformat(),
            "fase": fase,
        }
        (embarcados if fase == ColaboradorEscalaCorporativa.FASE_EMBARCADO else em_folga).append(item)

    return JsonResponse({
        "escala": {"id": escala.id, "nome": escala.nome, "tipo": escala.tipo,
                   "dias_embarcado": escala.dias_embarcado, "dias_folga": escala.dias_folga},
        "hoje": date.today().isoformat(),
        "embarcados": embarcados,
        "em_folga": em_folga,
        "total_embarcados": len(embarcados),
        "total_folga": len(em_folga),
    })


# ── ATRIBUIÇÕES ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_escala_atribuicoes(request, escala_id):
    empresa = _empresa_escalas(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    escala = EscalaCorporativa.objects.filter(id=escala_id, empresa=empresa).first()
    if not escala:
        return JsonResponse({"erro": "escala nao encontrada"}, status=404)

    if request.method == "GET":
        qs = ColaboradorEscalaCorporativa.objects.filter(escala=escala, ativo=True).select_related("alias")
        return JsonResponse({"atribuicoes": [
            {
                "id": a.id,
                "alias": a.alias.alias_publico,
                "inicio_ciclo": a.inicio_ciclo.isoformat(),
                "fase_atual": _fase_atual(a),
            }
            for a in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        alias_code = (dados.get("alias_code") or "").strip()
        inicio_str = (dados.get("inicio_ciclo") or "").strip()
        if not alias_code:
            return JsonResponse({"erro": "alias_code obrigatorio"}, status=400)
        try:
            inicio = date.fromisoformat(inicio_str) if inicio_str else date.today()
        except ValueError:
            inicio = date.today()
        alias = ColaboradorAliasCorporativo.objects.filter(empresa=empresa, alias_publico=alias_code).first()
        if not alias:
            return JsonResponse({"erro": "alias nao encontrado"}, status=404)
        atr, created = ColaboradorEscalaCorporativa.objects.get_or_create(
            alias=alias, escala=escala,
            defaults={"empresa": empresa, "inicio_ciclo": inicio},
        )
        if not created:
            atr.inicio_ciclo = inicio
            atr.ativo = True
            atr.save(update_fields=["inicio_ciclo", "ativo", "atualizado_em"])
        return JsonResponse({"id": atr.id, "created": created})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


# ── RESUMO GERAL ───────────────────────────────────────────────────────────────

def api_escalas_resumo(request):
    empresa = _empresa_escalas(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    escalas = EscalaCorporativa.objects.filter(empresa=empresa, ativo=True)
    total_embarcados = 0
    total_folga = 0
    for escala in escalas:
        for a in ColaboradorEscalaCorporativa.objects.filter(escala=escala, ativo=True):
            if _fase_atual(a) == ColaboradorEscalaCorporativa.FASE_EMBARCADO:
                total_embarcados += 1
            else:
                total_folga += 1

    return JsonResponse({
        "total_escalas": escalas.count(),
        "total_embarcados": total_embarcados,
        "total_folga": total_folga,
        "hoje": date.today().isoformat(),
    })
