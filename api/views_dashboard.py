from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta
import json
from .models import RegistroSintoma, DispositivoAutorizado, EmpresaUsuario, FinanceiroEventoSaaS, DonoAuditoriaAcao, AlertaGovernamental, DonoSaaS
from .inteligencia import nivel_risco
from .models import Empresa
from .planos import PACOTES_SAAS, detalhes_pacote, normalizar_ciclo, normalizar_codigo_pacote
from .push_service import enviar_alerta_governamental, push_disponivel
from .governanca import registrar_auditoria_institucional
from .command_ai import build_command_ai_payload
from .access_control import (
    api_requer_operacao_ou_gerencia,
    contexto_navegacao_setorial,
    destino_por_perfil,
    perfil_principal,
    principal_pode_configurar_ti,
    requer_gerencia_page,
    requer_operacao_page,
    requer_plataforma_ti_page,
    requer_rh_page,
    requer_setor,
)
from .services.auth_session import dono_autenticado_from_request, empresa_autenticada_from_request
from .services.dashboard_core import (
    build_owner_resumo_payload,
    dashboard_return_url,
    dashboard_url_por_setor,
    onboarding_eventos,
    onboarding_cliente,
    onboarding_snapshot,
    playbook_cliente,
    segmento_empresa,
    setor_conta,
    setor_label,
    status_contrato,
)
import csv



# API (JSON)
def dados_dashboard(request):
    total = RegistroSintoma.objects.count()

    return JsonResponse({
        "total_casos": total,
        "risco": nivel_risco()
    })


def _empresa_autenticada(request):
    return empresa_autenticada_from_request(request)


def _dono_autenticado(request):
    return dono_autenticado_from_request(request)


def _principal_label(request):
    principal = getattr(request, "principal", None)
    if principal:
        return getattr(principal, "nome", "") or getattr(principal, "email", "") or str(principal.id)
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa.nome
    return "sistema"


def _empresa_publica_app():
    from .views import _empresa_app_publico
    return _empresa_app_publico()


def _sincronizar_alerta_no_app_publico(alerta):
    if not alerta.protocolo or not alerta.empresa_id:
        return None

    empresa_publica = _empresa_publica_app()
    if alerta.empresa_id == empresa_publica.id:
        return alerta

    from api.middleware import _rls_set_empresa

    empresa_origem_id = alerta.empresa_id
    _rls_set_empresa(empresa_publica.id)
    try:
        espelho = (
            AlertaGovernamental.objects
            .filter(empresa=empresa_publica, protocolo=alerta.protocolo)
            .order_by("-id")
            .first()
        )
        dados = {
            "titulo": alerta.titulo,
            "mensagem": alerta.mensagem,
            "estado": alerta.estado,
            "cidade": alerta.cidade,
            "bairro": alerta.bairro,
            "nivel": alerta.nivel,
            "ativo": alerta.ativo,
            "status": alerta.status,
            "justificativa": alerta.justificativa,
            "criado_por": alerta.criado_por,
            "revisado_por": alerta.revisado_por,
            "aprovado_por": alerta.aprovado_por,
            "aprovado_em": alerta.aprovado_em,
            "publicado_em": alerta.publicado_em,
            "revogado_em": alerta.revogado_em,
        }
        if espelho is None:
            espelho = AlertaGovernamental.objects.create(
                empresa=empresa_publica,
                protocolo=alerta.protocolo,
                **dados,
            )
        else:
            for campo, valor in dados.items():
                setattr(espelho, campo, valor)
            espelho.save(update_fields=[*dados.keys()])
        return espelho
    finally:
        _rls_set_empresa(empresa_origem_id)


def _remover_alerta_do_app_publico(alerta):
    if not alerta.protocolo or not alerta.empresa_id:
        return

    empresa_publica = _empresa_publica_app()
    if alerta.empresa_id == empresa_publica.id:
        return

    from api.middleware import _rls_set_empresa

    empresa_origem_id = alerta.empresa_id
    _rls_set_empresa(empresa_publica.id)
    try:
        AlertaGovernamental.objects.filter(
            empresa=empresa_publica,
            protocolo=alerta.protocolo,
        ).delete()
    finally:
        _rls_set_empresa(empresa_origem_id)


def _principal_pode_configurar_ti(request, empresa):
    if not empresa:
        return False
    return principal_pode_configurar_ti(request)


def _atribuir_permissao_ti(empresa, usuario, concedido_por):
    try:
        from .models import RBACAtribuicao, RBACPermissao

        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo="plataforma_ti",
            defaults={
                "descricao": "Acesso exclusivo à Plataforma TI",
                "modulo": "ti",
            },
        )
        atribuicao, criada = RBACAtribuicao.objects.get_or_create(
            empresa=empresa,
            usuario=usuario,
            permissao=permissao,
            defaults={"concedido_por": concedido_por, "ativo": True},
        )
        if not criada and not atribuicao.ativo:
            atribuicao.ativo = True
            atribuicao.concedido_por = concedido_por or atribuicao.concedido_por
            atribuicao.save(update_fields=["ativo", "concedido_por", "atualizado_em"])
    except Exception:
        # Ambiente sem tabela RBAC migrada continua funcional via cargo TI.
        pass


def _status_contrato(empresa, agora):
    return status_contrato(empresa, agora)


def _segmento_empresa(empresa):
    return segmento_empresa(empresa)


def _setor_conta(empresa):
    return setor_conta(empresa)


def _dashboard_url_por_setor(setor):
    return dashboard_url_por_setor(setor)


def _setor_label(setor):
    return setor_label(setor)


def _registrar_auditoria_dono(dono, acao, empresa=None, detalhes=""):
    DonoAuditoriaAcao.objects.create(
        dono=dono,
        empresa=empresa,
        acao=acao,
        detalhes=detalhes or "",
    )


def _playbook_cliente(status_contrato, uso_usuarios, uso_dispositivos, dias_para_expirar, registros_24h, suspeitos_24h):
    return playbook_cliente(status_contrato, uso_usuarios, uso_dispositivos, dias_para_expirar, registros_24h, suspeitos_24h)


def _onboarding_eventos(empresa):
    return onboarding_eventos(empresa)


def _onboarding_cliente(empresa, usuarios_ativos, dispositivos_ativos, registros_24h):
    return onboarding_cliente(empresa, usuarios_ativos, dispositivos_ativos, registros_24h)


