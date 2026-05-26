"""
Plano de Saúde — Corretores e Comissões.
Gerenciamento de corretoras parceiras e lançamento/controle de comissões.
"""
import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Count, Q

from .access_control import api_requer_gerencia, contexto_navegacao_setorial
from .models import CorretoraPlano, CorretoraComissao
from .views_dashboard import _empresa_autenticada


# ── helpers ──────────────────────────────────────────────────────────────────

def _ps_auth(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return empresa, None


def _corretora_dict(c):
    return {
        "id": c.id,
        "razao_social": c.razao_social,
        "cnpj": c.cnpj,
        "susep": c.susep,
        "telefone": c.telefone,
        "email": c.email,
        "ativa": c.ativa,
        "criado_em": c.criado_em.strftime("%d/%m/%Y"),
    }


def _comissao_dict(cm):
    return {
        "id": cm.id,
        "corretora_id": cm.corretora_id,
        "competencia": cm.competencia,
        "vidas_vendidas": cm.vidas_vendidas,
        "receita_base": float(cm.receita_base),
        "percentual_comissao": float(cm.percentual_comissao),
        "valor_comissao": float(cm.valor_comissao),
        "pago": cm.pago,
        "pago_em": cm.pago_em.strftime("%d/%m/%Y %H:%M") if cm.pago_em else None,
    }


# ── page ─────────────────────────────────────────────────────────────────────

def plano_corretores_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_corretores.html", ctx)


# ── API: corretoras ───────────────────────────────────────────────────────────

@csrf_exempt
def api_corretoras_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = CorretoraPlano.objects.filter(empresa=empresa)
        ativa_filter = request.GET.get("ativa")
        if ativa_filter is not None:
            qs = qs.filter(ativa=(ativa_filter == "1" or ativa_filter.lower() == "true"))
        return JsonResponse({"corretoras": [_corretora_dict(c) for c in qs]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        razao = (data.get("razao_social") or "").strip()
        if not razao:
            return JsonResponse({"erro": "razao_social obrigatória"}, status=400)
        c = CorretoraPlano.objects.create(
            empresa=empresa,
            razao_social=razao,
            cnpj=data.get("cnpj", ""),
            susep=data.get("susep", ""),
            telefone=data.get("telefone", ""),
            email=data.get("email", ""),
            ativa=bool(data.get("ativa", True)),
        )
        return JsonResponse({"corretora": _corretora_dict(c)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_corretora_detalhe(request, cor_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        c = CorretoraPlano.objects.get(id=cor_id, empresa=empresa)
    except CorretoraPlano.DoesNotExist:
        return JsonResponse({"erro": "Corretora não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"corretora": _corretora_dict(c)})

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for field in ("razao_social", "cnpj", "susep", "telefone", "email"):
            if field in data:
                setattr(c, field, data[field])
        if "ativa" in data:
            c.ativa = bool(data["ativa"])
        c.save()
        return JsonResponse({"corretora": _corretora_dict(c)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── API: comissões ────────────────────────────────────────────────────────────

@csrf_exempt
def api_corretora_comissoes(request, cor_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        corretora = CorretoraPlano.objects.get(id=cor_id, empresa=empresa)
    except CorretoraPlano.DoesNotExist:
        return JsonResponse({"erro": "Corretora não encontrada"}, status=404)

    if request.method == "GET":
        qs = corretora.comissoes.all()
        return JsonResponse({"comissoes": [_comissao_dict(cm) for cm in qs]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        competencia = (data.get("competencia") or "").strip()
        if not competencia:
            return JsonResponse({"erro": "competencia obrigatória (AAAAMM)"}, status=400)
        receita_base = float(data.get("receita_base") or 0)
        percentual = float(data.get("percentual_comissao") or 0)
        valor = receita_base * (percentual / 100)
        cm = CorretoraComissao.objects.create(
            corretora=corretora,
            competencia=competencia,
            vidas_vendidas=int(data.get("vidas_vendidas") or 0),
            receita_base=receita_base,
            percentual_comissao=percentual,
            valor_comissao=round(valor, 2),
            pago=bool(data.get("pago", False)),
        )
        return JsonResponse({"comissao": _comissao_dict(cm)}, status=201)

    # PATCH: marcar como pago
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        cm_id = data.get("comissao_id")
        if not cm_id:
            return JsonResponse({"erro": "comissao_id obrigatório"}, status=400)
        try:
            cm = CorretoraComissao.objects.get(id=cm_id, corretora=corretora)
        except CorretoraComissao.DoesNotExist:
            return JsonResponse({"erro": "Comissão não encontrada"}, status=404)
        cm.pago = True
        cm.pago_em = timezone.now()
        cm.save()
        return JsonResponse({"comissao": _comissao_dict(cm)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── API: KPIs ─────────────────────────────────────────────────────────────────

def api_corretoras_kpis(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    hoje = date.today()
    mes_atual = hoje.strftime("%Y%m")

    total_corretoras = CorretoraPlano.objects.filter(empresa=empresa, ativa=True).count()

    # vidas vendidas no mês atual
    vidas_mes = CorretoraComissao.objects.filter(
        corretora__empresa=empresa,
        competencia=mes_atual,
    ).aggregate(total=Sum("vidas_vendidas"))["total"] or 0

    # comissões pagas (total histórico)
    pagas = CorretoraComissao.objects.filter(
        corretora__empresa=empresa,
        pago=True,
    ).aggregate(total=Sum("valor_comissao"))["total"] or 0

    # comissões a pagar (pendentes)
    a_pagar = CorretoraComissao.objects.filter(
        corretora__empresa=empresa,
        pago=False,
    ).aggregate(total=Sum("valor_comissao"))["total"] or 0

    return JsonResponse({
        "total_corretoras_ativas": total_corretoras,
        "vidas_vendidas_mes": vidas_mes,
        "total_comissoes_pagas": float(pagas),
        "total_comissoes_a_pagar": float(a_pagar),
    })
