"""
Reuniões SST — API e páginas
"""
import json
import time
import jwt as pyjwt
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Empresa, FuncionarioSST, ReuniaoSST, NotificacaoFuncionario, VinculoClinicaEmpresa
from .views_dashboard import _empresa_autenticada
from .access_control import get_setor, requer_permissao_modulo


# ── helpers ────────────────────────────────────────────────────────────────────

def _reuniao_dict(r, empresa=None):
    participantes = list(r.participantes.values("id", "nome", "cargo"))
    return {
        "id": r.id,
        "titulo": r.titulo,
        "descricao": r.descricao,
        "tipo": r.tipo,
        "tipo_label": r.get_tipo_display(),
        "data_hora": timezone.localtime(r.data_hora).isoformat(),
        "data_hora_fmt": timezone.localtime(r.data_hora).strftime("%d/%m/%Y %H:%M"),
        "duracao_minutos": r.duracao_minutos,
        "status": r.status,
        "status_label": r.get_status_display(),
        "link": r.link_reuniao,
        "sala_jitsi": r.sala_jitsi,
        "link_externo": r.link_externo,
        "clinica_nome": r.clinica.nome if r.clinica else None,
        "participantes": participantes,
        "todos_funcionarios": r.participantes.count() == 0,
        "notificar_funcionarios": r.notificar_funcionarios,
        "observacoes": r.observacoes,
        "criado_em": timezone.localtime(r.criado_em).isoformat(),
    }


def _autenticar(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, redirect("/login-empresa/")
    if get_setor(empresa) != "empresa":
        return None, JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)
    return empresa, None


# ── Página web ─────────────────────────────────────────────────────────────────

@requer_permissao_modulo("sst.operacional")
def sst_comunicacao_page(request):
    empresa, redir = _autenticar(request)
    if redir:
        return redir
    # Clínicas vinculadas à empresa (ativas)
    clinica_ids = VinculoClinicaEmpresa.objects.filter(
        empresa_contratante=empresa, status="ativo"
    ).values_list("clinica_id", flat=True)
    clinicas = list(
        Empresa.objects.filter(id__in=clinica_ids, ativo=True)
        .values("id", "nome")
        .order_by("nome")
    )
    return render(request, "sst_comunicacao.html", {
        "empresa_nome": empresa.nome,
        "clinicas_json": json.dumps(clinicas, ensure_ascii=False),
    })


# ── API reuniões ───────────────────────────────────────────────────────────────

