"""
Módulo Financeiro para Clínicas — SolusCRT SST
Faturamento, contas a pagar/receber, TISS, glosas, relatórios.

Endpoints:
  GET/POST  /api/clinica/financeiro/faturas/                 — listar / criar fatura
  GET/PATCH /api/clinica/financeiro/faturas/<id>/            — detalhe / editar
  POST      /api/clinica/financeiro/faturas/<id>/baixar/     — confirmar pagamento
  POST      /api/clinica/financeiro/faturas/<id>/cancelar/   — cancelar
  GET       /api/clinica/financeiro/faturas/<id>/pdf/        — nota/fatura PDF
  GET/POST  /api/clinica/financeiro/despesas/                — despesas da clínica
  GET       /api/clinica/financeiro/glosas/                  — glosas a contestar
  GET       /api/clinica/financeiro/kpis/                    — DRE simplificado
  GET       /api/clinica/financeiro/fluxo-caixa/             — fluxo de caixa mensal
"""
from datetime import date, timedelta
from django.http import JsonResponse, HttpResponse
import json


def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


STATUS_FATURA = [
    ("pendente", "Pendente"),
    ("enviada", "Enviada ao cliente"),
    ("paga", "Paga"),
    ("vencida", "Vencida"),
    ("cancelada", "Cancelada"),
    ("em_glosa", "Em glosa"),
    ("parcial", "Pago parcialmente"),
]

SERVICOS_PADRAO = [
    {"codigo": "10101012", "descricao": "Consulta Médica em Saúde Ocupacional", "preco_tabela": 180.00},
    {"codigo": "40302361", "descricao": "ASO — Atestado de Saúde Ocupacional", "preco_tabela": 95.00},
    {"codigo": "40103012", "descricao": "Hemograma completo", "preco_tabela": 35.00},
    {"codigo": "40103020", "descricao": "Glicemia em jejum", "preco_tabela": 18.00},
    {"codigo": "40103039", "descricao": "Colesterol total e frações", "preco_tabela": 28.00},
    {"codigo": "40601129", "descricao": "Audiometria tonal liminar", "preco_tabela": 65.00},
    {"codigo": "40601196", "descricao": "Espirometria", "preco_tabela": 75.00},
    {"codigo": "40601056", "descricao": "Acuidade Visual (Snellen)", "preco_tabela": 40.00},
    {"codigo": "40304361", "descricao": "Eletrocardiograma de repouso", "preco_tabela": 85.00},
    {"codigo": "40901280", "descricao": "Raio-X Tórax PA e Perfil", "preco_tabela": 110.00},
    {"codigo": "40101010", "descricao": "Toxicológico urinário ampliado (10 drogas)", "preco_tabela": 180.00},
    {"codigo": "40301558", "descricao": "Colinesterase eritrocitária", "preco_tabela": 45.00},
    {"codigo": "90800023", "descricao": "LTCAT — Laudo Técnico CA", "preco_tabela": 1200.00},
    {"codigo": "90800031", "descricao": "PGR — Programa de Gerenciamento de Riscos", "preco_tabela": 2500.00},
    {"codigo": "90800040", "descricao": "PPP — Perfil Profissiográfico Previdenciário", "preco_tabela": 80.00},
]


def _fatura_dict(f):
    return {
        "id": f.id,
        "numero": f.numero,
        "empresa_cliente_nome": f.empresa_cliente_nome,
        "empresa_cliente_cnpj": f.empresa_cliente_cnpj,
        "data_emissao": str(f.data_emissao),
        "data_vencimento": str(f.data_vencimento),
        "data_pagamento": str(f.data_pagamento or ""),
        "status": f.status,
        "itens": f.itens,
        "subtotal": float(f.subtotal),
        "desconto": float(f.desconto),
        "total": float(f.total),
        "valor_pago": float(f.valor_pago or 0),
        "saldo": float(f.total - (f.valor_pago or 0)),
        "forma_pagamento": f.forma_pagamento,
        "observacoes": f.observacoes,
        "glosa_valor": float(f.glosa_valor or 0),
        "glosa_motivo": f.glosa_motivo,
        "criado_em": str(f.criado_em.date()),
        "vencida": f.status == "pendente" and f.data_vencimento < date.today(),
    }


# ──────────────────────────────────────────────
# FATURAS (CONTAS A RECEBER)
# ──────────────────────────────────────────────

