"""
CIPA — Comissão Interna de Prevenção de Acidentes (NR-5)
Gestão completa de comissões, membros, reuniões e atas — SolusCRT SST.

Endpoints:
  GET  /api/sst/cipa/comissoes/                    — lista comissões
  POST /api/sst/cipa/comissoes/                    — cria comissão
  GET  /api/sst/cipa/comissoes/<id>/               — detalhe
  PATCH/DELETE /api/sst/cipa/comissoes/<id>/       — atualiza / remove
  GET  /api/sst/cipa/comissoes/<id>/membros/       — lista membros
  POST /api/sst/cipa/comissoes/<id>/membros/       — adiciona membro
  GET  /api/sst/cipa/comissoes/<id>/reunioes/      — lista reuniões
  POST /api/sst/cipa/comissoes/<id>/reunioes/      — cria reunião
  GET  /api/sst/cipa/reunioes/<id>/                — detalhe reunião
  PATCH /api/sst/cipa/reunioes/<id>/               — atualiza reunião
  GET  /api/sst/cipa/reunioes/<id>/ata/pdf/        — PDF da ata
  GET  /api/sst/cipa/kpis/                         — KPIs CIPA
  GET  /sst/cipa/                                  — página CIPA
"""
import io
import json
from datetime import date, datetime

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q

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
AMBER = colors.HexColor("#f0bf6b")

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
        "h3":     ParagraphStyle("h3",     fontSize=10, fontName="Helvetica-Bold", textColor=DARK,  leading=14, spaceBefore=8, spaceAfter=3),
        "label":  ParagraphStyle("label",  fontSize=8,  fontName="Helvetica-Bold", textColor=MUTED, leading=11),
        "value":  ParagraphStyle("value",  fontSize=10, fontName="Helvetica",      textColor=BLACK, leading=14, spaceBefore=1, spaceAfter=4),
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


def _comissao_dict(c):
    return {
        "id": c.id,
        "mandato_inicio": str(c.mandato_inicio),
        "mandato_fim": str(c.mandato_fim),
        "numero_membros_eleitos": c.numero_membros_eleitos,
        "numero_membros_indicados": c.numero_membros_indicados,
        "status": c.status,
        "designacao_nr5": c.designacao_nr5,
        "criado_em": str(c.criado_em.date()),
        "atualizado_em": str(c.atualizado_em.date()),
    }


def _membro_dict(m):
    return {
        "id": m.id,
        "funcionario_id": m.funcionario_id,
        "funcionario_nome": m.funcionario.nome,
        "funcionario_cargo_empresa": m.funcionario.cargo,
        "cargo_cipa": m.cargo,
        "tipo": m.tipo,
        "data_posse": str(m.data_posse) if m.data_posse else None,
        "ativo": m.ativo,
        "criado_em": str(m.criado_em.date()),
    }


def _reuniao_dict(r):
    return {
        "id": r.id,
        "comissao_id": r.comissao_id,
        "tipo": r.tipo,
        "data_reuniao": str(r.data_reuniao),
        "pauta": r.pauta,
        "ata": r.ata,
        "local": r.local,
        "status": r.status,
        "criado_em": str(r.criado_em.date()),
        "atualizado_em": str(r.atualizado_em.date()),
    }


# ── Views ─────────────────────────────────────────────────────────────────────

