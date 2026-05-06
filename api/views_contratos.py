"""
Views para Gestão de Contratos de Saúde / Convênios e Beneficiários.
"""
import json
from datetime import date, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ContratoSaude, BeneficiarioContrato, FuncionarioSST
from .views_dashboard import _empresa_autenticada


def _contrato_to_dict(c):
    hoje = date.today()
    dias = (c.data_fim - hoje).days if c.data_fim else None
    return {
        "id": c.id,
        "tipo": c.tipo,
        "tipo_label": c.get_tipo_display(),
        "operadora": c.operadora,
        "numero_contrato": c.numero_contrato,
        "registro_ans": c.registro_ans,
        "descricao": c.descricao,
        "abrangencia": c.abrangencia,
        "abrangencia_label": c.get_abrangencia_display(),
        "data_inicio": str(c.data_inicio),
        "data_fim": str(c.data_fim) if c.data_fim else None,
        "dias_para_vencer": dias,
        "vencido": bool(c.data_fim and c.data_fim < hoje),
        "vencendo_30d": bool(dias is not None and 0 <= dias <= 30),
        "valor_mensal": float(c.valor_mensal) if c.valor_mensal else None,
        "valor_per_capita": float(c.valor_per_capita) if c.valor_per_capita else None,
        "total_beneficiarios": c.total_beneficiarios,
        "status": c.status,
        "status_label": c.get_status_display(),
        "cobertura_detalhes": c.cobertura_detalhes,
        "carencias": c.carencias,
        "contato_operadora": c.contato_operadora,
        "observacoes": c.observacoes,
        "criado_em": c.criado_em.strftime("%d/%m/%Y"),
    }


def _beneficiario_to_dict(b):
    return {
        "id": b.id,
        "contrato_id": b.contrato_id,
        "contrato_operadora": b.contrato.operadora,
        "funcionario_id": b.funcionario_id,
        "funcionario_nome": b.funcionario.nome,
        "funcionario_cargo": b.funcionario.cargo or "",
        "numero_carteirinha": b.numero_carteirinha,
        "data_inclusao": str(b.data_inclusao) if b.data_inclusao else None,
        "data_exclusao": str(b.data_exclusao) if b.data_exclusao else None,
        "ativo": b.ativo,
        "dependentes": b.dependentes,
    }


