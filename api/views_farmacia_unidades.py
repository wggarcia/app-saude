"""
Farmácia — Unidades físicas internas
  • EmpresaUnidade reaproveitado (mesmo modelo usado pelo SST) para representar
    lojas físicas distintas dentro de UMA mesma conta de farmácia.
  • Existe pra fechar a lacuna de "max_unidades" do pacote: sem isso, uma conta
    Farmácia Local (max_unidades=1) podia operar várias lojas físicas
    compartilhando o mesmo estoque, sem nenhum limite real aplicado.
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import EmpresaUnidade
from .views_dashboard import _empresa_autenticada
from .access_control import (
    api_requer_operacao_ou_gerencia,
    api_requer_setor,
    dentro_do_limite,
    get_setor,
    principal_pode_operacao_setorial,
)


def _e(req):
    empresa = _empresa_autenticada(req)
    if empresa and get_setor(empresa) not in ('farmacia',):
        return None
    if empresa and not principal_pode_operacao_setorial(req):
        return None
    return empresa


@require_http_methods(["GET", "POST"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
def api_farmacia_unidades(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = EmpresaUnidade.objects.filter(empresa=e, ativo=True)
        return JsonResponse({"unidades": [
            {"id": u.id, "nome": u.nome, "codigo": u.codigo}
            for u in qs
        ]})

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = (data.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"erro": "nome é obrigatório"}, status=400)

    contagem_atual = EmpresaUnidade.objects.filter(empresa=e, ativo=True).count()
    if not dentro_do_limite(e, "max_unidades", contagem_atual):
        return JsonResponse({
            "erro": "Limite de unidades do seu plano atingido. Faça upgrade para registrar mais unidades.",
            "upgrade_necessario": True,
        }, status=403)

    if EmpresaUnidade.objects.filter(empresa=e, nome=nome).exists():
        return JsonResponse({"erro": "Já existe uma unidade com esse nome"}, status=409)

    codigo = (data.get("codigo") or "").strip()
    unidade = EmpresaUnidade.objects.create(empresa=e, nome=nome, codigo=codigo)
    return JsonResponse({"id": unidade.id, "nome": unidade.nome, "codigo": unidade.codigo}, status=201)


@require_http_methods(["PUT", "DELETE"])
@api_requer_setor("farmacia")
@api_requer_operacao_ou_gerencia
def api_farmacia_unidade_detalhe(request, unidade_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        unidade = EmpresaUnidade.objects.get(pk=unidade_id, empresa=e)
    except EmpresaUnidade.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "DELETE":
        unidade.ativo = False
        unidade.save()
        return JsonResponse({"ok": True})

    data = json.loads(request.body or "{}")
    for campo in ("nome", "codigo"):
        if campo in data:
            setattr(unidade, campo, data[campo])
    unidade.save()
    return JsonResponse({"ok": True})
