"""
Psicossocial NR-01 — Avaliação de riscos psicossociais no trabalho — SolusCRT SST.
Baseado na NR-01 (atualização 2024) e metodologia Copenhagen Psychosocial Questionnaire.

Endpoints:
  GET  /api/sst/psicossocial/                           — lista avaliações
  POST /api/sst/psicossocial/                           — cria avaliação
  GET  /api/sst/psicossocial/<id>/                      — detalhe
  PATCH/DELETE /api/sst/psicossocial/<id>/              — atualiza / remove
  POST /api/sst/psicossocial/<id>/ativar/               — ativa e gera link_token
  GET  /api/sst/psicossocial/<id>/questoes/             — lista questões
  POST /api/sst/psicossocial/<id>/questoes/             — adiciona questão
  POST /api/sst/psicossocial/responder/<token>/         — responde (público, sem auth)
  GET  /api/sst/psicossocial/<id>/resultados/           — resultados e scores
  GET  /api/sst/psicossocial/<id>/pdf/                  — PDF relatório
  GET  /api/sst/psicossocial/kpis/                      — KPIs geral
  GET  /sst/psicossocial/                               — página
"""
import io
import json
import secrets
from datetime import date

from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

from .access_control import api_requer_feature, requer_permissao_modulo

# ── Palette ──────────────────────────────────────────────────────────────────
TEAL   = colors.HexColor("#00c9a7")
DARK   = colors.HexColor("#071c28")
MUTED  = colors.HexColor("#7a9fa0")
WHITE  = colors.white
BLACK  = colors.black
LGREY  = colors.HexColor("#f4f8f7")
AMBER  = colors.HexColor("#f0bf6b")
RED    = colors.HexColor("#f87171")
GREEN  = colors.HexColor("#34d399")
PURPLE = colors.HexColor("#a374ff")

W, H = A4

# ── Categorias e labels ───────────────────────────────────────────────────────
CATEGORIA_LABELS = {
    "carga_trabalho":  "Carga de Trabalho",
    "autonomia":       "Autonomia e Controle",
    "relacionamento":  "Relacionamento Interpessoal",
    "reconhecimento":  "Reconhecimento e Recompensa",
    "seguranca":       "Segurança no Emprego",
    "equilibrio":      "Equilíbrio Trabalho-Vida",
    "violencia":       "Violência e Assédio",
}

NIVEL_RISCO = {
    "baixo":   (75, 100),
    "medio":   (50, 74),
    "alto":    (25, 49),
    "critico": (0,  24),
}


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
        "body":   ParagraphStyle("body",   fontSize=9,  fontName="Helvetica",      textColor=BLACK, leading=13, spaceAfter=4),
        "small":  ParagraphStyle("small",  fontSize=8,  fontName="Helvetica",      textColor=MUTED, leading=11),
        "center": ParagraphStyle("center", fontSize=9,  fontName="Helvetica",      textColor=MUTED, leading=13, alignment=1),
        "bold":   ParagraphStyle("bold",   fontSize=10, fontName="Helvetica-Bold", textColor=BLACK, leading=14),
    }


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


def _avaliacao_dict(av):
    return {
        "id": av.id,
        "titulo": av.titulo,
        "descricao": av.descricao,
        "setor_alvo": av.setor_alvo,
        "data_inicio": str(av.data_inicio),
        "data_fim": str(av.data_fim) if av.data_fim else None,
        "status": av.status,
        "anonima": av.anonima,
        "link_token": av.link_token,
        "total_enviados": av.total_enviados,
        "total_respondidos": av.total_respondidos,
        "criado_em": str(av.criado_em.date()),
        "atualizado_em": str(av.atualizado_em.date()),
    }


def _questao_dict(q):
    return {
        "id": q.id,
        "texto": q.texto,
        "categoria": q.categoria,
        "categoria_label": CATEGORIA_LABELS.get(q.categoria, q.categoria),
        "ordem": q.ordem,
        "escala": q.escala,
    }


def _calcular_score(av_id):
    """Calcula médias por categoria e score geral (0-100) para a avaliação."""
    from .models import QuestaoAvaliacaoPsicossocial, RespostaPsicossocial

    resultados = {}
    for cat, label in CATEGORIA_LABELS.items():
        questoes_ids = list(
            QuestaoAvaliacaoPsicossocial.objects.filter(
                avaliacao_id=av_id, categoria=cat, escala="likert5"
            ).values_list("id", flat=True)
        )
        if not questoes_ids:
            continue

        media = RespostaPsicossocial.objects.filter(
            avaliacao_id=av_id,
            questao_id__in=questoes_ids,
            resposta_num__isnull=False,
        ).aggregate(m=Avg("resposta_num"))["m"]

        if media is not None:
            # Normaliza: Likert 1-5 → score 0-100
            # 5 = ótimo (100), 1 = péssimo (0)
            score = round((media - 1) / 4 * 100, 1)
            resultados[cat] = {
                "label": label,
                "media_likert": round(media, 2),
                "score": score,
            }

    # Score geral = média dos scores de categoria
    if resultados:
        score_geral = round(sum(v["score"] for v in resultados.values()) / len(resultados), 1)
    else:
        score_geral = None

    nivel = None
    if score_geral is not None:
        for n, (minv, maxv) in NIVEL_RISCO.items():
            if minv <= score_geral <= maxv:
                nivel = n
                break

    return resultados, score_geral, nivel


