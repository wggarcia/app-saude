"""
PPP — Perfil Profissiográfico Previdenciário (SolusCRT SST)
Geração automatizada conforme IN INSS 128/2022 e eSocial S-2240.

Endpoints:
  GET  /api/sst/ppp/                            — lista PPPs da empresa
  POST /api/sst/ppp/                            — gerar PPP de um funcionário
  GET  /api/sst/ppp/<id>/                       — detalhe
  PATCH /api/sst/ppp/<id>/                      — editar campos
  POST /api/sst/ppp/<id>/finalizar/             — finalizar e assinar
  GET  /api/sst/ppp/<id>/pdf/                   — exportar PDF
  GET  /api/sst/ppp/kpis/                       — painel de cobertura
  GET  /api/sst/ppp/preview/<funcionario_id>/   — preview postos+agentes antes de gerar
"""
from datetime import date, timedelta
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
import json


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


def _ppp_dict(ppp):
    func = ppp.funcionario
    return {
        "id": ppp.id,
        "funcionario_id": ppp.funcionario_id,
        "funcionario_nome": func.nome,
        "funcionario_cpf": func.cpf,
        "funcionario_nit": ppp.nit_pis,
        "cargo": func.cargo,
        "setor": func.setor,
        "cbo": ppp.cbo,
        "data_admissao": str(func.data_admissao or ""),
        "data_desligamento": str(ppp.data_desligamento or ""),
        "data_geracao": str(ppp.data_geracao),
        "data_finalizacao": str(ppp.data_finalizacao or ""),
        "status": ppp.status,
        "responsavel_tecnico": ppp.responsavel_tecnico,
        "conselho_registro": ppp.conselho_registro,
        "agentes_nocivos": ppp.agentes_nocivos,
        "monitoracao_biologica": ppp.monitoracao_biologica,
        "historico_cargos": ppp.historico_cargos,
        "resultado_conclusao": ppp.resultado_conclusao,
        "tem_exposicao_nociva": any(
            not ag.get("epc_eficaz") and not ag.get("epi_eficaz")
            for ag in (ppp.agentes_nocivos or [])
        ),
        "criado_em": str(ppp.criado_em.date()),
    }


# ──────────────────────────────────────────────
# HELPERS DE PREENCHIMENTO AUTOMÁTICO
# ──────────────────────────────────────────────

def _postos_do_funcionario(funcionario):
    """Retorna os postos de trabalho vinculados ao funcionário (FuncionarioPostoTrabalho)."""
    try:
        from .models import FuncionarioPostoTrabalho
        return (
            FuncionarioPostoTrabalho.objects
            .filter(funcionario=funcionario)
            .select_related("posto")
            .order_by("data_inicio")
        )
    except Exception:
        return []


def _agentes_do_posto(posto):
    """Retorna agentes nocivos de um PostoTrabalho como lista de dicts."""
    try:
        from .models import AgenteNocivoPostoTrabalho
        return [
            {
                "codigo_tabela": a.cod_agente,
                "descricao": a.get_cod_agente_display() if hasattr(a, "get_cod_agente_display") else (a.dsc_agente or a.cod_agente),
                "descricao_complementar": a.dsc_agente,
                "tipo": a.tipo_agente,
                "tecnica_medicao": a.tec_medicao,
                "intensidade_concentracao": a.intensidade,
                "limite_tolerancia": a.limite_tolerancia,
                "epc_descricao": a.epc_descricao,
                "epc_eficaz": a.epc_eficaz,
                "epi_descricao": a.epi_descricao,
                "epi_ca": a.epi_ca,
                "epi_eficaz": a.epi_eficaz,
                "posto_nome": posto.nome,
                "posto_setor": posto.setor,
            }
            for a in AgenteNocivoPostoTrabalho.objects.filter(posto=posto)
        ]
    except Exception:
        return []


