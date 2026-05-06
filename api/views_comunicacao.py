import json
from datetime import datetime

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    ColaboradorAliasCorporativo,
    MembroGrupoChat,
    MensagemChat,
    SalaChat,
    SessaoVideo,
)
from .views_dashboard import _empresa_autenticada


def _alias_queryset(empresa):
    return (
        ColaboradorAliasCorporativo.objects.filter(empresa=empresa, ativo=True)
        .select_related("unidade", "setor", "turno", "cargo")
        .order_by("-atualizado_em")
    )


def _alias_label(alias):
    partes = []
    if alias.cargo:
        partes.append(alias.cargo.nome)
    if alias.setor:
        partes.append(alias.setor.nome)
    if alias.unidade:
        partes.append(alias.unidade.nome)
    return " · ".join(partes) or f"Colaborador {alias.alias_publico[:8]}"


def _alias_json(alias):
    return {
        "id": alias.alias_publico,
        "codigo": alias.alias_publico,
        "alias_codigo": alias.alias_publico,
        "nome": _alias_label(alias),
        "cargo": alias.cargo.nome if alias.cargo else "",
        "setor": alias.setor.nome if alias.setor else "",
        "unidade": alias.unidade.nome if alias.unidade else "",
        "turno": alias.turno.nome if alias.turno else "",
        "permite_contato": alias.permite_contato,
    }


def _get_or_create_sala_direta(empresa, alias):
    sala, created = SalaChat.objects.get_or_create(
        empresa=empresa,
        alias=alias,
        defaults={"tipo": SalaChat.TIPO_DIRETO, "nome": _alias_label(alias)},
    )
    if not created and (sala.tipo != SalaChat.TIPO_DIRETO or not sala.nome):
        sala.tipo = SalaChat.TIPO_DIRETO
        sala.nome = sala.nome or _alias_label(alias)
        sala.save(update_fields=["tipo", "nome"])
    return sala


def _sala_json(sala):
    ultima = sala.mensagens.order_by("-criado_em").first()
    nao_lidas = sala.mensagens.filter(origem=MensagemChat.ORIGEM_COLABORADOR, lida=False).count()
    membros_count = sala.membros.count() if sala.tipo == SalaChat.TIPO_GRUPO else 0
    nome = sala.nome
    if sala.tipo == SalaChat.TIPO_DIRETO and sala.alias:
        nome = sala.nome or _alias_label(sala.alias)
    return {
        "id": sala.id,
        "tipo": sala.tipo,
        "nome": nome or "Grupo",
        "alias_codigo": sala.alias.alias_publico if sala.alias else None,
        "ultima_mensagem": ultima.texto[:80] if ultima else None,
        "ultima_mensagem_em": ultima.criado_em.isoformat() if ultima else None,
        "ultima_atividade": (ultima.criado_em if ultima else sala.criado_em).isoformat(),
        "nao_lidas": nao_lidas,
        "membros_count": membros_count,
    }


def _mensagem_json(msg):
    remetente_nome = "Empresa" if msg.origem == MensagemChat.ORIGEM_EMPRESA else "Colaborador"
    return {
        "id": msg.id,
        "origem": msg.origem,
        "remetente": msg.origem,
        "remetente_nome": remetente_nome,
        "tipo": msg.origem,
        "texto": msg.texto,
        "conteudo": msg.texto,
        "enviado_por_empresa": msg.origem == MensagemChat.ORIGEM_EMPRESA,
        "lida": msg.lida,
        "criado_em": msg.criado_em.isoformat(),
    }


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except Exception:
        return None


def _filtrar_desde(qs, valor):
    if not valor:
        return qs
    if str(valor).isdigit():
        return qs.filter(id__gt=int(valor))
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return qs.filter(criado_em__gt=dt)
    except ValueError:
        return qs


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
        link_colaborador = request.build_absolute_uri(
            f"/colaborador/c/{sessao.alias.alias_publico}/video/{sessao.sala_jitsi}/"
        )
    return render(request, "comunicacao_video.html", {
        "empresa_nome": empresa.nome,
        "sessao_titulo": sessao.titulo,
        "sala_jitsi": sessao.sala_jitsi,
        "sessao_id": sessao.id,
        "link_colaborador": link_colaborador,
    })