@csrf_exempt
def api_reunioes(request):
    empresa, redir = _autenticar(request)
    if redir:
        return JsonResponse({"erro": "não autorizado"}, status=401)

    if request.method == "GET":
        status_filtro = request.GET.get("status", "")
        tipo_filtro   = request.GET.get("tipo", "")
        qs = ReuniaoSST.objects.filter(empresa=empresa).prefetch_related("participantes", "clinica")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        if tipo_filtro:
            qs = qs.filter(tipo=tipo_filtro)
        return JsonResponse({"reunioes": [_reuniao_dict(r) for r in qs[:50]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        titulo = (data.get("titulo") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "Título é obrigatório"}, status=400)

        data_hora_str = data.get("data_hora", "")
        if not data_hora_str:
            return JsonResponse({"erro": "Data e hora são obrigatórias"}, status=400)
        try:
            from django.utils.dateparse import parse_datetime
            data_hora = parse_datetime(data_hora_str)
            if data_hora is None:
                raise ValueError
            if timezone.is_naive(data_hora):
                data_hora = timezone.make_aware(data_hora)
        except Exception:
            return JsonResponse({"erro": "Formato de data inválido. Use YYYY-MM-DDTHH:MM"}, status=400)

        tipo = data.get("tipo", ReuniaoSST.TIPO_FUNCIONARIOS)
        if tipo not in dict(ReuniaoSST.TIPOS):
            return JsonResponse({"erro": "Tipo inválido"}, status=400)

        clinica = None
        if tipo == ReuniaoSST.TIPO_CLINICA and data.get("clinica_id"):
            clinica_ids = VinculoClinicaEmpresa.objects.filter(
                empresa_contratante=empresa, status="ativo"
            ).values_list("clinica_id", flat=True)
            clinica = Empresa.objects.filter(id=data["clinica_id"], id__in=clinica_ids).first()

        link_externo = (data.get("link_externo") or "").strip()

        reuniao = ReuniaoSST.objects.create(
            empresa=empresa,
            titulo=titulo,
            descricao=(data.get("descricao") or "").strip(),
            tipo=tipo,
            data_hora=data_hora,
            duracao_minutos=int(data.get("duracao_minutos") or 60),
            link_externo=link_externo,
            clinica=clinica,
            notificar_funcionarios=bool(data.get("notificar_funcionarios", True)),
            observacoes=(data.get("observacoes") or "").strip(),
        )

        # Participantes específicos
        func_ids = data.get("participantes_ids", [])
        if func_ids:
            funcs = FuncionarioSST.objects.filter(id__in=func_ids, empresa=empresa)
            reuniao.participantes.set(funcs)
            alvo_funcs = list(funcs)
        else:
            alvo_funcs = list(FuncionarioSST.objects.filter(empresa=empresa, ativo=True))

        # Notificar funcionários no app
        if reuniao.notificar_funcionarios and tipo in (
            ReuniaoSST.TIPO_FUNCIONARIOS, ReuniaoSST.TIPO_TODOS
        ):
            data_fmt = timezone.localtime(data_hora).strftime("%d/%m/%Y às %H:%M")
            link_reuniao = reuniao.link_reuniao
            for func in alvo_funcs:
                try:
                    NotificacaoFuncionario.objects.create(
                        funcionario=func,
                        empresa=empresa,
                        tipo="geral",
                        titulo=f"📹 Reunião agendada: {titulo}",
                        mensagem=(
                            f"Você foi convocado para a reunião '{titulo}' "
                            f"em {data_fmt}.\n\n"
                            f"🔗 Link para entrar: {link_reuniao}"
                        ),
                        referencia_id=reuniao.id,
                    )
                except Exception:
                    pass

        return JsonResponse(_reuniao_dict(reuniao), status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_reuniao_detalhe(request, reuniao_id):
    empresa, redir = _autenticar(request)
    if redir:
        return JsonResponse({"erro": "não autorizado"}, status=401)

    reuniao = ReuniaoSST.objects.filter(id=reuniao_id, empresa=empresa).first()
    if not reuniao:
        return JsonResponse({"erro": "Reunião não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_reuniao_dict(reuniao))

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        acao = data.get("acao", "")
        if acao == "iniciar":
            reuniao.status = ReuniaoSST.STATUS_EM_ANDAMENTO
            reuniao.save(update_fields=["status"])
        elif acao == "encerrar":
            reuniao.status = ReuniaoSST.STATUS_ENCERRADA
            reuniao.save(update_fields=["status"])
        elif acao == "cancelar":
            reuniao.status = ReuniaoSST.STATUS_CANCELADA
            reuniao.save(update_fields=["status"])
        else:
            return JsonResponse({"erro": "acao inválida. Use: iniciar, encerrar, cancelar"}, status=400)

        return JsonResponse(_reuniao_dict(reuniao))

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── API para o app do funcionário ──────────────────────────────────────────────

def api_funcionario_reunioes(request):
    """Retorna as reuniões futuras/em andamento para o funcionário autenticado."""
    from .views_funcionario_portal import _autenticar_funcionario
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autorizado"}, status=401)

    agora = timezone.now()
    # Reuniões onde o funcionário é participante OU reuniões abertas a todos (sem participantes específicos)
    reunioes_todas = ReuniaoSST.objects.filter(
        empresa=func.empresa,
        status__in=[ReuniaoSST.STATUS_AGENDADA, ReuniaoSST.STATUS_EM_ANDAMENTO],
        data_hora__gte=agora - timezone.timedelta(hours=2),
    ).prefetch_related("participantes")

    resultado = []
    for r in reunioes_todas:
        parte = r.participantes.count() == 0 or r.participantes.filter(id=func.id).exists()
        if parte and r.tipo in (ReuniaoSST.TIPO_FUNCIONARIOS, ReuniaoSST.TIPO_TODOS):
            resultado.append({
                "id": r.id,
                "titulo": r.titulo,
                "descricao": r.descricao,
                "data_hora": timezone.localtime(r.data_hora).isoformat(),
                "data_hora_fmt": timezone.localtime(r.data_hora).strftime("%d/%m/%Y %H:%M"),
                "duracao_minutos": r.duracao_minutos,
                "status": r.status,
                "status_label": r.get_status_display(),
                "link": r.link_reuniao,
            })

    return JsonResponse({"reunioes": resultado})


# ── JWT para Jitsi self-hosted ─────────────────────────────────────────────────

def api_reuniao_token(request, reuniao_id):
    """
    Gera um JWT assinado para o usuário entrar na reunião via Jitsi self-hosted.
    Se JITSI_SECRET não estiver configurado (dev), retorna token=None
    e o frontend usa meet.jit.si sem autenticação.
    """
    empresa, redir = _autenticar(request)
    if redir:
        return JsonResponse({"erro": "não autorizado"}, status=401)

    reuniao = ReuniaoSST.objects.filter(id=reuniao_id, empresa=empresa).first()
    if not reuniao:
        return JsonResponse({"erro": "Reunião não encontrada"}, status=404)

    domain = settings.JITSI_DOMAIN
    app_id = settings.JITSI_APP_ID
    secret = settings.JITSI_SECRET
    sala = reuniao.sala_jitsi

    # Sem secret configurado → modo dev (meet.jit.si público, sem JWT)
    if not secret:
        return JsonResponse({
            "token": None,
            "domain": domain,
            "room": sala,
            "link": reuniao.link_reuniao,
            "dev_mode": True,
        })

    agora = int(time.time())
    payload = {
        "iss": app_id,
        "sub": domain,
        "aud": "jitsi",
        "iat": agora,
        "exp": agora + 7200,  # válido por 2 horas
        "room": sala,
        "context": {
            "user": {
                "name": empresa.nome,
                "email": "",
                "avatar": "",
                "moderator": True,
            },
            "features": {
                "livestreaming": False,
                "recording": False,
            },
        },
    }

    token = pyjwt.encode(payload, secret, algorithm="HS256")

    return JsonResponse({
        "token": token,
        "domain": domain,
        "room": sala,
        "link": f"https://{domain}/{sala}?jwt={token}",
        "dev_mode": False,
    })
