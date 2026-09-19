"""
Audiometria Ocupacional + PCA (Programa de Conservação Auditiva) — SoloCRT SST.

Interpretação automática (NR-07) e comparação sequencial entre exames, com
audiograma em PDF. O motor de interpretação vive em audiometria_interpretacao.py
(função pura, testável); aqui ficam persistência, RBAC e renderização.

Endpoints:
  GET  /api/sst/audiometria/kpis/                          — KPIs
  GET  /api/sst/audiometria/                               — lista audiometrias
  POST /api/sst/audiometria/                               — cria (auto-interpreta)
  GET  /api/sst/audiometria/<id>/                          — detalhe
  PATCH/DELETE /api/sst/audiometria/<id>/                  — atualiza / remove
  GET  /api/sst/audiometria/<id>/pdf/                      — audiograma PDF
  GET  /api/sst/audiometria/funcionario/<fid>/historico/  — evolução sequencial
  GET  /api/sst/audiometria/pca/                           — lista PCAs
  POST /api/sst/audiometria/pca/                           — cria PCA
  GET/PATCH/DELETE /api/sst/audiometria/pca/<id>/          — detalhe PCA
  GET  /sst/audiometria/                                   — página
"""
import json
import logging
from datetime import date

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Flowable,
)

from .access_control import (
    api_requer_feature, requer_permissao_modulo, requer_feature_pacote,
    principal_pode_operacao_setorial,
)
from .audiometria_interpretacao import (
    FREQUENCIAS, interpretar, comparar_sequencial,
)

logger = logging.getLogger(__name__)

TEAL  = colors.HexColor("#00c9a7")
DARK  = colors.HexColor("#071c28")
MUTED = colors.HexColor("#7a9fa0")
WHITE = colors.white
BLACK = colors.black
LGREY = colors.HexColor("#f4f8f7")
AMBER = colors.HexColor("#f0bf6b")
RED   = colors.HexColor("#e05260")


# ── Helpers ────────────────────────────────────────────────────────────────

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


def _audiometria_dict(a, completo=False):
    d = {
        "id": a.id,
        "funcionario_id": a.funcionario_id,
        "funcionario_nome": a.funcionario.nome,
        "funcionario_cargo": a.funcionario.cargo,
        "tipo": a.tipo,
        "data_exame": str(a.data_exame),
        "classificacao": a.classificacao,
        "classificacao_sequencial": a.classificacao_sequencial,
        "sugestivo_pair": a.sugestivo_pair,
        "reteste_indicado": a.reteste_indicado,
        "resultado_resumo": a.resultado_resumo,
        "responsavel": a.responsavel,
        "conselho": a.conselho,
        "pca_id": a.pca_id,
    }
    if completo:
        d["limiares"] = a.limiares or {}
        d["interpretacao"] = a.interpretacao or {}
        d["repouso_acustico_horas"] = a.repouso_acustico_horas
        d["anamnese_auricular"] = a.anamnese_auricular or ""
        d["observacoes"] = a.observacoes or ""
    return d


def _pca_dict(p):
    return {
        "id": p.id,
        "ano": p.ano,
        "vigencia_inicio": str(p.vigencia_inicio) if p.vigencia_inicio else None,
        "vigencia_fim": str(p.vigencia_fim) if p.vigencia_fim else None,
        "medidas_engenharia": p.medidas_engenharia,
        "medidas_administrativas": p.medidas_administrativas,
        "medidas_epi": p.medidas_epi,
        "responsavel": p.responsavel,
        "conselho": p.conselho,
        "status": p.status,
        "observacoes": p.observacoes,
        "audiometrias_vinculadas": p.audiometrias.count(),
    }


