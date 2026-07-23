"""
Relatórios PDF SST — SoloCRT
Endpoints que geram PDFs com ReportLab para módulo SST.
"""
import io
from datetime import date

from django.http import HttpResponse, JsonResponse

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)

from .models import FuncionarioSST, ASOOcupacional, CATOcupacional, TreinamentoNR

# ──────────────────────────────────────────────────────────
# Estilos / helpers
# ──────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = 1.5 * cm

DARK_BG   = colors.HexColor("#111827")
ACCENT    = colors.HexColor("#0ea5e9")
HEADER_BG = colors.HexColor("#0f172a")
ROW_ALT   = colors.HexColor("#f8fafc")
RED_CELL  = colors.HexColor("#fef2f2")
RED_TEXT  = colors.HexColor("#991b1b")
GREY_TEXT = colors.HexColor("#64748b")
WHITE     = colors.white
BLACK     = colors.HexColor("#0f172a")


def _styles():
    ss = getSampleStyleSheet()
    title = ParagraphStyle(
        "title",
        parent=ss["Normal"],
        fontSize=18,
        fontName="Helvetica-Bold",
        textColor=WHITE,
        spaceAfter=2,
    )
    subtitle = ParagraphStyle(
        "subtitle",
        parent=ss["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.HexColor("#94a3b8"),
    )
    normal = ParagraphStyle(
        "normal_sst",
        parent=ss["Normal"],
        fontSize=9,
        fontName="Helvetica",
        textColor=BLACK,
    )
    footer_style = ParagraphStyle(
        "footer_sst",
        parent=ss["Normal"],
        fontSize=8,
        fontName="Helvetica",
        textColor=GREY_TEXT,
        alignment=1,  # centre
    )
    return title, subtitle, normal, footer_style


def _build_header_footer(canvas, doc, empresa_nome, titulo):
    """Desenha cabeçalho e rodapé em cada página."""
    canvas.saveState()
    # — cabeçalho
    canvas.setFillColor(HEADER_BG)
    canvas.rect(0, PAGE_H - 70, PAGE_W, 70, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 70, 5, 70, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(MARGIN + 4, PAGE_H - 30, "SoloCRT SST")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawString(MARGIN + 4, PAGE_H - 48, empresa_nome)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor("#e2e8f0"))
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 30, titulo)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 48, f"Página {doc.page}")
    # — linha separadora
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(1)
    canvas.line(MARGIN, PAGE_H - 72, PAGE_W - MARGIN, PAGE_H - 72)
    # — rodapé
    today_str = date.today().strftime("%d/%m/%Y")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY_TEXT)
    canvas.drawString(MARGIN, 18, f"Gerado em {today_str}  •  Gerado pelo SoloCRT SST")
    canvas.drawRightString(PAGE_W - MARGIN, 18, "Documento confidencial — uso interno")
    canvas.restoreState()


def _table_style_base(header_cols):
    """TableStyle padrão com zebra."""
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ROW_ALT]),
        ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 1), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 0), (-1, 0), [ACCENT]),
    ]
    return TableStyle(cmds)


def _pdf_response(buffer, filename):
    buffer.seek(0)
    pdf_bytes = buffer.read()
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ──────────────────────────────────────────────────────────
# 1. Relatório de Funcionários
# ──────────────────────────────────────────────────────────

