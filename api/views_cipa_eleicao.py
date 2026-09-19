"""
CIPA — Votação Eletrônica (NR-05) — SoloCRT SST.

Processo eleitoral online: inscrição de candidatos, urna eletrônica com voto
secreto (separação votante × cédula), apuração automática e ata de resultado.
Aditivo — não altera o módulo CIPA existente (views_cipa.py).

Endpoints:
  GET/POST /api/sst/cipa/eleicoes/                       — lista / cria eleição
  GET/PATCH/DELETE /api/sst/cipa/eleicoes/<id>/          — detalhe
  GET/POST /api/sst/cipa/eleicoes/<id>/candidatos/       — lista / inscreve candidato
  PATCH/DELETE /api/sst/cipa/candidatos/<id>/            — defere / remove
  POST /api/sst/cipa/eleicoes/<id>/votar/                — registra voto (secreto)
  POST /api/sst/cipa/eleicoes/<id>/apurar/               — apura resultado
  GET  /api/sst/cipa/eleicoes/<id>/resultado/            — resultado
  GET  /sst/cipa/eleicao/                                — página
"""
import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from .access_control import api_requer_feature, requer_feature_pacote, requer_permissao_modulo, principal_pode_operacao_setorial

logger = logging.getLogger(__name__)


def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


def _eleicao_dict(e):
    return {
        "id": e.id,
        "titulo": e.titulo,
        "comissao_id": e.comissao_id,
        "num_vagas": e.num_vagas,
        "inscricao_inicio": str(e.inscricao_inicio) if e.inscricao_inicio else None,
        "inscricao_fim": str(e.inscricao_fim) if e.inscricao_fim else None,
        "votacao_inicio": e.votacao_inicio.isoformat() if e.votacao_inicio else None,
        "votacao_fim": e.votacao_fim.isoformat() if e.votacao_fim else None,
        "status": e.status,
        "apurada_em": e.apurada_em.isoformat() if e.apurada_em else None,
        "total_candidatos": e.candidatos.count(),
        "total_votantes": e.votantes.count(),
        "total_votaram": e.votantes.filter(votou=True).count(),
    }


def _candidato_dict(c):
    return {
        "id": c.id,
        "funcionario_id": c.funcionario_id,
        "funcionario_nome": c.funcionario.nome,
        "funcionario_cargo": c.funcionario.cargo,
        "numero": c.numero,
        "proposta": c.proposta,
        "deferido": c.deferido,
        "votos": c.votos,
    }