# HTML (dashboard)
def _render_dashboard(request, variant):
    empresa = _empresa_autenticada(request)
    empresa_id = request.GET.get("empresa_id") or request.COOKIES.get("empresa_id")

    if empresa is None and not empresa_id:
        return redirect("/")

    if empresa is None:
        empresa = Empresa.objects.filter(id=empresa_id).first()

    if not empresa:
        return redirect("/")

    # 🔥 BLOQUEIO CORRETO
    if not empresa.ativo:
        if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
            return redirect("/contrato-governo/")
        return redirect("/pagamento/")

    # ⏰ verifica trial expirado — bloqueia e desativa a conta
    if empresa.ativo and empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        trial = getattr(empresa, "trial", None)
        if trial and not trial.convertido and trial.expira_em < timezone.now():
            empresa.ativo = False
            empresa.save(update_fields=["ativo"])
            return redirect("/pagamento/")

    if empresa.tipo_conta == Empresa.TIPO_GOVERNO and variant != "governo":
        return redirect("/dashboard-governo/")

    if empresa.tipo_conta != Empresa.TIPO_GOVERNO and variant == "governo":
        return redirect(_dashboard_url_por_setor(_setor_conta(empresa)))

    principal = getattr(request, "principal", None)
    perfil = perfil_principal(request)
    if principal and principal.__class__.__name__ == "EmpresaUsuario" and perfil in {"ti", "rh", "gerencia"}:
        destino = destino_por_perfil(request, empresa)
        if destino and destino != request.path:
            return redirect(destino)

    # acesso_governo gate removed — any tipo_conta == governo account has full access

    setor_conta = _setor_conta(empresa)
    if setor_conta == "empresa":
        return redirect("/dashboard-empresa/")
    if setor_conta != "governo":
        variant_permitida = setor_conta
        if variant != variant_permitida:
            return redirect(_dashboard_url_por_setor(setor_conta))

    template_by_variant = {
        "governo": "dashboard_governo.html",
        "farmacia": "dashboard_farmacia.html",
        "hospital": "dashboard_hospital.html",
    }
    template_name = template_by_variant.get(variant, "dashboard_unificado.html")

    response = render(request, template_name, {
        "empresa_id": str(empresa.id),
        "empresa_nome": empresa.nome,
        "dashboard_variant": variant,
        "setor_conta": setor_conta,
        "setor_label": _setor_label(setor_conta),
        "acesso_governo": empresa.acesso_governo,
        "tipo_conta": empresa.tipo_conta,
    })
    response.set_cookie("empresa_id", str(empresa.id), samesite="Lax", secure=not settings.DEBUG)
    return response


def dashboard(request):
    return _render_dashboard(request, "populacao")

def global_paises(request):

    dados = RegistroSintoma.objects.values("pais")\
        .annotate(total=Count("id"))\
        .order_by("-total")

    resultado = []

    for d in dados:
        if not d["pais"]:
            continue

        resultado.append({
            "pais": d["pais"],
            "total": d["total"]
        })

    return JsonResponse(resultado, safe=False)


def dashboard_farmacia(request):
    return _render_dashboard(request, "farmacia")


def dashboard_hospital(request):
    return _render_dashboard(request, "hospital")


def dashboard_governo(request):
    return _render_dashboard(request, "governo")


@ensure_csrf_cookie
@requer_setor('farmacia')
@requer_operacao_page
def farmacia_gestao_page(request):
    return render(request, "farmacia_gestao.html", contexto_navegacao_setorial(request, "farmacia"))


@ensure_csrf_cookie
@requer_setor('hospital')
@requer_operacao_page
def hospital_gestao_page(request):
    return render(request, "hospital_gestao.html", contexto_navegacao_setorial(request, "hospital"))


@ensure_csrf_cookie
@requer_setor('governo')
@requer_operacao_page
def governo_gestao_page(request):
    return render(request, "governo_gestao.html", contexto_navegacao_setorial(request, "governo"))


@ensure_csrf_cookie
@requer_setor('governo')
@requer_plataforma_ti_page
def governo_plataforma_page(request):
    return render(request, "governo_plataforma.html")


@ensure_csrf_cookie
@requer_setor('farmacia', 'hospital')
@requer_operacao_page
def rede_gestao_page(request):
    from .access_control import get_setor
    empresa = getattr(request, "empresa", None)
    setor = get_setor(empresa) if empresa else "farmacia"
    return render(request, "rede_gestao.html", {"setor": setor, **contexto_navegacao_setorial(request, setor)})


@ensure_csrf_cookie
@requer_setor('plano_saude')
@requer_operacao_page
def plano_saude_gestao_page(request):
    return render(request, "plano_saude_gestao.html", contexto_navegacao_setorial(request, "plano_saude"))


@ensure_csrf_cookie
@requer_gerencia_page
def gerencia_executiva_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "gerencia_executiva.html", {
        "empresa_id": str(empresa.id),
        "empresa_nome": empresa.nome,
        "setor_label": _setor_label(_setor_conta(empresa)),
        "setor_conta": _setor_conta(empresa),
        "return_url": _dashboard_return_url(empresa),
        "logout_url": "/logout-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/logout/",
        **contexto_navegacao_setorial(request),
    })


@ensure_csrf_cookie
@requer_rh_page
def portal_rh_page(request):
    return redirect("/usuarios/")


@ensure_csrf_cookie
@requer_setor('plano_saude')
@requer_operacao_page
def dashboard_plano_saude(request):
    return render(request, "dashboard_plano_saude.html")


def _dashboard_return_url(empresa):
    return dashboard_return_url(empresa)


@ensure_csrf_cookie
def command_ai(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    if not empresa.ativo:
        if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
            return redirect("/contrato-governo/")
        return redirect("/pagamento/")
    return render(request, "command_ai.html", {
        "empresa_id": str(empresa.id),
        "empresa_nome": empresa.nome,
        "setor_label": _setor_label(_setor_conta(empresa)),
        "setor_conta": _setor_conta(empresa),
        "return_url": _dashboard_return_url(empresa),
        "logout_url": "/logout-governo/" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "/logout/",
    })


def api_command_ai(request):
    if request.method != "GET":
        return JsonResponse({"erro": "metodo nao permitido"}, status=405)
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)
    if not empresa.ativo:
        return JsonResponse({"erro": "assinatura ou contrato inativo"}, status=403)
    return JsonResponse(build_command_ai_payload(empresa))