def relatorio_pdf_funcionarios(request):
    empresa = getattr(request, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).order_by("nome")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.8 * cm, bottomMargin=1.5 * cm,
    )

    title_style, subtitle_style, normal_style, footer_style = _styles()

    header_fn = lambda c, d: _build_header_footer(c, d, empresa.nome, "Relatório de Funcionários")

    # cabeçalho da tabela
    col_headers = ["Nome", "CPF", "Cargo", "Setor", "Admissão", "Classe Risco"]
    rows = [col_headers]
    for f in funcionarios:
        admissao = f.data_admissao.strftime("%d/%m/%Y") if f.data_admissao else "—"
        rows.append([
            f.nome,
            f.cpf or "—",
            f.cargo,
            f.setor or "—",
            admissao,
            f.get_classe_risco_display() if f.classe_risco else "—",
        ])

    if len(rows) == 1:
        rows.append(["Nenhum funcionário ativo encontrado.", "", "", "", "", ""])

    col_widths = [
        (PAGE_W - 2 * MARGIN) * p
        for p in [0.28, 0.14, 0.19, 0.15, 0.12, 0.12]
    ]

    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(_table_style_base(len(col_headers)))

    intro = Paragraph(
        f"Total de funcionários ativos: <b>{funcionarios.count()}</b>",
        ParagraphStyle("intro", fontSize=9, fontName="Helvetica", textColor=GREY_TEXT, spaceAfter=10),
    )

    story = [Spacer(1, 0.2 * cm), intro, t]
    doc.build(story, onFirstPage=header_fn, onLaterPages=header_fn)

    safe_name = empresa.nome.replace(" ", "-").replace("/", "-")
    return _pdf_response(buffer, f"funcionarios-{safe_name}.pdf")


# ──────────────────────────────────────────────────────────
# 2. Relatório de ASOs
# ──────────────────────────────────────────────────────────

def relatorio_pdf_asos(request):
    empresa = getattr(request, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    asos = ASOOcupacional.objects.filter(empresa=empresa).select_related("funcionario").order_by("-data_emissao")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.8 * cm, bottomMargin=1.5 * cm,
    )

    header_fn = lambda c, d: _build_header_footer(c, d, empresa.nome, "Relatório de ASOs")
    title_style, subtitle_style, normal_style, footer_style = _styles()

    today = date.today()

    col_headers = ["Funcionário", "Tipo", "Realização", "Validade", "Resultado", "Médico", "Status"]
    rows = [col_headers]
    vencidos_idx = []  # linhas com vencimento (índice no rows)

    for aso in asos:
        validade_str = aso.data_validade.strftime("%d/%m/%Y") if aso.data_validade else "—"
        realizacao_str = aso.data_emissao.strftime("%d/%m/%Y")

        if aso.data_validade:
            delta = (aso.data_validade - today).days
            if delta < 0:
                status_aso = "Vencido"
            elif delta <= 30:
                status_aso = "A vencer"
            else:
                status_aso = "Vigente"
        else:
            delta = None
            status_aso = "Sem validade"

        row = [
            aso.funcionario.nome,
            aso.get_tipo_display(),
            realizacao_str,
            validade_str,
            aso.get_resultado_display(),
            aso.medico_responsavel or "—",
            status_aso,
        ]
        rows.append(row)
        if status_aso == "Vencido":
            vencidos_idx.append(len(rows) - 1)

    if len(rows) == 1:
        rows.append(["Nenhum ASO encontrado.", "", "", "", "", "", ""])

    col_widths = [
        (PAGE_W - 2 * MARGIN) * p
        for p in [0.22, 0.12, 0.10, 0.10, 0.12, 0.20, 0.14]
    ]

    style_cmds = _table_style_base(len(col_headers)).getCommands()

    # Destacar vencidos em vermelho
    for idx in vencidos_idx:
        style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), RED_CELL))
        style_cmds.append(("TEXTCOLOR",  (0, idx), (-1, idx), RED_TEXT))
        style_cmds.append(("FONTNAME",   (0, idx), (-1, idx), "Helvetica-Bold"))

    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style_cmds))

    total = asos.count()
    vencidos_count = len(vencidos_idx)
    intro = Paragraph(
        f"Total de ASOs: <b>{total}</b> — Vencidos: <b>{vencidos_count}</b>  "
        f"(destacados em vermelho)",
        ParagraphStyle("intro", fontSize=9, fontName="Helvetica", textColor=GREY_TEXT, spaceAfter=10),
    )

    story = [Spacer(1, 0.2 * cm), intro, t]
    doc.build(story, onFirstPage=header_fn, onLaterPages=header_fn)

    safe_name = empresa.nome.replace(" ", "-").replace("/", "-")
    return _pdf_response(buffer, f"asos-{safe_name}.pdf")


# ──────────────────────────────────────────────────────────
# 3. Relatório de CATs
# ──────────────────────────────────────────────────────────

