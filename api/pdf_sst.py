"""
Geração de PDF para o módulo SST — usa ReportLab (já instalado).
"""
import io
from datetime import date

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette ───────────────────────────────────────────────────────────────────
TEAL   = colors.HexColor("#00c9a7")
DARK   = colors.HexColor("#071c28")
MUTED  = colors.HexColor("#7a9fa0")
WHITE  = colors.white
BLACK  = colors.black
AMBER  = colors.HexColor("#f0bf6b")
RED    = colors.HexColor("#f87171")
LGREY  = colors.HexColor("#f4f8f7")

W, H = A4


def _styles():
    # base sem textColor para evitar conflito ao sobrescrever por estilo
    base = dict(leading=14)
    return {
        "title":   ParagraphStyle("title",   **base, fontSize=16, fontName="Helvetica-Bold", textColor=DARK,  spaceAfter=2),
        "sub":     ParagraphStyle("sub",     **base, fontSize=9,  fontName="Helvetica",      textColor=MUTED, spaceAfter=6),
        "h2":      ParagraphStyle("h2",      **base, fontSize=11, fontName="Helvetica-Bold", textColor=DARK,  spaceBefore=10, spaceAfter=4),
        "label":   ParagraphStyle("label",   **base, fontSize=8,  fontName="Helvetica-Bold", textColor=MUTED),
        "value":   ParagraphStyle("value",   **base, fontSize=10, fontName="Helvetica",      textColor=BLACK, spaceBefore=1, spaceAfter=4),
        "small":   ParagraphStyle("small",   **base, fontSize=8,  fontName="Helvetica",      textColor=MUTED),
        "center":  ParagraphStyle("center",  **base, fontSize=9,  fontName="Helvetica",      alignment=TA_CENTER, textColor=MUTED),
        "bold":    ParagraphStyle("bold",    **base, fontSize=10, fontName="Helvetica-Bold", textColor=BLACK),
        "result":  ParagraphStyle("result",  **base, fontSize=13, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=BLACK),
    }