@api_requer_feature("sst.cipa")
def api_cipa_comissoes(request):
    """GET lista comissões + POST cria comissão."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import ComissaoCIPA

    if request.method == "GET":
        try:
            status_f = request.GET.get("status")
            qs = ComissaoCIPA.objects.filter(empresa=empresa)
            if status_f:
                qs = qs.filter(status=status_f)
            return JsonResponse({
                "total": qs.count(),
                "comissoes": [_comissao_dict(c) for c in qs[:50]],
            })
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "POST":
        try:
            data = _json(request)
            if not data.get("mandato_inicio") or not data.get("mandato_fim"):
                return JsonResponse({"erro": "mandato_inicio e mandato_fim são obrigatórios"}, status=400)

            c = ComissaoCIPA.objects.create(
                empresa=empresa,
                mandato_inicio=data["mandato_inicio"],
                mandato_fim=data["mandato_fim"],
                numero_membros_eleitos=data.get("numero_membros_eleitos", 0),
                numero_membros_indicados=data.get("numero_membros_indicados", 0),
                status=data.get("status", "em_formacao"),
                designacao_nr5=data.get("designacao_nr5", False),
            )
            return JsonResponse({"ok": True, "data": _comissao_dict(c)}, status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_comissao_detalhe(request, comissao_id):
    """GET + PATCH + DELETE de uma comissão."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import ComissaoCIPA

    try:
        c = ComissaoCIPA.objects.get(id=comissao_id, empresa=empresa)
    except ComissaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Comissão não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_comissao_dict(c))

    if request.method in ("PATCH", "PUT"):
        try:
            data = _json(request)
            for field in ("mandato_inicio", "mandato_fim", "numero_membros_eleitos",
                          "numero_membros_indicados", "status", "designacao_nr5"):
                if field in data:
                    setattr(c, field, data[field])
            c.save()
            return JsonResponse({"ok": True, "data": _comissao_dict(c)})
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "DELETE":
        try:
            c.delete()
            return JsonResponse({"ok": True, "msg": "Comissão removida"})
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_membros(request, comissao_id):
    """GET lista membros + POST adiciona membro."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import ComissaoCIPA, MembroCIPA, FuncionarioSST

    try:
        comissao = ComissaoCIPA.objects.get(id=comissao_id, empresa=empresa)
    except ComissaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Comissão não encontrada"}, status=404)

    if request.method == "GET":
        try:
            membros = MembroCIPA.objects.filter(comissao=comissao).select_related("funcionario")
            return JsonResponse({
                "total": membros.count(),
                "membros": [_membro_dict(m) for m in membros],
            })
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "POST":
        try:
            data = _json(request)
            if not data.get("funcionario_id") or not data.get("cargo") or not data.get("tipo"):
                return JsonResponse({"erro": "funcionario_id, cargo e tipo são obrigatórios"}, status=400)

            func = FuncionarioSST.objects.get(id=data["funcionario_id"], empresa=empresa)
            m = MembroCIPA.objects.create(
                comissao=comissao,
                funcionario=func,
                cargo=data["cargo"],
                tipo=data["tipo"],
                data_posse=data.get("data_posse") or None,
                ativo=data.get("ativo", True),
            )
            return JsonResponse({"ok": True, "data": _membro_dict(m)}, status=201)
        except FuncionarioSST.DoesNotExist:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_reunioes(request, comissao_id):
    """GET lista reuniões + POST cria reunião."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import ComissaoCIPA, ReuniaoCIPA

    try:
        comissao = ComissaoCIPA.objects.get(id=comissao_id, empresa=empresa)
    except ComissaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Comissão não encontrada"}, status=404)

    if request.method == "GET":
        try:
            qs = ReuniaoCIPA.objects.filter(comissao=comissao)
            status_f = request.GET.get("status")
            if status_f:
                qs = qs.filter(status=status_f)
            return JsonResponse({
                "total": qs.count(),
                "reunioes": [_reuniao_dict(r) for r in qs[:50]],
            })
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    if request.method == "POST":
        try:
            data = _json(request)
            if not data.get("data_reuniao"):
                return JsonResponse({"erro": "data_reuniao é obrigatória"}, status=400)

            r = ReuniaoCIPA.objects.create(
                comissao=comissao,
                tipo=data.get("tipo", "ordinaria"),
                data_reuniao=data["data_reuniao"],
                pauta=data.get("pauta", ""),
                ata=data.get("ata", ""),
                local=data.get("local", ""),
                status=data.get("status", "agendada"),
            )
            return JsonResponse({"ok": True, "data": _reuniao_dict(r)}, status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_reuniao_detalhe(request, reuniao_id):
    """GET + PATCH de uma reunião."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    from .models import ReuniaoCIPA

    try:
        r = ReuniaoCIPA.objects.get(id=reuniao_id, comissao__empresa=empresa)
    except ReuniaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Reunião não encontrada"}, status=404)

    if request.method == "GET":
        d = _reuniao_dict(r)
        # adiciona participantes
        participantes = r.participantes.select_related("funcionario").all()
        d["participantes"] = [
            {
                "funcionario_id": p.funcionario_id,
                "funcionario_nome": p.funcionario.nome,
                "presente": p.presente,
            }
            for p in participantes
        ]
        return JsonResponse(d)

    if request.method in ("PATCH", "PUT"):
        try:
            data = _json(request)
            for field in ("tipo", "data_reuniao", "pauta", "ata", "local", "status"):
                if field in data:
                    setattr(r, field, data[field])
            r.save()
            return JsonResponse({"ok": True, "data": _reuniao_dict(r)})
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_ata_pdf(request, reuniao_id):
    """GET — gera PDF da ata da reunião CIPA."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import ReuniaoCIPA

        r = ReuniaoCIPA.objects.get(id=reuniao_id, comissao__empresa=empresa)
        participantes = list(
            r.participantes.select_related("funcionario").all()
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
        header_data = [[
            Paragraph("<b>SolusCRT</b>", ParagraphStyle("logo", fontName="Helvetica-Bold", fontSize=14, textColor=TEAL, leading=18)),
            Paragraph(empresa.nome, ParagraphStyle("en", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13, alignment=2)),
        ]]
        ht = Table(header_data, colWidths=[W * 0.5 - 2 * cm, W * 0.5 - 2 * cm])
        ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(ht)
        story.append(HRFlowable(width="100%", thickness=2, color=TEAL, spaceAfter=8))
        story.append(Paragraph("Ata de Reunião CIPA", styles["title"]))

        data_fmt = r.data_reuniao.strftime("%d/%m/%Y às %H:%M") if r.data_reuniao else "—"
        story.append(Paragraph(
            f"Reunião {r.tipo.capitalize()} · {data_fmt} · {r.local or 'Local não informado'}",
            styles["sub"]
        ))
        story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=10))

        # Cabeçalho da reunião
        story.append(Paragraph("1. Dados da Reunião", styles["h2"]))
        meta = [
            ["Campo", "Informação"],
            ["Empresa", empresa.nome],
            ["Tipo de Reunião", r.tipo.capitalize()],
            ["Data e Hora", data_fmt],
            ["Local", r.local or "—"],
            ["Status", r.status.capitalize()],
        ]
        t = Table(meta, colWidths=[5 * cm, W - 9 * cm])
        t.setStyle(_table_style_base())
        story.append(t)
        story.append(Spacer(1, 12))

        # Pauta
        story.append(Paragraph("2. Pauta", styles["h2"]))
        story.append(Paragraph(r.pauta or "Pauta não registrada.", styles["body"]))
        story.append(Spacer(1, 12))

        # Participantes
        story.append(Paragraph("3. Lista de Presença", styles["h2"]))
        if participantes:
            p_data = [["Nome", "Presente", "Assinatura"]]
            for p in participantes:
                p_data.append([
                    p.funcionario.nome,
                    "Sim" if p.presente else "Não",
                    "________________________",
                ])
            tp = Table(p_data, colWidths=[8 * cm, 3 * cm, W - 13 * cm])
            tp.setStyle(_table_style_base())
            story.append(tp)
        else:
            story.append(Paragraph("Nenhum participante registrado.", styles["small"]))
        story.append(Spacer(1, 12))

        # Ata / Deliberações
        story.append(Paragraph("4. Deliberações / Ata", styles["h2"]))
        story.append(Paragraph(r.ata or "Ata não registrada.", styles["body"]))
        story.append(Spacer(1, 20))

        # Assinatura presidente
        story.append(HRFlowable(width="60%", thickness=0.5, color=LGREY, spaceAfter=4))
        story.append(Paragraph("Presidente da CIPA / Responsável", styles["center"]))
        story.append(Spacer(1, 12))

        # Rodapé
        story.append(HRFlowable(width="100%", thickness=0.5, color=LGREY, spaceAfter=6))
        hoje = date.today().strftime("%d/%m/%Y")
        story.append(Paragraph(
            f"Gerado por SolusCRT em {hoje} · Ata CIPA — NR-5 / CLT art. 163",
            styles["center"]
        ))

        pdf.build(story)
        buf.seek(0)

        nome_arquivo = f"ATA_CIPA_Reuniao{r.id}_{date.today().strftime('%Y%m%d')}.pdf"
        resp = HttpResponse(buf.read(), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
        return resp

    except ReuniaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Reunião não encontrada"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.cipa")
