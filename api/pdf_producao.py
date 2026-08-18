"""
pdf_producao.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Batch Record (Registro de Lote) da Ordem de Produção Industrial.

Gera o dossiê auditável de uma ordem: cabeçalho do lote, reconciliação de
rendimento, valores preenchidos por etapa com o status da validação, desvios com
o respectivo CAPA, assinaturas com hash e um selo de integridade de dados.

É a evidência documental exigida pelo desafio ("documentação para auditorias,
qualificação e validação") e pela BPF — pronta para impressão/arquivo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, HRFlowable

from .pdf_ops import _doc, _styles, _table_style, _header, OK, WARN, DANGER, MUTED


def _status_cor(status):
    return {"ok": OK, "alerta": WARN, "erro": DANGER}.get(status, MUTED)


def gerar_batch_record(ordem):
    """Recebe uma OrdemProducaoIndustrial e devolve os bytes do PDF."""
    esp = ordem.especificacao
    buf = io.BytesIO()
    doc = _doc(buf)
    s = _styles()
    story = []

    _header(story, s, "Registro de Lote — Ordem de Produção",
            ordem.empresa.nome,
            subtitulo=f"OP {ordem.numero_op} · {esp.nome} · Lote {ordem.numero_lote_fabricacao or '—'}")

    # ── Identificação ─────────────────────────────────────────────────────────
    story.append(Paragraph("1. Identificação do lote", s["section"]))
    ident = [
        ["Produto", esp.nome, "Código", esp.codigo_produto],
        ["Forma", esp.get_forma_farmaceutica_display(), "Concentração", esp.concentracao or "—"],
        ["MBR (versão)", f"v{esp.versao}", "Tamanho do lote", f"{ordem.tamanho_lote} {ordem.unidade}"],
        ["Status", ordem.get_status_display(), "Responsável", ordem.responsavel or "—"],
        ["Início", _dt(ordem.data_inicio), "Conclusão", _dt(ordem.data_conclusao)],
    ]
    t = Table(ident, colWidths=[3*_cm(), 5.5*_cm(), 3*_cm(), 5.5*_cm()])
    t.setStyle(_table_style())
    story.append(t)

    # ── Reconciliação de rendimento ───────────────────────────────────────────
    story.append(Paragraph("2. Reconciliação de rendimento", s["section"]))
    if ordem.rendimento_pct is not None:
        dentro = float(esp.faixa_rendimento_min) <= float(ordem.rendimento_pct) <= float(esp.faixa_rendimento_max)
        rend = [["Rendimento real", "Rendimento (%)", "Faixa aceitável", "Resultado"],
                [f"{ordem.rendimento_real} {ordem.unidade}", f"{ordem.rendimento_pct}%",
                 f"{esp.faixa_rendimento_min}–{esp.faixa_rendimento_max}%",
                 "DENTRO" if dentro else "FORA DA FAIXA"]]
        t = Table(rend, colWidths=[4.25*_cm() for _ in range(4)])
        st = _table_style()
        st.add("TEXTCOLOR", (3, 1), (3, 1), OK if dentro else DANGER)
        st.add("FONTNAME", (3, 1), (3, 1), "Helvetica-Bold")
        t.setStyle(st)
        story.append(t)
    else:
        story.append(Paragraph("Rendimento ainda não informado.", s["body"]))

    # ── Registro de preenchimento por etapa ───────────────────────────────────
    story.append(Paragraph("3. Registro de preenchimento (por etapa)", s["section"]))
    registros = {r.chave_campo: r for r in ordem.registros.all()}
    for e in esp.lista_etapas():
        chave = e.get("chave")
        story.append(Paragraph(f"<b>{e.get('rotulo') or chave}</b>", s["body"]))
        linhas = [["Campo", "Valor", "Faixa", "Status"]]
        for c in esp.campos_da_etapa(chave):
            reg = registros.get(c.get("chave"))
            faixa = "—"
            if c.get("min") is not None or c.get("max") is not None:
                faixa = f"{c.get('min', '−∞')}–{c.get('max', '+∞')} {c.get('unidade', '')}"
            linhas.append([
                c.get("rotulo") or c.get("chave"),
                (f"{reg.valor} {reg.unidade}" if reg and reg.valor else "—"),
                faixa,
                (reg.status_validacao.upper() if reg else "PENDENTE"),
            ])
        if len(linhas) == 1:
            continue
        t = Table(linhas, colWidths=[6*_cm(), 4*_cm(), 4*_cm(), 3*_cm()])
        st = _table_style()
        for i in range(1, len(linhas)):
            st.add("TEXTCOLOR", (3, i), (3, i), _status_cor(linhas[i][3].lower()))
        t.setStyle(st)
        story.append(t)
        story.append(Spacer(1, 6))

    # ── Desvios e CAPA ────────────────────────────────────────────────────────
    story.append(Paragraph("4. Desvios e tratamento (CAPA)", s["section"]))
    desvios = list(ordem.desvios.all())
    if not desvios:
        story.append(Paragraph("Nenhum desvio registrado — ordem correta na primeira vez (RFT).", s["body"]))
    else:
        for dv in desvios:
            status = "RESOLVIDO" if dv.resolvido else "EM ABERTO"
            story.append(Paragraph(
                f"<b>[{dv.get_severidade_display()}]</b> {dv.get_tipo_display()} — "
                f"{dv.descricao} <font color='#7a9bb5'>({status})</font>", s["body"]))
            if dv.resolvido:
                capa = f"Causa: {dv.get_categoria_causa_display() if dv.categoria_causa else 'n/d'}. "
                if dv.acao_corretiva:
                    capa += f"Corretiva: {dv.acao_corretiva}. "
                if dv.acao_preventiva:
                    capa += f"Preventiva: {dv.acao_preventiva}. "
                capa += f"Por: {dv.resolvido_por or '—'}."
                story.append(Paragraph(capa, s["label"]))
            story.append(Spacer(1, 4))

    # ── Assinaturas ───────────────────────────────────────────────────────────
    story.append(Paragraph("5. Assinaturas por etapa", s["section"]))
    assinaturas = list(ordem.assinaturas.all())
    if not assinaturas:
        story.append(Paragraph("Nenhuma assinatura registrada.", s["body"]))
    else:
        linhas = [["Etapa", "Papel", "Assinante", "Método", "Hash", "Data/hora"]]
        for a in assinaturas:
            linhas.append([
                a.etapa, a.get_papel_display().split(" —")[0], a.assinante_nome,
                a.metodo or "—", (a.hash_documento[:12] + "…") if a.hash_documento else "—",
                _dt(a.assinado_em),
            ])
        t = Table(linhas, colWidths=[2.6*_cm(), 2.6*_cm(), 3.6*_cm(), 2.8*_cm(), 2.6*_cm(), 2.8*_cm()])
        t.setStyle(_table_style())
        story.append(t)

    # ── Selo de integridade ───────────────────────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=MUTED, spaceAfter=6))
    story.append(Paragraph(
        "Documento gerado pelo SoloCRT — motor anti-erro de produção. Cada alteração "
        "de campo, assinatura e desvio possui trilha de auditoria imutável (quem, quando, "
        "de → para), em conformidade com os princípios de integridade de dados (ALCOA+). "
        f"Emitido em {datetime.now().strftime('%d/%m/%Y às %H:%M')}.", s["label"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _dt(value):
    return value.strftime("%d/%m/%Y %H:%M") if value else "—"


def _cm():
    from reportlab.lib.units import cm
    return cm
