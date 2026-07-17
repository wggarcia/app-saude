"""
Assistente IA para SST — RAG com Claude tool use.

Cada tool consulta o ORM do Django isolado por empresa (RLS já ativo na
conexão). Claude decide quais tools chamar, executa, e formula a resposta
final em português.

Requer feature "sst.assistente_ia" (plano Enterprise ou superior).
Requer ANTHROPIC_API_KEY configurada no ambiente.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    AfastamentoSST,
    ASOOcupacional,
    CATOcupacional,
    EntregaEPI,
    EPIItem,
    FuncionarioSST,
    TreinamentoNR,
)

# ── Limite de segurança: evita loops infinitos de tool calls ──────────────────
_MAX_TOOL_ROUNDS = 5

# ── Definição das tools que Claude pode chamar ────────────────────────────────
TOOLS = [
    {
        "name": "resumo_conformidade",
        "description": (
            "Retorna um resumo geral de conformidade SST da empresa: "
            "total de funcionários ativos, ASOs vencidos, ASOs a vencer em 30 dias, "
            "treinamentos atrasados, afastamentos ativos e EPIs com CA vencido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "listar_asos_vencidos_ou_vencendo",
        "description": (
            "Lista funcionários com ASO vencido OU a vencer nos próximos N dias. "
            "Use para perguntas como 'quem precisa renovar ASO', "
            "'ASOs vencidos', 'quem está com exame atrasado'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Janela futura em dias (padrão 30). Use 0 para apenas vencidos.",
                    "default": 30,
                }
            },
            "required": [],
        },
    },
    {
        "name": "listar_afastamentos_ativos",
        "description": (
            "Lista todos os funcionários em afastamento ativo no momento, "
            "com motivo, CID e data prevista de retorno."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "listar_treinamentos_vencidos",
        "description": (
            "Lista treinamentos NR com data de validade expirada. "
            "Use para 'treinamentos atrasados', 'NRs vencidas', 'quem está sem treinamento'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Também inclui treinamentos a vencer nos próximos N dias (padrão 0 = apenas vencidos).",
                    "default": 0,
                }
            },
            "required": [],
        },
    },
    {
        "name": "listar_epis_ca_vencido",
        "description": (
            "Lista EPIs cujo Certificado de Aprovação (CA) está vencido ou a vencer. "
            "Use para 'EPI vencido', 'CA expirado', 'EPIs fora de validade'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Janela futura em dias (padrão 30).",
                    "default": 30,
                }
            },
            "required": [],
        },
    },
    {
        "name": "listar_cats_pendentes",
        "description": (
            "Lista CATs (Comunicações de Acidente de Trabalho) com eSocial pendente ou com erro. "
            "Use para 'acidentes não enviados ao eSocial', 'CATs pendentes'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "buscar_funcionario",
        "description": (
            "Busca um funcionário pelo nome (busca parcial) e retorna seus dados SST: "
            "cargo, setor, ASO mais recente, afastamentos ativos e treinamentos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {
                    "type": "string",
                    "description": "Nome ou parte do nome do funcionário.",
                }
            },
            "required": ["nome"],
        },
    },
    {
        "name": "listar_funcionarios_inaptos",
        "description": (
            "Lista funcionários com resultado de ASO 'inapto' ou 'apto com restrição'. "
            "Use para 'quem está inapto', 'funcionários com restrição médica'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "estatisticas_acidentes",
        "description": (
            "Retorna estatísticas agregadas de acidentes de trabalho (CAT) prontas para gráfico: "
            "total de acidentes, dias de afastamento somados, e contagens por setor, por mês, "
            "por gravidade, por parte do corpo atingida e por agente causador (esta última é a "
            "base de um gráfico de Pareto — mostra as causas mais frequentes). "
            "Use antes de gerar um gráfico sobre acidentes, causas, setores de risco ou tendência."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "meses": {
                    "type": "integer",
                    "description": "Janela de tempo em meses para trás (padrão 12).",
                    "default": 12,
                }
            },
            "required": [],
        },
    },
    {
        "name": "gerar_grafico",
        "description": (
            "Anexa um gráfico visual à resposta, usando dados que você já obteve de outras tools "
            "(ex: estatisticas_acidentes, resumo_conformidade, listar_treinamentos_vencidos). "
            "Use sempre que o usuário pedir 'gráfico', 'visual', 'painel', 'dashboard', "
            "'evolução', 'proporção', 'comparativo', 'pareto' ou um relatório gráfico. "
            "Não busca dados novos — apenas formata números que você já tem em um gráfico. "
            "Continue respondendo em texto normalmente além de chamar esta tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título curto do gráfico."},
                "tipo": {
                    "type": "string",
                    "enum": ["barras", "pizza", "linha", "pareto"],
                    "description": (
                        "barras: comparar categorias (ex: acidentes por setor). "
                        "pizza: proporção de um total (ex: ASOs em dia vs atrasados). "
                        "linha: evolução ao longo do tempo (ex: acidentes por mês). "
                        "pareto: causas ordenadas da mais para a menos frequente, com % acumulado."
                    ),
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Rótulos das categorias, na ordem dos valores.",
                },
                "valores": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Valores numéricos, na mesma ordem dos labels.",
                },
                "rotulo_serie": {
                    "type": "string",
                    "description": "Nome da série de dados (ex: 'Quantidade', 'Dias de afastamento'). Padrão: 'Quantidade'.",
                },
            },
            "required": ["titulo", "tipo", "labels", "valores"],
        },
    },
    {
        "name": "abrir_relatorio_pdf",
        "description": (
            "Anexa um link para abrir/baixar um relatório em PDF já existente no sistema. "
            "Use quando o usuário pedir para 'imprimir', 'baixar', 'gerar PDF', 'exportar' ou "
            "'preparar para auditoria/fiscalização' de uma dessas áreas específicas. "
            "Não gera o PDF você mesmo — apenas aponta para o relatório certo, que o usuário abre com um clique."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": [
                        "conformidade", "consolidado_auditoria", "asos", "cats",
                        "epi_inspecoes", "instrumentos_calibracao", "homem_hora_treinamentos", "afastamentos",
                    ],
                    "description": (
                        "conformidade: índice de conformidade por funcionário. "
                        "consolidado_auditoria: dossiê completo para fiscalização (conformidade+ASOs+afastamentos+CATs+treinamentos+EPI+documentos legais). "
                        "asos: ficha de exames ocupacionais. cats: comunicações de acidente. "
                        "epi_inspecoes: inspeções periódicas de EPI. instrumentos_calibracao: calibração de instrumentos de medição. "
                        "homem_hora_treinamentos: relatório de homem-hora de treinamentos. afastamentos: relatório de afastamentos."
                    ),
                },
            },
            "required": ["tipo"],
        },
    },
]

_RELATORIOS_PDF = {
    "conformidade": {"url": "/api/sst/conformidade/pdf/", "titulo": "Conformidade SST"},
    "consolidado_auditoria": {"url": "/api/sst/relatorio/consolidado/pdf/", "titulo": "Dossiê Consolidado de Auditoria"},
    "asos": {"url": "/sst/asos/", "titulo": "ASOs (abra a ficha do funcionário desejado)"},
    "cats": {"url": "/sst/cats/", "titulo": "CATs (abra o registro do acidente desejado)"},
    "epi_inspecoes": {"url": "/api/sst/epis/inspecoes/pdf", "titulo": "Inspeções Periódicas de EPI"},
    "instrumentos_calibracao": {"url": "/api/sst/instrumentos/pdf", "titulo": "Calibração de Instrumentos"},
    "homem_hora_treinamentos": {"url": "/api/sst/treinamentos/homem-hora/pdf", "titulo": "Homem-Hora de Treinamentos"},
    "afastamentos": {"url": "/api/sst/afastamentos/pdf", "titulo": "Afastamentos"},
}


# ── Execução das tools ────────────────────────────────────────────────────────

def _executar_tool(nome: str, inputs: dict, empresa) -> dict:
    hoje = date.today()

    if nome == "resumo_conformidade":
        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        asos_vencidos = ASOOcupacional.objects.filter(
            empresa=empresa, data_validade__lt=hoje
        ).values("funcionario__nome").distinct().count()
        asos_vencendo = ASOOcupacional.objects.filter(
            empresa=empresa,
            data_validade__gte=hoje,
            data_validade__lte=hoje + timedelta(days=30),
        ).values("funcionario__nome").distinct().count()
        treinamentos_vencidos = TreinamentoNR.objects.filter(
            empresa=empresa, data_validade__lt=hoje
        ).count()
        afastamentos_ativos = AfastamentoSST.objects.filter(
            empresa=empresa, status=AfastamentoSST.STATUS_ATIVO
        ).count()
        epis_ca_vencido = EPIItem.objects.filter(
            empresa=empresa, ativo=True, validade_ca__lt=hoje
        ).count()
        return {
            "funcionarios_ativos": total_func,
            "asos_vencidos": asos_vencidos,
            "asos_vencendo_30d": asos_vencendo,
            "treinamentos_nr_vencidos": treinamentos_vencidos,
            "afastamentos_ativos": afastamentos_ativos,
            "epis_ca_vencido": epis_ca_vencido,
        }

    if nome == "listar_asos_vencidos_ou_vencendo":
        dias = int(inputs.get("dias", 30))
        limite = hoje + timedelta(days=dias)
        asos = ASOOcupacional.objects.filter(
            empresa=empresa,
            data_validade__lte=limite,
        ).select_related("funcionario").order_by("data_validade")[:50]
        return {
            "total": asos.count(),
            "asos": [
                {
                    "funcionario": a.funcionario.nome,
                    "cargo": a.funcionario.cargo,
                    "tipo": a.get_tipo_display(),
                    "vencimento": a.data_validade.isoformat() if a.data_validade else None,
                    "vencido": a.data_validade < hoje if a.data_validade else False,
                }
                for a in asos
            ],
        }

    if nome == "listar_afastamentos_ativos":
        afastamentos = AfastamentoSST.objects.filter(
            empresa=empresa, status=AfastamentoSST.STATUS_ATIVO
        ).select_related("funcionario").order_by("data_inicio")[:50]
        return {
            "total": afastamentos.count(),
            "afastamentos": [
                {
                    "funcionario": a.funcionario.nome,
                    "cargo": a.funcionario.cargo,
                    "motivo": a.get_motivo_display(),
                    "cid": a.cid or "não informado",
                    "inicio": a.data_inicio.isoformat(),
                    "retorno_previsto": a.data_prevista_retorno.isoformat() if a.data_prevista_retorno else None,
                }
                for a in afastamentos
            ],
        }

    if nome == "listar_treinamentos_vencidos":
        dias = int(inputs.get("dias", 0))
        limite = hoje + timedelta(days=dias)
        treinamentos = TreinamentoNR.objects.filter(
            empresa=empresa, data_validade__lte=limite
        ).select_related("funcionario").order_by("data_validade")[:50]
        return {
            "total": treinamentos.count(),
            "treinamentos": [
                {
                    "funcionario": t.funcionario.nome,
                    "nr": t.nr,
                    "descricao": t.get_nr_display(),
                    "vencimento": t.data_validade.isoformat() if t.data_validade else None,
                    "vencido": t.data_validade < hoje if t.data_validade else False,
                }
                for t in treinamentos
            ],
        }

    if nome == "listar_epis_ca_vencido":
        dias = int(inputs.get("dias", 30))
        limite = hoje + timedelta(days=dias)
        epis = EPIItem.objects.filter(
            empresa=empresa, ativo=True, validade_ca__lte=limite
        ).order_by("validade_ca")[:50]
        return {
            "total": epis.count(),
            "epis": [
                {
                    "nome": e.nome,
                    "tipo": e.get_tipo_display(),
                    "ca_numero": e.ca_numero or "não informado",
                    "vencimento_ca": e.validade_ca.isoformat() if e.validade_ca else None,
                    "vencido": e.validade_ca < hoje if e.validade_ca else False,
                }
                for e in epis
            ],
        }

    if nome == "listar_cats_pendentes":
        cats = CATOcupacional.objects.filter(
            empresa=empresa,
            status_esocial__in=["nao_enviado", "pendente", "erro"],
        ).select_related("funcionario").order_by("-data_acidente")[:50]
        return {
            "total": cats.count(),
            "cats": [
                {
                    "funcionario": c.funcionario.nome,
                    "tipo": c.get_tipo_display(),
                    "gravidade": c.get_gravidade_display() if hasattr(c, "get_gravidade_display") else c.gravidade,
                    "data_acidente": c.data_acidente.isoformat(),
                    "status_esocial": c.get_status_esocial_display(),
                }
                for c in cats
            ],
        }

    if nome == "buscar_funcionario":
        nome_busca = inputs.get("nome", "").strip()
        funcs = list(FuncionarioSST.objects.filter(
            empresa=empresa, nome__icontains=nome_busca, ativo=True
        )[:5])
        func_ids = [f.id for f in funcs]
        # Carrega relacionamentos em bulk (evita N+1: 1 query por relacionamento, não por funcionário)
        from django.db.models import Prefetch
        asos_qs = ASOOcupacional.objects.filter(funcionario_id__in=func_ids).order_by("-data_emissao")
        afastamentos_qs = AfastamentoSST.objects.filter(funcionario_id__in=func_ids, status=AfastamentoSST.STATUS_ATIVO)
        from collections import defaultdict
        asos_map = defaultdict(list)
        for a in asos_qs:
            asos_map[a.funcionario_id].append(a)
        afastamentos_map = {a.funcionario_id: a for a in afastamentos_qs}
        treinos_vencidos = dict(
            TreinamentoNR.objects.filter(funcionario_id__in=func_ids, data_validade__lt=hoje)
            .values("funcionario_id").annotate(n=Count("id"))
            .values_list("funcionario_id", "n")
        )
        resultado = []
        for f in funcs:
            aso_recente = asos_map[f.id][0] if asos_map[f.id] else None
            afastamento_ativo = afastamentos_map.get(f.id)
            treinamentos_vencidos_count = treinos_vencidos.get(f.id, 0)
            resultado.append({
                "nome": f.nome,
                "cargo": f.cargo,
                "setor": f.setor or "não informado",
                "classe_risco": f.get_classe_risco_display(),
                "aso_recente": {
                    "tipo": aso_recente.get_tipo_display(),
                    "resultado": aso_recente.get_resultado_display(),
                    "vencimento": aso_recente.data_validade.isoformat() if aso_recente.data_validade else None,
                    "vencido": aso_recente.data_validade < hoje if aso_recente.data_validade else False,
                } if aso_recente else None,
                "em_afastamento": bool(afastamento_ativo),
                "motivo_afastamento": afastamento_ativo.get_motivo_display() if afastamento_ativo else None,
                "treinamentos_vencidos": treinamentos_vencidos_count,
            })
        return {"encontrados": len(resultado), "funcionarios": resultado}

    if nome == "listar_funcionarios_inaptos":
        asos = ASOOcupacional.objects.filter(
            empresa=empresa,
            resultado__in=["inapto", "apto_restricao"],
        ).select_related("funcionario").order_by("-data_emissao")[:50]
        vistos = set()
        resultado = []
        for a in asos:
            if a.funcionario_id not in vistos:
                vistos.add(a.funcionario_id)
                resultado.append({
                    "funcionario": a.funcionario.nome,
                    "cargo": a.funcionario.cargo,
                    "resultado": a.get_resultado_display(),
                    "restricoes": a.restricoes or "não especificadas",
                    "data_aso": a.data_emissao.isoformat(),
                })
        return {"total": len(resultado), "funcionarios": resultado}

    if nome == "estatisticas_acidentes":
        meses = int(inputs.get("meses", 12) or 12)
        limite = hoje - timedelta(days=meses * 30)
        qs = CATOcupacional.objects.filter(empresa=empresa, data_acidente__gte=limite)
        total = qs.count()
        dias_afastamento_total = qs.aggregate(total=Sum("dias_afastamento"))["total"] or 0

        por_setor_raw = dict(qs.values("funcionario__setor").annotate(n=Count("id")).values_list("funcionario__setor", "n"))
        por_setor = {(k or "Não informado"): v for k, v in por_setor_raw.items()}

        gravidade_labels = dict(CATOcupacional.GRAVIDADE)
        por_gravidade_raw = dict(qs.values("gravidade").annotate(n=Count("id")).values_list("gravidade", "n"))
        por_gravidade = {gravidade_labels.get(k, k): v for k, v in por_gravidade_raw.items()}

        parte_labels = dict(CATOcupacional.COD_PARTE_CORPO)
        por_parte_raw = dict(qs.values("cod_parte_corpo").annotate(n=Count("id")).values_list("cod_parte_corpo", "n"))
        por_parte_corpo = {parte_labels.get(k, k): v for k, v in por_parte_raw.items()}

        agente_labels = dict(CATOcupacional.COD_AGENTE)
        por_agente_raw = dict(qs.values("cod_agente_causador").annotate(n=Count("id")).values_list("cod_agente_causador", "n"))
        por_agente_causador = {agente_labels.get(k, k): v for k, v in por_agente_raw.items()}

        por_mes = {}
        for d in qs.values_list("data_acidente", flat=True):
            chave = d.strftime("%m/%Y")
            por_mes[chave] = por_mes.get(chave, 0) + 1

        return {
            "periodo": f"últimos {meses} meses",
            "total_acidentes": total,
            "dias_afastamento_total": dias_afastamento_total,
            "por_setor": por_setor,
            "por_mes": por_mes,
            "por_gravidade": por_gravidade,
            "por_parte_corpo": por_parte_corpo,
            "por_agente_causador": por_agente_causador,
        }

    if nome == "gerar_grafico":
        labels = inputs.get("labels") or []
        valores = inputs.get("valores") or []
        if len(labels) != len(valores):
            return {"erro": "labels e valores devem ter o mesmo tamanho."}
        if not labels:
            return {"erro": "Informe ao menos uma categoria."}
        return {"ok": True, "mensagem": "Gráfico anexado à resposta final."}

    if nome == "abrir_relatorio_pdf":
        tipo = inputs.get("tipo")
        relatorio = _RELATORIOS_PDF.get(tipo)
        if not relatorio:
            return {"erro": f"Tipo de relatório desconhecido: {tipo}"}
        if tipo == "consolidado_auditoria":
            from .access_control import empresa_tem_feature
            if not empresa_tem_feature(empresa, "sst.relatorio_consolidado"):
                return {"erro": "O Dossiê Consolidado de Auditoria está disponível a partir de um plano superior."}
        return {"ok": True, "mensagem": f"Relatório '{relatorio['titulo']}' anexado à resposta final."}

    return {"erro": f"Tool desconhecida: {nome}"}


# ── View principal ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def assistente_sst(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    from .access_control import empresa_tem_feature
    if not empresa_tem_feature(empresa, "sst.assistente_ia"):
        return JsonResponse(
            {"erro": "O Assistente IA está disponível a partir do plano Enterprise SST."},
            status=403,
        )

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return JsonResponse(
            {"erro": "Assistente IA não configurado. Contate o suporte SolusCRT."},
            status=503,
        )

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    pergunta = (body.get("pergunta") or "").strip()
    if not pergunta:
        return JsonResponse({"erro": "Envie o campo 'pergunta'."}, status=400)
    if len(pergunta) > 500:
        return JsonResponse({"erro": "Pergunta muito longa (máx 500 caracteres)."}, status=400)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        hoje_str = date.today().strftime("%d/%m/%Y")
        system = (
            f"Você é o Assistente SST da plataforma SolusCRT. "
            f"Hoje é {hoje_str}. "
            f"Responda sempre em português, de forma objetiva e profissional. "
            f"Use os dados retornados pelas ferramentas — nunca invente informações. "
            f"Quando listar funcionários, use bullet points. "
            f"Se não houver ocorrências, diga isso claramente. "
            f"Quando o usuário pedir um gráfico, visão visual, painel, evolução, proporção, "
            f"comparativo ou pareto, busque os dados com as tools apropriadas (ex: "
            f"estatisticas_acidentes) e depois chame a tool gerar_grafico com os números — "
            f"além de continuar respondendo em texto normalmente. "
            f"Quando o usuário pedir para imprimir, baixar, exportar ou preparar um relatório "
            f"em PDF de uma área específica (conformidade, auditoria/fiscalização, ASOs, CATs, "
            f"EPI, instrumentos, treinamentos, afastamentos), chame a tool abrir_relatorio_pdf."
        )

        messages = [{"role": "user", "content": pergunta}]
        grafico_anexado = None
        relatorio_anexado = None

        for _ in range(_MAX_TOOL_ROUNDS):
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                texto = next(
                    (b.text for b in response.content if hasattr(b, "text")),
                    "Não foi possível gerar uma resposta.",
                )
                return JsonResponse({"resposta": texto, "grafico": grafico_anexado, "relatorio": relatorio_anexado})

            if response.stop_reason != "tool_use":
                break

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_uses:
                resultado = _executar_tool(tu.name, tu.input, empresa)
                if tu.name == "gerar_grafico" and not resultado.get("erro"):
                    grafico_anexado = tu.input
                if tu.name == "abrir_relatorio_pdf" and not resultado.get("erro"):
                    relatorio_anexado = _RELATORIOS_PDF.get(tu.input.get("tipo"))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                })
            messages.append({"role": "user", "content": tool_results})

        return JsonResponse({
            "resposta": "Não consegui processar a pergunta. Tente novamente.",
            "grafico": grafico_anexado,
            "relatorio": relatorio_anexado,
        })

    except Exception as exc:
        return JsonResponse(
            {"erro": "Erro ao processar. Tente novamente em instantes."},
            status=500,
        )


def _validar_grafico_payload(body):
    grafico = body.get("grafico") or {}
    if not grafico.get("labels") or not grafico.get("valores"):
        return None, JsonResponse({"erro": "Gráfico inválido."}, status=400)
    return grafico, None


@csrf_exempt
@require_http_methods(["POST"])
def api_assistente_grafico_pdf(request):
    """POST — gera o PDF de um gráfico anexado pelo Assistente IA SST (visualização ou download)."""
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    grafico, erro = _validar_grafico_payload(body)
    if erro:
        return erro
    resposta = body.get("resposta") or ""

    from .pdf_sst import gerar_pdf_grafico_assistente
    pdf_bytes = gerar_pdf_grafico_assistente(grafico, resposta, empresa.nome)

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    resp["Content-Disposition"] = f'{disposition}; filename="relatorio-assistente-sst.pdf"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def api_assistente_grafico_pdf_email(request):
    """POST — envia o PDF de um gráfico do Assistente IA SST por e-mail."""
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    destinatario = (body.get("email") or "").strip()
    if not destinatario or "@" not in destinatario:
        return JsonResponse({"erro": "Informe um e-mail válido."}, status=400)

    grafico, erro = _validar_grafico_payload(body)
    if erro:
        return erro
    resposta = body.get("resposta") or ""

    from .pdf_sst import gerar_pdf_grafico_assistente
    from django.core.mail import EmailMessage

    pdf_bytes = gerar_pdf_grafico_assistente(grafico, resposta, empresa.nome)

    try:
        msg = EmailMessage(
            subject=f"[SolusCRT] {grafico.get('titulo') or 'Relatório do Assistente IA SST'}",
            body=(
                f"Segue em anexo o relatório gerado pelo Assistente IA SST — {empresa.nome}.\n\n"
                "-- \nSolusCRT · Sistema de Gestão SST"
            ),
            from_email=None,
            to=[destinatario],
        )
        msg.attach("relatorio-assistente-sst.pdf", pdf_bytes, "application/pdf")
        enviados = msg.send(fail_silently=False)
        if enviados < 1:
            return JsonResponse({"erro": "Servidor de e-mail não confirmou o envio."}, status=502)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Erro ao enviar gráfico do Assistente IA SST por e-mail: %s", exc)
        return JsonResponse({"erro": f"Falha ao enviar e-mail: {exc}"}, status=502)

    return JsonResponse({"ok": True, "mensagem": f"Relatório enviado para {destinatario}."})
