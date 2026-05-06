"""
PDF generation for Farmácia, Hospital and Governo operational modules.
Uses ReportLab 4.x.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ── Palette ────────────────────────────────────────────────────────────────────
DARK = colors.HexColor("#041018")
ACCENT = colors.HexColor("#00c2ff")
SURFACE = colors.HexColor("#072030")
TEXT = colors.HexColor("#1a3a52")
MUTED = colors.HexColor("#7a9bb5")
OK = colors.HexColor("#00c896")
WARN = colors.HexColor("#e69500")
DANGER = colors.HexColor("#cc3355")
WHITE = colors.white

PAGE_W, PAGE_H = A4


def _doc(buffer):
    return SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2*cm,
    )


def _styles():
    base = getSampleStyleSheet()
    return {
        "title":   ParagraphStyle("title",   parent=base["Heading1"], fontSize=20, textColor=DARK, spaceAfter=4),
        "sub":     ParagraphStyle("sub",     parent=base["Normal"],   fontSize=10, textColor=MUTED),
        "section": ParagraphStyle("section", parent=base["Heading2"], fontSize=12, textColor=ACCENT, spaceBefore=12, spaceAfter=6),
        "body":    ParagraphStyle("body",    parent=base["Normal"],   fontSize=9,  textColor=TEXT,  leading=13),
        "label":   ParagraphStyle("label",   parent=base["Normal"],   fontSize=8,  textColor=MUTED),
        "center":  ParagraphStyle("center",  parent=base["Normal"],   fontSize=9,  alignment=TA_CENTER),
    }


def _table_style():
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5fafd"), WHITE]),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("TEXTCOLOR",   (0, 1), (-1, -1), TEXT),
        ("GRID",        (0, 0), (-1, -1), 0.25, colors.HexColor("#d0e8f0")),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ])


def _header(story, s, title, empresa_nome, subtitulo=""):
    story.append(Paragraph(f"<font color='#{hex(ACCENT.hexval())[2:].zfill(6)}'>■</font> {title}", s["title"]))
    story.append(Paragraph(empresa_nome, s["sub"]))
    if subtitulo:
        story.append(Paragraph(subtitulo, s["sub"]))
    story.append(Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", s["label"]))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=12))


def _fmt_date(s):
    if not s:
        return "—"
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(s)


# ── FARMÁCIA: Relatório de Estoque ────────────────────────────────────────────
def gerar_pdf_estoque_farmacia(empresa, itens):
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    _header(story, s, "Relatório de Estoque", empresa.nome, "Farmácia Operacional")

    # KPIs inline
    total = len(itens)
    abaixo = sum(1 for i in itens if i.estoque_atual < i.estoque_minimo)
    story.append(Paragraph(f"<b>Total de Itens:</b> {total} &nbsp;&nbsp; <b>Abaixo do Mínimo:</b> {abaixo}", s["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Inventário de Itens", s["section"]))
    data = [["Item", "Código", "Categoria", "Estoque Atual", "Mínimo", "Situação", "Fornecedor"]]
    for i in itens:
        sit = "⚠ BAIXO" if i.estoque_atual < i.estoque_minimo else "OK"
        data.append([
            i.nome,
            i.codigo or "—",
            i.get_categoria_display(),
            f"{i.estoque_atual} {i.unidade_medida}",
            f"{i.estoque_minimo} {i.unidade_medida}",
            sit,
            i.fornecedor.nome if i.fornecedor else "—",
        ])

    col_w = [4.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2*cm, 1.8*cm, 3.2*cm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(_table_style())
    # Highlight low stock rows
    for idx, i in enumerate(itens, start=1):
        if i.estoque_atual < i.estoque_minimo:
            t.setStyle(TableStyle([("TEXTCOLOR", (5, idx), (5, idx), DANGER), ("FONTNAME", (5, idx), (5, idx), "Helvetica-Bold")]))
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf


# ── FARMÁCIA: Relatório de Dispensações ───────────────────────────────────────
def gerar_pdf_dispensacoes_farmacia(empresa, dispensacoes):
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    _header(story, s, "Relatório de Dispensações", empresa.nome, "Farmácia Operacional")

    story.append(Paragraph(f"Total de dispensações: <b>{len(dispensacoes)}</b>", s["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Histórico de Dispensações", s["section"]))
    data = [["Medicamento", "Paciente", "CPF", "Qtd", "Responsável", "Data/Hora"]]
    for d in dispensacoes:
        data.append([
            d.item.nome,
            d.paciente_nome,
            d.paciente_cpf or "—",
            str(d.quantidade),
            d.responsavel or "—",
            _fmt_date(d.dispensado_em),
        ])

    col_w = [4*cm, 3.5*cm, 2.5*cm, 1.2*cm, 3*cm, 3.3*cm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(_table_style())
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf


# ── HOSPITAL: Relatório de Internações ────────────────────────────────────────
def gerar_pdf_internacoes_hospital(empresa, internacoes):
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    _header(story, s, "Relatório de Internações", empresa.nome, "Gestão Hospitalar")

    ativas = sum(1 for i in internacoes if i.status == "ativa")
    story.append(Paragraph(f"Total: <b>{len(internacoes)}</b> &nbsp;&nbsp; Ativas: <b>{ativas}</b>", s["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Internações", s["section"]))
    data = [["Paciente", "Leito", "Departamento", "Diagnóstico", "Médico", "Status", "Entrada"]]
    for i in internacoes:
        data.append([
            i.paciente.nome,
            i.leito.numero if i.leito else "—",
            i.leito.departamento.nome if i.leito else "—",
            (i.diagnostico[:40] + "…") if len(i.diagnostico) > 40 else i.diagnostico,
            i.medico_responsavel or "—",
            i.get_status_display(),
            _fmt_date(i.data_entrada),
        ])

    col_w = [3.5*cm, 1.5*cm, 3*cm, 4.5*cm, 3*cm, 1.8*cm, 2.7*cm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(_table_style())
    story.append(t)

    doc.build(story)
    buf.seek(0)
    return buf


# ── HOSPITAL: Ficha de Internação ─────────────────────────────────────────────
def gerar_pdf_ficha_internacao(empresa, internacao):
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    pac = internacao.paciente
    _header(story, s, "Ficha de Internação", empresa.nome)

    # Patient block
    story.append(Paragraph("Dados do Paciente", s["section"]))
    dados = [
        ["Nome:", pac.nome, "CPF:", pac.cpf or "—"],
        ["Nascimento:", str(pac.data_nascimento) if pac.data_nascimento else "—", "Sexo:", pac.get_sexo_display() if pac.sexo else "—"],
        ["Tipo Sanguíneo:", pac.tipo_sanguineo or "—", "Telefone:", pac.telefone or "—"],
        ["Alergias:", pac.alergias or "—", "", ""],
    ]
    t = Table(dados, colWidths=[3*cm, 5.5*cm, 3*cm, 5.5*cm])
    t.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",  (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTNAME",  (1, 0), (1, -1), "Helvetica"),
        ("FONTNAME",  (3, 0), (3, -1), "Helvetica"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Internação block
    story.append(Paragraph("Dados da Internação", s["section"]))
    leito_info = f"Leito {internacao.leito.numero} — {internacao.leito.departamento.nome}" if internacao.leito else "—"
    internacao_data = [
        ["Leito:", leito_info, "Status:", internacao.get_status_display()],
        ["Médico:", internacao.medico_responsavel or "—", "Entrada:", _fmt_date(internacao.data_entrada)],
        ["Saída:", _fmt_date(internacao.data_saida), "", ""],
    ]
    t2 = Table(internacao_data, colWidths=[3*cm, 5.5*cm, 3*cm, 5.5*cm])
    t2.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",  (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t2)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Diagnóstico:", s["label"]))
    story.append(Paragraph(internacao.diagnostico, s["body"]))
    story.append(Spacer(1, 10))

    # Evoluções
    evs = list(internacao.evolucoes.all())
    if evs:
        story.append(Paragraph("Evoluções Clínicas", s["section"]))
        ev_data = [["Data/Hora", "Responsável", "Evolução"]]
        for ev in evs:
            ev_data.append([
                _fmt_date(ev.registrado_em),
                ev.responsavel or "—",
                ev.descricao,
            ])
        t3 = Table(ev_data, colWidths=[3.5*cm, 3*cm, 10.5*cm], repeatRows=1)
        t3.setStyle(_table_style())
        story.append(t3)

    doc.build(story)
    buf.seek(0)
    return buf


# ── GOVERNO: Relatório de Programas e Indicadores ─────────────────────────────
def gerar_pdf_programas_gov(empresa, programas, indicadores, planos):
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    _header(story, s, "Relatório de Gestão em Saúde", empresa.nome, "Gestão Governamental")

    # Programas
    story.append(Paragraph("Programas de Saúde", s["section"]))
    p_data = [["Programa", "Status", "Orçamento Previsto", "Executado", "Responsável", "Início"]]
    for p in programas:
        p_data.append([
            p.nome,
            p.get_status_display(),
            f"R$ {float(p.orcamento_previsto):,.2f}" if p.orcamento_previsto else "—",
            f"R$ {float(p.orcamento_executado):,.2f}",
            p.responsavel or "—",
            str(p.data_inicio) if p.data_inicio else "—",
        ])
    t = Table(p_data, colWidths=[4.5*cm, 2.5*cm, 3*cm, 2.5*cm, 3*cm, 2*cm], repeatRows=1)
    t.setStyle(_table_style())
    story.append(t)
    story.append(Spacer(1, 12))

    # Indicadores
    if indicadores:
        story.append(Paragraph("Indicadores de Saúde", s["section"]))
        i_data = [["Indicador", "Programa", "Meta", "Atual", "Unidade", "Período"]]
        for i in indicadores:
            i_data.append([
                i.nome,
                i.programa.nome if i.programa else "—",
                str(i.meta) if i.meta is not None else "—",
                str(i.valor_atual) if i.valor_atual is not None else "—",
                i.unidade,
                i.periodo_referencia or "—",
            ])
        t2 = Table(i_data, colWidths=[4*cm, 3.5*cm, 2*cm, 2*cm, 2*cm, 3*cm], repeatRows=1)
        t2.setStyle(_table_style())
        story.append(t2)
        story.append(Spacer(1, 12))

    # Planos
    if planos:
        story.append(Paragraph("Planos de Ação", s["section"]))
        pl_data = [["Título", "Programa", "Prioridade", "Status", "Progresso", "Prazo"]]
        for p in planos:
            pl_data.append([
                (p.titulo[:35] + "…") if len(p.titulo) > 35 else p.titulo,
                p.programa.nome[:20] if p.programa else "—",
                p.get_prioridade_display(),
                p.get_status_display(),
                f"{p.progresso}%",
                str(p.prazo) if p.prazo else "—",
            ])
        t3 = Table(pl_data, colWidths=[4.5*cm, 3*cm, 2.5*cm, 2.5*cm, 2*cm, 2.5*cm], repeatRows=1)
        t3.setStyle(_table_style())
        story.append(t3)

    doc.build(story)
    buf.seek(0)
    return buf


def gerar_pdf_conformidade_sst(empresa, resumo, funcionarios):
    """Relatório de conformidade SST por funcionário."""
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    _header(story, s, "Relatório de Conformidade SST", empresa.nome,
            f"Índice de conformidade: {resumo.get('indice_conformidade', 0)}%")

    # Resumo KPIs como tabela
    story.append(Paragraph("Resumo Geral", s["section"]))
    kpi_data = [
        ["Total Funcionários", "Conformes", "Em Alerta", "Críticos", "Índice"],
        [
            str(resumo.get("total", 0)),
            str(resumo.get("conformes", 0)),
            str(resumo.get("alertas", 0)),
            str(resumo.get("criticos", 0)),
            f"{resumo.get('indice_conformidade', 0)}%",
        ]
    ]
    kpi_t = Table(kpi_data, colWidths=[3.5*cm, 3.5*cm, 3.5*cm, 3.5*cm, 3.5*cm], repeatRows=1)
    kpi_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f8ff"), WHITE]),
        ("BOX", (0, 0), (-1, -1), 0.5, MUTED),
        ("GRID", (0, 0), (-1, -1), 0.3, MUTED),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ])
    kpi_t.setStyle(kpi_style)
    story.append(kpi_t)
    story.append(Spacer(1, 16))

    # Tabela por funcionário
    story.append(Paragraph("Avaliação por Funcionário", s["section"]))
    headers = ["Funcionário", "Cargo", "Setor", "ASO", "Exames", "EPI", "Treinamento", "Score", "Status"]
    rows = [headers]

    STATUS_LABELS = {"conforme": "Conforme", "alerta": "Alerta", "critico": "Crítico"}
    for f in funcionarios:
        aso_val = "✓" if f.get("aso_ok") else "✗"
        if f.get("aso_ok") and f.get("aso_alerta"):
            aso_val = f"⚠ {f.get('aso_validade', '')}"
        exames_val = "✓" if f.get("exames_ok") else f"✗ {f.get('exames_vencidos', 0)}v"
        epi_val = "✓" if f.get("epi_ok") else "✗"
        trein_val = "✓" if f.get("treinamento_ok") else "✗"
        rows.append([
            (f["nome"][:28] + "…") if len(f["nome"]) > 28 else f["nome"],
            (f.get("cargo") or "—")[:18],
            (f.get("setor") or "—")[:16],
            aso_val,
            exames_val,
            epi_val,
            trein_val,
            f"{f.get('score', 0)}/4",
            STATUS_LABELS.get(f.get("status", ""), f.get("status", "")),
        ])

    col_widths = [4*cm, 3*cm, 2.8*cm, 1.8*cm, 1.8*cm, 1.5*cm, 2.2*cm, 1.5*cm, 2*cm]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl_style = _table_style()
    # Color-code status rows
    for idx, f in enumerate(funcionarios, start=1):
        if f.get("status") == "conforme":
            tbl_style.add("TEXTCOLOR", (8, idx), (8, idx), OK)
        elif f.get("status") == "alerta":
            tbl_style.add("TEXTCOLOR", (8, idx), (8, idx), WARN)
        elif f.get("status") == "critico":
            tbl_style.add("TEXTCOLOR", (8, idx), (8, idx), DANGER)
    tbl.setStyle(tbl_style)
    story.append(tbl)

    # Footer note
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"<font color='#7a9bb5' size='8'>Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        f"Critérios: ASO vigente, exames em dia, EPI entregue, treinamento NR válido.</font>",
        s["normal"]
    ))

    doc.build(story)
    buf.seek(0)
    return buf