def _aplicar_interpretacao(audiometria, empresa):
    """Roda o motor sobre os limiares e grava os campos calculados.
    Busca o exame anterior do mesmo funcionário para a comparação sequencial."""
    from .models import Audiometria

    interp = interpretar(audiometria.limiares or {})

    anterior = (
        Audiometria.objects
        .filter(empresa=empresa, funcionario=audiometria.funcionario, data_exame__lt=audiometria.data_exame)
        .exclude(id=audiometria.id or 0)
        .order_by("-data_exame")
        .first()
    )
    seq = comparar_sequencial(audiometria.limiares or {}, anterior.limiares if anterior else None)

    audiometria.classificacao = interp["classificacao"]
    audiometria.sugestivo_pair = interp["sugestivo_pair"]
    audiometria.classificacao_sequencial = seq["classificacao_sequencial"]
    audiometria.reteste_indicado = seq["reteste_indicado"]
    audiometria.interpretacao = {"exame": interp, "sequencial": seq}
    resumo = interp["resumo"]
    if seq["classificacao_sequencial"] not in ("referencia", "estavel"):
        resumo += f" Comparação sequencial: {seq['detalhe']}"
    audiometria.resultado_resumo = resumo
    return audiometria


# ── KPIs ───────────────────────────────────────────────────────────────────

