"""
Inspeções de Segurança / Checklists — SoloCRT SST.

Inspeções com checklist de itens conforme/não-conforme, índice de conformidade e
plano de ação para as não-conformidades. Aditivo.

Endpoints:
  GET  /api/sst/inspecoes/kpis/                  — KPIs
  GET/POST /api/sst/inspecoes/                   — lista / cria
  GET/PATCH/DELETE /api/sst/inspecoes/<id>/      — detalhe (com itens)
  GET/POST /api/sst/inspecoes/<id>/itens/        — itens do checklist
  PATCH/DELETE /api/sst/inspecoes/itens/<id>/    — atualiza / remove item
  GET  /sst/inspecoes/                           — página
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


def _item_dict(i):
    return {
        "id": i.id, "descricao": i.descricao, "conforme": i.conforme,
        "criticidade": i.criticidade, "observacao": i.observacao,
        "acao_corretiva": i.acao_corretiva, "responsavel_acao": i.responsavel_acao,
        "prazo": str(i.prazo) if i.prazo else None, "status_acao": i.status_acao,
    }


def _insp_dict(ins, completo=False):
    d = {
        "id": ins.id, "titulo": ins.titulo, "area": ins.area, "local": ins.local,
        "data_inspecao": str(ins.data_inspecao) if ins.data_inspecao else None,
        "responsavel": ins.responsavel, "status": ins.status,
        "indice_conformidade": ins.indice_conformidade,
        "itens_total": ins.itens.count(),
        "nao_conformidades": ins.itens.filter(conforme="nao_conforme").count(),
    }
    if completo:
        d["observacoes"] = ins.observacoes
        d["itens"] = [_item_dict(i) for i in ins.itens.all()]
    return d


@api_requer_feature("sst.inspecoes")
def api_inspecoes_kpis(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InspecaoSeguranca, ItemInspecao
    qs = InspecaoSeguranca.objects.filter(empresa=empresa)
    itens = ItemInspecao.objects.filter(inspecao__empresa=empresa)
    ncs = itens.filter(conforme="nao_conforme")
    return JsonResponse({
        "total": qs.count(),
        "planejadas": qs.filter(status="planejada").count(),
        "nao_conformidades": ncs.count(),
        "acoes_pendentes": ncs.exclude(status_acao="concluida").count(),
    })


@api_requer_feature("sst.inspecoes")
def api_inspecoes(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InspecaoSeguranca

    if request.method == "GET":
        qs = InspecaoSeguranca.objects.filter(empresa=empresa)
        if request.GET.get("status"):
            qs = qs.filter(status=request.GET["status"])
        return JsonResponse({"total": qs.count(), "inspecoes": [_insp_dict(i) for i in qs[:100]]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("titulo"):
                return JsonResponse({"erro": "titulo é obrigatório"}, status=400)
            ins = InspecaoSeguranca.objects.create(
                empresa=empresa, titulo=data["titulo"], area=data.get("area", ""),
                local=data.get("local", ""), data_inspecao=data.get("data_inspecao") or None,
                responsavel=data.get("responsavel", ""), status=data.get("status", "planejada"),
                observacoes=data.get("observacoes", ""),
            )
            return JsonResponse({"ok": True, "data": _insp_dict(ins, completo=True)}, status=201)
        except Exception:
            logger.exception("Erro ao criar inspeção")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.inspecoes")
def api_inspecao_detalhe(request, insp_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InspecaoSeguranca
    try:
        ins = InspecaoSeguranca.objects.get(id=insp_id, empresa=empresa)
    except InspecaoSeguranca.DoesNotExist:
        return JsonResponse({"erro": "Inspeção não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_insp_dict(ins, completo=True))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("titulo", "area", "local", "responsavel", "status", "observacoes"):
            if f in data:
                setattr(ins, f, data[f])
        if "data_inspecao" in data:
            ins.data_inspecao = data["data_inspecao"] or None
        ins.save()
        return JsonResponse({"ok": True, "data": _insp_dict(ins, completo=True)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        ins.delete()
        return JsonResponse({"ok": True, "msg": "Inspeção removida"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.inspecoes")
def api_inspecao_itens(request, insp_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InspecaoSeguranca, ItemInspecao
    try:
        ins = InspecaoSeguranca.objects.get(id=insp_id, empresa=empresa)
    except InspecaoSeguranca.DoesNotExist:
        return JsonResponse({"erro": "Inspeção não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"itens": [_item_dict(i) for i in ins.itens.all()]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("descricao"):
                return JsonResponse({"erro": "descricao é obrigatória"}, status=400)
            i = ItemInspecao.objects.create(
                inspecao=ins, descricao=data["descricao"], conforme=data.get("conforme", "conforme"),
                criticidade=data.get("criticidade", "media"), observacao=data.get("observacao", ""),
                acao_corretiva=data.get("acao_corretiva", ""), responsavel_acao=data.get("responsavel_acao", ""),
                prazo=data.get("prazo") or None, status_acao=data.get("status_acao", "pendente"),
            )
            return JsonResponse({"ok": True, "data": _item_dict(i), "indice_conformidade": ins.indice_conformidade}, status=201)
        except Exception:
            logger.exception("Erro ao criar item de inspeção")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.inspecoes")
def api_inspecao_item_detalhe(request, item_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import ItemInspecao
    try:
        i = ItemInspecao.objects.get(id=item_id, inspecao__empresa=empresa)
    except ItemInspecao.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("descricao", "conforme", "criticidade", "observacao",
                  "acao_corretiva", "responsavel_acao", "status_acao"):
            if f in data:
                setattr(i, f, data[f])
        if "prazo" in data:
            i.prazo = data["prazo"] or None
        i.save()
        return JsonResponse({"ok": True, "data": _item_dict(i), "indice_conformidade": i.inspecao.indice_conformidade})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        i.delete()
        return JsonResponse({"ok": True, "msg": "Item removido"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@requer_feature_pacote("sst.inspecoes", "Inspeções de Segurança")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_inspecoes_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_inspecoes.html", {"empresa_nome": empresa.nome})
