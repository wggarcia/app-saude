"""
PPP — Perfil Profissiográfico Previdenciário (SolusCRT SST)
Geração automatizada conforme IN INSS 128/2022 e eSocial S-2240.

Endpoints:
  GET  /api/sst/ppp/                       — lista PPPs da empresa
  POST /api/sst/ppp/                       — gerar PPP de um funcionário
  GET  /api/sst/ppp/<id>/                  — detalhe
  POST /api/sst/ppp/<id>/finalizar/        — finalizar e assinar
  GET  /api/sst/ppp/<id>/pdf/              — exportar PDF
  GET  /api/sst/ppp/kpis/                  — painel de cobertura
"""
from datetime import date, timedelta
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
import json


def _empresa(request):
    return getattr(request, "empresa", None)


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


def _ppp_dict(ppp):
    return {
        "id": ppp.id,
        "funcionario_id": ppp.funcionario_id,
        "funcionario_nome": ppp.funcionario.nome,
        "funcionario_cpf": ppp.funcionario.cpf,
        "funcionario_nit": ppp.nit_pis,
        "cargo": ppp.funcionario.cargo,
        "cbo": ppp.cbo,
        "data_admissao": str(ppp.funcionario.data_admissao or ""),
        "data_desligamento": str(ppp.data_desligamento or ""),
        "data_geracao": str(ppp.data_geracao),
        "status": ppp.status,
        "responsavel_tecnico": ppp.responsavel_tecnico,
        "conselho_registro": ppp.conselho_registro,
        "agentes_nocivos": ppp.agentes_nocivos,
        "monitoracao_biologica": ppp.monitoracao_biologica,
        "historico_cargos": ppp.historico_cargos,
        "resultado_conclusao": ppp.resultado_conclusao,
        "criado_em": str(ppp.criado_em.date()),
    }


# ──────────────────────────────────────────────
# HELPERS DE PREENCHIMENTO AUTOMÁTICO
# ──────────────────────────────────────────────

def _coletar_agentes_nocivos(funcionario, empresa):
    """Coleta agentes nocivos do S-2240 (PostoTrabalho + AgentesNocivos)."""
    try:
        from .models import PostoTrabalho, AgenteNocivoSST
        postos = PostoTrabalho.objects.filter(empresa=empresa, ativo=True)
        # tenta filtrar por setor do funcionário
        if funcionario.setor:
            postos_setor = postos.filter(setor__icontains=funcionario.setor)
            if postos_setor.exists():
                postos = postos_setor

        agentes = []
        for posto in postos:
            for agente in AgenteNocivoSST.objects.filter(posto=posto):
                agentes.append({
                    "codigo_tabela": agente.codigo_tabela,
                    "descricao": agente.descricao,
                    "tipo": agente.tipo,          # fisico / quimico / biologico / ergonomico
                    "tecnica_medicao": agente.tecnica_medicao,
                    "intensidade_concentracao": agente.intensidade_concentracao,
                    "limite_tolerancia": agente.limite_tolerancia,
                    "epc_eficaz": agente.epc_eficaz,
                    "epi_ca": agente.epi_ca,
                    "data_avaliacao": str(agente.data_avaliacao or ""),
                })
        return agentes
    except Exception:
        return []


def _coletar_monitoracao(funcionario, empresa):
    """Coleta resultados de exames laboratoriais (monitoração biológica)."""
    try:
        from .models import ResultadoExameLaboratorio
        resultados = ResultadoExameLaboratorio.objects.filter(
            funcionario=funcionario
        ).order_by("-data_coleta")[:20]
        return [
            {
                "exame": r.exame,
                "data_coleta": str(r.data_coleta),
                "resultado": r.resultado,
                "unidade": r.unidade,
                "valor_referencia": r.valor_referencia,
                "laboratorio": r.laboratorio_nome,
                "alterado": r.alterado,
            }
            for r in resultados
        ]
    except Exception:
        return []


def _historico_cargos(funcionario, empresa):
    """Coleta histórico de cargos do funcionário via ASOs."""
    try:
        from .models import ASOOcupacional
        asos = ASOOcupacional.objects.filter(
            funcionario=funcionario
        ).order_by("data_exame")
        cargos = []
        cargo_ant = None
        for aso in asos:
            if aso.cargo != cargo_ant:
                cargos.append({
                    "cargo": aso.cargo,
                    "data_inicio": str(aso.data_exame),
                    "setor": aso.setor or funcionario.setor,
                })
                cargo_ant = aso.cargo
        return cargos
    except Exception:
        return []


# ──────────────────────────────────────────────
# VIEWS
# ──────────────────────────────────────────────