# ── Views ─────────────────────────────────────────────────────────────────────

@api_requer_feature("sst.psicossocial")
def api_psicossocial_avaliacoes(request):
    """GET lista + POST cria avaliação."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import AvaliacaoPsicossocial

    if request.method == "GET":
        try:
            status_f = request.GET.get("status")
            qs = AvaliacaoPsicossocial.objects.filter(empresa=empresa)
            if status_f:
                qs = qs.filter(status=status_f)
            return JsonResponse({
                "total": qs.count(),
                "avaliacoes": [_avaliacao_dict(av) for av in qs[:50]],
            })
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "POST":
        try:
            data = _json(request)
            if not data.get("titulo") or not data.get("data_inicio"):
                return JsonResponse({"erro": "titulo e data_inicio são obrigatórios"}, status=400)

            av = AvaliacaoPsicossocial.objects.create(
                empresa=empresa,
                titulo=data["titulo"],
                descricao=data.get("descricao", ""),
                setor_alvo=data.get("setor_alvo", ""),
                data_inicio=data["data_inicio"],
                data_fim=data.get("data_fim") or None,
                status="rascunho",
                anonima=data.get("anonima", True),
                link_token=secrets.token_hex(32),
            )
            return JsonResponse({"ok": True, "data": _avaliacao_dict(av)}, status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.psicossocial")
def api_psicossocial_detalhe(request, av_id):
    """GET + PATCH + DELETE de uma avaliação."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import AvaliacaoPsicossocial

    try:
        av = AvaliacaoPsicossocial.objects.get(id=av_id, empresa=empresa)
    except AvaliacaoPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Avaliação não encontrada"}, status=404)

    if request.method == "GET":
        d = _avaliacao_dict(av)
        d["total_questoes"] = av.questoes.count()
        return JsonResponse(d)

    if request.method in ("PATCH", "PUT"):
        try:
            data = _json(request)
            if av.status in ("ativa", "processada"):
                campos_permitidos = ("data_fim", "status")
            else:
                campos_permitidos = ("titulo", "descricao", "setor_alvo", "data_inicio",
                                     "data_fim", "anonima", "status")
            for field in campos_permitidos:
                if field in data:
                    setattr(av, field, data[field])
            av.save()
            return JsonResponse({"ok": True, "data": _avaliacao_dict(av)})
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "DELETE":
        try:
            if av.status == "ativa":
                return JsonResponse({"erro": "Não é possível excluir avaliação ativa"}, status=400)
            av.delete()
            return JsonResponse({"ok": True, "msg": "Avaliação removida"})
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.psicossocial")
def api_psicossocial_ativar(request, av_id):
    """POST — ativa avaliação e gera link_token."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    from .models import AvaliacaoPsicossocial

    try:
        av = AvaliacaoPsicossocial.objects.get(id=av_id, empresa=empresa)
        if av.status != "rascunho":
            return JsonResponse({"erro": f"Avaliação não pode ser ativada — status: {av.status}"}, status=400)
        if av.questoes.count() == 0:
            return JsonResponse({"erro": "Adicione ao menos uma questão antes de ativar"}, status=400)

        av.status = "ativa"
        av.link_token = secrets.token_hex(32)
        av.save(update_fields=["status", "link_token"])

        link_publico = f"/api/sst/psicossocial/responder/{av.link_token}/"
        return JsonResponse({
            "ok": True,
            "link_token": av.link_token,
            "link_publico": link_publico,
            "data": _avaliacao_dict(av),
        })
    except AvaliacaoPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Avaliação não encontrada"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.psicossocial")
def api_psicossocial_questoes(request, av_id):
    """GET lista questões + POST adiciona questão."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import AvaliacaoPsicossocial, QuestaoAvaliacaoPsicossocial

    try:
        av = AvaliacaoPsicossocial.objects.get(id=av_id, empresa=empresa)
    except AvaliacaoPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Avaliação não encontrada"}, status=404)

    if request.method == "GET":
        try:
            questoes = av.questoes.all()
            return JsonResponse({
                "total": questoes.count(),
                "questoes": [_questao_dict(q) for q in questoes],
            })
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "POST":
        try:
            if av.status not in ("rascunho",):
                return JsonResponse({"erro": "Questões só podem ser adicionadas em avaliações em rascunho"}, status=400)

            data = _json(request)
            if not data.get("texto") or not data.get("categoria"):
                return JsonResponse({"erro": "texto e categoria são obrigatórios"}, status=400)

            ultima_ordem = av.questoes.count()
            q = QuestaoAvaliacaoPsicossocial.objects.create(
                avaliacao=av,
                texto=data["texto"],
                categoria=data["categoria"],
                ordem=data.get("ordem", ultima_ordem + 1),
                escala=data.get("escala", "likert5"),
            )
            return JsonResponse({"ok": True, "data": _questao_dict(q)}, status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
def api_psicossocial_responder_publico(request, token):
    """POST público (sem auth) — registra respostas do colaborador."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        from .models import AvaliacaoPsicossocial, QuestaoAvaliacaoPsicossocial, RespostaPsicossocial

        av = AvaliacaoPsicossocial.objects.get(link_token=token, status="ativa")
        data = _json(request)
        respostas = data.get("respostas", [])

        if not respostas:
            return JsonResponse({"erro": "Nenhuma resposta enviada"}, status=400)

        criadas = 0
        for r in respostas:
            questao_id = r.get("questao_id")
            if not questao_id:
                continue
            try:
                questao = QuestaoAvaliacaoPsicossocial.objects.get(id=questao_id, avaliacao=av)
                resposta_num = r.get("resposta_num")
                resposta_bool_raw = r.get("resposta_bool")
                resposta_bool = None
                if resposta_bool_raw is not None:
                    resposta_bool = bool(resposta_bool_raw)

                RespostaPsicossocial.objects.create(
                    avaliacao=av,
                    questao=questao,
                    resposta_num=resposta_num,
                    resposta_bool=resposta_bool,
                    funcionario=None,  # anônimo
                )
                criadas += 1
            except QuestaoAvaliacaoPsicossocial.DoesNotExist:
                continue

        # Atualiza contador de respondidos (aprox. — conta sessões únicas via respostas criadas)
        if criadas > 0:
            av.total_respondidos = av.total_respondidos + 1
            av.save(update_fields=["total_respondidos"])

        return JsonResponse({"ok": True, "respostas_registradas": criadas})

    except AvaliacaoPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Avaliação não encontrada ou não está ativa"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.psicossocial")
def api_psicossocial_resultados(request, av_id):
    """GET — resultados com médias por categoria e score geral."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import AvaliacaoPsicossocial

        av = AvaliacaoPsicossocial.objects.get(id=av_id, empresa=empresa)
        categorias, score_geral, nivel = _calcular_score(av_id)

        return JsonResponse({
            "avaliacao_id": av.id,
            "titulo": av.titulo,
            "total_respondidos": av.total_respondidos,
            "total_enviados": av.total_enviados,
            "score_geral": score_geral,
            "nivel_risco": nivel,
            "categorias": categorias,
            "interpretacao": {
                "baixo":   "Score 75-100: Risco baixo — ambiente favorável.",
                "medio":   "Score 50-74: Risco médio — atenção a categorias críticas.",
                "alto":    "Score 25-49: Risco alto — intervenção recomendada.",
                "critico": "Score 0-24: Risco crítico — intervenção urgente.",
            }.get(nivel, "Sem dados suficientes para calcular."),
        })
    except AvaliacaoPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Avaliação não encontrada"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.psicossocial")