def _header_empresa(story, empresa_nome, titulo, subtitulo, styles):
    # Logotipo/cabeçalho
    header_data = [[
        Paragraph(f"<b>SolusCRT</b>", ParagraphStyle("logo", fontName="Helvetica-Bold", fontSize=14, textColor=TEAL)),
        Paragraph(empresa_nome, ParagraphStyle("en", fontName="Helvetica", fontSize=9, textColor=MUTED, alignment=TA_RIGHT)),
    ]]
    ht = Table(header_data, colWidths=[W*0.5 - 2*cm, W*0.5 - 2*cm])
    ht.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=2, color=TEAL, spaceAfter=8))
    story.append(Paragraph(titulo, styles["title"]))
    story.append(Paragraph(subtitulo, styles["sub"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=10))


def _footer_text(styles):
    hoje = date.today().strftime("%d/%m/%Y")
    return Paragraph(
        f"Gerado por SolusCRT em {hoje} · Documento eletrônico — NR-7 / CLT art. 168",
        styles["center"]
    )


def _field_row(label, value, styles):
    return [
        Paragraph(label, styles["label"]),
        Paragraph(str(value or "—"), styles["value"]),
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  ASO — Atestado de Saúde Ocupacional
# ─────────────────────────────────────────────────────────────────────────────

def gerar_pdf_aso(aso, funcionario, empresa_nome, config=None):
    """Retorna bytes do PDF do ASO."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"ASO — {funcionario.nome}",
    )
    styles = _styles()
    story = []

    tipo_labels = {
        "admissional":     "Admissional",
        "periodico":       "Periódico",
        "retorno_trabalho":"Retorno ao Trabalho",
        "mudanca_risco":   "Mudança de Risco",
        "demissional":     "Demissional",
    }
    resultado_labels = {
        "apto":            "APTO",
        "apto_restricao":  "APTO COM RESTRIÇÃO",
        "inapto":          "INAPTO",
    }

    _header_empresa(
        story, empresa_nome,
        "Atestado de Saúde Ocupacional — ASO",
        f"Tipo: {tipo_labels.get(aso.tipo, aso.tipo)}  ·  Emissão: {aso.data_emissao.strftime('%d/%m/%Y') if aso.data_emissao else '—'}",
        styles,
    )

    # Dados do funcionário
    story.append(Paragraph("DADOS DO TRABALHADOR", styles["h2"]))
    rows = [
        ["Nome completo", funcionario.nome,            "Matrícula", funcionario.matricula or "—"],
        ["CPF",           funcionario.cpf or "—",      "Data de nascimento", "—"],
        ["Cargo",         funcionario.cargo or "—",    "Setor", funcionario.setor or "—"],
        ["Admissão",      funcionario.data_admissao.strftime("%d/%m/%Y") if funcionario.data_admissao else "—",
         "Grau de risco", f"Grau {funcionario.classe_risco}" if funcionario.classe_risco else "—"],
    ]
    tbl_data = []
    for r in rows:
        tbl_data.append([
            Paragraph(r[0], styles["label"]), Paragraph(r[1], styles["value"]),
            Paragraph(r[2], styles["label"]), Paragraph(r[3], styles["value"]),
        ])
    t = Table(tbl_data, colWidths=[3.5*cm, 6*cm, 3.5*cm, 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LGREY),
        ("BACKGROUND", (2,0), (2,-1), LGREY),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#e0ecec")),
        ("VALIGN",     (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Dados do ASO
    story.append(Paragraph("DADOS DO EXAME", styles["h2"]))
    rows2 = [
        ["Tipo de exame",    tipo_labels.get(aso.tipo, aso.tipo),
         "Data de emissão",  aso.data_emissao.strftime("%d/%m/%Y") if aso.data_emissao else "—"],
        ["Data de validade", aso.data_validade.strftime("%d/%m/%Y") if aso.data_validade else "—",
         "Médico examinador", aso.medico_responsavel or (config.nome_medico_coordenador if config else "—")],
        ["CRM",              (config.crm_medico if config else "—"),
         "Especialidade",    (config.especialidade_medico if config else "Medicina do Trabalho")],
    ]
    tbl2_data = []
    for r in rows2:
        tbl2_data.append([
            Paragraph(r[0], styles["label"]), Paragraph(r[1], styles["value"]),
            Paragraph(r[2], styles["label"]), Paragraph(r[3], styles["value"]),
        ])
    t2 = Table(tbl2_data, colWidths=[3.5*cm, 6*cm, 3.5*cm, 4*cm])
    t2.setStyle(t.tblStyle if hasattr(t, "tblStyle") else TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LGREY),
        ("BACKGROUND", (2,0), (2,-1), LGREY),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#e0ecec")),
        ("VALIGN",     (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 16))

    # Resultado
    res = resultado_labels.get(aso.resultado, aso.resultado or "—")
    res_color = TEAL if aso.resultado == "apto" else (AMBER if aso.resultado == "apto_restricao" else RED)
    res_box = Table(
        [[Paragraph(res, ParagraphStyle("r", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, textColor=WHITE))]],
        colWidths=[W - 4*cm],
    )
    res_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), res_color),
        ("TOPPADDING",    (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(res_box)
    story.append(Spacer(1, 20))

    # Observações
    if aso.observacoes:
        story.append(Paragraph("OBSERVAÇÕES / RESTRIÇÕES", styles["h2"]))
        story.append(Paragraph(aso.observacoes, styles["value"]))
        story.append(Spacer(1, 10))

    # Assinaturas
    story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceBefore=20))
    sig_data = [[
        Paragraph("_________________________\nMédico Examinador\nCRM: " + (config.crm_medico if config else ""), styles["center"]),
        Paragraph("_________________________\nTrabalhador\nAssinatura", styles["center"]),
        Paragraph("_________________________\nEmpresa / SESMT\nAssinatura", styles["center"]),
    ]]
    sig = Table(sig_data, colWidths=[(W - 4*cm)/3]*3)
    sig.setStyle(TableStyle([("TOPPADDING", (0,0), (-1,-1), 30)]))
    story.append(sig)
    story.append(Spacer(1, 16))
    story.append(_footer_text(styles))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  CAT — Comunicação de Acidente de Trabalho
# ─────────────────────────────────────────────────────────────────────────────

def gerar_pdf_cat(cat, funcionario, empresa_nome, config=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"CAT — {funcionario.nome}",
    )
    styles = _styles()
    story = []

    tipo_labels     = {"tipico":"Típico","trajeto":"De Trajeto","doenca":"Doença Ocupacional"}
    grav_labels     = {"leve":"Leve","moderado":"Moderado","grave":"Grave","fatal":"Fatal"}

    _header_empresa(
        story, empresa_nome,
        "Comunicação de Acidente de Trabalho — CAT",
        f"Nº {cat.numero_cat or 'Não registrado'}  ·  Emissão: {date.today().strftime('%d/%m/%Y')}",
        styles,
    )

    def info_table(rows_data):
        tbl_data = []
        for r in rows_data:
            tbl_data.append([
                Paragraph(r[0], styles["label"]), Paragraph(str(r[1] or "—"), styles["value"]),
                Paragraph(r[2], styles["label"]), Paragraph(str(r[3] or "—"), styles["value"]),
            ])
        t = Table(tbl_data, colWidths=[3.5*cm, 6*cm, 3.5*cm, 4*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,-1), LGREY),
            ("BACKGROUND",    (2,0), (2,-1), LGREY),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e0ecec")),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ]))
        return t

    story.append(Paragraph("1. IDENTIFICAÇÃO DO ACIDENTADO", styles["h2"]))
    story.append(info_table([
        ["Nome",       funcionario.nome,        "Matrícula", funcionario.matricula or "—"],
        ["CPF",        funcionario.cpf or "—",  "Cargo",     funcionario.cargo or "—"],
        ["Setor",      funcionario.setor or "—","Admissão",  funcionario.data_admissao.strftime("%d/%m/%Y") if funcionario.data_admissao else "—"],
    ]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. DADOS DO ACIDENTE", styles["h2"]))
    story.append(info_table([
        ["Tipo",            tipo_labels.get(cat.tipo, cat.tipo or "—"),
         "Data do acidente", cat.data_acidente.strftime("%d/%m/%Y") if cat.data_acidente else "—"],
        ["Gravidade",       grav_labels.get(cat.gravidade, cat.gravidade or "—"),
         "CID",             cat.cid or "—"],
        ["Nº CAT",          cat.numero_cat or "Não registrado",
         "Houve afastamento", "Sim" if cat.houve_afastamento else "Não"],
    ]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. DESCRIÇÃO DO ACIDENTE", styles["h2"]))
    story.append(Paragraph(cat.descricao or "—", styles["value"]))
    story.append(Spacer(1, 8))

    story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceBefore=20))
    sig_data = [[
        Paragraph("_________________________\nEmitente / Empresa\nAssinatura e Carimbo", styles["center"]),
        Paragraph("_________________________\nTrabalhador ou Responsável\nAssinatura", styles["center"]),
    ]]
    sig = Table(sig_data, colWidths=[(W - 4*cm)/2]*2)
    sig.setStyle(TableStyle([("TOPPADDING", (0,0), (-1,-1), 30)]))
    story.append(sig)
    story.append(Spacer(1, 12))
    story.append(_footer_text(styles))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  Prontuário do Funcionário
# ─────────────────────────────────────────────────────────────────────────────

def gerar_pdf_prontuario(funcionario, asos, exames, cats, afastamentos, empresa_nome):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Prontuário — {funcionario.nome}",
    )
    styles = _styles()
    story = []

    _header_empresa(
        story, empresa_nome,
        f"Prontuário Ocupacional",
        f"{funcionario.nome}  ·  {funcionario.cargo or ''}  ·  Grau de Risco {funcionario.classe_risco or '—'}",
        styles,
    )

    # Identificação
    story.append(Paragraph("IDENTIFICAÇÃO", styles["h2"]))
    id_data = [
        [Paragraph("Nome",       styles["label"]), Paragraph(funcionario.nome, styles["value"]),
         Paragraph("Matrícula",  styles["label"]), Paragraph(funcionario.matricula or "—", styles["value"])],
        [Paragraph("CPF",        styles["label"]), Paragraph(funcionario.cpf or "—", styles["value"]),
         Paragraph("Cargo",      styles["label"]), Paragraph(funcionario.cargo or "—", styles["value"])],
        [Paragraph("Setor",      styles["label"]), Paragraph(funcionario.setor or "—", styles["value"]),
         Paragraph("Admissão",   styles["label"]), Paragraph(funcionario.data_admissao.strftime("%d/%m/%Y") if funcionario.data_admissao else "—", styles["value"])],
    ]
    id_t = Table(id_data, colWidths=[3.5*cm, 6*cm, 3.5*cm, 4*cm])
    id_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,-1), LGREY),
        ("BACKGROUND",    (2,0), (2,-1), LGREY),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e0ecec")),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ]))
    story.append(id_t)
    story.append(Spacer(1, 12))

    def simple_table(title, headers, rows_data, col_widths):
        story.append(Paragraph(title, styles["h2"]))
        if not rows_data:
            story.append(Paragraph("Nenhum registro.", styles["small"]))
            story.append(Spacer(1, 6))
            return
        header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE)) for h in headers]
        data = [header_row] + [[Paragraph(str(c or "—"), styles["small"]) for c in row] for row in rows_data]
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), DARK),
            ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#e0ecec")),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    tipo_aso = {"admissional":"Admissional","periodico":"Periódico","retorno_trabalho":"Retorno","mudanca_risco":"Mud. Risco","demissional":"Demissional"}
    res_aso  = {"apto":"Apto","apto_restricao":"Apto c/ restrição","inapto":"Inapto"}

    simple_table(
        f"ASOs ({len(asos)})",
        ["Tipo", "Data Emissão", "Validade", "Resultado", "Médico"],
        [[tipo_aso.get(a.tipo, a.tipo),
          a.data_emissao.strftime("%d/%m/%Y") if a.data_emissao else "—",
          a.data_validade.strftime("%d/%m/%Y") if a.data_validade else "—",
          res_aso.get(a.resultado, a.resultado or "—"),
          a.medico_responsavel or "—"] for a in asos],
        [3*cm, 3*cm, 3*cm, 4*cm, 4*cm],
    )

    simple_table(
        f"Exames ({len(exames)})",
        ["Tipo", "Realização", "Validade", "Status", "Resultado"],
        [[e.tipo_exame, e.data_realizacao.strftime("%d/%m/%Y") if e.data_realizacao else "—",
          e.data_validade.strftime("%d/%m/%Y") if e.data_validade else "—",
          e.status, e.resultado or "—"] for e in exames],
        [4*cm, 3*cm, 3*cm, 3*cm, 4*cm],
    )

    tipo_cat = {"tipico":"Típico","trajeto":"De Trajeto","doenca":"Doença Ocup."}
    simple_table(
        f"CATs ({len(cats)})",
        ["Tipo", "Data Acidente", "CID", "Gravidade", "Nº CAT"],
        [[tipo_cat.get(c.tipo, c.tipo or "—"),
          c.data_acidente.strftime("%d/%m/%Y") if c.data_acidente else "—",
          c.cid or "—", c.gravidade or "—", c.numero_cat or "Não reg."] for c in cats],
        [3*cm, 3*cm, 2.5*cm, 3*cm, 3*cm],
    )

    motivo_af = {"acidente_trabalho":"Acidente","doenca_ocupacional":"D. Ocup.","doenca_comum":"D. Comum","licenca_maternidade":"Maternidade","licenca_paternidade":"Paternidade","outro":"Outro"}
    simple_table(
        f"Afastamentos ({len(afastamentos)})",
        ["Motivo", "Início", "Retorno Previsto", "CID"],
        [[motivo_af.get(af.motivo, af.motivo or "—"),
          af.data_inicio.strftime("%d/%m/%Y") if af.data_inicio else "—",
          af.data_prevista_retorno.strftime("%d/%m/%Y") if af.data_prevista_retorno else "Em curso",
          af.cid or "—"] for af in afastamentos],
        [4.5*cm, 3*cm, 4*cm, 2.5*cm],
    )

    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  Ficha de EPI
# ─────────────────────────────────────────────────────────────────────────────

def gerar_pdf_ficha_epi(funcionario, entregas, empresa_nome):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Ficha EPI — {funcionario.nome}",
    )
    styles = _styles()
    story = []

    _header_empresa(
        story, empresa_nome,
        "Ficha de Controle de EPI",
        f"NR-6 · Comprovante de entrega e devolução de Equipamentos de Proteção Individual",
        styles,
    )

    story.append(Paragraph("TRABALHADOR", styles["h2"]))
    id_data = [[
        Paragraph("Nome", styles["label"]), Paragraph(funcionario.nome, styles["value"]),
        Paragraph("Matrícula", styles["label"]), Paragraph(funcionario.matricula or "—", styles["value"]),
        Paragraph("Cargo", styles["label"]), Paragraph(funcionario.cargo or "—", styles["value"]),
    ]]
    id_t = Table(id_data, colWidths=[2*cm, 5*cm, 2.5*cm, 3*cm, 2*cm, 3*cm])
    id_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LGREY), ("BACKGROUND", (2,0), (2,-1), LGREY), ("BACKGROUND", (4,0), (4,-1), LGREY),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e0ecec")),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4), ("LEFTPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(id_t)
    story.append(Spacer(1, 12))

    story.append(Paragraph("REGISTRO DE ENTREGAS E DEVOLUÇÕES", styles["h2"]))
    headers = ["EPI / Descrição", "CA Nº", "Validade CA", "Entrega", "Qtd", "Devolução", "Assinatura do Trabalhador"]
    header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7, textColor=WHITE)) for h in headers]
    rows = [header_row]
    for e in entregas:
        rows.append([
            Paragraph(e.epi.nome, styles["small"]),
            Paragraph(e.epi.ca_numero or "—", styles["small"]),
            Paragraph(e.epi.validade_ca.strftime("%d/%m/%Y") if e.epi.validade_ca else "—", styles["small"]),
            Paragraph(e.data_entrega.strftime("%d/%m/%Y"), styles["small"]),
            Paragraph(str(e.quantidade), styles["small"]),
            Paragraph(e.data_devolucao.strftime("%d/%m/%Y") if e.data_devolucao else "—", styles["small"]),
            Paragraph("", styles["small"]),  # assinatura
        ])
    # Add empty rows for future entries
    for _ in range(max(0, 8 - len(entregas))):
        rows.append([Paragraph("", styles["small"])]*7)

    epi_t = Table(rows, colWidths=[5*cm, 1.8*cm, 2*cm, 2*cm, 1*cm, 2*cm, 3.2*cm])
    epi_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), DARK),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#d0e8e4")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(epi_t)
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "Declaro que recebi os EPIs listados acima, estando ciente da obrigatoriedade de uso, "
        "guarda e conservação adequada, conforme NR-6 da Portaria MTb nº 3.214/78.",
        styles["small"]
    ))
    story.append(Spacer(1, 20))
    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()


def gerar_pdf_inspecoes_epi(inspecoes, empresa_nome):
    """Relatório de inspeções periódicas de EPI (teste dielétrico NR-10,
    talabarte/cinto NR-35 etc.) — lista consolidada para auditoria."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Relatório de Inspeções Periódicas de EPI",
    )
    styles = _styles()
    story = []
    _header_empresa(
        story, empresa_nome,
        "Relatório de Inspeções Periódicas de EPI",
        "Inspeção técnica periódica de EPIs especiais (ex: teste dielétrico NR-10, talabarte/cinto NR-35) — distinta da validade do CA",
        styles,
    )

    resultado_label = {"aprovado": "Aprovado", "reprovado": "Reprovado", "condicional": "Aprovado c/ ressalva"}
    contagem_resultado = {}
    for i in inspecoes:
        rotulo = resultado_label.get(i.resultado, i.resultado)
        contagem_resultado[rotulo] = contagem_resultado.get(rotulo, 0) + 1
    if contagem_resultado:
        story.append(_desenhar_grafico("pizza", list(contagem_resultado.keys()), list(contagem_resultado.values()), W - 3*cm))
        story.append(Spacer(1, 12))

    headers = ["Trabalhador", "EPI", "Nº Série", "Data Inspeção", "Resultado", "Responsável Técnico", "Próxima Inspeção"]
    header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7, textColor=WHITE)) for h in headers]
    rows = [header_row]
    for i in inspecoes:
        rows.append([
            Paragraph(i.entrega.funcionario.nome, styles["small"]),
            Paragraph(i.entrega.epi.nome, styles["small"]),
            Paragraph(i.entrega.numero_serie_item or "—", styles["small"]),
            Paragraph(i.data_inspecao.strftime("%d/%m/%Y"), styles["small"]),
            Paragraph(resultado_label.get(i.resultado, i.resultado), styles["small"]),
            Paragraph(i.responsavel_tecnico or "—", styles["small"]),
            Paragraph(i.proxima_inspecao.strftime("%d/%m/%Y") if i.proxima_inspecao else "—", styles["small"]),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("Nenhuma inspeção registrada no período.", styles["small"])] + [Paragraph("", styles["small"])]*6)

    t = Table(rows, colWidths=[3.2*cm, 3*cm, 2*cm, 2.3*cm, 2.6*cm, 3*cm, 2.4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), DARK),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#d0e8e4")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()


