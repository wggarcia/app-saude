"""
Views Farmácia PBM — Convênios PBM e Farmácia Popular.
Endpoints para: convênios (CRUD), registros Farmácia Popular, KPIs.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Sum, Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import PBMConvenio, FarmaciaPopularRegistro
from .access_control import api_requer_gerencia


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _convenio_to_dict(c):
    return {
        "id": c.id,
        "nome": c.nome,
        "codigo_credenciado": c.codigo_credenciado,
        "percentual_desconto_padrao": float(c.percentual_desconto_padrao),
        "ativo": c.ativo,
        "criado_em": c.criado_em.isoformat(),
    }


def _registro_to_dict(r):
    return {
        "id": r.id,
        "mes_referencia": r.mes_referencia.isoformat(),
        "medicamentos_dispensados": r.medicamentos_dispensados,
        "valor_subsidiado": float(r.valor_subsidiado),
        "valor_copagamento": float(r.valor_copagamento),
        "arquivos_transmitidos": r.arquivos_transmitidos,
        "enviado_em": r.enviado_em.isoformat() if r.enviado_em else None,
    }


# ─── Page view ────────────────────────────────────────────────────────────────

def farmacia_pbm_page(request):
    return render(request, "farmacia_pbm.html")


# ─── Convênios PBM ────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
def api_pbm_convenios(request):
    """GET — lista convênios PBM. POST — cria convênio."""
    empresa = request.empresa

    if request.method == "GET":
        qs = PBMConvenio.objects.filter(empresa=empresa)

        ativo = request.GET.get("ativo", "").strip()
        if ativo == "1":
            qs = qs.filter(ativo=True)
        elif ativo == "0":
            qs = qs.filter(ativo=False)

        return JsonResponse({
            "ok": True,
            "convenios": [_convenio_to_dict(c) for c in qs],
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = (data.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Campo 'nome' é obrigatório"}, status=400)

        convenio = PBMConvenio.objects.create(
            empresa=empresa,
            nome=nome,
            codigo_credenciado=data.get("codigo_credenciado", ""),
            percentual_desconto_padrao=_decimal(data.get("percentual_desconto_padrao", 0)),
            ativo=bool(data.get("ativo", True)),
        )

        return JsonResponse({"ok": True, "convenio": _convenio_to_dict(convenio)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_gerencia
def api_pbm_convenio_detalhe(request, conv_id):
    """GET — detalhe. PUT — atualiza. DELETE — remove convênio PBM."""
    empresa = request.empresa

    try:
        convenio = PBMConvenio.objects.get(pk=conv_id, empresa=empresa)
    except PBMConvenio.DoesNotExist:
        return JsonResponse({"erro": "Convênio não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"ok": True, "convenio": _convenio_to_dict(convenio)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        if "nome" in data:
            convenio.nome = (data["nome"] or "").strip() or convenio.nome
        if "codigo_credenciado" in data:
            convenio.codigo_credenciado = data["codigo_credenciado"]
        if "percentual_desconto_padrao" in data:
            convenio.percentual_desconto_padrao = _decimal(data["percentual_desconto_padrao"])
        if "ativo" in data:
            convenio.ativo = bool(data["ativo"])

        convenio.save()
        return JsonResponse({"ok": True, "convenio": _convenio_to_dict(convenio)})

    if request.method == "DELETE":
        convenio.delete()
        return JsonResponse({"ok": True, "mensagem": "Convênio removido"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── Farmácia Popular ─────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
def api_farmacia_popular_registros(request):
    """GET — lista registros mensais. POST — cria/atualiza registro do mês."""
    empresa = request.empresa

    if request.method == "GET":
        qs = FarmaciaPopularRegistro.objects.filter(empresa=empresa)

        ano = request.GET.get("ano", "").strip()
        if ano:
            qs = qs.filter(mes_referencia__year=ano)

        return JsonResponse({
            "ok": True,
            "registros": [_registro_to_dict(r) for r in qs],
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        mes_ref_str = (data.get("mes_referencia") or "").strip()
        if not mes_ref_str:
            return JsonResponse({"erro": "Campo 'mes_referencia' é obrigatório (formato YYYY-MM-DD)"}, status=400)

        try:
            mes_ref = date.fromisoformat(mes_ref_str)
            # Normalizar para primeiro dia do mês
            mes_ref = mes_ref.replace(day=1)
        except ValueError:
            return JsonResponse({"erro": "Formato de data inválido. Use YYYY-MM-DD"}, status=400)

        # Upsert por empresa + mês
        registro, created = FarmaciaPopularRegistro.objects.get_or_create(
            empresa=empresa,
            mes_referencia=mes_ref,
            defaults={
                "medicamentos_dispensados": 0,
                "valor_subsidiado": Decimal("0"),
                "valor_copagamento": Decimal("0"),
                "arquivos_transmitidos": False,
            },
        )

        # Atualizar campos
        if "medicamentos_dispensados" in data:
            registro.medicamentos_dispensados = int(data["medicamentos_dispensados"])
        if "valor_subsidiado" in data:
            registro.valor_subsidiado = _decimal(data["valor_subsidiado"])
        if "valor_copagamento" in data:
            registro.valor_copagamento = _decimal(data["valor_copagamento"])
        if "arquivos_transmitidos" in data:
            registro.arquivos_transmitidos = bool(data["arquivos_transmitidos"])
            if registro.arquivos_transmitidos and not registro.enviado_em:
                registro.enviado_em = timezone.now()

        registro.save()

        status_code = 201 if created else 200
        return JsonResponse({"ok": True, "registro": _registro_to_dict(registro)}, status=status_code)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── KPIs PBM / Farmácia Popular ──────────────────────────────────────────────

@csrf_exempt
@api_requer_gerencia
def api_farmacia_popular_kpis(request):
    """GET — totais do mês corrente para convênios e Farmácia Popular."""
    empresa = request.empresa

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    hoje = date.today()
    mes_atual = hoje.replace(day=1)

    # Convênios ativos
    convenios_ativos = PBMConvenio.objects.filter(empresa=empresa, ativo=True).count()

    # Registro do mês atual
    registro_mes = FarmaciaPopularRegistro.objects.filter(
        empresa=empresa,
        mes_referencia=mes_atual,
    ).first()

    dispensacoes_mes = registro_mes.medicamentos_dispensados if registro_mes else 0
    valor_subsidiado_mes = float(registro_mes.valor_subsidiado) if registro_mes else 0.0
    valor_copagamento_mes = float(registro_mes.valor_copagamento) if registro_mes else 0.0

    # Total acumulado do ano
    registros_ano = FarmaciaPopularRegistro.objects.filter(
        empresa=empresa,
        mes_referencia__year=hoje.year,
    )
    total_subsidiado_ano = float(
        registros_ano.aggregate(soma=Sum("valor_subsidiado"))["soma"] or Decimal("0")
    )

    return JsonResponse({
        "ok": True,
        "kpis": {
            "convenios_ativos": convenios_ativos,
            "dispensacoes_pbm_mes": dispensacoes_mes,
            "valor_subsidiado_mes": valor_subsidiado_mes,
            "valor_copagamento_mes": valor_copagamento_mes,
            "total_subsidiado_ano": total_subsidiado_ano,
            "transmissao_pendente": registro_mes is not None and not registro_mes.arquivos_transmitidos,
        },
    })
