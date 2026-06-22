import json
from datetime import date

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import PlanoAcaoSST, RiscoOcupacional
from .views_dashboard import _empresa_autenticada


def _json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _risco_to_dict(risco):
    return {
        "id": risco.id,
        "setor": risco.setor,
        "tipo_risco": risco.tipo_risco,
        "tipo_risco_label": risco.get_tipo_risco_display(),
        "agente": risco.agente,
        "descricao": risco.descricao,
        "nivel": risco.nivel,
        "probabilidade": risco.probabilidade,
        "severidade": risco.severidade,
        "grr": risco.grr,
        "nr_referencia": risco.nr_referencia,
        "medida_controle_existente": risco.medida_controle_existente,
        "medida_controle_proposta": risco.medida_controle_proposta,
        "prazo": str(risco.prazo) if risco.prazo else None,
        "responsavel": risco.responsavel,
        "status": risco.status,
        "status_label": risco.get_status_display(),
        "criado_em": risco.criado_em.strftime("%d/%m/%Y"),
        "atualizado_em": risco.atualizado_em.strftime("%d/%m/%Y"),
        "planos_count": risco.planos_acao.count(),
    }


def _plano_to_dict(plano):
    hoje = date.today()
    atrasado = (
        plano.status not in ("concluido", "cancelado")
        and plano.data_prazo is not None
        and plano.data_prazo < hoje
    )
    return {
        "id": plano.id,
        "titulo": plano.titulo,
        "descricao": plano.descricao,
        "origem": plano.origem,
        "origem_label": plano.get_origem_display(),
        "prioridade": plano.prioridade,
        "prioridade_label": plano.get_prioridade_display(),
        "responsavel": plano.responsavel,
        "setor": plano.setor,
        "data_prazo": str(plano.data_prazo) if plano.data_prazo else None,
        "data_conclusao": str(plano.data_conclusao) if plano.data_conclusao else None,
        "status": plano.status,
        "status_label": plano.get_status_display(),
        "observacoes": plano.observacoes,
        "atrasado": atrasado,
        "dias_prazo": (plano.data_prazo - hoje).days if plano.data_prazo else None,
        "risco_id": plano.risco_id,
        "criado_em": plano.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
def api_riscos_ocupacionais(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    if request.method == "GET":
        riscos = RiscoOcupacional.objects.filter(empresa=empresa)
        tipo_risco = request.GET.get("tipo_risco")
        nivel = request.GET.get("nivel")
        status = request.GET.get("status")
        setor = request.GET.get("setor")

        if tipo_risco:
            riscos = riscos.filter(tipo_risco=tipo_risco)
        if nivel:
            riscos = riscos.filter(nivel=nivel)
        if status:
            riscos = riscos.filter(status=status)
        if setor:
            riscos = riscos.filter(setor__icontains=setor)

        return JsonResponse({"riscos": [_risco_to_dict(risco) for risco in riscos]})

    if request.method == "POST":
        data = _json_body(request)
        if not data.get("agente"):
            return JsonResponse({"erro": "agente obrigatorio"}, status=400)
        if not data.get("setor"):
            return JsonResponse({"erro": "setor obrigatorio"}, status=400)

        risco = RiscoOcupacional.objects.create(
            empresa=empresa,
            setor=data["setor"],
            tipo_risco=data.get("tipo_risco", "fisico"),
            agente=data["agente"],
            descricao=data.get("descricao", ""),
            nivel=data.get("nivel", "III"),
            probabilidade=int(data.get("probabilidade", 3)),
            severidade=int(data.get("severidade", 3)),
            nr_referencia=data.get("nr_referencia", ""),
            medida_controle_existente=data.get("medida_controle_existente", ""),
            medida_controle_proposta=data.get("medida_controle_proposta", ""),
            prazo=data.get("prazo") or None,
            responsavel=data.get("responsavel", ""),
            status=data.get("status", "identificado"),
        )
        return JsonResponse({"risco": _risco_to_dict(risco)}, status=201)

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


@csrf_exempt
def api_risco_detalhe(request, risco_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    try:
        risco = RiscoOcupacional.objects.get(id=risco_id, empresa=empresa)
    except RiscoOcupacional.DoesNotExist:
        return JsonResponse({"erro": "Risco nao encontrado"}, status=404)

    if request.method == "GET":
        data = _risco_to_dict(risco)
        data["planos"] = [_plano_to_dict(plano) for plano in risco.planos_acao.all()]
        return JsonResponse({"risco": data})

    if request.method in ("PUT", "PATCH"):
        data = _json_body(request)
        campos = [
            "setor",
            "tipo_risco",
            "agente",
            "descricao",
            "nivel",
            "nr_referencia",
            "medida_controle_existente",
            "medida_controle_proposta",
            "responsavel",
            "status",
        ]
        for campo in campos:
            if campo in data:
                setattr(risco, campo, data[campo])
        if "probabilidade" in data:
            risco.probabilidade = int(data["probabilidade"])
        if "severidade" in data:
            risco.severidade = int(data["severidade"])
        if "prazo" in data:
            risco.prazo = data["prazo"] or None
        risco.save()
        return JsonResponse({"risco": _risco_to_dict(risco)})

    if request.method == "DELETE":
        risco.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


def api_riscos_kpis(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    riscos = RiscoOcupacional.objects.filter(empresa=empresa)
    hoje = date.today()
    planos = PlanoAcaoSST.objects.filter(empresa=empresa)
    planos_abertos = planos.filter(status__in=["aberto", "em_andamento"])

    por_tipo = {}
    por_nivel = {}
    for risco in riscos:
        por_tipo[risco.get_tipo_risco_display()] = por_tipo.get(risco.get_tipo_risco_display(), 0) + 1
        por_nivel[risco.nivel] = por_nivel.get(risco.nivel, 0) + 1

    return JsonResponse({
        "kpis": {
            "total_riscos": riscos.count(),
            "criticos": riscos.filter(nivel__in=["IV", "V"]).count(),
            "controlados": riscos.filter(status="controlado").count(),
            "pendentes": riscos.filter(status="identificado").count(),
            "prazos_vencidos": riscos.filter(status__in=["identificado", "em_controle"], prazo__lt=hoje).count(),
            "planos_abertos": planos_abertos.count(),
            "planos_atrasados": planos_abertos.filter(data_prazo__lt=hoje).count(),
            "planos_concluidos": planos.filter(status="concluido").count(),
        },
        "por_tipo": [{"tipo": chave, "qtd": valor} for chave, valor in sorted(por_tipo.items())],
        "por_nivel": [{"nivel": chave, "qtd": valor} for chave, valor in sorted(por_nivel.items())],
    })


@csrf_exempt
def api_planos_acao_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    if request.method == "GET":
        planos = PlanoAcaoSST.objects.filter(empresa=empresa)
        status = request.GET.get("status")
        prioridade = request.GET.get("prioridade")
        origem = request.GET.get("origem")

        if status:
            planos = planos.filter(status=status)
        if prioridade:
            planos = planos.filter(prioridade=prioridade)
        if origem:
            planos = planos.filter(origem=origem)

        return JsonResponse({"planos": [_plano_to_dict(plano) for plano in planos]})

    if request.method == "POST":
        data = _json_body(request)
        if not data.get("titulo"):
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)

        risco = None
        if data.get("risco_id"):
            try:
                risco = RiscoOcupacional.objects.get(id=data["risco_id"], empresa=empresa)
            except RiscoOcupacional.DoesNotExist:
                risco = None

        plano = PlanoAcaoSST.objects.create(
            empresa=empresa,
            risco=risco,
            titulo=data["titulo"],
            descricao=data.get("descricao", ""),
            origem=data.get("origem", "risco"),
            prioridade=data.get("prioridade", "media"),
            responsavel=data.get("responsavel", ""),
            setor=data.get("setor", ""),
            data_prazo=data.get("data_prazo") or None,
            status=data.get("status", "aberto"),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"plano": _plano_to_dict(plano)}, status=201)

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


@csrf_exempt
def api_plano_acao_sst_detalhe(request, plano_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    try:
        plano = PlanoAcaoSST.objects.get(id=plano_id, empresa=empresa)
    except PlanoAcaoSST.DoesNotExist:
        return JsonResponse({"erro": "Plano nao encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"plano": _plano_to_dict(plano)})

    if request.method in ("PUT", "PATCH"):
        data = _json_body(request)
        campos = ["titulo", "descricao", "origem", "prioridade", "responsavel", "setor", "status", "observacoes"]
        for campo in campos:
            if campo in data:
                setattr(plano, campo, data[campo])
        for campo_data in ["data_prazo", "data_conclusao"]:
            if campo_data in data:
                setattr(plano, campo_data, data[campo_data] or None)
        if "risco_id" in data:
            try:
                plano.risco = RiscoOcupacional.objects.get(id=data["risco_id"], empresa=empresa)
            except RiscoOcupacional.DoesNotExist:
                plano.risco = None
        if plano.status == "concluido" and not plano.data_conclusao:
            plano.data_conclusao = date.today()
        plano.save()
        return JsonResponse({"plano": _plano_to_dict(plano)})

    if request.method == "DELETE":
        plano.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


from .access_control import requer_permissao_modulo


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_riscos_page(request):
    from django.shortcuts import render, redirect
    from .views_dashboard import _empresa_autenticada
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_riscos.html", {"empresa_nome": empresa.nome})
