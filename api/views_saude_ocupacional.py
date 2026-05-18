import json
from datetime import date, timedelta

from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    CheckinDiarioCorporativo,
    CheckinSemanalCorporativo,
    ColaboradorAliasCorporativo,
    ConteudoSSTPublicado,
    EmpresaSetor,
    PedidoApoioCorporativo,
    RegistroConflitoCultural,
)
from .views_dashboard import _empresa_autenticada


# ─── pages ────────────────────────────────────────────────────────────────────

def sst_saude_comunicacao_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return __import__("django.shortcuts", fromlist=["redirect"]).redirect("/login-empresa/")
    setores = list(EmpresaSetor.objects.filter(empresa=empresa).values("id", "nome"))
    return render(request, "sst_saude_comunicacao.html", {
        "empresa_nome": empresa.nome,
        "setores_json": json.dumps(setores),
    })


def app_colaborador_saude(request, codigo):
    from .views_comunicacao import _resolve_alias
    alias = _resolve_alias(codigo)
    if not alias:
        return __import__("django.shortcuts", fromlist=["redirect"]).redirect("/")
    empresa = alias.empresa
    setores = list(EmpresaSetor.objects.filter(empresa=empresa).values("id", "nome"))
    return render(request, "app_colaborador_corporativo.html", {
        "empresa_nome": empresa.nome,
        "codigo_acesso": alias.codigo_acesso,
        "alias_nome": alias.nome,
        "cargo": alias.cargo.nome if alias.cargo else "",
        "setor": alias.setor.nome if alias.setor else "",
        "setores_json": json.dumps(setores),
    })


# ─── wellness dashboard (SST gestor) ──────────────────────────────────────────

def api_wellness_resumo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    hoje = date.today()
    semana_ini = hoje - timedelta(days=6)

    checkins = CheckinDiarioCorporativo.objects.filter(
        empresa=empresa, data_referencia__gte=semana_ini
    )
    total = checkins.count()
    agg = checkins.aggregate(
        humor=Avg("humor"),
        energia=Avg("energia"),
        estresse=Avg("estresse"),
        fadiga=Avg("fadiga"),
        ansiedade=Avg("ansiedade"),
        dor_fisica=Avg("dor_fisica"),
    )

    apoios = PedidoApoioCorporativo.objects.filter(
        empresa=empresa, status=PedidoApoioCorporativo.STATUS_NOVO
    ).count()

    conflitos = RegistroConflitoCultural.objects.filter(
        empresa=empresa, status=RegistroConflitoCultural.STATUS_NOVO
    ).count()

    burnout_alto = CheckinSemanalCorporativo.objects.filter(
        empresa=empresa, semana_referencia__gte=hoje - timedelta(days=7), risco_burnout__gte=4
    ).count()

    return JsonResponse({
        "total_checkins_7d": total,
        "medias": {k: round(v, 1) if v else None for k, v in agg.items()},
        "apoios_pendentes": apoios,
        "conflitos_pendentes": conflitos,
        "burnout_alto_7d": burnout_alto,
    })


