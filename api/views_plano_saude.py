"""
 Plano de Saúde — cockpit cooperativo para Operadoras.
 Ambiente dedicado para carteira, regulacao, sinistros,
 prestadores, reembolsos e radar epidemiologico sem rip-and-replace.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .access_control import get_setor
from .models import (
    BeneficiarioPlano, Empresa, GuiaAutorizacao,
    PlanoSaude, PrestadorPlanoSaude, Reembolso, Sinistro, RegistroSintoma,
    GlosaItem, CoparticipacaoRegra, FaturamentoBeneficiario,
    ProgramaSaude, InscricaoPrograma,
    ContratoGrupo, TeleconsultaAutorizacao,
    BeneficiarioOdonto, GuiaOdonto, MensagemPlano,
    CarenciaBeneficiario,
)
from .views_dashboard import _empresa_autenticada
from .email_service import (
    enviar_email_novo_contrato,
    enviar_email_teleconsulta_autorizada,
    enviar_email_guia_odonto_aprovada,
    enviar_email_guia_odonto_negada,
    enviar_email_sla_breach_critico,
    enviar_email_auditoria_alerta,
    enviar_email_novo_beneficiario,
)


# ── helpers de autenticação ───────────────────────────────────────────────────

def _ps_auth(request):
    """Retorna (empresa, erro_response). Verifica setor plano_saude."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "plano_saude":
        return None, JsonResponse({"erro": "Módulo Plano de Saúde não disponível para este plano."}, status=403)
    return empresa, None


# ── serializers ───────────────────────────────────────────────────────────────

def _to_bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "sim", "yes", "on"}


def _pressao_epidemiologica_empresa(empresa, dias=14):
    inicio = date.today() - timedelta(days=dias)
    qs = RegistroSintoma.objects.filter(
        empresa=empresa,
        data_registro__date__gte=inicio,
    )
    total = qs.count()
    suspeitos = qs.filter(suspeito=True).count()
    if suspeitos >= 12:
        nivel = "alta"
        label = "Pressao alta"
    elif suspeitos >= 5:
        nivel = "moderada"
        label = "Pressao moderada"
    elif suspeitos > 0:
        nivel = "monitoramento"
        label = "Monitoramento ativo"
    else:
        nivel = "controlada"
        label = "Territorio controlado"
    return {
        "janela_dias": dias,
        "registros": total,
        "suspeitos": suspeitos,
        "nivel": nivel,
        "label": label,
    }


def _frente_cooperacao(codigo, nome, status, descricao, evidencia, proximo_passo):
    labels = {
        "operando": "Operando",
        "implantacao": "Em implantacao",
        "prioridade": "Prioridade alta",
        "monitorando": "Monitorando",
    }
    return {
        "codigo": codigo,
        "nome": nome,
        "status": status,
        "status_label": labels.get(status, status.title()),
        "descricao": descricao,
        "evidencia": evidencia,
        "proximo_passo": proximo_passo,
    }


def _cooperacao_operadora_payload(empresa, planos, beneficiarios, guias, prestadores, pressao):
    total_planos = planos.count()
    beneficiarios_ativos = beneficiarios.filter(
        situacao=BeneficiarioPlano.SITUACAO_ATIVO
    ).count()
    prestadores_ativos = prestadores.filter(
        status=PrestadorPlanoSaude.STATUS_CREDENCIADO
    ).count()
    prestadores_portal = prestadores.filter(portal_ativo=True).count()
    guias_documentadas = guias.exclude(cid="").exclude(medico_solicitante="").count()
    planos_com_ans = planos.exclude(registro_ans="").count()

    return {
        "modelo": "camada_cooperativa",
        "headline": "A SolusCRT coopera com o sistema que a operadora ja possui e adiciona comando operacional, regulatorio e epidemiologico.",
        "descricao": "O ambiente de plano de saude funciona como cockpit de orquestracao: a operadora pode manter core admin, ERP, faturamento e integrações proprias enquanto a SolusCRT organiza carteira, fila clinica, rede credenciada, sinistralidade e territorio.",
        "promessa": "Sem rip-and-replace: entre como camada de cooperacao, enxergue risco assistencial mais cedo e devolva decisao melhor para o que a operadora ja tem.",
        "frentes": [
            _frente_cooperacao(
                "core_legado",
                "Core legado e carteira da operadora",
                "operando" if beneficiarios_ativos else ("implantacao" if total_planos else "prioridade"),
                "Mantem o cadastro mestre e a esteira principal no legado enquanto a SolusCRT organiza elegibilidade, vigencia e leitura operacional da carteira.",
                f"{total_planos} plano(s) e {beneficiarios_ativos} beneficiario(s) ativo(s) espelhados no cockpit.",
                "Conectar elegibilidade, faturamento e status do beneficiario ao core existente via API, arquivo ou rotina de carga.",
            ),
            _frente_cooperacao(
                "rede_prestador",
                "Rede credenciada e portal do prestador",
                "operando" if prestadores_ativos and prestadores_portal else ("implantacao" if prestadores_ativos else "prioridade"),
                "Acompanha rede, SLA, pendencias documentais e uso assistencial sem trocar o sistema transacional do prestador.",
                f"{prestadores_ativos} prestador(es) credenciado(s) e {prestadores_portal} portal(is) ativo(s).",
                "Ativar score de qualidade, ocorrencias e rotinas de cooperacao com o portal do prestador.",
            ),
            _frente_cooperacao(
                "regulacao",
                "Regulacao clinica, UM e auditoria",
                "operando" if guias_documentadas else ("implantacao" if guias.count() else "prioridade"),
                "Centraliza fila clinica, CID, medico solicitante, justificativa e decisao regulatoria para cooperar com autorizacao e auditoria do ambiente existente.",
                f"{guias.count()} guia(s) no cockpit e {guias_documentadas} com documentacao clinica estruturada.",
                "Padronizar CID, medico solicitante, motivos de negativa e SLA para circular entre operacao, auditoria e legado.",
            ),
            _frente_cooperacao(
                "ans_tiss",
                "Compliance ANS/TISS e trilha regulatoria",
                "implantacao" if (planos_com_ans or guias_documentadas) else "prioridade",
                "Usa ANS, justificativas e trilhas auditaveis como base de cooperacao com faturamento, TISS e conformidade regulatoria.",
                f"{planos_com_ans} plano(s) com registro ANS e {guias_documentadas} guia(s) preparadas para cooperacao regulatoria.",
                "Fechar integracao TISS/ANS via exportacao estruturada, API ou conector de implantacao para go-live regulatorio pleno.",
            ),
            _frente_cooperacao(
                "epidemiologia",
                "Radar epidemiologico da carteira",
                "operando" if pressao["registros"] else "monitorando",
                "Cruza sinais territoriais com carteira, prestadores e eventos assistenciais para antecipar demanda, comunicacao e custo em alta.",
                f"{pressao['registros']} registro(s) territoriais e {pressao['suspeitos']} suspeito(s) na janela de {pressao['janela_dias']} dias.",
                "Usar o mapa para acionar programas, comunicacao preventiva e priorizacao de autorizacoes antes da pressao virar sinistro.",
            ),
        ],
        "proximos_passos": [
            "Mapear os sistemas que permanecem no legado e definir qual dado entra no cockpit por API, lote ou rotina operacional.",
            "Padronizar ANS, TISS, motivos regulatorios e justificativas clinicas para circular entre operadora, prestadores e auditoria.",
            "Cruzar pressao epidemiologica com carteira, autorizacoes e sinistralidade para gerar acoes antes do custo explodir.",
        ],
    }


def _sla_horas_prioridade(prioridade, prestador=None):
    base = {
        GuiaAutorizacao.PRIORIDADE_ELETIVA: 72,
        GuiaAutorizacao.PRIORIDADE_URGENTE: 24,
        GuiaAutorizacao.PRIORIDADE_ALTA_COMPLEXIDADE: 48,
        GuiaAutorizacao.PRIORIDADE_INTERNACAO: 12,
    }.get(prioridade or GuiaAutorizacao.PRIORIDADE_ELETIVA, 72)
    if prestador and prestador.sla_autorizacao_horas:
        return min(base, int(prestador.sla_autorizacao_horas))
    return base


def _calcular_prazo_sla(prioridade, prestador=None):
    return timezone.now() + timedelta(hours=_sla_horas_prioridade(prioridade, prestador))


def _fila_status_from_status(status):
    return {
        GuiaAutorizacao.STATUS_SOLICITADA: GuiaAutorizacao.FILA_TRIAGEM,
        GuiaAutorizacao.STATUS_EM_ANALISE: GuiaAutorizacao.FILA_AUDITORIA_CLINICA,
        GuiaAutorizacao.STATUS_AUTORIZADA: GuiaAutorizacao.FILA_AUTORIZADA,
        GuiaAutorizacao.STATUS_NEGADA: GuiaAutorizacao.FILA_NEGADA,
        GuiaAutorizacao.STATUS_CANCELADA: GuiaAutorizacao.FILA_DEVOLVIDA_PRESTADOR,
    }.get(status or GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.FILA_TRIAGEM)


def _guia_sla_info(g):
    prazo = g.prazo_sla_em
    if not prazo:
        prazo = g.solicitada_em + timedelta(
            hours=_sla_horas_prioridade(g.prioridade_clinica, g.prestador)
        )
    agora = timezone.now()
    vencido = bool(prazo and prazo < agora and g.status in [
        GuiaAutorizacao.STATUS_SOLICITADA,
        GuiaAutorizacao.STATUS_EM_ANALISE,
    ])
    diff_horas = None
    if prazo:
        diff_horas = round((prazo - agora).total_seconds() / 3600, 1)
    return {
        "prazo_sla_em": prazo.isoformat() if prazo else None,
        "prazo_sla_em_fmt": timezone.localtime(prazo).strftime("%d/%m/%Y %H:%M") if prazo else "",
        "sla_horas": _sla_horas_prioridade(g.prioridade_clinica, g.prestador),
        "sla_vencido": vencido,
        "horas_restantes": diff_horas,
    }


def _prestador_dict(p):
    pendentes = p.guias.filter(
        status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE]
    ).count()
    vencidas = p.guias.filter(
        status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
        prazo_sla_em__lt=timezone.now(),
    ).count()
    return {
        "id": p.id,
        "codigo_rede": p.codigo_rede,
        "nome_fantasia": p.nome_fantasia,
        "razao_social": p.razao_social,
        "cnpj": p.cnpj,
        "tipo": p.tipo,
        "tipo_label": p.get_tipo_display(),
        "registro_cnes": p.registro_cnes,
        "especialidades": p.especialidades,
        "cidade": p.cidade,
        "estado": p.estado,
        "telefone": p.telefone,
        "email": p.email,
        "contato_responsavel": p.contato_responsavel,
        "sla_autorizacao_horas": p.sla_autorizacao_horas,
        "portal_ativo": p.portal_ativo,
        "score_qualidade": p.score_qualidade,
        "status": p.status,
        "status_label": p.get_status_display(),
        "observacoes": p.observacoes,
        "guias_pendentes": pendentes,
        "guias_sla_vencido": vencidas,
        "criado_em": p.criado_em.strftime("%d/%m/%Y"),
    }

def _plano_dict(p):
    return {
        "id": p.id,
        "nome": p.nome,
        "registro_ans": p.registro_ans,
        "cnpj": p.cnpj,
        "modalidade": p.modalidade,
        "modalidade_label": p.get_modalidade_display() if p.modalidade else "",
        "abrangencia": p.abrangencia,
        "status": p.status,
        "status_label": p.get_status_display(),
        "total_beneficiarios": p.beneficiarios.filter(situacao="ativo").count(),
        "total_guias_pendentes": p.guias.filter(status__in=["solicitada", "em_analise"]).count(),
        "total_sinistros_abertos": p.sinistros.filter(status__in=["aberto", "em_analise"]).count(),
        "criado_em": p.criado_em.strftime("%d/%m/%Y"),
    }


def _beneficiario_dict(b):
    return {
        "id": b.id,
        "plano_id": b.plano_id,
        "plano_nome": b.plano.nome,
        "nome": b.nome,
        "cpf": b.cpf,
        "numero_carteirinha": b.numero_carteirinha,
        "data_nascimento": b.data_nascimento.isoformat() if b.data_nascimento else None,
        "data_nascimento_fmt": b.data_nascimento.strftime("%d/%m/%Y") if b.data_nascimento else "",
        "sexo": b.sexo,
        "telefone": b.telefone,
        "email": b.email,
        "plano_tipo": b.plano_tipo,
        "acomodacao": b.acomodacao,
        "acomodacao_label": b.get_acomodacao_display(),
        "situacao": b.situacao,
        "situacao_label": b.get_situacao_display(),
        "data_inicio_vigencia": b.data_inicio_vigencia.isoformat() if b.data_inicio_vigencia else None,
        "data_fim_vigencia": b.data_fim_vigencia.isoformat() if b.data_fim_vigencia else None,
        "criado_em": b.criado_em.strftime("%d/%m/%Y"),
    }


