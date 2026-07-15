"""
Vigilância Sanitária Municipal — cadastro de estabelecimentos, alvarás e
inspeções/fiscalização (auto de infração, interdição).
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import api_requer_permissao_modulo


def _get_vigilancia_models():
    from .models import EstabelecimentoSanitario, AlvaraSanitario, InspecaoSanitaria
    return EstabelecimentoSanitario, AlvaraSanitario, InspecaoSanitaria


def _estab_to_dict(e):
    return {
        "id": e.id,
        "razao_social": e.razao_social,
        "nome_fantasia": e.nome_fantasia,
        "cnpj_cpf": e.cnpj_cpf,
        "tipo": e.tipo,
        "endereco": e.endereco,
        "bairro": e.bairro,
        "responsavel_tecnico": e.responsavel_tecnico,
        "status": e.status,
        "total_alvaras": e.alvaras.count(),
        "total_inspecoes": e.inspecoes.count(),
        "criado_em": e.criado_em.isoformat(),
    }


def _alvara_to_dict(a):
    return {
        "id": a.id,
        "estabelecimento_id": a.estabelecimento_id,
        "numero": a.numero,
        "data_emissao": a.data_emissao.isoformat(),
        "data_validade": a.data_validade.isoformat(),
        "status": a.status,
        "responsavel_emissao": a.responsavel_emissao,
        "observacoes": a.observacoes,
    }


def _inspecao_to_dict(i):
    return {
        "id": i.id,
        "estabelecimento_id": i.estabelecimento_id,
        "fiscal_nome": i.fiscal_nome,
        "fiscal_matricula": i.fiscal_matricula,
        "data_inspecao": i.data_inspecao.isoformat(),
        "itens_verificados": i.itens_verificados,
        "resultado": i.resultado,
        "numero_auto_infracao": i.numero_auto_infracao,
        "valor_multa": float(i.valor_multa) if i.valor_multa is not None else None,
        "prazo_regularizacao": i.prazo_regularizacao.isoformat() if i.prazo_regularizacao else None,
        "observacoes": i.observacoes,
        "criado_em": i.criado_em.isoformat(),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_vigsan_estabelecimentos(request):
    """GET/POST /api/governo/vigilancia-sanitaria/estabelecimentos/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    EstabelecimentoSanitario, *_ = _get_vigilancia_models()

    if request.method == "GET":
        qs = EstabelecimentoSanitario.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        q = request.GET.get("q")
        if q:
            qs = qs.filter(razao_social__icontains=q)
        return JsonResponse({"estabelecimentos": [_estab_to_dict(e) for e in qs[:300]]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    razao_social = (data.get("razao_social") or "").strip()
    if not razao_social:
        return JsonResponse({"erro": "razao_social é obrigatória"}, status=400)

    estab = EstabelecimentoSanitario.objects.create(
        empresa=empresa,
        razao_social=razao_social,
        nome_fantasia=(data.get("nome_fantasia") or "").strip(),
        cnpj_cpf=(data.get("cnpj_cpf") or "").strip(),
        tipo=data.get("tipo", "alimentos"),
        endereco=(data.get("endereco") or "").strip(),
        bairro=(data.get("bairro") or "").strip(),
        responsavel_tecnico=(data.get("responsavel_tecnico") or "").strip(),
        status=data.get("status", "pendente"),
    )
    return JsonResponse({"ok": True, "estabelecimento": _estab_to_dict(estab)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_vigsan_alvaras(request, estab_id):
    """GET/POST /api/governo/vigilancia-sanitaria/estabelecimentos/<id>/alvaras/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    EstabelecimentoSanitario, AlvaraSanitario, _ = _get_vigilancia_models()
    estab = EstabelecimentoSanitario.objects.filter(pk=estab_id, empresa=empresa).first()
    if not estab:
        return JsonResponse({"erro": "Estabelecimento não encontrado"}, status=404)

    if request.method == "GET":
        qs = estab.alvaras.all()[:50]
        return JsonResponse({"alvaras": [_alvara_to_dict(a) for a in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    numero = (data.get("numero") or "").strip()
    data_emissao = data.get("data_emissao")
    data_validade = data.get("data_validade")
    if not numero or not data_emissao or not data_validade:
        return JsonResponse({"erro": "numero, data_emissao e data_validade são obrigatórios"}, status=400)

    alvara = AlvaraSanitario.objects.create(
        estabelecimento=estab,
        numero=numero,
        data_emissao=data_emissao,
        data_validade=data_validade,
        responsavel_emissao=(data.get("responsavel_emissao") or "").strip(),
        observacoes=(data.get("observacoes") or "").strip(),
    )
    estab.status = "regular"
    estab.save(update_fields=["status"])

    return JsonResponse({"ok": True, "alvara": _alvara_to_dict(alvara)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_vigsan_inspecoes(request, estab_id):
    """GET/POST /api/governo/vigilancia-sanitaria/estabelecimentos/<id>/inspecoes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    EstabelecimentoSanitario, _, InspecaoSanitaria = _get_vigilancia_models()
    estab = EstabelecimentoSanitario.objects.filter(pk=estab_id, empresa=empresa).first()
    if not estab:
        return JsonResponse({"erro": "Estabelecimento não encontrado"}, status=404)

    if request.method == "GET":
        qs = estab.inspecoes.all()[:50]
        return JsonResponse({"inspecoes": [_inspecao_to_dict(i) for i in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    fiscal_nome = (data.get("fiscal_nome") or "").strip()
    data_inspecao = data.get("data_inspecao")
    if not fiscal_nome or not data_inspecao:
        return JsonResponse({"erro": "fiscal_nome e data_inspecao são obrigatórios"}, status=400)

    inspecao = InspecaoSanitaria.objects.create(
        estabelecimento=estab,
        fiscal_nome=fiscal_nome,
        fiscal_matricula=(data.get("fiscal_matricula") or "").strip(),
        data_inspecao=data_inspecao,
        itens_verificados=data.get("itens_verificados") or [],
        resultado=data.get("resultado", "conforme"),
        numero_auto_infracao=(data.get("numero_auto_infracao") or "").strip(),
        valor_multa=data.get("valor_multa") or None,
        prazo_regularizacao=data.get("prazo_regularizacao") or None,
        observacoes=(data.get("observacoes") or "").strip(),
    )

    if inspecao.resultado == "interdicao":
        estab.status = "interditado"
    elif inspecao.resultado in ("nao_conforme", "auto_infracao"):
        estab.status = "pendente"
    estab.save(update_fields=["status"])

    return JsonResponse({"ok": True, "inspecao": _inspecao_to_dict(inspecao)}, status=201)
