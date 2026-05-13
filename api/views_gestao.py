import json

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    AcaoCorporativa,
    EmpresaSetor,
    EmpresaUnidade,
    PedidoApoioCorporativo,
    ProgramaCorporativo,
)
from .access_control import api_requer_setor, requer_setor
from .views_dashboard import _empresa_autenticada, _setor_conta


def _empresa_gestao(request):
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


@requer_setor("empresa")
def gestao_corporativa(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return redirect("/")
    return render(request, "gestao_corporativa.html", {"empresa_nome": empresa.nome})


# ── APOIO ─────────────────────────────────────────────────────────────────────

@api_requer_setor("empresa")
def api_apoio_fila(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    status_filter = request.GET.get("status")
    qs = PedidoApoioCorporativo.objects.filter(empresa=empresa).select_related(
        "alias", "unidade", "setor", "turno"
    )
    if not status_filter:
        qs = qs.filter(status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE])
    elif status_filter != "todos":
        qs = qs.filter(status=status_filter)
    qs = qs.order_by("-criado_em")[:100]

    return JsonResponse({"pedidos": [
        {
            "id": p.id,
            "alias": p.alias.alias_publico,
            "unidade_nome": p.unidade.nome if p.unidade else None,
            "setor_nome": p.setor.nome if p.setor else None,
            "turno_nome": p.turno.nome if p.turno else None,
            "deseja_contato": p.deseja_contato,
            "canal_preferido": p.canal_preferido,
            "relato": p.relato,
            "status": p.status,
            "atendente": p.atendente,
            "resolucao": p.resolucao,
            "criado_em": p.criado_em.isoformat(),
            "concluido_em": p.concluido_em.isoformat() if p.concluido_em else None,
        }
        for p in qs
    ]})


@csrf_exempt
@api_requer_setor("empresa")
def api_apoio_atualizar(request, pedido_id):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    pedido = PedidoApoioCorporativo.objects.filter(id=pedido_id, empresa=empresa).first()
    if not pedido:
        return JsonResponse({"erro": "pedido nao encontrado"}, status=404)

    status_validos = [s[0] for s in PedidoApoioCorporativo.STATUS_CHOICES]
    novo_status = dados.get("status")
    if novo_status and novo_status not in status_validos:
        return JsonResponse({"erro": "status invalido"}, status=400)

    campos = []
    if novo_status:
        pedido.status = novo_status
        campos.append("status")
    if "atendente" in dados:
        pedido.atendente = (dados["atendente"] or "")[:160]
        campos.append("atendente")
    if "resolucao" in dados:
        pedido.resolucao = (dados["resolucao"] or "")
        campos.append("resolucao")

    if novo_status == PedidoApoioCorporativo.STATUS_CONCLUIDO and not pedido.concluido_em:
        pedido.concluido_em = timezone.now()
        campos.append("concluido_em")

    if campos:
        campos.append("atualizado_em")
        pedido.save(update_fields=campos)

    return JsonResponse({"ok": True, "status": pedido.status})


# ── PROGRAMAS ─────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("empresa")
def api_programas(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        status_filter = request.GET.get("status")
        qs = ProgramaCorporativo.objects.filter(empresa=empresa).select_related("unidade", "setor")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return JsonResponse({"programas": [
            {
                "id": p.id,
                "titulo": p.titulo,
                "tipo": p.tipo,
                "status": p.status,
                "owner": p.owner,
                "objetivo": p.objetivo,
                "unidade_nome": p.unidade.nome if p.unidade else None,
                "setor_nome": p.setor.nome if p.setor else None,
                "prazo": p.prazo.isoformat() if p.prazo else None,
                "resultado": p.resultado,
                "criado_em": p.criado_em.isoformat(),
                "encerrado_em": p.encerrado_em.isoformat() if p.encerrado_em else None,
                "total_acoes": p.acoes.filter(status__in=[
                    AcaoCorporativa.STATUS_ABERTA, AcaoCorporativa.STATUS_EM_ANDAMENTO
                ]).count(),
            }
            for p in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        titulo = (dados.get("titulo") or "").strip()
        owner = (dados.get("owner") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)
        if not owner:
            return JsonResponse({"erro": "owner obrigatorio"}, status=400)

        tipo = dados.get("tipo") or ProgramaCorporativo.TIPO_LIVRE
        if tipo not in dict(ProgramaCorporativo.TIPOS):
            tipo = ProgramaCorporativo.TIPO_LIVRE

        unidade = EmpresaUnidade.objects.filter(id=dados.get("unidade_id"), empresa=empresa).first() if dados.get("unidade_id") else None
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None

        prazo = None
        if dados.get("prazo"):
            try:
                from datetime import date
                prazo = date.fromisoformat(dados["prazo"])
            except (ValueError, TypeError):
                pass

        programa = ProgramaCorporativo.objects.create(
            empresa=empresa,
            titulo=titulo,
            tipo=tipo,
            owner=owner,
            objetivo=(dados.get("objetivo") or "").strip(),
            unidade=unidade,
            setor=setor,
            prazo=prazo,
            status=ProgramaCorporativo.STATUS_RASCUNHO,
        )
        return JsonResponse({"id": programa.id, "titulo": programa.titulo})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


@csrf_exempt
@api_requer_setor("empresa")
def api_programa_status(request, programa_id):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    programa = ProgramaCorporativo.objects.filter(id=programa_id, empresa=empresa).first()
    if not programa:
        return JsonResponse({"erro": "programa nao encontrado"}, status=404)

    novo_status = dados.get("status")
    status_validos = [s[0] for s in ProgramaCorporativo.STATUS_CHOICES]
    if novo_status not in status_validos:
        return JsonResponse({"erro": "status invalido"}, status=400)

    campos = ["status", "atualizado_em"]
    programa.status = novo_status

    if novo_status == ProgramaCorporativo.STATUS_ENCERRADO:
        programa.encerrado_em = timezone.now()
        programa.resultado = (dados.get("resultado") or "").strip()
        campos += ["encerrado_em", "resultado"]

    programa.save(update_fields=campos)
    return JsonResponse({"ok": True, "status": programa.status})


# ── AÇÕES ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("empresa")
def api_acoes(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        status_filter = request.GET.get("status")
        qs = AcaoCorporativa.objects.filter(empresa=empresa).select_related(
            "unidade", "setor", "programa", "pedido_apoio"
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            qs = qs.exclude(status__in=[AcaoCorporativa.STATUS_CONCLUIDA, AcaoCorporativa.STATUS_CANCELADA])
        return JsonResponse({"acoes": [
            {
                "id": a.id,
                "titulo": a.titulo,
                "descricao": a.descricao,
                "status": a.status,
                "origem": a.origem,
                "owner": a.owner,
                "unidade_nome": a.unidade.nome if a.unidade else None,
                "setor_nome": a.setor.nome if a.setor else None,
                "prazo": a.prazo.isoformat() if a.prazo else None,
                "evidencia": a.evidencia,
                "programa_titulo": a.programa.titulo if a.programa else None,
                "criado_em": a.criado_em.isoformat(),
                "concluido_em": a.concluido_em.isoformat() if a.concluido_em else None,
            }
            for a in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        titulo = (dados.get("titulo") or "").strip()
        owner = (dados.get("owner") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)
        if not owner:
            return JsonResponse({"erro": "owner obrigatorio"}, status=400)

        origem = dados.get("origem") or AcaoCorporativa.ORIGEM_MANUAL
        if origem not in dict(AcaoCorporativa.ORIGENS):
            origem = AcaoCorporativa.ORIGEM_MANUAL

        unidade = EmpresaUnidade.objects.filter(id=dados.get("unidade_id"), empresa=empresa).first() if dados.get("unidade_id") else None
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None
        programa = ProgramaCorporativo.objects.filter(id=dados.get("programa_id"), empresa=empresa).first() if dados.get("programa_id") else None

        prazo = None
        if dados.get("prazo"):
            try:
                from datetime import date
                prazo = date.fromisoformat(dados["prazo"])
            except (ValueError, TypeError):
                pass

        acao = AcaoCorporativa.objects.create(
            empresa=empresa,
            titulo=titulo,
            descricao=(dados.get("descricao") or "").strip(),
            owner=owner,
            origem=origem,
            unidade=unidade,
            setor=setor,
            prazo=prazo,
            programa=programa,
            status=AcaoCorporativa.STATUS_ABERTA,
        )
        return JsonResponse({"id": acao.id, "titulo": acao.titulo})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


@csrf_exempt
@api_requer_setor("empresa")
def api_acao_status(request, acao_id):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    acao = AcaoCorporativa.objects.filter(id=acao_id, empresa=empresa).first()
    if not acao:
        return JsonResponse({"erro": "acao nao encontrada"}, status=404)

    novo_status = dados.get("status")
    status_validos = [s[0] for s in AcaoCorporativa.STATUS_CHOICES]
    if novo_status not in status_validos:
        return JsonResponse({"erro": "status invalido"}, status=400)

    campos = ["status", "atualizado_em"]
    acao.status = novo_status

    if "evidencia" in dados:
        acao.evidencia = (dados["evidencia"] or "").strip()
        campos.append("evidencia")

    if novo_status == AcaoCorporativa.STATUS_CONCLUIDA and not acao.concluido_em:
        acao.concluido_em = timezone.now()
        campos.append("concluido_em")

    acao.save(update_fields=campos)
    return JsonResponse({"ok": True, "status": acao.status})


# ── RESUMO DA FILA (para o dashboard) ────────────────────────────────────────

@api_requer_setor("empresa")
def api_gestao_resumo(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    apoio_aberto = PedidoApoioCorporativo.objects.filter(
        empresa=empresa,
        status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE]
    ).count()

    acoes_abertas = AcaoCorporativa.objects.filter(
        empresa=empresa,
        status__in=[AcaoCorporativa.STATUS_ABERTA, AcaoCorporativa.STATUS_EM_ANDAMENTO]
    ).count()

    programas_ativos = ProgramaCorporativo.objects.filter(
        empresa=empresa, status=ProgramaCorporativo.STATUS_ATIVO
    ).count()

    return JsonResponse({
        "apoio_aberto": apoio_aberto,
        "acoes_abertas": acoes_abertas,
        "programas_ativos": programas_ativos,
        "total_atencao": apoio_aberto + acoes_abertas,
    })
