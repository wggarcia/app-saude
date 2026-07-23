"""
Laudos Técnicos SST — SoloCRT
LTCAT (Laudo Técnico das Condições Ambientais do Trabalho)
LIP   (Laudo de Insalubridade e Periculosidade)
LTIP  (Laudo Técnico de Insalubridade e Periculosidade)
PGR   (Programa de Gerenciamento de Riscos) — resumo executivo
PCMSO (Programa de Controle Médico) — resumo executivo

Endpoints:
  GET/POST  /api/sst/laudos/              — listar / criar
  GET/PATCH /api/sst/laudos/<id>/         — detalhe / editar
  POST      /api/sst/laudos/<id>/assinar/ — assinar e finalizar
  GET       /api/sst/laudos/<id>/pdf/     — exportar PDF
  GET       /api/sst/laudos/kpis/         — painel de validade
"""
from datetime import date, timedelta
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json

from .access_control import api_requer_feature


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


TIPOS_LAUDO = {
    "ltcat": "LTCAT — Laudo Técnico das Condições Ambientais do Trabalho",
    "lip":   "LIP — Laudo de Insalubridade e Periculosidade",
    "ltip":  "LTIP — Laudo Técnico de Insalubridade e Periculosidade",
    "pgr":   "PGR — Programa de Gerenciamento de Riscos",
    "pcmso": "PCMSO — Programa de Controle Médico de Saúde Ocupacional",
}

# Validade legal de cada laudo (anos)
VALIDADE_ANOS = {
    "ltcat": 2,
    "lip": 2,
    "ltip": 2,
    "pgr": 2,
    "pcmso": 1,
}


def _laudo_dict(laudo):
    vencimento = None
    if laudo.data_emissao:
        anos = VALIDADE_ANOS.get(laudo.tipo, 2)
        vencimento = laudo.data_emissao.replace(year=laudo.data_emissao.year + anos)
    dias_vencer = (vencimento - date.today()).days if vencimento else None
    return {
        "id": laudo.id,
        "tipo": laudo.tipo,
        "tipo_label": TIPOS_LAUDO.get(laudo.tipo, laudo.tipo),
        "posto_trabalho": laudo.posto_trabalho,
        "setor": laudo.setor,
        "data_emissao": str(laudo.data_emissao or ""),
        "data_vencimento": str(vencimento or ""),
        "dias_para_vencer": dias_vencer,
        "status": laudo.status,
        "responsavel_tecnico": laudo.responsavel_tecnico,
        "conselho_registro": laudo.conselho_registro,
        "agentes_avaliados": laudo.agentes_avaliados,
        "metodologia": laudo.metodologia,
        "resultados": laudo.resultados,
        "conclusao": laudo.conclusao,
        "grau_insalubridade": laudo.grau_insalubridade,
        "adicional_pct": laudo.adicional_pct,
        "vencido": dias_vencer is not None and dias_vencer < 0,
        "alerta_vencimento": dias_vencer is not None and 0 <= dias_vencer <= 60,
        "criado_em": str(laudo.criado_em.date()),
    }


