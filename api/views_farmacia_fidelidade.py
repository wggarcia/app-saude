"""
Fidelidade — Programa de Pontos da Farmácia.

Regra padrão (fixa, sem configuração por enquanto):
  • Acúmulo: 1 ponto a cada R$ 1,00 em compras.
  • Resgate: mínimo de 100 pontos, cada ponto vale R$ 0,05 de desconto
    (100 pontos = R$ 5,00).

GET/POST /api/farmacia/fidelidade/clientes         Lista/busca por CPF, cadastra
GET      /api/farmacia/fidelidade/clientes/<cpf>   Saldo + extrato do cliente
POST     /api/farmacia/fidelidade/acumular         Credita pontos por uma venda
POST     /api/farmacia/fidelidade/resgatar         Debita pontos, retorna desconto
GET      /api/farmacia/fidelidade/kpis             KPIs do programa
"""
import json
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.db.models import Sum, Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo, api_requer_feature,
)
from .services.auth_session import empresa_autenticada_from_request as get_empresa

PONTOS_POR_REAL = 1
VALOR_POR_PONTO_RESGATE = Decimal("0.05")
RESGATE_MINIMO = 100


def _e(request):
    empresa = get_empresa(request)
    if not empresa or get_setor(empresa) != "farmacia":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("farmacia")
@requer_operacao_page
@requer_permissao_modulo("farmacia.gestao")
def farmacia_fidelidade_page(request):
    return render(request, "farmacia_fidelidade.html")


