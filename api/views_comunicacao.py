import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    ColaboradorAliasCorporativo,
    FuncionarioSST,
    MensagemChat,
    SalaChat,
    SessaoVideo,
)
from .views_dashboard import _empresa_autenticada


# ─── helpers ──────────────────────────────────────────────────────────────────

def _resolve_nome_alias(alias_publico):
    """Resolve 'sst-{id}' alias codes to real FuncionarioSST names."""
    if alias_publico and alias_publico.startswith("sst-"):
        try:
            func = FuncionarioSST.objects.filter(id=int(alias_publico[4:])).first()
            if func:
                return func.nome
        except (ValueError, Exception):
            pass
    return alias_publico


def _get_or_create_sala_direta(empresa, alias, nome_display=None):
    nome = nome_display or _resolve_nome_alias(alias.alias_publico)
    sala, created = SalaChat.objects.get_or_create(
        empresa=empresa,
        alias=alias,
        defaults={"tipo": SalaChat.TIPO_DIRETO, "nome": nome},
    )
    # Update name if sala was created with the raw alias code
    if not created and sala.nome == alias.alias_publico and nome != alias.alias_publico:
        sala.nome = nome
        sala.save(update_fields=["nome"])
    return sala


def _sala_json(sala):
    ultima = sala.mensagens.last()
    nao_lidas = sala.mensagens.filter(origem=MensagemChat.ORIGEM_COLABORADOR, lida=False).count()
    nome = sala.nome or (sala.alias.alias_publico if sala.alias else "Grupo")
    # Resolve sst-{id} alias codes to real employee names for display
    if sala.alias:
        nome = _resolve_nome_alias(sala.alias.alias_publico) if nome == sala.alias.alias_publico else nome
    return {
        "id": sala.id,
        "tipo": sala.tipo,
        "nome": nome,
        "alias_codigo": sala.alias.alias_publico if sala.alias else None,
        "ultima_mensagem": ultima.texto[:80] if ultima else None,
        "ultima_atividade": ultima.criado_em.isoformat() if ultima else None,
        "nao_lidas": nao_lidas,
    }


def _mensagem_json(msg):
    return {
        "id": msg.id,
        "origem": msg.origem,
        "texto": msg.texto,
        "lida": msg.lida,
        "criado_em": msg.criado_em.isoformat(),
    }


# ─── Empresa-side pages ───────────────────────────────────────────────────────

def painel_comunicacao(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "comunicacao_painel.html", {"empresa_nome": empresa.nome})


