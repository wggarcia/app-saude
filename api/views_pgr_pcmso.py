"""
PGR (Programa de Gerenciamento de Riscos) e PCMSO (Programa de Controle Médico de Saúde Ocupacional)
Geração automática de documentos e PDFs — SolusCRT SST.

Endpoints:
  POST /api/sst/pgr/gerar/            — gera PGR automático
  GET  /api/sst/pgr/<id>/pdf/         — exporta PDF do PGR
  POST /api/sst/pcmso/gerar/          — gera PCMSO automático
  GET  /api/sst/pcmso/<id>/pdf/       — exporta PDF do PCMSO
"""
import io
import json
from datetime import date, timedelta

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

from .access_control import api_requer_feature, requer_permissao_modulo, requer_feature_pacote

# ── Palette ──────────────────────────────────────────────────────────────────
TEAL  = colors.HexColor("#00c9a7")
DARK  = colors.HexColor("#071c28")
MUTED = colors.HexColor("#7a9fa0")
WHITE = colors.white
BLACK = colors.black
LGREY = colors.HexColor("#f4f8f7")

W, H = A4


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def _styles():
    return {
        "title":  ParagraphStyle("title",  fontSize=16, fontName="Helvetica-Bold", textColor=DARK,  leading=20, spaceAfter=4),
        "sub":    ParagraphStyle("sub",    fontSize=9,  fontName="Helvetica",      textColor=MUTED, leading=13, spaceAfter=6),
        "h2":     ParagraphStyle("h2",     fontSize=11, fontName="Helvetica-Bold", textColor=DARK,  leading=15, spaceBefore=10, spaceAfter=4),
        "label":  ParagraphStyle("label",  fontSize=8,  fontName="Helvetica-Bold", textColor=MUTED, leading=11),
        "value":  ParagraphStyle("value",  fontSize=10, fontName="Helvetica",      textColor=BLACK, leading=14, spaceBefore=1, spaceAfter=4),
        "small":  ParagraphStyle("small",  fontSize=8,  fontName="Helvetica",      textColor=MUTED, leading=11),
        "center": ParagraphStyle("center", fontSize=9,  fontName="Helvetica",      textColor=MUTED, leading=13, alignment=1),
        "bold":   ParagraphStyle("bold",   fontSize=10, fontName="Helvetica-Bold", textColor=BLACK, leading=14),
    }


def _header_empresa(story, empresa_nome, titulo, subtitulo, styles):
    header_data = [[
        Paragraph("<b>SolusCRT</b>", ParagraphStyle("logo", fontName="Helvetica-Bold", fontSize=14, textColor=TEAL, leading=18)),
        Paragraph(empresa_nome, ParagraphStyle("en", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13, alignment=2)),
    ]]
    ht = Table(header_data, colWidths=[W * 0.5 - 2 * cm, W * 0.5 - 2 * cm])
    ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=2, color=TEAL, spaceAfter=8))
    story.append(Paragraph(titulo, styles["title"]))
    story.append(Paragraph(subtitulo, styles["sub"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=10))


def _footer_text(styles, norma):
    hoje = date.today().strftime("%d/%m/%Y")
    return Paragraph(
        f"Gerado por SolusCRT em {hoje} · Documento eletrônico — {norma}",
        styles["center"]
    )


def _table_style_base():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LGREY]),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0e8e4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])


# ── PGR ──────────────────────────────────────────────────────────────────────

