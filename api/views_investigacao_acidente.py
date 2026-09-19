"""
Investigação de Acidentes (Ishikawa / 5 Porquês) — SoloCRT SST.

Análise de causa-raiz de acidentes/incidentes com diagrama de Ishikawa (6M) e/ou
5 Porquês, e plano de ação corretiva/preventiva. Liga-se às CATs. Aditivo.

Endpoints:
  GET  /api/sst/investigacoes/kpis/                 — KPIs
  GET/POST /api/sst/investigacoes/                  — lista / cria
  GET/PATCH/DELETE /api/sst/investigacoes/<id>/     — detalhe
  GET/POST /api/sst/investigacoes/<id>/acoes/       — ações corretivas
  PATCH/DELETE /api/sst/investigacoes/acoes/<id>/   — atualiza / remove ação
  GET  /sst/investigacoes/                          — página
"""
import json
import logging

from django.http import JsonResponse

from .access_control import api_requer_feature, requer_feature_pacote, requer_permissao_modulo, principal_pode_operacao_setorial

logger = logging.getLogger(__name__)

ISHIKAWA_6M = ["metodo", "maquina", "mao_de_obra", "material", "meio_ambiente", "medicao"]


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


def _acao_dict(a):
    return {
        "id": a.id, "descricao": a.descricao, "tipo": a.tipo,
        "responsavel": a.responsavel, "prazo": str(a.prazo) if a.prazo else None,
        "status": a.status, "concluida_em": str(a.concluida_em) if a.concluida_em else None,
    }


def _inv_dict(i, completo=False):
    total = i.acoes.count()
    concluidas = i.acoes.filter(status="concluida").count()
    d = {
        "id": i.id, "titulo": i.titulo, "cat_id": i.cat_id,
        "funcionario_nome": i.funcionario.nome if i.funcionario else None,
        "data_ocorrencia": str(i.data_ocorrencia) if i.data_ocorrencia else None,
        "local": i.local, "metodo": i.metodo, "status": i.status,
        "causa_raiz": i.causa_raiz,
        "acoes_total": total, "acoes_concluidas": concluidas,
    }
    if completo:
        d.update({
            "descricao": i.descricao, "ishikawa": i.ishikawa or {},
            "cinco_porques": i.cinco_porques or [], "responsavel": i.responsavel,
            "acoes": [_acao_dict(a) for a in i.acoes.all()],
        })
    return d


@api_requer_feature("sst.investigacao_acidente")
def api_investigacoes_kpis(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InvestigacaoAcidente, AcaoCorretivaAcidente
    qs = InvestigacaoAcidente.objects.filter(empresa=empresa)
    acoes = AcaoCorretivaAcidente.objects.filter(investigacao__empresa=empresa)
    return JsonResponse({
        "total": qs.count(),
        "abertas": qs.exclude(status="concluida").count(),
        "acoes_pendentes": acoes.exclude(status="concluida").count(),
        "acoes_concluidas": acoes.filter(status="concluida").count(),
    })


@api_requer_feature("sst.investigacao_acidente")
def api_investigacoes(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InvestigacaoAcidente, CATOcupacional, FuncionarioSST

    if request.method == "GET":
        qs = InvestigacaoAcidente.objects.filter(empresa=empresa).select_related("funcionario")
        if request.GET.get("status"):
            qs = qs.filter(status=request.GET["status"])
        return JsonResponse({"total": qs.count(), "investigacoes": [_inv_dict(i) for i in qs[:100]]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("titulo"):
                return JsonResponse({"erro": "titulo é obrigatório"}, status=400)
            i = InvestigacaoAcidente(
                empresa=empresa, titulo=data["titulo"],
                data_ocorrencia=data.get("data_ocorrencia") or None, local=data.get("local", ""),
                descricao=data.get("descricao", ""), metodo=data.get("metodo", "ishikawa"),
                ishikawa=data.get("ishikawa") or {}, cinco_porques=data.get("cinco_porques") or [],
                causa_raiz=data.get("causa_raiz", ""), responsavel=data.get("responsavel", ""),
                status=data.get("status", "aberta"),
            )
            if data.get("cat_id"):
                i.cat = CATOcupacional.objects.filter(id=data["cat_id"], empresa=empresa).first()
            if data.get("funcionario_id"):
                i.funcionario = FuncionarioSST.objects.filter(id=data["funcionario_id"], empresa=empresa).first()
            i.save()
            return JsonResponse({"ok": True, "data": _inv_dict(i, completo=True)}, status=201)
        except Exception:
            logger.exception("Erro ao criar investigação")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.investigacao_acidente")
def api_investigacao_detalhe(request, inv_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InvestigacaoAcidente
    try:
        i = InvestigacaoAcidente.objects.select_related("funcionario").get(id=inv_id, empresa=empresa)
    except InvestigacaoAcidente.DoesNotExist:
        return JsonResponse({"erro": "Investigação não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_inv_dict(i, completo=True))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("titulo", "local", "descricao", "metodo", "causa_raiz", "responsavel", "status"):
            if f in data:
                setattr(i, f, data[f])
        if "data_ocorrencia" in data:
            i.data_ocorrencia = data["data_ocorrencia"] or None
        if "ishikawa" in data and isinstance(data["ishikawa"], dict):
            i.ishikawa = data["ishikawa"]
        if "cinco_porques" in data and isinstance(data["cinco_porques"], list):
            i.cinco_porques = data["cinco_porques"]
        i.save()
        return JsonResponse({"ok": True, "data": _inv_dict(i, completo=True)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        i.delete()
        return JsonResponse({"ok": True, "msg": "Investigação removida"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.investigacao_acidente")
def api_investigacao_acoes(request, inv_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import InvestigacaoAcidente, AcaoCorretivaAcidente
    try:
        i = InvestigacaoAcidente.objects.get(id=inv_id, empresa=empresa)
    except InvestigacaoAcidente.DoesNotExist:
        return JsonResponse({"erro": "Investigação não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"acoes": [_acao_dict(a) for a in i.acoes.all()]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("descricao"):
                return JsonResponse({"erro": "descricao é obrigatória"}, status=400)
            a = AcaoCorretivaAcidente.objects.create(
                investigacao=i, descricao=data["descricao"], tipo=data.get("tipo", "corretiva"),
                responsavel=data.get("responsavel", ""), prazo=data.get("prazo") or None,
                status=data.get("status", "pendente"),
            )
            return JsonResponse({"ok": True, "data": _acao_dict(a)}, status=201)
        except Exception:
            logger.exception("Erro ao criar ação")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.investigacao_acidente")
def api_investigacao_acao_detalhe(request, acao_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import AcaoCorretivaAcidente
    try:
        a = AcaoCorretivaAcidente.objects.get(id=acao_id, investigacao__empresa=empresa)
    except AcaoCorretivaAcidente.DoesNotExist:
        return JsonResponse({"erro": "Ação não encontrada"}, status=404)

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("descricao", "tipo", "responsavel", "status"):
            if f in data:
                setattr(a, f, data[f])
        if "prazo" in data:
            a.prazo = data["prazo"] or None
        if "concluida_em" in data:
            a.concluida_em = data["concluida_em"] or None
        if data.get("status") == "concluida" and not a.concluida_em:
            from django.utils import timezone
            a.concluida_em = timezone.now().date()
        a.save()
        return JsonResponse({"ok": True, "data": _acao_dict(a)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        a.delete()
        return JsonResponse({"ok": True, "msg": "Ação removida"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@requer_feature_pacote("sst.investigacao_acidente", "Investigação de Acidentes")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_investigacao_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_investigacao_acidente.html", {"empresa_nome": empresa.nome})