# ── Clientes ──────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("farmacia.fidelidade")
def api_fidelidade_clientes(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ClienteFidelidade

    if request.method == "GET":
        qs = ClienteFidelidade.objects.filter(empresa=empresa, ativo=True)
        q = request.GET.get("q")
        if q:
            qs = qs.filter(cpf__icontains=q) if q.replace(".", "").replace("-", "").isdigit() else qs.filter(nome__icontains=q)
        return JsonResponse({
            "total": qs.count(),
            "clientes": [
                {"id": c.id, "cpf": c.cpf, "nome": c.nome, "telefone": c.telefone, "pontos_saldo": c.pontos_saldo}
                for c in qs.order_by("nome")[:200]
            ],
        })

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cpf = (data.get("cpf") or "").strip()
    nome = (data.get("nome") or "").strip()
    if not cpf or not nome:
        return JsonResponse({"erro": "CPF e nome são obrigatórios"}, status=400)
    if ClienteFidelidade.objects.filter(empresa=empresa, cpf=cpf).exists():
        return JsonResponse({"erro": "Já existe um cliente com esse CPF"}, status=409)

    c = ClienteFidelidade.objects.create(
        empresa=empresa, cpf=cpf, nome=nome, telefone=data.get("telefone", ""),
    )
    return JsonResponse({"id": c.id}, status=201)


@require_http_methods(["GET"])
@api_requer_feature("farmacia.fidelidade")
def api_fidelidade_cliente_detalhe(request, cpf):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ClienteFidelidade
    try:
        c = ClienteFidelidade.objects.get(empresa=empresa, cpf=cpf)
    except ClienteFidelidade.DoesNotExist:
        return JsonResponse({"erro": "Cliente não encontrado"}, status=404)

    transacoes = c.transacoes.order_by("-criado_em")[:100]
    return JsonResponse({
        "id": c.id, "cpf": c.cpf, "nome": c.nome, "telefone": c.telefone,
        "pontos_saldo": c.pontos_saldo,
        "valor_disponivel_resgate": float((c.pontos_saldo * VALOR_POR_PONTO_RESGATE).quantize(Decimal("0.01"))),
        "transacoes": [
            {
                "id": t.id, "tipo": t.tipo, "tipo_display": t.get_tipo_display(),
                "pontos": t.pontos, "valor_referencia": float(t.valor_referencia),
                "descricao": t.descricao, "criado_em": t.criado_em.isoformat(),
            }
            for t in transacoes
        ],
    })


# ── Acumular / Resgatar ───────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("farmacia.fidelidade")
def api_fidelidade_acumular(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ClienteFidelidade, TransacaoFidelidade

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cpf = (data.get("cpf") or "").strip()
    try:
        valor_venda = Decimal(str(data.get("valor_venda", "0")))
    except Exception:
        return JsonResponse({"erro": "valor_venda inválido"}, status=400)
    if valor_venda <= 0:
        return JsonResponse({"erro": "valor_venda deve ser maior que zero"}, status=400)

    try:
        cliente = ClienteFidelidade.objects.get(empresa=empresa, cpf=cpf)
    except ClienteFidelidade.DoesNotExist:
        return JsonResponse({"erro": "Cliente não cadastrado no programa de fidelidade"}, status=404)

    pontos_ganhos = int((valor_venda * PONTOS_POR_REAL).to_integral_value(rounding=ROUND_DOWN))

    with transaction.atomic():
        cliente.pontos_saldo += pontos_ganhos
        cliente.save(update_fields=["pontos_saldo"])
        TransacaoFidelidade.objects.create(
            empresa=empresa, cliente=cliente, tipo="acumulo",
            pontos=pontos_ganhos, valor_referencia=valor_venda,
            descricao=data.get("descricao", ""),
        )

    return JsonResponse({"ok": True, "pontos_ganhos": pontos_ganhos, "pontos_saldo": cliente.pontos_saldo})


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("farmacia.fidelidade")
def api_fidelidade_resgatar(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ClienteFidelidade, TransacaoFidelidade

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cpf = (data.get("cpf") or "").strip()
    try:
        pontos = int(data.get("pontos", 0))
    except (TypeError, ValueError):
        return JsonResponse({"erro": "pontos inválido"}, status=400)

    if pontos < RESGATE_MINIMO:
        return JsonResponse({"erro": f"Resgate mínimo é de {RESGATE_MINIMO} pontos"}, status=400)

    try:
        cliente = ClienteFidelidade.objects.get(empresa=empresa, cpf=cpf)
    except ClienteFidelidade.DoesNotExist:
        return JsonResponse({"erro": "Cliente não cadastrado no programa de fidelidade"}, status=404)

    if cliente.pontos_saldo < pontos:
        return JsonResponse({"erro": f"Saldo insuficiente (disponível: {cliente.pontos_saldo} pontos)"}, status=400)

    valor_desconto = (pontos * VALOR_POR_PONTO_RESGATE).quantize(Decimal("0.01"))

    with transaction.atomic():
        cliente.pontos_saldo -= pontos
        cliente.save(update_fields=["pontos_saldo"])
        TransacaoFidelidade.objects.create(
            empresa=empresa, cliente=cliente, tipo="resgate",
            pontos=-pontos, valor_referencia=valor_desconto,
            descricao=data.get("descricao", ""),
        )

    return JsonResponse({"ok": True, "valor_desconto": float(valor_desconto), "pontos_saldo": cliente.pontos_saldo})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("farmacia.fidelidade")
def api_fidelidade_kpis(request):
    empresa = _e(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import ClienteFidelidade, TransacaoFidelidade

    clientes = ClienteFidelidade.objects.filter(empresa=empresa, ativo=True)
    tx = TransacaoFidelidade.objects.filter(empresa=empresa)

    return JsonResponse({
        "total_clientes": clientes.count(),
        "pontos_em_circulacao": clientes.aggregate(s=Sum("pontos_saldo"))["s"] or 0,
        "total_acumulado": tx.filter(tipo="acumulo").aggregate(s=Sum("pontos"))["s"] or 0,
        "total_resgatado_pontos": abs(tx.filter(tipo="resgate").aggregate(s=Sum("pontos"))["s"] or 0),
        "valor_total_resgatado": float(tx.filter(tipo="resgate").aggregate(s=Sum("valor_referencia"))["s"] or 0),
        "regra_acumulo": f"{PONTOS_POR_REAL} ponto por R$ 1,00",
        "regra_resgate": f"mínimo {RESGATE_MINIMO} pontos = R$ {(RESGATE_MINIMO * VALOR_POR_PONTO_RESGATE):.2f}",
    })
