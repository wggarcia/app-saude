"""
Grupo Focal Psicossocial (NR-01) — SoloCRT SST.

Escuta estruturada em grupo para identificar fatores de risco psicossocial,
complementar às avaliações individuais já existentes (views_psicossocial.py).
Aditivo — não altera o módulo psicossocial existente.

Endpoints:
  GET/POST /api/sst/psicossocial/grupos-focais/            — lista / cria
  GET/PATCH/DELETE /api/sst/psicossocial/grupos-focais/<id>/  — detalhe
  GET/POST /api/sst/psicossocial/grupos-focais/<id>/fatores/  — fatores
  DELETE   /api/sst/psicossocial/fatores/<id>/             — remove fator
  GET  /sst/psicossocial/grupos-focais/                    — página
"""
import json
import logging

from django.http import JsonResponse

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


def _grupo_dict(g, completo=False):
    d = {
        "id": g.id,
        "titulo": g.titulo,
        "data": str(g.data) if g.data else None,
        "facilitador": g.facilitador,
        "setor_alvo": g.setor_alvo,
        "num_participantes": g.num_participantes,
        "status": g.status,
        "total_fatores": g.fatores.count(),
    }
    if completo:
        d["roteiro"] = g.roteiro
        d["achados"] = g.achados
        d["plano_acao"] = g.plano_acao
        d["fatores"] = [_fator_dict(f) for f in g.fatores.all()]
    return d


def _fator_dict(f):
    return {
        "id": f.id,
        "categoria": f.categoria,
        "categoria_label": f.get_categoria_display(),
        "descricao": f.descricao,
        "gravidade": f.gravidade,
        "medida_recomendada": f.medida_recomendada,
    }


@api_requer_feature("sst.psicossocial")
def api_grupos_focais(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import GrupoFocalPsicossocial

    if request.method == "GET":
        try:
            qs = GrupoFocalPsicossocial.objects.filter(empresa=empresa)
            return JsonResponse({"total": qs.count(), "grupos": [_grupo_dict(g) for g in qs[:50]]})
        except Exception:
            logger.exception("Erro ao listar grupos focais")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("titulo"):
                return JsonResponse({"erro": "titulo é obrigatório"}, status=400)
            g = GrupoFocalPsicossocial.objects.create(
                empresa=empresa,
                titulo=data["titulo"],
                data=data.get("data") or None,
                facilitador=data.get("facilitador", ""),
                setor_alvo=data.get("setor_alvo", ""),
                num_participantes=data.get("num_participantes", 0),
                roteiro=data.get("roteiro", ""),
                achados=data.get("achados", ""),
                plano_acao=data.get("plano_acao", ""),
                status=data.get("status", "planejado"),
            )
            if data.get("avaliacao_id"):
                from .models import AvaliacaoPsicossocial
                g.avaliacao = AvaliacaoPsicossocial.objects.filter(id=data["avaliacao_id"], empresa=empresa).first()
                g.save()
            return JsonResponse({"ok": True, "data": _grupo_dict(g, completo=True)}, status=201)
        except Exception:
            logger.exception("Erro ao criar grupo focal")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.psicossocial")
def api_grupo_focal_detalhe(request, grupo_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import GrupoFocalPsicossocial
    try:
        g = GrupoFocalPsicossocial.objects.get(id=grupo_id, empresa=empresa)
    except GrupoFocalPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Grupo focal não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_grupo_dict(g, completo=True))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("titulo", "facilitador", "setor_alvo", "num_participantes",
                  "roteiro", "achados", "plano_acao", "status"):
            if f in data:
                setattr(g, f, data[f])
        if "data" in data:
            g.data = data["data"] or None
        g.save()
        return JsonResponse({"ok": True, "data": _grupo_dict(g, completo=True)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        g.delete()
        return JsonResponse({"ok": True, "msg": "Grupo focal removido"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.psicossocial")
def api_grupo_focal_fatores(request, grupo_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import GrupoFocalPsicossocial, FatorPsicossocialGrupoFocal
    try:
        g = GrupoFocalPsicossocial.objects.get(id=grupo_id, empresa=empresa)
    except GrupoFocalPsicossocial.DoesNotExist:
        return JsonResponse({"erro": "Grupo focal não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"fatores": [_fator_dict(f) for f in g.fatores.all()]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("categoria") or not data.get("descricao"):
                return JsonResponse({"erro": "categoria e descricao são obrigatórios"}, status=400)
            f = FatorPsicossocialGrupoFocal.objects.create(
                grupo=g,
                categoria=data["categoria"],
                descricao=data["descricao"],
                gravidade=data.get("gravidade", "media"),
                medida_recomendada=data.get("medida_recomendada", ""),
            )
            return JsonResponse({"ok": True, "data": _fator_dict(f)}, status=201)
        except Exception:
            logger.exception("Erro ao adicionar fator")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.psicossocial")
def api_grupo_focal_fator_detalhe(request, fator_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import FatorPsicossocialGrupoFocal
    try:
        f = FatorPsicossocialGrupoFocal.objects.get(id=fator_id, grupo__empresa=empresa)
    except FatorPsicossocialGrupoFocal.DoesNotExist:
        return JsonResponse({"erro": "Fator não encontrado"}, status=404)

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        f.delete()
        return JsonResponse({"ok": True, "msg": "Fator removido"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@requer_feature_pacote("sst.psicossocial", "Grupo Focal NR-01")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_grupo_focal_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_grupo_focal.html", {"empresa_nome": empresa.nome})
