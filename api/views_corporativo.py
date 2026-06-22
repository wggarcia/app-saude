import json
from datetime import date, timedelta

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .corporativo_ai import MIN_GROUP_SIZE, build_empresa_corporativo_payload
from .models import (
    CheckinDiarioCorporativo,
    CheckinSemanalCorporativo,
    ColaboradorAliasCorporativo,
    CompetenciaItemCorporativo,
    Empresa,
    EmpresaSetor,
    EmpresaTurno,
    EmpresaUnidade,
    EvidenciaCompetenciaCorporativa,
    FuncionarioSST,
    PedidoApoioCorporativo,
    TrilhaCompetenciaCorporativa,
)
from .access_control import api_requer_feature, dentro_do_limite, empresa_tem_feature
from .services.dashboard_core import setor_conta
from .views_dashboard import _empresa_autenticada


def _empresa_corporativa_autenticada(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    setor = setor_conta(empresa)
    if setor != "empresa" or empresa.tipo_conta != Empresa.TIPO_EMPRESA:
        return None
    return empresa


def _resolver_empresa_por_codigo(codigo):
    empresa = get_object_or_404(Empresa, codigo_acesso_corporativo=codigo, ativo=True)
    if setor_conta(empresa) != "empresa":
        raise ValueError("codigo indisponivel para setor nao corporativo")
    return empresa


def _obter_ou_criar_unidade(empresa, nome):
    nome = (nome or "").strip()
    if not nome:
        return None
    existente = EmpresaUnidade.objects.filter(empresa=empresa, nome=nome).first()
    if existente:
        return existente
    contagem_atual = EmpresaUnidade.objects.filter(empresa=empresa, ativo=True).count()
    if not dentro_do_limite(empresa, "max_unidades", contagem_atual):
        return None
    return EmpresaUnidade.objects.create(empresa=empresa, nome=nome, codigo="")


def _obter_ou_criar_setor(empresa, nome, unidade=None):
    nome = (nome or "").strip()
    if not nome:
        return None
    setor, _ = EmpresaSetor.objects.get_or_create(empresa=empresa, unidade=unidade, nome=nome)
    return setor


def _obter_ou_criar_turno(empresa, nome):
    nome = (nome or "").strip()
    if not nome:
        return None
    existente = EmpresaTurno.objects.filter(empresa=empresa, nome=nome).first()
    if existente:
        return existente
    if not empresa_tem_feature(empresa, "sst.turnos"):
        return None
    return EmpresaTurno.objects.create(empresa=empresa, nome=nome, janela="")


def _normalizar_score(valor, default=3):
    try:
        parsed = int(valor)
    except (TypeError, ValueError):
        return default
    return max(1, min(5, parsed))


def dashboard_empresa_corporativo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")

    setor = setor_conta(empresa)
    if setor == "farmacia":
        return redirect("/dashboard-farmacia/")
    if setor == "hospital":
        return redirect("/dashboard-hospital/")
    if setor == "governo" or empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return redirect("/dashboard-governo/")
    if setor == "plano_saude":
        return redirect("/dashboard-plano-saude/")

    payload = build_empresa_corporativo_payload(empresa)
    return render(request, "dashboard_empresa_corporativo.html", {
        "empresa_nome": empresa.nome,
        "payload": payload,
    })


def api_empresa_corporativo_resumo(request):
    empresa = _empresa_corporativa_autenticada(request)
    if not empresa:
        if not _empresa_autenticada(request):
            return JsonResponse({"erro": "nao autenticado"}, status=401)
        return JsonResponse({"erro": "ambiente corporativo restrito ao setor empresa"}, status=403)

    return JsonResponse(build_empresa_corporativo_payload(empresa))


def api_empresa_corporativo_catalogo(request):
    empresa = _empresa_corporativa_autenticada(request)
    if not empresa:
        if not _empresa_autenticada(request):
            return JsonResponse({"erro": "nao autenticado"}, status=401)
        return JsonResponse({"erro": "ambiente corporativo restrito ao setor empresa"}, status=403)

    return JsonResponse({
        "company": empresa.nome,
        "access_code": empresa.codigo_acesso_corporativo,
        "group_minimum": MIN_GROUP_SIZE,
        "units": [
            {"id": unidade.id, "name": unidade.nome}
            for unidade in EmpresaUnidade.objects.filter(empresa=empresa, ativo=True)
        ],
        "sectors": [
            {"id": setor.id, "name": setor.nome, "unit_id": setor.unidade_id}
            for setor in EmpresaSetor.objects.filter(empresa=empresa, ativo=True)
        ],
        "shifts": [
            {"id": turno.id, "name": turno.nome}
            for turno in EmpresaTurno.objects.filter(empresa=empresa, ativo=True)
        ],
    })


def app_colaborador_corporativo(request, codigo):
    try:
        empresa = _resolver_empresa_por_codigo(codigo)
    except ValueError:
        return redirect("/")

    return render(request, "app_colaborador_corporativo.html", {
        "empresa_nome": empresa.nome,
        "codigo_acesso": codigo,
        "min_group_size": MIN_GROUP_SIZE,
        "mobile_api_base": f"/api/colaborador-mobile/{codigo}",
    })


def api_colaborador_corporativo_config(request, codigo):
    try:
        empresa = _resolver_empresa_por_codigo(codigo)
    except ValueError:
        return JsonResponse({"erro": "codigo invalido"}, status=404)

    return JsonResponse({
        "company": empresa.nome,
        "group_minimum": MIN_GROUP_SIZE,
        "units": [
            {"id": unidade.id, "name": unidade.nome}
            for unidade in EmpresaUnidade.objects.filter(empresa=empresa, ativo=True)
        ],
        "sectors": [
            {"id": setor.id, "name": setor.nome, "unit_id": setor.unidade_id}
            for setor in EmpresaSetor.objects.filter(empresa=empresa, ativo=True)
        ],
        "shifts": [
            {"id": turno.id, "name": turno.nome}
            for turno in EmpresaTurno.objects.filter(empresa=empresa, ativo=True)
        ],
    })


def _build_alias(empresa, dados):
    alias_code = (dados.get("alias_code") or "").strip()
    if not alias_code:
        return None

    unidade = _obter_ou_criar_unidade(empresa, dados.get("unit_name"))
    setor = _obter_ou_criar_setor(empresa, dados.get("sector_name"), unidade=unidade)
    turno = _obter_ou_criar_turno(empresa, dados.get("shift_name"))
    alias, _ = ColaboradorAliasCorporativo.objects.get_or_create(
        empresa=empresa,
        alias_publico=alias_code,
        defaults={
            "unidade": unidade,
            "setor": setor,
            "turno": turno,
            "permite_contato": bool(dados.get("allow_contact")),
        },
    )

    changed = []
    for field, value in {
        "unidade": unidade or alias.unidade,
        "setor": setor or alias.setor,
        "turno": turno or alias.turno,
        "permite_contato": bool(dados.get("allow_contact")),
        "ativo": True,
    }.items():
        if getattr(alias, field) != value:
            setattr(alias, field, value)
            changed.append(field)
    if changed:
        alias.save(update_fields=changed + ["atualizado_em"])
    return alias


@csrf_exempt
def api_corporativo_checkin_diario(request, codigo):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)
    try:
        empresa = _resolver_empresa_por_codigo(codigo)
    except ValueError:
        return JsonResponse({"erro": "codigo invalido"}, status=404)

    try:
        dados = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json invalido"}, status=400)

    alias = _build_alias(empresa, dados)
    if not alias:
        return JsonResponse({"erro": "alias_code obrigatorio"}, status=400)

    unidade = alias.unidade
    setor = alias.setor
    turno = alias.turno
    checkin, created = CheckinDiarioCorporativo.objects.update_or_create(
        empresa=empresa,
        alias=alias,
        data_referencia=timezone.localdate(),
        defaults={
            "unidade": unidade,
            "setor": setor,
            "turno": turno,
            "humor": _normalizar_score(dados.get("mood")),
            "energia": _normalizar_score(dados.get("energy")),
            "estresse": _normalizar_score(dados.get("stress")),
            "sono": _normalizar_score(dados.get("sleep_quality")),
            "dor_fisica": _normalizar_score(dados.get("physical_pain"), default=1),
            "fadiga": _normalizar_score(dados.get("fatigue"), default=1),
            "ansiedade": _normalizar_score(dados.get("anxiety"), default=1),
            "tristeza": _normalizar_score(dados.get("sadness"), default=1),
            "irritabilidade": _normalizar_score(dados.get("irritability"), default=1),
            "sintomas_respiratorios": bool(dados.get("respiratory_symptoms")),
            "dor_corporal": bool(dados.get("body_pain")),
            "dor_cabeca": bool(dados.get("headache")),
            "febre": bool(dados.get("fever")),
            "apoio_solicitado": bool(dados.get("request_support")),
            "observacao": str(dados.get("note") or "")[:280],
        },
    )

    if dados.get("request_support"):
        PedidoApoioCorporativo.objects.create(
            empresa=empresa,
            alias=alias,
            unidade=unidade,
            setor=setor,
            turno=turno,
            deseja_contato=bool(dados.get("allow_contact")),
            canal_preferido=str(dados.get("contact_channel") or "")[:80],
            relato=str(dados.get("support_note") or dados.get("note") or "")[:280],
        )

    return JsonResponse({
        "status": "ok",
        "created": created,
        "company": empresa.nome,
        "recorded_for": checkin.data_referencia.isoformat(),
    })


