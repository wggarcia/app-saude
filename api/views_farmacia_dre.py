"""
Views Farmácia DRE — Demonstração do Resultado do Exercício / Financeiro.
Endpoints para: listagem mensal, salvar DRE, dashboard calculado.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .models import DREFarmacia
from .access_control import api_requer_gerencia, requer_setor, requer_operacao_page, requer_permissao_modulo, api_requer_feature


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _dre_calcular(dre):
    """Calcula os campos derivados do DRE."""
    receita_liquida = dre.receita_bruta - dre.devolucoes - dre.impostos
    lucro_bruto = receita_liquida - dre.cmv
    total_despesas = (
        dre.despesas_operacionais
        + dre.despesas_pessoal
        + dre.despesas_aluguel
        + dre.outras_despesas
    )
    lucro_liquido = lucro_bruto - total_despesas

    margem_bruta = float((lucro_bruto / receita_liquida * 100) if receita_liquida else Decimal("0"))
    margem_liquida = float((lucro_liquido / receita_liquida * 100) if receita_liquida else Decimal("0"))

    return {
        "receita_liquida": float(receita_liquida),
        "lucro_bruto": float(lucro_bruto),
        "total_despesas": float(total_despesas),
        "lucro_liquido": float(lucro_liquido),
        "margem_bruta_pct": round(margem_bruta, 2),
        "margem_liquida_pct": round(margem_liquida, 2),
    }


def _dre_to_dict(dre):
    calculado = _dre_calcular(dre)
    return {
        "id": dre.id,
        "mes_referencia": dre.mes_referencia.isoformat(),
        "receita_bruta": float(dre.receita_bruta),
        "devolucoes": float(dre.devolucoes),
        "impostos": float(dre.impostos),
        "cmv": float(dre.cmv),
        "despesas_operacionais": float(dre.despesas_operacionais),
        "despesas_pessoal": float(dre.despesas_pessoal),
        "despesas_aluguel": float(dre.despesas_aluguel),
        "outras_despesas": float(dre.outras_despesas),
        "observacoes": dre.observacoes,
        "criado_em": dre.criado_em.isoformat(),
        "atualizado_em": dre.atualizado_em.isoformat(),
        **calculado,
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("farmacia")
@requer_operacao_page
@requer_permissao_modulo("farmacia.gestao")
def farmacia_financeiro_page(request):
    return render(request, "farmacia_financeiro.html")


# ─── Lista DRE ────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.dre")
def api_dre_lista(request):
    """GET — últimos 12 meses de DRE da empresa."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    qs = DREFarmacia.objects.filter(empresa=empresa)[:12]
    return JsonResponse({
        "ok": True,
        "dre_lista": [_dre_to_dict(d) for d in qs],
    })


# ─── Salvar DRE ───────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.dre")
def api_dre_salvar(request):
    """POST — cria ou atualiza o DRE para o mês de referência."""
    empresa = request.empresa

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    mes_ref_str = (data.get("mes_referencia") or "").strip()
    if not mes_ref_str:
        return JsonResponse({"erro": "Campo 'mes_referencia' é obrigatório (formato YYYY-MM-DD)"}, status=400)

    try:
        mes_ref = date.fromisoformat(mes_ref_str)
        mes_ref = mes_ref.replace(day=1)  # normaliza para primeiro dia do mês
    except ValueError:
        return JsonResponse({"erro": "Formato de data inválido. Use YYYY-MM-DD"}, status=400)

    dre, created = DREFarmacia.objects.get_or_create(
        empresa=empresa,
        mes_referencia=mes_ref,
        defaults={
            "receita_bruta": Decimal("0"),
            "devolucoes": Decimal("0"),
            "impostos": Decimal("0"),
            "cmv": Decimal("0"),
            "despesas_operacionais": Decimal("0"),
            "despesas_pessoal": Decimal("0"),
            "despesas_aluguel": Decimal("0"),
            "outras_despesas": Decimal("0"),
            "observacoes": "",
        },
    )

    # Campos atualizáveis
    campos = [
        "receita_bruta", "devolucoes", "impostos", "cmv",
        "despesas_operacionais", "despesas_pessoal",
        "despesas_aluguel", "outras_despesas",
    ]
    for campo in campos:
        if campo in data:
            setattr(dre, campo, _decimal(data[campo]))

    if "observacoes" in data:
        dre.observacoes = data["observacoes"]

    dre.save()

    status_code = 201 if created else 200
    return JsonResponse({"ok": True, "dre": _dre_to_dict(dre)}, status=status_code)


# ─── Dashboard calculado ─────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
@api_requer_feature("farmacia.dre")
def api_dre_dashboard(request):
    """GET — dashboard financeiro calculado: mês atual e tendência."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    hoje = date.today()

    # Mês de referência via query param ou mês atual
    mes_ref_str = request.GET.get("mes_referencia", "").strip()
    if mes_ref_str:
        try:
            mes_ref = date.fromisoformat(mes_ref_str).replace(day=1)
        except ValueError:
            mes_ref = hoje.replace(day=1)
    else:
        mes_ref = hoje.replace(day=1)

    dre_atual = DREFarmacia.objects.filter(empresa=empresa, mes_referencia=mes_ref).first()

    if not dre_atual:
        return JsonResponse({
            "ok": True,
            "mes_referencia": mes_ref.isoformat(),
            "dre": None,
            "kpis": {
                "receita_liquida": 0,
                "lucro_bruto": 0,
                "lucro_liquido": 0,
                "margem_liquida_pct": 0,
                "margem_bruta_pct": 0,
            },
            "historico": [],
        })

    calculado = _dre_calcular(dre_atual)

    # Histórico dos últimos 12 meses para gráfico
    historico_qs = DREFarmacia.objects.filter(empresa=empresa).order_by("mes_referencia")[:12]
    historico = []
    for d in historico_qs:
        c = _dre_calcular(d)
        historico.append({
            "mes": d.mes_referencia.isoformat(),
            "receita_bruta": float(d.receita_bruta),
            "receita_liquida": c["receita_liquida"],
            "lucro_bruto": c["lucro_bruto"],
            "lucro_liquido": c["lucro_liquido"],
            "margem_liquida_pct": c["margem_liquida_pct"],
        })

    return JsonResponse({
        "ok": True,
        "mes_referencia": mes_ref.isoformat(),
        "dre": _dre_to_dict(dre_atual),
        "kpis": {
            "receita_liquida": calculado["receita_liquida"],
            "lucro_bruto": calculado["lucro_bruto"],
            "lucro_liquido": calculado["lucro_liquido"],
            "margem_liquida_pct": calculado["margem_liquida_pct"],
            "margem_bruta_pct": calculado["margem_bruta_pct"],
        },
        "historico": historico,
    })