@api_requer_feature("sst.cipa")
def api_cipa_eleicoes(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import EleicaoCIPA

    if request.method == "GET":
        try:
            qs = EleicaoCIPA.objects.filter(empresa=empresa)
            return JsonResponse({"total": qs.count(), "eleicoes": [_eleicao_dict(e) for e in qs[:50]]})
        except Exception:
            logger.exception("Erro ao listar eleições CIPA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão para criar eleição"}, status=403)
        try:
            data = _json(request)
            if not data.get("titulo"):
                return JsonResponse({"erro": "titulo é obrigatório"}, status=400)
            e = EleicaoCIPA.objects.create(
                empresa=empresa,
                titulo=data["titulo"],
                num_vagas=data.get("num_vagas", 1),
                inscricao_inicio=data.get("inscricao_inicio") or None,
                inscricao_fim=data.get("inscricao_fim") or None,
                votacao_inicio=data.get("votacao_inicio") or None,
                votacao_fim=data.get("votacao_fim") or None,
                status=data.get("status", "inscricoes"),
            )
            if data.get("comissao_id"):
                from .models import ComissaoCIPA
                e.comissao = ComissaoCIPA.objects.filter(id=data["comissao_id"], empresa=empresa).first()
                e.save()
            return JsonResponse({"ok": True, "data": _eleicao_dict(e)}, status=201)
        except Exception:
            logger.exception("Erro ao criar eleição CIPA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_eleicao_detalhe(request, eleicao_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import EleicaoCIPA
    try:
        e = EleicaoCIPA.objects.get(id=eleicao_id, empresa=empresa)
    except EleicaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Eleição não encontrada"}, status=404)

    if request.method == "GET":
        d = _eleicao_dict(e)
        d["candidatos"] = [_candidato_dict(c) for c in e.candidatos.select_related("funcionario")]
        return JsonResponse(d)

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            for f in ("titulo", "num_vagas", "status"):
                if f in data:
                    setattr(e, f, data[f])
            for f in ("inscricao_inicio", "inscricao_fim", "votacao_inicio", "votacao_fim"):
                if f in data:
                    setattr(e, f, data[f] or None)
            e.save()
            return JsonResponse({"ok": True, "data": _eleicao_dict(e)})
        except Exception:
            logger.exception("Erro ao editar eleição CIPA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        e.delete()
        return JsonResponse({"ok": True, "msg": "Eleição removida"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_candidatos(request, eleicao_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import EleicaoCIPA, CandidatoCIPA, FuncionarioSST
    try:
        e = EleicaoCIPA.objects.get(id=eleicao_id, empresa=empresa)
    except EleicaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Eleição não encontrada"}, status=404)

    if request.method == "GET":
        cs = e.candidatos.select_related("funcionario")
        return JsonResponse({"total": cs.count(), "candidatos": [_candidato_dict(c) for c in cs]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        if e.status != "inscricoes":
            return JsonResponse({"erro": "Inscrições encerradas para esta eleição"}, status=400)
        try:
            data = _json(request)
            if not data.get("funcionario_id"):
                return JsonResponse({"erro": "funcionario_id é obrigatório"}, status=400)
            try:
                func = FuncionarioSST.objects.get(id=data["funcionario_id"], empresa=empresa)
            except FuncionarioSST.DoesNotExist:
                return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
            if CandidatoCIPA.objects.filter(eleicao=e, funcionario=func).exists():
                return JsonResponse({"erro": "Funcionário já inscrito nesta eleição"}, status=400)
            numero = data.get("numero") or (e.candidatos.count() + 1)
            c = CandidatoCIPA.objects.create(
                eleicao=e, funcionario=func, numero=numero,
                proposta=data.get("proposta", ""), deferido=data.get("deferido", True),
            )
            return JsonResponse({"ok": True, "data": _candidato_dict(c)}, status=201)
        except Exception:
            logger.exception("Erro ao inscrever candidato CIPA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_candidato_detalhe(request, candidato_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import CandidatoCIPA
    try:
        c = CandidatoCIPA.objects.select_related("funcionario", "eleicao").get(
            id=candidato_id, eleicao__empresa=empresa
        )
    except CandidatoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Candidato não encontrado"}, status=404)

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("numero", "proposta", "deferido"):
            if f in data:
                setattr(c, f, data[f])
        c.save()
        return JsonResponse({"ok": True, "data": _candidato_dict(c)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        c.delete()
        return JsonResponse({"ok": True, "msg": "Candidato removido"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.cipa")
def api_cipa_votar(request, eleicao_id):
    """Registra um voto secreto. Marca o votante como já votado e grava a cédula
    anônima em transação atômica, impedindo voto duplo."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import EleicaoCIPA, CandidatoCIPA, VotanteCIPA, VotoCIPA, FuncionarioSST
    try:
        e = EleicaoCIPA.objects.get(id=eleicao_id, empresa=empresa)
    except EleicaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Eleição não encontrada"}, status=404)

    if e.status != "votacao":
        return JsonResponse({"erro": "Votação não está aberta"}, status=400)
    agora = timezone.now()
    if e.votacao_inicio and agora < e.votacao_inicio:
        return JsonResponse({"erro": "Votação ainda não começou"}, status=400)
    if e.votacao_fim and agora > e.votacao_fim:
        return JsonResponse({"erro": "Votação encerrada"}, status=400)

    data = _json(request)
    eleitor_id = data.get("eleitor_funcionario_id")
    candidato_id = data.get("candidato_id")
    if not eleitor_id or not candidato_id:
        return JsonResponse({"erro": "eleitor_funcionario_id e candidato_id são obrigatórios"}, status=400)

    try:
        eleitor = FuncionarioSST.objects.get(id=eleitor_id, empresa=empresa)
    except FuncionarioSST.DoesNotExist:
        return JsonResponse({"erro": "Eleitor não encontrado"}, status=404)
    try:
        cand = CandidatoCIPA.objects.get(id=candidato_id, eleicao=e, deferido=True)
    except CandidatoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Candidato inválido"}, status=404)

    try:
        with transaction.atomic():
            votante, _ = VotanteCIPA.objects.select_for_update().get_or_create(eleicao=e, funcionario=eleitor)
            if votante.votou:
                return JsonResponse({"erro": "Este eleitor já votou"}, status=409)
            votante.votou = True
            votante.votou_em = agora
            votante.save()
            VotoCIPA.objects.create(eleicao=e, candidato=cand)  # cédula anônima
        return JsonResponse({"ok": True, "msg": "Voto registrado com sucesso"})
    except Exception:
        logger.exception("Erro ao registrar voto CIPA")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


@api_requer_feature("sst.cipa")
def api_cipa_apurar(request, eleicao_id):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Sem permissão para apurar"}, status=403)
    from django.db.models import Count
    from .models import EleicaoCIPA, VotoCIPA
    try:
        e = EleicaoCIPA.objects.get(id=eleicao_id, empresa=empresa)
    except EleicaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Eleição não encontrada"}, status=404)

    try:
        contagem = dict(
            VotoCIPA.objects.filter(eleicao=e).values_list("candidato_id").annotate(n=Count("id"))
        )
        for c in e.candidatos.all():
            c.votos = contagem.get(c.id, 0)
            c.save(update_fields=["votos"])
        e.status = "apurada"
        e.apurada_em = timezone.now()
        e.save(update_fields=["status", "apurada_em"])
        return JsonResponse({"ok": True, "msg": "Apuração concluída"})
    except Exception:
        logger.exception("Erro ao apurar eleição CIPA")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


@api_requer_feature("sst.cipa")
def api_cipa_resultado(request, eleicao_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import EleicaoCIPA
    try:
        e = EleicaoCIPA.objects.get(id=eleicao_id, empresa=empresa)
    except EleicaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Eleição não encontrada"}, status=404)

    cands = sorted(
        [_candidato_dict(c) for c in e.candidatos.select_related("funcionario")],
        key=lambda x: x["votos"], reverse=True,
    )
    for i, c in enumerate(cands):
        c["classificacao"] = i + 1
        c["eleito"] = c["deferido"] and i < e.num_vagas and c["votos"] > 0
    return JsonResponse({
        "eleicao": _eleicao_dict(e),
        "num_vagas": e.num_vagas,
        "resultado": cands,
    })


@requer_feature_pacote("sst.cipa", "CIPA — Votação Eletrônica")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_cipa_eleicao_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_cipa_eleicao.html", {"empresa_nome": empresa.nome})


# ── Votantes (eleitores) + links individuais ─────────────────────────────────

@api_requer_feature("sst.cipa")
def api_cipa_votantes(request, eleicao_id):
    """GET lista votantes + links · POST inscreve eleitores aptos (gera tokens)."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    import secrets
    from .models import EleicaoCIPA, VotanteCIPA, FuncionarioSST
    try:
        e = EleicaoCIPA.objects.get(id=eleicao_id, empresa=empresa)
    except EleicaoCIPA.DoesNotExist:
        return JsonResponse({"erro": "Eleição não encontrada"}, status=404)

    if request.method == "GET":
        base = f"{request.scheme}://{request.get_host()}"
        vs = e.votantes.select_related("funcionario")
        return JsonResponse({
            "total": vs.count(),
            "votaram": vs.filter(votou=True).count(),
            "votantes": [{
                "id": v.id,
                "funcionario_nome": v.funcionario.nome,
                "votou": v.votou,
                "link": f"{base}/cipa/votar/{v.token}/" if v.token else None,
            } for v in vs],
        })

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        ids = data.get("funcionario_ids")
        if ids == "todos" or data.get("todos"):
            funcs = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
        else:
            if not isinstance(ids, list) or not ids:
                return JsonResponse({"erro": "Informe funcionario_ids (lista) ou todos=true"}, status=400)
            funcs = FuncionarioSST.objects.filter(empresa=empresa, id__in=ids)
        criados = 0
        for f in funcs:
            v, novo = VotanteCIPA.objects.get_or_create(eleicao=e, funcionario=f)
            if not v.token:
                v.token = secrets.token_urlsafe(24)
                v.save(update_fields=["token"])
            if novo:
                criados += 1
        return JsonResponse({"ok": True, "criados": criados, "total": e.votantes.count()})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Portal público de votação (colaborador vota pelo próprio link) ────────────

def _votante_por_token(token):
    from .models import VotanteCIPA
    if not token:
        return None
    return VotanteCIPA.objects.select_related("eleicao", "funcionario").filter(token=token).first()


def cipa_votar_page(request, token):
    from django.shortcuts import render
    v = _votante_por_token(token)
    if not v:
        return render(request, "cipa_votar.html", {"invalido": True, "token": ""})
    return render(request, "cipa_votar.html", {
        "invalido": False, "token": token,
        "eleitor": v.funcionario.nome, "eleicao_titulo": v.eleicao.titulo,
    })


def api_cipa_votar_publico(request, token):
    """GET candidatos + status · POST registra o voto secreto do próprio eleitor."""
    from django.utils import timezone
    from django.db import transaction
    from .models import CandidatoCIPA, VotoCIPA
    v = _votante_por_token(token)
    if not v:
        return JsonResponse({"erro": "Link de votação inválido"}, status=403)
    e = v.eleicao

    if request.method == "GET":
        cands = [_candidato_dict(c) for c in e.candidatos.filter(deferido=True).select_related("funcionario")]
        for c in cands:
            c.pop("votos", None)  # nunca expor contagem durante a votação
        return JsonResponse({
            "eleicao": e.titulo, "eleitor": v.funcionario.nome,
            "status": e.status, "ja_votou": v.votou,
            "candidatos": cands,
        })

    if request.method == "POST":
        if e.status != "votacao":
            return JsonResponse({"erro": "Votação não está aberta"}, status=400)
        agora = timezone.now()
        if e.votacao_inicio and agora < e.votacao_inicio:
            return JsonResponse({"erro": "Votação ainda não começou"}, status=400)
        if e.votacao_fim and agora > e.votacao_fim:
            return JsonResponse({"erro": "Votação encerrada"}, status=400)
        data = _json(request)
        cand_id = data.get("candidato_id")
        if not cand_id:
            return JsonResponse({"erro": "candidato_id é obrigatório"}, status=400)
        try:
            cand = CandidatoCIPA.objects.get(id=cand_id, eleicao=e, deferido=True)
        except CandidatoCIPA.DoesNotExist:
            return JsonResponse({"erro": "Candidato inválido"}, status=404)
        try:
            with transaction.atomic():
                from .models import VotanteCIPA
                vlock = VotanteCIPA.objects.select_for_update().get(id=v.id)
                if vlock.votou:
                    return JsonResponse({"erro": "Você já votou nesta eleição"}, status=409)
                vlock.votou = True
                vlock.votou_em = agora
                vlock.save(update_fields=["votou", "votou_em"])
                VotoCIPA.objects.create(eleicao=e, candidato=cand)  # cédula anônima
            return JsonResponse({"ok": True, "msg": "Voto registrado. Obrigado por participar!"})
        except Exception:
            logger.exception("Erro no voto público CIPA")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)