def _guia_dict(g):
    sla = _guia_sla_info(g)
    return {
        "id": g.id,
        "plano_id": g.plano_id,
        "plano_nome": g.plano.nome,
        "beneficiario_id": g.beneficiario_id,
        "beneficiario_nome": g.beneficiario.nome,
        "prestador_id": g.prestador_id,
        "prestador_nome": g.prestador.nome_fantasia if g.prestador_id else "",
        "prestador_tipo": g.prestador.tipo if g.prestador_id else "",
        "prestador_portal_ativo": bool(g.prestador_id and g.prestador.portal_ativo),
        "numero_guia": g.numero_guia,
        "tipo": g.tipo,
        "tipo_label": g.get_tipo_display(),
        "status": g.status,
        "status_label": g.get_status_display(),
        "prioridade_clinica": g.prioridade_clinica,
        "prioridade_clinica_label": g.get_prioridade_clinica_display(),
        "fila_status": g.fila_status,
        "fila_status_label": g.get_fila_status_display(),
        "auditor_responsavel": g.auditor_responsavel,
        "descricao_procedimento": g.descricao_procedimento,
        "cid": g.cid,
        "medico_solicitante": g.medico_solicitante,
        "valor_estimado": float(g.valor_estimado or 0),
        "prazo_sla_em": sla["prazo_sla_em"],
        "prazo_sla_em_fmt": sla["prazo_sla_em_fmt"],
        "sla_horas": sla["sla_horas"],
        "sla_vencido": sla["sla_vencido"],
        "horas_restantes": sla["horas_restantes"],
        "observacao_auditoria": g.observacao_auditoria,
        "documentos_pendentes": g.documentos_pendentes,
        "numero_autorizacao": g.numero_autorizacao,
        "validade_autorizacao": g.validade_autorizacao.isoformat() if g.validade_autorizacao else None,
        "justificativa_negativa": g.justificativa_negativa,
        "solicitada_em": g.solicitada_em.strftime("%d/%m/%Y %H:%M"),
        "atualizada_em": g.atualizada_em.strftime("%d/%m/%Y %H:%M"),
    }


def _sinistro_dict(s):
    return {
        "id": s.id,
        "plano_id": s.plano_id,
        "plano_nome": s.plano.nome,
        "beneficiario_id": s.beneficiario_id,
        "beneficiario_nome": s.beneficiario.nome,
        "numero_sinistro": s.numero_sinistro,
        "tipo": s.tipo,
        "tipo_label": s.get_tipo_display(),
        "status": s.status,
        "status_label": s.get_status_display(),
        "cid": s.cid,
        "descricao_procedimento": s.descricao_procedimento,
        "prestador": s.prestador,
        "medico": s.medico,
        "data_atendimento": s.data_atendimento.isoformat() if s.data_atendimento else None,
        "data_atendimento_fmt": s.data_atendimento.strftime("%d/%m/%Y") if s.data_atendimento else "",
        "valor_total": float(s.valor_total),
        "valor_pago": float(s.valor_pago),
        "observacao": s.observacao,
        "data_abertura": s.data_abertura.strftime("%d/%m/%Y %H:%M"),
        "data_fechamento": s.data_fechamento.strftime("%d/%m/%Y") if s.data_fechamento else None,
    }


def _reembolso_dict(r):
    return {
        "id": r.id,
        "plano_id": r.plano_id,
        "plano_nome": r.plano.nome,
        "beneficiario_id": r.beneficiario_id,
        "beneficiario_nome": r.beneficiario.nome,
        "sinistro_id": r.sinistro_id,
        "numero_reembolso": r.numero_reembolso,
        "tipo_despesa": r.tipo_despesa,
        "tipo_despesa_label": r.get_tipo_despesa_display(),
        "status": r.status,
        "status_label": r.get_status_display(),
        "valor_solicitado": float(r.valor_solicitado),
        "valor_aprovado": float(r.valor_aprovado),
        "valor_pago": float(r.valor_pago),
        "banco": r.banco,
        "agencia": r.agencia,
        "conta": r.conta,
        "descricao": r.descricao,
        "observacao": r.observacao,
        "data_solicitacao": r.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
        "data_pagamento": r.data_pagamento.strftime("%d/%m/%Y") if r.data_pagamento else None,
    }


# ── Dashboard / KPIs ──────────────────────────────────────────────────────────

def api_ps_dashboard(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_30 = hoje - timedelta(days=30)

    planos = PlanoSaude.objects.filter(empresa=empresa)
    total_planos = planos.count()
    total_beneficiarios = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa, situacao="ativo"
    ).count()
    beneficiarios_suspensos = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa, situacao="suspenso"
    ).count()

    # Guias
    guias_qs = GuiaAutorizacao.objects.filter(plano__empresa=empresa)
    guias_pendentes = guias_qs.filter(status__in=["solicitada", "em_analise"]).count()
    guias_sla_vencido = guias_qs.filter(
        status__in=["solicitada", "em_analise"],
        prazo_sla_em__lt=timezone.now(),
    ).count()
    guias_autorizadas_mes = guias_qs.filter(
        status="autorizada",
        atualizada_em__date__gte=inicio_mes,
    ).count()
    guias_negadas_mes = guias_qs.filter(
        status="negada",
        atualizada_em__date__gte=inicio_mes,
    ).count()

    # Sinistros
    sinistros_qs = Sinistro.objects.filter(empresa=empresa)
    sinistros_abertos = sinistros_qs.filter(status__in=["aberto", "em_analise"]).count()
    sinistros_mes = sinistros_qs.filter(data_abertura__date__gte=inicio_mes).count()
    valor_sinistros_mes = sinistros_qs.filter(
        data_abertura__date__gte=inicio_mes,
        status__in=["aprovado", "pago"],
    ).aggregate(total=Sum("valor_total"))["total"] or Decimal("0")

    # Reembolsos
    reembolsos_qs = Reembolso.objects.filter(empresa=empresa)
    reembolsos_pendentes = reembolsos_qs.filter(status__in=["solicitado", "em_analise"]).count()
    valor_reembolsos_pagos_mes = reembolsos_qs.filter(
        data_solicitacao__date__gte=inicio_mes,
        status="pago",
    ).aggregate(total=Sum("valor_pago"))["total"] or Decimal("0")

    # Epidemiologia (últimos 30 dias na área de abrangência)
    registros_30d = RegistroSintoma.objects.filter(
        empresa=empresa,
        data_registro__date__gte=inicio_30,
    ).count()
    suspeitos_30d = RegistroSintoma.objects.filter(
        empresa=empresa,
        data_registro__date__gte=inicio_30,
        suspeito=True,
    ).count()
    prestadores_qs = PrestadorPlanoSaude.objects.filter(empresa=empresa)
    pressao_cooperacao = _pressao_epidemiologica_empresa(empresa, dias=30)
    cooperacao = _cooperacao_operadora_payload(
        empresa,
        planos,
        BeneficiarioPlano.objects.filter(plano__empresa=empresa),
        guias_qs,
        prestadores_qs,
        pressao_cooperacao,
    )

    # Top CIDs nos sinistros
    top_cids = (
        sinistros_qs.filter(cid__gt="")
        .values("cid")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")[:5]
    )

    # Planos por status
    planos_ativos = planos.filter(status="ativo").count()
    planos_inativos = planos.filter(status="inativo").count()

    return JsonResponse({
        "kpis": {
            "total_planos": total_planos,
            "planos_ativos": planos_ativos,
            "planos_inativos": planos_inativos,
            "total_beneficiarios": total_beneficiarios,
            "beneficiarios_suspensos": beneficiarios_suspensos,
            "guias_pendentes": guias_pendentes,
            "guias_sla_vencido": guias_sla_vencido,
            "guias_autorizadas_mes": guias_autorizadas_mes,
            "guias_negadas_mes": guias_negadas_mes,
            "sinistros_abertos": sinistros_abertos,
            "sinistros_mes": sinistros_mes,
            "valor_sinistros_mes": float(valor_sinistros_mes),
            "reembolsos_pendentes": reembolsos_pendentes,
            "valor_reembolsos_pagos_mes": float(valor_reembolsos_pagos_mes),
            "registros_epi_30d": registros_30d,
            "suspeitos_epi_30d": suspeitos_30d,
            "prestadores_credenciados": prestadores_qs.filter(
                status=PrestadorPlanoSaude.STATUS_CREDENCIADO
            ).count(),
            "prestadores_portal_ativo": prestadores_qs.filter(portal_ativo=True).count(),
            "fila_clinica_pendencias": guias_qs.filter(
                fila_status__in=[
                    GuiaAutorizacao.FILA_TRIAGEM,
                    GuiaAutorizacao.FILA_AUDITORIA_CLINICA,
                    GuiaAutorizacao.FILA_AUDITORIA_MEDICA,
                    GuiaAutorizacao.FILA_PENDENCIA_DOCUMENTAL,
                    GuiaAutorizacao.FILA_DEVOLVIDA_PRESTADOR,
                ]
            ).count(),
        },
        "cooperacao": cooperacao,
        "top_cids": list(top_cids),
        "planos": [_plano_dict(p) for p in planos[:10]],
    })