def api_faturas(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    if request.method == "POST":
        return _criar_fatura(request, empresa)

    try:
        from .models import FaturaClinica
        qs = FaturaClinica.objects.filter(clinica=empresa)

        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        mes = request.GET.get("mes")  # YYYY-MM
        if mes:
            ano, m = mes.split("-")
            qs = qs.filter(data_emissao__year=ano, data_emissao__month=m)

        cliente = request.GET.get("cliente")
        if cliente:
            qs = qs.filter(empresa_cliente_nome__icontains=cliente)

        faturas = [_fatura_dict(f) for f in qs.order_by("-data_emissao")[:200]]

        from django.db.models import Sum
        totais = qs.aggregate(
            total_faturado=Sum("total"),
            total_recebido=Sum("valor_pago"),
        )

        return JsonResponse({
            "total_faturas": len(faturas),
            "total_faturado": float(totais["total_faturado"] or 0),
            "total_recebido": float(totais["total_recebido"] or 0),
            "a_receber": float((totais["total_faturado"] or 0) - (totais["total_recebido"] or 0)),
            "faturas": faturas,
            "tabela_servicos": SERVICOS_PADRAO,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def _criar_fatura(request, empresa):
    data = _json(request)
    obrig = ["empresa_cliente_nome", "empresa_cliente_cnpj", "itens"]
    for c in obrig:
        if not data.get(c):
            return JsonResponse({"erro": f"Campo obrigatório: {c}"}, status=400)

    try:
        from .models import FaturaClinica

        itens = data["itens"]
        subtotal = sum(float(i.get("preco_unitario", 0)) * int(i.get("quantidade", 1)) for i in itens)
        desconto = float(data.get("desconto", 0))
        total = subtotal - desconto

        # Gera número sequencial
        ultimo = FaturaClinica.objects.filter(clinica=empresa).count()
        numero = f"FAT-{date.today().year}-{str(ultimo + 1).zfill(4)}"

        fatura = FaturaClinica.objects.create(
            clinica=empresa,
            numero=numero,
            empresa_cliente_nome=data["empresa_cliente_nome"],
            empresa_cliente_cnpj=data["empresa_cliente_cnpj"],
            data_emissao=data.get("data_emissao") or date.today(),
            data_vencimento=data.get("data_vencimento") or (date.today() + timedelta(days=30)),
            status="pendente",
            itens=itens,
            subtotal=subtotal,
            desconto=desconto,
            total=total,
            valor_pago=0,
            forma_pagamento=data.get("forma_pagamento", "transferencia"),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"sucesso": True, "fatura": _fatura_dict(fatura)}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_fatura_detalhe(request, fatura_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FaturaClinica
        fatura = FaturaClinica.objects.get(id=fatura_id, clinica=empresa)
        if request.method == "PATCH":
            data = _json(request)
            for c in ["observacoes", "forma_pagamento", "data_vencimento", "desconto"]:
                if c in data:
                    setattr(fatura, c, data[c])
            if "desconto" in data:
                fatura.total = float(fatura.subtotal) - float(data["desconto"])
            fatura.save()
        return JsonResponse(_fatura_dict(fatura))
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_fatura_baixar(request, fatura_id):
    """Registra pagamento (total ou parcial)."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    data = _json(request)
    valor_pago = float(data.get("valor_pago", 0))
    if valor_pago <= 0:
        return JsonResponse({"erro": "valor_pago deve ser positivo"}, status=400)
    try:
        from .models import FaturaClinica
        fatura = FaturaClinica.objects.get(id=fatura_id, clinica=empresa)
        fatura.valor_pago = (fatura.valor_pago or 0) + valor_pago
        fatura.data_pagamento = data.get("data_pagamento") or date.today()
        fatura.forma_pagamento = data.get("forma_pagamento", fatura.forma_pagamento)
        if float(fatura.valor_pago) >= float(fatura.total):
            fatura.status = "paga"
        else:
            fatura.status = "parcial"
        fatura.save()
        return JsonResponse({"sucesso": True, "fatura": _fatura_dict(fatura)})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_fatura_cancelar(request, fatura_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        from .models import FaturaClinica
        fatura = FaturaClinica.objects.get(id=fatura_id, clinica=empresa)
        fatura.status = "cancelada"
        fatura.save()
        return JsonResponse({"sucesso": True})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_fatura_pdf(request, fatura_id):
    """Gera PDF da fatura/nota de serviço."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FaturaClinica
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        import io

        fatura = FaturaClinica.objects.get(id=fatura_id, clinica=empresa)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        azul = colors.HexColor("#0A2540")
        verde = colors.HexColor("#00C896")

        tit = ParagraphStyle("tit", fontSize=16, textColor=azul, fontName="Helvetica-Bold")
        sub = ParagraphStyle("sub", fontSize=8.5, textColor=colors.HexColor("#5A6A80"),
                             parent=styles["Normal"])
        body = ParagraphStyle("body", fontSize=9, parent=styles["Normal"])

        story = []
        story.append(Paragraph(f"FATURA DE SERVIÇOS Nº {fatura.numero}", tit))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            f"SolusCRT Tecnologia em Saúde Ltda. · CNPJ 66.940.015/0001-48 · "
            f"contato@soluscrt.com.br · soluscrt.com.br", sub))
        story.append(HRFlowable(width="100%", thickness=1.5, color=verde, spaceAfter=8))

        # PARTES
        story.append(Table([
            [Paragraph("<b>PRESTADOR</b>", body), Paragraph("<b>TOMADOR</b>", body)],
            [Paragraph(empresa.nome, body), Paragraph(fatura.empresa_cliente_nome, body)],
            [Paragraph(f"CNPJ: {getattr(empresa,'cnpj','—')}", sub),
             Paragraph(f"CNPJ: {fatura.empresa_cliente_cnpj}", sub)],
        ], colWidths=[8*cm, 8*cm]))
        story.append(Spacer(1, 0.3*cm))

        # INFO FATURA
        story.append(Table([
            [f"Emissão: {fatura.data_emissao}", f"Vencimento: {fatura.data_vencimento}",
             f"Status: {fatura.status.upper()}", f"Forma: {fatura.forma_pagamento}"],
        ], colWidths=[4*cm, 4*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 0.3*cm))

        # ITENS
        story.append(Paragraph("ITENS DE SERVIÇO", ParagraphStyle("h", fontSize=10,
                                textColor=azul, fontName="Helvetica-Bold")))
        story.append(Spacer(1, 0.2*cm))
        itens_data = [["Código", "Descrição", "Qtd", "Valor Unit.", "Total"]]
        for item in fatura.itens:
            qty = int(item.get("quantidade", 1))
            preco = float(item.get("preco_unitario", 0))
            itens_data.append([
                item.get("codigo", "—"),
                Paragraph(item.get("descricao", "—"), body),
                str(qty),
                f"R$ {preco:,.2f}",
                f"R$ {qty * preco:,.2f}",
            ])
        t = Table(itens_data, colWidths=[2.5*cm, 7*cm, 1.5*cm, 2.5*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), azul),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTSIZE",   (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE3EC")),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3*cm))

        # TOTAIS
        totais_data = [
            ["", "Subtotal:", f"R$ {fatura.subtotal:,.2f}"],
            ["", "Desconto:", f"- R$ {fatura.desconto:,.2f}"],
            ["", "TOTAL:", f"R$ {fatura.total:,.2f}"],
        ]
        if fatura.valor_pago:
            totais_data.append(["", "Valor pago:", f"R$ {fatura.valor_pago:,.2f}"])
            totais_data.append(["", "Saldo:", f"R$ {float(fatura.total) - float(fatura.valor_pago):,.2f}"])
        t2 = Table(totais_data, colWidths=[9*cm, 4*cm, 3*cm])
        t2.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
            ("FONTSIZE", (1, 2), (-1, 2), 11),
            ("TEXTCOLOR", (1, 2), (-1, 2), azul),
        ]))
        story.append(t2)

        if fatura.observacoes:
            story.append(Spacer(1, 0.4*cm))
            story.append(Paragraph(f"Observações: {fatura.observacoes}", sub))

        doc.build(story)
        buf.seek(0)
        resp = HttpResponse(buf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="Fatura_{fatura.numero}.pdf"'
        return resp
    except ImportError:
        return JsonResponse({"erro": "ReportLab não instalado"}, status=500)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ──────────────────────────────────────────────
# DESPESAS (CONTAS A PAGAR)
# ──────────────────────────────────────────────

def api_despesas_clinica(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method == "POST":
        data = _json(request)
        try:
            from .models import DespesaClinica
            despesa = DespesaClinica.objects.create(
                clinica=empresa,
                descricao=data.get("descricao", ""),
                categoria=data.get("categoria", "outros"),
                valor=float(data.get("valor", 0)),
                data_competencia=data.get("data_competencia") or str(date.today()),
                data_vencimento=data.get("data_vencimento"),
                pago=data.get("pago", False),
                data_pagamento=data.get("data_pagamento"),
                fornecedor=data.get("fornecedor", ""),
                observacoes=data.get("observacoes", ""),
            )
            return JsonResponse({"sucesso": True, "id": despesa.id}, status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)
    try:
        from .models import DespesaClinica
        from django.db.models import Sum
        qs = DespesaClinica.objects.filter(clinica=empresa)
        mes = request.GET.get("mes")
        if mes:
            ano, m = mes.split("-")
            qs = qs.filter(data_competencia__year=ano, data_competencia__month=m)
        total = qs.aggregate(t=Sum("valor"))["t"] or 0
        pagas = qs.filter(pago=True).aggregate(t=Sum("valor"))["t"] or 0
        return JsonResponse({
            "total_despesas": float(total),
            "pagas": float(pagas),
            "a_pagar": float(total - pagas),
            "despesas": list(qs.values().order_by("-data_competencia")[:200]),
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ──────────────────────────────────────────────
# GLOSAS
# ──────────────────────────────────────────────

def api_glosas(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FaturaClinica
        glosas = FaturaClinica.objects.filter(clinica=empresa, status="em_glosa")
        return JsonResponse({
            "total_glosas": glosas.count(),
            "valor_em_glosa": float(sum(f.glosa_valor or 0 for f in glosas)),
            "glosas": [_fatura_dict(f) for f in glosas],
            "orientacao": "Conteste a glosa em até 30 dias com documentação de suporte (ASO, laudos, protocolos).",
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ──────────────────────────────────────────────
# DRE + FLUXO DE CAIXA
# ──────────────────────────────────────────────

def api_financeiro_kpis_clinica(request):
    """DRE simplificado — Receita, Despesas, Lucro, Margem."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FaturaClinica, DespesaClinica
        from django.db.models import Sum

        hoje = date.today()
        mes_ini = hoje.replace(day=1)

        receita_mes = FaturaClinica.objects.filter(
            clinica=empresa, status__in=["paga", "parcial"],
            data_pagamento__gte=mes_ini
        ).aggregate(t=Sum("valor_pago"))["t"] or 0

        faturado_mes = FaturaClinica.objects.filter(
            clinica=empresa, data_emissao__gte=mes_ini
        ).aggregate(t=Sum("total"))["t"] or 0

        a_receber = FaturaClinica.objects.filter(
            clinica=empresa, status__in=["pendente", "enviada", "parcial"]
        ).aggregate(t=Sum("total"))["t"] or 0

        despesas_mes = DespesaClinica.objects.filter(
            clinica=empresa, data_competencia__gte=mes_ini
        ).aggregate(t=Sum("valor"))["t"] or 0

        lucro = float(receita_mes) - float(despesas_mes)
        margem = round(lucro / float(receita_mes) * 100, 1) if receita_mes > 0 else 0

        vencidas = FaturaClinica.objects.filter(
            clinica=empresa, status="pendente",
            data_vencimento__lt=hoje
        ).count()

        return JsonResponse({
            "mes_referencia": mes_ini.strftime("%b/%Y"),
            "receita_realizada": float(receita_mes),
            "faturado_emitido": float(faturado_mes),
            "a_receber": float(a_receber),
            "despesas": float(despesas_mes),
            "lucro_liquido": lucro,
            "margem_pct": margem,
            "faturas_vencidas": vencidas,
            "tabela_servicos": SERVICOS_PADRAO,
            "alerta": lucro < 0,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_fluxo_caixa_clinica(request):
    """Fluxo de caixa mensal — últimos 6 meses."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FaturaClinica, DespesaClinica
        from django.db.models import Sum

        hoje = date.today()
        resultado = []
        for i in range(5, -1, -1):
            mes = (hoje.replace(day=1) - __import__('datetime').timedelta(days=30*i)).replace(day=1)
            prox = (mes.replace(day=28) + __import__('datetime').timedelta(days=4)).replace(day=1)

            rec = FaturaClinica.objects.filter(
                clinica=empresa, data_pagamento__gte=mes, data_pagamento__lt=prox
            ).aggregate(t=Sum("valor_pago"))["t"] or 0

            desp = DespesaClinica.objects.filter(
                clinica=empresa, data_competencia__gte=mes, data_competencia__lt=prox
            ).aggregate(t=Sum("valor"))["t"] or 0

            resultado.append({
                "mes": mes.strftime("%Y-%m"),
                "mes_fmt": mes.strftime("%b/%y"),
                "receita": float(rec),
                "despesas": float(desp),
                "saldo": float(rec) - float(desp),
            })

        return JsonResponse({"fluxo_caixa": resultado})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ── Página HTML ───────────────────────────────────────────────────────────────

def sst_financeiro_clinica_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_expansao_modulo.html", {
        "modulo_id":      "financeiro_clinica",
        "modulo_area":    "Financeiro · Clínica Ocupacional",
        "modulo_titulo":  "Financeiro da Clínica",
        "modulo_descricao": (
            "Faturamento de serviços SST com TISS, DRE mensal, fluxo de caixa de 6 meses, "
            "gestão de glosas e contas a pagar/receber para clínicas ocupacionais."
        ),
        "api_base":     "/api/clinica/financeiro/faturas/",
        "api_kpi":      "/api/clinica/financeiro/kpis/",
        "accent_color": "#a374ff",
        "empresa_nome": empresa.nome,
    })