def _coletar_agentes_nocivos(funcionario, empresa):
    """
    Coleta agentes nocivos do S-2240 a partir dos postos de trabalho
    realmente vinculados ao funcionário (FuncionarioPostoTrabalho).
    """
    vinculos = _postos_do_funcionario(funcionario)
    agentes = []
    vistos = set()
    for vinculo in vinculos:
        for ag in _agentes_do_posto(vinculo.posto):
            chave = (ag["codigo_tabela"], vinculo.posto.id)
            if chave not in vistos:
                vistos.add(chave)
                agentes.append(ag)
    return agentes


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
    """
    Constrói histórico de cargos/postos a partir de FuncionarioPostoTrabalho,
    complementado com ASOs quando não há vínculos de posto.
    """
    try:
        vinculos = _postos_do_funcionario(funcionario)
        if vinculos:
            return [
                {
                    "cargo": v.posto.nome,
                    "setor": v.posto.setor,
                    "data_inicio": str(v.data_inicio),
                    "data_fim": str(v.data_fim) if v.data_fim else "",
                    "posto_id": v.posto.id,
                    "tem_agentes_nocivos": AgenteNocivoPostoTrabalho_count(v.posto),
                }
                for v in vinculos
            ]
    except Exception:
        pass

    # fallback: histórico via ASOs
    try:
        from .models import ASOOcupacional
        asos = ASOOcupacional.objects.filter(funcionario=funcionario).order_by("data_exame")
        cargos = []
        cargo_ant = None
        for aso in asos:
            if aso.cargo != cargo_ant:
                cargos.append({
                    "cargo": aso.cargo,
                    "setor": aso.setor or funcionario.setor,
                    "data_inicio": str(aso.data_exame),
                    "data_fim": "",
                    "posto_id": None,
                    "tem_agentes_nocivos": 0,
                })
                cargo_ant = aso.cargo
        return cargos
    except Exception:
        return []


def AgenteNocivoPostoTrabalho_count(posto):
    try:
        from .models import AgenteNocivoPostoTrabalho
        return AgenteNocivoPostoTrabalho.objects.filter(posto=posto).count()
    except Exception:
        return 0


def _gerar_conclusao(agentes_nocivos):
    """Gera texto de conclusão automático baseado nos agentes nocivos encontrados."""
    if not agentes_nocivos:
        return (
            "Não foram identificados agentes nocivos nos postos de trabalho ocupados "
            "pelo trabalhador. Não há caracterização de exposição a agentes prejudiciais "
            "à saúde para fins de aposentadoria especial."
        )
    nao_neutralizados = [
        ag for ag in agentes_nocivos
        if not ag.get("epc_eficaz") and not ag.get("epi_eficaz")
    ]
    tipos = list({ag["tipo"] for ag in nao_neutralizados})
    descricoes = list({ag["descricao"] for ag in nao_neutralizados[:3]})
    if nao_neutralizados:
        return (
            f"O trabalhador esteve exposto a agentes nocivos ({', '.join(descricoes)}) "
            f"de natureza {', '.join(tipos)}, sem neutralização eficaz por EPC/EPI, "
            f"nos termos do Anexo IV do Decreto 3.048/1999 e IN INSS 128/2022. "
            f"Caracterizada exposição habitual e permanente para fins de aposentadoria especial."
        )
    return (
        f"O trabalhador esteve exposto a agentes nocivos ({', '.join(d['descricao'] for d in agentes_nocivos[:2])}), "
        f"porém os equipamentos de proteção coletiva (EPC) e/ou individual (EPI) fornecidos "
        f"são eficazes na neutralização da nocividade. "
        f"Não caracterizada exposição para fins de aposentadoria especial."
    )


# ──────────────────────────────────────────────
# ENDPOINT: PREVIEW (antes de gerar o PPP)
# ──────────────────────────────────────────────