@csrf_exempt
def api_contratos_saude(request):
    """GET list / POST create contratos."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = ContratoSaude.objects.filter(empresa=empresa)
        tipo_f   = request.GET.get("tipo")
        status_f = request.GET.get("status")
        if tipo_f:   qs = qs.filter(tipo=tipo_f)
        if status_f: qs = qs.filter(status=status_f)
        return JsonResponse({"contratos": [_contrato_to_dict(c) for c in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        if not data.get("operadora"):
            return JsonResponse({"erro": "operadora obrigatório"}, status=400)
        if not data.get("data_inicio"):
            return JsonResponse({"erro": "data_inicio obrigatório"}, status=400)

        c = ContratoSaude.objects.create(
            empresa=empresa,
            tipo=data.get("tipo", "plano_saude"),
            operadora=data["operadora"],
            numero_contrato=data.get("numero_contrato", ""),
            registro_ans=data.get("registro_ans", ""),
            descricao=data.get("descricao", ""),
            abrangencia=data.get("abrangencia", "nacional"),
            data_inicio=data["data_inicio"],
            data_fim=data.get("data_fim") or None,
            valor_mensal=data.get("valor_mensal") or None,
            valor_per_capita=data.get("valor_per_capita") or None,
            total_beneficiarios=data.get("total_beneficiarios", 0),
            status=data.get("status", "ativo"),
            cobertura_detalhes=data.get("cobertura_detalhes", ""),
            carencias=data.get("carencias", ""),
            contato_operadora=data.get("contato_operadora", ""),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"contrato": _contrato_to_dict(c)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_contrato_saude_detalhe(request, contrato_id):
    """GET / PUT / DELETE contrato."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        c = ContratoSaude.objects.get(id=contrato_id, empresa=empresa)
    except ContratoSaude.DoesNotExist:
        return JsonResponse({"erro": "Contrato não encontrado"}, status=404)

    if request.method == "GET":
        bens = c.beneficiarios.filter(ativo=True).select_related("funcionario")
        return JsonResponse({
            "contrato": _contrato_to_dict(c),
            "beneficiarios": [_beneficiario_to_dict(b) for b in bens],
        })

    elif request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        campos = ["tipo", "operadora", "numero_contrato", "registro_ans", "descricao",
                  "abrangencia", "status", "cobertura_detalhes", "carencias",
                  "contato_operadora", "observacoes"]
        for f in campos:
            if f in data:
                setattr(c, f, data[f])
        for df in ["data_inicio", "data_fim"]:
            if df in data:
                setattr(c, df, data[df] or None)
        for nf in ["valor_mensal", "valor_per_capita"]:
            if nf in data:
                setattr(c, nf, data[nf] or None)
        if "total_beneficiarios" in data:
            c.total_beneficiarios = int(data["total_beneficiarios"] or 0)
        c.save()
        return JsonResponse({"contrato": _contrato_to_dict(c)})

    elif request.method == "DELETE":
        c.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_beneficiarios_contrato(request, contrato_id):
    """GET beneficiários / POST adicionar beneficiário."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        contrato = ContratoSaude.objects.get(id=contrato_id, empresa=empresa)
    except ContratoSaude.DoesNotExist:
        return JsonResponse({"erro": "Contrato não encontrado"}, status=404)

    if request.method == "GET":
        ativo_f = request.GET.get("ativo")
        qs = contrato.beneficiarios.select_related("funcionario")
        if ativo_f is not None:
            qs = qs.filter(ativo=ativo_f.lower() == "true")
        return JsonResponse({"beneficiarios": [_beneficiario_to_dict(b) for b in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        func_id = data.get("funcionario_id")
        if not func_id:
            return JsonResponse({"erro": "funcionario_id obrigatório"}, status=400)
        try:
            func = FuncionarioSST.objects.get(id=func_id, empresa=empresa)
        except FuncionarioSST.DoesNotExist:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

        b, created = BeneficiarioContrato.objects.get_or_create(
            contrato=contrato, funcionario=func,
            defaults={
                "numero_carteirinha": data.get("numero_carteirinha", ""),
                "data_inclusao": data.get("data_inclusao") or None,
                "dependentes": int(data.get("dependentes", 0)),
                "ativo": True,
            }
        )
        if not created:
            b.ativo = True
            b.numero_carteirinha = data.get("numero_carteirinha", b.numero_carteirinha)
            b.data_inclusao = data.get("data_inclusao") or b.data_inclusao
            b.dependentes = int(data.get("dependentes", b.dependentes))
            b.save()

        # Atualizar contagem
        contrato.total_beneficiarios = contrato.beneficiarios.filter(ativo=True).count()
        contrato.save(update_fields=["total_beneficiarios"])

        return JsonResponse({"beneficiario": _beneficiario_to_dict(b)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_beneficiario_excluir(request, beneficiario_id):
    """DELETE / PUT (inativar) beneficiário."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        b = BeneficiarioContrato.objects.get(
            id=beneficiario_id, contrato__empresa=empresa
        )
    except BeneficiarioContrato.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)

    if request.method in ("PUT", "PATCH"):
        # Inativar (exclusão do plano sem remover registro)
        b.ativo = False
        b.data_exclusao = date.today()
        b.save()
        b.contrato.total_beneficiarios = b.contrato.beneficiarios.filter(ativo=True).count()
        b.contrato.save(update_fields=["total_beneficiarios"])
        return JsonResponse({"ok": True, "ativo": False})

    elif request.method == "DELETE":
        contrato = b.contrato
        b.delete()
        contrato.total_beneficiarios = contrato.beneficiarios.filter(ativo=True).count()
        contrato.save(update_fields=["total_beneficiarios"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


def api_contratos_kpis(request):
    """KPIs de contratos: ativos, vencendo, custo total."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    qs = ContratoSaude.objects.filter(empresa=empresa)

    ativos    = qs.filter(status="ativo").count()
    vencidos  = qs.filter(status="ativo", data_fim__lt=hoje).count()
    vencendo  = qs.filter(status="ativo", data_fim__gte=hoje,
                          data_fim__lte=hoje + timedelta(days=30)).count()
    total_ben = sum(c.total_beneficiarios for c in qs.filter(status="ativo"))

    # Custo mensal total dos ativos
    custo_total = sum(
        float(c.valor_mensal) for c in qs.filter(status="ativo")
        if c.valor_mensal
    )

    # Por tipo
    por_tipo = {}
    for c in qs.filter(status="ativo"):
        k = c.get_tipo_display()
        por_tipo[k] = por_tipo.get(k, 0) + 1

    return JsonResponse({
        "kpis": {
            "total": qs.count(),
            "ativos": ativos,
            "vencidos": vencidos,
            "vencendo_30d": vencendo,
            "total_beneficiarios": total_ben,
            "custo_mensal_total": custo_total,
        },
        "por_tipo": [{"tipo": k, "quantidade": v} for k, v in por_tipo.items()],
    })


def contratos_page(request):
    from django.shortcuts import render
    return render(request, "contratos_saude.html")