def api_command_ai_feedback(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "metodo nao permitido"}, status=405)
    try:
        dados = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "json invalido"}, status=400)
    feedback = (dados.get("feedback") or "").strip().lower()
    if feedback not in {"util", "ajustar", "nao_aplica"}:
        return JsonResponse({"erro": "feedback invalido"}, status=400)
    request.empresa = empresa
    if not getattr(request, "principal", None):
        request.principal = empresa
    registrar_auditoria_institucional(
        request,
        "command_ai_feedback",
        detalhes={
            "insight_id": str(dados.get("insight_id") or "")[:120],
            "feedback": feedback,
            "observacao": str(dados.get("observacao") or "")[:500],
            "origem": "command_ai",
        },
    )
    return JsonResponse({"ok": True, "feedback": feedback})


def contrato_governo(request):
    empresa = _empresa_autenticada(request)

    if empresa and empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        return redirect(_dashboard_return_url(empresa))

    return render(request, "contrato_governo.html", {
        "empresa_nome": empresa.nome if empresa else "Orgao Governamental",
    })


@api_requer_operacao_ou_gerencia
def api_alertas_governo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        return JsonResponse({"erro": "acesso restrito ao governo"}, status=403)

    alertas = AlertaGovernamental.objects.filter(empresa=empresa).order_by("-criado_em")[:30]
    return JsonResponse({
        "alertas": [
            {
                "id": alerta.id,
                "titulo": alerta.titulo,
                "mensagem": alerta.mensagem,
                "estado": alerta.estado,
                "cidade": alerta.cidade,
                "bairro": alerta.bairro,
                "nivel": alerta.nivel,
                "ativo": alerta.ativo,
                "status": alerta.status,
                "protocolo": alerta.protocolo,
                "justificativa": alerta.justificativa,
                "criado_por": alerta.criado_por,
                "revisado_por": alerta.revisado_por,
                "aprovado_por": alerta.aprovado_por,
                "aprovado_em": alerta.aprovado_em.isoformat() if alerta.aprovado_em else None,
                "publicado_em": alerta.publicado_em.isoformat() if alerta.publicado_em else None,
                "revogado_em": alerta.revogado_em.isoformat() if alerta.revogado_em else None,
                "criado_em": alerta.criado_em.isoformat(),
            }
            for alerta in alertas
        ]
    })