def gerar_pdf_calibracao_instrumentos(instrumentos, empresa_nome):
    """Relatório de calibração rastreável dos instrumentos de medição usados
    em inspeções/avaliações de SST (decibelímetro, luxímetro etc.)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Relatório de Calibração de Instrumentos",
    )
    styles = _styles()
    story = []
    _header_empresa(
        story, empresa_nome,
        "Relatório de Calibração de Instrumentos de Medição",
        "Rastreabilidade metrológica conforme INMETRO/NRs — decibelímetro, luxímetro, medidor de campo elétrico etc.",
        styles,
    )

    status_label = {"calibrado": "Calibrado", "vencido": "Calibração Vencida", "em_calibracao": "Em Calibração"}
    contagem_status = {}
    for it in instrumentos:
        rotulo = status_label.get(it.status_calculado, it.status_calculado)
        contagem_status[rotulo] = contagem_status.get(rotulo, 0) + 1
    if contagem_status:
        story.append(_desenhar_grafico("pizza", list(contagem_status.keys()), list(contagem_status.values()), W - 3*cm))
        story.append(Spacer(1, 12))

    headers = ["Instrumento", "Tipo", "Nº Série", "Norma", "Últ. Calibração", "Próx. Calibração", "Status"]
    header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7, textColor=WHITE)) for h in headers]
    rows = [header_row]
    for it in instrumentos:
        rows.append([
            Paragraph(it.nome, styles["small"]),
            Paragraph(it.get_tipo_display(), styles["small"]),
            Paragraph(it.numero_serie or "—", styles["small"]),
            Paragraph(it.norma_referencia or "—", styles["small"]),
            Paragraph(it.data_ultima_calibracao.strftime("%d/%m/%Y") if it.data_ultima_calibracao else "—", styles["small"]),
            Paragraph(it.data_proxima_calibracao.strftime("%d/%m/%Y") if it.data_proxima_calibracao else "—", styles["small"]),
            Paragraph(status_label.get(it.status_calculado, "—"), styles["small"]),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("Nenhum instrumento cadastrado.", styles["small"])] + [Paragraph("", styles["small"])]*6)

    t = Table(rows, colWidths=[3.5*cm, 2.8*cm, 2.2*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), DARK),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#d0e8e4")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()


def gerar_pdf_homem_hora_treinamentos(linhas, total_geral, empresa_nome, periodo_label):
    """Relatório de homem-hora de treinamentos por tipo/NR — controle interno e auditoria.
    `linhas` é uma lista de dicts: {nr, nome_tipo, participantes, carga_horaria, homem_hora}."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Relatório de Homem-Hora — Treinamentos NR",
    )
    styles = _styles()
    story = []
    _header_empresa(
        story, empresa_nome,
        "Relatório de Homem-Hora — Treinamentos NR",
        f"Controle interno e auditoria — {periodo_label}",
        styles,
    )

    homem_hora_por_grupo = {}
    for l in linhas:
        homem_hora_por_grupo[l["nr"]] = homem_hora_por_grupo.get(l["nr"], 0) + l["homem_hora"]
    if homem_hora_por_grupo:
        top = sorted(homem_hora_por_grupo.items(), key=lambda x: -x[1])[:10]
        story.append(_desenhar_grafico("barras", [k for k, _ in top], [v for _, v in top], W - 3*cm))
        story.append(Spacer(1, 12))

    headers = ["NR", "Tipo de Treinamento", "Participantes", "Carga Horária (h)", "Homem-Hora Total"]
    header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE)) for h in headers]
    rows = [header_row]
    for l in linhas:
        rows.append([
            Paragraph(l["nr"], styles["small"]),
            Paragraph(l["nome_tipo"], styles["small"]),
            Paragraph(str(l["participantes"]), styles["small"]),
            Paragraph(str(l["carga_horaria"]), styles["small"]),
            Paragraph(str(l["homem_hora"]), styles["bold"]),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("Nenhum treinamento registrado no período.", styles["small"])] + [Paragraph("", styles["small"])]*4)

    t = Table(rows, colWidths=[2*cm, 6.5*cm, 3*cm, 3.5*cm, 3.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), DARK),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#d0e8e4")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"TOTAL GERAL DE HOMEM-HORA NO PERÍODO: {total_geral}", styles["h2"]))
    story.append(Spacer(1, 16))
    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  Afastamentos