@csrf_exempt
def api_corporativo_checkin_semanal(request, codigo):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)
    try:
        empresa = _resolver_empresa_por_codigo(codigo)
    except ValueError:
        return JsonResponse({"erro": "codigo invalido"}, status=404)

    try:
        dados = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json invalido"}, status=400)

    alias = _build_alias(empresa, dados)
    if not alias:
        return JsonResponse({"erro": "alias_code obrigatorio"}, status=400)

    semana_referencia = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    checkin, created = CheckinSemanalCorporativo.objects.update_or_create(
        empresa=empresa,
        alias=alias,
        semana_referencia=semana_referencia,
        defaults={
            "unidade": alias.unidade,
            "setor": alias.setor,
            "turno": alias.turno,
            "carga_emocional": _normalizar_score(dados.get("emotional_load")),
            "seguranca_psicologica": _normalizar_score(dados.get("psychological_safety")),
            "apoio_percebido": _normalizar_score(dados.get("support_perception")),
            "pressao_trabalho": _normalizar_score(dados.get("work_pressure")),
            "bem_estar_geral": _normalizar_score(dados.get("overall_wellbeing")),
            "risco_burnout": _normalizar_score(dados.get("burnout_risk"), default=1),
            "observacao": str(dados.get("note") or "")[:280],
        },
    )

    return JsonResponse({
        "status": "ok",
        "created": created,
        "company": empresa.nome,
        "week_reference": checkin.semana_referencia.isoformat(),
    })