@csrf_exempt
@api_requer_operacao_ou_gerencia
def api_criar_alerta_governo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        return JsonResponse({"erro": "acesso restrito ao governo"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    titulo = (dados.get("titulo") or "").strip()
    mensagem = (dados.get("mensagem") or "").strip()
    if not titulo or not mensagem:
        return JsonResponse({"erro": "titulo e mensagem são obrigatórios"}, status=400)

    publicar_agora = bool(dados.get("publicar_agora"))
    status_inicial = AlertaGovernamental.STATUS_PUBLICADO if publicar_agora else AlertaGovernamental.STATUS_EM_REVISAO
    agora = timezone.now()
    alerta = AlertaGovernamental.objects.create(
        empresa=empresa,
        titulo=titulo[:160],
        mensagem=mensagem,
        estado=(dados.get("estado") or "").strip() or None,
        cidade=(dados.get("cidade") or "").strip() or None,
        bairro=(dados.get("bairro") or "").strip() or None,
        nivel=((dados.get("nivel") or "moderado").strip() or "moderado")[:20],
        ativo=publicar_agora,
        status=status_inicial,
        protocolo=f"ALR-{agora.strftime('%Y%m%d%H%M%S')}",
        justificativa=(dados.get("justificativa") or "").strip(),
        criado_por=_principal_label(request),
        revisado_por=_principal_label(request) if publicar_agora else "",
        aprovado_por=_principal_label(request) if publicar_agora else "",
        aprovado_em=agora if publicar_agora else None,
        publicado_em=agora if publicar_agora else None,
    )
    registrar_auditoria_institucional(
        request,
        "alerta_governo_criado",
        alerta,
        {
            "status": alerta.status,
            "publicar_agora": publicar_agora,
            "nivel": alerta.nivel,
            "escopo": {"estado": alerta.estado, "cidade": alerta.cidade, "bairro": alerta.bairro},
        },
    )
    if publicar_agora:
        _sincronizar_alerta_no_app_publico(alerta)
    push_resultado = enviar_alerta_governamental(alerta) if publicar_agora else {"status": "aguardando_aprovacao", "enviados": 0}
    return JsonResponse({
        "status": "ok",
        "alerta_id": alerta.id,
        "alerta_status": alerta.status,
        "protocolo": alerta.protocolo,
        "push": push_resultado,
        "push_configurado": push_disponivel(),
    })


@csrf_exempt
@api_requer_operacao_ou_gerencia
def api_toggle_alerta_governo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        return JsonResponse({"erro": "acesso restrito ao governo"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    alerta = AlertaGovernamental.objects.filter(id=dados.get("alerta_id"), empresa=empresa).first()
    if not alerta:
        return JsonResponse({"erro": "alerta não encontrado"}, status=404)

    alerta.ativo = bool(dados.get("ativo", not alerta.ativo))
    if alerta.ativo:
        alerta.status = AlertaGovernamental.STATUS_PUBLICADO
        alerta.publicado_em = alerta.publicado_em or timezone.now()
    else:
        alerta.status = AlertaGovernamental.STATUS_REVOGADO
        alerta.revogado_em = timezone.now()
    alerta.save(update_fields=["ativo", "status", "publicado_em", "revogado_em"])
    _sincronizar_alerta_no_app_publico(alerta)
    registrar_auditoria_institucional(
        request,
        "alerta_governo_toggle",
        alerta,
        {"ativo": alerta.ativo, "status": alerta.status},
    )
    return JsonResponse({"status": "ok"})


@csrf_exempt
@api_requer_operacao_ou_gerencia
def api_fluxo_alerta_governo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if empresa.tipo_conta != Empresa.TIPO_GOVERNO:
        return JsonResponse({"erro": "acesso restrito ao governo"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    alerta = AlertaGovernamental.objects.filter(id=dados.get("alerta_id"), empresa=empresa).first()
    if not alerta:
        return JsonResponse({"erro": "alerta não encontrado"}, status=404)

    acao = (dados.get("acao") or "").strip()
    justificativa = (dados.get("justificativa") or "").strip()
    agora = timezone.now()
    push_resultado = {"status": "nao_enviado", "enviados": 0}
    update_fields = [
        "status",
        "ativo",
        "justificativa",
        "revisado_por",
        "aprovado_por",
        "aprovado_em",
        "publicado_em",
        "revogado_em",
        "protocolo",
    ]
    if not alerta.protocolo:
        alerta.protocolo = f"ALR-{agora.strftime('%Y%m%d%H%M%S')}"

    if acao == "rascunho":
        alerta.status = AlertaGovernamental.STATUS_RASCUNHO
        alerta.ativo = False
    elif acao == "enviar_revisao":
        alerta.status = AlertaGovernamental.STATUS_EM_REVISAO
        alerta.ativo = False
        alerta.revisado_por = _principal_label(request)
    elif acao == "aprovar":
        alerta.status = AlertaGovernamental.STATUS_APROVADO
        alerta.ativo = False
        alerta.aprovado_por = _principal_label(request)
        alerta.aprovado_em = agora
    elif acao == "publicar":
        if alerta.status not in {AlertaGovernamental.STATUS_APROVADO, AlertaGovernamental.STATUS_PUBLICADO}:
            return JsonResponse({"erro": "alerta precisa estar aprovado antes da publicação"}, status=400)
        alerta.status = AlertaGovernamental.STATUS_PUBLICADO
        alerta.ativo = True
        alerta.publicado_em = agora
        push_resultado = enviar_alerta_governamental(alerta)
    elif acao == "revogar":
        alerta.status = AlertaGovernamental.STATUS_REVOGADO
        alerta.ativo = False
        alerta.revogado_em = agora
    elif acao == "excluir":
        if alerta.status != AlertaGovernamental.STATUS_REVOGADO:
            return JsonResponse({"erro": "somente alertas revogados podem ser excluidos"}, status=400)
        alerta_id = alerta.id
        protocolo = alerta.protocolo
        _remover_alerta_do_app_publico(alerta)
        registrar_auditoria_institucional(
            request,
            "alerta_governo_excluir",
            alerta,
            {"status": alerta.status, "protocolo": protocolo},
        )
        alerta.delete()
        return JsonResponse({
            "status": "ok",
            "alerta_id": alerta_id,
            "alerta_status": "excluido",
            "ativo": False,
            "push": push_resultado,
        })
    else:
        return JsonResponse({"erro": "ação inválida"}, status=400)

    if justificativa:
        alerta.justificativa = justificativa

    alerta.save(update_fields=update_fields)
    if acao in {"publicar", "revogar"}:
        _sincronizar_alerta_no_app_publico(alerta)
    registrar_auditoria_institucional(
        request,
        f"alerta_governo_{acao}",
        alerta,
        {"status": alerta.status, "justificativa": justificativa},
    )
    return JsonResponse({
        "status": "ok",
        "alerta_id": alerta.id,
        "alerta_status": alerta.status,
        "ativo": alerta.ativo,
        "push": push_resultado,
    })


def licencas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "licencas.html", {
        "empresa_nome": empresa.nome,
        "tipo_conta": empresa.tipo_conta,
        "max_dispositivos": empresa.max_dispositivos,
    })


def seguranca(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "seguranca.html", {
        "empresa_nome": empresa.nome,
        "tipo_conta": empresa.tipo_conta,
    })


def api_dispositivos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    dispositivos = DispositivoAutorizado.objects.filter(empresa=empresa).order_by("-ultimo_acesso")
    payload = [
        {
            "id": device.id,
            "device_id": device.device_id,
            "apelido": device.apelido or "Sem apelido",
            "ip": device.ip,
            "ativo": device.ativo,
            "ultimo_acesso": device.ultimo_acesso.isoformat(),
            "criado_em": device.criado_em.isoformat(),
            "user_agent": (device.user_agent or "")[:180],
        }
        for device in dispositivos
    ]

    return JsonResponse({
        "empresa": empresa.nome,
        "tipo_conta": empresa.tipo_conta,
        "max_dispositivos": empresa.max_dispositivos,
        "ativos_em_uso": dispositivos.filter(ativo=True).count(),
        "dispositivos": payload,
    })


@csrf_exempt
def api_revogar_dispositivo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    dispositivo_id = dados.get("device_id")
    if not dispositivo_id:
        return JsonResponse({"erro": "device_id obrigatório"}, status=400)

    dispositivo = DispositivoAutorizado.objects.filter(empresa=empresa, device_id=dispositivo_id, ativo=True).first()
    if not dispositivo:
        return JsonResponse({"erro": "dispositivo não encontrado"}, status=404)

    dispositivo.ativo = False
    dispositivo.save(update_fields=["ativo", "ultimo_acesso"])
    return JsonResponse({"status": "ok"})


def api_auditoria_seguranca(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    agora = timezone.now()
    base = RegistroSintoma.objects.filter(empresa=empresa)
    janela_24h = base.filter(data_registro__gte=agora - timedelta(hours=24))
    suspeitos = base.filter(suspeito=True)

    top_ips = (
        suspeitos.exclude(ip__isnull=True).exclude(ip="")
        .values("ip")
        .annotate(total=Count("id"), media_confianca=Avg("confianca"))
        .order_by("-total")[:8]
    )
    top_devices = (
        suspeitos.exclude(device_id__isnull=True).exclude(device_id="")
        .values("device_id")
        .annotate(total=Count("id"), media_confianca=Avg("confianca"))
        .order_by("-total")[:8]
    )
    recentes = base.order_by("-data_registro")[:20]

    return JsonResponse({
        "summary": {
            "total_registros": base.count(),
            "registros_24h": janela_24h.count(),
            "suspeitos_total": suspeitos.count(),
            "suspeitos_24h": janela_24h.filter(suspeito=True).count(),
            "confianca_media": round(float(base.aggregate(media=Avg("confianca"))["media"] or 0.0), 2),
        },
        "top_ips": [
            {
                "ip": item["ip"],
                "total": item["total"],
                "media_confianca": round(float(item["media_confianca"] or 0.0), 2),
            }
            for item in top_ips
        ],
        "top_devices": [
            {
                "device_id": item["device_id"],
                "total": item["total"],
                "media_confianca": round(float(item["media_confianca"] or 0.0), 2),
            }
            for item in top_devices
        ],
        "recentes": [
            {
                "data_registro": item.data_registro.isoformat(),
                "cidade": item.cidade,
                "estado": item.estado,
                "bairro": item.bairro,
                "grupo": item.grupo,
                "classificacao": item.classificacao,
                "confianca": item.confianca,
                "suspeito": item.suspeito,
                "ip": item.ip,
                "device_id": item.device_id,
            }
            for item in recentes
        ],
    })


def usuarios_empresa(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    if perfil_principal(request) == "ti":
        return redirect(destino_por_perfil(request, empresa))
    pode_configurar_ti = _principal_pode_configurar_ti(request, empresa)
    if not pode_configurar_ti:
        return redirect(destino_por_perfil(request, empresa))
    return render(request, "usuarios_empresa.html", {
        "empresa_nome": empresa.nome,
        "tipo_conta": empresa.tipo_conta,
        "max_usuarios": empresa.max_usuarios,
        "pacote": detalhes_pacote(empresa.pacote_codigo),
        "pode_configurar_ti": pode_configurar_ti,
    })


def api_usuarios_empresa(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if not _principal_pode_configurar_ti(request, empresa):
        return JsonResponse({"erro": "Acesso restrito a RH/gerência."}, status=403)

    usuarios = EmpresaUsuario.objects.filter(empresa=empresa).order_by("nome")
    return JsonResponse({
        "max_usuarios": empresa.max_usuarios,
        "usuarios_ativos": usuarios.filter(ativo=True).count(),
        "pode_configurar_ti": _principal_pode_configurar_ti(request, empresa),
        "usuarios": [
            {
                "id": usuario.id,
                "nome": usuario.nome,
                "email": usuario.email,
                "cargo": usuario.cargo,
                "ativo": usuario.ativo,
                "is_admin": usuario.is_admin,
                "criado_em": usuario.criado_em.isoformat(),
            }
            for usuario in usuarios
        ],
    })


@csrf_exempt
def api_criar_usuario_empresa(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if not _principal_pode_configurar_ti(request, empresa):
        return JsonResponse({"erro": "Acesso restrito a RH/gerência."}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        from django.contrib.auth.hashers import make_password
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    nome = (dados.get("nome") or "").strip()
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""
    cargo = (dados.get("cargo") or "").strip()

    if not nome or not email or not senha:
        return JsonResponse({"erro": "nome, email e senha são obrigatórios"}, status=400)

    if EmpresaUsuario.objects.filter(email=email).exists() or Empresa.objects.filter(email=email).exists():
        return JsonResponse({"erro": "email já cadastrado"}, status=400)

    ativos = EmpresaUsuario.objects.filter(empresa=empresa, ativo=True).count()
    if ativos >= empresa.max_usuarios:
        return JsonResponse({"erro": "limite de usuários do pacote atingido"}, status=403)

    usuario = EmpresaUsuario.objects.create(
        empresa=empresa,
        nome=nome,
        email=email,
        senha=make_password(senha),
        cargo=cargo,
    )

    return JsonResponse({"status": "ok", "usuario_id": usuario.id})


@csrf_exempt
def api_criar_credencial_ti(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)
    if not _principal_pode_configurar_ti(request, empresa):
        return JsonResponse({
            "erro": "Apenas RH ou administrador da empresa pode configurar credenciais de TI.",
        }, status=403)

    try:
        from django.contrib.auth.hashers import make_password
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    nome = (dados.get("nome") or "Responsável TI").strip()
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""

    if not email or not senha:
        return JsonResponse({"erro": "email e senha são obrigatórios"}, status=400)
    if len(senha) < 8:
        return JsonResponse({"erro": "senha deve ter pelo menos 8 caracteres"}, status=400)

    usuario_empresa = EmpresaUsuario.objects.filter(empresa=empresa, email=email).first()
    email_em_outra_empresa = EmpresaUsuario.objects.filter(email=email).exclude(empresa=empresa).exists()
    email_conta_empresa = Empresa.objects.filter(email=email).exists()

    if email_em_outra_empresa or email_conta_empresa:
        return JsonResponse({"erro": "email já cadastrado em outra conta"}, status=400)

    criado = False
    if usuario_empresa:
        usuario_empresa.nome = nome
        usuario_empresa.cargo = "TI"
        usuario_empresa.senha = make_password(senha)
        usuario_empresa.ativo = True
        usuario_empresa.sessao_ativa_chave = None
        usuario_empresa.sessao_ativa_device_id = None
        usuario_empresa.sessao_ativa_em = None
        usuario_empresa.save(update_fields=[
            "nome", "cargo", "senha", "ativo",
            "sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em",
        ])
    else:
        ativos = EmpresaUsuario.objects.filter(empresa=empresa, ativo=True).count()
        if ativos >= empresa.max_usuarios:
            return JsonResponse({"erro": "limite de usuários do pacote atingido"}, status=403)
        usuario_empresa = EmpresaUsuario.objects.create(
            empresa=empresa,
            nome=nome,
            email=email,
            senha=make_password(senha),
            cargo="TI",
            ativo=True,
        )
        criado = True

    _atribuir_permissao_ti(
        empresa,
        usuario_empresa,
        concedido_por=_principal_label(request),
    )

    return JsonResponse({
        "status": "ok",
        "acao": "criado" if criado else "atualizado",
        "usuario_id": usuario_empresa.id,
        "usuario_email": usuario_empresa.email,
    })


@csrf_exempt
def api_desativar_usuario_empresa(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if not _principal_pode_configurar_ti(request, empresa):
        return JsonResponse({"erro": "Acesso restrito a RH/gerência."}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    usuario_id = dados.get("usuario_id")
    usuario = EmpresaUsuario.objects.filter(id=usuario_id, empresa=empresa, ativo=True).first()
    if not usuario:
        return JsonResponse({"erro": "usuário não encontrado"}, status=404)

    usuario.ativo = False
    usuario.sessao_ativa_chave = None
    usuario.sessao_ativa_device_id = None
    usuario.sessao_ativa_em = None
    usuario.save(update_fields=["ativo", "sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em"])
    return JsonResponse({"status": "ok"})


def login_operacao(request):
    return render(request, "login_dono.html")


def console_operacional(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return redirect("/operacao-central/")
    return render(request, "painel_dono.html", {
        "owner_nome": dono.nome,
        "pacotes_json": json.dumps(PACOTES_SAAS),
    })


login_dono = login_operacao
painel_dono = console_operacional


def api_dono_resumo(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    return JsonResponse(build_owner_resumo_payload(dono))


def api_dono_financeiro_real(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .services.dashboard_core import build_owner_financeiro_real
    return JsonResponse(build_owner_financeiro_real(dono))


def api_dono_saude(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .services.dashboard_core import build_owner_saude_sistema
    return JsonResponse(build_owner_saude_sistema(dono))


def api_dono_app_funcionario(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .services.dashboard_core import build_owner_app_funcionario
    return JsonResponse(build_owner_app_funcionario(dono))


def api_dono_operadores(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .services.dashboard_core import build_owner_operadores_payload
    return JsonResponse(build_owner_operadores_payload(dono))


@csrf_exempt
def api_dono_operador_acao(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)
    # RBAC: só administradores gerenciam operadores
    if dono.papel != DonoSaaS.PAPEL_ADMIN:
        return JsonResponse({"erro": "apenas administradores podem gerenciar operadores"}, status=403)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    from django.contrib.auth.hashers import make_password
    acao = (dados.get("acao") or "").strip()
    papeis_validos = {p[0] for p in DonoSaaS.PAPEIS}

    if acao == "criar":
        nome = (dados.get("nome") or "").strip()
        email = (dados.get("email") or "").strip().lower()
        senha = dados.get("senha") or ""
        papel = (dados.get("papel") or "leitura").strip()
        if not nome or not email or not senha:
            return JsonResponse({"erro": "nome, email e senha são obrigatórios"}, status=400)
        if papel not in papeis_validos:
            papel = "leitura"
        if DonoSaaS.objects.filter(email=email).exists():
            return JsonResponse({"erro": "já existe um operador com este email"}, status=409)
        op = DonoSaaS.objects.create(
            nome=nome, email=email, senha=make_password(senha), papel=papel, ativo=True
        )
        _registrar_auditoria_dono(dono, "operador_criado", detalhes=f"{email} ({papel})")
        return JsonResponse({"status": "ok", "id": op.id})

    op = DonoSaaS.objects.filter(id=dados.get("operador_id")).first()
    if not op:
        return JsonResponse({"erro": "operador não encontrado"}, status=404)
    if op.id == dono.id and acao in {"desativar"}:
        return JsonResponse({"erro": "você não pode desativar a si mesmo"}, status=400)

    if acao == "desativar":
        op.ativo = False
        op.sessao_ativa_chave = None
        op.save(update_fields=["ativo", "sessao_ativa_chave"])
        _registrar_auditoria_dono(dono, "operador_desativado", detalhes=op.email)
    elif acao == "reativar":
        op.ativo = True
        op.save(update_fields=["ativo"])
        _registrar_auditoria_dono(dono, "operador_reativado", detalhes=op.email)
    elif acao == "papel":
        novo = (dados.get("papel") or "").strip()
        if novo not in papeis_validos:
            return JsonResponse({"erro": "papel inválido"}, status=400)
        op.papel = novo
        op.save(update_fields=["papel"])
        _registrar_auditoria_dono(dono, "operador_papel", detalhes=f"{op.email} -> {novo}")
    else:
        return JsonResponse({"erro": "ação inválida"}, status=400)

    return JsonResponse({"status": "ok"})


@csrf_exempt
def api_dono_atualizar_cliente(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    empresa = Empresa.objects.filter(id=dados.get("empresa_id")).first()
    if not empresa:
        return JsonResponse({"erro": "cliente não encontrado"}, status=404)

    pacote_codigo = normalizar_codigo_pacote(dados.get("pacote_codigo") or empresa.pacote_codigo)
    pacote = detalhes_pacote(pacote_codigo)
    plano = "anual" if empresa.tipo_conta == Empresa.TIPO_GOVERNO or pacote.get("setor") == "governo" else normalizar_ciclo(pacote_codigo, dados.get("plano") or empresa.plano or "mensal")
    ativo_raw = dados.get("ativo", empresa.ativo)
    if isinstance(ativo_raw, str):
        ativo = ativo_raw.lower() == "true"
    else:
        ativo = bool(ativo_raw)

    empresa.pacote_codigo = pacote_codigo
    empresa.max_usuarios = pacote["usuarios"]
    empresa.max_dispositivos = pacote["dispositivos"]
    empresa.plano = plano
    empresa.ativo = ativo
    update_fields = ["pacote_codigo", "max_usuarios", "max_dispositivos", "plano", "ativo"]

    if dados.get("data_expiracao"):
        from django.utils import timezone as tz
        from datetime import datetime as _dt
        try:
            nova_exp = _dt.fromisoformat(dados["data_expiracao"])
            if nova_exp.tzinfo is None:
                nova_exp = tz.make_aware(nova_exp)
            empresa.data_expiracao = nova_exp
            update_fields.append("data_expiracao")
        except ValueError:
            pass

    empresa.save(update_fields=update_fields)

    FinanceiroEventoSaaS.objects.create(
        empresa=empresa,
        tipo_evento="ajuste_owner",
        pacote_codigo=empresa.pacote_codigo,
        ciclo=empresa.plano,
        valor=0,
        status="manual",
        observacao=f"Ajuste operacional para pacote {pacote['label']} / ativo={empresa.ativo}",
    )
    _registrar_auditoria_dono(
        dono,
        "ajuste_cliente",
        empresa=empresa,
        detalhes=f"Pacote={empresa.pacote_codigo}; plano={empresa.plano}; ativo={empresa.ativo}",
    )

    return JsonResponse({"status": "ok"})


@csrf_exempt
def api_dono_financeiro_acao(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    empresa = Empresa.objects.filter(id=dados.get("empresa_id")).first()
    if not empresa:
        return JsonResponse({"erro": "cliente não encontrado"}, status=404)

    acao = (dados.get("acao") or "").strip()
    if not acao:
        return JsonResponse({"erro": "ação obrigatória"}, status=400)

    pacote = detalhes_pacote(empresa.pacote_codigo)
    plano_atual = "anual" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else normalizar_ciclo(empresa.pacote_codigo, empresa.plano)
    valor = pacote["anual"] if plano_atual == "anual" else pacote["mensal"]
    observacao = ""

    if acao == "marcar_cobranca":
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="cobranca_manual",
            pacote_codigo=empresa.pacote_codigo,
            ciclo=plano_atual,
            valor=valor,
            status="cobranca",
            observacao="Cobrança manual iniciada pelo console operacional",
        )
        observacao = "Cobrança manual registrada"
    elif acao == "marcar_inadimplente":
        empresa.ativo = False
        empresa.save(update_fields=["ativo"])
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="inadimplencia",
            pacote_codigo=empresa.pacote_codigo,
            ciclo=plano_atual,
            valor=valor,
            status="inadimplente",
            observacao="Cliente marcado como inadimplente pelo console operacional",
        )
        observacao = "Cliente marcado como inadimplente"
    elif acao == "reativar":
        empresa.ativo = True
        if not empresa.data_expiracao or empresa.data_expiracao < timezone.now():
            dias = 365 if plano_atual == "anual" else 30
            empresa.data_expiracao = timezone.now() + timedelta(days=dias)
        empresa.save(update_fields=["ativo", "data_expiracao"])
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="reativacao_manual",
            pacote_codigo=empresa.pacote_codigo,
            ciclo=plano_atual,
            valor=valor,
            status="manual",
            observacao="Cliente reativado pelo console operacional",
        )
        observacao = "Cliente reativado"
    elif acao == "renovar_30":
        if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
            return JsonResponse({"erro": "governo possui somente contrato anual fechado"}, status=400)
        base = empresa.data_expiracao if empresa.data_expiracao and empresa.data_expiracao > timezone.now() else timezone.now()
        empresa.ativo = True
        empresa.data_expiracao = base + timedelta(days=30)
        empresa.save(update_fields=["ativo", "data_expiracao"])
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="renovacao_manual",
            pacote_codigo=empresa.pacote_codigo,
            ciclo="mensal",
            valor=pacote["mensal"],
            status="manual",
            observacao="Renovação manual de 30 dias",
        )
        observacao = "Contrato renovado por 30 dias"
    elif acao == "renovar_365":
        base = empresa.data_expiracao if empresa.data_expiracao and empresa.data_expiracao > timezone.now() else timezone.now()
        empresa.ativo = True
        empresa.data_expiracao = base + timedelta(days=365)
        empresa.plano = "anual"
        empresa.save(update_fields=["ativo", "data_expiracao", "plano"])
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="renovacao_manual",
            pacote_codigo=empresa.pacote_codigo,
            ciclo="anual",
            valor=pacote["anual"],
            status="manual",
            observacao="Renovação manual de 365 dias",
        )
        observacao = "Contrato renovado por 365 dias"
    elif acao == "carencia_7":
        base = empresa.data_expiracao if empresa.data_expiracao and empresa.data_expiracao > timezone.now() else timezone.now()
        empresa.ativo = True
        empresa.data_expiracao = base + timedelta(days=7)
        empresa.save(update_fields=["ativo", "data_expiracao"])
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="carencia_operacional",
            pacote_codigo=empresa.pacote_codigo,
            ciclo=plano_atual,
            valor=0,
            status="manual",
            observacao="Carencia operacional de 7 dias concedida pelo console",
        )
        observacao = "Carencia operacional de 7 dias concedida"
    elif acao == "cancelar":
        empresa.ativo = False
        empresa.data_expiracao = timezone.now()
        empresa.sessao_ativa_chave = None
        empresa.sessao_ativa_device_id = None
        empresa.sessao_ativa_em = None
        empresa.save(update_fields=["ativo", "data_expiracao", "sessao_ativa_chave", "sessao_ativa_device_id", "sessao_ativa_em"])
        EmpresaUsuario.objects.filter(empresa=empresa).update(
            sessao_ativa_chave=None,
            sessao_ativa_device_id=None,
            sessao_ativa_em=None,
        )
        FinanceiroEventoSaaS.objects.create(
            empresa=empresa,
            tipo_evento="cancelamento_operacional",
            pacote_codigo=empresa.pacote_codigo,
            ciclo=plano_atual,
            valor=valor,
            status="cancelado",
            observacao="Contrato cancelado pelo console operacional",
        )
        observacao = "Contrato cancelado e sessoes encerradas"
    else:
        return JsonResponse({"erro": "ação inválida"}, status=400)

    _registrar_auditoria_dono(
        dono,
        f"financeiro_{acao}",
        empresa=empresa,
        detalhes=observacao,
    )
    return JsonResponse({"status": "ok", "observacao": observacao})


@csrf_exempt
def api_dono_onboarding_acao(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    empresa = Empresa.objects.filter(id=dados.get("empresa_id")).first()
    if not empresa:
        return JsonResponse({"erro": "cliente não encontrado"}, status=404)

    acoes = {
        "kickoff": ("onboarding_kickoff", "Kickoff de implantacao registrado"),
        "treinamento": ("onboarding_treinamento", "Treinamento operacional realizado"),
        "validacao": ("onboarding_validacao", "Validacao com dados reais concluida"),
        "go_live": ("onboarding_go_live", "Go-live aprovado pelo console operacional"),
    }
    acao = (dados.get("acao") or "").strip()
    if acao not in acoes:
        return JsonResponse({"erro": "ação inválida"}, status=400)

    tipo_evento, observacao = acoes[acao]
    detalhe_extra = (dados.get("observacao") or "").strip()[:240]
    observacao_final = observacao if not detalhe_extra else f"{observacao}. {detalhe_extra}"
    plano_atual = "anual" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else normalizar_ciclo(empresa.pacote_codigo, empresa.plano)

    FinanceiroEventoSaaS.objects.create(
        empresa=empresa,
        tipo_evento=tipo_evento,
        pacote_codigo=empresa.pacote_codigo,
        ciclo=plano_atual,
        valor=0,
        status="manual",
        observacao=observacao_final,
    )
    _registrar_auditoria_dono(
        dono,
        f"onboarding_{acao}",
        empresa=empresa,
        detalhes=observacao_final,
    )

    return JsonResponse({
        "status": "ok",
        "observacao": observacao_final,
        "onboarding": onboarding_snapshot(empresa),
    })


def api_dono_exportar(request):
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    tipo = (request.GET.get("tipo") or "clientes").strip()
    formato = (request.GET.get("formato") or "csv").strip()
    if formato != "csv":
        return JsonResponse({"erro": "somente csv disponível no momento"}, status=400)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="soluscrt_{tipo}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)

    if tipo == "clientes":
        writer.writerow(["cliente", "email", "segmento", "pacote", "plano", "ativo", "usuarios", "dispositivos", "registros_24h", "suspeitos_24h", "expira_em"])
        for empresa in Empresa.objects.order_by("nome"):
            writer.writerow([
                empresa.nome,
                empresa.email,
                _segmento_empresa(empresa),
                empresa.pacote_codigo,
                empresa.plano or "",
                "sim" if empresa.ativo else "nao",
                empresa.max_usuarios,
                empresa.max_dispositivos,
                RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=timezone.now() - timedelta(hours=24)).count(),
                RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=timezone.now() - timedelta(hours=24), suspeito=True).count(),
                empresa.data_expiracao.isoformat() if empresa.data_expiracao else "",
            ])
    elif tipo == "financeiro":
        writer.writerow(["cliente", "tipo_evento", "pacote", "ciclo", "valor", "status", "observacao", "criado_em"])
        for evento in FinanceiroEventoSaaS.objects.select_related("empresa").order_by("-criado_em")[:1000]:
            writer.writerow([
                evento.empresa.nome,
                evento.tipo_evento,
                evento.pacote_codigo or "",
                evento.ciclo or "",
                float(evento.valor),
                evento.status,
                evento.observacao or "",
                evento.criado_em.isoformat(),
            ])
    elif tipo == "auditoria":
        writer.writerow(["operador", "empresa", "acao", "detalhes", "criado_em"])
        for item in DonoAuditoriaAcao.objects.select_related("empresa", "dono").order_by("-criado_em")[:1000]:
            writer.writerow([
                item.dono.email,
                item.empresa.nome if item.empresa else "Plataforma",
                item.acao,
                item.detalhes,
                item.criado_em.isoformat(),
            ])
    else:
        return JsonResponse({"erro": "tipo de exportação inválido"}, status=400)

    _registrar_auditoria_dono(dono, f"exportacao_{tipo}", detalhes=f"Formato={formato}")
    return response


@csrf_exempt
def api_dono_excluir_cliente(request):
    """
    POST /api/operacao-central/cliente/excluir
    Exclui permanentemente uma conta e todos os seus dados.
    Libera o email para novo cadastro.
    Requer confirmação via campo 'confirmar_email' igual ao email da empresa.
    """
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    empresa_id = dados.get("empresa_id")
    confirmar_email = (dados.get("confirmar_email") or "").strip().lower()

    empresa = Empresa.objects.filter(id=empresa_id).first()
    if not empresa:
        return JsonResponse({"erro": "cliente não encontrado"}, status=404)

    if confirmar_email != empresa.email.strip().lower():
        return JsonResponse({
            "erro": "Confirmação inválida. Digite o email exato da conta para confirmar a exclusão."
        }, status=400)

    # Registra auditoria ANTES de deletar (dados serão perdidos)
    _registrar_auditoria_dono(
        dono,
        "exclusao_conta",
        empresa=None,  # empresa será deletada, não manter referência
        detalhes=(
            f"Conta excluída: id={empresa.id} | nome={empresa.nome} | "
            f"email={empresa.email} | setor={empresa.pacote_codigo} | "
            f"ativo={empresa.ativo} | criado_em={empresa.criado_em.isoformat() if hasattr(empresa, 'criado_em') and empresa.criado_em else 'N/A'}"
        ),
    )

    nome_backup = empresa.nome
    email_backup = empresa.email

    # Deleta em cascata (todos os dados relacionados)
    empresa.delete()

    return JsonResponse({
        "status": "ok",
        "mensagem": f"Conta '{nome_backup}' ({email_backup}) excluída com sucesso. O email está livre para novo cadastro.",
    })


@csrf_exempt
def api_dono_reset_trial(request):
    """
    POST /api/operacao-central/cliente/reset-trial
    Reseta o trial de uma empresa: exclui o trial existente e cria um novo de 15 dias.
    Útil para dar segunda chance a um cliente em negociação.
    """
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    from .models import TrialEmpresa
    empresa = Empresa.objects.filter(id=dados.get("empresa_id")).first()
    if not empresa:
        return JsonResponse({"erro": "cliente não encontrado"}, status=404)

    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return JsonResponse({"erro": "Governo não usa trial"}, status=400)

    # Remove trial anterior e cria novo
    TrialEmpresa.objects.filter(empresa=empresa).delete()
    nova_expiracao = timezone.now() + timedelta(days=15)
    TrialEmpresa.objects.create(empresa=empresa, expira_em=nova_expiracao)

    # Garante que a empresa está ativa
    if not empresa.ativo:
        empresa.ativo = True
        empresa.save(update_fields=["ativo"])

    _registrar_auditoria_dono(
        dono,
        "reset_trial",
        empresa=empresa,
        detalhes=f"Trial resetado para 15 dias. Expira em: {nova_expiracao.strftime('%d/%m/%Y')}",
    )

    return JsonResponse({
        "status": "ok",
        "mensagem": f"Trial de '{empresa.nome}' resetado. Novo vencimento: {nova_expiracao.strftime('%d/%m/%Y')}",
        "dias_restantes": 15,
    })


@csrf_exempt
def api_dono_forcar_logout(request):
    """
    POST /api/operacao-central/cliente/forcar-logout
    Encerra todas as sessões ativas da empresa (admin + usuários).
    """
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    empresa = Empresa.objects.filter(id=dados.get("empresa_id")).first()
    if not empresa:
        return JsonResponse({"erro": "cliente não encontrado"}, status=404)

    # Encerra sessão do admin (Empresa)
    empresa.sessao_ativa_chave = None
    empresa.sessao_ativa_em = None
    update_fields = ["sessao_ativa_chave", "sessao_ativa_em"]
    if hasattr(empresa, "sessao_ativa_device_id"):
        empresa.sessao_ativa_device_id = None
        update_fields.append("sessao_ativa_device_id")
    empresa.save(update_fields=update_fields)

    # Encerra sessão de todos os usuários da empresa
    usuarios_afetados = EmpresaUsuario.objects.filter(empresa=empresa, ativo=True)
    count = usuarios_afetados.count()
    usuarios_afetados.update(sessao_ativa_chave=None, sessao_ativa_em=None)

    _registrar_auditoria_dono(
        dono,
        "forcar_logout",
        empresa=empresa,
        detalhes=f"Sessão encerrada: admin + {count} usuário(s)",
    )

    return JsonResponse({
        "status": "ok",
        "mensagem": f"Todas as sessões de '{empresa.nome}' foram encerradas ({count + 1} sessão(ões)).",
    })


def api_dono_auditoria(request):
    """
    GET /api/operacao-central/auditoria?empresa_id=X&limit=50
    Retorna log de ações do console operacional.
    """
    dono = getattr(request, "dono_saas", None) or _dono_autenticado(request)
    if not dono:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    empresa_id = request.GET.get("empresa_id")
    limit = min(int(request.GET.get("limit", 50)), 200)

    qs = DonoAuditoriaAcao.objects.order_by("-criado_em")
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)

    registros = []
    for r in qs[:limit]:
        registros.append({
            "id": r.id,
            "acao": r.acao,
            "empresa_id": r.empresa_id,
            "empresa_nome": r.empresa.nome if r.empresa_id else "—",
            "detalhes": r.detalhes,
            "criado_em": timezone.localtime(r.criado_em).strftime("%d/%m/%Y %H:%M"),
        })

    return JsonResponse({"registros": registros, "total": qs.count()})
