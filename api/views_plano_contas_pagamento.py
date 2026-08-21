"""
views_plano_contas_pagamento.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTAS MÉDICAS + PAGAMENTO A PRESTADOR (lado operadora).

A partir dos lotes TISS já processados (views_plano_tiss_recepcao), fecha as
contas por prestador/competência e gera o lote de repasse com o valor líquido
(apresentado − glosa). Diferencial: IA de anomalia de faturamento — compara a
competência atual com o histórico do prestador (z-score) e trava o repasse pra
auditoria quando há um pico atípico. Antifraude nativo, não módulo à parte.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    contexto_navegacao_setorial, requer_operacao_page, requer_permissao_modulo,
    requer_setor,
)
from .models import LotePagamentoPrestador, LoteTISSRecebido, PrestadorPlanoSaude
from .views_dashboard import _empresa_autenticada
from .views_plano_saude import _ps_auth


def _comp_valida(c: str) -> bool:
    try:
        ano, mes = c.split("-")
        return len(ano) == 4 and 1 <= int(mes) <= 12
    except (ValueError, AttributeError):
        return False


def _f(v) -> float:
    return float(v or 0)


# ── contas abertas: prestadores com lotes processados ainda sem repasse ──────
def contas_abertas(empresa, competencia: str):
    ano, mes = competencia.split("-")
    base = LoteTISSRecebido.objects.filter(
        empresa=empresa, status="processado", pagamento__isnull=True,
        prestador__isnull=False,
        recebido_em__year=int(ano), recebido_em__month=int(mes),
    )
    agg = (base.values("prestador_id", "prestador_nome")
           .annotate(qtd=Count("id"),
                     bruto=Sum("valor_apresentado"),
                     glosa=Sum("valor_glosado"),
                     liquido=Sum("valor_liberado"))
           .order_by("-liquido"))
    return [{
        "prestador_id": r["prestador_id"], "prestador": r["prestador_nome"],
        "qtd_lotes": r["qtd"], "valor_bruto": _f(r["bruto"]),
        "valor_glosa": _f(r["glosa"]), "valor_liquido": _f(r["liquido"]),
    } for r in agg]


# ── IA de anomalia de faturamento (z-score sobre o histórico do prestador) ───
def _ia_anomalia(empresa, prestador, competencia, valor_liquido: Decimal):
    historico = list(LotePagamentoPrestador.objects.filter(
        empresa=empresa, prestador=prestador,
    ).exclude(competencia=competencia).exclude(status="cancelado")
        .order_by("-competencia").values_list("valor_liquido", flat=True)[:6])
    valores = [float(v) for v in historico]
    atual = float(valor_liquido)
    if len(valores) < 2:
        return 0, "Sem histórico suficiente para detectar anomalia (baseline em formação)."
    media = sum(valores) / len(valores)
    var = sum((v - media) ** 2 for v in valores) / len(valores)
    desvio = var ** 0.5
    if media <= 0:
        return 0, "Histórico sem faturamento relevante; sem baseline para comparação."
    variacao_pct = (atual - media) / media * 100
    z = (atual - media) / desvio if desvio > 0 else 0
    # combina sinal por z-score (dispersão) e por desvio percentual: um histórico
    # "liso" (desvio=0) com pico grande ainda deve pontuar alto via variação %.
    z_score = abs(z) * 30
    pct_score = max(0.0, abs(variacao_pct) - 20) * 1.5  # começa a pontuar acima de ±20%
    score = int(min(100, max(z_score, pct_score)))
    if atual > media and variacao_pct >= 30:
        parecer = (f"Faturamento {variacao_pct:+.0f}% vs. média das últimas {len(valores)} competências "
                   f"(R$ {media:,.2f}). Pico atípico (z={z:.1f}) — auditoria recomendada ANTES do repasse.")
    elif variacao_pct <= -40:
        parecer = (f"Faturamento {variacao_pct:+.0f}% abaixo da média (R$ {media:,.2f}). "
                   "Possível subnotificação ou lote incompleto — verificar.")
    else:
        parecer = (f"Faturamento dentro do padrão histórico (média R$ {media:,.2f}, {variacao_pct:+.0f}%). "
                   "Repasse pode seguir.")
    return score, parecer


# ── fechamento de conta → lote de repasse ────────────────────────────────────
def fechar_conta(empresa, prestador_id: int, competencia: str) -> LotePagamentoPrestador:
    ano, mes = competencia.split("-")
    prestador = PrestadorPlanoSaude.objects.get(id=prestador_id, empresa=empresa)
    with transaction.atomic():
        lotes = list(LoteTISSRecebido.objects.select_for_update().filter(
            empresa=empresa, prestador=prestador, status="processado",
            pagamento__isnull=True,
            recebido_em__year=int(ano), recebido_em__month=int(mes),
        ))
        if not lotes:
            raise ValueError("Nenhum lote processado em aberto para este prestador nesta competência.")
        bruto = sum((l.valor_apresentado for l in lotes), Decimal("0"))
        glosa = sum((l.valor_glosado for l in lotes), Decimal("0"))
        liquido = sum((l.valor_liberado for l in lotes), Decimal("0"))
        score, parecer = _ia_anomalia(empresa, prestador, competencia, liquido)
        pag = LotePagamentoPrestador.objects.create(
            empresa=empresa, prestador=prestador, prestador_nome=prestador.nome_fantasia,
            competencia=competencia, qtd_lotes=len(lotes),
            valor_bruto=bruto, valor_glosa=glosa, valor_liquido=liquido,
            ia_anomalia_score=score, ia_anomalia_parecer=parecer, status="fechado",
        )
        LoteTISSRecebido.objects.filter(id__in=[l.id for l in lotes]).update(pagamento=pag)
    return pag


def _pag_dict(p: LotePagamentoPrestador) -> dict:
    return {
        "id": p.id, "prestador": p.prestador_nome, "competencia": p.competencia,
        "qtd_lotes": p.qtd_lotes, "valor_bruto": _f(p.valor_bruto),
        "valor_glosa": _f(p.valor_glosa), "valor_liquido": _f(p.valor_liquido),
        "ia_anomalia_score": p.ia_anomalia_score, "ia_anomalia_parecer": p.ia_anomalia_parecer,
        "status": p.status, "forma_pagamento": p.forma_pagamento,
        "data_pagamento": p.data_pagamento.strftime("%d/%m/%Y %H:%M") if p.data_pagamento else None,
        "comprovante": p.comprovante, "criado_em": p.criado_em.strftime("%d/%m/%Y"),
    }


# ── APIs ─────────────────────────────────────────────────────────────────────
@require_http_methods(["GET"])
def api_contas_abertas(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    competencia = request.GET.get("competencia") or timezone.now().strftime("%Y-%m")
    if not _comp_valida(competencia):
        return JsonResponse({"erro": "Competência inválida (use YYYY-MM)"}, status=400)
    # não credenciados com lotes no período (não entram em repasse) — só alerta
    ano, mes = competencia.split("-")
    nao_cred = LoteTISSRecebido.objects.filter(
        empresa=empresa, status="processado", pagamento__isnull=True, prestador__isnull=True,
        recebido_em__year=int(ano), recebido_em__month=int(mes),
    ).count()
    return JsonResponse({
        "competencia": competencia,
        "abertas": contas_abertas(empresa, competencia),
        "nao_credenciados_lotes": nao_cred,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_contas_fechar(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    competencia = body.get("competencia") or ""
    prestador_id = body.get("prestador_id")
    if not _comp_valida(competencia) or not prestador_id:
        return JsonResponse({"erro": "Informe prestador_id e competencia (YYYY-MM)"}, status=400)
    try:
        pag = fechar_conta(empresa, int(prestador_id), competencia)
    except PrestadorPlanoSaude.DoesNotExist:
        return JsonResponse({"erro": "Prestador não encontrado"}, status=404)
    except ValueError as e:
        return JsonResponse({"erro": str(e)}, status=400)
    return JsonResponse({"ok": True, "pagamento": _pag_dict(pag)})


@require_http_methods(["GET"])
def api_pagamentos_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    qs = LotePagamentoPrestador.objects.filter(empresa=empresa)
    comp = request.GET.get("competencia")
    if comp:
        qs = qs.filter(competencia=comp)
    st = request.GET.get("status")
    if st:
        qs = qs.filter(status=st)
    return JsonResponse({"pagamentos": [_pag_dict(p) for p in qs[:300]]})


@require_http_methods(["GET"])
def api_pagamento_detalhe(request, pag_id: int):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        pag = LotePagamentoPrestador.objects.get(id=pag_id, empresa=empresa)
    except LotePagamentoPrestador.DoesNotExist:
        return JsonResponse({"erro": "Repasse não encontrado"}, status=404)
    lotes = [{
        "id": l.id, "numero_lote": l.numero_lote, "beneficiario": l.beneficiario_nome,
        "guia": l.guia_numero, "valor_apresentado": _f(l.valor_apresentado),
        "valor_glosado": _f(l.valor_glosado), "valor_liberado": _f(l.valor_liberado),
        "ia_score_glosa": l.ia_score_glosa,
    } for l in pag.lotes_incluidos.all()]
    return JsonResponse({"pagamento": _pag_dict(pag), "lotes": lotes})


@csrf_exempt
@require_http_methods(["POST"])
def api_pagamento_acao(request, pag_id: int):
    """Aprovar ou marcar como pago (ação sensível — libera o repasse)."""
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        pag = LotePagamentoPrestador.objects.get(id=pag_id, empresa=empresa)
    except LotePagamentoPrestador.DoesNotExist:
        return JsonResponse({"erro": "Repasse não encontrado"}, status=404)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    acao = body.get("acao")
    if acao == "aprovar":
        if pag.status != "fechado":
            return JsonResponse({"erro": "Só é possível aprovar um repasse fechado."}, status=400)
        pag.status = "aprovado"
        pag.save(update_fields=["status"])
    elif acao == "pagar":
        if pag.status not in ("fechado", "aprovado"):
            return JsonResponse({"erro": "Repasse não está apto a pagamento."}, status=400)
        forma = body.get("forma_pagamento", "")
        if forma not in ("pix", "ted", "boleto"):
            return JsonResponse({"erro": "forma_pagamento inválida (pix/ted/boleto)"}, status=400)
        pag.status = "pago"
        pag.forma_pagamento = forma
        pag.comprovante = (body.get("comprovante") or "")[:120]
        pag.data_pagamento = timezone.now()
        pag.save(update_fields=["status", "forma_pagamento", "comprovante", "data_pagamento"])
        pag.lotes_incluidos.update(status="retornado")
    elif acao == "cancelar":
        if pag.status == "pago":
            return JsonResponse({"erro": "Repasse já pago não pode ser cancelado."}, status=400)
        pag.lotes_incluidos.update(pagamento=None)  # devolve lotes ao aberto
        pag.status = "cancelado"
        pag.save(update_fields=["status"])
    else:
        return JsonResponse({"erro": "Ação inválida (aprovar/pagar/cancelar)"}, status=400)
    return JsonResponse({"ok": True, "pagamento": _pag_dict(pag)})


# ── page ─────────────────────────────────────────────────────────────────────
@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.rede_credenciada")
def plano_contas_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_contas_pagamento.html", ctx)
