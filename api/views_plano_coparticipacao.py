"""
views_plano_coparticipacao.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MOTOR DE COPARTICIPAÇÃO (fator moderador) — lado operadora.

Calcula a coparticipação de cada procedimento consumido pelo beneficiário a
partir das regras do plano, já embutindo a conformidade ANS:
  • teto de 40% do valor do procedimento (RN 507/2022 — fator moderador);
  • isenção de procedimentos preventivos e de acompanhamento de crônicos;
  • teto mensal por beneficiário (quando o plano define).

Diferencial vs. legado: a conformidade ANS é NATIVA (o sistema recusa/ajusta
regra que fura o teto), tem AUDITOR de regras e um SIMULADOR de gasto mensal —
os sistemas antigos só aplicam % cego e deixam a operadora exposta a multa.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    contexto_navegacao_setorial, requer_operacao_page, requer_permissao_modulo,
    requer_setor,
)
from .models import (
    BeneficiarioPlano, CoparticipacaoRegra, EventoCoparticipacao,
    FaturamentoBeneficiario, PlanoSaude,
)
from .views_dashboard import _empresa_autenticada
from .views_plano_saude import _ps_auth

# ANS RN 507/2022 — fator moderador limitado a 40% do valor do procedimento.
FATOR_ANS_MAX = Decimal("0.40")
CENT = Decimal("0.01")


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")).quantize(CENT)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _f(v):
    return float(v or 0)


def _comp_valida(c):
    try:
        a, m = c.split("-")
        return len(a) == 4 and 1 <= int(m) <= 12
    except (ValueError, AttributeError):
        return False


# ── cálculo de um evento (coração do motor) ──────────────────────────────────
def calcular_coparticipacao(regra, valor_procedimento: Decimal, preventivo: bool,
                            ja_acumulado: Decimal):
    """Retorna dict: percentual, base, valor, isento, motivo. Não persiste."""
    valor_procedimento = _dec(valor_procedimento)
    if preventivo:
        return {"percentual": Decimal("0"), "base": Decimal("0"), "valor": Decimal("0"),
                "isento": True, "motivo": "Procedimento preventivo — isento (RN 465/RN 507)"}
    if regra is None or not regra.ativo:
        return {"percentual": Decimal("0"), "base": Decimal("0"), "valor": Decimal("0"),
                "isento": True, "motivo": "Sem regra de coparticipação para este tipo — sem cobrança"}
    perc = _dec(regra.percentual)
    if perc > 0:
        base = (valor_procedimento * perc / Decimal("100")).quantize(CENT)
    else:
        base = _dec(regra.valor_fixo)
    # teto ANS: nunca acima de 40% do valor do procedimento
    teto_ans = (valor_procedimento * FATOR_ANS_MAX).quantize(CENT)
    valor = base
    motivo = ""
    if valor > teto_ans:
        valor = teto_ans
        motivo = "Ajustado ao teto ANS de 40% (RN 507)"
    # teto mensal do plano
    if regra.teto_mensal is not None:
        restante = _dec(regra.teto_mensal) - _dec(ja_acumulado)
        if restante <= 0:
            return {"percentual": perc, "base": base, "valor": Decimal("0"),
                    "isento": False, "motivo": "Teto mensal do plano já atingido — sem cobrança"}
        if valor > restante:
            valor = restante
            motivo = "Limitado ao teto mensal do plano"
    return {"percentual": perc, "base": base, "valor": valor.quantize(CENT),
            "isento": False, "motivo": motivo}


def registrar_evento(empresa, beneficiario, tipo, valor_procedimento, descricao="",
                     data_evento=None, preventivo=False, competencia=None):
    plano = beneficiario.plano
    data_evento = data_evento or timezone.now().date()
    competencia = competencia or data_evento.strftime("%Y-%m")
    regra = CoparticipacaoRegra.objects.filter(plano=plano, tipo_atendimento=tipo).first()
    ja = EventoCoparticipacao.objects.filter(
        empresa=empresa, beneficiario=beneficiario, competencia=competencia,
    ).aggregate(s=Sum("valor_coparticipacao"))["s"] or Decimal("0")
    calc = calcular_coparticipacao(regra, valor_procedimento, preventivo, ja)
    return EventoCoparticipacao.objects.create(
        empresa=empresa, beneficiario=beneficiario, plano=plano, regra=regra,
        competencia=competencia, tipo_atendimento=tipo, descricao=descricao[:200],
        data_evento=data_evento, valor_procedimento=_dec(valor_procedimento),
        percentual_aplicado=calc["percentual"], valor_base=calc["base"],
        valor_coparticipacao=calc["valor"], isento=calc["isento"], motivo=calc["motivo"],
    )


def consolidar_competencia(empresa, beneficiario, competencia):
    """Soma os eventos da competência na fatura do beneficiário (coparticipação)."""
    total = EventoCoparticipacao.objects.filter(
        empresa=empresa, beneficiario=beneficiario, competencia=competencia,
    ).aggregate(s=Sum("valor_coparticipacao"))["s"] or Decimal("0")
    fatura, _created = FaturamentoBeneficiario.objects.get_or_create(
        empresa=empresa, beneficiario=beneficiario, competencia=competencia,
        defaults={"plano": beneficiario.plano},
    )
    fatura.valor_coparticipacao = total
    fatura.valor_total = _dec(fatura.valor_mensalidade) + total
    fatura.save(update_fields=["valor_coparticipacao", "valor_total", "atualizado_em"])
    return fatura


# ── auditoria de conformidade ANS sobre as regras cadastradas ────────────────
def auditar_regras_ans(empresa):
    regras = CoparticipacaoRegra.objects.filter(plano__empresa=empresa).select_related("plano")
    achados = []
    for r in regras:
        problemas = []
        if _dec(r.percentual) > Decimal("40"):
            problemas.append(f"Percentual {r.percentual}% acima do teto ANS de 40% (RN 507).")
        if r.tipo_atendimento == CoparticipacaoRegra.TIPO_URGENCIA and _dec(r.percentual) > Decimal("0"):
            problemas.append("Coparticipação em urgência/emergência exige cautela regulatória (revisar RN 507).")
        if r.teto_mensal is not None and _dec(r.teto_mensal) <= 0:
            problemas.append("Teto mensal configurado como zero/negativo.")
        if problemas:
            achados.append({
                "regra_id": r.id, "plano": r.plano.nome,
                "tipo": r.get_tipo_atendimento_display(),
                "percentual": _f(r.percentual), "problemas": problemas,
            })
    return achados


# ═══════════════════ APIs ═══════════════════
@require_http_methods(["GET"])
def api_copart_regras(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    regras = CoparticipacaoRegra.objects.filter(plano__empresa=empresa).select_related("plano")
    return JsonResponse({"regras": [{
        "id": r.id, "plano_id": r.plano_id, "plano": r.plano.nome,
        "tipo": r.tipo_atendimento, "tipo_label": r.get_tipo_atendimento_display(),
        "percentual": _f(r.percentual), "valor_fixo": _f(r.valor_fixo),
        "teto_mensal": _f(r.teto_mensal) if r.teto_mensal is not None else None,
        "ativo": r.ativo,
        "conforme_ans": _dec(r.percentual) <= Decimal("40"),
    } for r in regras]})


@csrf_exempt
@require_http_methods(["POST"])
def api_copart_regra_salvar(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    plano_id, tipo = b.get("plano_id"), b.get("tipo")
    if not plano_id or tipo not in dict(CoparticipacaoRegra.TIPO_CHOICES):
        return JsonResponse({"erro": "Informe plano_id e tipo válido"}, status=400)
    perc = _dec(b.get("percentual", 0))
    # guarda de conformidade ANS: recusa regra que fura o teto de 40%
    if perc > Decimal("40"):
        return JsonResponse({"erro": "Percentual acima do teto ANS de 40% (RN 507). Ajuste para ≤ 40%."},
                            status=400)
    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({"erro": "Plano não encontrado"}, status=404)
    teto = b.get("teto_mensal")
    regra, _c = CoparticipacaoRegra.objects.update_or_create(
        plano=plano, tipo_atendimento=tipo,
        defaults={"percentual": perc, "valor_fixo": _dec(b.get("valor_fixo", 0)),
                  "teto_mensal": _dec(teto) if teto not in (None, "") else None,
                  "ativo": bool(b.get("ativo", True))},
    )
    return JsonResponse({"ok": True, "regra_id": regra.id})


@csrf_exempt
@require_http_methods(["POST"])
def api_copart_evento(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    try:
        benef = BeneficiarioPlano.objects.get(id=b.get("beneficiario_id"), plano__empresa=empresa)
    except BeneficiarioPlano.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)
    tipo = b.get("tipo")
    if tipo not in dict(CoparticipacaoRegra.TIPO_CHOICES):
        return JsonResponse({"erro": "tipo inválido"}, status=400)
    ev = registrar_evento(
        empresa, benef, tipo, b.get("valor_procedimento", 0),
        descricao=b.get("descricao", ""), preventivo=bool(b.get("preventivo", False)),
    )
    return JsonResponse({"ok": True, "evento": {
        "id": ev.id, "valor_coparticipacao": _f(ev.valor_coparticipacao),
        "isento": ev.isento, "motivo": ev.motivo, "competencia": ev.competencia,
    }})


@require_http_methods(["GET"])
def api_copart_extrato(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    benef_id = request.GET.get("beneficiario_id")
    competencia = request.GET.get("competencia") or timezone.now().strftime("%Y-%m")
    if not benef_id:
        return JsonResponse({"erro": "Informe beneficiario_id"}, status=400)
    evs = EventoCoparticipacao.objects.filter(
        empresa=empresa, beneficiario_id=benef_id, competencia=competencia)
    total = sum((e.valor_coparticipacao for e in evs), Decimal("0"))
    return JsonResponse({
        "competencia": competencia, "total": _f(total),
        "eventos": [{
            "id": e.id, "tipo": e.tipo_atendimento, "descricao": e.descricao,
            "data": e.data_evento.strftime("%d/%m/%Y") if e.data_evento else None,
            "valor_procedimento": _f(e.valor_procedimento),
            "percentual": _f(e.percentual_aplicado), "valor": _f(e.valor_coparticipacao),
            "isento": e.isento, "motivo": e.motivo,
        } for e in evs],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_copart_consolidar(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    competencia = b.get("competencia")
    if not _comp_valida(competencia):
        return JsonResponse({"erro": "competencia inválida (YYYY-MM)"}, status=400)
    try:
        benef = BeneficiarioPlano.objects.get(id=b.get("beneficiario_id"), plano__empresa=empresa)
    except BeneficiarioPlano.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)
    fatura = consolidar_competencia(empresa, benef, competencia)
    return JsonResponse({"ok": True, "fatura": {
        "competencia": fatura.competencia, "coparticipacao": _f(fatura.valor_coparticipacao),
        "total": _f(fatura.valor_total)}})


@require_http_methods(["GET"])
def api_copart_auditoria_ans(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    achados = auditar_regras_ans(empresa)
    return JsonResponse({"conforme": len(achados) == 0, "achados": achados})


@csrf_exempt
@require_http_methods(["POST"])
def api_copart_simular(request):
    """Simulador: dada uma cesta de uso mensal, projeta a coparticipação (com tetos)."""
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    try:
        benef = BeneficiarioPlano.objects.get(id=b.get("beneficiario_id"), plano__empresa=empresa)
    except BeneficiarioPlano.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)
    cesta = b.get("cesta") or []  # [{tipo, valor, preventivo?}]
    plano = benef.plano
    acumulado = Decimal("0")
    linhas = []
    for item in cesta:
        tipo = item.get("tipo")
        regra = CoparticipacaoRegra.objects.filter(plano=plano, tipo_atendimento=tipo).first()
        calc = calcular_coparticipacao(regra, item.get("valor", 0),
                                       bool(item.get("preventivo", False)), acumulado)
        acumulado += calc["valor"]
        linhas.append({"tipo": tipo, "valor_procedimento": _f(_dec(item.get("valor", 0))),
                       "coparticipacao": _f(calc["valor"]), "motivo": calc["motivo"]})
    return JsonResponse({"total_mensal": _f(acumulado), "linhas": linhas})


# ── page ─────────────────────────────────────────────────────────────────────
@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.autorizacao")
def plano_coparticipacao_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    ctx["planos"] = PlanoSaude.objects.filter(empresa=empresa)[:100]
    return render(request, "plano_coparticipacao.html", ctx)
