"""
API de Integração SST (ERP / RH / Folha) — SoloCRT SST.

Permite que sistemas externos (ERP, folha de pagamento, RH) sincronizem
funcionários e leiam dados de SST via token de API. O token é autenticado por
hash (nunca armazenado em claro). Aditivo.

Lado gestão (consultoria/empresa, autenticado por sessão):
  GET/POST /api/sst/integracao/tokens/          — lista / cria token (valor em claro só na criação)
  DELETE   /api/sst/integracao/tokens/<id>/     — revoga token
  GET  /sst/integracao/                         — página de gestão

API externa (auth via header X-API-Token):
  GET  /api/integracao-sst/funcionarios/        — exporta funcionários
  POST /api/integracao-sst/funcionarios/        — upsert de funcionários (por matrícula/CPF)
  GET  /api/integracao-sst/asos/                — exporta ASOs (validade, resultado)
"""
import hashlib
import json
import logging
import secrets

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


def _hash_token(valor):
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _token_dict(t):
    return {
        "id": t.id,
        "nome": t.nome,
        "prefixo": t.prefixo,
        "ativo": t.ativo,
        "ultimo_uso": t.ultimo_uso.isoformat() if t.ultimo_uso else None,
        "criado_em": t.criado_em.strftime("%d/%m/%Y"),
    }


# ── Lado gestão (autenticado por sessão) ─────────────────────────────────────

@api_requer_feature("sst.integracao_api")
def api_integracao_tokens(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import TokenIntegracaoSST

    if request.method == "GET":
        qs = TokenIntegracaoSST.objects.filter(empresa=empresa)
        return JsonResponse({"total": qs.count(), "tokens": [_token_dict(t) for t in qs]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        if not data.get("nome"):
            return JsonResponse({"erro": "nome é obrigatório"}, status=400)
        valor = "sst_" + secrets.token_urlsafe(32)
        t = TokenIntegracaoSST.objects.create(
            empresa=empresa, nome=data["nome"],
            token_hash=_hash_token(valor), prefixo=valor[:12],
        )
        # o valor em claro só é devolvido AGORA — nunca mais é recuperável
        return JsonResponse({"ok": True, "data": _token_dict(t), "token": valor}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.integracao_api")
def api_integracao_token_detalhe(request, token_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import TokenIntegracaoSST
    try:
        t = TokenIntegracaoSST.objects.get(id=token_id, empresa=empresa)
    except TokenIntegracaoSST.DoesNotExist:
        return JsonResponse({"erro": "Token não encontrado"}, status=404)
    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        t.delete()
        return JsonResponse({"ok": True, "msg": "Token revogado"})
    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        if "ativo" in data:
            t.ativo = data["ativo"]
        if "nome" in data:
            t.nome = data["nome"]
        t.save()
        return JsonResponse({"ok": True, "data": _token_dict(t)})
    return JsonResponse({"erro": "Método não permitido"}, status=405)


@requer_feature_pacote("sst.integracao_api", "API de Integração")
@requer_permissao_modulo("sst.administracao")
def sst_integracao_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_integracao.html", {"empresa_nome": empresa.nome})


# ── API externa (auth via header X-API-Token) ────────────────────────────────

def _autenticar_token(request, endpoint):
    """Resolve a empresa a partir do header X-API-Token. Registra log e ultimo_uso."""
    from .models import TokenIntegracaoSST, LogIntegracaoSST
    valor = request.META.get("HTTP_X_API_TOKEN", "") or request.headers.get("X-API-Token", "")
    if not valor:
        return None, None
    t = TokenIntegracaoSST.objects.filter(token_hash=_hash_token(valor), ativo=True).select_related("empresa").first()
    if not t:
        return None, None
    t.ultimo_uso = timezone.now()
    t.save(update_fields=["ultimo_uso"])
    LogIntegracaoSST.objects.create(token=t, endpoint=endpoint, metodo=request.method, status_code=200)
    return t.empresa, t


def api_integracao_funcionarios(request):
    empresa, token = _autenticar_token(request, "funcionarios")
    if not empresa:
        return JsonResponse({"erro": "Token de integração inválido ou ausente"}, status=401)
    from .models import FuncionarioSST

    if request.method == "GET":
        funcs = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).values(
            "id", "nome", "cpf", "matricula", "cargo", "setor"
        )
        return JsonResponse({"total": len(funcs), "funcionarios": list(funcs)})

    if request.method == "POST":
        data = _json(request)
        lista = data.get("funcionarios") or []
        if not isinstance(lista, list):
            return JsonResponse({"erro": "funcionarios deve ser uma lista"}, status=400)
        criados, atualizados, erros = 0, 0, 0
        for f in lista[:1000]:
            nome = (f.get("nome") or "").strip()
            cargo = (f.get("cargo") or "").strip()
            matricula = (f.get("matricula") or "").strip()
            cpf = (f.get("cpf") or "").strip()
            if not nome or not cargo:
                erros += 1
                continue
            existente = None
            if matricula:
                existente = FuncionarioSST.objects.filter(empresa=empresa, matricula=matricula).first()
            if not existente and cpf:
                existente = FuncionarioSST.objects.filter(empresa=empresa, cpf=cpf).first()
            if existente:
                existente.nome = nome
                existente.cargo = cargo
                if f.get("setor"):
                    existente.setor = f["setor"]
                existente.save()
                atualizados += 1
            else:
                FuncionarioSST.objects.create(
                    empresa=empresa, nome=nome, cargo=cargo,
                    matricula=matricula, cpf=cpf, setor=f.get("setor", ""),
                )
                criados += 1
        return JsonResponse({"ok": True, "criados": criados, "atualizados": atualizados, "erros": erros})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


def api_integracao_asos(request):
    empresa, token = _autenticar_token(request, "asos")
    if not empresa:
        return JsonResponse({"erro": "Token de integração inválido ou ausente"}, status=401)
    from .models import ASOOcupacional
    qs = ASOOcupacional.objects.filter(empresa=empresa).select_related("funcionario").order_by("-data_emissao")[:2000]
    asos = [{
        "id": a.id,
        "funcionario": a.funcionario.nome,
        "matricula": a.funcionario.matricula,
        "tipo": a.tipo,
        "data_emissao": str(a.data_emissao),
        "data_validade": str(a.data_validade) if a.data_validade else None,
        "resultado": a.resultado,
    } for a in qs]
    return JsonResponse({"total": len(asos), "asos": asos})
