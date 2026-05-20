"""
Plano de Saúde — Gestão completa para Operadoras.
Ambiente dedicado: beneficiários, contratos, sinistros,
reembolsos, guias de autorização e mapa epidemiológico.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .access_control import get_setor
from .models import (
    BeneficiarioPlano, Empresa, GuiaAutorizacao,
    PlanoSaude, PrestadorPlanoSaude, Reembolso, Sinistro, RegistroSintoma,
    GlosaItem, CoparticipacaoRegra, FaturamentoBeneficiario,
    ProgramaSaude, InscricaoPrograma,
)
from .views_dashboard import _empresa_autenticada


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

    # Série mensal de sinistros (últimos 6 meses)
    hoje = date.today()
    serie = []
    for i in range(5, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=i * 28)
        mes_inicio = ref.replace(day=1)
        if i == 0:
            mes_fim = hoje
        else:
            prox = (mes_inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
            mes_fim = prox - timedelta(days=1)
        qtd = sinistros_qs.filter(
            data_abertura__date__gte=mes_inicio,
            data_abertura__date__lte=mes_fim,
        ).count()
        valor = sinistros_qs.filter(
            data_abertura__date__gte=mes_inicio,
            data_abertura__date__lte=mes_fim,
            status__in=["aprovado", "pago"],
        ).aggregate(total=Sum("valor_total"))["total"] or 0
        serie.append({
            "mes": mes_inicio.strftime("%b/%y"),
            "sinistros": qtd,
            "valor": float(valor),
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
