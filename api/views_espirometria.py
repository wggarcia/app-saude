"""
Espirometria ocupacional (NR-07) — SoloCRT SST.

Interpretação automática (obstrutivo/restritivo/misto + grau) e comparação
sequencial do VEF1. Motor puro em espirometria_interpretacao.py. Aditivo.

Endpoints:
  GET  /api/sst/espirometria/kpis/                        — KPIs
  GET/POST /api/sst/espirometria/                         — lista / cria
  GET/PATCH/DELETE /api/sst/espirometria/<id>/            — detalhe
  GET  /api/sst/espirometria/funcionario/<fid>/historico/ — evolução
  GET  /sst/espirometria/                                 — página
"""
import json
import logging

from django.http import JsonResponse

from .access_control import api_requer_feature, requer_feature_pacote, requer_permissao_modulo, principal_pode_operacao_setorial
from .espirometria_interpretacao import interpretar, comparar_sequencial

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


def _dados(e):
    return {"cvf": e.cvf, "vef1": e.vef1, "vef1_cvf": e.vef1_cvf,
            "cvf_prev": e.cvf_prev, "vef1_prev": e.vef1_prev}


def _dict(e, completo=False):
    d = {
        "id": e.id,
        "funcionario_id": e.funcionario_id,
        "funcionario_nome": e.funcionario.nome,
        "funcionario_cargo": e.funcionario.cargo,
        "tipo": e.tipo,
        "data_exame": str(e.data_exame),
        "padrao": e.padrao,
        "grau": e.grau,
        "classificacao_sequencial": e.classificacao_sequencial,
        "declinio_indicado": e.declinio_indicado,
        "resultado_resumo": e.resultado_resumo,
    }
    if completo:
        d.update({"cvf": e.cvf, "vef1": e.vef1, "vef1_cvf": e.vef1_cvf,
                  "cvf_prev": e.cvf_prev, "vef1_prev": e.vef1_prev,
                  "responsavel": e.responsavel, "conselho": e.conselho,
                  "interpretacao": e.interpretacao or {}, "observacoes": e.observacoes or ""})
    return d


def _aplicar(esp, empresa):
    from .models import Espirometria
    interp = interpretar(_dados(esp))
    anterior = (Espirometria.objects
                .filter(empresa=empresa, funcionario=esp.funcionario, data_exame__lt=esp.data_exame)
                .exclude(id=esp.id or 0).order_by("-data_exame").first())
    seq = comparar_sequencial(_dados(esp), _dados(anterior) if anterior else None)
    esp.padrao = interp["padrao"]
    esp.grau = interp["grau"]
    esp.classificacao_sequencial = seq["classificacao_sequencial"]
    esp.declinio_indicado = seq["declinio_indicado"]
    esp.interpretacao = {"exame": interp, "sequencial": seq}
    resumo = interp["resumo"]
    if seq["classificacao_sequencial"] not in ("referencia", "estavel"):
        resumo += f" {seq['detalhe']}"
    esp.resultado_resumo = resumo
    return esp


@api_requer_feature("sst.espirometria")
def api_espirometria_kpis(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Espirometria
    qs = Espirometria.objects.filter(empresa=empresa)
    return JsonResponse({
        "total": qs.count(),
        "alteradas": qs.exclude(padrao__in=["normal", "indeterminado"]).count(),
        "obstrutivo": qs.filter(padrao="obstrutivo").count(),
        "restritivo": qs.filter(padrao="restritivo").count(),
        "declinios": qs.filter(classificacao_sequencial="declinio").count(),
    })


@api_requer_feature("sst.espirometria")
def api_espirometrias(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Espirometria, FuncionarioSST

    if request.method == "GET":
        qs = Espirometria.objects.filter(empresa=empresa).select_related("funcionario")
        if request.GET.get("funcionario_id"):
            qs = qs.filter(funcionario_id=request.GET["funcionario_id"])
        if request.GET.get("padrao"):
            qs = qs.filter(padrao=request.GET["padrao"])
        return JsonResponse({"total": qs.count(), "espirometrias": [_dict(e) for e in qs[:100]]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("funcionario_id") or not data.get("data_exame"):
                return JsonResponse({"erro": "funcionario_id e data_exame são obrigatórios"}, status=400)
            try:
                func = FuncionarioSST.objects.get(id=data["funcionario_id"], empresa=empresa)
            except FuncionarioSST.DoesNotExist:
                return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
            e = Espirometria(
                empresa=empresa, funcionario=func,
                tipo=data.get("tipo", "sequencial"), data_exame=data["data_exame"],
                cvf=data.get("cvf"), vef1=data.get("vef1"), vef1_cvf=data.get("vef1_cvf"),
                cvf_prev=data.get("cvf_prev"), vef1_prev=data.get("vef1_prev"),
                responsavel=data.get("responsavel", ""), conselho=data.get("conselho", ""),
                observacoes=data.get("observacoes", ""),
            )
            _aplicar(e, empresa)
            e.save()
            return JsonResponse({"ok": True, "data": _dict(e, completo=True)}, status=201)
        except Exception:
            logger.exception("Erro ao criar espirometria")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.espirometria")
def api_espirometria_detalhe(request, esp_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Espirometria
    try:
        e = Espirometria.objects.select_related("funcionario").get(id=esp_id, empresa=empresa)
    except Espirometria.DoesNotExist:
        return JsonResponse({"erro": "Espirometria não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_dict(e, completo=True))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("tipo", "data_exame", "cvf", "vef1", "vef1_cvf", "cvf_prev",
                  "vef1_prev", "responsavel", "conselho", "observacoes"):
            if f in data:
                setattr(e, f, data[f])
        _aplicar(e, empresa)
        e.save()
        return JsonResponse({"ok": True, "data": _dict(e, completo=True)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        e.delete()
        return JsonResponse({"ok": True, "msg": "Espirometria removida"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.espirometria")
def api_espirometria_historico(request, funcionario_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import Espirometria, FuncionarioSST
    try:
        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)
    except FuncionarioSST.DoesNotExist:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
    qs = Espirometria.objects.filter(empresa=empresa, funcionario=func).order_by("data_exame")
    return JsonResponse({"funcionario_nome": func.nome, "total": qs.count(),
                         "historico": [_dict(e, completo=True) for e in qs]})


@requer_feature_pacote("sst.espirometria", "Espirometria")
@requer_permissao_modulo("sst.clinico")
def sst_espirometria_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_espirometria.html", {"empresa_nome": empresa.nome})
