"""
EPI Offline — SoloCRT SST.

Entrega de EPI em campo sem internet: o dispositivo baixa o pacote (catálogo +
funcionários), registra entregas localmente e sincroniza depois. Sincronização
idempotente pelo uuid gerado no cliente — reenvio não duplica. Aditivo: cria
registros EntregaEPI já existentes, sem alterar o módulo de EPI.

Endpoints:
  GET  /api/sst/epi/offline/pacote/    — catálogo + funcionários para uso offline
  POST /api/sst/epi/offline/sync/      — sincroniza fila de entregas offline
  GET  /sst/epi/offline/               — página (PWA-like, fila local)
"""
import json
import logging
from datetime import date

from django.db import transaction
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


@api_requer_feature("sst.epi_offline")
def api_epi_offline_pacote(request):
    """Pacote para trabalho offline: EPIs ativos + funcionários ativos."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import EPIItem, FuncionarioSST
    try:
        epis = EPIItem.objects.filter(empresa=empresa, ativo=True).values("id", "nome", "tipo", "ca_numero")
        funcs = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).values("id", "nome", "cargo", "matricula")
        return JsonResponse({
            "gerado_em": date.today().isoformat(),
            "epis": list(epis),
            "funcionarios": list(funcs),
        })
    except Exception:
        logger.exception("Erro ao gerar pacote offline EPI")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


@api_requer_feature("sst.epi_offline")
def api_epi_offline_sync(request):
    """Sincroniza uma fila de entregas registradas offline. Idempotente por uuid."""
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Sem permissão para sincronizar entregas"}, status=403)

    from .models import SincronizacaoEPIOffline, EntregaEPI, EPIItem, FuncionarioSST

    data = _json(request)
    fila = data.get("entregas") or []
    if not isinstance(fila, list):
        return JsonResponse({"erro": "entregas deve ser uma lista"}, status=400)

    criados, duplicados, erros = 0, 0, []
    for item in fila[:500]:
        uuid = (item.get("uuid") or "").strip()
        if not uuid:
            erros.append({"item": item, "erro": "uuid ausente"})
            continue
        # idempotência: já sincronizado?
        if SincronizacaoEPIOffline.objects.filter(empresa=empresa, uuid_cliente=uuid).exists():
            duplicados += 1
            continue
        try:
            with transaction.atomic():
                func = FuncionarioSST.objects.filter(id=item.get("funcionario_id"), empresa=empresa).first()
                epi = EPIItem.objects.filter(id=item.get("epi_id"), empresa=empresa).first()
                if not func or not epi:
                    SincronizacaoEPIOffline.objects.create(
                        empresa=empresa, uuid_cliente=uuid, payload=item,
                        processado=False, erro="funcionário ou EPI inválido",
                    )
                    erros.append({"uuid": uuid, "erro": "funcionário ou EPI inválido"})
                    continue
                entrega = EntregaEPI.objects.create(
                    empresa=empresa, funcionario=func, epi=epi,
                    data_entrega=item.get("data_entrega") or date.today().isoformat(),
                    quantidade=item.get("quantidade", 1),
                    observacoes=item.get("observacoes", ""),
                    biometria_confirmada=bool(item.get("biometria_confirmada")),
                    foto_entrega_base64=item.get("foto_entrega_base64", ""),
                )
                SincronizacaoEPIOffline.objects.create(
                    empresa=empresa, uuid_cliente=uuid, payload=item,
                    entrega=entrega, processado=True,
                )
                criados += 1
        except Exception:
            logger.exception("Erro ao sincronizar entrega offline uuid=%s", uuid)
            erros.append({"uuid": uuid, "erro": "falha ao processar"})

    return JsonResponse({
        "ok": True, "criados": criados, "duplicados": duplicados,
        "erros": len(erros), "detalhe_erros": erros[:20],
    })


@requer_feature_pacote("sst.epi_offline", "EPI Offline")
@requer_permissao_modulo("sst.operacional")
def sst_epi_offline_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_epi_offline.html", {"empresa_nome": empresa.nome})