def api_wellness_por_setor(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    hoje = date.today()
    semana_ini = hoje - timedelta(days=6)

    por_setor = (
        CheckinDiarioCorporativo.objects
        .filter(empresa=empresa, data_referencia__gte=semana_ini, setor__isnull=False)
        .values("setor__id", "setor__nome")
        .annotate(
            total=Count("id"),
            humor=Avg("humor"),
            estresse=Avg("estresse"),
            fadiga=Avg("fadiga"),
            ansiedade=Avg("ansiedade"),
        )
        .order_by("setor__nome")
    )

    return JsonResponse({"setores": [
        {
            "id": s["setor__id"],
            "nome": s["setor__nome"],
            "total": s["total"],
            "humor": round(s["humor"], 1) if s["humor"] else None,
            "estresse": round(s["estresse"], 1) if s["estresse"] else None,
            "fadiga": round(s["fadiga"], 1) if s["fadiga"] else None,
            "ansiedade": round(s["ansiedade"], 1) if s["ansiedade"] else None,
        }
        for s in por_setor
    ]})


def api_wellness_alertas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    hoje = date.today()

    apoios = list(
        PedidoApoioCorporativo.objects
        .filter(empresa=empresa, status=PedidoApoioCorporativo.STATUS_NOVO)
        .select_related("alias", "setor")
        .values("id", "alias__nome", "setor__nome", "relato", "criado_em", "deseja_contato")
        .order_by("-criado_em")[:20]
    )

    conflitos = list(
        RegistroConflitoCultural.objects
        .filter(empresa=empresa, status=RegistroConflitoCultural.STATUS_NOVO)
        .select_related("alias", "setor")
        .values("id", "tipo", "ambiente", "descricao", "anonimo", "setor__nome", "criado_em")
        .order_by("-criado_em")[:20]
    )

    return JsonResponse({
        "apoios": [
            {
                **a,
                "criado_em": a["criado_em"].strftime("%d/%m/%Y %H:%M") if a["criado_em"] else None,
            }
            for a in apoios
        ],
        "conflitos": [
            {
                **c,
                "criado_em": c["criado_em"].strftime("%d/%m/%Y %H:%M") if c["criado_em"] else None,
            }
            for c in conflitos
        ],
    })


# ─── conteúdo SST ─────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_conteudos_listar(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    tipo = request.GET.get("tipo")
    ambiente = request.GET.get("ambiente")
    qs = ConteudoSSTPublicado.objects.filter(empresa=empresa, ativo=True)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if ambiente and ambiente != "ambos":
        qs = qs.filter(Q(ambiente=ambiente) | Q(ambiente="ambos"))

    items = list(qs.values(
        "id", "titulo", "tipo", "descricao", "url_conteudo",
        "setor_alvo__nome", "ambiente", "publicado_por", "visualizacoes", "publicado_em"
    )[:50])
    for i in items:
        i["publicado_em"] = i["publicado_em"].strftime("%d/%m/%Y") if i["publicado_em"] else None

    return JsonResponse({"conteudos": items})


@require_http_methods(["POST"])
def api_conteudos_criar(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    try:
        d = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    setor = None
    if d.get("setor_id"):
        setor = EmpresaSetor.objects.filter(empresa=empresa, id=d["setor_id"]).first()

    c = ConteudoSSTPublicado.objects.create(
        empresa=empresa,
        titulo=d.get("titulo", "").strip()[:200],
        tipo=d.get("tipo", ConteudoSSTPublicado.TIPO_COMUNICADO),
        descricao=d.get("descricao", "").strip(),
        url_conteudo=d.get("url_conteudo", "").strip(),
        setor_alvo=setor,
        ambiente=d.get("ambiente", ConteudoSSTPublicado.AMBIENTE_AMBOS),
        publicado_por=d.get("publicado_por", "Gestor SST"),
    )
    return JsonResponse({"id": c.id, "titulo": c.titulo}, status=201)


@require_http_methods(["POST"])
def api_conteudos_remover(request, conteudo_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    c = ConteudoSSTPublicado.objects.filter(empresa=empresa, id=conteudo_id).first()
    if not c:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    c.ativo = False
    c.save(update_fields=["ativo"])
    return JsonResponse({"ok": True})


# ─── conflitos culturais ───────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_conflitos_listar(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    status = request.GET.get("status")
    qs = RegistroConflitoCultural.objects.filter(empresa=empresa)
    if status:
        qs = qs.filter(status=status)

    items = list(qs.select_related("alias", "setor").values(
        "id", "tipo", "ambiente", "descricao", "paises_envolvidos",
        "anonimo", "alias__nome", "setor__nome", "status", "observacao_gestor", "criado_em"
    )[:50])
    for i in items:
        if i["anonimo"]:
            i["alias__nome"] = "Anônimo"
        i["criado_em"] = i["criado_em"].strftime("%d/%m/%Y %H:%M") if i["criado_em"] else None

    return JsonResponse({"conflitos": items})


@require_http_methods(["POST"])
def api_conflito_atualizar(request, conflito_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    c = RegistroConflitoCultural.objects.filter(empresa=empresa, id=conflito_id).first()
    if not c:
        return JsonResponse({"erro": "não encontrado"}, status=404)

    try:
        d = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if "status" in d:
        c.status = d["status"]
    if "observacao_gestor" in d:
        c.observacao_gestor = d["observacao_gestor"][:280]
    c.save(update_fields=["status", "observacao_gestor", "atualizado_em"])
    return JsonResponse({"ok": True})


# ─── colaborador: conteúdo (leitura no app) ───────────────────────────────────

def api_colab_conteudos(request, codigo):
    from .views_comunicacao import _resolve_alias
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)

    tipo = request.GET.get("tipo")
    ambiente = request.GET.get("ambiente")
    qs = ConteudoSSTPublicado.objects.filter(empresa=alias.empresa, ativo=True)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if ambiente and ambiente != "ambos":
        qs = qs.filter(Q(ambiente=ambiente) | Q(ambiente="ambos"))

    items = list(qs.values(
        "id", "titulo", "tipo", "descricao", "url_conteudo",
        "ambiente", "publicado_por", "publicado_em"
    )[:30])
    for i in items:
        i["publicado_em"] = i["publicado_em"].strftime("%d/%m/%Y") if i["publicado_em"] else None

    return JsonResponse({"conteudos": items})


# ─── colaborador: conflito cultural (envio no app) ────────────────────────────

@require_http_methods(["POST"])
def api_colab_conflito_registrar(request, codigo):
    from .views_comunicacao import _resolve_alias
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)

    try:
        d = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    c = RegistroConflitoCultural.objects.create(
        empresa=alias.empresa,
        alias=alias,
        setor=alias.setor,
        tipo=d.get("tipo", RegistroConflitoCultural.TIPO_OUTRO),
        ambiente=d.get("ambiente", RegistroConflitoCultural.AMBIENTE_ONSHORE),
        descricao=d.get("descricao", "").strip()[:500],
        paises_envolvidos=d.get("paises_envolvidos", "").strip()[:200],
        anonimo=d.get("anonimo", True),
    )
    return JsonResponse({"id": c.id, "ok": True}, status=201)


# ─── colaborador: checkin diário (usado pelo app) ─────────────────────────────

@require_http_methods(["POST"])
def api_colab_checkin_diario(request, codigo):
    from .views_comunicacao import _resolve_alias
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)

    try:
        d = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    hoje = date.today()
    defaults = {
        "humor": int(d.get("humor", 3)),
        "energia": int(d.get("energia", 3)),
        "estresse": int(d.get("estresse", 3)),
        "sono": int(d.get("sono", 3)),
        "dor_fisica": int(d.get("dor_fisica", 1)),
        "fadiga": int(d.get("fadiga", 1)),
        "ansiedade": int(d.get("ansiedade", 1)),
        "tristeza": int(d.get("tristeza", 1)),
        "irritabilidade": int(d.get("irritabilidade", 1)),
        "sintomas_respiratorios": bool(d.get("sintomas_respiratorios", False)),
        "dor_corporal": bool(d.get("dor_corporal", False)),
        "dor_cabeca": bool(d.get("dor_cabeca", False)),
        "febre": bool(d.get("febre", False)),
        "apoio_solicitado": bool(d.get("apoio_solicitado", False)),
        "observacao": d.get("observacao", "").strip()[:280],
    }

    obj, created = CheckinDiarioCorporativo.objects.update_or_create(
        empresa=alias.empresa,
        alias=alias,
        data_referencia=hoje,
        defaults={**defaults, "setor": alias.setor, "unidade": alias.unidade if hasattr(alias, "unidade") else None},
    )

    if defaults["apoio_solicitado"]:
        PedidoApoioCorporativo.objects.get_or_create(
            empresa=alias.empresa,
            alias=alias,
            status=PedidoApoioCorporativo.STATUS_NOVO,
            defaults={"setor": alias.setor, "relato": defaults["observacao"]},
        )

    return JsonResponse({"ok": True, "criado": created}, status=201 if created else 200)


@require_http_methods(["POST"])
def api_colab_checkin_semanal(request, codigo):
    from .views_comunicacao import _resolve_alias
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)

    try:
        d = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    hoje = date.today()
    ini_semana = hoje - timedelta(days=hoje.weekday())

    defaults = {
        "carga_emocional": int(d.get("carga_emocional", 3)),
        "seguranca_psicologica": int(d.get("seguranca_psicologica", 3)),
        "apoio_percebido": int(d.get("apoio_percebido", 3)),
        "pressao_trabalho": int(d.get("pressao_trabalho", 3)),
        "bem_estar_geral": int(d.get("bem_estar_geral", 3)),
        "risco_burnout": int(d.get("risco_burnout", 1)),
        "observacao": d.get("observacao", "").strip()[:280],
        "setor": alias.setor,
    }

    obj, created = CheckinSemanalCorporativo.objects.update_or_create(
        empresa=alias.empresa,
        alias=alias,
        semana_referencia=ini_semana,
        defaults=defaults,
    )
    return JsonResponse({"ok": True, "criado": created}, status=201 if created else 200)