@api_requer_feature("sst.audiometria")
def api_audiometria_kpis(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Audiometria
    try:
        qs = Audiometria.objects.filter(empresa=empresa)
        return JsonResponse({
            "total": qs.count(),
            "alteradas": qs.exclude(classificacao__in=["normal", "indeterminado"]).count(),
            "sugestivo_pair": qs.filter(sugestivo_pair=True).count(),
            "retestes_pendentes": qs.filter(reteste_indicado=True).count(),
            "agravamentos": qs.filter(classificacao_sequencial__in=["agravamento", "desencadeamento"]).count(),
        })
    except Exception:
        logger.exception("Erro em KPIs audiometria")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


# ── Lista + criação ──────────────────────────────────────────────────────────

@api_requer_feature("sst.audiometria")
def api_audiometrias(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Audiometria, FuncionarioSST

    if request.method == "GET":
        try:
            qs = Audiometria.objects.filter(empresa=empresa).select_related("funcionario")
            func_id = request.GET.get("funcionario_id")
            if func_id:
                qs = qs.filter(funcionario_id=func_id)
            classif = request.GET.get("classificacao")
            if classif:
                qs = qs.filter(classificacao=classif)
            if request.GET.get("reteste") == "1":
                qs = qs.filter(reteste_indicado=True)
            return JsonResponse({
                "total": qs.count(),
                "audiometrias": [_audiometria_dict(a) for a in qs[:100]],
            })
        except Exception:
            logger.exception("Erro ao listar audiometrias")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para registrar audiometria"}, status=403)
        try:
            data = _json(request)
            if not data.get("funcionario_id") or not data.get("data_exame"):
                return JsonResponse({"erro": "funcionario_id e data_exame são obrigatórios"}, status=400)
            try:
                func = FuncionarioSST.objects.get(id=data["funcionario_id"], empresa=empresa)
            except FuncionarioSST.DoesNotExist:
                return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

            limiares = data.get("limiares") or {}
            if not isinstance(limiares, dict):
                return JsonResponse({"erro": "limiares deve ser um objeto"}, status=400)

            a = Audiometria(
                empresa=empresa,
                funcionario=func,
                tipo=data.get("tipo", "sequencial"),
                data_exame=data["data_exame"],
                limiares=limiares,
                anamnese_auricular=data.get("anamnese_auricular", ""),
                repouso_acustico_horas=data.get("repouso_acustico_horas", 14),
                responsavel=data.get("responsavel", ""),
                conselho=data.get("conselho", ""),
                observacoes=data.get("observacoes", ""),
            )
            pca_id = data.get("pca_id")
            if pca_id:
                from .models import ProgramaConservacaoAuditiva
                a.pca = ProgramaConservacaoAuditiva.objects.filter(id=pca_id, empresa=empresa).first()
            _aplicar_interpretacao(a, empresa)
            a.save()
            return JsonResponse({"ok": True, "data": _audiometria_dict(a, completo=True)}, status=201)
        except Exception:
            logger.exception("Erro ao criar audiometria")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.audiometria")
def api_audiometria_detalhe(request, aud_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Audiometria
    try:
        a = Audiometria.objects.select_related("funcionario").get(id=aud_id, empresa=empresa)
    except Audiometria.DoesNotExist:
        return JsonResponse({"erro": "Audiometria não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_audiometria_dict(a, completo=True))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para editar audiometria"}, status=403)
        try:
            data = _json(request)
            for f in ("tipo", "data_exame", "anamnese_auricular", "repouso_acustico_horas",
                      "responsavel", "conselho", "observacoes"):
                if f in data:
                    setattr(a, f, data[f])
            recalcular = False
            if "limiares" in data and isinstance(data["limiares"], dict):
                a.limiares = data["limiares"]
                recalcular = True
            if "data_exame" in data:
                recalcular = True
            if recalcular:
                _aplicar_interpretacao(a, empresa)
            a.save()
            return JsonResponse({"ok": True, "data": _audiometria_dict(a, completo=True)})
        except Exception:
            logger.exception("Erro ao editar audiometria")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para excluir audiometria"}, status=403)
        try:
            a.delete()
            return JsonResponse({"ok": True, "msg": "Audiometria removida"})
        except Exception:
            logger.exception("Erro ao excluir audiometria")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.audiometria")
def api_audiometria_historico(request, funcionario_id):
    """Evolução sequencial de um funcionário (linha do tempo das audiometrias)."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Audiometria, FuncionarioSST
    try:
        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)
    except FuncionarioSST.DoesNotExist:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
    try:
        qs = Audiometria.objects.filter(empresa=empresa, funcionario=func).order_by("data_exame")
        return JsonResponse({
            "funcionario_nome": func.nome,
            "total": qs.count(),
            "historico": [_audiometria_dict(a, completo=True) for a in qs],
        })
    except Exception:
        logger.exception("Erro no histórico de audiometria")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


# ── PCA (Programa de Conservação Auditiva) ───────────────────────────────────

@api_requer_feature("sst.audiometria")
def api_pca(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import ProgramaConservacaoAuditiva

    if request.method == "GET":
        try:
            qs = ProgramaConservacaoAuditiva.objects.filter(empresa=empresa)
            return JsonResponse({"total": qs.count(), "pcas": [_pca_dict(p) for p in qs[:50]]})
        except Exception:
            logger.exception("Erro ao listar PCA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para criar PCA"}, status=403)
        try:
            data = _json(request)
            if not data.get("ano"):
                return JsonResponse({"erro": "ano é obrigatório"}, status=400)
            p = ProgramaConservacaoAuditiva.objects.create(
                empresa=empresa,
                ano=data["ano"],
                vigencia_inicio=data.get("vigencia_inicio") or None,
                vigencia_fim=data.get("vigencia_fim") or None,
                medidas_engenharia=data.get("medidas_engenharia", ""),
                medidas_administrativas=data.get("medidas_administrativas", ""),
                medidas_epi=data.get("medidas_epi", ""),
                responsavel=data.get("responsavel", ""),
                conselho=data.get("conselho", ""),
                status=data.get("status", "ativo"),
                observacoes=data.get("observacoes", ""),
            )
            return JsonResponse({"ok": True, "data": _pca_dict(p)}, status=201)
        except Exception:
            logger.exception("Erro ao criar PCA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.audiometria")
def api_pca_detalhe(request, pca_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import ProgramaConservacaoAuditiva
    try:
        p = ProgramaConservacaoAuditiva.objects.get(id=pca_id, empresa=empresa)
    except ProgramaConservacaoAuditiva.DoesNotExist:
        return JsonResponse({"erro": "PCA não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_pca_dict(p))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para editar PCA"}, status=403)
        try:
            data = _json(request)
            for f in ("ano", "medidas_engenharia", "medidas_administrativas",
                      "medidas_epi", "responsavel", "conselho", "status", "observacoes"):
                if f in data:
                    setattr(p, f, data[f])
            for f in ("vigencia_inicio", "vigencia_fim"):
                if f in data:
                    setattr(p, f, data[f] or None)
            p.save()
            return JsonResponse({"ok": True, "data": _pca_dict(p)})
        except Exception:
            logger.exception("Erro ao editar PCA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para excluir PCA"}, status=403)
        try:
            p.delete()
            return JsonResponse({"ok": True, "msg": "PCA removido"})
        except Exception:
            logger.exception("Erro ao excluir PCA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Audiograma PDF ───────────────────────────────────────────────────────────

class _AudiogramaFlowable(Flowable):
    """Desenha o audiograma (limiar × frequência) de OD e OE."""
    def __init__(self, limiares, width=17 * cm, height=9 * cm):
        super().__init__()
        self.limiares = limiares or {}
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        freqs = FREQUENCIAS
        n = len(freqs)
        left, bottom = 1.4 * cm, 1.2 * cm
        plot_w = self.width - left - 0.4 * cm
        plot_h = self.height - bottom - 0.4 * cm
        db_min, db_max = -10, 120

        def x(i):
            return left + (plot_w * i / (n - 1))

        def y(db):
            return bottom + plot_h * (1 - (db - db_min) / (db_max - db_min))

        # grade horizontal (dB) e rótulos
        c.setFont("Helvetica", 6)
        for db in range(0, 121, 10):
            c.setStrokeColor(colors.HexColor("#e3efec"))
            c.setLineWidth(0.3)
            c.line(left, y(db), left + plot_w, y(db))
            c.setFillColor(MUTED)
            c.drawRightString(left - 0.15 * cm, y(db) - 2, str(db))
        # grade vertical (frequências)
        for i, f in enumerate(freqs):
            c.setStrokeColor(colors.HexColor("#e3efec"))
            c.line(x(i), bottom, x(i), bottom + plot_h)
            c.setFillColor(MUTED)
            lbl = f"{f//1000}k" if f >= 1000 else str(f)
            c.drawCentredString(x(i), bottom - 0.35 * cm, lbl)

        def plot(orelha_key, cor, marca):
            serie = self.limiares.get(orelha_key) or {}
            pts = []
            for i, f in enumerate(freqs):
                v = serie.get(str(f), serie.get(f))
                if v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                pts.append((x(i), y(v)))
            if not pts:
                return
            c.setStrokeColor(cor)
            c.setLineWidth(1.3)
            for j in range(len(pts) - 1):
                c.line(pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1])
            c.setFillColor(cor)
            for px, py in pts:
                if marca == "O":
                    c.circle(px, py, 3, stroke=1, fill=0)
                else:  # X
                    c.line(px - 3, py - 3, px + 3, py + 3)
                    c.line(px - 3, py + 3, px + 3, py - 3)

        plot("od_aerea", colors.HexColor("#e05260"), "O")   # OD vermelho, círculo
        plot("oe_aerea", colors.HexColor("#2f6fed"), "X")   # OE azul, X


@api_requer_feature("sst.audiometria")
def api_audiometria_pdf(request, aud_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Audiometria
    try:
        a = Audiometria.objects.select_related("funcionario").get(id=aud_id, empresa=empresa)
    except Audiometria.DoesNotExist:
        return JsonResponse({"erro": "Audiometria não encontrada"}, status=404)

    try:
        buf = _gerar_pdf_audiometria(a, empresa)
        resp = HttpResponse(buf, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="audiometria_{a.id}.pdf"'
        return resp
    except Exception:
        logger.exception("Erro ao gerar PDF de audiometria")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


def _gerar_pdf_audiometria(a, empresa):
    import io
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.4 * cm, bottomMargin=1.4 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    st = {
        "title": ParagraphStyle("t", fontSize=15, fontName="Helvetica-Bold", textColor=DARK, leading=19),
        "sub":   ParagraphStyle("s", fontSize=9, fontName="Helvetica", textColor=MUTED, leading=13, spaceAfter=6),
        "h2":    ParagraphStyle("h2", fontSize=11, fontName="Helvetica-Bold", textColor=DARK, leading=15, spaceBefore=8, spaceAfter=4),
        "body":  ParagraphStyle("b", fontSize=9, fontName="Helvetica", textColor=BLACK, leading=13, spaceAfter=3),
        "small": ParagraphStyle("sm", fontSize=8, fontName="Helvetica", textColor=MUTED, leading=11),
    }
    el = []
    el.append(Paragraph("Audiometria Ocupacional", st["title"]))
    el.append(Paragraph(f"{empresa.nome} · Conforme NR-07", st["sub"]))
    el.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8))

    ident = [
        ["Funcionário", a.funcionario.nome, "Cargo", a.funcionario.cargo or "—"],
        ["Data do exame", str(a.data_exame), "Tipo", a.get_tipo_display()],
        ["Repouso acústico", f"{a.repouso_acustico_horas}h", "Responsável", a.responsavel or "—"],
    ]
    t = Table(ident, colWidths=[3 * cm, 6 * cm, 3 * cm, 4.5 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LGREY),
    ]))
    el.append(t)
    el.append(Spacer(1, 8))

    el.append(Paragraph("Audiograma", st["h2"]))
    el.append(Paragraph("OD: ○ (vermelho) · OE: ✕ (azul) · via aérea", st["small"]))
    el.append(Spacer(1, 4))
    el.append(_AudiogramaFlowable(a.limiares))
    el.append(Spacer(1, 8))

    # tabela de limiares
    header = ["Orelha"] + [f"{f//1000}k" if f >= 1000 else str(f) for f in FREQUENCIAS]
    rows = [header]
    for key, lbl in (("od_aerea", "OD aérea"), ("oe_aerea", "OE aérea")):
        serie = (a.limiares or {}).get(key) or {}
        rows.append([lbl] + [str(serie.get(str(f), serie.get(f, "—"))) for f in FREQUENCIAS])
    lt = Table(rows, colWidths=[2.4 * cm] + [1.9 * cm] * len(FREQUENCIAS))
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0e8e4")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    el.append(lt)
    el.append(Spacer(1, 10))

    el.append(Paragraph("Interpretação automática (NR-07)", st["h2"]))
    el.append(Paragraph(a.resultado_resumo or "—", st["body"]))
    interp = (a.interpretacao or {}).get("exame", {})
    for lado, lbl in (("od", "Orelha Direita"), ("oe", "Orelha Esquerda")):
        o = interp.get(lado, {})
        if o:
            grau = o.get("grau", "—")
            mf = o.get("media_fala")
            el.append(Paragraph(
                f"<b>{lbl}:</b> grau {grau} · média fala {mf if mf is not None else '—'} dB"
                + (" · padrão sugestivo de PAIR" if o.get("sugestivo_pair") else ""),
                st["body"]))
    if a.reteste_indicado:
        el.append(Spacer(1, 4))
        el.append(Paragraph("⚠ Reteste imediato indicado (piora significativa em relação à referência).", st["body"]))

    el.append(Spacer(1, 20))
    el.append(HRFlowable(width="50%", thickness=0.5, color=MUTED))
    el.append(Paragraph(f"{a.responsavel or '_______________________'} — {a.conselho or ''}", st["small"]))
    el.append(Paragraph("Responsável técnico pelo exame", st["small"]))

    doc.build(el)
    buf.seek(0)
    return buf.getvalue()


# ── Página ───────────────────────────────────────────────────────────────────

@requer_feature_pacote("sst.audiometria", "Audiometria")
@requer_permissao_modulo("sst.clinico")
def sst_audiometria_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_audiometria.html", {"empresa_nome": empresa.nome})