def api_colaboradores_comunicacao(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    return JsonResponse({"colaboradores": [_alias_json(alias) for alias in _alias_queryset(empresa)]})


def api_listar_salas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    tipo = request.GET.get("tipo", "")
    salas = (
        SalaChat.objects.filter(empresa=empresa, ativo=True)
        .select_related("alias", "alias__unidade", "alias__setor", "alias__turno", "alias__cargo")
        .prefetch_related("mensagens", "membros")
    )
    if tipo in {SalaChat.TIPO_DIRETO, SalaChat.TIPO_GRUPO}:
        salas = salas.filter(tipo=tipo)
    return JsonResponse({"salas": [_sala_json(sala) for sala in salas]})


def api_criar_sala(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    codigo = str(
        data.get("alias_codigo")
        or data.get("alias_code")
        or data.get("codigo")
        or data.get("colaborador_id")
        or ""
    ).strip()
    alias = _alias_queryset(empresa).filter(alias_publico=codigo).first()
    if not alias and codigo.isdigit():
        alias = _alias_queryset(empresa).filter(id=int(codigo)).first()
    if not alias:
        return JsonResponse({"erro": "colaborador não encontrado"}, status=404)

    sala = _get_or_create_sala_direta(empresa, alias)
    return JsonResponse({"sala": _sala_json(sala)})


def api_criar_grupo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = (data.get("nome") or "").strip()
    membros_codigos = data.get("membros") or []
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)
    if not membros_codigos:
        return JsonResponse({"erro": "selecione pelo menos um colaborador"}, status=400)

    sala = SalaChat.objects.create(empresa=empresa, tipo=SalaChat.TIPO_GRUPO, nome=nome[:120])
    aliases = _alias_queryset(empresa).filter(alias_publico__in=membros_codigos)
    for alias in aliases:
        MembroGrupoChat.objects.get_or_create(sala=sala, alias=alias)
    payload = _sala_json(sala)
    return JsonResponse({"sala": payload, **payload}, status=201)


def api_membros_grupo(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa, tipo=SalaChat.TIPO_GRUPO)
    membros = MembroGrupoChat.objects.filter(sala=sala).select_related(
        "alias", "alias__unidade", "alias__setor", "alias__turno", "alias__cargo"
    )
    return JsonResponse({"membros": [_alias_json(m.alias) for m in membros]})


def api_mensagens(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa)
    sala.mensagens.filter(origem=MensagemChat.ORIGEM_COLABORADOR, lida=False).update(lida=True)
    qs = _filtrar_desde(sala.mensagens.all(), request.GET.get("desde"))
    return JsonResponse({"mensagens": [_mensagem_json(m) for m in qs]})


def api_enviar_mensagem(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    texto = (data.get("texto") or data.get("conteudo") or "").strip()
    if not texto:
        return JsonResponse({"erro": "mensagem vazia"}, status=400)

    msg = MensagemChat.objects.create(
        sala=sala,
        empresa=empresa,
        origem=MensagemChat.ORIGEM_EMPRESA,
        texto=texto[:2000],
    )
    if sala.tipo == SalaChat.TIPO_GRUPO:
        prefixo = f"[{sala.nome}] "
        for membro in sala.membros.select_related("alias"):
            direta = _get_or_create_sala_direta(empresa, membro.alias)
            MensagemChat.objects.create(
                sala=direta,
                empresa=empresa,
                origem=MensagemChat.ORIGEM_EMPRESA,
                texto=(prefixo + texto)[:2000],
            )
    return JsonResponse({"mensagem": _mensagem_json(msg)})


def api_marcar_lida(request, sala_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    sala = get_object_or_404(SalaChat, id=sala_id, empresa=empresa)
    sala.mensagens.filter(origem=MensagemChat.ORIGEM_COLABORADOR, lida=False).update(lida=True)
    return JsonResponse({"ok": True})


def api_criar_video(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    sala = None
    alias = None
    sala_id = data.get("sala_id")
    if sala_id:
        sala = SalaChat.objects.filter(id=sala_id, empresa=empresa).first()
        if sala and sala.tipo == SalaChat.TIPO_DIRETO:
            alias = sala.alias

    titulo = (data.get("titulo") or "Reunião")[:120]
    sessao = SessaoVideo.objects.create(empresa=empresa, alias=alias, titulo=titulo)

    if sala:
        if sala.tipo == SalaChat.TIPO_GRUPO:
            MensagemChat.objects.create(
                sala=sala,
                empresa=empresa,
                origem=MensagemChat.ORIGEM_EMPRESA,
                texto=f"Reunião iniciada para o grupo: /colaborador/c/SEU-CODIGO/video/{sessao.sala_jitsi}/",
            )
            for membro in sala.membros.select_related("alias"):
                link = f"/colaborador/c/{membro.alias.alias_publico}/video/{sessao.sala_jitsi}/"
                direta = _get_or_create_sala_direta(empresa, membro.alias)
                MensagemChat.objects.create(
                    sala=direta,
                    empresa=empresa,
                    origem=MensagemChat.ORIGEM_EMPRESA,
                    texto=f"Reunião do grupo {sala.nome} iniciada. Entre por aqui: {link}",
                )
        elif alias:
            link = f"/colaborador/c/{alias.alias_publico}/video/{sessao.sala_jitsi}/"
            MensagemChat.objects.create(
                sala=sala,
                empresa=empresa,
                origem=MensagemChat.ORIGEM_EMPRESA,
                texto=f"Reunião iniciada. Entre por aqui: {link}",
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


def _resolve_alias(codigo):
    return ColaboradorAliasCorporativo.objects.select_related("empresa").filter(
        alias_publico=codigo,
        ativo=True,
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
    sessao = SessaoVideo.objects.filter(
        Q(alias=alias) | Q(alias__isnull=True),
        sala_jitsi=sala,
        empresa=alias.empresa,
        status=SessaoVideo.STATUS_ATIVA,
    ).first()
    if not sessao:
        return redirect(f"/colaborador/c/{codigo}/chat/")
    return render(request, "colaborador_video.html", {
        "codigo": codigo,
        "sala_jitsi": sessao.sala_jitsi,
        "sessao_titulo": sessao.titulo,
        "empresa_nome": alias.empresa.nome,
    })


def api_colab_mensagens(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    sala = _get_or_create_sala_direta(alias.empresa, alias)
    sala.mensagens.filter(origem=MensagemChat.ORIGEM_EMPRESA, lida=False).update(lida=True)
    qs = _filtrar_desde(sala.mensagens.all(), request.GET.get("desde"))
    return JsonResponse({"mensagens": [_mensagem_json(m) for m in qs]})


def api_colab_enviar(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    texto = (data.get("texto") or data.get("conteudo") or "").strip()
    if not texto:
        return JsonResponse({"erro": "mensagem vazia"}, status=400)
    sala = _get_or_create_sala_direta(alias.empresa, alias)
    msg = MensagemChat.objects.create(
        sala=sala,
        empresa=alias.empresa,
        origem=MensagemChat.ORIGEM_COLABORADOR,
        texto=texto[:2000],
    )
    return JsonResponse({"mensagem": _mensagem_json(msg)})


def api_colab_video_ativa(request, codigo):
    alias = _resolve_alias(codigo)
    if not alias:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    sessao = SessaoVideo.objects.filter(
        empresa=alias.empresa,
        alias=alias,
        status=SessaoVideo.STATUS_ATIVA,
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
