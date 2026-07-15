"""
views_governo_fase2.py
Fase 2 do módulo de gestão governamental de saúde pública.
Todos os endpoints exigem autenticação via _empresa_autenticada.
"""
import json
import uuid
from datetime import date, timedelta
from django.db.models import Sum, Count, Avg, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_plataforma_ti, get_setor, principal_pode_operacao_setorial,
    api_requer_permissao_modulo,
)
from .models import (
    UnidadeSaude, EquipeSaude,
    NotificacaoCompulsoria, SurtoEpidemiologico,
    RegulacaoLeito, ProducaoAmbulatorial,
    MetaPrevine, ContratoGestao, AtendimentoUrgencia,
    ApiKeyEmpresa, UsoApiEmpresa, SubscricaoEvento,
    AuditoriaInstitucional, EmpresaUsuario,
)
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base


def _empresa_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


def _e(req):
    return _empresa_autenticada(req)


def _unidade_dict(u):
    return {
        "id": u.id, "cnes": u.cnes, "nome": u.nome,
        "tipo": u.tipo, "tipo_label": u.get_tipo_display(),
        "status": u.status, "status_label": u.get_status_display(),
        "municipio": u.municipio, "uf": u.uf, "bairro": u.bairro,
        "endereco": u.endereco, "telefone": u.telefone,
        "latitude": str(u.latitude) if u.latitude is not None else "",
        "longitude": str(u.longitude) if u.longitude is not None else "",
        "populacao_referenciada": u.populacao_referenciada,
        "leitos_sus": u.leitos_sus, "leitos_uti": u.leitos_uti,
        "diretor": u.diretor,
        "criado_em": u.criado_em.isoformat(),
        "atualizado_em": u.atualizado_em.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# REDE DE SAÚDE
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_unidades_saude(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = UnidadeSaude.objects.filter(empresa=e)
        tipo = request.GET.get("tipo")
        status = request.GET.get("status")
        municipio = request.GET.get("municipio")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if status:
            qs = qs.filter(status=status)
        if municipio:
            qs = qs.filter(municipio__icontains=municipio)
        return JsonResponse({"unidades": [_unidade_dict(u) for u in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("nome") or not data.get("tipo") or not data.get("municipio"):
        return JsonResponse({"erro": "nome, tipo e municipio são obrigatórios"}, status=400)
    u = UnidadeSaude.objects.create(
        empresa=e,
        cnes=data.get("cnes", ""),
        nome=data["nome"],
        tipo=data["tipo"],
        status=data.get("status", "ativa"),
        municipio=data["municipio"],
        uf=data.get("uf", ""),
        bairro=data.get("bairro", ""),
        endereco=data.get("endereco", ""),
        telefone=data.get("telefone", ""),
        latitude=data.get("latitude") or None,
        longitude=data.get("longitude") or None,
        populacao_referenciada=data.get("populacao_referenciada", 0),
        leitos_sus=data.get("leitos_sus", 0),
        leitos_uti=data.get("leitos_uti", 0),
        diretor=data.get("diretor", ""),
    )
    return JsonResponse(_unidade_dict(u), status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
@api_requer_permissao_modulo("governo.administrativo")
def api_unidade_saude_detalhe(request, unidade_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        u = UnidadeSaude.objects.get(pk=unidade_id, empresa=e)
    except UnidadeSaude.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        d = _unidade_dict(u)
        d["equipes"] = list(u.equipes.filter(ativa=True).values(
            "id", "nome", "tipo", "ine", "area_codigo", "populacao_cadastrada", "ativa"
        ))
        return JsonResponse(d)

    if request.method == "DELETE":
        u.delete()
        return JsonResponse({"ok": True})

    data = json.loads(request.body or "{}")
    campos = ["cnes","nome","tipo","status","municipio","uf","bairro","endereco",
              "telefone","populacao_referenciada","leitos_sus","leitos_uti","diretor"]
    nullable = {"latitude","longitude"}
    for campo in campos:
        if campo in data:
            setattr(u, campo, data[campo])
    for campo in nullable:
        if campo in data:
            setattr(u, campo, data[campo] or None)
    u.save()
    return JsonResponse(_unidade_dict(u))


@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_equipes_saude(request, unidade_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        unidade = UnidadeSaude.objects.get(pk=unidade_id, empresa=e)
    except UnidadeSaude.DoesNotExist:
        return JsonResponse({"erro": "Unidade não encontrada"}, status=404)

    if request.method == "GET":
        qs = EquipeSaude.objects.filter(unidade=unidade)
        return JsonResponse({"equipes": list(qs.values(
            "id","nome","tipo","ine","area_codigo","populacao_cadastrada","ativa","criado_em"
        ))})

    data = json.loads(request.body or "{}")
    eq = EquipeSaude.objects.create(
        empresa=e, unidade=unidade,
        nome=data.get("nome",""),
        tipo=data.get("tipo","esf"),
        ine=data.get("ine",""),
        area_codigo=data.get("area_codigo",""),
        populacao_cadastrada=data.get("populacao_cadastrada",0),
        ativa=data.get("ativa",True),
    )
    return JsonResponse({"id": eq.id, "nome": eq.nome}, status=201)


# ═══════════════════════════════════════════════════════════════
# VIGILÂNCIA EPIDEMIOLÓGICA
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_notificacoes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = NotificacaoCompulsoria.objects.filter(empresa=e).select_related("unidade_notificante","surto")
        doenca = request.GET.get("doenca")
        status_inv = request.GET.get("status_investigacao")
        municipio = request.GET.get("municipio")
        data_inicio = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        if doenca:
            qs = qs.filter(doenca=doenca)
        if status_inv:
            qs = qs.filter(status_investigacao=status_inv)
        if municipio:
            qs = qs.filter(municipio_notificacao__icontains=municipio)
        if data_inicio:
            qs = qs.filter(data_notificacao__gte=data_inicio)
        if data_fim:
            qs = qs.filter(data_notificacao__lte=data_fim)
        return JsonResponse({"notificacoes": [{
            "id": n.id,
            "doenca": n.doenca, "doenca_label": n.get_doenca_display(),
            "data_notificacao": str(n.data_notificacao),
            "data_inicio_sintomas": str(n.data_inicio_sintomas) if n.data_inicio_sintomas else "",
            "municipio_notificacao": n.municipio_notificacao,
            "uf_notificacao": n.uf_notificacao,
            "unidade_notificante_id": n.unidade_notificante_id,
            "unidade_notificante_nome": n.unidade_notificante.nome if n.unidade_notificante else "",
            "idade_paciente": n.idade_paciente,
            "sexo": n.sexo, "zona": n.zona,
            "status_investigacao": n.status_investigacao,
            "evolucao": n.evolucao, "evolucao_label": n.get_evolucao_display(),
            "surto_id": n.surto_id,
            "observacoes": n.observacoes,
            "criado_em": n.criado_em.isoformat(),
        } for n in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("doenca") or not data.get("data_notificacao") or not data.get("municipio_notificacao"):
        return JsonResponse({"erro": "doenca, data_notificacao e municipio_notificacao são obrigatórios"}, status=400)
    n = NotificacaoCompulsoria.objects.create(
        empresa=e,
        doenca=data["doenca"],
        data_notificacao=data["data_notificacao"],
        data_inicio_sintomas=data.get("data_inicio_sintomas") or None,
        municipio_notificacao=data["municipio_notificacao"],
        uf_notificacao=data.get("uf_notificacao",""),
        unidade_notificante_id=data.get("unidade_notificante_id") or None,
        idade_paciente=data.get("idade_paciente") or None,
        sexo=data.get("sexo","I"),
        zona=data.get("zona","urbana"),
        status_investigacao=data.get("status_investigacao","aberto"),
        evolucao=data.get("evolucao","ativo"),
        surto_id=data.get("surto_id") or None,
        observacoes=data.get("observacoes",""),
    )
    return JsonResponse({"id": n.id}, status=201)


@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_surtos(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = SurtoEpidemiologico.objects.filter(empresa=e)
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return JsonResponse({"surtos": [{
            "id": s.id, "doenca": s.doenca,
            "municipio": s.municipio, "uf": s.uf, "bairro": s.bairro,
            "data_inicio": str(s.data_inicio),
            "data_encerramento": str(s.data_encerramento) if s.data_encerramento else "",
            "total_casos": s.total_casos, "total_obitos": s.total_obitos,
            "status": s.status, "status_label": s.get_status_display(),
            "nivel_alerta": s.nivel_alerta,
            "acoes_resposta": s.acoes_resposta,
            "responsavel_investigacao": s.responsavel_investigacao,
            "total_notificacoes": s.notificacoes.count(),
            "criado_em": s.criado_em.isoformat(),
        } for s in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("doenca") or not data.get("municipio") or not data.get("data_inicio"):
        return JsonResponse({"erro": "doenca, municipio e data_inicio são obrigatórios"}, status=400)
    s = SurtoEpidemiologico.objects.create(
        empresa=e,
        doenca=data["doenca"],
        municipio=data["municipio"],
        uf=data.get("uf",""),
        bairro=data.get("bairro",""),
        data_inicio=data["data_inicio"],
        data_encerramento=data.get("data_encerramento") or None,
        total_casos=data.get("total_casos",0),
        total_obitos=data.get("total_obitos",0),
        status=data.get("status","ativo"),
        nivel_alerta=data.get("nivel_alerta","amarelo"),
        acoes_resposta=data.get("acoes_resposta",""),
        responsavel_investigacao=data.get("responsavel_investigacao",""),
    )
    return JsonResponse({"id": s.id}, status=201)


@require_http_methods(["GET", "PUT"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_surto_detalhe(request, surto_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        s = SurtoEpidemiologico.objects.get(pk=surto_id, empresa=e)
    except SurtoEpidemiologico.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": s.id, "doenca": s.doenca,
            "municipio": s.municipio, "uf": s.uf, "bairro": s.bairro,
            "data_inicio": str(s.data_inicio),
            "data_encerramento": str(s.data_encerramento) if s.data_encerramento else "",
            "total_casos": s.total_casos, "total_obitos": s.total_obitos,
            "status": s.status, "nivel_alerta": s.nivel_alerta,
            "acoes_resposta": s.acoes_resposta,
            "responsavel_investigacao": s.responsavel_investigacao,
        })

    data = json.loads(request.body or "{}")
    nullable = {"data_encerramento"}
    for campo in ["doenca","municipio","uf","bairro","data_inicio","data_encerramento",
                  "total_casos","total_obitos","status","nivel_alerta","acoes_resposta","responsavel_investigacao"]:
        if campo in data:
            setattr(s, campo, data[campo] or None if campo in nullable else data[campo])
    s.save()
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.vigilancia_acs", "governo.epidemiologia")
def api_vigilancia_dashboard(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    trinta_dias_atras = hoje - timedelta(days=30)

    # Contagens por doença (últimos 30 dias)
    por_doenca = list(
        NotificacaoCompulsoria.objects
        .filter(empresa=e, data_notificacao__gte=trinta_dias_atras)
        .values("doenca")
        .annotate(total=Count("id"))
        .order_by("-total")[:15]
    )
    for item in por_doenca:
        item["doenca_label"] = dict(NotificacaoCompulsoria.DOENCA_CHOICES).get(item["doenca"], item["doenca"])

    surtos_ativos = SurtoEpidemiologico.objects.filter(empresa=e, status="ativo")
    surtos_list = [{
        "id": s.id, "doenca": s.doenca, "municipio": s.municipio, "uf": s.uf,
        "total_casos": s.total_casos, "total_obitos": s.total_obitos,
        "nivel_alerta": s.nivel_alerta, "data_inicio": str(s.data_inicio),
    } for s in surtos_ativos]

    # Tendência últimos 30 dias agrupada por semana
    from django.db.models.functions import TruncWeek
    tendencia = list(
        NotificacaoCompulsoria.objects
        .filter(empresa=e, data_notificacao__gte=trinta_dias_atras)
        .annotate(semana=TruncWeek("data_notificacao"))
        .values("semana")
        .annotate(total=Count("id"))
        .order_by("semana")
    )
    for t in tendencia:
        t["semana"] = str(t["semana"]) if t["semana"] else ""

    # Por município
    por_municipio = list(
        NotificacaoCompulsoria.objects
        .filter(empresa=e, data_notificacao__gte=trinta_dias_atras)
        .values("municipio_notificacao","uf_notificacao")
        .annotate(total=Count("id"))
        .order_by("-total")[:20]
    )

    total_notif_30d = NotificacaoCompulsoria.objects.filter(
        empresa=e, data_notificacao__gte=trinta_dias_atras
    ).count()
    total_obitos_notif = NotificacaoCompulsoria.objects.filter(
        empresa=e, evolucao="obito"
    ).count()

    return JsonResponse({
        "total_notificacoes_30d": total_notif_30d,
        "total_obitos_notificacoes": total_obitos_notif,
        "surtos_ativos": len(surtos_list),
        "surtos_vermelho": surtos_ativos.filter(nivel_alerta="vermelho").count(),
        "surtos": surtos_list,
        "por_doenca": por_doenca,
        "tendencia_semanal": tendencia,
        "por_municipio": por_municipio,
    })


# ═══════════════════════════════════════════════════════════════
# REGULAÇÃO DE LEITOS
# ═══════════════════════════════════════════════════════════════

def _reg_dict(r):
    return {
        "id": r.id,
        "numero_solicitacao": r.numero_solicitacao,
        "unidade_origem_id": r.unidade_origem_id,
        "unidade_origem_nome": r.unidade_origem.nome if r.unidade_origem else "",
        "unidade_destino_id": r.unidade_destino_id,
        "unidade_destino_nome": r.unidade_destino.nome if r.unidade_destino else "",
        "tipo_leito": r.tipo_leito, "tipo_leito_label": r.get_tipo_leito_display(),
        "prioridade": r.prioridade, "prioridade_label": r.get_prioridade_display(),
        "status": r.status, "status_label": r.get_status_display(),
        "cid_principal": r.cid_principal, "diagnostico": r.diagnostico,
        "idade_paciente": r.idade_paciente,
        "municipio_origem": r.municipio_origem,
        "medico_solicitante": r.medico_solicitante,
        "data_solicitacao": r.data_solicitacao.isoformat(),
        "data_regulacao": r.data_regulacao.isoformat() if r.data_regulacao else "",
        "data_internacao": r.data_internacao.isoformat() if r.data_internacao else "",
        "tempo_espera_horas": str(r.tempo_espera_horas) if r.tempo_espera_horas is not None else "",
        "observacoes": r.observacoes,
    }


def _gerar_numero_solicitacao():
    return f"REG{date.today().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"


@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_regulacao_leitos(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = RegulacaoLeito.objects.filter(empresa=e).select_related("unidade_origem","unidade_destino")
        status = request.GET.get("status")
        tipo = request.GET.get("tipo_leito")
        prioridade = request.GET.get("prioridade")
        if status:
            qs = qs.filter(status=status)
        if tipo:
            qs = qs.filter(tipo_leito=tipo)
        if prioridade:
            qs = qs.filter(prioridade=prioridade)
        return JsonResponse({"regulacoes": [_reg_dict(r) for r in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("tipo_leito"):
        return JsonResponse({"erro": "tipo_leito é obrigatório"}, status=400)
    r = RegulacaoLeito.objects.create(
        empresa=e,
        numero_solicitacao=_gerar_numero_solicitacao(),
        unidade_origem_id=data.get("unidade_origem_id") or None,
        unidade_destino_id=data.get("unidade_destino_id") or None,
        tipo_leito=data["tipo_leito"],
        prioridade=data.get("prioridade","urgencia"),
        status=data.get("status","solicitado"),
        cid_principal=data.get("cid_principal",""),
        diagnostico=data.get("diagnostico",""),
        idade_paciente=data.get("idade_paciente") or None,
        municipio_origem=data.get("municipio_origem",""),
        medico_solicitante=data.get("medico_solicitante",""),
        observacoes=data.get("observacoes",""),
    )
    return JsonResponse(_reg_dict(r), status=201)


@require_http_methods(["GET", "PATCH"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_regulacao_detalhe(request, regulacao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        r = RegulacaoLeito.objects.select_related("unidade_origem","unidade_destino").get(pk=regulacao_id, empresa=e)
    except RegulacaoLeito.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_reg_dict(r))

    data = json.loads(request.body or "{}")
    campos_simples = ["tipo_leito","prioridade","cid_principal","diagnostico",
                      "municipio_origem","medico_solicitante","observacoes"]
    nullable_fk = ["unidade_origem_id","unidade_destino_id"]
    nullable_dt = ["data_regulacao","data_internacao"]
    nullable_dec = ["tempo_espera_horas","idade_paciente"]

    for campo in campos_simples:
        if campo in data:
            setattr(r, campo, data[campo])
    for campo in nullable_fk:
        if campo in data:
            setattr(r, campo, data[campo] or None)
    if "status" in data:
        r.status = data["status"]
        if data["status"] == "regulado" and not r.data_regulacao:
            r.data_regulacao = timezone.now()
        elif data["status"] == "internado" and not r.data_internacao:
            r.data_internacao = timezone.now()
            if r.data_regulacao:
                delta = (r.data_internacao - r.data_regulacao).total_seconds() / 3600
                r.tempo_espera_horas = round(delta, 1)
    for campo in nullable_dt:
        if campo in data:
            setattr(r, campo, data[campo] or None)
    for campo in nullable_dec:
        if campo in data:
            setattr(r, campo, data[campo] or None)
    r.save()
    return JsonResponse(_reg_dict(r))


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_regulacao_dashboard(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    qs = RegulacaoLeito.objects.filter(empresa=e)

    por_tipo = {}
    for tipo, label in RegulacaoLeito.TIPO_LEITO_CHOICES:
        sub = qs.filter(tipo_leito=tipo)
        por_tipo[tipo] = {
            "label": label,
            "solicitado": sub.filter(status="solicitado").count(),
            "regulado": sub.filter(status="regulado").count(),
            "internado": sub.filter(status="internado").count(),
            "cancelado": sub.filter(status="cancelado").count(),
        }

    tempo_medio = qs.filter(
        tempo_espera_horas__isnull=False
    ).aggregate(media=Avg("tempo_espera_horas"))["media"]

    por_prioridade = {
        p: qs.filter(prioridade=p, status__in=["solicitado","regulado"]).count()
        for p, _ in RegulacaoLeito.PRIORIDADE_CHOICES
    }

    return JsonResponse({
        "total_solicitacoes": qs.count(),
        "aguardando_vaga": qs.filter(status="regulado").count(),
        "internados_hoje": qs.filter(status="internado").count(),
        "obitos_fila": qs.filter(status="obito_espera").count(),
        "tempo_medio_espera_horas": float(round(tempo_medio, 1)) if tempo_medio else 0,
        "por_tipo_leito": por_tipo,
        "por_prioridade": por_prioridade,
    })


# ═══════════════════════════════════════════════════════════════
# PRODUÇÃO AMBULATORIAL
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_producao_ambulatorial(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = ProducaoAmbulatorial.objects.filter(empresa=e).select_related("unidade")
        competencia = request.GET.get("competencia")
        unidade_id = request.GET.get("unidade_id")
        if competencia:
            qs = qs.filter(competencia=competencia)
        if unidade_id:
            qs = qs.filter(unidade_id=unidade_id)
        return JsonResponse({"producoes": [{
            "id": p.id,
            "unidade_id": p.unidade_id,
            "unidade_nome": p.unidade.nome,
            "competencia": p.competencia,
            "consultas_basicas": p.consultas_basicas,
            "consultas_especializadas": p.consultas_especializadas,
            "procedimentos_basicos": p.procedimentos_basicos,
            "procedimentos_especializados": p.procedimentos_especializados,
            "exames_realizados": p.exames_realizados,
            "visitas_domiciliares": p.visitas_domiciliares,
            "acolhimentos": p.acolhimentos,
            "total_procedimentos": (
                p.consultas_basicas + p.consultas_especializadas +
                p.procedimentos_basicos + p.procedimentos_especializados +
                p.exames_realizados
            ),
            "atualizado_em": p.atualizado_em.isoformat(),
        } for p in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("unidade_id") or not data.get("competencia"):
        return JsonResponse({"erro": "unidade_id e competencia são obrigatórios"}, status=400)
    try:
        unidade = UnidadeSaude.objects.get(pk=data["unidade_id"], empresa=e)
    except UnidadeSaude.DoesNotExist:
        return JsonResponse({"erro": "Unidade não encontrada"}, status=404)

    p, created = ProducaoAmbulatorial.objects.update_or_create(
        empresa=e, unidade=unidade, competencia=data["competencia"],
        defaults={
            "consultas_basicas": data.get("consultas_basicas", 0),
            "consultas_especializadas": data.get("consultas_especializadas", 0),
            "procedimentos_basicos": data.get("procedimentos_basicos", 0),
            "procedimentos_especializados": data.get("procedimentos_especializados", 0),
            "exames_realizados": data.get("exames_realizados", 0),
            "visitas_domiciliares": data.get("visitas_domiciliares", 0),
            "acolhimentos": data.get("acolhimentos", 0),
        }
    )
    return JsonResponse({"id": p.id, "created": created}, status=201 if created else 200)


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_producao_dashboard(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    qs = ProducaoAmbulatorial.objects.filter(empresa=e)

    # Totais por competência (últimas 12)
    por_competencia = list(
        qs.values("competencia")
        .annotate(
            consultas=Sum("consultas_basicas") + Sum("consultas_especializadas"),
            procedimentos=Sum("procedimentos_basicos") + Sum("procedimentos_especializados"),
            exames=Sum("exames_realizados"),
            visitas=Sum("visitas_domiciliares"),
        )
        .order_by("-competencia")[:12]
    )

    # Ranking das unidades pela competência mais recente
    competencia_atual = qs.values_list("competencia", flat=True).order_by("-competencia").first()
    ranking = []
    if competencia_atual:
        ranking = list(
            qs.filter(competencia=competencia_atual)
            .select_related("unidade")
            .annotate(
                total=Sum("consultas_basicas") + Sum("consultas_especializadas") +
                      Sum("procedimentos_basicos") + Sum("procedimentos_especializados") +
                      Sum("exames_realizados")
            )
            .order_by("-total")[:10]
            .values("unidade__nome","unidade__tipo",
                    "consultas_basicas","consultas_especializadas",
                    "procedimentos_basicos","procedimentos_especializados","exames_realizados")
        )

    totais_gerais = qs.aggregate(
        total_consultas=Sum("consultas_basicas"),
        total_consultas_esp=Sum("consultas_especializadas"),
        total_proc=Sum("procedimentos_basicos"),
        total_exames=Sum("exames_realizados"),
        total_visitas=Sum("visitas_domiciliares"),
    )

    return JsonResponse({
        "competencia_atual": competencia_atual or "",
        "por_competencia": por_competencia,
        "ranking_unidades": ranking,
        "totais_gerais": {k: (v or 0) for k, v in totais_gerais.items()},
    })


# ═══════════════════════════════════════════════════════════════
# PREVINE BRASIL
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_metas_previne(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = MetaPrevine.objects.filter(empresa=e)
        competencia = request.GET.get("competencia")
        indicador = request.GET.get("indicador")
        municipio = request.GET.get("municipio")
        if competencia:
            qs = qs.filter(competencia=competencia)
        if indicador:
            qs = qs.filter(indicador=indicador)
        if municipio:
            qs = qs.filter(municipio__icontains=municipio)
        return JsonResponse({"metas": [{
            "id": m.id,
            "indicador": m.indicador, "indicador_label": m.get_indicador_display(),
            "competencia": m.competencia, "municipio": m.municipio,
            "denominador": m.denominador, "numerador": m.numerador,
            "meta_percentual": str(m.meta_percentual),
            "resultado_percentual": str(m.resultado_percentual),
            "atingiu_meta": m.atingiu_meta,
            "criado_em": m.criado_em.isoformat(),
        } for m in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("indicador") or not data.get("competencia"):
        return JsonResponse({"erro": "indicador e competencia são obrigatórios"}, status=400)

    numerador = int(data.get("numerador", 0))
    denominador = int(data.get("denominador", 0))
    meta_pct = float(data.get("meta_percentual", 0))
    resultado_pct = round((numerador / denominador * 100), 2) if denominador > 0 else 0.0
    atingiu = resultado_pct >= meta_pct

    m, _ = MetaPrevine.objects.update_or_create(
        empresa=e,
        indicador=data["indicador"],
        competencia=data["competencia"],
        municipio=data.get("municipio", ""),
        defaults={
            "denominador": denominador,
            "numerador": numerador,
            "meta_percentual": meta_pct,
            "resultado_percentual": resultado_pct,
            "atingiu_meta": atingiu,
        }
    )
    return JsonResponse({"id": m.id, "resultado_percentual": resultado_pct, "atingiu_meta": atingiu}, status=201)


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_previne_dashboard(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    qs = MetaPrevine.objects.filter(empresa=e)
    competencia = request.GET.get("competencia")
    if not competencia:
        competencia = qs.values_list("competencia", flat=True).order_by("-competencia").first()

    qs_atual = qs.filter(competencia=competencia) if competencia else qs.none()

    por_indicador = []
    for ind, label in MetaPrevine.INDICADOR_CHOICES:
        sub = qs_atual.filter(indicador=ind)
        total = sub.count()
        atingiram = sub.filter(atingiu_meta=True).count()
        media_resultado = sub.aggregate(m=Avg("resultado_percentual"))["m"] or 0
        media_meta = sub.aggregate(m=Avg("meta_percentual"))["m"] or 0
        por_indicador.append({
            "indicador": ind, "label": label,
            "total_municipios": total,
            "atingiram_meta": atingiram,
            "percentual_atingimento": round(atingiram / total * 100, 1) if total > 0 else 0,
            "media_resultado": float(round(media_resultado, 1)),
            "media_meta": float(round(media_meta, 1)),
        })

    total_metas = qs_atual.count()
    total_atingidas = qs_atual.filter(atingiu_meta=True).count()
    score_geral = round(total_atingidas / total_metas * 100, 1) if total_metas > 0 else 0

    # Comparativo trimestral — 2 competências anteriores
    competencias_recentes = list(
        qs.values_list("competencia", flat=True)
        .distinct().order_by("-competencia")[:3]
    )
    comparativo = []
    for comp in competencias_recentes:
        sub = qs.filter(competencia=comp)
        total_sub = sub.count()
        ating_sub = sub.filter(atingiu_meta=True).count()
        comparativo.append({
            "competencia": comp,
            "score": round(ating_sub / total_sub * 100, 1) if total_sub > 0 else 0,
            "total": total_sub, "atingidas": ating_sub,
        })

    return JsonResponse({
        "competencia": competencia or "",
        "score_geral": score_geral,
        "total_metas": total_metas,
        "total_atingidas": total_atingidas,
        "por_indicador": por_indicador,
        "comparativo_trimestral": comparativo,
    })


# ═══════════════════════════════════════════════════════════════
# CONTRATOS DE GESTÃO
# ═══════════════════════════════════════════════════════════════

def _contrato_dict(c):
    return {
        "id": c.id,
        "numero_contrato": c.numero_contrato,
        "fornecedor_nome": c.fornecedor_nome,
        "fornecedor_cnpj": c.fornecedor_cnpj,
        "tipo": c.tipo, "tipo_label": c.get_tipo_display(),
        "status": c.status, "status_label": c.get_status_display(),
        "objeto": c.objeto,
        "valor_total": str(c.valor_total),
        "valor_mensal": str(c.valor_mensal),
        "data_inicio": str(c.data_inicio),
        "data_fim": str(c.data_fim),
        "gestor_contrato": c.gestor_contrato,
        "producao_prevista": c.producao_prevista,
        "producao_realizada": c.producao_realizada,
        "observacoes": c.observacoes,
        "criado_em": c.criado_em.isoformat(),
        "atualizado_em": c.atualizado_em.isoformat(),
        "vencido": c.data_fim < date.today() and c.status == "vigente",
        "dias_para_vencer": (c.data_fim - date.today()).days,
    }


@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo")
def api_contratos_gestao(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = ContratoGestao.objects.filter(empresa=e)
        status = request.GET.get("status")
        tipo = request.GET.get("tipo")
        if status:
            qs = qs.filter(status=status)
        if tipo:
            qs = qs.filter(tipo=tipo)
        return JsonResponse({"contratos": [_contrato_dict(c) for c in qs]})

    data = json.loads(request.body or "{}")
    required = ["numero_contrato","fornecedor_nome","tipo","objeto","data_inicio","data_fim"]
    for field in required:
        if not data.get(field):
            return JsonResponse({"erro": f"{field} é obrigatório"}, status=400)

    c = ContratoGestao.objects.create(
        empresa=e,
        numero_contrato=data["numero_contrato"],
        fornecedor_nome=data["fornecedor_nome"],
        fornecedor_cnpj=data.get("fornecedor_cnpj",""),
        tipo=data["tipo"],
        status=data.get("status","vigente"),
        objeto=data["objeto"],
        valor_total=data.get("valor_total",0) or 0,
        valor_mensal=data.get("valor_mensal",0) or 0,
        data_inicio=data["data_inicio"],
        data_fim=data["data_fim"],
        gestor_contrato=data.get("gestor_contrato",""),
        producao_prevista=data.get("producao_prevista",{}),
        producao_realizada=data.get("producao_realizada",{}),
        observacoes=data.get("observacoes",""),
    )
    return JsonResponse(_contrato_dict(c), status=201)


@require_http_methods(["GET", "PUT"])
@api_requer_permissao_modulo("governo.administrativo")
def api_contrato_detalhe(request, contrato_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        c = ContratoGestao.objects.get(pk=contrato_id, empresa=e)
    except ContratoGestao.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_contrato_dict(c))

    data = json.loads(request.body or "{}")
    for campo in ["numero_contrato","fornecedor_nome","fornecedor_cnpj","tipo","status",
                  "objeto","valor_total","valor_mensal","data_inicio","data_fim",
                  "gestor_contrato","producao_prevista","producao_realizada","observacoes"]:
        if campo in data:
            setattr(c, campo, data[campo])
    c.save()
    return JsonResponse(_contrato_dict(c))


# ═══════════════════════════════════════════════════════════════
# URGÊNCIA E EMERGÊNCIA
# ═══════════════════════════════════════════════════════════════

def _urgencia_dict(a):
    return {
        "id": a.id,
        "unidade_id": a.unidade_id,
        "unidade_nome": a.unidade.nome if a.unidade else "",
        "tipo_unidade": a.tipo_unidade, "tipo_unidade_label": a.get_tipo_unidade_display(),
        "data_atendimento": str(a.data_atendimento),
        "total_atendimentos": a.total_atendimentos,
        "vermelho": a.vermelho, "laranja": a.laranja,
        "amarelo": a.amarelo, "verde": a.verde, "azul": a.azul,
        "obitos": a.obitos,
        "tempo_espera_medio_min": a.tempo_espera_medio_min,
        "criado_em": a.criado_em.isoformat(),
    }


@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_atendimentos_urgencia(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = AtendimentoUrgencia.objects.filter(empresa=e).select_related("unidade")
        tipo = request.GET.get("tipo_unidade")
        data_inicio = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        if tipo:
            qs = qs.filter(tipo_unidade=tipo)
        if data_inicio:
            qs = qs.filter(data_atendimento__gte=data_inicio)
        if data_fim:
            qs = qs.filter(data_atendimento__lte=data_fim)
        return JsonResponse({"atendimentos": [_urgencia_dict(a) for a in qs]})

    data = json.loads(request.body or "{}")
    if not data.get("tipo_unidade") or not data.get("data_atendimento"):
        return JsonResponse({"erro": "tipo_unidade e data_atendimento são obrigatórios"}, status=400)

    a, _ = AtendimentoUrgencia.objects.update_or_create(
        empresa=e,
        unidade_id=data.get("unidade_id") or None,
        data_atendimento=data["data_atendimento"],
        defaults={
            "tipo_unidade": data["tipo_unidade"],
            "total_atendimentos": data.get("total_atendimentos", 0),
            "vermelho": data.get("vermelho", 0),
            "laranja": data.get("laranja", 0),
            "amarelo": data.get("amarelo", 0),
            "verde": data.get("verde", 0),
            "azul": data.get("azul", 0),
            "obitos": data.get("obitos", 0),
            "tempo_espera_medio_min": data.get("tempo_espera_medio_min", 0),
        }
    )
    return JsonResponse(_urgencia_dict(a), status=201)


@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.regulacao_urgencia")
def api_urgencia_dashboard(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    sete_dias = hoje - timedelta(days=7)
    quatorze_dias = hoje - timedelta(days=14)

    qs = AtendimentoUrgencia.objects.filter(empresa=e)
    qs_semana = qs.filter(data_atendimento__gte=sete_dias)
    qs_semana_ant = qs.filter(data_atendimento__gte=quatorze_dias, data_atendimento__lt=sete_dias)

    def totais(queryset):
        return queryset.aggregate(
            total=Sum("total_atendimentos"),
            vermelho=Sum("vermelho"), laranja=Sum("laranja"),
            amarelo=Sum("amarelo"), verde=Sum("verde"), azul=Sum("azul"),
            obitos=Sum("obitos"),
            tempo_medio=Avg("tempo_espera_medio_min"),
        )

    sem_atual = totais(qs_semana)
    sem_ant = totais(qs_semana_ant)

    # Por tipo de unidade
    por_tipo = {}
    for tipo, label in AtendimentoUrgencia.TIPO_UNIDADE_CHOICES:
        sub = qs_semana.filter(tipo_unidade=tipo)
        agg = sub.aggregate(t=Sum("total_atendimentos"), o=Sum("obitos"), tem=Avg("tempo_espera_medio_min"))
        por_tipo[tipo] = {
            "label": label,
            "total": agg["t"] or 0,
            "obitos": agg["o"] or 0,
            "tempo_medio_min": float(round(agg["tem"] or 0, 0)),
        }

    # Evolução diária última semana (data_atendimento já é DateField, sem necessidade de truncar)
    evolucao = list(
        qs_semana
        .values("data_atendimento")
        .annotate(total=Sum("total_atendimentos"), obitos=Sum("obitos"))
        .order_by("data_atendimento")
    )
    for item in evolucao:
        item["dia"] = str(item.pop("data_atendimento"))

    return JsonResponse({
        "semana_atual": {k: float(round(v or 0, 1)) if k == "tempo_medio" else (v or 0) for k, v in sem_atual.items()},
        "semana_anterior": {k: float(round(v or 0, 1)) if k == "tempo_medio" else (v or 0) for k, v in sem_ant.items()},
        "por_tipo_unidade": por_tipo,
        "evolucao_diaria": evolucao,
    })


# ═══════════════════════════════════════════════════════════════
# DASHBOARD GERAL FASE 2
# ═══════════════════════════════════════════════════════════════

@require_http_methods(["GET"])
def api_governo_fase2_dashboard(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    trinta_dias = hoje - timedelta(days=30)

    # Rede de saúde
    unidades_ativas = UnidadeSaude.objects.filter(empresa=e, status="ativa").count()
    unidades_total = UnidadeSaude.objects.filter(empresa=e).count()
    equipes_esf = EquipeSaude.objects.filter(empresa=e, tipo="esf", ativa=True).count()
    populacao_coberta = EquipeSaude.objects.filter(
        empresa=e, tipo="esf", ativa=True
    ).aggregate(total=Sum("populacao_cadastrada"))["total"] or 0

    # Vigilância
    surtos_ativos = SurtoEpidemiologico.objects.filter(empresa=e, status="ativo").count()
    notif_30d = NotificacaoCompulsoria.objects.filter(
        empresa=e, data_notificacao__gte=trinta_dias
    ).count()

    # Regulação
    leitos_aguardando = RegulacaoLeito.objects.filter(empresa=e, status="regulado").count()
    tempo_medio_reg = RegulacaoLeito.objects.filter(
        empresa=e, tempo_espera_horas__isnull=False
    ).aggregate(m=Avg("tempo_espera_horas"))["m"]

    # Previne Brasil — score na competência mais recente
    competencia = (
        MetaPrevine.objects.filter(empresa=e)
        .values_list("competencia", flat=True)
        .order_by("-competencia").first()
    )
    score_previne = 0
    if competencia:
        total_prev = MetaPrevine.objects.filter(empresa=e, competencia=competencia).count()
        ating_prev = MetaPrevine.objects.filter(empresa=e, competencia=competencia, atingiu_meta=True).count()
        score_previne = round(ating_prev / total_prev * 100, 1) if total_prev > 0 else 0

    # Contratos
    contratos_vigentes = ContratoGestao.objects.filter(empresa=e, status="vigente").count()
    contratos_vencendo = ContratoGestao.objects.filter(
        empresa=e, status="vigente", data_fim__lte=hoje + timedelta(days=30)
    ).count()

    # Urgência 7 dias
    urgencia_7d = AtendimentoUrgencia.objects.filter(
        empresa=e, data_atendimento__gte=hoje - timedelta(days=7)
    ).aggregate(total=Sum("total_atendimentos"), obitos=Sum("obitos"))

    return JsonResponse({
        "rede": {
            "unidades_ativas": unidades_ativas,
            "unidades_total": unidades_total,
            "equipes_esf": equipes_esf,
            "populacao_coberta_esf": populacao_coberta,
        },
        "vigilancia": {
            "surtos_ativos": surtos_ativos,
            "notificacoes_30d": notif_30d,
        },
        "regulacao": {
            "leitos_aguardando": leitos_aguardando,
            "tempo_medio_espera_horas": float(round(tempo_medio_reg, 1)) if tempo_medio_reg else 0,
        },
        "previne": {
            "competencia": competencia or "",
            "score_percentual": score_previne,
        },
        "contratos": {
            "vigentes": contratos_vigentes,
            "vencendo_30d": contratos_vencendo,
        },
        "urgencia_7d": {
            "total_atendimentos": urgencia_7d["total"] or 0,
            "obitos": urgencia_7d["obitos"] or 0,
        },
    })


# ═══════════════════════════════════════════════════════════════
# PLATAFORMA TI GOVERNAMENTAL
# ═══════════════════════════════════════════════════════════════

@api_requer_plataforma_ti
def api_governo_plataforma_integracoes(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        integracoes = [
            {"codigo": "rnds",          "nome": "RNDS",               "descricao": "Rede Nacional de Dados em Saúde",          "status": "desconectado"},
            {"codigo": "esus_ab",       "nome": "e-SUS AB",           "descricao": "Sistema e-SUS Atenção Básica",             "status": "desconectado"},
            {"codigo": "sinan",         "nome": "SINAN Online",       "descricao": "Notificações Compulsórias",                "status": "desconectado"},
            {"codigo": "cnes",          "nome": "CNES",               "descricao": "Cadastro de Estabelecimentos",             "status": "desconectado"},
            {"codigo": "siops",         "nome": "SIOPS",              "descricao": "Orçamentos Públicos em Saúde",             "status": "desconectado"},
            {"codigo": "bpa_raas",      "nome": "BPA/RAAS",           "descricao": "Produção Ambulatorial",                   "status": "desconectado"},
            {"codigo": "sihsus",        "nome": "SIHSUS",             "descricao": "Informações Hospitalares",                 "status": "desconectado"},
            {"codigo": "conectesus",    "nome": "ConecteSUS",         "descricao": "Portal do Paciente",                      "status": "desconectado"},
            {"codigo": "cadunico",      "nome": "CadÚnico",           "descricao": "Cadastro Único Social",                   "status": "desconectado"},
            {"codigo": "sigtap",        "nome": "SIGTAP",             "descricao": "Tabela de Procedimentos",                 "status": "desconectado"},
            {"codigo": "tce_tcu",       "nome": "TCE/TCU",            "descricao": "Tribunal de Contas",                      "status": "desconectado"},
            {"codigo": "transparencia", "nome": "Transparência",      "descricao": "Portal da Transparência",                 "status": "desconectado"},
        ]
        return JsonResponse({"integracoes": integracoes})
    except Exception:
        return JsonResponse({"disponivel": False}, status=500)


@api_requer_plataforma_ti
def api_governo_plataforma_chaves(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        if request.method == "POST":
            dados = json.loads(request.body or "{}")
            nome = (dados.get("nome") or "Chave API").strip()[:100]
            key = ApiKeyEmpresa.objects.create(empresa=empresa, nome=nome)
            AuditoriaInstitucional.objects.create(
                empresa=empresa, acao="api_key_criada",
                objeto_tipo="ApiKeyEmpresa", objeto_id=str(key.id),
                detalhes={"nome": nome},
            )
            return JsonResponse({"chave": key.chave, "id": key.id, "nome": key.nome, "criado": True}, status=201)

        # GET — lista chaves com uso de hoje
        hoje = date.today().strftime("%Y-%m")
        keys = ApiKeyEmpresa.objects.filter(empresa=empresa).order_by("-criado_em")
        chamadas_hoje = (
            UsoApiEmpresa.objects.filter(empresa=empresa, ano_mes=hoje)
            .aggregate(total=Sum("chamadas"))["total"] or 0
        )
        ativas = keys.filter(ativa=True).count()
        return JsonResponse({
            "chaves": [
                {
                    "id": k.id,
                    "nome": k.nome,
                    "chave_prefixo": k.chave[:8] + "••••••••",
                    "ativa": k.ativa,
                    "total_chamadas": k.total_chamadas,
                    "ultimo_uso_em": k.ultimo_uso_em.isoformat() if k.ultimo_uso_em else None,
                    "criado_em": k.criado_em.strftime("%d/%m/%Y"),
                }
                for k in keys
            ],
            "total": keys.count(),
            "ativas": ativas,
            "chamadas_hoje": chamadas_hoje,
            "taxa_sucesso": 100,
        })
    except Exception as ex:
        return JsonResponse({"disponivel": False, "erro": str(ex)[:200]}, status=500)


@api_requer_plataforma_ti
def api_governo_plataforma_webhooks(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        if request.method == "POST":
            dados = json.loads(request.body or "{}")
            url = (dados.get("url_destino") or "").strip()
            pattern = (dados.get("tipo_evento_pattern") or "*").strip()
            if not url:
                return JsonResponse({"erro": "url_destino é obrigatório"}, status=400)
            import secrets
            sub = SubscricaoEvento.objects.create(
                empresa=empresa,
                tipo_evento_pattern=pattern,
                url_destino=url,
                secret_hmac=secrets.token_hex(32),
                ativo=True,
            )
            AuditoriaInstitucional.objects.create(
                empresa=empresa, acao="webhook_criado",
                objeto_tipo="SubscricaoEvento", objeto_id=str(sub.id),
                detalhes={"url": url, "pattern": pattern},
            )
            return JsonResponse({
                "id": sub.id,
                "url_destino": sub.url_destino,
                "tipo_evento_pattern": sub.tipo_evento_pattern,
                "secret_hmac": sub.secret_hmac,
                "criado": True,
            }, status=201)

        # GET — lista webhooks cadastrados
        subs = SubscricaoEvento.objects.filter(empresa=empresa).order_by("-criado_em")
        return JsonResponse({
            "webhooks": [
                {
                    "id": s.id,
                    "url_destino": s.url_destino,
                    "tipo_evento_pattern": s.tipo_evento_pattern,
                    "ativo": s.ativo,
                    "criado_em": s.criado_em.strftime("%d/%m/%Y"),
                }
                for s in subs
            ],
            "total": subs.count(),
        })
    except Exception as ex:
        return JsonResponse({"disponivel": False, "erro": str(ex)[:200]}, status=500)


@api_requer_plataforma_ti
def api_governo_plataforma_seguranca(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        # LGPD checklist — verificado contra dados reais
        tem_dpo = EmpresaUsuario.objects.filter(
            empresa=empresa, ativo=True,
            cargo__icontains="dpo"
        ).exists() or EmpresaUsuario.objects.filter(
            empresa=empresa, ativo=True,
            cargo__icontains="encarregado"
        ).exists()

        tem_mapeamento = AuditoriaInstitucional.objects.filter(
            empresa=empresa, acao__icontains="mapeamento_dados"
        ).exists()

        tem_ripd = AuditoriaInstitucional.objects.filter(
            empresa=empresa, acao__icontains="ripd"
        ).exists()

        tem_acordo = AuditoriaInstitucional.objects.filter(
            empresa=empresa, acao__icontains="acordo_ministerio"
        ).exists()

        # Sessões ativas (últimas 8 horas)
        oito_horas = timezone.now() - timedelta(hours=8)
        sessoes = EmpresaUsuario.objects.filter(
            empresa=empresa, ativo=True,
            sessao_ativa_em__gte=oito_horas,
        ).values("id", "nome", "email", "sessao_ativa_em")

        return JsonResponse({
            "lgpd_checklist": [
                {"item": "Encarregado DPO nomeado",                         "ok": tem_dpo},
                {"item": "Mapeamento de dados sensíveis concluído",         "ok": tem_mapeamento},
                {"item": "Relatório de Impacto (RIPD) elaborado",           "ok": tem_ripd},
                {"item": "Acordo de processamento com Ministério da Saúde", "ok": tem_acordo},
            ],
            "sessoes_ativas": [
                {
                    "usuario_id": s["id"],
                    "nome": s["nome"],
                    "email": s["email"],
                    "ativo_desde": s["sessao_ativa_em"].isoformat() if s["sessao_ativa_em"] else None,
                }
                for s in sessoes
            ],
            "total_sessoes_ativas": sessoes.count(),
            "2fa_ativo": False,  # 2FA implementável como próximo passo
        })
    except Exception as ex:
        return JsonResponse({"disponivel": False, "erro": str(ex)[:200]}, status=500)


@api_requer_plataforma_ti
def api_governo_plataforma_logs(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        limite = min(int(request.GET.get("limite", 50)), 200)
        acao_filtro = request.GET.get("acao", "")

        qs = AuditoriaInstitucional.objects.filter(empresa=empresa)
        if acao_filtro:
            qs = qs.filter(acao__icontains=acao_filtro)

        logs = qs.order_by("-criado_em")[:limite]
        return JsonResponse({
            "logs": [
                {
                    "id": l.id,
                    "acao": l.acao,
                    "objeto_tipo": l.objeto_tipo or "—",
                    "objeto_id": l.objeto_id or "—",
                    "principal_nome": l.principal_nome or "sistema",
                    "ip": l.ip,
                    "data": l.criado_em.strftime("%d/%m/%Y %H:%M"),
                    "detalhes": l.detalhes,
                }
                for l in logs
            ],
            "total": qs.count(),
        })
    except Exception as ex:
        return JsonResponse({"disponivel": False, "erro": str(ex)[:200]}, status=500)
