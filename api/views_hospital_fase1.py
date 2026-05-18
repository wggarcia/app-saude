"""
Hospital — Fase 1: Consolidação + Alta Formal + UTI + Centro Cirúrgico
  • Evoluções clínicas estruturadas por tipo (médico/enfermagem/fisio/nutrição…)
  • Monitoramento UTI com escores SOFA e Glasgow, ventilação mecânica
  • Sumário de Alta formal com receituário e orientações
  • Centro Cirúrgico (agendamento, equipe, relatório cirúrgico)
  • Controle de isolamento/infecção em PacienteInternado
"""
import json
from datetime import datetime, date

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .views_dashboard import _empresa_autenticada
from .models import (
    PacienteInternado, LeitoHospitalar,
    EvolucaoClinicaInternado, MonitoramentoUTI, SumarioAlta, CentroCirurgico,
)


def _pac_or_404(empresa, pac_id):
    try:
        return PacienteInternado.objects.get(pk=pac_id, empresa=empresa)
    except PacienteInternado.DoesNotExist:
        return None


def _evo_to_dict(e):
    return {
        "id": e.id,
        "tipo": e.tipo,
        "descricao": e.descricao,
        "responsavel": e.responsavel,
        "crm_coren": e.crm_coren,
        "sinais_vitais": e.sinais_vitais,
        "registrado_em": e.registrado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _mon_to_dict(m):
    return {
        "id": m.id,
        "registrado_em": m.registrado_em.strftime("%d/%m/%Y %H:%M"),
        "pressao_arterial": m.pressao_arterial,
        "pressao_arterial_media": m.pressao_arterial_media,
        "frequencia_cardiaca": m.frequencia_cardiaca,
        "frequencia_respiratoria": m.frequencia_respiratoria,
        "temperatura": float(m.temperatura) if m.temperatura else None,
        "saturacao_o2": m.saturacao_o2,
        "diurese_ml": m.diurese_ml,
        "glasgow_total": m.glasgow_total,
        "glasgow_ocular": m.glasgow_ocular,
        "glasgow_verbal": m.glasgow_verbal,
        "glasgow_motor": m.glasgow_motor,
        "sofa_total": m.sofa_total,
        "sofa_respiratorio": m.sofa_respiratorio,
        "sofa_coagulacao": m.sofa_coagulacao,
        "sofa_hepatico": m.sofa_hepatico,
        "sofa_cardiovascular": m.sofa_cardiovascular,
        "sofa_neurologico": m.sofa_neurologico,
        "sofa_renal": m.sofa_renal,
        "ventilacao_mecanica": m.ventilacao_mecanica,
        "modo_ventilatorio": m.modo_ventilatorio,
        "fio2_pct": m.fio2_pct,
        "peep": m.peep,
        "volume_corrente_ml": m.volume_corrente_ml,
        "drogas_vasoativas": m.drogas_vasoativas,
        "droga_vasoativa_desc": m.droga_vasoativa_desc,
        "responsavel": m.responsavel,
        "observacoes": m.observacoes,
    }


def _alta_to_dict(a):
    return {
        "id": a.id,
        "paciente_id": a.paciente_id,
        "paciente_nome": a.paciente.nome,
        "tipo_alta": a.tipo_alta,
        "data_alta": a.data_alta.strftime("%d/%m/%Y %H:%M"),
        "medico_responsavel": a.medico_responsavel,
        "medico_crm": a.medico_crm,
        "diagnostico_final": a.diagnostico_final,
        "cid_principal": a.cid_principal,
        "cid_secundarios": a.cid_secundarios,
        "resumo_internacao": a.resumo_internacao,
        "procedimentos_realizados": a.procedimentos_realizados,
        "medicamentos_alta": a.medicamentos_alta,
        "orientacoes_paciente": a.orientacoes_paciente,
        "retorno_previsao": a.retorno_previsao.strftime("%d/%m/%Y") if a.retorno_previsao else None,
        "restricoes_atividade": a.restricoes_atividade,
        "encaminhamentos": a.encaminhamentos,
        "condicao_alta": a.condicao_alta,
        "criado_em": a.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def _cc_to_dict(c):
    duracao = None
    if c.data_hora_inicio and c.data_hora_fim:
        duracao = int((c.data_hora_fim - c.data_hora_inicio).total_seconds() // 60)
    return {
        "id": c.id,
        "paciente_id": c.paciente_id,
        "paciente_nome": c.paciente.nome if c.paciente else "",
        "data_hora_prevista": c.data_hora_prevista.strftime("%d/%m/%Y %H:%M"),
        "data_hora_inicio": c.data_hora_inicio.strftime("%d/%m/%Y %H:%M") if c.data_hora_inicio else None,
        "data_hora_fim": c.data_hora_fim.strftime("%d/%m/%Y %H:%M") if c.data_hora_fim else None,
        "duracao_minutos": duracao,
        "sala": c.sala,
        "procedimento": c.procedimento,
        "codigo_tuss": c.codigo_tuss,
        "porte": c.porte,
        "cirurgiao_principal": c.cirurgiao_principal,
        "cirurgiao_crm": c.cirurgiao_crm,
        "anestesiologista": c.anestesiologista,
        "tipo_anestesia": c.tipo_anestesia,
        "equipe": c.equipe,
        "status": c.status,
        "cid_indicacao": c.cid_indicacao,
        "relatorio_cirurgico": c.relatorio_cirurgico,
        "intercorrencias": c.intercorrencias,
        "sangramento_ml": c.sangramento_ml,
        "criado_em": c.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Evoluções Clínicas Estruturadas ─────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_evolucoes_paciente(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        tipo = request.GET.get("tipo", "")
        qs = pac.evolucoes_estruturadas.all()
        if tipo:
            qs = qs.filter(tipo=tipo)
        return JsonResponse({"evolucoes": [_evo_to_dict(e) for e in qs[:100]]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    descricao = (data.get("descricao") or "").strip()
    if not descricao:
        return JsonResponse({"erro": "descricao é obrigatória"}, status=400)

    evo = EvolucaoClinicaInternado.objects.create(
        paciente=pac,
        tipo=data.get("tipo", "medica"),
        descricao=descricao,
        responsavel=data.get("responsavel", ""),
        crm_coren=data.get("crm_coren", ""),
        sinais_vitais=data.get("sinais_vitais", {}),
    )
    return JsonResponse({"ok": True, "evolucao": _evo_to_dict(evo)}, status=201)


# ─── Monitoramento UTI ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_monitoramento_uti(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        limite = int(request.GET.get("limite", 24))
        qs = pac.monitoramentos_uti.all()[:limite]
        return JsonResponse({"monitoramentos": [_mon_to_dict(m) for m in qs]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    def _int(val):
        try:
            return int(val) if val not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def _dec(val):
        try:
            from decimal import Decimal
            return Decimal(str(val)) if val not in (None, "") else None
        except Exception:
            return None

    mon = MonitoramentoUTI.objects.create(
        paciente=pac,
        pressao_arterial=data.get("pressao_arterial", ""),
        pressao_arterial_media=_int(data.get("pressao_arterial_media")),
        frequencia_cardiaca=_int(data.get("frequencia_cardiaca")),
        frequencia_respiratoria=_int(data.get("frequencia_respiratoria")),
        temperatura=_dec(data.get("temperatura")),
        saturacao_o2=_int(data.get("saturacao_o2")),
        diurese_ml=_int(data.get("diurese_ml")),
        glasgow_ocular=_int(data.get("glasgow_ocular")),
        glasgow_verbal=_int(data.get("glasgow_verbal")),
        glasgow_motor=_int(data.get("glasgow_motor")),
        sofa_respiratorio=_int(data.get("sofa_respiratorio")),
        sofa_coagulacao=_int(data.get("sofa_coagulacao")),
        sofa_hepatico=_int(data.get("sofa_hepatico")),
        sofa_cardiovascular=_int(data.get("sofa_cardiovascular")),
        sofa_neurologico=_int(data.get("sofa_neurologico")),
        sofa_renal=_int(data.get("sofa_renal")),
        ventilacao_mecanica=bool(data.get("ventilacao_mecanica", False)),
        modo_ventilatorio=data.get("modo_ventilatorio", ""),
        fio2_pct=_int(data.get("fio2_pct")),
        peep=_int(data.get("peep")),
        volume_corrente_ml=_int(data.get("volume_corrente_ml")),
        drogas_vasoativas=bool(data.get("drogas_vasoativas", False)),
        droga_vasoativa_desc=data.get("droga_vasoativa_desc", ""),
        responsavel=data.get("responsavel", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"ok": True, "monitoramento": _mon_to_dict(mon)}, status=201)


# ─── Sumário de Alta ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST", "PUT"])
def api_sumario_alta(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        try:
            alta = pac.sumario_alta
            return JsonResponse({"sumario": _alta_to_dict(alta)})
        except SumarioAlta.DoesNotExist:
            return JsonResponse({"sumario": None})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    data_alta_str = data.get("data_alta")
    if not data_alta_str:
        return JsonResponse({"erro": "data_alta é obrigatória"}, status=400)

    try:
        data_alta = datetime.fromisoformat(data_alta_str)
        if not data_alta.tzinfo:
            data_alta = timezone.make_aware(data_alta)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "data_alta inválida (use ISO 8601)"}, status=400)

    retorno_str = data.get("retorno_previsao")
    retorno = None
    if retorno_str:
        try:
            retorno = date.fromisoformat(retorno_str)
        except (ValueError, TypeError):
            pass

    fields = dict(
        tipo_alta=data.get("tipo_alta", "alta_medica"),
        data_alta=data_alta,
        medico_responsavel=data.get("medico_responsavel", ""),
        medico_crm=data.get("medico_crm", ""),
        diagnostico_final=data.get("diagnostico_final", ""),
        cid_principal=data.get("cid_principal", ""),
        cid_secundarios=data.get("cid_secundarios", []),
        resumo_internacao=data.get("resumo_internacao", ""),
        procedimentos_realizados=data.get("procedimentos_realizados", ""),
        medicamentos_alta=data.get("medicamentos_alta", []),
        orientacoes_paciente=data.get("orientacoes_paciente", ""),
        retorno_previsao=retorno,
        restricoes_atividade=data.get("restricoes_atividade", ""),
        encaminhamentos=data.get("encaminhamentos", ""),
        condicao_alta=data.get("condicao_alta", "melhorado"),
    )

    if request.method == "PUT":
        try:
            alta = pac.sumario_alta
            for k, v in fields.items():
                setattr(alta, k, v)
            alta.save()
        except SumarioAlta.DoesNotExist:
            alta = SumarioAlta.objects.create(paciente=pac, **fields)
    else:
        alta, _ = SumarioAlta.objects.update_or_create(paciente=pac, defaults=fields)

    # Dar alta no paciente se tipo_alta não for transferência em andamento
    if data.get("dar_alta", True):
        pac.status = "obito" if fields["tipo_alta"] == "obito" else ("transferido" if fields["tipo_alta"] == "transferencia" else "alta")
        pac.save(update_fields=["status", "atualizado_em"])
        if pac.leito:
            pac.leito.status = "livre"
            pac.leito.paciente_nome = None
            pac.leito.data_internacao = None
            pac.leito.save(update_fields=["status", "paciente_nome", "data_internacao", "atualizado_em"])

    return JsonResponse({"ok": True, "sumario": _alta_to_dict(alta)}, status=201)


# ─── Centro Cirúrgico ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_centro_cirurgico(request):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    if request.method == "GET":
        qs = CentroCirurgico.objects.filter(empresa=empresa).select_related("paciente")

        status = request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)

        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        if data_ini:
            qs = qs.filter(data_hora_prevista__date__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_hora_prevista__date__lte=data_fim)

        return JsonResponse({"cirurgias": [_cc_to_dict(c) for c in qs[:200]]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    procedimento = (data.get("procedimento") or "").strip()
    data_hora_str = data.get("data_hora_prevista")
    if not procedimento or not data_hora_str:
        return JsonResponse({"erro": "procedimento e data_hora_prevista são obrigatórios"}, status=400)

    try:
        data_hora = datetime.fromisoformat(data_hora_str)
        if not data_hora.tzinfo:
            data_hora = timezone.make_aware(data_hora)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "data_hora_prevista inválida"}, status=400)

    pac = None
    pac_id = data.get("paciente_id")
    if pac_id:
        pac = _pac_or_404(empresa, pac_id)

    cc = CentroCirurgico.objects.create(
        empresa=empresa,
        paciente=pac,
        data_hora_prevista=data_hora,
        procedimento=procedimento,
        codigo_tuss=data.get("codigo_tuss", ""),
        sala=data.get("sala", ""),
        porte=data.get("porte", "medio"),
        cirurgiao_principal=data.get("cirurgiao_principal", ""),
        cirurgiao_crm=data.get("cirurgiao_crm", ""),
        anestesiologista=data.get("anestesiologista", ""),
        tipo_anestesia=data.get("tipo_anestesia", ""),
        equipe=data.get("equipe", []),
        cid_indicacao=data.get("cid_indicacao", ""),
        status="agendado",
    )
    return JsonResponse({"ok": True, "cirurgia": _cc_to_dict(cc)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_centro_cirurgico_detalhe(request, cc_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        cc = CentroCirurgico.objects.select_related("paciente").get(pk=cc_id, empresa=empresa)
    except CentroCirurgico.DoesNotExist:
        return JsonResponse({"erro": "Cirurgia não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"cirurgia": _cc_to_dict(cc)})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    campos_editaveis = [
        "status", "sala", "procedimento", "codigo_tuss", "porte",
        "cirurgiao_principal", "cirurgiao_crm", "anestesiologista", "tipo_anestesia",
        "equipe", "cid_indicacao", "relatorio_cirurgico", "intercorrencias", "sangramento_ml",
    ]
    for campo in campos_editaveis:
        if campo in data:
            setattr(cc, campo, data[campo])

    for dt_campo in ["data_hora_inicio", "data_hora_fim"]:
        val = data.get(dt_campo)
        if val:
            try:
                dt = datetime.fromisoformat(val)
                if not dt.tzinfo:
                    dt = timezone.make_aware(dt)
                setattr(cc, dt_campo, dt)
            except (ValueError, TypeError):
                pass

    cc.save()
    return JsonResponse({"ok": True, "cirurgia": _cc_to_dict(cc)})


# ─── Dashboard UTI ────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_hospital_uti_dashboard(request):
    """KPIs e lista de pacientes em UTI com últimos escores SOFA/Glasgow."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pacientes_uti = PacienteInternado.objects.filter(
        empresa=empresa, status="internado",
        leito__tipo="uti",
    ).select_related("leito")

    resultado = []
    for p in pacientes_uti:
        ultimo_mon = p.monitoramentos_uti.first()
        resultado.append({
            "id": p.id,
            "nome": p.nome,
            "leito": p.leito.numero if p.leito else "",
            "data_internacao": p.data_internacao.strftime("%d/%m/%Y"),
            "dias_uti": (date.today() - p.data_internacao).days,
            "diagnostico": p.diagnostico_cid,
            "ventilacao_mecanica": ultimo_mon.ventilacao_mecanica if ultimo_mon else False,
            "drogas_vasoativas": ultimo_mon.drogas_vasoativas if ultimo_mon else False,
            "sofa_total": ultimo_mon.sofa_total if ultimo_mon else None,
            "glasgow_total": ultimo_mon.glasgow_total if ultimo_mon else None,
            "saturacao_o2": ultimo_mon.saturacao_o2 if ultimo_mon else None,
            "pa": ultimo_mon.pressao_arterial if ultimo_mon else "",
            "ultimo_registro": ultimo_mon.registrado_em.strftime("%d/%m %H:%M") if ultimo_mon else None,
            "tipo_isolamento": p.tipo_isolamento,
        })

    em_ventilacao = sum(1 for p in resultado if p["ventilacao_mecanica"])
    em_vasoativos = sum(1 for p in resultado if p["drogas_vasoativas"])
    sofa_alto = sum(1 for p in resultado if p["sofa_total"] is not None and p["sofa_total"] >= 8)

    return JsonResponse({
        "total_uti": len(resultado),
        "em_ventilacao_mecanica": em_ventilacao,
        "em_drogas_vasoativas": em_vasoativos,
        "sofa_alto_risco": sofa_alto,
        "pacientes": resultado,
    })


# ─── Controle de Isolamento ───────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def api_isolamento_paciente(request, pac_id):
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    pac = _pac_or_404(empresa, pac_id)
    if not pac:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "paciente_id": pac.id,
            "nome": pac.nome,
            "tipo_isolamento": pac.tipo_isolamento,
            "motivo_isolamento": pac.motivo_isolamento,
        })

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    pac.tipo_isolamento = data.get("tipo_isolamento", pac.tipo_isolamento)
    pac.motivo_isolamento = data.get("motivo_isolamento", pac.motivo_isolamento)
    pac.save(update_fields=["tipo_isolamento", "motivo_isolamento", "atualizado_em"])

    return JsonResponse({"ok": True, "tipo_isolamento": pac.tipo_isolamento})