def relatorio_pdf_cats(request):
    empresa = getattr(request, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    cats = CATOcupacional.objects.filter(empresa=empresa).select_related("funcionario").order_by("-data_acidente")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.8 * cm, bottomMargin=1.5 * cm,
    )

    header_fn = lambda c, d: _build_header_footer(c, d, empresa.nome, "Relatório de CATs")

    col_headers = ["Funcionário", "Tipo", "Data", "Gravidade", "CID", "Status eSocial"]
    rows = [col_headers]

    for cat in cats:
        rows.append([
            cat.funcionario.nome,
            cat.get_tipo_display(),
            cat.data_acidente.strftime("%d/%m/%Y"),
            cat.get_gravidade_display(),
            cat.cid or "—",
            cat.get_status_esocial_display(),
        ])

    if len(rows) == 1:
        rows.append(["Nenhuma CAT encontrada.", "", "", "", "", ""])

    col_widths = [
        (PAGE_W - 2 * MARGIN) * p
        for p in [0.28, 0.13, 0.11, 0.13, 0.10, 0.25]
    ]

    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(_table_style_base(len(col_headers)))

    intro = Paragraph(
        f"Total de CATs registradas: <b>{cats.count()}</b>",
        ParagraphStyle("intro", fontSize=9, fontName="Helvetica", textColor=GREY_TEXT, spaceAfter=10),
    )

    story = [Spacer(1, 0.2 * cm), intro, t]
    doc.build(story, onFirstPage=header_fn, onLaterPages=header_fn)

    safe_name = empresa.nome.replace(" ", "-").replace("/", "-")
    return _pdf_response(buffer, f"cats-{safe_name}.pdf")


# ──────────────────────────────────────────────────────────
# 4. Relatório de Treinamentos NR
# ──────────────────────────────────────────────────────────

def relatorio_pdf_treinamentos(request):
    empresa = getattr(request, "empresa", None)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    treinamentos = (
        TreinamentoNR.objects
        .filter(empresa=empresa)
        .select_related("funcionario")
        .order_by("funcionario__nome", "nr")
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.8 * cm, bottomMargin=1.5 * cm,
    )

    header_fn = lambda c, d: _build_header_footer(c, d, empresa.nome, "Relatório de Treinamentos NR")

    col_headers = ["Funcionário", "NR", "Título", "Realização", "Validade", "Status"]
    rows = [col_headers]

    for tr in treinamentos:
        realizacao = tr.data_realizacao.strftime("%d/%m/%Y") if tr.data_realizacao else "—"
        validade   = tr.data_validade.strftime("%d/%m/%Y")   if tr.data_validade   else "—"
        rows.append([
            tr.funcionario.nome,
            tr.nr,
            tr.titulo or tr.get_nr_display(),
            realizacao,
            validade,
            tr.get_status_display(),
        ])

    if len(rows) == 1:
        rows.append(["Nenhum treinamento encontrado.", "", "", "", "", ""])

    col_widths = [
        (PAGE_W - 2 * MARGIN) * p
        for p in [0.26, 0.08, 0.28, 0.12, 0.12, 0.14]
    ]

    style_cmds = _table_style_base(len(col_headers)).getCommands()

    # Destacar vencidos
    today = date.today()
    for i, tr in enumerate(treinamentos, start=1):
        if tr.status == "vencido" or (tr.data_validade and tr.data_validade < today):
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), RED_CELL))
            style_cmds.append(("TEXTCOLOR",  (0, i), (-1, i), RED_TEXT))

    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style_cmds))

    intro = Paragraph(
        f"Total de registros de treinamento: <b>{treinamentos.count()}</b>",
        ParagraphStyle("intro", fontSize=9, fontName="Helvetica", textColor=GREY_TEXT, spaceAfter=10),
    )

    story = [Spacer(1, 0.2 * cm), intro, t]
    doc.build(story, onFirstPage=header_fn, onLaterPages=header_fn)

    safe_name = empresa.nome.replace(" ", "-").replace("/", "-")
    return _pdf_response(buffer, f"treinamentos-{safe_name}.pdf")