@csrf_exempt
@api_requer_feature("sst.laudos_tecnicos")
def api_laudos_lista(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    if request.method == "POST":
        return api_laudos_criar(request)

    try:
        from .models import LaudoTecnicoSST
        qs = LaudoTecnicoSST.objects.filter(empresa=empresa)

        tipo = request.GET.get("tipo")
        if tipo:
            qs = qs.filter(tipo=tipo)

        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        laudos = [_laudo_dict(l) for l in qs.order_by("-data_emissao")[:200]]
        vencidos = sum(1 for l in laudos if l["vencido"])
        alertas = sum(1 for l in laudos if l["alerta_vencimento"])

        return JsonResponse({
            "total": len(laudos),
            "vencidos": vencidos,
            "alertas_vencimento": alertas,
            "laudos": laudos,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
@api_requer_feature("sst.laudos_tecnicos")
def api_laudos_criar(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    data = _json(request)

    tipo = data.get("tipo", "ltcat")
    if tipo not in TIPOS_LAUDO:
        return JsonResponse({"erro": f"Tipo inválido. Opções: {list(TIPOS_LAUDO.keys())}"}, status=400)

    try:
        from .models import LaudoTecnicoSST

        # Agentes padrão por tipo de laudo
        agentes_default = {
            "ltcat": [
                {"agente": "Ruído", "codigo_esocial": "01.01.001", "tipo": "fisico", "unidade": "dB(A)", "metodo": "NHO 01 FUNDACENTRO"},
                {"agente": "Calor", "codigo_esocial": "01.02.001", "tipo": "fisico", "unidade": "°C IBUTG", "metodo": "NHO 06 FUNDACENTRO"},
                {"agente": "Poeiras minerais", "codigo_esocial": "02.01.001", "tipo": "quimico", "unidade": "mg/m³", "metodo": "NIOSH 0600"},
            ],
            "lip": [
                {"agente": "Ruído contínuo ou intermitente", "nr": "NR-15 Anexo 1", "grau": "médio", "adicional": 20},
                {"agente": "Calor", "nr": "NR-15 Anexo 3", "grau": "mínimo", "adicional": 10},
            ],
        }

        laudo = LaudoTecnicoSST.objects.create(
            empresa=empresa,
            tipo=tipo,
            posto_trabalho=data.get("posto_trabalho", ""),
            setor=data.get("setor", ""),
            data_emissao=data.get("data_emissao") or date.today(),
            responsavel_tecnico=data.get("responsavel_tecnico", ""),
            conselho_registro=data.get("conselho_registro", ""),
            agentes_avaliados=data.get("agentes_avaliados") or agentes_default.get(tipo, []),
            metodologia=data.get("metodologia", "Avaliação quantitativa com instrumentos calibrados conforme ABNT NBR e NHO FUNDACENTRO"),
            resultados=data.get("resultados", []),
            conclusao=data.get("conclusao", ""),
            grau_insalubridade=data.get("grau_insalubridade", ""),
            adicional_pct=data.get("adicional_pct", 0),
            status="rascunho",
        )
        return JsonResponse({"sucesso": True, "laudo": _laudo_dict(laudo)}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
@api_requer_feature("sst.laudos_tecnicos")
def api_laudo_detalhe(request, laudo_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import LaudoTecnicoSST
        laudo = LaudoTecnicoSST.objects.get(id=laudo_id, empresa=empresa)
        if request.method == "PATCH":
            data = _json(request)
            campos = ["posto_trabalho", "setor", "responsavel_tecnico", "conselho_registro",
                      "agentes_avaliados", "metodologia", "resultados", "conclusao",
                      "grau_insalubridade", "adicional_pct", "data_emissao"]
            for c in campos:
                if c in data:
                    setattr(laudo, c, data[c])
            laudo.save()
        return JsonResponse(_laudo_dict(laudo))
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


@csrf_exempt
@api_requer_feature("sst.laudos_tecnicos")
def api_laudo_assinar(request, laudo_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        from .models import LaudoTecnicoSST
        laudo = LaudoTecnicoSST.objects.get(id=laudo_id, empresa=empresa)
        if not laudo.responsavel_tecnico or not laudo.conclusao:
            return JsonResponse({"erro": "Preencha responsável técnico e conclusão antes de assinar"}, status=400)
        laudo.status = "vigente"
        laudo.data_assinatura = date.today()
        laudo.save()
        return JsonResponse({"sucesso": True, "status": "vigente", "laudo": _laudo_dict(laudo)})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


@csrf_exempt
@api_requer_feature("sst.laudos_tecnicos")
def api_laudo_pdf(request, laudo_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import LaudoTecnicoSST
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        import io

        laudo = LaudoTecnicoSST.objects.get(id=laudo_id, empresa=empresa)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2.5*cm, rightMargin=2.5*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        azul = colors.HexColor("#0A2540")
        verde = colors.HexColor("#00C896")

        tit = ParagraphStyle("tit", parent=styles["Heading1"], fontSize=14,
                             textColor=azul, spaceAfter=4)
        sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9,
                             textColor=colors.HexColor("#5A6A80"))
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11,
                            textColor=azul, spaceBefore=10, spaceAfter=4)
        body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=14)

        story = []
        story.append(Paragraph(TIPOS_LAUDO.get(laudo.tipo, laudo.tipo).upper(), tit))
        story.append(Paragraph(
            f"Empresa: <b>{empresa.nome}</b> &nbsp;|&nbsp; "
            f"Setor/Posto: {laudo.setor or laudo.posto_trabalho or '—'} &nbsp;|&nbsp; "
            f"Emissão: {laudo.data_emissao} &nbsp;|&nbsp; Status: {laudo.status.upper()}",
            sub))
        story.append(Paragraph(
            "SolusCRT Tecnologia em Saúde Ltda. · CNPJ 66.940.015/0001-48 · contato@soluscrt.com.br",
            sub))
        story.append(HRFlowable(width="100%", thickness=1.5, color=verde, spaceAfter=10))

        # IDENTIFICAÇÃO
        story.append(Paragraph("1. IDENTIFICAÇÃO", h2))
        dados_id = [
            ["Empresa", empresa.nome],
            ["CNPJ Empresa", getattr(empresa, "cnpj", "—") or "—"],
            ["Posto / Setor avaliado", f"{laudo.posto_trabalho or '—'} / {laudo.setor or '—'}"],
            ["Responsável Técnico", laudo.responsavel_tecnico or "—"],
            ["Conselho / Registro", laudo.conselho_registro or "—"],
            ["Data de Emissão", str(laudo.data_emissao or "—")],
            ["Data de Assinatura", str(getattr(laudo, "data_assinatura", None) or "—")],
            ["Validade", f"{VALIDADE_ANOS.get(laudo.tipo, 2)} ano(s)"],
        ]
        t = Table(dados_id, colWidths=[6*cm, 10.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F7FA")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE3EC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

        # AGENTES AVALIADOS
        story.append(Paragraph("2. AGENTES AVALIADOS / FATORES DE RISCO", h2))
        if laudo.agentes_avaliados:
            ag_data = [["Agente", "Tipo / NR", "Metodologia / Código", "Unidade"]]
            for ag in laudo.agentes_avaliados:
                ag_data.append([
                    Paragraph(str(ag.get("agente", "—")), body),
                    ag.get("tipo", ag.get("nr", "—")),
                    ag.get("metodo", ag.get("codigo_esocial", "—")),
                    ag.get("unidade", "—"),
                ])
            t2 = Table(ag_data, colWidths=[5*cm, 4*cm, 5*cm, 2.5*cm])
            t2.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), azul),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE3EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING",  (0, 0), (-1, -1), 3),
            ]))
            story.append(t2)
        else:
            story.append(Paragraph("Nenhum agente registrado.", body))

        # METODOLOGIA
        story.append(Paragraph("3. METODOLOGIA DE AVALIAÇÃO", h2))
        story.append(Paragraph(laudo.metodologia or "—", body))

        # RESULTADOS
        story.append(Paragraph("4. RESULTADOS E ANÁLISE", h2))
        if laudo.resultados:
            for r in laudo.resultados:
                story.append(Paragraph(f"• {r}", body))
        else:
            story.append(Paragraph("Resultados a serem preenchidos.", body))

        # CONCLUSÃO
        story.append(Paragraph("5. CONCLUSÃO", h2))
        if laudo.tipo in ("lip", "ltip") and laudo.grau_insalubridade:
            story.append(Paragraph(
                f"<b>Grau de Insalubridade:</b> {laudo.grau_insalubridade.upper()} — "
                f"Adicional de {laudo.adicional_pct}% sobre o salário mínimo.",
                body))
        story.append(Paragraph(laudo.conclusao or "Conclusão a ser preenchida.", body))

        story.append(Spacer(1, 1.5*cm))
        story.append(HRFlowable(width="50%", thickness=0.5, color=azul))
        story.append(Paragraph(
            f"Responsável Técnico: {laudo.responsavel_tecnico or '—'}<br/>"
            f"Registro: {laudo.conselho_registro or '—'}",
            sub))

        doc.build(story)
        buf.seek(0)
        nome_arquivo = f"{laudo.tipo.upper()}_{empresa.nome.replace(' ','_')}_{laudo.data_emissao}.pdf"
        resp = HttpResponse(buf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
        return resp
    except ImportError:
        return JsonResponse({"erro": "ReportLab não instalado"}, status=500)
    except LaudoTecnicoSST.DoesNotExist:
        return JsonResponse({"erro": "Laudo não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
@api_requer_feature("sst.laudos_tecnicos")
def api_laudos_kpis(request):
    """Painel de validade dos laudos — alertas de vencimento."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import LaudoTecnicoSST
        hoje = date.today()
        laudos = LaudoTecnicoSST.objects.filter(empresa=empresa)
        total = laudos.count()

        resumo = []
        for tipo, label in TIPOS_LAUDO.items():
            laudo = laudos.filter(tipo=tipo, status="vigente").order_by("-data_emissao").first()
            anos = VALIDADE_ANOS.get(tipo, 2)
            if laudo and laudo.data_emissao:
                venc = laudo.data_emissao.replace(year=laudo.data_emissao.year + anos)
                dias = (venc - hoje).days
                status_val = "vencido" if dias < 0 else ("alerta" if dias <= 60 else "ok")
            else:
                venc = None
                dias = None
                status_val = "sem_laudo"

            resumo.append({
                "tipo": tipo,
                "label": label.split("—")[0].strip(),
                "tem_laudo": laudo is not None,
                "data_emissao": str(laudo.data_emissao) if laudo else None,
                "data_vencimento": str(venc) if venc else None,
                "dias_para_vencer": dias,
                "status_validade": status_val,
            })

        return JsonResponse({
            "total_laudos": total,
            "resumo_por_tipo": resumo,
            "alertas_criticos": [r for r in resumo if r["status_validade"] in ("vencido", "sem_laudo")],
            "alertas_atencao": [r for r in resumo if r["status_validade"] == "alerta"],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ── Página HTML ───────────────────────────────────────────────────────────────

from .access_control import requer_permissao_modulo, requer_feature_pacote


@requer_feature_pacote("sst.laudos_tecnicos", "Laudos Técnicos")
@requer_permissao_modulo("sst.clinico")
def sst_laudos_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_laudos.html", {
        "empresa_nome": empresa.nome,
    })