# ─────────────────────────────────────────────────────────────────────────────

def gerar_pdf_afastamentos(afastamentos, empresa_nome):
    """Relatório de afastamentos — `afastamentos` é uma lista de dicts:
    {funcionario_nome, motivo_label, cid, data_inicio, data_retorno, status_label, dias}."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Relatório de Afastamentos",
    )
    styles = _styles()
    story = []
    _header_empresa(
        story, empresa_nome,
        "Relatório de Afastamentos",
        "Controle de afastamentos por acidente de trabalho, doença ocupacional, doença comum e licenças",
        styles,
    )

    por_motivo = {}
    for a in afastamentos:
        rotulo = a.get("motivo_label", "—")
        por_motivo[rotulo] = por_motivo.get(rotulo, 0) + 1
    if por_motivo:
        story.append(_desenhar_grafico("barras", list(por_motivo.keys()), list(por_motivo.values()), W - 3*cm))
        story.append(Spacer(1, 12))

    headers = ["Funcionário", "Motivo", "CID", "Início", "Retorno", "Dias", "Status"]
    header_row = [Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7, textColor=WHITE)) for h in headers]
    rows = [header_row]
    for a in afastamentos:
        rows.append([
            Paragraph(a.get("funcionario_nome", "—"), styles["small"]),
            Paragraph(a.get("motivo_label", "—"), styles["small"]),
            Paragraph(a.get("cid") or "—", styles["small"]),
            Paragraph(a.get("data_inicio") or "—", styles["small"]),
            Paragraph(a.get("data_retorno") or "Em curso", styles["small"]),
            Paragraph(str(a.get("dias", "—")), styles["small"]),
            Paragraph(a.get("status_label", "—"), styles["small"]),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("Nenhum afastamento registrado.", styles["small"])] + [Paragraph("", styles["small"])]*6)

    t = Table(rows, colWidths=[3.5*cm, 3.2*cm, 1.8*cm, 2.3*cm, 2.3*cm, 1.5*cm, 2.9*cm])
    style = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), DARK),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#d0e8e4")),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LGREY]),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ])
    for row_idx, a in enumerate(afastamentos, 1):
        if a.get("status_raw") == "ativo":
            style.add("TEXTCOLOR", (6, row_idx), (6, row_idx), RED)
    t.setStyle(style)
    story.append(t)
    story.append(Spacer(1, 16))
    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  Certificados de treinamento interno / e-learning
# ─────────────────────────────────────────────────────────────────────────────

def _qr_certificado(url, tamanho=65):
    qr = QrCodeWidget(url)
    b = qr.getBounds()
    largura_nativa = b[2] - b[0]
    altura_nativa = b[3] - b[1]
    d = Drawing(tamanho, tamanho, transform=[tamanho / largura_nativa, 0, 0, tamanho / altura_nativa, 0, 0])
    d.add(qr)
    return d


def _logo_certificado(logo_url, largura_max, altura_max):
    """Baixa o logo da marca (ConfiguracaoMarca.logo_url) para embutir no certificado.
    Retorna None silenciosamente se não houver logo ou o download falhar — o
    certificado ainda é gerado, só sem o logo."""
    if not logo_url:
        return None
    try:
        import requests
        r = requests.get(logo_url, timeout=5)
        r.raise_for_status()
        leitor = ImageReader(io.BytesIO(r.content))
        largura_nativa, altura_nativa = leitor.getSize()
        escala = min(largura_max / largura_nativa, altura_max / altura_nativa, 1)
        return Image(io.BytesIO(r.content), width=largura_nativa * escala, height=altura_nativa * escala)
    except Exception:
        return None


def gerar_certificado_treinamento(dados):
    """Gera o PDF de um certificado de conclusão de curso interno.

    `dados`: dict com funcionario_nome, funcionario_cpf, curso_titulo, carga_horaria,
    data_conclusao (str), treinador_nome, treinador_cargo, treinador_registro,
    treinador_assinatura_path (caminho local ou None), empresa_nome, empresa_logo_url,
    estilo ('classico'/'moderno'/'compacto'), cor_destaque (hex ou None),
    texto_rodape, numero_certificado, url_verificacao."""
    estilo = dados.get("estilo") or "classico"
    cor = colors.HexColor(dados["cor_destaque"]) if dados.get("cor_destaque") else TEAL

    pagesize = landscape(A4)
    largura_pagina = pagesize[0]
    margem_h = 2.2 * cm if estilo != "compacto" else 1.5 * cm
    margem_v = 1.6 * cm if estilo != "compacto" else 1.1 * cm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize,
        leftMargin=margem_h, rightMargin=margem_h, topMargin=margem_v, bottomMargin=margem_v,
        title=f"Certificado — {dados.get('curso_titulo', '')}",
    )
    largura_util = largura_pagina - 2 * margem_h
    story = []

    if estilo == "moderno":
        faixa = Table([[""]], colWidths=[largura_util], rowHeights=[0.5 * cm])
        faixa.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), cor)]))
        story.append(faixa)
        story.append(Spacer(1, 14))

    logo = _logo_certificado(dados.get("empresa_logo_url"), largura_max=3.6 * cm, altura_max=1.8 * cm)
    if logo and estilo != "compacto":
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 8))

    tam_titulo = {"classico": 25, "moderno": 27, "compacto": 17}[estilo]
    titulo_style = ParagraphStyle(
        "cert_titulo", fontName="Helvetica-Bold", fontSize=tam_titulo,
        textColor=cor if estilo != "moderno" else DARK, alignment=TA_CENTER, spaceAfter=4,
    )
    story.append(Paragraph("CERTIFICADO DE CONCLUSÃO", titulo_style))
    if estilo != "compacto":
        story.append(HRFlowable(width="55%", thickness=1.4, color=cor, spaceBefore=6, spaceAfter=16, hAlign="CENTER"))
    else:
        story.append(Spacer(1, 8))

    tam_corpo = 11.5 if estilo != "compacto" else 10
    corpo_style = ParagraphStyle("cert_corpo", fontName="Helvetica", fontSize=tam_corpo, leading=tam_corpo + 7, alignment=TA_CENTER, textColor=DARK)
    nome_style = ParagraphStyle(
        "cert_nome", fontName="Helvetica-Bold", fontSize=19 if estilo != "compacto" else 15,
        alignment=TA_CENTER, textColor=cor if estilo == "moderno" else DARK, spaceBefore=8, spaceAfter=8,
    )

    cpf = dados.get("funcionario_cpf") or ""
    cpf_txt = f", portador do CPF {cpf},".strip()
    if estilo != "compacto":
        story.append(Paragraph("Certificamos que", corpo_style))
    story.append(Paragraph(dados.get("funcionario_nome", ""), nome_style))
    story.append(Paragraph(
        f"concluiu com aproveitamento o curso <b>{dados.get('curso_titulo', '')}</b>{cpf_txt if cpf else ''} "
        f"com carga horária de <b>{dados.get('carga_horaria', '—')} hora(s)</b>, "
        f"realizado em {dados.get('data_conclusao', '—')}, promovido por <b>{dados.get('empresa_nome', '')}</b>.",
        corpo_style,
    ))
    story.append(Spacer(1, 30 if estilo != "compacto" else 16))

    assinatura_path = dados.get("treinador_assinatura_path")
    ass_img = None
    if assinatura_path:
        try:
            ass_img = Image(assinatura_path, width=3.8 * cm, height=1.5 * cm)
        except Exception:
            ass_img = None

    linha_style = ParagraphStyle("linha_ass", fontName="Helvetica-Bold", fontSize=9.5, alignment=TA_CENTER, textColor=DARK)
    sub_style = ParagraphStyle("sub_ass", fontName="Helvetica", fontSize=8, alignment=TA_CENTER, textColor=MUTED)

    bloco_assinatura = [ass_img] if ass_img else [Spacer(1, 1.5 * cm)]
    bloco_assinatura.append(HRFlowable(width="80%", thickness=0.75, color=MUTED, hAlign="CENTER", spaceBefore=2))
    bloco_assinatura.append(Paragraph(dados.get("treinador_nome", "—"), linha_style))
    sub = " · ".join(x for x in [dados.get("treinador_cargo"), dados.get("treinador_registro")] if x)
    if sub:
        bloco_assinatura.append(Paragraph(sub, sub_style))

    url_verificacao = dados.get("url_verificacao")
    qr = _qr_certificado(url_verificacao, tamanho=60) if url_verificacao else None
    bloco_qr = []
    if qr:
        bloco_qr.append(qr)
        bloco_qr.append(Paragraph(f"Nº {dados.get('numero_certificado', '')}", sub_style))
        bloco_qr.append(Paragraph("Verifique a autenticidade", sub_style))

    if qr:
        linhas_rodape = [[bloco_assinatura, bloco_qr]]
        larguras_rodape = [largura_util - 4.2 * cm, 4.2 * cm]
    else:
        linhas_rodape = [[bloco_assinatura]]
        larguras_rodape = [largura_util]
    tabela_rodape = Table(linhas_rodape, colWidths=larguras_rodape)
    estilo_rodape = [("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (0, 0), (0, 0), "CENTER")]
    if qr:
        estilo_rodape.append(("ALIGN", (1, 0), (1, 0), "CENTER"))
    tabela_rodape.setStyle(TableStyle(estilo_rodape))
    story.append(tabela_rodape)

    if dados.get("texto_rodape"):
        story.append(Spacer(1, 12))
        story.append(Paragraph(dados["texto_rodape"], sub_style))

    def _borda_classica(canvas, doc_):
        if estilo != "classico":
            return
        canvas.saveState()
        canvas.setStrokeColor(cor)
        canvas.setLineWidth(1.6)
        m = 0.8 * cm
        canvas.rect(m, m, largura_pagina - 2 * m, pagesize[1] - 2 * m)
        canvas.setLineWidth(0.6)
        canvas.rect(m + 0.15 * cm, m + 0.15 * cm, largura_pagina - 2 * m - 0.3 * cm, pagesize[1] - 2 * m - 0.3 * cm)
        canvas.restoreState()

    doc.build(story, onFirstPage=_borda_classica)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  Assistente IA SST — gráfico anexado à resposta
# ─────────────────────────────────────────────────────────────────────────────

_PALETA_GRAFICO = [TEAL, AMBER, RED, MUTED, DARK, colors.HexColor("#6ba3f5"), colors.HexColor("#c084fc")]


def _desenhar_grafico(tipo, labels, valores, largura):
    """Monta um reportlab.graphics.shapes.Drawing para o tipo pedido.
    'pareto' é desenhado como barras ordenadas (a % acumulado só aparece no chat/Chart.js —
    combinar barra+linha com eixo duplo no reportlab exigiria mais código do que vale aqui)."""
    altura = 230
    drawing = Drawing(largura, altura)
    max_val = max(valores) if valores else 1

    if tipo == "pizza":
        pie = Pie()
        pie.x = largura / 2 - 90
        pie.y = 20
        pie.width = 180
        pie.height = 180
        pie.data = valores
        pie.labels = [f"{l} ({v:g})" for l, v in zip(labels, valores)]
        pie.slices.strokeWidth = 0.5
        pie.slices.strokeColor = WHITE
        for i in range(len(valores)):
            pie.slices[i].fillColor = _PALETA_GRAFICO[i % len(_PALETA_GRAFICO)]
        drawing.add(pie)
        return drawing

    if tipo == "linha":
        chart = HorizontalLineChart()
    else:  # barras, pareto
        chart = VerticalBarChart()

    chart.x = 45
    chart.y = 45
    chart.width = largura - 90
    chart.height = altura - 70
    chart.data = [valores]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.dy = -12
    chart.categoryAxis.labels.dx = -6
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max_val * 1.2 if max_val else 1
    if tipo == "linha":
        chart.lines[0].strokeColor = TEAL
        chart.lines[0].strokeWidth = 2
    else:
        chart.bars[0].fillColor = TEAL
    drawing.add(chart)
    return drawing


def gerar_pdf_grafico_assistente(grafico, resposta_texto, empresa_nome):
    """PDF de um gráfico anexado pelo Assistente IA SST.
    `grafico`: {titulo, tipo (barras/pizza/linha/pareto), labels, valores, rotulo_serie}."""
    buf = io.BytesIO()
    titulo = grafico.get("titulo") or "Relatório do Assistente IA SST"
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=titulo,
    )
    styles = _styles()
    story = []
    _header_empresa(story, empresa_nome, titulo, "Gerado pelo Assistente IA — SolusCRT SST", styles)

    labels = [str(l) for l in (grafico.get("labels") or [])]
    valores = [float(v) for v in (grafico.get("valores") or [])]
    tipo = grafico.get("tipo") or "barras"
    rotulo_serie = grafico.get("rotulo_serie") or "Quantidade"

    if labels and valores:
        story.append(_desenhar_grafico(tipo, labels, valores, W - 3*cm))
        story.append(Spacer(1, 10))
        story.append(Paragraph(rotulo_serie, styles["label"]))
        story.append(Spacer(1, 12))

    if resposta_texto:
        texto_html = resposta_texto.replace("\n", "<br/>")
        story.append(Paragraph(texto_html, styles["value"]))

    story.append(Spacer(1, 16))
    story.append(_footer_text(styles))
    doc.build(story)
    return buf.getvalue()