def api_psicossocial_pdf(request, av_id):
    """GET — PDF relatório da avaliação psicossocial."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import AvaliacaoPsicossocial

        av = AvaliacaoPsicossocial.objects.get(id=av_id, empresa=empresa)
        categorias, score_geral, nivel = _calcular_score(av_id)

        buf = io.BytesIO()
        styles = _styles()

        pdf = SimpleDocTemplate(
            buf, pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        story = []

        # Cabeçalho
        header_data = [[
            Paragraph("<b>SolusCRT</b>", ParagraphStyle("logo", fontName="Helvetica-Bold", fontSize=14, textColor=TEAL, leading=18)),
            Paragraph(empresa.nome, ParagraphStyle("en", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13, alignment=2)),
        ]]
        ht = Table(header_data, colWidths=[W * 0.5 - 2 * cm, W * 0.5 - 2 * cm])
        ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(ht)
        story.append(HRFlowable(width="100%", thickness=2, color=TEAL, spaceAfter=8))
        story.append(Paragraph("Relatório de Avaliação Psicossocial — NR-01", styles["title"]))
        story.append(Paragraph(
            f"Empresa: {empresa.nome} · Gerado em: {date.today().strftime('%d/%m/%Y')}",
            styles["sub"]
        ))
        story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=10))

        # Info da avaliação
        story.append(Paragraph("1. Dados da Avaliação", styles["h2"]))
        meta = [
            ["Campo", "Informação"],
            ["Título", av.titulo],
            ["Setor Alvo", av.setor_alvo or "Toda a empresa"],
            ["Data Início", str(av.data_inicio)],
            ["Status", av.status.capitalize()],
            ["Anônima", "Sim" if av.anonima else "Não"],
            ["Respondentes", f"{av.total_respondidos} de {av.total_enviados} enviados"],
        ]
        t = Table(meta, colWidths=[5 * cm, W - 9 * cm])
        t.setStyle(_table_style_base())
        story.append(t)
        story.append(Spacer(1, 12))

        # Score geral
        story.append(Paragraph("2. Score Geral e Nível de Risco", styles["h2"]))
        if score_geral is not None:
            cor_nivel = {"baixo": GREEN, "medio": AMBER, "alto": RED, "critico": RED}.get(nivel, MUTED)
            score_data = [
                ["Score Geral", "Nível de Risco", "Interpretação"],
                [
                    f"{score_geral}/100",
                    (nivel or "—").upper(),
                    {
                        "baixo":   "Risco baixo — ambiente favorável",
                        "medio":   "Risco médio — atenção às categorias críticas",
                        "alto":    "Risco alto — intervenção recomendada",
                        "critico": "Risco crítico — intervenção urgente",
                    }.get(nivel, "—")
                ],
            ]
            ts = Table(score_data, colWidths=[4 * cm, 4 * cm, W - 10 * cm])
            ts.setStyle(_table_style_base())
            story.append(ts)
        else:
            story.append(Paragraph("Dados insuficientes para cálculo de score.", styles["small"]))
        story.append(Spacer(1, 12))

        # Scores por categoria
        story.append(Paragraph("3. Resultados por Categoria", styles["h2"]))
        if categorias:
            cat_data = [["Categoria", "Média Likert (1-5)", "Score (0-100)"]]
            for cat_key, cat_val in sorted(categorias.items(), key=lambda x: x[1]["score"]):
                cat_data.append([
                    cat_val["label"],
                    str(cat_val["media_likert"]),
                    f"{cat_val['score']}/100",
                ])
            tc = Table(cat_data, colWidths=[7 * cm, 5 * cm, W - 14 * cm])
            tc.setStyle(_table_style_base())
            story.append(tc)
        else:
            story.append(Paragraph("Nenhuma resposta registrada.", styles["small"]))
        story.append(Spacer(1, 12))

        # Recomendações
        story.append(Paragraph("4. Recomendações", styles["h2"]))
        story.append(Paragraph(
            "Com base nos resultados desta avaliação, recomenda-se: (1) revisar carga de trabalho nas "
            "áreas com maior risco; (2) implementar programas de desenvolvimento de liderança positiva; "
            "(3) estabelecer canais de comunicação e reconhecimento; (4) reavaliar em até 12 meses.",
            styles["body"]
        ))
        story.append(Spacer(1, 16))

        # Rodapé
        story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=6))
        story.append(Paragraph(
            f"Gerado por SolusCRT em {date.today().strftime('%d/%m/%Y')} · Relatório Psicossocial — NR-01 / Portaria MTE 1.419/2024",
            styles["center"]
        ))

        pdf.build(story)
        buf.seek(0)

        nome_arquivo = f"Psicossocial_{av.id}_{empresa.nome.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf"
        resp = HttpResponse(buf.read(), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
        return resp

    except AvaliacaoPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Avaliação não encontrada"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.psicossocial")
def api_psicossocial_kpis(request):
    """GET — KPIs de avaliações psicossociais da empresa."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import AvaliacaoPsicossocial

        qs = AvaliacaoPsicossocial.objects.filter(empresa=empresa)
        total = qs.count()
        ativas = qs.filter(status="ativa").count()
        respondidas = qs.filter(status__in=("encerrada", "processada")).count()

        # Score médio de avaliações processadas
        scores = []
        for av in qs.filter(status__in=("encerrada", "processada", "ativa"))[:10]:
            _, score, _ = _calcular_score(av.id)
            if score is not None:
                scores.append(score)

        score_medio = round(sum(scores) / len(scores), 1) if scores else None

        return JsonResponse({
            "total_avaliacoes": total,
            "ativas": ativas,
            "respondidas": respondidas,
            "rascunhos": qs.filter(status="rascunho").count(),
            "score_medio_empresa": score_medio,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@requer_permissao_modulo("sst.clinico")
def sst_psicossocial_page(request):
    """Página Psicossocial — renderiza template."""
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada

    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_psicossocial.html", {"empresa_nome": empresa.nome})