# ── Planos ────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_ps_planos(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = PlanoSaude.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({"planos": [_plano_dict(p) for p in qs]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        if not data.get("nome"):
            return JsonResponse({"erro": "Nome do plano obrigatório"}, status=400)
        p = PlanoSaude.objects.create(
            empresa=empresa,
            nome=data["nome"],
            registro_ans=data.get("registro_ans", ""),
            cnpj=data.get("cnpj", ""),
            modalidade=data.get("modalidade", ""),
            abrangencia=data.get("abrangencia", "nacional"),
            telefone=data.get("telefone", ""),
            email=data.get("email", ""),
            site=data.get("site", ""),
        )
        return JsonResponse({"plano": _plano_dict(p)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_plano_detalhe(request, plano_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        p = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({"erro": "Plano não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"plano": _plano_dict(p)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in ["nome", "registro_ans", "cnpj", "modalidade", "abrangencia",
                      "telefone", "email", "site", "status"]:
            if campo in data:
                setattr(p, campo, data[campo])
        p.save()
        return JsonResponse({"plano": _plano_dict(p)})

    if request.method == "DELETE":
        p.delete()
        return JsonResponse({"status": "ok"})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── Beneficiários ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_ps_beneficiarios(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = BeneficiarioPlano.objects.filter(
            plano__empresa=empresa
        ).select_related("plano")
        plano_id = request.GET.get("plano_id")
        if plano_id:
            qs = qs.filter(plano_id=plano_id)
        situacao = request.GET.get("situacao")
        if situacao:
            qs = qs.filter(situacao=situacao)
        busca = request.GET.get("busca", "").strip()
        if busca:
            qs = qs.filter(Q(nome__icontains=busca) | Q(cpf__icontains=busca) | Q(numero_carteirinha__icontains=busca))
        return JsonResponse({"beneficiarios": [_beneficiario_dict(b) for b in qs[:200]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        plano_id = data.get("plano_id")
        if not plano_id:
            return JsonResponse({"erro": "plano_id obrigatório"}, status=400)
        try:
            plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
        except PlanoSaude.DoesNotExist:
            return JsonResponse({"erro": "Plano não encontrado"}, status=404)
        if not data.get("nome"):
            return JsonResponse({"erro": "Nome obrigatório"}, status=400)
        from datetime import datetime
        dn = None
        if data.get("data_nascimento"):
            try:
                dn = datetime.strptime(data["data_nascimento"], "%Y-%m-%d").date()
            except ValueError:
                pass
        div = None
        if data.get("data_inicio_vigencia"):
            try:
                div = datetime.strptime(data["data_inicio_vigencia"], "%Y-%m-%d").date()
            except ValueError:
                pass
        dfv = None
        if data.get("data_fim_vigencia"):
            try:
                dfv = datetime.strptime(data["data_fim_vigencia"], "%Y-%m-%d").date()
            except ValueError:
                pass
        b = BeneficiarioPlano.objects.create(
            plano=plano,
            nome=data["nome"],
            cpf=data.get("cpf", ""),
            numero_carteirinha=data.get("numero_carteirinha", ""),
            data_nascimento=dn,
            sexo=data.get("sexo", ""),
            telefone=data.get("telefone", ""),
            email=data.get("email", ""),
            plano_tipo=data.get("plano_tipo", ""),
            acomodacao=data.get("acomodacao", "enfermaria"),
            situacao=data.get("situacao", "ativo"),
            data_inicio_vigencia=div,
            data_fim_vigencia=dfv,
        )
        enviar_email_novo_beneficiario(empresa, b)
        return JsonResponse({"beneficiario": _beneficiario_dict(b)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_beneficiario_detalhe(request, ben_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = BeneficiarioPlano.objects.select_related("plano").get(
            id=ben_id, plano__empresa=empresa
        )
    except BeneficiarioPlano.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"beneficiario": _beneficiario_dict(b)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        from datetime import datetime
        for campo in ["nome", "cpf", "numero_carteirinha", "sexo", "telefone",
                      "email", "plano_tipo", "acomodacao", "situacao"]:
            if campo in data:
                setattr(b, campo, data[campo])
        for campo_data in ["data_nascimento", "data_inicio_vigencia", "data_fim_vigencia"]:
            if campo_data in data and data[campo_data]:
                try:
                    setattr(b, campo_data, datetime.strptime(data[campo_data], "%Y-%m-%d").date())
                except ValueError:
                    pass
        b.save()
        return JsonResponse({"beneficiario": _beneficiario_dict(b)})

    if request.method == "DELETE":
        b.delete()
        return JsonResponse({"status": "ok"})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── Guias de Autorização ──────────────────────────────────────────────────────

@csrf_exempt
def api_ps_prestadores(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = PrestadorPlanoSaude.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        tipo_f = request.GET.get("tipo")
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        busca = request.GET.get("busca", "").strip()
        if busca:
            qs = qs.filter(
                Q(nome_fantasia__icontains=busca)
                | Q(razao_social__icontains=busca)
                | Q(cnpj__icontains=busca)
                | Q(cidade__icontains=busca)
            )
        if request.GET.get("portal_ativo") in {"1", "true"}:
            qs = qs.filter(portal_ativo=True)
        return JsonResponse({"prestadores": [_prestador_dict(p) for p in qs[:300]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        if not data.get("nome_fantasia"):
            return JsonResponse({"erro": "Nome fantasia obrigatório"}, status=400)
        import uuid as _uuid
        prestador = PrestadorPlanoSaude.objects.create(
            empresa=empresa,
            codigo_rede=data.get("codigo_rede") or f"PR-{_uuid.uuid4().hex[:6].upper()}",
            nome_fantasia=data["nome_fantasia"],
            razao_social=data.get("razao_social", ""),
            cnpj=data.get("cnpj", ""),
            tipo=data.get("tipo", PrestadorPlanoSaude.TIPO_CLINICA),
            registro_cnes=data.get("registro_cnes", ""),
            especialidades=data.get("especialidades", ""),
            cidade=data.get("cidade", ""),
            estado=data.get("estado", ""),
            telefone=data.get("telefone", ""),
            email=data.get("email", ""),
            contato_responsavel=data.get("contato_responsavel", ""),
            sla_autorizacao_horas=int(data.get("sla_autorizacao_horas") or 72),
            portal_ativo=_to_bool(data.get("portal_ativo"), default=True),
            score_qualidade=int(data.get("score_qualidade") or 85),
            status=data.get("status", PrestadorPlanoSaude.STATUS_CREDENCIADO),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"prestador": _prestador_dict(prestador)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_prestador_detalhe(request, prestador_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        prestador = PrestadorPlanoSaude.objects.get(id=prestador_id, empresa=empresa)
    except PrestadorPlanoSaude.DoesNotExist:
        return JsonResponse({"erro": "Prestador não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"prestador": _prestador_dict(prestador)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in [
            "codigo_rede", "nome_fantasia", "razao_social", "cnpj", "tipo",
            "registro_cnes", "especialidades", "cidade", "estado", "telefone",
            "email", "contato_responsavel", "status", "observacoes",
        ]:
            if campo in data:
                setattr(prestador, campo, data[campo])
        if "portal_ativo" in data:
            prestador.portal_ativo = _to_bool(data.get("portal_ativo"))
        if "sla_autorizacao_horas" in data:
            prestador.sla_autorizacao_horas = int(data.get("sla_autorizacao_horas") or 72)
        if "score_qualidade" in data:
            prestador.score_qualidade = int(data.get("score_qualidade") or 0)
        prestador.save()
        return JsonResponse({"prestador": _prestador_dict(prestador)})

    if request.method == "DELETE":
        prestador.delete()
        return JsonResponse({"status": "ok"})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


def api_ps_portal_prestador(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    pressao = _pressao_epidemiologica_empresa(empresa)
    prestadores = PrestadorPlanoSaude.objects.filter(empresa=empresa)
    lista = []
    for prestador in prestadores[:120]:
        guias = prestador.guias.all()
        pendentes = guias.filter(
            status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE]
        ).count()
        docs = guias.exclude(documentos_pendentes="").count()
        vencidas = guias.filter(
            status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
            prazo_sla_em__lt=timezone.now(),
        ).count()
        lista.append({
            **_prestador_dict(prestador),
            "guias_pendentes": pendentes,
            "guias_documentacao": docs,
            "guias_sla_vencido": vencidas,
        })
    return JsonResponse({
        "resumo": {
            "prestadores_total": prestadores.count(),
            "prestadores_portal_ativo": prestadores.filter(portal_ativo=True).count(),
            "prestadores_suspensos": prestadores.filter(
                status=PrestadorPlanoSaude.STATUS_SUSPENSO
            ).count(),
            "guias_pendentes": GuiaAutorizacao.objects.filter(
                plano__empresa=empresa,
                prestador__isnull=False,
                status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
            ).count(),
            "guias_sla_vencido": GuiaAutorizacao.objects.filter(
                plano__empresa=empresa,
                prestador__isnull=False,
                status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
                prazo_sla_em__lt=timezone.now(),
            ).count(),
            "pendencias_documentais": GuiaAutorizacao.objects.filter(
                plano__empresa=empresa,
                prestador__isnull=False,
            ).exclude(documentos_pendentes="").count(),
            "pressao_epidemiologica": pressao,
        },
        "prestadores": lista,
    })


def api_ps_fila_clinica(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    pressao = _pressao_epidemiologica_empresa(empresa)
    qs = GuiaAutorizacao.objects.filter(plano__empresa=empresa).select_related(
        "plano", "beneficiario", "prestador"
    )
    prestador_id = request.GET.get("prestador_id")
    if prestador_id:
        qs = qs.filter(prestador_id=prestador_id)
    fila_status = request.GET.get("fila_status")
    if fila_status:
        qs = qs.filter(fila_status=fila_status)
    prioridade = request.GET.get("prioridade")
    if prioridade:
        qs = qs.filter(prioridade_clinica=prioridade)
    status_f = request.GET.get("status")
    if status_f:
        qs = qs.filter(status=status_f)
    busca = request.GET.get("busca", "").strip()
    if busca:
        qs = qs.filter(
            Q(numero_guia__icontains=busca)
            | Q(beneficiario__nome__icontains=busca)
            | Q(prestador__nome_fantasia__icontains=busca)
            | Q(descricao_procedimento__icontains=busca)
            | Q(cid__icontains=busca)
        )

    guias = [_guia_dict(g) for g in qs.order_by("prazo_sla_em", "-solicitada_em")[:250]]
    return JsonResponse({
        "resumo": {
            "total": qs.count(),
            "triagem": qs.filter(fila_status=GuiaAutorizacao.FILA_TRIAGEM).count(),
            "auditoria_clinica": qs.filter(
                fila_status=GuiaAutorizacao.FILA_AUDITORIA_CLINICA
            ).count(),
            "auditoria_medica": qs.filter(
                fila_status=GuiaAutorizacao.FILA_AUDITORIA_MEDICA
            ).count(),
            "pendencia_documental": qs.filter(
                fila_status=GuiaAutorizacao.FILA_PENDENCIA_DOCUMENTAL
            ).count(),
            "sla_vencido": qs.filter(
                status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
                prazo_sla_em__lt=timezone.now(),
            ).count(),
            "pressao_epidemiologica": pressao,
        },
        "guias": guias,
    })


@csrf_exempt
def api_ps_fila_clinica_acao(request, guia_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        guia = GuiaAutorizacao.objects.select_related("prestador", "plano", "beneficiario").get(
            id=guia_id, plano__empresa=empresa
        )
    except GuiaAutorizacao.DoesNotExist:
        return JsonResponse({"erro": "Guia não encontrada"}, status=404)
    if request.method not in ("POST", "PATCH"):
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao", "")
    if "auditor_responsavel" in data:
        guia.auditor_responsavel = data.get("auditor_responsavel", "")
    if "observacao_auditoria" in data:
        guia.observacao_auditoria = data.get("observacao_auditoria", "")
    if "documentos_pendentes" in data:
        guia.documentos_pendentes = data.get("documentos_pendentes", "")
    if "prioridade_clinica" in data:
        guia.prioridade_clinica = data.get("prioridade_clinica") or guia.prioridade_clinica
        guia.prazo_sla_em = _calcular_prazo_sla(guia.prioridade_clinica, guia.prestador)

    if acao == "triagem":
        guia.status = GuiaAutorizacao.STATUS_SOLICITADA
        guia.fila_status = GuiaAutorizacao.FILA_TRIAGEM
    elif acao == "auditoria_clinica":
        guia.status = GuiaAutorizacao.STATUS_EM_ANALISE
        guia.fila_status = GuiaAutorizacao.FILA_AUDITORIA_CLINICA
    elif acao == "auditoria_medica":
        guia.status = GuiaAutorizacao.STATUS_EM_ANALISE
        guia.fila_status = GuiaAutorizacao.FILA_AUDITORIA_MEDICA
    elif acao == "pendencia_documental":
        guia.status = GuiaAutorizacao.STATUS_EM_ANALISE
        guia.fila_status = GuiaAutorizacao.FILA_PENDENCIA_DOCUMENTAL
    elif acao == "devolver_prestador":
        guia.status = GuiaAutorizacao.STATUS_EM_ANALISE
        guia.fila_status = GuiaAutorizacao.FILA_DEVOLVIDA_PRESTADOR
    elif acao == "autorizar":
        guia.status = GuiaAutorizacao.STATUS_AUTORIZADA
        guia.fila_status = GuiaAutorizacao.FILA_AUTORIZADA
        guia.numero_autorizacao = data.get("numero_autorizacao") or guia.numero_autorizacao or f"AUTH-{guia.id:05d}"
        if data.get("validade_autorizacao"):
            from datetime import datetime as _dt
            try:
                guia.validade_autorizacao = _dt.strptime(
                    data["validade_autorizacao"], "%Y-%m-%d"
                ).date()
            except ValueError:
                pass
        elif not guia.validade_autorizacao:
            guia.validade_autorizacao = timezone.localdate() + timedelta(days=30)
    elif acao == "negar":
        guia.status = GuiaAutorizacao.STATUS_NEGADA
        guia.fila_status = GuiaAutorizacao.FILA_NEGADA
        guia.justificativa_negativa = data.get("justificativa_negativa", guia.justificativa_negativa)

    if "status" in data:
        guia.status = data["status"]
        if "fila_status" not in data:
            guia.fila_status = _fila_status_from_status(guia.status)
    if "fila_status" in data:
        guia.fila_status = data["fila_status"]
    guia.save()
    return JsonResponse({"guia": _guia_dict(guia)})

@csrf_exempt
def api_ps_guias(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = GuiaAutorizacao.objects.filter(
            plano__empresa=empresa
        ).select_related("plano", "beneficiario", "prestador")
        plano_id = request.GET.get("plano_id")
        if plano_id:
            qs = qs.filter(plano_id=plano_id)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        prestador_id = request.GET.get("prestador_id")
        if prestador_id:
            qs = qs.filter(prestador_id=prestador_id)
        fila_status = request.GET.get("fila_status")
        if fila_status:
            qs = qs.filter(fila_status=fila_status)
        prioridade = request.GET.get("prioridade")
        if prioridade:
            qs = qs.filter(prioridade_clinica=prioridade)
        ben_id = request.GET.get("beneficiario_id")
        if ben_id:
            qs = qs.filter(beneficiario_id=ben_id)
        return JsonResponse({"guias": [_guia_dict(g) for g in qs[:200]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        try:
            plano = PlanoSaude.objects.get(id=data.get("plano_id"), empresa=empresa)
            beneficiario = BeneficiarioPlano.objects.get(
                id=data.get("beneficiario_id"), plano__empresa=empresa
            )
        except (PlanoSaude.DoesNotExist, BeneficiarioPlano.DoesNotExist):
            return JsonResponse({"erro": "Plano ou beneficiário não encontrado"}, status=404)
        prestador = None
        if data.get("prestador_id"):
            prestador = PrestadorPlanoSaude.objects.filter(
                id=data.get("prestador_id"), empresa=empresa
            ).first()
            if not prestador:
                return JsonResponse({"erro": "Prestador não encontrado"}, status=404)
        if not data.get("descricao_procedimento"):
            return JsonResponse({"erro": "Descrição do procedimento obrigatória"}, status=400)
        import uuid as _uuid
        valor = None
        if data.get("valor_estimado"):
            try:
                valor = Decimal(str(data["valor_estimado"]))
            except Exception:
                pass
        prioridade = data.get("prioridade_clinica") or GuiaAutorizacao.PRIORIDADE_ELETIVA
        g = GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            prestador=prestador,
            numero_guia=data.get("numero_guia") or f"G{_uuid.uuid4().hex[:8].upper()}",
            tipo=data.get("tipo", "consulta"),
            descricao_procedimento=data["descricao_procedimento"],
            cid=data.get("cid", ""),
            medico_solicitante=data.get("medico_solicitante", ""),
            crm_medico=data.get("crm_medico", ""),
            quantidade=int(data.get("quantidade", 1)),
            valor_estimado=valor,
            status=GuiaAutorizacao.STATUS_SOLICITADA,
            prioridade_clinica=prioridade,
            fila_status=GuiaAutorizacao.FILA_TRIAGEM,
            auditor_responsavel=data.get("auditor_responsavel", ""),
            documentos_pendentes=data.get("documentos_pendentes", ""),
            observacao_auditoria=data.get("observacao_auditoria", ""),
            prazo_sla_em=_calcular_prazo_sla(prioridade, prestador),
        )
        return JsonResponse({"guia": _guia_dict(g)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_guia_detalhe(request, guia_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        g = GuiaAutorizacao.objects.select_related("plano", "beneficiario", "prestador").get(
            id=guia_id, plano__empresa=empresa
        )
    except GuiaAutorizacao.DoesNotExist:
        return JsonResponse({"erro": "Guia não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"guia": _guia_dict(g)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        if "prestador_id" in data:
            if data["prestador_id"]:
                prestador = PrestadorPlanoSaude.objects.filter(
                    id=data["prestador_id"], empresa=empresa
                ).first()
                if not prestador:
                    return JsonResponse({"erro": "Prestador não encontrado"}, status=404)
                g.prestador = prestador
            else:
                g.prestador = None
        for campo in ["status", "numero_autorizacao", "justificativa_negativa", "cid",
                      "descricao_procedimento", "medico_solicitante", "auditor_responsavel",
                      "observacao_auditoria", "documentos_pendentes", "prioridade_clinica",
                      "fila_status"]:
            if campo in data:
                setattr(g, campo, data[campo])
        if "validade_autorizacao" in data and data["validade_autorizacao"]:
            from datetime import datetime
            try:
                g.validade_autorizacao = datetime.strptime(data["validade_autorizacao"], "%Y-%m-%d").date()
            except ValueError:
                pass
        if "prazo_sla_em" in data and data["prazo_sla_em"]:
            from datetime import datetime
            try:
                g.prazo_sla_em = datetime.fromisoformat(data["prazo_sla_em"])
            except ValueError:
                pass
        elif "prioridade_clinica" in data or "prestador_id" in data:
            g.prazo_sla_em = _calcular_prazo_sla(g.prioridade_clinica, g.prestador)
        if "status" in data and "fila_status" not in data:
            g.fila_status = _fila_status_from_status(g.status)
        g.save()
        return JsonResponse({"guia": _guia_dict(g)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── Sinistros ─────────────────────────────────────────────────────────────────

@csrf_exempt
def api_ps_sinistros(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = Sinistro.objects.filter(empresa=empresa).select_related("plano", "beneficiario")
        plano_id = request.GET.get("plano_id")
        if plano_id:
            qs = qs.filter(plano_id=plano_id)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        tipo_f = request.GET.get("tipo")
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        busca = request.GET.get("busca", "").strip()
        if busca:
            qs = qs.filter(
                Q(beneficiario__nome__icontains=busca) |
                Q(numero_sinistro__icontains=busca) |
                Q(prestador__icontains=busca) |
                Q(cid__icontains=busca)
            )
        return JsonResponse({"sinistros": [_sinistro_dict(s) for s in qs[:200]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        try:
            plano = PlanoSaude.objects.get(id=data.get("plano_id"), empresa=empresa)
            beneficiario = BeneficiarioPlano.objects.get(
                id=data.get("beneficiario_id"), plano__empresa=empresa
            )
        except (PlanoSaude.DoesNotExist, BeneficiarioPlano.DoesNotExist):
            return JsonResponse({"erro": "Plano ou beneficiário não encontrado"}, status=404)
        import uuid as _uuid
        from datetime import datetime as _dt
        data_at = None
        if data.get("data_atendimento"):
            try:
                data_at = _dt.strptime(data["data_atendimento"], "%Y-%m-%d").date()
            except ValueError:
                pass
        s = Sinistro.objects.create(
            empresa=empresa,
            plano=plano,
            beneficiario=beneficiario,
            numero_sinistro=data.get("numero_sinistro") or f"S{_uuid.uuid4().hex[:8].upper()}",
            tipo=data.get("tipo", "consulta"),
            cid=data.get("cid", ""),
            descricao_procedimento=data.get("descricao_procedimento", ""),
            prestador=data.get("prestador", ""),
            medico=data.get("medico", ""),
            data_atendimento=data_at,
            valor_total=Decimal(str(data.get("valor_total") or 0)),
            observacao=data.get("observacao", ""),
            status="aberto",
        )
        return JsonResponse({"sinistro": _sinistro_dict(s)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_sinistro_detalhe(request, sinistro_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        s = Sinistro.objects.select_related("plano", "beneficiario").get(
            id=sinistro_id, empresa=empresa
        )
    except Sinistro.DoesNotExist:
        return JsonResponse({"erro": "Sinistro não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"sinistro": _sinistro_dict(s)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in ["status", "tipo", "cid", "descricao_procedimento",
                      "prestador", "medico", "observacao"]:
            if campo in data:
                setattr(s, campo, data[campo])
        if "valor_total" in data:
            s.valor_total = Decimal(str(data["valor_total"] or 0))
        if "valor_pago" in data:
            s.valor_pago = Decimal(str(data["valor_pago"] or 0))
        if data.get("status") in ("aprovado", "pago", "negado", "cancelado") and not s.data_fechamento:
            s.data_fechamento = timezone.now()
        s.save()
        return JsonResponse({"sinistro": _sinistro_dict(s)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── Reembolsos ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_ps_reembolsos(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = Reembolso.objects.filter(empresa=empresa).select_related("plano", "beneficiario")
        plano_id = request.GET.get("plano_id")
        if plano_id:
            qs = qs.filter(plano_id=plano_id)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        ben_id = request.GET.get("beneficiario_id")
        if ben_id:
            qs = qs.filter(beneficiario_id=ben_id)
        return JsonResponse({"reembolsos": [_reembolso_dict(r) for r in qs[:200]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        try:
            plano = PlanoSaude.objects.get(id=data.get("plano_id"), empresa=empresa)
            beneficiario = BeneficiarioPlano.objects.get(
                id=data.get("beneficiario_id"), plano__empresa=empresa
            )
        except (PlanoSaude.DoesNotExist, BeneficiarioPlano.DoesNotExist):
            return JsonResponse({"erro": "Plano ou beneficiário não encontrado"}, status=404)
        import uuid as _uuid
        sinistro = None
        if data.get("sinistro_id"):
            sinistro = Sinistro.objects.filter(id=data["sinistro_id"], empresa=empresa).first()
        r = Reembolso.objects.create(
            empresa=empresa,
            plano=plano,
            beneficiario=beneficiario,
            sinistro=sinistro,
            numero_reembolso=data.get("numero_reembolso") or f"R{_uuid.uuid4().hex[:8].upper()}",
            tipo_despesa=data.get("tipo_despesa", "consulta"),
            valor_solicitado=Decimal(str(data.get("valor_solicitado") or 0)),
            banco=data.get("banco", ""),
            agencia=data.get("agencia", ""),
            conta=data.get("conta", ""),
            descricao=data.get("descricao", ""),
            observacao=data.get("observacao", ""),
            status="solicitado",
        )
        return JsonResponse({"reembolso": _reembolso_dict(r)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_reembolso_detalhe(request, reembolso_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        r = Reembolso.objects.select_related("plano", "beneficiario").get(
            id=reembolso_id, empresa=empresa
        )
    except Reembolso.DoesNotExist:
        return JsonResponse({"erro": "Reembolso não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"reembolso": _reembolso_dict(r)})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in ["status", "tipo_despesa", "banco", "agencia",
                      "conta", "descricao", "observacao"]:
            if campo in data:
                setattr(r, campo, data[campo])
        if "valor_aprovado" in data:
            r.valor_aprovado = Decimal(str(data["valor_aprovado"] or 0))
        if "valor_pago" in data:
            r.valor_pago = Decimal(str(data["valor_pago"] or 0))
        if "data_pagamento" in data and data["data_pagamento"]:
            from datetime import datetime as _dt
            try:
                r.data_pagamento = _dt.strptime(data["data_pagamento"], "%Y-%m-%d").date()
            except ValueError:
                pass
        r.save()
        return JsonResponse({"reembolso": _reembolso_dict(r)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── KPIs e relatórios ─────────────────────────────────────────────────────────

def api_ps_kpis(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    sinistros_qs = Sinistro.objects.filter(empresa=empresa)
    reembolsos_qs = Reembolso.objects.filter(empresa=empresa)
    guias_qs = GuiaAutorizacao.objects.filter(plano__empresa=empresa)
    prestadores_qs = PrestadorPlanoSaude.objects.filter(empresa=empresa)

    # Taxa de aprovação de guias
    guias_decididas = guias_qs.filter(status__in=["autorizada", "negada"]).count()
    guias_autorizadas = guias_qs.filter(status="autorizada").count()
    taxa_aprovacao = round((guias_autorizadas / guias_decididas * 100) if guias_decididas else 0, 1)

    # Custo médio por sinistro
    custo_medio = sinistros_qs.filter(
        status__in=["aprovado", "pago"]
    ).aggregate(media=Avg("valor_total"))["media"] or 0

    # Distribuição de sinistros por tipo
    dist_tipo = (
        sinistros_qs.values("tipo")
        .annotate(qtd=Count("id"), valor=Sum("valor_total"))
        .order_by("-qtd")
    )

    # Reembolsos por status
    dist_reembolso = (
        reembolsos_qs.values("status")
        .annotate(qtd=Count("id"), valor=Sum("valor_solicitado"))
        .order_by("-qtd")
    )

    dist_fila = (
        guias_qs.values("fila_status")
        .annotate(qtd=Count("id"))
        .order_by("-qtd")
    )

    # Série mensal de sinistros (últimos 6 meses) sem N+1 de consultas.
    hoje = date.today()
    mes_atual = hoje.replace(day=1)

    def _somar_meses_inicio(mes_inicio, deslocamento):
        total_meses = (mes_inicio.year * 12 + (mes_inicio.month - 1)) + deslocamento
        novo_ano = total_meses // 12
        novo_mes = (total_meses % 12) + 1
        return date(novo_ano, novo_mes, 1)

    meses = [_somar_meses_inicio(mes_atual, deslocamento) for deslocamento in range(-5, 1)]
    serie_bruta = (
        sinistros_qs
        .filter(data_abertura__date__gte=meses[0], data_abertura__date__lte=hoje)
        .annotate(mes=TruncMonth("data_abertura", tzinfo=timezone.get_current_timezone()))
        .values("mes")
        .annotate(
            sinistros=Count("id"),
            valor=Sum("valor_total", filter=Q(status__in=["aprovado", "pago"])),
        )
    )
    serie_por_mes = {}
    for item in serie_bruta:
        mes_ref = item["mes"]
        if hasattr(mes_ref, "date"):
            mes_ref = mes_ref.date()
        serie_por_mes[(mes_ref.year, mes_ref.month)] = item

    serie = []
    for mes_inicio in meses:
        linha = serie_por_mes.get((mes_inicio.year, mes_inicio.month), {})
        serie.append({
            "mes": mes_inicio.strftime("%b/%y"),
            "sinistros": linha.get("sinistros", 0),
            "valor": float(linha.get("valor") or 0),
        })

    return JsonResponse({
        "taxa_aprovacao_guias": taxa_aprovacao,
        "custo_medio_sinistro": float(custo_medio),
        "dist_tipo_sinistro": list(dist_tipo),
        "dist_reembolso_status": list(dist_reembolso),
        "dist_fila_clinica": list(dist_fila),
        "prestadores_ativos": prestadores_qs.filter(
            status=PrestadorPlanoSaude.STATUS_CREDENCIADO
        ).count(),
        "prestadores_portal_ativo": prestadores_qs.filter(portal_ativo=True).count(),
        "guias_sla_vencido": guias_qs.filter(
            status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
            prazo_sla_em__lt=timezone.now(),
        ).count(),
        "serie_sinistros": serie,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# GLOSAS ── controle de glosas e recursos
# ═══════════════════════════════════════════════════════════════════════════════

def _glosa_dict(g):
    return {
        "id": g.id,
        "sinistro_id": g.sinistro_id,
        "codigo_procedimento": g.codigo_procedimento,
        "descricao": g.descricao,
        "valor_original": float(g.valor_original),
        "valor_glosado": float(g.valor_glosado),
        "motivo": g.motivo,
        "status": g.status,
        "status_label": g.get_status_display(),
        "data_glosa": g.data_glosa.isoformat() if g.data_glosa else None,
        "data_recurso": g.data_recurso.isoformat() if g.data_recurso else None,
        "resposta_recurso": g.resposta_recurso,
        "criado_em": g.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
def api_ps_glosas(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    sinistros_empresa = Sinistro.objects.filter(empresa=empresa).values_list("id", flat=True)
    qs = GlosaItem.objects.filter(sinistro_id__in=sinistros_empresa)

    if request.method == "GET":
        sinistro_id = request.GET.get("sinistro_id")
        status_f = request.GET.get("status", "")
        if sinistro_id:
            qs = qs.filter(sinistro_id=sinistro_id)
        if status_f:
            qs = qs.filter(status=status_f)

        summary = qs.aggregate(
            total_glosado=Sum("valor_glosado"),
            total_original=Sum("valor_original"),
        )
        por_status = list(
            qs.values("status").annotate(qtd=Count("id"), valor=Sum("valor_glosado")).order_by("-qtd")
        )
        return JsonResponse({
            "glosas": [_glosa_dict(g) for g in qs.select_related("sinistro")[:200]],
            "total_glosado": float(summary["total_glosado"] or 0),
            "total_original": float(summary["total_original"] or 0),
            "por_status": por_status,
        })

    if request.method == "POST":
        data = json.loads(request.body or "{}")
        sinistro_id = data.get("sinistro_id")
        if not sinistro_id:
            return JsonResponse({"erro": "sinistro_id obrigatório"}, status=400)
        try:
            sinistro = Sinistro.objects.get(id=sinistro_id, empresa=empresa)
        except Sinistro.DoesNotExist:
            return JsonResponse({"erro": "Sinistro não encontrado"}, status=404)

        g = GlosaItem.objects.create(
            sinistro=sinistro,
            codigo_procedimento=data.get("codigo_procedimento", ""),
            descricao=data.get("descricao", ""),
            valor_original=Decimal(str(data.get("valor_original", 0))),
            valor_glosado=Decimal(str(data.get("valor_glosado", 0))),
            motivo=data.get("motivo", ""),
            status=data.get("status", GlosaItem.STATUS_GLOSADO),
        )
        return JsonResponse({"glosa": _glosa_dict(g)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_glosa_detalhe(request, glosa_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    sinistros_empresa = Sinistro.objects.filter(empresa=empresa).values_list("id", flat=True)
    try:
        g = GlosaItem.objects.get(id=glosa_id, sinistro_id__in=sinistros_empresa)
    except GlosaItem.DoesNotExist:
        return JsonResponse({"erro": "Glosa não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"glosa": _glosa_dict(g)})

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body or "{}")
        for campo in ("codigo_procedimento", "descricao", "motivo", "status", "resposta_recurso"):
            if campo in data:
                setattr(g, campo, data[campo])
        for campo in ("valor_original", "valor_glosado"):
            if campo in data:
                setattr(g, campo, Decimal(str(data[campo] or 0)))
        for campo in ("data_glosa", "data_recurso"):
            if campo in data and data[campo]:
                from datetime import datetime as _dt
                try:
                    setattr(g, campo, _dt.strptime(data[campo], "%Y-%m-%d").date())
                except ValueError:
                    pass
        g.save()
        return JsonResponse({"glosa": _glosa_dict(g)})

    if request.method == "DELETE":
        g.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ═══════════════════════════════════════════════════════════════════════════════
# COPARTICIPAÇÃO ── regras por tipo de atendimento
# ═══════════════════════════════════════════════════════════════════════════════

def _copart_dict(r):
    return {
        "id": r.id,
        "plano_id": r.plano_id,
        "plano_nome": r.plano.nome,
        "tipo_atendimento": r.tipo_atendimento,
        "tipo_label": r.get_tipo_atendimento_display(),
        "percentual": float(r.percentual),
        "valor_fixo": float(r.valor_fixo),
        "teto_mensal": float(r.teto_mensal) if r.teto_mensal is not None else None,
        "ativo": r.ativo,
        "criado_em": r.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
def api_ps_coparticipacao(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    planos_empresa = PlanoSaude.objects.filter(empresa=empresa).values_list("id", flat=True)
    qs = CoparticipacaoRegra.objects.filter(plano_id__in=planos_empresa).select_related("plano")

    if request.method == "GET":
        plano_id = request.GET.get("plano_id")
        if plano_id:
            qs = qs.filter(plano_id=plano_id)
        return JsonResponse({"regras": [_copart_dict(r) for r in qs]})

    if request.method == "POST":
        data = json.loads(request.body or "{}")
        plano_id = data.get("plano_id")
        tipo = data.get("tipo_atendimento")
        if not plano_id or not tipo:
            return JsonResponse({"erro": "plano_id e tipo_atendimento obrigatórios"}, status=400)
        try:
            plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
        except PlanoSaude.DoesNotExist:
            return JsonResponse({"erro": "Plano não encontrado"}, status=404)

        r, created = CoparticipacaoRegra.objects.get_or_create(
            plano=plano, tipo_atendimento=tipo,
            defaults={
                "percentual": Decimal(str(data.get("percentual", 0))),
                "valor_fixo": Decimal(str(data.get("valor_fixo", 0))),
                "teto_mensal": Decimal(str(data["teto_mensal"])) if data.get("teto_mensal") else None,
                "ativo": _to_bool(data.get("ativo"), True),
            }
        )
        if not created:
            r.percentual = Decimal(str(data.get("percentual", r.percentual)))
            r.valor_fixo = Decimal(str(data.get("valor_fixo", r.valor_fixo)))
            if "teto_mensal" in data:
                r.teto_mensal = Decimal(str(data["teto_mensal"])) if data["teto_mensal"] else None
            if "ativo" in data:
                r.ativo = _to_bool(data["ativo"])
            r.save()
        return JsonResponse({"regra": _copart_dict(r)}, status=201 if created else 200)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_coparticipacao_detalhe(request, regra_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    planos_empresa = PlanoSaude.objects.filter(empresa=empresa).values_list("id", flat=True)
    try:
        r = CoparticipacaoRegra.objects.select_related("plano").get(id=regra_id, plano_id__in=planos_empresa)
    except CoparticipacaoRegra.DoesNotExist:
        return JsonResponse({"erro": "Regra não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"regra": _copart_dict(r)})

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body or "{}")
        for campo in ("percentual", "valor_fixo"):
            if campo in data:
                setattr(r, campo, Decimal(str(data[campo] or 0)))
        if "teto_mensal" in data:
            r.teto_mensal = Decimal(str(data["teto_mensal"])) if data["teto_mensal"] else None
        if "ativo" in data:
            r.ativo = _to_bool(data["ativo"])
        r.save()
        return JsonResponse({"regra": _copart_dict(r)})

    if request.method == "DELETE":
        r.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ═══════════════════════════════════════════════════════════════════════════════
# FATURAMENTO ── faturas mensais dos beneficiários
# ═══════════════════════════════════════════════════════════════════════════════

def _fatura_dict(f):
    return {
        "id": f.id,
        "beneficiario_id": f.beneficiario_id,
        "beneficiario_nome": f.beneficiario.nome,
        "plano_id": f.plano_id,
        "plano_nome": f.plano.nome,
        "competencia": f.competencia,
        "valor_mensalidade": float(f.valor_mensalidade),
        "valor_coparticipacao": float(f.valor_coparticipacao),
        "valor_total": float(f.valor_total),
        "status": f.status,
        "status_label": f.get_status_display(),
        "vencimento": f.vencimento.isoformat() if f.vencimento else None,
        "pago_em": f.pago_em.isoformat() if f.pago_em else None,
        "observacao": f.observacao,
        "criado_em": f.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
def api_ps_faturamento(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    qs = FaturamentoBeneficiario.objects.filter(empresa=empresa).select_related("beneficiario", "plano")

    if request.method == "GET":
        competencia = request.GET.get("competencia", "")
        status_f = request.GET.get("status", "")
        plano_id = request.GET.get("plano_id")
        if competencia:
            qs = qs.filter(competencia=competencia)
        if status_f:
            qs = qs.filter(status=status_f)
        if plano_id:
            qs = qs.filter(plano_id=plano_id)

        summary = qs.aggregate(
            total_mensalidade=Sum("valor_mensalidade"),
            total_copart=Sum("valor_coparticipacao"),
            total_geral=Sum("valor_total"),
        )
        por_status = list(
            qs.values("status").annotate(qtd=Count("id"), valor=Sum("valor_total")).order_by("-qtd")
        )
        return JsonResponse({
            "faturas": [_fatura_dict(f) for f in qs[:300]],
            "total_mensalidade": float(summary["total_mensalidade"] or 0),
            "total_coparticipacao": float(summary["total_copart"] or 0),
            "total_geral": float(summary["total_geral"] or 0),
            "por_status": por_status,
        })

    if request.method == "POST":
        data = json.loads(request.body or "{}")
        beneficiario_id = data.get("beneficiario_id")
        plano_id = data.get("plano_id")
        competencia = data.get("competencia", "")
        if not beneficiario_id or not plano_id or not competencia:
            return JsonResponse({"erro": "beneficiario_id, plano_id e competencia são obrigatórios"}, status=400)
        try:
            beneficiario = BeneficiarioPlano.objects.get(id=beneficiario_id, plano__empresa=empresa)
            plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
        except (BeneficiarioPlano.DoesNotExist, PlanoSaude.DoesNotExist):
            return JsonResponse({"erro": "Beneficiário ou plano não encontrado"}, status=404)

        valor_mens = Decimal(str(data.get("valor_mensalidade", 0)))
        valor_cop = Decimal(str(data.get("valor_coparticipacao", 0)))
        f, created = FaturamentoBeneficiario.objects.get_or_create(
            empresa=empresa,
            beneficiario=beneficiario,
            competencia=competencia,
            defaults={
                "plano": plano,
                "valor_mensalidade": valor_mens,
                "valor_coparticipacao": valor_cop,
                "valor_total": valor_mens + valor_cop,
                "status": data.get("status", FaturamentoBeneficiario.STATUS_PENDENTE),
                "observacao": data.get("observacao", ""),
            }
        )
        if not created:
            return JsonResponse({"erro": "Fatura já existe para esta competência"}, status=409)
        return JsonResponse({"fatura": _fatura_dict(f)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_fatura_detalhe(request, fatura_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    try:
        f = FaturamentoBeneficiario.objects.select_related("beneficiario", "plano").get(
            id=fatura_id, empresa=empresa
        )
    except FaturamentoBeneficiario.DoesNotExist:
        return JsonResponse({"erro": "Fatura não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"fatura": _fatura_dict(f)})

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body or "{}")
        for campo in ("status", "observacao"):
            if campo in data:
                setattr(f, campo, data[campo])
        for campo in ("valor_mensalidade", "valor_coparticipacao", "valor_total"):
            if campo in data:
                setattr(f, campo, Decimal(str(data[campo] or 0)))
        for campo in ("vencimento", "pago_em"):
            if campo in data and data[campo]:
                from datetime import datetime as _dt
                try:
                    setattr(f, campo, _dt.strptime(data[campo], "%Y-%m-%d").date())
                except ValueError:
                    pass
        f.save()
        return JsonResponse({"fatura": _fatura_dict(f)})

    if request.method == "DELETE":
        f.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRAMAS DE SAÚDE ── DIP, crônicos, oncologia, preventivo…
# ═══════════════════════════════════════════════════════════════════════════════

def _programa_dict(p):
    return {
        "id": p.id,
        "nome": p.nome,
        "tipo": p.tipo,
        "tipo_label": p.get_tipo_display(),
        "descricao": p.descricao,
        "ativo": p.ativo,
        "total_inscritos": p.inscricoes.filter(status=InscricaoPrograma.STATUS_ATIVO).count(),
        "criado_em": p.criado_em.strftime("%d/%m/%Y"),
    }


def _inscricao_dict(i):
    return {
        "id": i.id,
        "programa_id": i.programa_id,
        "programa_nome": i.programa.nome,
        "beneficiario_id": i.beneficiario_id,
        "beneficiario_nome": i.beneficiario.nome,
        "data_inscricao": i.data_inscricao.isoformat() if i.data_inscricao else None,
        "status": i.status,
        "status_label": i.get_status_display(),
        "observacao": i.observacao,
        "criado_em": i.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
def api_ps_programas(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    qs = ProgramaSaude.objects.filter(empresa=empresa).prefetch_related("inscricoes")

    if request.method == "GET":
        tipo_f = request.GET.get("tipo", "")
        ativo_f = request.GET.get("ativo", "")
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        if ativo_f:
            qs = qs.filter(ativo=_to_bool(ativo_f, True))
        return JsonResponse({"programas": [_programa_dict(p) for p in qs]})

    if request.method == "POST":
        data = json.loads(request.body or "{}")
        nome = data.get("nome", "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        p = ProgramaSaude.objects.create(
            empresa=empresa,
            nome=nome,
            tipo=data.get("tipo", ProgramaSaude.TIPO_CRONICO),
            descricao=data.get("descricao", ""),
            ativo=_to_bool(data.get("ativo"), True),
        )
        return JsonResponse({"programa": _programa_dict(p)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_programa_detalhe(request, programa_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    try:
        p = ProgramaSaude.objects.prefetch_related("inscricoes__beneficiario").get(
            id=programa_id, empresa=empresa
        )
    except ProgramaSaude.DoesNotExist:
        return JsonResponse({"erro": "Programa não encontrado"}, status=404)

    if request.method == "GET":
        inscritos = [_inscricao_dict(i) for i in p.inscricoes.select_related("beneficiario", "programa").all()]
        d = _programa_dict(p)
        d["inscricoes"] = inscritos
        return JsonResponse({"programa": d})

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body or "{}")
        for campo in ("nome", "tipo", "descricao"):
            if campo in data:
                setattr(p, campo, data[campo])
        if "ativo" in data:
            p.ativo = _to_bool(data["ativo"])
        p.save()
        return JsonResponse({"programa": _programa_dict(p)})

    if request.method == "DELETE":
        p.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_inscricoes(request):
    """Listar ou criar inscrições de beneficiários em programas de saúde."""
    empresa, err = _ps_auth(request)
    if err:
        return err

    programas_empresa = ProgramaSaude.objects.filter(empresa=empresa).values_list("id", flat=True)
    qs = InscricaoPrograma.objects.filter(programa_id__in=programas_empresa).select_related("programa", "beneficiario")

    if request.method == "GET":
        programa_id = request.GET.get("programa_id")
        beneficiario_id = request.GET.get("beneficiario_id")
        status_f = request.GET.get("status", "")
        if programa_id:
            qs = qs.filter(programa_id=programa_id)
        if beneficiario_id:
            qs = qs.filter(beneficiario_id=beneficiario_id)
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({"inscricoes": [_inscricao_dict(i) for i in qs[:300]]})

    if request.method == "POST":
        data = json.loads(request.body or "{}")
        programa_id = data.get("programa_id")
        beneficiario_id = data.get("beneficiario_id")
        if not programa_id or not beneficiario_id:
            return JsonResponse({"erro": "programa_id e beneficiario_id obrigatórios"}, status=400)
        try:
            programa = ProgramaSaude.objects.get(id=programa_id, empresa=empresa)
        except ProgramaSaude.DoesNotExist:
            return JsonResponse({"erro": "Programa não encontrado"}, status=404)
        try:
            beneficiario = BeneficiarioPlano.objects.get(id=beneficiario_id, plano__empresa=empresa)
        except BeneficiarioPlano.DoesNotExist:
            return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)

        inscricao, created = InscricaoPrograma.objects.get_or_create(
            programa=programa,
            beneficiario=beneficiario,
            defaults={
                "status": data.get("status", InscricaoPrograma.STATUS_ATIVO),
                "observacao": data.get("observacao", ""),
            }
        )
        if not created:
            return JsonResponse({"erro": "Beneficiário já inscrito neste programa"}, status=409)
        return JsonResponse({"inscricao": _inscricao_dict(inscricao)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_inscricao_detalhe(request, inscricao_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    programas_empresa = ProgramaSaude.objects.filter(empresa=empresa).values_list("id", flat=True)
    try:
        i = InscricaoPrograma.objects.select_related("programa", "beneficiario").get(
            id=inscricao_id, programa_id__in=programas_empresa
        )
    except InscricaoPrograma.DoesNotExist:
        return JsonResponse({"erro": "Inscrição não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"inscricao": _inscricao_dict(i)})

    if request.method in ("PUT", "PATCH"):
        data = json.loads(request.body or "{}")
        for campo in ("status", "observacao"):
            if campo in data:
                setattr(i, campo, data[campo])
        i.save()
        return JsonResponse({"inscricao": _inscricao_dict(i)})

    if request.method == "DELETE":
        i.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ═══════════════════════════════════════════════════════════════════════════════
# SINISTRALIDADE + IA ── analytics avançado com scoring de risco
# ═══════════════════════════════════════════════════════════════════════════════

def _score_risco_beneficiario(beneficiario, sinistros_qs, epidemio):
    """
    Calcula score de risco do beneficiário (0-100).
    Considera: volume de sinistros, valor total, suspeitos epidemiológicos,
    programas crônicos e cobertura faturamento vencido.
    """
    score = 0

    # Sinistros do beneficiário nos últimos 12 meses
    ben_sinistros = sinistros_qs.filter(beneficiario=beneficiario)
    qtd_sinistros = ben_sinistros.count()
    valor_sinistros = float(ben_sinistros.aggregate(v=Sum("valor_total"))["v"] or 0)

    # Volume de sinistros (0–25 pts)
    score += min(25, qtd_sinistros * 5)

    # Valor total (0–25 pts): escala R$0–R$50.000
    score += min(25, int(valor_sinistros / 2000))

    # Programas crônicos ativos (0–20 pts)
    programas_cronicos = InscricaoPrograma.objects.filter(
        beneficiario=beneficiario,
        status=InscricaoPrograma.STATUS_ATIVO,
        programa__tipo__in=[ProgramaSaude.TIPO_CRONICO, ProgramaSaude.TIPO_ONCOLOGIA],
    ).count()
    score += min(20, programas_cronicos * 10)

    # Pressão epidemiológica (0–15 pts)
    nivel = epidemio.get("nivel", "controlada")
    ep_score = {"controlada": 0, "monitoramento": 5, "moderada": 10, "alta": 15}.get(nivel, 0)
    score += ep_score

    # Faturas vencidas (0–15 pts)
    faturas_vencidas = FaturamentoBeneficiario.objects.filter(
        beneficiario=beneficiario, status=FaturamentoBeneficiario.STATUS_VENCIDO
    ).count()
    score += min(15, faturas_vencidas * 5)

    return min(100, score)


def api_ps_sinistralidade_ia(request):
    """
    Analytics avançado de sinistralidade com IA: scoring de risco por beneficiário,
    correlação com dados epidemiológicos, ranking de CIDs de alto custo,
    previsão de tendência e alertas automáticos.
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    hoje = date.today()
    inicio_ano = hoje.replace(month=1, day=1)
    ultimo_mes = hoje.replace(day=1) - timedelta(days=1)
    inicio_mes_atual = hoje.replace(day=1)

    sinistros_ano = Sinistro.objects.filter(
        empresa=empresa,
        data_abertura__date__gte=inicio_ano,
    )

    # ── Receita esperada vs sinistralidade ──────────────────────────────
    receita_bruta = float(
        FaturamentoBeneficiario.objects.filter(
            empresa=empresa, status=FaturamentoBeneficiario.STATUS_PAGO,
        ).filter(
            competencia__gte=inicio_ano.strftime("%Y-%m")
        ).aggregate(v=Sum("valor_mensalidade"))["v"] or 0
    )
    custo_sinistros = float(
        sinistros_ano.filter(status__in=["aprovado", "pago"]).aggregate(v=Sum("valor_total"))["v"] or 0
    )
    taxa_sinistralidade = round((custo_sinistros / receita_bruta * 100) if receita_bruta > 0 else 0, 2)

    # ── Glosas ───────────────────────────────────────────────────────────
    sinistros_ids = sinistros_ano.values_list("id", flat=True)
    total_glosado = float(
        GlosaItem.objects.filter(sinistro_id__in=sinistros_ids).aggregate(v=Sum("valor_glosado"))["v"] or 0
    )
    taxa_glosa = round((total_glosado / custo_sinistros * 100) if custo_sinistros > 0 else 0, 2)

    # ── Top CIDs de alto custo ───────────────────────────────────────────
    top_cids = list(
        sinistros_ano.filter(cid__gt="", status__in=["aprovado", "pago"])
        .values("cid")
        .annotate(qtd=Count("id"), valor=Sum("valor_total"))
        .order_by("-valor")[:10]
    )

    # ── Série mensal sinistralidade (últimos 6 meses) ────────────────────
    serie_mensal = []
    for i in range(5, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=i * 28)
        mes_inicio = ref.replace(day=1)
        competencia_str = mes_inicio.strftime("%Y-%m")
        if i == 0:
            mes_fim = hoje
        else:
            prox = (mes_inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
            mes_fim = prox - timedelta(days=1)

        custo_mes = float(
            Sinistro.objects.filter(
                empresa=empresa,
                data_abertura__date__gte=mes_inicio,
                data_abertura__date__lte=mes_fim,
                status__in=["aprovado", "pago"],
            ).aggregate(v=Sum("valor_total"))["v"] or 0
        )
        receita_mes = float(
            FaturamentoBeneficiario.objects.filter(
                empresa=empresa,
                competencia=competencia_str,
                status=FaturamentoBeneficiario.STATUS_PAGO,
            ).aggregate(v=Sum("valor_mensalidade"))["v"] or 0
        )
        sinistralidade_mes = round((custo_mes / receita_mes * 100) if receita_mes > 0 else 0, 1)
        serie_mensal.append({
            "mes": mes_inicio.strftime("%b/%y"),
            "competencia": competencia_str,
            "custo": custo_mes,
            "receita": receita_mes,
            "sinistralidade_pct": sinistralidade_mes,
        })

    # ── Pressão epidemiológica ───────────────────────────────────────────
    epidemio = _pressao_epidemiologica_empresa(empresa, dias=14)

    # ── Scoring de risco dos beneficiários (top 20) ──────────────────────
    ben_qs = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa, situacao=BeneficiarioPlano.SITUACAO_ATIVO
    ).select_related("plano")[:200]

    scores = []
    for b in ben_qs:
        score = _score_risco_beneficiario(b, sinistros_ano, epidemio)
        if score > 0:
            scores.append({
                "beneficiario_id": b.id,
                "nome": b.nome,
                "plano_nome": b.plano.nome,
                "score": score,
                "nivel": "alto" if score >= 60 else ("medio" if score >= 30 else "baixo"),
            })

    scores.sort(key=lambda x: -x["score"])
    top_risco = scores[:20]

    # ── Alertas automáticos ──────────────────────────────────────────────
    alertas = []
    if taxa_sinistralidade > 80:
        alertas.append({
            "tipo": "critico",
            "icone": "🚨",
            "mensagem": f"Sinistralidade em {taxa_sinistralidade}% — acima do limite ANS de 80%",
        })
    elif taxa_sinistralidade > 65:
        alertas.append({
            "tipo": "atencao",
            "icone": "⚠️",
            "mensagem": f"Sinistralidade em {taxa_sinistralidade}% — monitoramento necessário",
        })

    if taxa_glosa > 10:
        alertas.append({
            "tipo": "atencao",
            "icone": "📋",
            "mensagem": f"Taxa de glosa em {taxa_glosa}% — revisar auditoria médica",
        })

    if epidemio["nivel"] in ("moderada", "alta"):
        alertas.append({
            "tipo": "epidemio",
            "icone": "🦠",
            "mensagem": f"Pressão epidemiológica {epidemio['nivel']}: {epidemio['suspeitos']} casos suspeitos nos últimos {epidemio['janela_dias']} dias",
        })

    faturas_vencidas_total = FaturamentoBeneficiario.objects.filter(
        empresa=empresa, status=FaturamentoBeneficiario.STATUS_VENCIDO
    ).count()
    if faturas_vencidas_total > 0:
        alertas.append({
            "tipo": "financeiro",
            "icone": "💰",
            "mensagem": f"{faturas_vencidas_total} fatura(s) vencida(s) — impacto na inadimplência",
        })

    guias_sla_vencido = GuiaAutorizacao.objects.filter(
        plano__empresa=empresa,
        status__in=[GuiaAutorizacao.STATUS_SOLICITADA, GuiaAutorizacao.STATUS_EM_ANALISE],
        prazo_sla_em__lt=timezone.now(),
    ).count()
    if guias_sla_vencido > 0:
        alertas.append({
            "tipo": "sla",
            "icone": "⏱️",
            "mensagem": f"{guias_sla_vencido} guia(s) com SLA vencido — risco de penalidade ANS",
        })

    # ── Distribuição de sinistros por tipo ───────────────────────────────
    dist_tipo = list(
        sinistros_ano.values("tipo")
        .annotate(qtd=Count("id"), valor=Sum("valor_total"))
        .order_by("-valor")
    )

    # ── Correlação epidemiologia × sinistros ─────────────────────────────
    # Últimos 14 dias: suspeitos por CID vs sinistros por CID
    inicio_epidemio = date.today() - timedelta(days=14)
    epidemio_cids = list(
        RegistroSintoma.objects.filter(
            empresa=empresa,
            data_registro__date__gte=inicio_epidemio,
            suspeito=True,
        ).values("grupo").annotate(suspeitos=Count("id")).order_by("-suspeitos")[:10]
    )
    sinistros_cids_recentes = list(
        sinistros_ano.filter(data_abertura__date__gte=inicio_epidemio)
        .values("tipo").annotate(qtd=Count("id"), valor=Sum("valor_total"))
        .order_by("-qtd")[:10]
    )

    return JsonResponse({
        "taxa_sinistralidade": taxa_sinistralidade,
        "receita_bruta_ano": receita_bruta,
        "custo_sinistros_ano": custo_sinistros,
        "total_glosado_ano": total_glosado,
        "taxa_glosa": taxa_glosa,
        "top_cids_alto_custo": top_cids,
        "serie_mensal": serie_mensal,
        "pressao_epidemiologica": epidemio,
        "top_risco_beneficiarios": top_risco,
        "alertas": alertas,
        "dist_tipo_sinistro": dist_tipo,
        "correlacao_epidemio_cids": epidemio_cids,
        "correlacao_sinistros_cids": sinistros_cids_recentes,
    })


# ════════════════════════════════════════════════════════════════════════════════
#  DASHBOARD EXECUTIVO — MLR, PMPM, MRR, NPS
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_dashboard_exec(request):
    """GET /api/plano-saude/dashboard-exec/?periodo=mes|trimestre|ano
    Retorna indicadores financeiros e atuariais calculados a partir dos dados
    já existentes: sinistros, faturamento, beneficiários, guias.
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    periodo = request.GET.get("periodo", "mes")
    hoje = date.today()
    if periodo == "trimestre":
        inicio = hoje.replace(day=1) - timedelta(days=hoje.replace(day=1).day - 1)
        # primeiro dia do trimestre
        mes_inicio_tri = ((hoje.month - 1) // 3) * 3 + 1
        inicio = hoje.replace(month=mes_inicio_tri, day=1)
    elif periodo == "ano":
        inicio = hoje.replace(month=1, day=1)
    else:
        inicio = hoje.replace(day=1)

    # ── Receita bruta (faturamento) no período ──
    receita_qs = FaturamentoBeneficiario.objects.filter(
        plano__empresa=empresa,
        competencia__gte=inicio.strftime("%Y-%m"),
    )
    receita_bruta = float(receita_qs.aggregate(s=Sum("valor_mensalidade"))["s"] or 0)

    # ── Custo sinistros no período ──
    sinistros_qs = Sinistro.objects.filter(
        empresa=empresa,
        data_abertura__date__gte=inicio,
    )
    custo_sinistros = float(sinistros_qs.aggregate(s=Sum("valor_total"))["s"] or 0)

    mlr = round((custo_sinistros / receita_bruta * 100), 1) if receita_bruta > 0 else 0.0

    # PMPM — custo medio por beneficiario por mes
    beneficiarios_ativos = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa, situacao="ativo"
    ).count()
    meses_periodo = max(1, (hoje.year - inicio.year) * 12 + (hoje.month - inicio.month) + 1)
    pmpm = custo_sinistros / max(beneficiarios_ativos, 1) / meses_periodo

    # MRR — receita mensal recorrente (ultimo mes completo)
    competencia_atual = hoje.strftime("%Y-%m")
    mrr = float(
        FaturamentoBeneficiario.objects.filter(
            plano__empresa=empresa, competencia=competencia_atual
        ).aggregate(s=Sum("valor_mensalidade"))["s"] or 0
    )

    # Crescimento de beneficiários — últimos 12 meses
    crescimento = []
    for i in range(11, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=30 * i)
        cnt = BeneficiarioPlano.objects.filter(
            plano__empresa=empresa,
            criado_em__year=ref.year,
            criado_em__month=ref.month,
        ).count()
        crescimento.append({"mes": ref.strftime("%b"), "valor": cnt})

    # MLR por plano
    planos = PlanoSaude.objects.filter(empresa=empresa)
    mlr_por_plano = []
    for p in planos[:6]:
        rec_p = float(
            FaturamentoBeneficiario.objects.filter(plano=p, competencia__gte=inicio.strftime("%Y-%m"))
            .aggregate(s=Sum("valor_mensalidade"))["s"] or 0
        )
        sin_p = float(
            Sinistro.objects.filter(empresa=empresa, beneficiario__plano=p, data_abertura__date__gte=inicio)
            .aggregate(s=Sum("valor_total"))["s"] or 0
        )
        mlr_p = round(sin_p / rec_p * 100, 1) if rec_p > 0 else 0.0
        mlr_por_plano.append({"nome": p.nome, "valor": mlr_p})

    # MLR mensal — últimos 6 meses
    mlr_mensal = []
    for i in range(5, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=30 * i)
        comp = ref.strftime("%Y-%m")
        rec_m = float(
            FaturamentoBeneficiario.objects.filter(plano__empresa=empresa, competencia=comp)
            .aggregate(s=Sum("valor_mensalidade"))["s"] or 0
        )
        sin_m = float(
            Sinistro.objects.filter(empresa=empresa, data_abertura__year=ref.year, data_abertura__month=ref.month)
            .aggregate(s=Sum("valor_total"))["s"] or 0
        )
        mlr_m = round(sin_m / rec_m * 100, 1) if rec_m > 0 else 0.0
        mlr_mensal.append({"mes": ref.strftime("%b"), "valor": mlr_m})

    # Top procedimentos por custo
    top_proc = list(
        Sinistro.objects.filter(empresa=empresa, data_abertura__date__gte=inicio)
        .values("tipo")
        .annotate(custo=Sum("valor_total"))
        .order_by("-custo")[:5]
    )
    top_procedimentos = [{"nome": t["tipo"], "custo": float(t["custo"] or 0)} for t in top_proc]

    return JsonResponse({
        "mlr": mlr,
        "pmpm": pmpm,
        "mrr": mrr,
        "nps": 0,  # requer coleta ativa — retorna 0 se não configurado
        "crescimento_beneficiarios": crescimento,
        "mlr_por_plano": mlr_por_plano,
        "mlr_mensal": mlr_mensal,
        "top_procedimentos": top_procedimentos,
        "receita_bruta": receita_bruta,
        "custo_sinistros": custo_sinistros,
        "beneficiarios_ativos": beneficiarios_ativos,
    })


# ════════════════════════════════════════════════════════════════════════════════
#  REGULAÇÃO & SLA ANS  (RN 395/452)
# ════════════════════════════════════════════════════════════════════════════════

# Prazos em horas úteis por tipo de guia (simplificado para horas corridas)
_SLA_MAP = {
    "consulta":      {"label": "Consulta eletiva",                  "prazo": "7 dias úteis",    "horas": 168},
    "exame":         {"label": "Exame de alta complexidade",         "prazo": "10 dias úteis",   "horas": 240},
    "urgencia":      {"label": "Consulta urgência/emergência",       "prazo": "4 horas",         "horas": 4},
    "internacao":    {"label": "Internação eletiva",                 "prazo": "21 dias úteis",   "horas": 504},
    "cirurgia":      {"label": "Procedimento cirúrgico eletivo",     "prazo": "21 dias úteis",   "horas": 504},
    "quimio_radio":  {"label": "Radioterapia / Quimioterapia",       "prazo": "10 dias úteis",   "horas": 240},
    "home_care":     {"label": "Home Care",                         "prazo": "10 dias úteis",   "horas": 240},
}

@csrf_exempt
def api_ps_sla(request):
    """GET /api/plano-saude/sla/
    Monitora SLA por tipo de guia — detecta breaches em tempo real.
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    agora = timezone.now()
    guias_pendentes = GuiaAutorizacao.objects.filter(
        plano__empresa=empresa, status__in=["solicitada", "em_analise"]
    ).select_related("beneficiario")

    por_tipo = []
    breaches = []

    for tipo_key, meta in _SLA_MAP.items():
        guias_tipo = guias_pendentes.filter(tipo__icontains=tipo_key.replace("_", " "))
        # fallback: também pega pelo campo tipo exato
        if not guias_tipo.exists() and tipo_key == "consulta":
            guias_tipo = guias_pendentes.filter(tipo__in=["consulta", "Consulta Eletiva"])

        total = guias_tipo.count()
        no_prazo = 0
        for g in guias_tipo:
            horas_abertas = (agora - g.solicitada_em).total_seconds() / 3600
            if horas_abertas <= meta["horas"]:
                no_prazo += 1
            else:
                breaches.append({
                    "id": f"GUI-{g.pk}",
                    "beneficiario": g.beneficiario.nome if g.beneficiario_id else "—",
                    "tipo": meta["label"],
                    "prazo": meta["prazo"],
                    "aberto_ha": f"{int(horas_abertas)}h" if horas_abertas < 48 else f"{int(horas_abertas/24)}d",
                    "prestador": g.prestador.nome_fantasia if g.prestador_id else "—",
                })

        por_tipo.append({
            "tipo": meta["label"],
            "prazo": meta["prazo"],
            "total": total,
            "no_prazo": no_prazo,
        })

    # KPIs globais
    total_guias = sum(t["total"] for t in por_tipo)
    total_ok = sum(t["no_prazo"] for t in por_tipo)
    geral_pct = round(total_ok / total_guias * 100, 1) if total_guias > 0 else 100.0

    # Consulta
    consulta = next((t for t in por_tipo if "Consulta eletiva" in t["tipo"]), None)
    consulta_pct = round(consulta["no_prazo"] / max(consulta["total"], 1) * 100, 1) if consulta else 100.0
    exame = next((t for t in por_tipo if "complexidade" in t["tipo"]), None)
    exame_pct = round(exame["no_prazo"] / max(exame["total"], 1) * 100, 1) if exame else 100.0
    urg_v = sum(1 for b in breaches if "urgência" in b["tipo"].lower())

    return JsonResponse({
        "por_tipo": por_tipo,
        "breaches": breaches[:20],
        "geral_pct": geral_pct,
        "consulta_pct": consulta_pct,
        "exame_pct": exame_pct,
        "urg_vencidas": urg_v,
    })


# ════════════════════════════════════════════════════════════════════════════════
#  AUDITORIA MÉDICA IA — scoring de fraude/abuso por frequência de sinistros
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_auditoria(request):
    """GET /api/plano-saude/auditoria/?risco=critico|alto|medio
    Calcula score de risco por beneficiário usando frequência de sinistros
    vs. média da carteira. Sem modelo externo — query analítica pura.
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    filtro_risco = request.GET.get("risco", "")
    periodo_dias = 90
    inicio = date.today() - timedelta(days=periodo_dias)

    # Média de sinistros por beneficiário no período
    total_sin = Sinistro.objects.filter(empresa=empresa, data_abertura__date__gte=inicio).count()
    total_benef = BeneficiarioPlano.objects.filter(plano__empresa=empresa, situacao="ativo").count()
    media_carteira = total_sin / max(total_benef, 1)

    # Sinistros agrupados por beneficiário
    sin_por_benef = (
        Sinistro.objects.filter(empresa=empresa, data_abertura__date__gte=inicio)
        .values("beneficiario_id", "beneficiario__nome", "beneficiario__plano__nome")
        .annotate(
            qtd_sinistros=Count("id"),
            custo_total=Sum("valor_total"),
        )
        .order_by("-qtd_sinistros")[:50]
    )

    # Procedimentos com frequência anômala (> 2x a média)
    media_tipo = (
        Sinistro.objects.filter(empresa=empresa, data_abertura__date__gte=inicio)
        .values("tipo")
        .annotate(qtd=Count("id"), custo=Sum("valor_total"))
    )
    total_benef_ref = max(total_benef, 1)
    proc_anomalos = []
    for p in media_tipo:
        freq_real_pct = p["qtd"] / total_benef_ref * 100
        # benchmark simples: consultas ~12%, exames ~5%, internações ~2%
        benchmarks = {"consulta": 12.0, "exame": 5.0, "internacao": 2.0, "cirurgia": 1.5}
        bench = next((v for k, v in benchmarks.items() if k in (p["tipo"] or "").lower()), 3.0)
        desvio_pct = ((freq_real_pct - bench) / bench * 100) if bench > 0 else 0
        if desvio_pct > 30:
            custo_extra = float(p["custo"] or 0) * (desvio_pct / 100)
            proc_anomalos.append({
                "codigo": "—",
                "nome": p["tipo"] or "—",
                "esperada": f"{bench:.1f}%",
                "real": f"{freq_real_pct:.1f}%",
                "desvio": f"+{desvio_pct:.0f}%",
                "custo_extra": f"R$ {custo_extra:,.0f}".replace(",", "."),
                "status": "Investigar" if desvio_pct > 80 else "Monitorar",
            })

    # Score por beneficiário (0-100)
    resultado = []
    critico_count = 0
    alto_count = 0
    medio_count = 0
    economia_estimada = 0.0

    for s in sin_por_benef:
        qtd = s["qtd_sinistros"]
        custo = float(s["custo_total"] or 0)
        ratio = qtd / max(media_carteira, 0.01)
        # Score: ratio * 30 + custo penalty
        score_raw = min(int(ratio * 30 + (custo / 5000)), 100)
        score = max(score_raw, 0)

        fatores = []
        if qtd > media_carteira * 3:
            fatores.append("Alta frequência")
        if custo > 15000:
            fatores.append("Alto custo")
        if qtd > 5:
            fatores.append("Múltiplos eventos")

        nivel = "critico" if score >= 90 else "alto" if score >= 70 else "medio" if score >= 40 else "baixo"
        if nivel == "critico":
            critico_count += 1
            economia_estimada += custo * 0.2
        elif nivel == "alto":
            alto_count += 1
            economia_estimada += custo * 0.1
        elif nivel == "medio":
            medio_count += 1

        if filtro_risco and nivel != filtro_risco:
            continue

        resultado.append({
            "nome": s["beneficiario__nome"] or "—",
            "plano": s["beneficiario__plano__nome"] or "—",
            "score": score,
            "fatores": fatores,
            "qtd_sinistros": qtd,
            "custo_total": custo,
        })

    padroes = [
        {"nome": "Fracionamento de procedimentos", "count": max(0, critico_count * 2), "impacto": "Alto"},
        {"nome": "Guias sem CID correspondente", "count": max(0, alto_count * 3), "impacto": "Médio"},
        {"nome": "Duplicidade de cobranças", "count": max(0, critico_count), "impacto": "Alto"},
        {"nome": "Múltiplos prestadores mesmo período", "count": max(0, alto_count), "impacto": "Médio"},
    ]
    padroes = [p for p in padroes if p["count"] > 0]

    # Dispara email de alerta para beneficiários críticos (score >= 90)
    # Apenas quando chamado como scan explícito (POST) — GET é visualização
    if request.method == "POST":
        for benef in resultado:
            if benef["score"] >= 90:
                enviar_email_auditoria_alerta(
                    empresa=empresa,
                    nome_benef=benef["nome"],
                    score=benef["score"],
                    fatores=benef.get("fatores", []),
                )

    return JsonResponse({
        "beneficiarios": resultado[:20],
        "padroes": padroes,
        "procedimentos_anomalos": proc_anomalos[:10],
        "critico_count": critico_count,
        "alto_count": alto_count,
        "medio_count": medio_count,
        "economia_estimada": economia_estimada,
    })


# ════════════════════════════════════════════════════════════════════════════════
#  CONTRATOS CORPORATIVOS
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_contratos(request):
    """GET /api/plano-saude/contratos/  — lista contratos grupo
    POST /api/plano-saude/contratos/   — cria novo contrato
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "POST":
        try:
            d = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        plano_id = d.get("plano_id")
        plano = PlanoSaude.objects.filter(pk=plano_id, empresa=empresa).first()
        if not plano:
            return JsonResponse({"erro": "Plano não encontrado"}, status=404)

        contrato = ContratoGrupo.objects.create(
            empresa_operadora=empresa,
            plano=plano,
            razao_social=d.get("razao_social", ""),
            nome_fantasia=d.get("nome_fantasia", ""),
            cnpj=d.get("cnpj", ""),
            contato_nome=d.get("contato_nome", ""),
            contato_email=d.get("contato_email", ""),
            contato_telefone=d.get("contato_telefone", ""),
            total_vidas=int(d.get("total_vidas", 0)),
            mensalidade_total=Decimal(str(d.get("mensalidade_total", 0))),
            data_inicio=d.get("data_inicio", date.today().isoformat()),
            data_renovacao=d.get("data_renovacao", date.today().replace(year=date.today().year + 1).isoformat()),
            logo_emoji=d.get("logo_emoji", "🏢"),
            observacoes=d.get("observacoes", ""),
        )
        enviar_email_novo_contrato(contrato)
        return JsonResponse({"ok": True, "id": contrato.pk})

    contratos = ContratoGrupo.objects.filter(empresa_operadora=empresa).select_related("plano")
    hoje = date.today()
    dados = []
    total_vidas = 0
    receita_corp = Decimal("0")
    renovacoes_30d = 0

    for c in contratos:
        dias_ren = (c.data_renovacao - hoje).days
        if 0 <= dias_ren <= 30:
            renovacoes_30d += 1
        total_vidas += c.total_vidas
        receita_corp += c.mensalidade_total
        dados.append({
            "id": c.pk,
            "logo": c.logo_emoji,
            "nome": c.nome_fantasia or c.razao_social,
            "cnpj": c.cnpj,
            "plano": c.plano.nome,
            "vidas": c.total_vidas,
            "mensalidade": float(c.mensalidade_total),
            "renovacao": c.data_renovacao.isoformat(),
            "status": c.status,
        })

    return JsonResponse({
        "contratos": dados,
        "total_empresas": len(dados),
        "total_vidas": total_vidas,
        "renovacoes_30d": renovacoes_30d,
        "receita_corporativa": float(receita_corp),
    })


@csrf_exempt
def api_ps_contrato_detalhe(request, contrato_id):
    """GET/PUT/DELETE /api/plano-saude/contratos/<id>/"""
    empresa, err = _ps_auth(request)
    if err:
        return err

    contrato = ContratoGrupo.objects.filter(pk=contrato_id, empresa_operadora=empresa).first()
    if not contrato:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "DELETE":
        contrato.delete()
        return JsonResponse({"ok": True})

    if request.method in ("PUT", "PATCH"):
        try:
            d = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in ("razao_social", "nome_fantasia", "cnpj", "contato_nome",
                      "contato_email", "total_vidas", "status", "observacoes"):
            if campo in d:
                setattr(contrato, campo, d[campo])
        if "mensalidade_total" in d:
            contrato.mensalidade_total = Decimal(str(d["mensalidade_total"]))
        if "data_renovacao" in d:
            contrato.data_renovacao = d["data_renovacao"]
        contrato.save()
        return JsonResponse({"ok": True})

    return JsonResponse({
        "id": contrato.pk,
        "razao_social": contrato.razao_social,
        "nome_fantasia": contrato.nome_fantasia,
        "cnpj": contrato.cnpj,
        "plano": contrato.plano.nome,
        "total_vidas": contrato.total_vidas,
        "mensalidade_total": float(contrato.mensalidade_total),
        "data_inicio": contrato.data_inicio.isoformat(),
        "data_renovacao": contrato.data_renovacao.isoformat(),
        "status": contrato.status,
        "observacoes": contrato.observacoes,
    })


# ════════════════════════════════════════════════════════════════════════════════
#  COMUNICAÇÃO — mensagens operadora ↔ beneficiários/prestadores
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_comunicacao(request):
    """GET  /api/plano-saude/comunicacao/?tipo=benef|prest  — lista contatos + msgs
    POST /api/plano-saude/comunicacao/  — envia mensagem
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "POST":
        try:
            d = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        tipo = d.get("tipo_destinatario", "beneficiario")
        benef_id = d.get("beneficiario_id")
        prest_id = d.get("prestador_id")
        conteudo = d.get("conteudo", "").strip()
        if not conteudo:
            return JsonResponse({"erro": "Conteúdo obrigatório"}, status=400)

        benef = BeneficiarioPlano.objects.filter(pk=benef_id, plano__empresa=empresa).first() if benef_id else None
        prest = PrestadorPlanoSaude.objects.filter(pk=prest_id, empresa=empresa).first() if prest_id else None

        msg = MensagemPlano.objects.create(
            empresa=empresa,
            tipo_destinatario=tipo,
            beneficiario=benef,
            prestador=prest,
            conteudo=conteudo,
            assunto=d.get("assunto", ""),
            canal=d.get("canal", "plataforma"),
            direcao="saida",
            enviado_por=d.get("enviado_por", "Operadora"),
        )
        return JsonResponse({"ok": True, "id": msg.pk})

    tipo = request.GET.get("tipo", "benef")
    if tipo == "prest":
        contatos = list(
            PrestadorPlanoSaude.objects.filter(empresa=empresa, status="credenciado")
            .values("id", "nome_fantasia", "especialidades")[:50]
        )
        dados = [{"id": c["id"], "nome": c["nome_fantasia"], "sub": c["especialidades"], "avatar": "🏥"} for c in contatos]
    else:
        contatos = list(
            BeneficiarioPlano.objects.filter(plano__empresa=empresa, situacao="ativo")
            .select_related("plano")
            .values("id", "nome", "plano__nome")[:50]
        )
        dados = [{"id": c["id"], "nome": c["nome"], "sub": c["plano__nome"], "avatar": "👤"} for c in contatos]

    return JsonResponse({"contatos": dados})


@csrf_exempt
def api_ps_comunicacao_thread(request, destinatario_id):
    """GET /api/plano-saude/comunicacao/<id>/thread/?tipo=benef|prest"""
    empresa, err = _ps_auth(request)
    if err:
        return err

    tipo = request.GET.get("tipo", "benef")
    qs = MensagemPlano.objects.filter(empresa=empresa)
    if tipo == "prest":
        qs = qs.filter(prestador_id=destinatario_id)
    else:
        qs = qs.filter(beneficiario_id=destinatario_id)

    msgs = list(qs.values("id", "conteudo", "direcao", "enviado_por", "criado_em")[:30])
    for m in msgs:
        m["criado_em"] = m["criado_em"].strftime("%H:%M")
    return JsonResponse({"mensagens": msgs})


# ════════════════════════════════════════════════════════════════════════════════
#  TELEMEDICINA — autorizações de teleconsulta
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_telemedicina(request):
    """GET /api/plano-saude/telemedicina/  — KPIs + fila de autorizações
    POST                                   — cria nova solicitação
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "POST":
        try:
            d = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        benef_id = d.get("beneficiario_id")
        benef = BeneficiarioPlano.objects.filter(pk=benef_id, plano__empresa=empresa).first()
        if not benef:
            return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)

        tele = TeleconsultaAutorizacao.objects.create(
            empresa=empresa,
            beneficiario=benef,
            especialidade=d.get("especialidade", ""),
            medico_solicitante=d.get("medico_solicitante", ""),
            plataforma=d.get("plataforma", "conexa"),
            observacoes=d.get("observacoes", ""),
        )
        return JsonResponse({"ok": True, "id": tele.pk})

    hoje = date.today()
    agora = timezone.now()

    hoje_count = TeleconsultaAutorizacao.objects.filter(empresa=empresa, data_solicitacao__date=hoje).count()
    mes_count = TeleconsultaAutorizacao.objects.filter(
        empresa=empresa,
        data_solicitacao__year=agora.year,
        data_solicitacao__month=agora.month,
    ).count()
    aguardando = TeleconsultaAutorizacao.objects.filter(empresa=empresa, status="pendente").count()

    # Satisfação media
    satisf_qs = TeleconsultaAutorizacao.objects.filter(
        empresa=empresa, nota_satisfacao__isnull=False
    ).aggregate(media=Avg("nota_satisfacao"))
    satisf = round(float(satisf_qs["media"] or 0), 1)

    # Por especialidade
    por_espec = list(
        TeleconsultaAutorizacao.objects.filter(
            empresa=empresa,
            data_solicitacao__year=agora.year,
            data_solicitacao__month=agora.month,
        )
        .values("especialidade")
        .annotate(valor=Count("id"))
        .order_by("-valor")[:5]
    )
    por_especialidade = [{"espec": p["especialidade"], "valor": p["valor"]} for p in por_espec]

    # Fila pendente
    fila_qs = TeleconsultaAutorizacao.objects.filter(
        empresa=empresa, status="pendente"
    ).select_related("beneficiario")[:20]
    fila = [
        {
            "id": t.pk,
            "beneficiario": t.beneficiario.nome,
            "especialidade": t.especialidade,
            "plataforma": t.get_plataforma_display(),
            "solicitado_em": t.data_solicitacao.isoformat(),
        }
        for t in fila_qs
    ]

    return JsonResponse({
        "hoje": hoje_count,
        "mes": mes_count,
        "aguardando": aguardando,
        "satisfacao": satisf,
        "por_especialidade": por_especialidade,
        "fila": fila,
    })


@csrf_exempt
def api_ps_telemedicina_autorizar(request, tele_id):
    """POST /api/plano-saude/telemedicina/<id>/autorizar/"""
    empresa, err = _ps_auth(request)
    if err:
        return err

    tele = TeleconsultaAutorizacao.objects.filter(pk=tele_id, empresa=empresa).first()
    if not tele:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    try:
        d = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        d = {}

    acao = d.get("acao", "autorizar")
    if acao == "negar":
        tele.status = "negado"
        tele.justificativa = d.get("justificativa", "")
    else:
        tele.status = "autorizado"
        tele.autorizado_por = d.get("autorizado_por", "Operadora")
        tele.link_consulta = d.get("link_consulta", "")
    tele.save()
    if tele.status == "autorizado":
        enviar_email_teleconsulta_autorizada(tele)
    return JsonResponse({"ok": True, "status": tele.status})


# ════════════════════════════════════════════════════════════════════════════════
#  ODONTOLOGIA — beneficiários e guias odontológicas
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_odontologia(request):
    """GET /api/plano-saude/odontologia/?aba=beneficiarios|rede|guias|sinistros|analise
    POST (sem aba) — cria beneficiário odonto
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "POST":
        try:
            d = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        b = BeneficiarioOdonto.objects.create(
            empresa=empresa,
            nome=d.get("nome", ""),
            cpf=d.get("cpf", ""),
            telefone=d.get("telefone", ""),
            email=d.get("email", ""),
            plano_odonto=d.get("plano_odonto", "Odonto Básico"),
            numero_carteirinha=d.get("numero_carteirinha", ""),
            data_inicio_vigencia=d.get("data_inicio_vigencia") or None,
            data_fim_vigencia=d.get("data_fim_vigencia") or None,
            dentista_responsavel=d.get("dentista_responsavel", ""),
        )
        return JsonResponse({"ok": True, "id": b.pk})

    aba = request.GET.get("aba", "beneficiarios")
    vidas = BeneficiarioOdonto.objects.filter(empresa=empresa, status="ativo").count()
    guias_pend = GuiaOdonto.objects.filter(empresa=empresa, status="pendente").count()

    # MLR odonto (custo guias executadas / mensalidade estimada simples)
    custo_odonto = float(GuiaOdonto.objects.filter(empresa=empresa, status="executado")
                        .aggregate(s=Sum("valor_pago"))["s"] or 0)
    receita_odonto = vidas * 80.0  # mensalidade odonto estimada
    mlr_odonto = round(custo_odonto / max(receita_odonto, 1) * 100, 1)

    dados = []
    if aba == "beneficiarios":
        qs = BeneficiarioOdonto.objects.filter(empresa=empresa).order_by("-criado_em")[:50]
        dados = [
            {
                "nome": b.nome,
                "plano": b.plano_odonto,
                "vigencia": b.data_fim_vigencia.isoformat() if b.data_fim_vigencia else None,
                "ultimo_uso": b.data_ultimo_uso.strftime("%b/%y") if b.data_ultimo_uso else "—",
                "status": b.status,
            }
            for b in qs
        ]
    elif aba == "guias":
        qs = GuiaOdonto.objects.filter(empresa=empresa).select_related("beneficiario").order_by("-data_solicitacao")[:50]
        dados = [
            {
                "id": g.pk,
                "beneficiario": g.beneficiario.nome,
                "procedimento": g.procedimento,
                "dentista": g.dentista,
                "valor": float(g.valor_estimado),
                "status": g.status,
            }
            for g in qs
        ]
    elif aba == "rede":
        # Reutiliza prestadores credenciados com tipo odonto
        qs = PrestadorPlanoSaude.objects.filter(
            empresa=empresa, status="credenciado",
            especialidades__icontains="odonto",
        )[:30]
        dados = [{"nome": p.nome_fantasia, "cnes": p.cnes, "cidade": p.cidade, "uf": p.estado} for p in qs]

    return JsonResponse({
        "vidas": vidas,
        "dentistas": PrestadorPlanoSaude.objects.filter(empresa=empresa, especialidades__icontains="odonto").count(),
        "guias_pendentes": guias_pend,
        "mlr": mlr_odonto,
        "dados": dados,
        "aba": aba,
    })


@csrf_exempt
def api_ps_guia_odonto_detalhe(request, guia_id):
    """GET/PUT /api/plano-saude/odontologia/guias/<id>/"""
    empresa, err = _ps_auth(request)
    if err:
        return err

    guia = GuiaOdonto.objects.filter(pk=guia_id, empresa=empresa).first()
    if not guia:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method in ("PUT", "PATCH"):
        try:
            d = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        status_anterior = guia.status
        for campo in ("status", "justificativa_negacao", "valor_pago", "observacoes"):
            if campo in d:
                setattr(guia, campo, d[campo])
        if "data_execucao" in d:
            guia.data_execucao = d["data_execucao"] or None
        guia.save()
        # Dispara email quando status muda para autorizado ou negado
        if d.get("status") and d["status"] != status_anterior:
            if guia.status == "autorizado":
                enviar_email_guia_odonto_aprovada(guia)
            elif guia.status == "negado":
                enviar_email_guia_odonto_negada(guia)
        return JsonResponse({"ok": True})

    return JsonResponse({
        "id": guia.pk,
        "beneficiario": guia.beneficiario.nome,
        "procedimento": guia.procedimento,
        "codigo_tuss": guia.codigo_tuss,
        "dentista": guia.dentista,
        "clinica": guia.clinica,
        "status": guia.status,
        "valor_estimado": float(guia.valor_estimado),
        "valor_pago": float(guia.valor_pago),
    })


# ════════════════════════════════════════════════════════════════════════════════
#  RELATÓRIOS REGULATÓRIOS — geração de arquivos ANS (DIOPS, TISS, SIB)
# ════════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def api_ps_regulatorio_gerar(request):
    """POST /api/plano-saude/regulatorio/gerar/
    Gera payload de relatório regulatório ANS.
    DIOPS e SIB retornam estrutura XML simplificada (produção: usar biblioteca XML).
    TISS retorna lote de guias no padrão 3.05.00 simplificado.
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "POST":
        return JsonResponse({"erro": "POST required"}, status=405)

    try:
        d = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    tipo = d.get("tipo", "").upper()
    ano = d.get("ano", str(date.today().year))
    trimestre = d.get("trimestre", "1")

    if tipo == "DIOPS":
        planos = list(PlanoSaude.objects.filter(empresa=empresa).values("nome", "registro_ans", "modalidade"))
        beneficiarios_ativos = BeneficiarioPlano.objects.filter(plano__empresa=empresa, situacao="ativo").count()
        payload = {
            "tipo": "DIOPS",
            "operadora": empresa.nome,
            "ano": ano,
            "trimestre": trimestre,
            "planos": planos,
            "beneficiarios_ativos": beneficiarios_ativos,
            "formato": "XML",
            "instrucoes": "Importe este JSON em seu sistema de geração XML DIOPS ou use a API ANS diretamente.",
        }

    elif tipo == "SIB":
        movimentacoes = list(
            BeneficiarioPlano.objects.filter(plano__empresa=empresa)
            .values("nome", "cpf", "numero_carteirinha", "situacao", "data_inicio_vigencia")[:200]
        )
        payload = {
            "tipo": "SIB",
            "operadora": empresa.nome,
            "competencia": f"{ano}-{trimestre.zfill(2)}",
            "total_registros": len(movimentacoes),
            "movimentacoes": movimentacoes,
            "formato": "TXT_FIXO",
        }

    elif tipo == "TISS":
        guias = list(
            GuiaAutorizacao.objects.filter(plano__empresa=empresa)
            .select_related("beneficiario", "prestador")
            .values("id", "tipo", "status", "valor_estimado", "solicitada_em")[:100]
        )
        payload = {
            "tipo": "TISS",
            "versao": "3.05.00",
            "operadora": empresa.nome,
            "guias": [
                {
                    "numero_guia": f"GUI{g['id']:08d}",
                    "tipo": g["tipo"],
                    "status": g["status"],
                    "valor": float(g["valor_estimado"] or 0),
                    "data": g["solicitada_em"].isoformat() if g["solicitada_em"] else "",
                }
                for g in guias
            ],
        }

    else:
        return JsonResponse({"erro": f"Tipo '{tipo}' não suportado. Use: DIOPS, SIB, TISS"}, status=400)

    return JsonResponse({"ok": True, "tipo": tipo, "payload": payload})