@csrf_exempt
def api_ppp_preview(request, funcionario_id):
    """
    Retorna os postos de trabalho e agentes nocivos do funcionário
    sem criar nenhum registro — usado para pré-visualizar o PPP.
    """
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FuncionarioSST
        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)

        vinculos = _postos_do_funcionario(func)
        postos_preview = []
        for v in vinculos:
            agentes = _agentes_do_posto(v.posto)
            postos_preview.append({
                "posto_id": v.posto.id,
                "posto_nome": v.posto.nome,
                "setor": v.posto.setor,
                "data_inicio": str(v.data_inicio),
                "data_fim": str(v.data_fim) if v.data_fim else "",
                "ativo": v.data_fim is None,
                "responsavel_tecnico": v.posto.responsavel_tecnico,
                "conselho_registro": v.posto.responsavel_registro,
                "data_laudo": str(v.posto.data_laudo or ""),
                "agentes_nocivos": agentes,
                "tem_exposicao_nao_neutralizada": any(
                    not a.get("epc_eficaz") and not a.get("epi_eficaz")
                    for a in agentes
                ),
            })

        todos_agentes = _coletar_agentes_nocivos(func, empresa)
        monitoracao = _coletar_monitoracao(func, empresa)

        # CBO automático por cargo
        CBO_MAP = {
            "gerente": "1231-05", "supervisor": "3517-10", "operador": "7170-35",
            "tecnico": "3115-10", "engenheiro": "2143-05", "assistente": "4110-05",
            "auxiliar": "4110-05", "analista": "2521-05", "soldador": "7243-35",
            "eletricista": "7156-10", "motorista": "7824-05", "enfermeiro": "2235-05",
            "medico": "2231-20", "seguranca": "7911-10",
        }
        cargo_lower = func.cargo.lower()
        cbo_auto = next((v for k, v in CBO_MAP.items() if k in cargo_lower), "")

        # Responsável técnico do posto ativo mais recente
        resp_auto = ""
        conselho_auto = ""
        if postos_preview:
            atual = next((p for p in reversed(postos_preview) if p["ativo"]), postos_preview[-1])
            resp_auto = atual.get("responsavel_tecnico", "")
            conselho_auto = atual.get("conselho_registro", "")

        return JsonResponse({
            "funcionario": {
                "id": func.id,
                "nome": func.nome,
                "cpf": func.cpf,
                "cargo": func.cargo,
                "setor": func.setor,
                "data_admissao": str(func.data_admissao or ""),
                "cbo_sugerido": cbo_auto,
            },
            "postos": postos_preview,
            "agentes_nocivos": todos_agentes,
            "monitoracao_biologica": monitoracao,
            "responsavel_tecnico_sugerido": resp_auto,
            "conselho_registro_sugerido": conselho_auto,
            "conclusao_sugerida": _gerar_conclusao(todos_agentes),
            "tem_exposicao_nociva": any(
                not a.get("epc_eficaz") and not a.get("epi_eficaz")
                for a in todos_agentes
            ),
            "sem_postos_vinculados": len(postos_preview) == 0,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)



# ──────────────────────────────────────────────
# VIEWS
# ──────────────────────────────────────────────

@csrf_exempt
def api_ppp_lista(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    if request.method == "POST":
        return api_ppp_criar(request)

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


@csrf_exempt
def api_ppp_criar(request):
    """
    Gera PPP automaticamente a partir dos postos de trabalho vinculados
    ao funcionário (FuncionarioPostoTrabalho → AgenteNocivoPostoTrabalho).
    """
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

        # Coleta dados automaticamente dos postos vinculados
        agentes = _coletar_agentes_nocivos(func, empresa)
        historico = _historico_cargos(func, empresa)
        monitoracao = _coletar_monitoracao(func, empresa)

        # CBO automático por cargo
        CBO_MAP = {
            "gerente": "1231-05", "supervisor": "3517-10", "operador": "7170-35",
            "tecnico": "3115-10", "engenheiro": "2143-05", "assistente": "4110-05",
            "auxiliar": "4110-05", "analista": "2521-05", "soldador": "7243-35",
            "eletricista": "7156-10", "motorista": "7824-05", "enfermeiro": "2235-05",
            "medico": "2231-20", "seguranca": "7911-10",
        }
        cargo_lower = func.cargo.lower()
        cbo_auto = next((v for k, v in CBO_MAP.items() if k in cargo_lower), "0000-00")

        # Responsável técnico: usa do payload ou tenta pegar do posto ativo
        resp = data.get("responsavel_tecnico", "")
        conselho = data.get("conselho_registro", "")
        if not resp:
            vinculos = list(_postos_do_funcionario(func))
            for v in reversed(vinculos):
                if v.posto.responsavel_tecnico:
                    resp = v.posto.responsavel_tecnico
                    conselho = v.posto.responsavel_registro
                    break

        # Conclusão: usa do payload ou gera automaticamente
        conclusao = data.get("resultado_conclusao", "") or _gerar_conclusao(agentes)

        ppp = PPPFuncionario.objects.create(
            empresa=empresa,
            funcionario=func,
            nit_pis=data.get("nit_pis", ""),
            cbo=data.get("cbo", cbo_auto),
            data_geracao=date.today(),
            data_desligamento=data.get("data_desligamento") or None,
            responsavel_tecnico=resp,
            conselho_registro=conselho,
            agentes_nocivos=agentes,
            monitoracao_biologica=monitoracao,
            historico_cargos=historico,
            resultado_conclusao=conclusao,
            status="rascunho",
        )
        return JsonResponse({"sucesso": True, "ppp": _ppp_dict(ppp)}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
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


@csrf_exempt
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


@csrf_exempt
def api_ppp_transmitir_esocial(request, ppp_id):
    """
    Transmite os eventos S-2240 referentes aos postos de trabalho do funcionário
    para o eSocial — que é o canal oficial pelo qual o INSS recebe os dados do PPP.

    Cria um eSocialEventoSST (S-2240) por posto de trabalho vinculado,
    gera o XML e chama transmitir_evento() para envio imediato.

    Retorna status de cada transmissão e protocolos recebidos.
    """
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        from .models import PPPFuncionario, eSocialEventoSST, ConfiguracaoSST
        from .views_esocial_sst import _gerar_xml_s2240
        from .esocial_transmissao import transmitir_evento
        from django.utils import timezone

        ppp = PPPFuncionario.objects.get(id=ppp_id, empresa=empresa)
        func = ppp.funcionario

        # Configuração eSocial da empresa (certificado, ambiente, CNPJ)
        try:
            cfg = empresa.configuracao_sst
        except ConfiguracaoSST.DoesNotExist:
            return JsonResponse({
                "erro": "Configuração eSocial não encontrada. Configure o certificado digital em Configurações SST."
            }, status=400)

        if not cfg.certificado_pfx_b64:
            return JsonResponse({
                "erro": "Certificado digital não configurado. Faça upload do certificado A1 (.pfx) em Configurações SST."
            }, status=400)

        # Pega os postos vinculados ao funcionário
        vinculos = list(_postos_do_funcionario(func))
        if not vinculos:
            return JsonResponse({
                "aviso": "Funcionário sem postos de trabalho vinculados. Vincule o funcionário a postos em Postos S-2240 antes de transmitir.",
                "transmitidos": 0,
            })

        periodo = date.today().strftime("%Y-%m")
        resultados = []

        for vinculo in vinculos:
            posto = vinculo.posto
            try:
                # Verifica se já existe evento S-2240 pendente para este posto neste período
                ev_existente = eSocialEventoSST.objects.filter(
                    empresa=empresa,
                    tipo_evento="S-2240",
                    referencia__contains=f"posto_{posto.id}",
                    status__in=["transmitido"],
                ).order_by("-criado_em").first()

                if ev_existente:
                    resultados.append({
                        "posto": posto.nome,
                        "status": "ja_transmitido",
                        "protocolo": ev_existente.protocolo,
                        "mensagem": f"S-2240 já transmitido anteriormente (protocolo: {ev_existente.protocolo})",
                    })
                    continue

                # Gera XML S-2240 para este posto
                xml = _gerar_xml_s2240(empresa, cfg, periodo=periodo, posto=posto)

                # Cria o evento na fila
                evento = eSocialEventoSST.objects.create(
                    empresa=empresa,
                    tipo_evento="S-2240",
                    status="pendente",
                    referencia=f"PPP#{ppp.id} — {func.nome} — posto_{posto.id} — {posto.nome}",
                    xml_gerado=xml,
                )

                # Transmite imediatamente
                ok, mensagem = transmitir_evento(evento)
                evento.refresh_from_db()

                resultados.append({
                    "posto": posto.nome,
                    "posto_id": posto.id,
                    "evento_id": evento.id,
                    "status": evento.status,
                    "protocolo": evento.protocolo,
                    "mensagem": mensagem,
                    "sucesso": ok,
                })

            except Exception as e_posto:
                resultados.append({
                    "posto": posto.nome,
                    "status": "erro",
                    "mensagem": str(e_posto),
                    "sucesso": False,
                })

        transmitidos = sum(1 for r in resultados if r.get("sucesso"))
        erros = sum(1 for r in resultados if not r.get("sucesso") and r.get("status") != "ja_transmitido")

        # Atualiza status do PPP se tudo foi transmitido com sucesso
        if transmitidos > 0 and erros == 0:
            if ppp.status == "rascunho":
                ppp.status = "finalizado"
                ppp.data_finalizacao = date.today()
                ppp.save(update_fields=["status", "data_finalizacao"])

        return JsonResponse({
            "sucesso": transmitidos > 0,
            "postos_processados": len(vinculos),
            "transmitidos": transmitidos,
            "ja_transmitidos": sum(1 for r in resultados if r.get("status") == "ja_transmitido"),
            "erros": erros,
            "ambiente": cfg.esocial_ambiente or "homologacao",
            "resultados": resultados,
        })

    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
def api_ppp_status_esocial(request, ppp_id):
    """Retorna o status de transmissão eSocial (S-2240) dos postos do funcionário."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import PPPFuncionario, eSocialEventoSST
        ppp = PPPFuncionario.objects.get(id=ppp_id, empresa=empresa)
        func = ppp.funcionario

        vinculos = list(_postos_do_funcionario(func))
        postos_ids = [v.posto.id for v in vinculos]

        eventos = eSocialEventoSST.objects.filter(
            empresa=empresa,
            tipo_evento="S-2240",
        ).filter(
            referencia__regex=r"posto_\d+"
        ).order_by("-criado_em")[:50]

        # Filtra apenas os relacionados aos postos deste funcionário
        relevantes = [
            ev for ev in eventos
            if any(f"posto_{pid}" in ev.referencia for pid in postos_ids)
        ]

        return JsonResponse({
            "postos_vinculados": len(vinculos),
            "eventos": [
                {
                    "id": ev.id,
                    "status": ev.status,
                    "protocolo": ev.protocolo,
                    "referencia": ev.referencia,
                    "data_envio": ev.data_envio.strftime("%d/%m/%Y %H:%M") if ev.data_envio else None,
                    "mensagem_erro": ev.mensagem_erro,
                }
                for ev in relevantes
            ],
            "todos_transmitidos": len(vinculos) > 0 and all(
                any(f"posto_{v.posto.id}" in ev.referencia and ev.status == "transmitido"
                    for ev in relevantes)
                for v in vinculos
            ),
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
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


@csrf_exempt
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


# ── Página HTML ───────────────────────────────────────────────────────────────

from .access_control import requer_permissao_modulo


@requer_permissao_modulo("sst.clinico")
def sst_ppp_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_ppp.html", {
        "empresa_nome": empresa.nome,
    })