def api_colaborador_trilhas(request, codigo):
    try:
        empresa = _resolver_empresa_por_codigo(codigo)
    except ValueError:
        return JsonResponse({"erro": "codigo invalido"}, status=404)

    alias_code = request.GET.get("alias_code", "").strip()
    alias = None
    if alias_code:
        alias = ColaboradorAliasCorporativo.objects.filter(empresa=empresa, alias_publico=alias_code).first()

    trilhas = TrilhaCompetenciaCorporativa.objects.filter(empresa=empresa, ativo=True).prefetch_related("itens")

    evidencias_por_item = {}
    if alias:
        for ev in EvidenciaCompetenciaCorporativa.objects.filter(empresa=empresa, alias=alias).select_related("item"):
            evidencias_por_item[ev.item_id] = ev

    result = []
    for t in trilhas:
        itens = []
        for item in t.itens.filter(ativo=True):
            ev = evidencias_por_item.get(item.id)
            itens.append({
                "id": item.id,
                "titulo": item.titulo,
                "tipo": item.tipo,
                "descricao": item.descricao,
                "obrigatorio": item.obrigatorio,
                "evidencia_status": ev.status if ev else None,
                "evidencia_id": ev.id if ev else None,
            })
        result.append({
            "id": t.id,
            "titulo": t.titulo,
            "descricao": t.descricao,
            "nivel_alvo": t.nivel_alvo,
            "cargo": t.cargo.nome if t.cargo else None,
            "itens": itens,
            "total": len(itens),
            "concluidos": sum(1 for i in itens if i["evidencia_status"] == EvidenciaCompetenciaCorporativa.STATUS_VALIDADA),
        })

    return JsonResponse({"trilhas": result})


