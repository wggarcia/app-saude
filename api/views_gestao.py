import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F as models_F
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    AcaoCorporativa,
    ApiKeyEmpresa,
    DispositivoAutorizado,
    Empresa,
    EmpresaSetor,
    EmpresaUnidade,
    FuncionarioSST,
    IntegracaoRH,
    OnboardingPasso,
    PedidoApoioCorporativo,
    ProgramaCorporativo,
    SubscricaoEvento,
    TrialEmpresa,
    UsoApiEmpresa,
)
from .access_control import (
    contexto_navegacao_setorial,
    api_requer_plataforma_ti,
    api_requer_plataforma_ti_ou_gestor,
    api_requer_setor,
    requer_operacao_page,
    requer_plataforma_ti_page,
    requer_setor,
)
from .services.dashboard_core import setor_conta
from .views_dashboard import _empresa_autenticada


def _empresa_gestao(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return None
    return empresa


def _contexto_plataforma_ti(empresa):
    setor = setor_conta(empresa)
    contexto = {
        "empresa": {
            "return_url": "/gestao/",
            "return_label": "Gestão SST",
            "panel_url": "/sst/",
            "panel_label": "Painel SST",
            "reports_url": "/sst/relatorios/",
            "reports_label": "Relatórios SST",
        },
        "farmacia": {
            "return_url": "/farmacia/gestao/",
            "return_label": "Gestão Farmácia",
            "panel_url": "/dashboard-farmacia/",
            "panel_label": "Radar Farmácia",
            "reports_url": "/farmacia/gestao/",
            "reports_label": "Operação Farmácia",
        },
        "hospital": {
            "return_url": "/hospital/gestao/",
            "return_label": "Gestão Hospitalar",
            "panel_url": "/dashboard-hospital/",
            "panel_label": "Radar Hospital",
            "reports_url": "/hospital/gestao/",
            "reports_label": "Operação Hospital",
        },
        "plano_saude": {
            "return_url": "/plano-saude/gestao/",
            "return_label": "Gestão Operadora",
            "panel_url": "/dashboard-plano-saude/",
            "panel_label": "Radar Plano de Saúde",
            "reports_url": "/plano-saude/gestao/",
            "reports_label": "Operação Plano",
        },
    }
    return {
        "setor_conta": setor,
        **contexto.get(setor, contexto["empresa"]),
    }


def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


@requer_setor("empresa")
@requer_operacao_page
def gestao_corporativa(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return redirect("/")
    return render(request, "gestao_corporativa.html", {
        "empresa_nome": empresa.nome,
        **contexto_navegacao_setorial(request, "empresa"),
    })


@requer_setor("empresa", "farmacia", "hospital", "plano_saude")
@requer_plataforma_ti_page
def gestao_plataforma(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return redirect("/")
    contexto = _contexto_plataforma_ti(empresa)
    return render(request, "gestao_plataforma.html", {
        "empresa_nome": empresa.nome,
        **contexto,
    })


def portal_ti_unificado(request):
    """
    Entrada única da TI por empresa.
    Governo usa rota própria /governo/plataforma/.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    if setor_conta(empresa) == "governo":
        return redirect("/governo/plataforma/")
    return gestao_plataforma(request)


# ── APOIO ─────────────────────────────────────────────────────────────────────

@api_requer_setor("empresa")
def api_apoio_fila(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    status_filter = request.GET.get("status")
    qs = PedidoApoioCorporativo.objects.filter(empresa=empresa).select_related(
        "alias", "unidade", "setor", "turno"
    )
    if not status_filter:
        qs = qs.filter(status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE])
    elif status_filter != "todos":
        qs = qs.filter(status=status_filter)
    qs = qs.order_by("-criado_em")[:100]

    return JsonResponse({"pedidos": [
        {
            "id": p.id,
            "alias": p.alias.alias_publico,
            "unidade_nome": p.unidade.nome if p.unidade else None,
            "setor_nome": p.setor.nome if p.setor else None,
            "turno_nome": p.turno.nome if p.turno else None,
            "deseja_contato": p.deseja_contato,
            "canal_preferido": p.canal_preferido,
            "relato": p.relato,
            "status": p.status,
            "atendente": p.atendente,
            "resolucao": p.resolucao,
            "criado_em": p.criado_em.isoformat(),
            "concluido_em": p.concluido_em.isoformat() if p.concluido_em else None,
        }
        for p in qs
    ]})


@csrf_exempt
@api_requer_setor("empresa")
def api_apoio_atualizar(request, pedido_id):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    pedido = PedidoApoioCorporativo.objects.filter(id=pedido_id, empresa=empresa).first()
    if not pedido:
        return JsonResponse({"erro": "pedido nao encontrado"}, status=404)

    status_validos = [s[0] for s in PedidoApoioCorporativo.STATUS_CHOICES]
    novo_status = dados.get("status")
    if novo_status and novo_status not in status_validos:
        return JsonResponse({"erro": "status invalido"}, status=400)

    campos = []
    if novo_status:
        pedido.status = novo_status
        campos.append("status")
    if "atendente" in dados:
        pedido.atendente = (dados["atendente"] or "")[:160]
        campos.append("atendente")
    if "resolucao" in dados:
        pedido.resolucao = (dados["resolucao"] or "")
        campos.append("resolucao")

    if novo_status == PedidoApoioCorporativo.STATUS_CONCLUIDO and not pedido.concluido_em:
        pedido.concluido_em = timezone.now()
        campos.append("concluido_em")

    if campos:
        campos.append("atualizado_em")
        pedido.save(update_fields=campos)

    return JsonResponse({"ok": True, "status": pedido.status})


# ── PROGRAMAS ─────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("empresa")
def api_programas(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        status_filter = request.GET.get("status")
        qs = ProgramaCorporativo.objects.filter(empresa=empresa).select_related("unidade", "setor")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return JsonResponse({"programas": [
            {
                "id": p.id,
                "titulo": p.titulo,
                "tipo": p.tipo,
                "status": p.status,
                "owner": p.owner,
                "objetivo": p.objetivo,
                "unidade_nome": p.unidade.nome if p.unidade else None,
                "setor_nome": p.setor.nome if p.setor else None,
                "prazo": p.prazo.isoformat() if p.prazo else None,
                "resultado": p.resultado,
                "criado_em": p.criado_em.isoformat(),
                "encerrado_em": p.encerrado_em.isoformat() if p.encerrado_em else None,
                "total_acoes": p.acoes.filter(status__in=[
                    AcaoCorporativa.STATUS_ABERTA, AcaoCorporativa.STATUS_EM_ANDAMENTO
                ]).count(),
            }
            for p in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        titulo = (dados.get("titulo") or "").strip()
        owner = (dados.get("owner") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)
        if not owner:
            return JsonResponse({"erro": "owner obrigatorio"}, status=400)

        tipo = dados.get("tipo") or ProgramaCorporativo.TIPO_LIVRE
        if tipo not in dict(ProgramaCorporativo.TIPOS):
            tipo = ProgramaCorporativo.TIPO_LIVRE

        unidade = EmpresaUnidade.objects.filter(id=dados.get("unidade_id"), empresa=empresa).first() if dados.get("unidade_id") else None
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None

        prazo = None
        if dados.get("prazo"):
            try:
                from datetime import date
                prazo = date.fromisoformat(dados["prazo"])
            except (ValueError, TypeError):
                pass

        programa = ProgramaCorporativo.objects.create(
            empresa=empresa,
            titulo=titulo,
            tipo=tipo,
            owner=owner,
            objetivo=(dados.get("objetivo") or "").strip(),
            unidade=unidade,
            setor=setor,
            prazo=prazo,
            status=ProgramaCorporativo.STATUS_RASCUNHO,
        )
        return JsonResponse({"id": programa.id, "titulo": programa.titulo})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


@csrf_exempt
@api_requer_setor("empresa")
def api_programa_status(request, programa_id):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    programa = ProgramaCorporativo.objects.filter(id=programa_id, empresa=empresa).first()
    if not programa:
        return JsonResponse({"erro": "programa nao encontrado"}, status=404)

    novo_status = dados.get("status")
    status_validos = [s[0] for s in ProgramaCorporativo.STATUS_CHOICES]
    if novo_status not in status_validos:
        return JsonResponse({"erro": "status invalido"}, status=400)

    campos = ["status", "atualizado_em"]
    programa.status = novo_status

    if novo_status == ProgramaCorporativo.STATUS_ENCERRADO:
        programa.encerrado_em = timezone.now()
        programa.resultado = (dados.get("resultado") or "").strip()
        campos += ["encerrado_em", "resultado"]

    programa.save(update_fields=campos)
    return JsonResponse({"ok": True, "status": programa.status})


# ── AÇÕES ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_setor("empresa")
def api_acoes(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        status_filter = request.GET.get("status")
        qs = AcaoCorporativa.objects.filter(empresa=empresa).select_related(
            "unidade", "setor", "programa", "pedido_apoio"
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            qs = qs.exclude(status__in=[AcaoCorporativa.STATUS_CONCLUIDA, AcaoCorporativa.STATUS_CANCELADA])
        return JsonResponse({"acoes": [
            {
                "id": a.id,
                "titulo": a.titulo,
                "descricao": a.descricao,
                "status": a.status,
                "origem": a.origem,
                "owner": a.owner,
                "unidade_nome": a.unidade.nome if a.unidade else None,
                "setor_nome": a.setor.nome if a.setor else None,
                "prazo": a.prazo.isoformat() if a.prazo else None,
                "evidencia": a.evidencia,
                "programa_titulo": a.programa.titulo if a.programa else None,
                "criado_em": a.criado_em.isoformat(),
                "concluido_em": a.concluido_em.isoformat() if a.concluido_em else None,
            }
            for a in qs
        ]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "json invalido"}, status=400)
        titulo = (dados.get("titulo") or "").strip()
        owner = (dados.get("owner") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "titulo obrigatorio"}, status=400)
        if not owner:
            return JsonResponse({"erro": "owner obrigatorio"}, status=400)

        origem = dados.get("origem") or AcaoCorporativa.ORIGEM_MANUAL
        if origem not in dict(AcaoCorporativa.ORIGENS):
            origem = AcaoCorporativa.ORIGEM_MANUAL

        unidade = EmpresaUnidade.objects.filter(id=dados.get("unidade_id"), empresa=empresa).first() if dados.get("unidade_id") else None
        setor = EmpresaSetor.objects.filter(id=dados.get("setor_id"), empresa=empresa).first() if dados.get("setor_id") else None
        programa = ProgramaCorporativo.objects.filter(id=dados.get("programa_id"), empresa=empresa).first() if dados.get("programa_id") else None

        prazo = None
        if dados.get("prazo"):
            try:
                from datetime import date
                prazo = date.fromisoformat(dados["prazo"])
            except (ValueError, TypeError):
                pass

        acao = AcaoCorporativa.objects.create(
            empresa=empresa,
            titulo=titulo,
            descricao=(dados.get("descricao") or "").strip(),
            owner=owner,
            origem=origem,
            unidade=unidade,
            setor=setor,
            prazo=prazo,
            programa=programa,
            status=AcaoCorporativa.STATUS_ABERTA,
        )
        return JsonResponse({"id": acao.id, "titulo": acao.titulo})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


@csrf_exempt
@api_requer_setor("empresa")
def api_acao_status(request, acao_id):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request)
    if dados is None:
        return JsonResponse({"erro": "json invalido"}, status=400)

    acao = AcaoCorporativa.objects.filter(id=acao_id, empresa=empresa).first()
    if not acao:
        return JsonResponse({"erro": "acao nao encontrada"}, status=404)

    novo_status = dados.get("status")
    status_validos = [s[0] for s in AcaoCorporativa.STATUS_CHOICES]
    if novo_status not in status_validos:
        return JsonResponse({"erro": "status invalido"}, status=400)

    campos = ["status", "atualizado_em"]
    acao.status = novo_status

    if "evidencia" in dados:
        acao.evidencia = (dados["evidencia"] or "").strip()
        campos.append("evidencia")

    if novo_status == AcaoCorporativa.STATUS_CONCLUIDA and not acao.concluido_em:
        acao.concluido_em = timezone.now()
        campos.append("concluido_em")

    acao.save(update_fields=campos)
    return JsonResponse({"ok": True, "status": acao.status})


# ── RESUMO DA FILA (para o dashboard) ────────────────────────────────────────

@api_requer_setor("empresa")
def api_gestao_resumo(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    apoio_aberto = PedidoApoioCorporativo.objects.filter(
        empresa=empresa,
        status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE]
    ).count()

    acoes_abertas = AcaoCorporativa.objects.filter(
        empresa=empresa,
        status__in=[AcaoCorporativa.STATUS_ABERTA, AcaoCorporativa.STATUS_EM_ANDAMENTO]
    ).count()

    programas_ativos = ProgramaCorporativo.objects.filter(
        empresa=empresa, status=ProgramaCorporativo.STATUS_ATIVO
    ).count()

    return JsonResponse({
        "apoio_aberto": apoio_aberto,
        "acoes_abertas": acoes_abertas,
        "programas_ativos": programas_ativos,
        "total_atencao": apoio_aberto + acoes_abertas,
    })


# ── TRIAL / SELF-SERVICE ONBOARDING ──────────────────────────────────────────

_PASSOS_ORDENADOS = [p[0] for p in OnboardingPasso.PASSOS]


def _trial_dict(trial):
    return {
        "ativo": trial.ativo(),
        "dias_restantes": trial.dias_restantes(),
        "expira_em": trial.expira_em.strftime("%d/%m/%Y"),
        "expiracao_em": trial.expira_em.isoformat(),
        "convertido": trial.convertido,
    }


def _onboarding_dict(empresa):
    concluidos = set(
        OnboardingPasso.objects.filter(empresa=empresa).values_list("passo", flat=True)
    )
    passos = []
    for codigo, label in OnboardingPasso.PASSOS:
        passos.append({
            "passo": codigo,
            "label": label,
            "concluido": codigo in concluidos,
        })
    total = len(passos)
    feitos = len(concluidos)
    return {
        "passos": passos,
        "percentual": round(feitos / total * 100) if total else 0,
        "completo": feitos == total,
    }


@api_requer_plataforma_ti_ou_gestor
def api_trial_status(request):
    """GET — situação do trial e checklist de onboarding."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    trial = TrialEmpresa.objects.filter(empresa=empresa).first()
    onboarding = _onboarding_dict(empresa)
    trial_payload = _trial_dict(trial) if trial else None
    if trial_payload:
        status = "trial" if trial_payload["ativo"] else "expirado"
    else:
        status = "ativo" if empresa.ativo else "inativo"
    return JsonResponse({
        "status": status,
        "setor": setor_conta(empresa),
        "trial": trial_payload,
        "onboarding": onboarding,
        "onboarding_passos": onboarding["passos"],
    })


@csrf_exempt
@api_requer_plataforma_ti_ou_gestor
def api_trial_ativar(request):
    """POST — inicia trial self-service. Idempotente."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    trial, criado = TrialEmpresa.objects.get_or_create(
        empresa=empresa,
        defaults={"expira_em": timezone.now() + timedelta(days=settings.TRIAL_DAYS)},
    )
    return JsonResponse({"trial": _trial_dict(trial), "novo": criado}, status=201 if criado else 200)


@csrf_exempt
@api_requer_plataforma_ti_ou_gestor
def api_onboarding_passo(request, passo):
    """POST — marca um passo do onboarding como concluído."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    codigos_validos = {p[0] for p in OnboardingPasso.PASSOS}
    if passo not in codigos_validos:
        return JsonResponse({"erro": "passo inválido"}, status=400)

    obj, criado = OnboardingPasso.objects.get_or_create(empresa=empresa, passo=passo)
    return JsonResponse({"passo": passo, "novo": criado, "onboarding": _onboarding_dict(empresa)})


# ── INTEGRAÇÕES RH ────────────────────────────────────────────────────────────

def _integracao_dict(i):
    return {
        "id": i.id,
        "sistema": i.sistema,
        "sistema_label": i.get_sistema_display(),
        "nome": i.nome,
        "status": i.status,
        "ativo": i.status == "ativo",
        "webhook_secret": i.webhook_secret,
        "secret": i.webhook_secret,
        "endpoint_destino": i.endpoint_destino,
        "url_callback": i.endpoint_destino,
        "funcionarios_importados": i.funcionarios_importados,
        "total_funcionarios": i.funcionarios_importados,
        "ultimo_sync_em": i.ultimo_sync_em.strftime("%d/%m/%Y %H:%M") if i.ultimo_sync_em else None,
        "ultima_sync": i.ultimo_sync_em.isoformat() if i.ultimo_sync_em else None,
        "ultimo_erro": i.ultimo_erro,
        "criado_em": i.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
@api_requer_plataforma_ti_ou_gestor
def api_integracoes(request):
    """GET lista / POST cria integração com sistema de RH."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = IntegracaoRH.objects.filter(empresa=empresa)
        return JsonResponse({"integracoes": [_integracao_dict(i) for i in qs]})

    if request.method == "POST":
        dados = _parse_json(request)
        if dados is None:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        sistema = dados.get("sistema", "")
        sistemas_validos = {s[0] for s in IntegracaoRH.SISTEMAS}
        if sistema not in sistemas_validos:
            return JsonResponse({"erro": "sistema inválido", "opcoes": list(sistemas_validos)}, status=400)

        integracao, criada = IntegracaoRH.objects.get_or_create(
            empresa=empresa,
            sistema=sistema,
            defaults={
                "nome": dados.get("nome") or f"Integração {sistema.upper()}",
                "endpoint_destino": dados.get("endpoint_destino") or dados.get("url_callback") or "",
                "status": "ativo" if dados.get("ativo") else "inativo",
            },
        )
        if not criada:
            if "nome" in dados:
                integracao.nome = dados["nome"]
            if "endpoint_destino" in dados or "url_callback" in dados:
                integracao.endpoint_destino = dados.get("endpoint_destino") or dados.get("url_callback") or ""
            if "ativo" in dados:
                integracao.status = "ativo" if dados.get("ativo") else "inativo"
            integracao.save(update_fields=["nome", "endpoint_destino", "status", "atualizado_em"])

        return JsonResponse({"integracao": _integracao_dict(integracao)}, status=201 if criada else 200)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_integracao_webhook(request, sistema):
    """POST — recebe payload do sistema de RH e importa funcionários."""
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    # Localiza integração pela empresa via header X-Empresa-Id
    empresa_id = request.headers.get("X-Empresa-Id") or request.GET.get("empresa_id")
    if not empresa_id:
        return JsonResponse({"erro": "X-Empresa-Id obrigatório"}, status=400)

    integracao = IntegracaoRH.objects.filter(
        empresa_id=empresa_id, sistema=sistema
    ).select_related("empresa").first()
    if not integracao:
        return JsonResponse({"erro": "integração não encontrada"}, status=404)

    # Valida assinatura HMAC
    secret = integracao.webhook_secret.encode()
    sig_header = request.headers.get("X-Signature", "")
    body = request.body
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not sig_header or not hmac.compare_digest(sig_header, expected):
        return JsonResponse({"erro": "assinatura inválida"}, status=401)

    try:
        payload = json.loads(body.decode("utf-8") or "[]")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    funcionarios = payload if isinstance(payload, list) else payload.get("funcionarios", [])

    importados = 0
    erros = []
    with transaction.atomic():
        for item in funcionarios[:500]:
            cpf = (item.get("cpf") or "").replace(".", "").replace("-", "").strip()
            nome = (item.get("nome") or "").strip()
            if not cpf or not nome:
                erros.append({"item": item, "erro": "cpf e nome obrigatórios"})
                continue
            _, criado = FuncionarioSST.objects.get_or_create(
                empresa=integracao.empresa,
                cpf=cpf,
                defaults={
                    "nome": nome,
                    "cargo": item.get("cargo", ""),
                    "setor": item.get("setor", ""),
                    "data_admissao": item.get("data_admissao") or None,
                },
            )
            if not criado:
                FuncionarioSST.objects.filter(empresa=integracao.empresa, cpf=cpf).update(
                    nome=nome,
                    cargo=item.get("cargo", ""),
                    setor=item.get("setor", ""),
                )
            importados += 1

    integracao.funcionarios_importados += importados
    integracao.ultimo_sync_em = timezone.now()
    integracao.status = "ativo"
    integracao.ultimo_erro = ""
    integracao.save(update_fields=["funcionarios_importados", "ultimo_sync_em", "status", "ultimo_erro", "atualizado_em"])

    # Marca onboarding se for o primeiro import
    if importados > 0:
        OnboardingPasso.objects.get_or_create(empresa=integracao.empresa, passo="primeiro_funcionario")

    return JsonResponse({"importados": importados, "erros": erros[:20]})


@csrf_exempt
@api_requer_plataforma_ti_ou_gestor
def api_integracao_status(request, integracao_id):
    """POST — ativa, desativa ou reseta uma integração."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    integracao = IntegracaoRH.objects.filter(id=integracao_id, empresa=empresa).first()
    if not integracao:
        return JsonResponse({"erro": "integração não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_integracao_dict(integracao))

    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    dados = _parse_json(request) or {}
    novo_status = dados.get("status")
    if novo_status not in {s[0] for s in IntegracaoRH.STATUS}:
        return JsonResponse({"erro": "status inválido"}, status=400)

    integracao.status = novo_status
    if novo_status == "inativo":
        integracao.ultimo_erro = ""
    integracao.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
    return JsonResponse({"ok": True, "integracao": _integracao_dict(integracao)})


# ── API KEYS (acesso programático) ────────────────────────────────────────────

def _key_dict(k, mostrar_chave=False):
    return {
        "id": k.id,
        "nome": k.nome,
        "chave": k.chave if mostrar_chave else k.chave[:8] + "…",
        "ativa": k.ativa,
        "total_chamadas": k.total_chamadas,
        "ultimo_uso_em": k.ultimo_uso_em.strftime("%d/%m/%Y %H:%M") if k.ultimo_uso_em else None,
        "criado_em": k.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
@api_requer_plataforma_ti_ou_gestor
def api_chaves(request):
    """GET lista / POST cria API key para a empresa."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        qs = ApiKeyEmpresa.objects.filter(empresa=empresa, ativa=True)
        return JsonResponse({"chaves": [_key_dict(k) for k in qs]})

    if request.method == "POST":
        dados = _parse_json(request) or {}
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        if ApiKeyEmpresa.objects.filter(empresa=empresa, ativa=True).count() >= 10:
            return JsonResponse({"erro": "limite de 10 chaves ativas atingido"}, status=400)

        chave = secrets.token_hex(32)
        key = ApiKeyEmpresa.objects.create(empresa=empresa, nome=nome, chave=chave)
        return JsonResponse({"chave": _key_dict(key, mostrar_chave=True)}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
@api_requer_plataforma_ti_ou_gestor
def api_chave_revogar(request, chave_id):
    """POST — revoga (desativa permanentemente) uma API key."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    key = ApiKeyEmpresa.objects.filter(id=chave_id, empresa=empresa, ativa=True).first()
    if not key:
        return JsonResponse({"erro": "chave não encontrada"}, status=404)

    key.ativa = False
    key.revogada_em = timezone.now()
    key.save(update_fields=["ativa", "revogada_em"])
    return JsonResponse({"ok": True})


@api_requer_plataforma_ti_ou_gestor
def api_uso_api(request):
    """GET — consumo mensal de API por endpoint."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    ano_mes = request.GET.get("ano_mes") or timezone.now().strftime("%Y-%m")
    qs = UsoApiEmpresa.objects.filter(empresa=empresa, ano_mes=ano_mes).order_by("-chamadas")

    total = sum(u.chamadas for u in qs)
    ultima_chamada = (
        ApiKeyEmpresa.objects.filter(empresa=empresa, ultimo_uso_em__isnull=False)
        .order_by("-ultimo_uso_em")
        .values_list("ultimo_uso_em", flat=True)
        .first()
    )

    uso = [
        {"endpoint": u.endpoint, "chamadas": u.chamadas}
        for u in qs
    ]
    return JsonResponse({
        "ano_mes": ano_mes,
        "total_chamadas": total,
        "por_endpoint": uso,
        "uso": uso,
        "ultima_chamada": ultima_chamada.isoformat() if ultima_chamada else None,
    })


# ── WEBHOOKS / SEGURANÇA / LOGS DA PLATAFORMA ────────────────────────────────

@csrf_exempt
@api_requer_plataforma_ti
def api_plataforma_webhooks(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    if request.method == "GET":
        agrupado = {}
        for sub in SubscricaoEvento.objects.filter(empresa=empresa).order_by("-criado_em"):
            item = agrupado.setdefault(sub.url_destino, {
                "id": sub.id,
                "url": sub.url_destino,
                "eventos": [],
                "ultimo_disparo": None,
            })
            if sub.tipo_evento_pattern not in item["eventos"]:
                item["eventos"].append(sub.tipo_evento_pattern)
        return JsonResponse({"webhooks": list(agrupado.values())})

    if request.method == "POST":
        dados = _parse_json(request) or {}
        url = (dados.get("url") or "").strip()
        eventos = [str(evento).strip() for evento in (dados.get("eventos") or []) if str(evento).strip()]
        if not url:
            return JsonResponse({"erro": "url obrigatoria"}, status=400)
        if not eventos:
            return JsonResponse({"erro": "selecione ao menos um evento"}, status=400)

        existentes = set(
            SubscricaoEvento.objects.filter(empresa=empresa, url_destino=url)
            .values_list("tipo_evento_pattern", flat=True)
        )
        criados = 0
        for evento in eventos:
            if evento in existentes:
                continue
            SubscricaoEvento.objects.create(
                empresa=empresa,
                url_destino=url,
                tipo_evento_pattern=evento,
            )
            criados += 1

        return JsonResponse({"criado": True, "novos_eventos": criados}, status=201)

    if request.method == "DELETE":
        dados = _parse_json(request) or {}
        webhook_id = dados.get("id")
        webhook = SubscricaoEvento.objects.filter(empresa=empresa, id=webhook_id).first()
        if not webhook:
            return JsonResponse({"erro": "webhook nao encontrado"}, status=404)
        SubscricaoEvento.objects.filter(
            empresa=empresa,
            url_destino=webhook.url_destino,
        ).delete()
        return JsonResponse({"removido": True})

    return JsonResponse({"erro": "metodo nao permitido"}, status=405)


def _auditoria_plataforma_ti(empresa):
    from .models import ASOOcupacional, SolicitacaoExame, eSocialEventoSST

    eventos = []

    for dispositivo in DispositivoAutorizado.objects.filter(empresa=empresa).order_by("-ultimo_acesso")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(dispositivo.ultimo_acesso),
            "sistema": "plataforma",
            "acao": "acessar",
            "objeto": dispositivo.apelido or dispositivo.device_id,
            "status": "ok" if dispositivo.ativo else "warn",
            "ip": dispositivo.ip or "",
            "detalhes": "Sessao rastreada por dispositivo autorizado.",
        })

    for integracao in IntegracaoRH.objects.filter(empresa=empresa).order_by("-atualizado_em")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(integracao.atualizado_em),
            "sistema": "integracao_rh",
            "acao": "editar" if integracao.funcionarios_importados else "criar",
            "objeto": integracao.nome or integracao.get_sistema_display(),
            "status": "ok" if integracao.status == "ativo" else ("erro" if integracao.status == "erro" else "warn"),
            "ip": "",
            "detalhes": f"Status {integracao.status}. Funcionarios importados: {integracao.funcionarios_importados}.",
        })

    for chave in ApiKeyEmpresa.objects.filter(empresa=empresa).order_by("-criado_em")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(chave.revogada_em or chave.criado_em),
            "sistema": "api",
            "acao": "excluir" if chave.revogada_em else "criar",
            "objeto": chave.nome,
            "status": "warn" if chave.revogada_em else "ok",
            "ip": "",
            "detalhes": "Chave revogada." if chave.revogada_em else "Chave criada para integracoes externas.",
        })

    for webhook in SubscricaoEvento.objects.filter(empresa=empresa).order_by("-criado_em")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(webhook.criado_em),
            "sistema": "plataforma",
            "acao": "criar",
            "objeto": webhook.url_destino,
            "status": "ok" if webhook.ativo else "warn",
            "ip": "",
            "detalhes": f"Webhook inscrito para {webhook.tipo_evento_pattern}.",
        })

    for aso in ASOOcupacional.objects.filter(empresa=empresa).select_related("funcionario").order_by("-criado_em")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(aso.criado_em),
            "sistema": "sst",
            "acao": "criar",
            "objeto": aso.funcionario.nome,
            "status": "ok",
            "ip": "",
            "detalhes": f"ASO {aso.get_tipo_display()} emitido com resultado {aso.get_resultado_display()}.",
        })

    for solicitacao in SolicitacaoExame.objects.filter(empresa=empresa).select_related("funcionario").order_by("-data_solicitacao")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(solicitacao.data_solicitacao),
            "sistema": "sst",
            "acao": "criar" if solicitacao.status == "pendente" else "editar",
            "objeto": solicitacao.funcionario.nome,
            "status": "ok" if solicitacao.status in {"agendado", "realizado"} else ("warn" if solicitacao.status == "pendente" else "erro"),
            "ip": "",
            "detalhes": f"Solicitacao {solicitacao.get_tipo_aso_display()} para {solicitacao.clinica_nome_externo or getattr(solicitacao.clinica, 'nome', 'clinica interna')} — status {solicitacao.status}.",
        })

    for evento in eSocialEventoSST.objects.filter(empresa=empresa).order_by("-criado_em")[:20]:
        eventos.append({
            "timestamp": timezone.localtime(evento.criado_em),
            "sistema": "esocial",
            "acao": "editar" if evento.status in {"erro", "pendente"} else "exportar",
            "objeto": evento.tipo_evento,
            "status": "ok" if evento.status == "transmitido" else ("erro" if evento.status == "erro" else "warn"),
            "ip": "",
            "detalhes": evento.mensagem_erro or evento.referencia or f"Evento {evento.tipo_evento} com status {evento.status}.",
        })

    eventos.sort(key=lambda item: item["timestamp"], reverse=True)
    return eventos


@api_requer_plataforma_ti
def api_plataforma_seguranca(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    dispositivos = list(
        DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).order_by("-ultimo_acesso")[:20]
    )
    integracoes = list(IntegracaoRH.objects.filter(empresa=empresa))
    chaves = list(ApiKeyEmpresa.objects.filter(empresa=empresa))
    checklist = [
        {
            "item": "Acesso da Plataforma TI restrito a usuário com perfil técnico",
            "ok": True,
        },
        {
            "item": "Sessões rastreadas por dispositivo autorizado",
            "ok": bool(dispositivos),
        },
        {
            "item": "Integrações RH protegidas por segredo de webhook",
            "ok": all(bool(item.webhook_secret) for item in integracoes) if integracoes else False,
        },
        {
            "item": "Chaves de API sob governança e revogação centralizada",
            "ok": bool(chaves) and all(item.ativa or item.revogada_em for item in chaves),
        },
    ]

    auditoria = []
    for item in _auditoria_plataforma_ti(empresa)[:8]:
        auditoria.append({
            "timestamp": item["timestamp"].strftime("%d/%m/%Y %H:%M"),
            "acao": item["acao"],
            "sistema": item["sistema"],
            "status": item["status"],
            "detalhes": item["detalhes"],
        })

    return JsonResponse({
        "lgpd_checklist": checklist,
        "2fa_ativo": False,
        "sessoes_ativas": [
            {
                "id": item.device_id,
                "dispositivo": item.apelido or item.device_id,
                "ip": item.ip,
                "ultimo_acesso": timezone.localtime(item.ultimo_acesso).strftime("%d/%m/%Y %H:%M"),
            }
            for item in dispositivos
        ],
        "auditoria": auditoria,
    })


@api_requer_plataforma_ti
def api_plataforma_logs(request):
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    logs = _auditoria_plataforma_ti(empresa)

    sistema = (request.GET.get("sistema") or "").strip().lower()
    acao = (request.GET.get("acao") or "").strip().lower()
    data_inicio = (request.GET.get("data_inicio") or "").strip()
    data_fim = (request.GET.get("data_fim") or "").strip()

    if sistema:
        logs = [item for item in logs if item["sistema"] == sistema]
    if acao:
        logs = [item for item in logs if item["acao"] == acao]

    if data_inicio:
        try:
            from datetime import datetime as _dt
            ini = _dt.fromisoformat(data_inicio).date()
            logs = [item for item in logs if item["timestamp"].date() >= ini]
        except ValueError:
            pass
    if data_fim:
        try:
            from datetime import datetime as _dt
            fim = _dt.fromisoformat(data_fim).date()
            logs = [item for item in logs if item["timestamp"].date() <= fim]
        except ValueError:
            pass

    total = len(logs)
    try:
        pagina = max(int(request.GET.get("pagina", 1)), 1)
    except (TypeError, ValueError):
        pagina = 1
    por_pagina = 20
    inicio = (pagina - 1) * por_pagina
    fatia = logs[inicio:inicio + por_pagina]

    return JsonResponse({
        "logs": [
            {
                "timestamp": item["timestamp"].strftime("%d/%m/%Y %H:%M"),
                "sistema": item["sistema"],
                "acao": item["acao"],
                "objeto": item["objeto"],
                "status": item["status"],
                "ip": item["ip"],
                "detalhes": item["detalhes"],
            }
            for item in fatia
        ],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    })


# ── BENCHMARK SETORIAL ────────────────────────────────────────────────────────

def api_benchmark(request):
    """GET — compara métricas da empresa com médias do setor."""
    empresa = _empresa_gestao(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)

    from .models import (
        ASOOcupacional, CATOcupacional, FuncionarioSST,
        AfastamentoSST, TreinamentoNR, Empresa,
    )

    total_func = FuncionarioSST.objects.filter(empresa=empresa).count()
    total_asos = ASOOcupacional.objects.filter(empresa=empresa).count()
    total_cats = CATOcupacional.objects.filter(empresa=empresa).count()
    total_afastamentos = AfastamentoSST.objects.filter(empresa=empresa).count()
    total_treinamentos = TreinamentoNR.objects.filter(empresa=empresa).count()

    # Médias gerais (todas as empresas do setor empresa)
    empresas_setor = Empresa.objects.filter(tipo_conta=Empresa.TIPO_EMPRESA, ativo=True)
    n_empresas = empresas_setor.count() or 1

    media_func = FuncionarioSST.objects.filter(empresa__in=empresas_setor).count() / n_empresas
    media_asos = ASOOcupacional.objects.filter(empresa__in=empresas_setor).count() / n_empresas
    media_cats = CATOcupacional.objects.filter(empresa__in=empresas_setor).count() / n_empresas
    media_afastamentos = AfastamentoSST.objects.filter(empresa__in=empresas_setor).count() / n_empresas
    media_treinamentos = TreinamentoNR.objects.filter(empresa__in=empresas_setor).count() / n_empresas

    def _pct(empresa_val, media_val):
        if media_val == 0:
            return None
        return round((empresa_val - media_val) / media_val * 100, 1)

    return JsonResponse({
        "empresa": {
            "funcionarios": total_func,
            "asos": total_asos,
            "cats": total_cats,
            "afastamentos": total_afastamentos,
            "treinamentos": total_treinamentos,
        },
        "media_setor": {
            "funcionarios": round(media_func, 1),
            "asos": round(media_asos, 1),
            "cats": round(media_cats, 1),
            "afastamentos": round(media_afastamentos, 1),
            "treinamentos": round(media_treinamentos, 1),
        },
        "vs_setor_pct": {
            "funcionarios": _pct(total_func, media_func),
            "asos": _pct(total_asos, media_asos),
            "cats": _pct(total_cats, media_cats),
            "afastamentos": _pct(total_afastamentos, media_afastamentos),
            "treinamentos": _pct(total_treinamentos, media_treinamentos),
        },
        "nota": f"Comparado com {n_empresas} empresa(s) ativa(s) na plataforma.",
    })


# ── AUTENTICAÇÃO VIA API KEY (helper para endpoints públicos) ─────────────────

def _empresa_por_api_key(request):
    """Autentica via header Authorization: ApiKey <chave> e registra uso."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("ApiKey "):
        return None, None
    chave = auth[7:].strip()
    key = None
    for candidata in ApiKeyEmpresa.objects.filter(ativa=True).select_related("empresa"):
        if hmac.compare_digest(candidata.chave, chave):
            key = candidata
            break
    if not key:
        return None, None

    now = timezone.now()
    key.total_chamadas += 1
    key.ultimo_uso_em = now
    key.save(update_fields=["total_chamadas", "ultimo_uso_em"])

    ano_mes = now.strftime("%Y-%m")
    endpoint = request.path[:120]
    UsoApiEmpresa.objects.update_or_create(
        empresa=key.empresa, api_key=key, ano_mes=ano_mes, endpoint=endpoint,
        defaults={"chamadas": 0},
    )
    UsoApiEmpresa.objects.filter(
        empresa=key.empresa, api_key=key, ano_mes=ano_mes, endpoint=endpoint
    ).update(chamadas=models_F("chamadas") + 1)

    return key.empresa, key


def api_dados_empresa(request):
    """GET — exporta dados SST da empresa via API Key (para BI, TOTVS, etc.)."""
    empresa, key = _empresa_por_api_key(request)
    if not empresa:
        return JsonResponse({"erro": "Authorization: ApiKey <chave> inválida"}, status=401)

    from .models import ASOOcupacional, FuncionarioSST

    # .values() bypassa from_db_value do EncryptedCPFField — iteramos objetos para descriptografar.
    funcionarios = [
        {
            "id": f.id,
            "nome": f.nome,
            "cpf": f.cpf,
            "cargo": f.cargo,
            "setor": f.setor,
            "data_admissao": f.data_admissao,
            "ativo": f.ativo,
        }
        for f in FuncionarioSST.objects.filter(empresa=empresa).only(
            "id", "nome", "cpf", "cargo", "setor", "data_admissao", "ativo"
        )[:1000]
    ]
    asos_recentes = list(
        ASOOcupacional.objects.filter(empresa=empresa)
        .order_by("-data_emissao")
        .values("id", "funcionario_id", "tipo", "resultado", "data_emissao", "data_validade")[:500]
    )

    return JsonResponse({
        "empresa": empresa.nome,
        "funcionarios": funcionarios,
        "asos_recentes": asos_recentes,
        "gerado_em": timezone.now().isoformat(),
    })