@api_requer_feature("sst.pgr_ppra")
def api_pgr_gerar(request):
    """POST — gera PGR automático com dados da empresa."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        from .models import RiscoOcupacional, PostoTrabalho, DocumentoSST

        riscos = list(
            RiscoOcupacional.objects.filter(empresa=empresa)
            .values("id", "descricao", "tipo_risco", "nivel", "setor")[:100]
        )
        postos = list(
            PostoTrabalho.objects.filter(empresa=empresa, ativo=True)
            .values("id", "nome", "setor")[:50]
        )

        # Cria documento no banco
        doc = DocumentoSST.objects.create(
            empresa=empresa,
            tipo="PGR",
            titulo=f"PGR — {empresa.nome} — {date.today().strftime('%m/%Y')}",
            status="vigente",
            responsavel_tecnico=getattr(empresa, "responsavel_tecnico", "") or empresa.nome,
            data_emissao=date.today(),
            data_validade=date.today().replace(year=date.today().year + 2),
            observacoes=f"Gerado automaticamente. Riscos identificados: {len(riscos)}. Postos: {len(postos)}.",
        )

        return JsonResponse({
            "ok": True,
            "data": {
                "id": doc.id,
                "titulo": doc.titulo,
                "data_emissao": str(doc.data_emissao),
                "data_validade": str(doc.data_validade),
                "total_riscos": len(riscos),
                "total_postos": len(postos),
                "cnae": getattr(empresa, "cnae", "") or "",
                "grau_risco": getattr(empresa, "grau_risco", 2) or 2,
            }
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.pgr_ppra")
def api_pgr_pdf(request, doc_id):
    """GET — gera PDF do PGR."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import DocumentoSST, RiscoOcupacional, PostoTrabalho

        doc = DocumentoSST.objects.get(id=doc_id, empresa=empresa, tipo="PGR")
        riscos = list(
            RiscoOcupacional.objects.filter(empresa=empresa)
            .values("descricao", "tipo_risco", "nivel", "setor")[:100]
        )
        postos = list(
            PostoTrabalho.objects.filter(empresa=empresa, ativo=True)
            .values("nome", "setor")[:50]
        )

        buf = io.BytesIO()
        styles = _styles()

        pdf = SimpleDocTemplate(
            buf, pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        story = []

        # Cabeçalho
        _header_empresa(
            story, empresa.nome,
            "Programa de Gerenciamento de Riscos — PGR",
            f"NR-01 / Portaria MTE 1.419/2024 · Emissão: {doc.data_emissao.strftime('%d/%m/%Y') if doc.data_emissao else '—'} · Validade: {doc.data_validade.strftime('%d/%m/%Y') if doc.data_validade else '—'}",
            styles
        )

        # Dados da empresa
        story.append(Paragraph("1. Identificação da Empresa", styles["h2"]))
        emp_data = [
            ["Campo", "Informação"],
            ["Razão Social", empresa.nome],
            ["CNAE", getattr(empresa, "cnae", "") or "—"],
            ["Grau de Risco", str(getattr(empresa, "grau_risco", 2) or 2)],
            ["Endereço", getattr(empresa, "endereco", "") or "—"],
            ["Responsável Técnico", doc.responsavel_tecnico or empresa.nome],
            ["Registro Profissional", doc.registro_profissional or "—"],
        ]
        t = Table(emp_data, colWidths=[5 * cm, W - 9 * cm])
        t.setStyle(_table_style_base())
        story.append(t)
        story.append(Spacer(1, 12))

        # Inventário de riscos
        story.append(Paragraph("2. Inventário de Riscos Ocupacionais", styles["h2"]))
        if riscos:
            risco_data = [["Descrição", "Tipo", "Nível", "Setor"]]
            for r in riscos:
                risco_data.append([
                    r.get("descricao", "—"),
                    (r.get("tipo_risco") or "—").capitalize(),
                    (r.get("nivel") or "—").capitalize(),
                    r.get("setor", "—") or "Geral",
                ])
            t2 = Table(risco_data, colWidths=[7 * cm, 3 * cm, 3 * cm, W - 15 * cm])
            t2.setStyle(_table_style_base())
            story.append(t2)
        else:
            story.append(Paragraph("Nenhum risco cadastrado.", styles["small"]))
        story.append(Spacer(1, 12))

        # Planos de ação
        story.append(Paragraph("3. Planos de Ação", styles["h2"]))
        story.append(Paragraph(
            "Os planos de ação devem ser elaborados para cada risco identificado no inventário, "
            "com responsáveis, prazos e indicadores de controle conforme NR-01.",
            styles["value"]
        ))
        story.append(Spacer(1, 8))

        # Postos de trabalho
        story.append(Paragraph("4. Postos de Trabalho Avaliados", styles["h2"]))
        if postos:
            posto_data = [["Nome do Posto", "Setor"]]
            for p in postos:
                posto_data.append([p.get("nome", "—"), p.get("setor", "—") or "Geral"])
            t3 = Table(posto_data, colWidths=[10 * cm, W - 12 * cm])
            t3.setStyle(_table_style_base())
            story.append(t3)
        else:
            story.append(Paragraph("Nenhum posto de trabalho cadastrado.", styles["small"]))
        story.append(Spacer(1, 12))

        # Rodapé
        story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=6))
        story.append(_footer_text(styles, "NR-01 · Portaria MTE 1.419/2024"))

        pdf.build(story)
        buf.seek(0)

        nome_arquivo = f"PGR_{empresa.nome.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf"
        resp = HttpResponse(buf.read(), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
        return resp

    except DocumentoSST.DoesNotExist:
        return JsonResponse({"erro": "PGR não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ── PCMSO ─────────────────────────────────────────────────────────────────────

@api_requer_feature("sst.pgr_ppra")
def api_pcmso_gerar(request):
    """POST — gera PCMSO automático."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        from .models import FuncionarioSST, ASOOcupacional, DocumentoSST

        funcionarios_ativos = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        asos_recentes = ASOOcupacional.objects.filter(empresa=empresa).order_by("-data_exame")[:10]
        total_asos = asos_recentes.count()

        doc = DocumentoSST.objects.create(
            empresa=empresa,
            tipo="PCMSO",
            titulo=f"PCMSO — {empresa.nome} — {date.today().strftime('%m/%Y')}",
            status="vigente",
            responsavel_tecnico=getattr(empresa, "medico_responsavel", "") or empresa.nome,
            data_emissao=date.today(),
            data_validade=date.today().replace(year=date.today().year + 1),
            observacoes=f"Gerado automaticamente. Funcionários: {funcionarios_ativos}. ASOs recentes: {total_asos}.",
        )

        return JsonResponse({
            "ok": True,
            "data": {
                "id": doc.id,
                "titulo": doc.titulo,
                "data_emissao": str(doc.data_emissao),
                "data_validade": str(doc.data_validade),
                "total_funcionarios": funcionarios_ativos,
                "total_asos_recentes": total_asos,
            }
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.pgr_ppra")
def api_pcmso_pdf(request, doc_id):
    """GET — gera PDF do PCMSO."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import DocumentoSST, FuncionarioSST, ASOOcupacional

        doc = DocumentoSST.objects.get(id=doc_id, empresa=empresa, tipo="PCMSO")
        funcionarios = list(
            FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
            .values("nome", "cargo", "setor", "data_admissao")[:100]
        )
        asos = list(
            ASOOcupacional.objects.filter(empresa=empresa)
            .order_by("-data_exame")
            .values("funcionario__nome", "tipo_aso", "data_exame", "resultado", "proxima_avaliacao")[:50]
        )

        buf = io.BytesIO()
        styles = _styles()

        pdf = SimpleDocTemplate(
            buf, pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        story = []

        _header_empresa(
            story, empresa.nome,
            "Programa de Controle Médico de Saúde Ocupacional — PCMSO",
            f"NR-7 / CLT art. 168 · Emissão: {doc.data_emissao.strftime('%d/%m/%Y') if doc.data_emissao else '—'} · Validade: {doc.data_validade.strftime('%d/%m/%Y') if doc.data_validade else '—'}",
            styles
        )

        # Identificação
        story.append(Paragraph("1. Identificação da Empresa e Responsável", styles["h2"]))
        emp_data = [
            ["Campo", "Informação"],
            ["Razão Social", empresa.nome],
            ["Médico Responsável", doc.responsavel_tecnico or "—"],
            ["Registro CRM", doc.registro_profissional or "—"],
            ["Vigência", f"{doc.data_emissao.strftime('%d/%m/%Y') if doc.data_emissao else '—'} a {doc.data_validade.strftime('%d/%m/%Y') if doc.data_validade else '—'}"],
        ]
        t = Table(emp_data, colWidths=[5 * cm, W - 9 * cm])
        t.setStyle(_table_style_base())
        story.append(t)
        story.append(Spacer(1, 12))

        # Quadro de funcionários
        story.append(Paragraph("2. Quadro de Funcionários Ativos", styles["h2"]))
        if funcionarios:
            func_data = [["Nome", "Cargo", "Setor", "Admissão"]]
            for f in funcionarios:
                func_data.append([
                    f.get("nome", "—"),
                    f.get("cargo", "—"),
                    f.get("setor", "—") or "—",
                    str(f.get("data_admissao", "") or "—"),
                ])
            t2 = Table(func_data, colWidths=[6 * cm, 4 * cm, 4 * cm, 3 * cm])
            t2.setStyle(_table_style_base())
            story.append(t2)
        else:
            story.append(Paragraph("Nenhum funcionário ativo cadastrado.", styles["small"]))
        story.append(Spacer(1, 12))

        # Cronograma de exames
        story.append(Paragraph("3. Cronograma de Exames Periódicos", styles["h2"]))
        if asos:
            aso_data = [["Funcionário", "Tipo ASO", "Realizado", "Resultado", "Próxima Avaliação"]]
            for a in asos:
                aso_data.append([
                    a.get("funcionario__nome", "—"),
                    a.get("tipo_aso", "—"),
                    str(a.get("data_exame", "") or "—"),
                    a.get("resultado", "—"),
                    str(a.get("proxima_avaliacao", "") or "—"),
                ])
            t3 = Table(aso_data, colWidths=[5 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
            t3.setStyle(_table_style_base())
            story.append(t3)
        else:
            story.append(Paragraph("Nenhum ASO registrado.", styles["small"]))
        story.append(Spacer(1, 12))

        # Rodapé
        story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=6))
        story.append(_footer_text(styles, "NR-7 / CLT art. 168"))

        pdf.build(story)
        buf.seek(0)

        nome_arquivo = f"PCMSO_{empresa.nome.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf"
        resp = HttpResponse(buf.read(), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
        return resp

    except DocumentoSST.DoesNotExist:
        return JsonResponse({"erro": "PCMSO não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@requer_feature_pacote("sst.pgr_ppra", "PGR/PCMSO")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_pgr_page(request):
    """Página PGR/PCMSO — renderiza template."""
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada

    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_pgr.html", {"empresa_nome": empresa.nome})
