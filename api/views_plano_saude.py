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
    PlanoSaude, Reembolso, Sinistro, RegistroSintoma,
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
    return {
        "id": g.id,
        "plano_id": g.plano_id,
        "beneficiario_id": g.beneficiario_id,
        "beneficiario_nome": g.beneficiario.nome,
        "numero_guia": g.numero_guia,
        "tipo": g.tipo,
        "tipo_label": g.get_tipo_display(),
        "status": g.status,
        "status_label": g.get_status_display(),
        "descricao_procedimento": g.descricao_procedimento,
        "cid": g.cid,
        "medico_solicitante": g.medico_solicitante,
        "valor_estimado": float(g.valor_estimado or 0),
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
            "guias_autorizadas_mes": guias_autorizadas_mes,
            "guias_negadas_mes": guias_negadas_mes,
            "sinistros_abertos": sinistros_abertos,
            "sinistros_mes": sinistros_mes,
            "valor_sinistros_mes": float(valor_sinistros_mes),
            "reembolsos_pendentes": reembolsos_pendentes,
            "valor_reembolsos_pagos_mes": float(valor_reembolsos_pagos_mes),
            "registros_epi_30d": registros_30d,
            "suspeitos_epi_30d": suspeitos_30d,
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
def api_ps_guias(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = GuiaAutorizacao.objects.filter(
            plano__empresa=empresa
        ).select_related("plano", "beneficiario")
        plano_id = request.GET.get("plano_id")
        if plano_id:
            qs = qs.filter(plano_id=plano_id)
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
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
        if not data.get("descricao_procedimento"):
            return JsonResponse({"erro": "Descrição do procedimento obrigatória"}, status=400)
        import uuid as _uuid
        valor = None
        if data.get("valor_estimado"):
            try:
                valor = Decimal(str(data["valor_estimado"]))
            except Exception:
                pass
        g = GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            numero_guia=data.get("numero_guia") or f"G{_uuid.uuid4().hex[:8].upper()}",
            tipo=data.get("tipo", "consulta"),
            descricao_procedimento=data["descricao_procedimento"],
            cid=data.get("cid", ""),
            medico_solicitante=data.get("medico_solicitante", ""),
            crm_medico=data.get("crm_medico", ""),
            quantidade=int(data.get("quantidade", 1)),
            valor_estimado=valor,
            status="solicitada",
        )
        return JsonResponse({"guia": _guia_dict(g)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ps_guia_detalhe(request, guia_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        g = GuiaAutorizacao.objects.select_related("plano", "beneficiario").get(
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
        for campo in ["status", "numero_autorizacao", "justificativa_negativa", "cid",
                      "descricao_procedimento", "medico_solicitante"]:
            if campo in data:
                setattr(g, campo, data[campo])
        if "validade_autorizacao" in data and data["validade_autorizacao"]:
            from datetime import datetime
            try:
                g.validade_autorizacao = datetime.strptime(data["validade_autorizacao"], "%Y-%m-%d").date()
            except ValueError:
                pass
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

    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    sinistros_qs = Sinistro.objects.filter(empresa=empresa)
    reembolsos_qs = Reembolso.objects.filter(empresa=empresa)
    guias_qs = GuiaAutorizacao.objects.filter(plano__empresa=empresa)

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

    # Série mensal de sinistros (últimos 6 meses)
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
        "serie_sinistros": serie,
    })