def api_cipa_kpis(request):
    """GET — KPIs CIPA."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import ComissaoCIPA, ReuniaoCIPA
        import datetime

        comissao_ativa = ComissaoCIPA.objects.filter(empresa=empresa, status="ativa").first()
        hoje = date.today()
        ano_atual = hoje.year

        # Próxima reunião
        proxima_reuniao = None
        total_reunioes_ano = 0
        reunioes_realizadas_ano = 0

        if comissao_ativa:
            proxima = ReuniaoCIPA.objects.filter(
                comissao=comissao_ativa,
                status="agendada",
                data_reuniao__gte=datetime.datetime.now()
            ).order_by("data_reuniao").first()

            if proxima:
                proxima_reuniao = {
                    "id": proxima.id,
                    "data": str(proxima.data_reuniao),
                    "tipo": proxima.tipo,
                    "local": proxima.local,
                }

            total_reunioes_ano = ReuniaoCIPA.objects.filter(
                comissao=comissao_ativa,
                data_reuniao__year=ano_atual,
            ).count()

            reunioes_realizadas_ano = ReuniaoCIPA.objects.filter(
                comissao=comissao_ativa,
                data_reuniao__year=ano_atual,
                status="realizada",
            ).count()

        total_comissoes = ComissaoCIPA.objects.filter(empresa=empresa).count()

        return JsonResponse({
            "total_comissoes": total_comissoes,
            "comissao_ativa": _comissao_dict(comissao_ativa) if comissao_ativa else None,
            "proxima_reuniao": proxima_reuniao,
            "reunioes_no_ano": total_reunioes_ano,
            "reunioes_realizadas_ano": reunioes_realizadas_ano,
            "ano": ano_atual,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@requer_feature_pacote("sst.cipa", "CIPA")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_cipa_page(request):
    """Página CIPA — renderiza template."""
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada

    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_cipa.html", {"empresa_nome": empresa.nome})
