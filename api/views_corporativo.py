import json
from datetime import timedelta

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
    PedidoApoioCorporativo,
    TrilhaCompetenciaCorporativa,
)
from .views_dashboard import _empresa_autenticada, _setor_conta


def _empresa_corporativa_autenticada(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    setor = _setor_conta(empresa)
    if setor != "empresa" or empresa.tipo_conta != Empresa.TIPO_EMPRESA:
        return None
    return empresa


def _resolver_empresa_por_codigo(codigo):
    empresa = get_object_or_404(Empresa, codigo_acesso_corporativo=codigo, ativo=True)
    if _setor_conta(empresa) != "empresa":
        raise ValueError("codigo indisponivel para setor nao corporativo")
    return empresa


def _obter_ou_criar_unidade(empresa, nome):
    nome = (nome or "").strip()
    if not nome:
        return None
    unidade, _ = EmpresaUnidade.objects.get_or_create(empresa=empresa, nome=nome, defaults={"codigo": ""})
    return unidade


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
    turno, _ = EmpresaTurno.objects.get_or_create(empresa=empresa, nome=nome, defaults={"janela": ""})
    return turno


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

    setor = _setor_conta(empresa)
    if setor == "farmacia":
        return redirect("/dashboard-farmacia/")
    if setor == "hospital":
        return redirect("/dashboard-hospital/")
    if setor == "governo" or empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return redirect("/dashboard-governo/")

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