@csrf_exempt
@api_requer_feature("sst.painel_rh")
def api_corporativo_rh_resumo(request):
    """GET /api/corporativo/rh/resumo/ — Headcount & turnover analytics from FuncionarioSST"""
    empresa = _empresa_corporativa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    trinta_dias = hoje - timedelta(days=30)

    qs = FuncionarioSST.objects.filter(empresa=empresa)
    headcount_total = qs.count()
    ativos = qs.filter(ativo=True).count()
    admissoes_30d = qs.filter(data_admissao__gte=trinta_dias).count()
    desligamentos_30d = qs.filter(data_demissao__gte=trinta_dias).count()

    # By department (setor)
    por_dept_raw = (
        qs.filter(ativo=True)
        .values("setor")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    por_departamento = [
        {"departamento": d["setor"] or "Sem setor", "total": d["total"]}
        for d in por_dept_raw
    ]

    # Monthly turnover — last 12 months
    turnover_mensal = []
    for i in range(11, -1, -1):
        ref = hoje.replace(day=1) - timedelta(days=i * 30)
        mes_inicio = ref.replace(day=1)
        mes_fim = (mes_inicio + timedelta(days=32)).replace(day=1)
        saidas = qs.filter(data_demissao__gte=mes_inicio, data_demissao__lt=mes_fim).count()
        turnover_mensal.append({
            "mes": mes_inicio.strftime("%b/%y"),
            "saidas": saidas,
        })

    # Annual turnover rate
    saidas_anuais = qs.filter(data_demissao__gte=hoje - timedelta(days=365)).count()
    taxa_turnover_anual = round((saidas_anuais / headcount_total * 100), 1) if headcount_total > 0 else 0

    return JsonResponse({
        "headcount_total": headcount_total,
        "ativos": ativos,
        "admissoes_30d": admissoes_30d,
        "desligamentos_30d": desligamentos_30d,
        "por_departamento": por_departamento,
        "turnover_mensal": turnover_mensal,
        "taxa_turnover_anual": taxa_turnover_anual,
    })


@csrf_exempt
@api_requer_feature("sst.painel_rh")
def api_corporativo_rh_sincronizar(request):
    """
    Sincroniza dados SST → corporativo para a empresa autenticada.

    Reconcilia FuncionarioSST com a visão corporativa:
    - Conta ativos, desligados no mês, ASOs vencidos e ausentes
    - Identifica funcionários sem nenhum ASO cadastrado
    - Retorna diagnóstico acionável para o RH

    POST /api/corporativo/rh/sincronizar/
    """
    empresa = _empresa_corporativa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)

    hoje = date.today()

    from .models import ASOOcupacional, eSocialEventoSST

    # ── Funcionários SST ─────────────────────────────────────────────────────
    todos_func      = FuncionarioSST.objects.filter(empresa=empresa)
    ativos          = todos_func.filter(ativo=True)
    total_ativos    = ativos.count()
    total_inativos  = todos_func.filter(ativo=False).count()

    # Admissões e desligamentos no mês atual
    mes_inicio = hoje.replace(day=1)
    admissoes_mes   = ativos.filter(data_admissao__gte=mes_inicio).count()
    desligamentos_mes = todos_func.filter(
        ativo=False, data_demissao__gte=mes_inicio
    ).count()

    # ── ASOs ─────────────────────────────────────────────────────────────────
    func_ids_com_aso = ASOOcupacional.objects.filter(
        empresa=empresa
    ).values_list("funcionario_id", flat=True).distinct()

    sem_aso = ativos.exclude(pk__in=func_ids_com_aso).count()

    asos_vencidos = ASOOcupacional.objects.filter(
        empresa=empresa,
        funcionario__ativo=True,
        data_validade__lt=hoje,
        data_validade__isnull=False,
    ).count()

    asos_vencendo_30d = ASOOcupacional.objects.filter(
        empresa=empresa,
        funcionario__ativo=True,
        data_validade__gte=hoje,
        data_validade__lte=hoje + timedelta(days=30),
    ).count()

    # ── eSocial ───────────────────────────────────────────────────────────────
    esocial_pendentes = eSocialEventoSST.objects.filter(
        empresa=empresa, status="pendente"
    ).count()
    esocial_erros = eSocialEventoSST.objects.filter(
        empresa=empresa, status="erro"
    ).count()

    # ── Score de conformidade SST ─────────────────────────────────────────────
    problemas = sem_aso + asos_vencidos + esocial_erros
    score_sst = max(0, 100 - (problemas * 5)) if total_ativos > 0 else 100

    return JsonResponse({
        "ok":               True,
        "sincronizado_em":  hoje.isoformat(),
        "funcionarios": {
            "total_ativos":      total_ativos,
            "total_inativos":    total_inativos,
            "admissoes_mes":     admissoes_mes,
            "desligamentos_mes": desligamentos_mes,
        },
        "asos": {
            "sem_aso":            sem_aso,
            "vencidos":           asos_vencidos,
            "vencendo_30_dias":   asos_vencendo_30d,
        },
        "esocial": {
            "pendentes":  esocial_pendentes,
            "com_erro":   esocial_erros,
        },
        "score_conformidade_sst": score_sst,
        "alertas": [
            *([f"{sem_aso} funcionário(s) sem nenhum ASO cadastrado."] if sem_aso else []),
            *([f"{asos_vencidos} ASO(s) vencido(s)."] if asos_vencidos else []),
            *([f"{asos_vencendo_30d} ASO(s) vencendo em até 30 dias."] if asos_vencendo_30d else []),
            *([f"{esocial_pendentes} evento(s) eSocial pendente(s)."] if esocial_pendentes else []),
            *([f"{esocial_erros} evento(s) eSocial com erro."] if esocial_erros else []),
        ],
    })