def api_ppp_lista(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import PPPFuncionario
        qs = PPPFuncionario.objects.filter(empresa=empresa).select_related("funcionario")

        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        func_id = request.GET.get("funcionario_id")
        if func_id:
            qs = qs.filter(funcionario_id=func_id)

        return JsonResponse({
            "total": qs.count(),
            "ppps": [_ppp_dict(p) for p in qs.order_by("-data_geracao")[:200]],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_ppp_criar(request):
    """Gera PPP automaticamente a partir dos dados existentes (ASO, S2240, exames)."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    data = _json(request)
    funcionario_id = data.get("funcionario_id")
    if not funcionario_id:
        return JsonResponse({"erro": "funcionario_id obrigatório"}, status=400)

    try:
        from .models import FuncionarioSST, PPPFuncionario

        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)

        # CBO padrão por cargo (pode ser expandido)
        CBO_MAP = {
            "gerente": "1231-05", "supervisor": "3517-10", "operador": "7170-35",
            "tecnico": "3115-10", "engenheiro": "2143-05", "assistente": "4110-05",
            "auxiliar": "4110-05", "analista": "2521-05",
        }
        cargo_lower = func.cargo.lower()
        cbo = next((v for k, v in CBO_MAP.items() if k in cargo_lower), "0000-00")

        ppp = PPPFuncionario.objects.create(
            empresa=empresa,
            funcionario=func,
            nit_pis=data.get("nit_pis", ""),
            cbo=data.get("cbo", cbo),
            data_geracao=date.today(),
            data_desligamento=data.get("data_desligamento") or None,
            responsavel_tecnico=data.get("responsavel_tecnico", empresa.nome),
            conselho_registro=data.get("conselho_registro", ""),
            agentes_nocivos=_coletar_agentes_nocivos(func, empresa),
            monitoracao_biologica=_coletar_monitoracao(func, empresa),
            historico_cargos=_historico_cargos(func, empresa),
            resultado_conclusao=data.get("resultado_conclusao", "Conforme registros de exposição ocupacional vigentes."),
            status="rascunho",
        )
        return JsonResponse({"sucesso": True, "ppp": _ppp_dict(ppp)}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_ppp_detalhe(request, ppp_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import PPPFuncionario
        ppp = PPPFuncionario.objects.get(id=ppp_id, empresa=empresa)
        if request.method == "PATCH":
            data = _json(request)
            for campo in ["nit_pis", "cbo", "responsavel_tecnico", "conselho_registro",
                          "resultado_conclusao", "agentes_nocivos", "monitoracao_biologica"]:
                if campo in data:
                    setattr(ppp, campo, data[campo])
            ppp.save()
        return JsonResponse(_ppp_dict(ppp))
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_ppp_finalizar(request, ppp_id):
    """Marca PPP como finalizado — pronto para entrega ao trabalhador."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        from .models import PPPFuncionario
        ppp = PPPFuncionario.objects.get(id=ppp_id, empresa=empresa)
        if ppp.status == "finalizado":
            return JsonResponse({"aviso": "PPP já finalizado"})
        ppp.status = "finalizado"
        ppp.data_finalizacao = date.today()
        ppp.save()
        return JsonResponse({"sucesso": True, "status": "finalizado"})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_ppp_pdf(request, ppp_id):
    """Gera PDF do PPP conforme layout da IN INSS 128/2022."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import PPPFuncionario
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        import io

        ppp = PPPFuncionario.objects.get(id=ppp_id, empresa=empresa)
        func = ppp.funcionario
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        titulo = ParagraphStyle("titulo", parent=styles["Heading1"],
                                fontSize=13, textColor=colors.HexColor("#0A2540"),
                                spaceAfter=6)
        subtitulo = ParagraphStyle("sub", parent=styles["Normal"],
                                   fontSize=9, textColor=colors.HexColor("#5A6A80"))
        cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8)

        story = []
        story.append(Paragraph("PERFIL PROFISSIOGRÁFICO PREVIDENCIÁRIO — PPP", titulo))
        story.append(Paragraph(f"SolusCRT Tecnologia em Saúde Ltda. · CNPJ 66.940.015/0001-48 · Gerado em {date.today()}", subtitulo))
        story.append(Spacer(1, 0.4*cm))

        def tabela(dados, col_widths=None):
            t = Table(dados, colWidths=col_widths or [6*cm, 11*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2540")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE3EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            return t

        # SEÇÃO 1 — DADOS DO TRABALHADOR
        story.append(Paragraph("1. DADOS DO TRABALHADOR", styles["Heading2"]))
        story.append(tabela([
            ["Campo", "Valor"],
            ["Nome", func.nome],
            ["CPF", func.cpf or "—"],
            ["NIT/PIS", ppp.nit_pis or "—"],
            ["Data de Nascimento", str(func.data_nascimento or "—")],
            ["Sexo", func.get_sexo_display() if hasattr(func, "get_sexo_display") else (func.sexo or "—")],
            ["Data de Admissão", str(func.data_admissao or "—")],
            ["Data de Desligamento", str(ppp.data_desligamento or "—")],
            ["Cargo", func.cargo],
            ["CBO", ppp.cbo or "—"],
            ["Setor", func.setor or "—"],
        ]))
        story.append(Spacer(1, 0.3*cm))

        # SEÇÃO 2 — DADOS DA EMPRESA
        story.append(Paragraph("2. DADOS DA EMPRESA / EMPREGADORA", styles["Heading2"]))
        story.append(tabela([
            ["Campo", "Valor"],
            ["Razão Social", empresa.nome],
            ["CNPJ", getattr(empresa, "cnpj", "—") or "—"],
            ["CNAE Principal", getattr(empresa, "cnae", "—") or "—"],
            ["Responsável Técnico", ppp.responsavel_tecnico or "—"],
            ["Conselho / Registro", ppp.conselho_registro or "—"],
        ]))
        story.append(Spacer(1, 0.3*cm))

        # SEÇÃO 3 — AGENTES NOCIVOS
        story.append(Paragraph("3. EXPOSIÇÃO A AGENTES NOCIVOS (S-2240)", styles["Heading2"]))
        if ppp.agentes_nocivos:
            dados_ag = [["Código", "Agente", "Tipo", "Intensidade", "Limite", "EPI-CA"]]
            for ag in ppp.agentes_nocivos:
                dados_ag.append([
                    ag.get("codigo_tabela", "—"),
                    Paragraph(ag.get("descricao", "—"), cell),
                    ag.get("tipo", "—"),
                    ag.get("intensidade_concentracao", "—"),
                    ag.get("limite_tolerancia", "—"),
                    ag.get("epi_ca", "—"),
                ])
            t = Table(dados_ag, colWidths=[2*cm, 5*cm, 2*cm, 2.5*cm, 2.5*cm, 3*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2540")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTSIZE",   (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE3EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("Nenhum agente nocivo registrado.", styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))

        # SEÇÃO 4 — MONITORAÇÃO BIOLÓGICA
        story.append(Paragraph("4. MONITORAÇÃO BIOLÓGICA (Exames)", styles["Heading2"]))
        if ppp.monitoracao_biologica:
            dados_mb = [["Exame", "Data Coleta", "Resultado", "Unidade", "Ref.", "Alt."]]
            for mb in ppp.monitoracao_biologica:
                dados_mb.append([
                    Paragraph(mb.get("exame", "—"), cell),
                    mb.get("data_coleta", "—"),
                    mb.get("resultado", "—"),
                    mb.get("unidade", "—"),
                    mb.get("valor_referencia", "—"),
                    "Sim" if mb.get("alterado") else "Não",
                ])
            t = Table(dados_mb, colWidths=[4*cm, 2.5*cm, 2.5*cm, 2*cm, 3*cm, 2*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2540")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTSIZE",   (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE3EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("Nenhum exame laboratorial registrado.", styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))

        # SEÇÃO 5 — CONCLUSÃO
        story.append(Paragraph("5. CONCLUSÃO / OBSERVAÇÕES", styles["Heading2"]))
        story.append(Paragraph(ppp.resultado_conclusao or "—", styles["Normal"]))
        story.append(Spacer(1, 0.5*cm))

        # ASSINATURA
        story.append(Paragraph("_" * 50 + "    " + "_" * 50, styles["Normal"]))
        story.append(Paragraph(
            f"Responsável Técnico: {ppp.responsavel_tecnico or '—'}   "
            f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            f"Trabalhador: {func.nome}",
            subtitulo
        ))

        doc.build(story)
        buf.seek(0)
        resp = HttpResponse(buf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="PPP_{func.nome.replace(" ","_")}_{date.today()}.pdf"'
        return resp
    except ImportError:
        return JsonResponse({"erro": "ReportLab não instalado"}, status=500)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_ppp_kpis(request):
    """Painel de cobertura PPP da empresa."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FuncionarioSST, PPPFuncionario
        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        ppps = PPPFuncionario.objects.filter(empresa=empresa)
        finalizados = ppps.filter(status="finalizado").count()
        rascunhos = ppps.filter(status="rascunho").count()
        sem_ppp = total_func - ppps.values("funcionario").distinct().count()
        cobertura = round(finalizados / total_func * 100, 1) if total_func > 0 else 0
        return JsonResponse({
            "total_funcionarios": total_func,
            "ppps_finalizados": finalizados,
            "ppps_rascunho": rascunhos,
            "sem_ppp": max(sem_ppp, 0),
            "cobertura_pct": cobertura,
            "alerta": cobertura < 80,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)