def sala_video_empresa(request, sessao_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    sessao = get_object_or_404(SessaoVideo, id=sessao_id, empresa=empresa)
    link_colaborador = ""
    if sessao.alias:
        link_colaborador = (
            request.build_absolute_uri(
                f"/colaborador/c/{sessao.alias.alias_publico}/video/{sessao.sala_jitsi}/"
            )
        )
    return render(request, "comunicacao_video.html", {
        "empresa_nome": empresa.nome,
        "sessao_titulo": sessao.titulo,
        "sala_jitsi": sessao.sala_jitsi,
        "sessao_id": sessao.id,
        "link_colaborador": link_colaborador,
    })


# ─── Empresa-side API ─────────────────────────────────────────────────────────

def api_listar_salas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    salas = SalaChat.objects.filter(empresa=empresa, ativo=True).prefetch_related("mensagens")
    return JsonResponse({"salas": [_sala_json(s) for s in salas]})


def api_colaboradores_comunicacao(request):
    """GET → lista de funcionários SST (nomes reais) para o modal Nova Conversa"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    # Prefer FuncionarioSST so the manager sees real employee names
    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).order_by("nome")
    if funcionarios.exists():
        colaboradores = []
        for func in funcionarios:
            # Stable alias code derived from the SST employee ID
            alias_code = f"sst-{func.id}"
            alias, _ = ColaboradorAliasCorporativo.objects.get_or_create(
                empresa=empresa,
                alias_publico=alias_code,
            )
            colaboradores.append({
                "id": alias.id,
                "alias_codigo": alias_code,
                "nome": func.nome,
                "cargo": func.cargo or "",
            })
        return JsonResponse({"colaboradores": colaboradores})

    # Fallback: use existing anonymous aliases when no SST employees exist
    aliases = ColaboradorAliasCorporativo.objects.filter(
        empresa=empresa, ativo=True
    ).select_related("cargo")
    return JsonResponse({
        "colaboradores": [
            {
                "id": a.id,
                "alias_codigo": a.alias_publico,
                "nome": a.alias_publico,
                "cargo": a.cargo.nome if a.cargo else "",
            }
            for a in aliases
        ]
    })


def api_criar_sala(request):
    """POST {alias_codigo} → cria ou retorna sala direta"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    codigo = data.get("alias_codigo", "").strip()
    alias = ColaboradorAliasCorporativo.objects.filter(empresa=empresa, alias_publico=codigo).first()
    if not alias:
        return JsonResponse({"erro": "colaborador não encontrado"}, status=404)
    sala = _get_or_create_sala_direta(empresa, alias)
    return JsonResponse({"sala": _sala_json(sala)})


def api_mensagens(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa)
    # mark colaborador messages as read
    sala.mensagens.filter(origem=MensagemChat.ORIGEM_COLABORADOR, lida=False).update(lida=True)
    # optional: only return messages after ?desde=<iso>
    desde = request.GET.get("desde")
    qs = sala.mensagens.all()
    if desde:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(desde.replace("Z", "+00:00"))
            qs = qs.filter(criado_em__gt=dt)
        except ValueError:
            pass
    return JsonResponse({"mensagens": [_mensagem_json(m) for m in qs]})


def api_marcar_lida(request, sala_id):
    """POST → marca msgs do colaborador como lidas (atalho; api_mensagens já faz isso)"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa)
    sala.mensagens.filter(origem=MensagemChat.ORIGEM_COLABORADOR, lida=False).update(lida=True)
    return JsonResponse({"ok": True})


def api_enviar_mensagem(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    texto = data.get("texto", "").strip()
    if not texto:
        return JsonResponse({"erro": "mensagem vazia"}, status=400)
    msg = MensagemChat.objects.create(
        sala=sala, empresa=empresa,
        origem=MensagemChat.ORIGEM_EMPRESA,
        texto=texto[:2000],
    )
    return JsonResponse({"mensagem": _mensagem_json(msg)})


def api_criar_video(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    sala_id = data.get("sala_id")
    titulo = data.get("titulo", "Reunião")[:120]
    alias = None
    if sala_id:
        sala = SalaChat.objects.filter(id=sala_id, empresa=empresa).first()
        if sala and sala.alias:
            alias = sala.alias

    sessao = SessaoVideo.objects.create(empresa=empresa, alias=alias, titulo=titulo)

    # Post a system message in the sala so the colaborador sees the video link
    if alias:
        sala = _get_or_create_sala_direta(empresa, alias)
        link = f"/colaborador/c/{alias.alias_publico}/video/{sessao.sala_jitsi}/"
        MensagemChat.objects.create(
            sala=sala, empresa=empresa,
            origem=MensagemChat.ORIGEM_EMPRESA,
            texto=f"📹 Reunião iniciada! Clique para entrar: {link}",
        )

    return JsonResponse({
        "sessao_id": sessao.id,
        "sala_jitsi": sessao.sala_jitsi,
        "link_colaborador": (
            f"/colaborador/c/{alias.alias_publico}/video/{sessao.sala_jitsi}/"
            if alias else None
        ),
    })


def api_encerrar_video(request, sessao_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    sessao = get_object_or_404(SessaoVideo, id=sessao_id, empresa=empresa)
    sessao.status = SessaoVideo.STATUS_ENCERRADA
    sessao.encerrado_em = timezone.now()
    sessao.save(update_fields=["status", "encerrado_em"])
    return JsonResponse({"ok": True})


# ─── Colaborador-side pages ───────────────────────────────────────────────────

def _resolve_alias(codigo):
    return ColaboradorAliasCorporativo.objects.select_related("empresa").filter(
        alias_publico=codigo
    ).first()


def colaborador_chat(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return redirect("/")
    sala = _get_or_create_sala_direta(alias.empresa, alias)
    return render(request, "colaborador_chat.html", {
        "codigo": codigo,
        "empresa_nome": alias.empresa.nome,
        "sala_id": sala.id,
    })


def colaborador_video(request, codigo, sala):
    alias = _resolve_alias(codigo)
    if not alias:
        return redirect("/")
    sessao = get_object_or_404(
        SessaoVideo,
        sala_jitsi=sala,
        empresa=alias.empresa,
        status=SessaoVideo.STATUS_ATIVA,
    )
    return render(request, "colaborador_video.html", {
        "codigo": codigo,
        "sala_jitsi": sessao.sala_jitsi,
        "sessao_titulo": sessao.titulo,
        "empresa_nome": alias.empresa.nome,
    })


# ─── Colaborador-side API ─────────────────────────────────────────────────────

def api_colab_mensagens(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    sala = _get_or_create_sala_direta(alias.empresa, alias)
    # mark empresa messages as read
    sala.mensagens.filter(origem=MensagemChat.ORIGEM_EMPRESA, lida=False).update(lida=True)
    desde = request.GET.get("desde")
    qs = sala.mensagens.all()
    if desde:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(desde.replace("Z", "+00:00"))
            qs = qs.filter(criado_em__gt=dt)
        except ValueError:
            pass
    return JsonResponse({"mensagens": [_mensagem_json(m) for m in qs]})


def api_colab_enviar(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    texto = data.get("texto", "").strip()
    if not texto:
        return JsonResponse({"erro": "mensagem vazia"}, status=400)
    sala = _get_or_create_sala_direta(alias.empresa, alias)
    msg = MensagemChat.objects.create(
        sala=sala, empresa=alias.empresa,
        origem=MensagemChat.ORIGEM_COLABORADOR,
        texto=texto[:2000],
    )
    return JsonResponse({"mensagem": _mensagem_json(msg)})


def api_colab_video_ativa(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    sessao = SessaoVideo.objects.filter(
        empresa=alias.empresa, alias=alias, status=SessaoVideo.STATUS_ATIVA
    ).first()
    if not sessao:
        return JsonResponse({"video": None})
    return JsonResponse({
        "video": {
            "id": sessao.id,
            "sala_jitsi": sessao.sala_jitsi,
            "titulo": sessao.titulo,
            "link": f"/colaborador/c/{codigo}/video/{sessao.sala_jitsi}/",
        }
    })


# ─── Grupos de chat ───────────────────────────────────────────────────────────
from .models import MembroGrupoChat


def painel_grupos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_comunicacao_grupos.html", {"empresa_nome": empresa.nome})


def api_criar_grupo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    nome = data.get("nome", "").strip()
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)
    membros_codigos = data.get("membros", [])

    sala = SalaChat.objects.create(
        empresa=empresa, tipo=SalaChat.TIPO_GRUPO, nome=nome
    )
    adicionados = 0
    for codigo in membros_codigos:
        alias = ColaboradorAliasCorporativo.objects.filter(
            empresa=empresa, alias_publico=codigo
        ).first()
        if alias:
            MembroGrupoChat.objects.get_or_create(sala=sala, alias=alias)
            adicionados += 1

    return JsonResponse({"sala": _sala_json(sala), "membros_adicionados": adicionados}, status=201)


def api_listar_salas_por_tipo(request):
    """GET /api/comunicacao/salas/?tipo=grupo|direto — filtra por tipo"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    tipo = request.GET.get("tipo")
    qs = SalaChat.objects.filter(empresa=empresa, ativo=True)
    if tipo:
        qs = qs.filter(tipo=tipo)
    # Enrich with member count for groups
    salas = []
    for s in qs:
        d = _sala_json(s)
        if s.tipo == SalaChat.TIPO_GRUPO:
            d["membros_count"] = MembroGrupoChat.objects.filter(sala=s).count()
        salas.append(d)
    return JsonResponse({"salas": salas})


def api_membros_grupo(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa, tipo=SalaChat.TIPO_GRUPO)
    membros = MembroGrupoChat.objects.filter(sala=sala).select_related("alias")
    return JsonResponse({
        "membros": [{"codigo": m.alias.alias_publico} for m in membros]
    })


@csrf_exempt
def api_editar_grupo(request, sala_id):
    """PUT /api/comunicacao/grupos/<sala_id>/ — editar nome/membros de um grupo"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa, tipo=SalaChat.TIPO_GRUPO)
    if request.method != "PUT":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    nome = data.get("nome", "").strip()
    if nome:
        sala.nome = nome
        sala.save()
    # Update members if provided
    novos_membros = data.get("membros")
    if novos_membros is not None:
        # Replace member list
        MembroGrupoChat.objects.filter(sala=sala).delete()
        adicionados = 0
        for codigo in novos_membros:
            alias = ColaboradorAliasCorporativo.objects.filter(
                empresa=empresa, alias_publico=codigo
            ).first()
            if alias:
                MembroGrupoChat.objects.get_or_create(sala=sala, alias=alias)
                adicionados += 1
    return JsonResponse({"sala": _sala_json(sala), "ok": True})
