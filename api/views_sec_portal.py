"""
Portal do Cliente (SEC) — SoloCRT SST.

Consultorias de SST compartilham documentos (DocumentoSST, laudos) com suas
empresas-clientes, que acessam um portal público por token — sem virar tenant.
Isolado por empresa (a consultoria). Aditivo.

Lado gestão (consultoria, autenticado):
  GET/POST /api/sst/sec/clientes/                 — lista / cria cliente
  GET/PATCH/DELETE /api/sst/sec/clientes/<id>/    — detalhe (inclui link do portal)
  GET/POST /api/sst/sec/clientes/<id>/documentos/ — lista / compartilha documento
  DELETE   /api/sst/sec/compartilhamentos/<id>/   — remove compartilhamento
  GET  /sst/sec/                                  — página de gestão

Lado cliente (público via token):
  GET  /portal-sec/<token>/                       — página do portal
  GET  /api/portal-sec/<token>/documentos/        — documentos do cliente
"""
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


def _client_ip(request):
    xf = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR", "")
    return (xf or "")[:64]


def _cliente_dict(c, request=None):
    base = ""
    if request is not None:
        base = f"{request.scheme}://{request.get_host()}"
    return {
        "id": c.id,
        "nome_cliente": c.nome_cliente,
        "cnpj_cliente": c.cnpj_cliente,
        "email_contato": c.email_contato,
        "pode_baixar": c.pode_baixar,
        "ativo": c.ativo,
        "ultimo_acesso": c.ultimo_acesso.isoformat() if c.ultimo_acesso else None,
        "total_documentos": c.documentos.count(),
        "portal_url": f"{base}/portal-sec/{c.token_acesso}/" if base else f"/portal-sec/{c.token_acesso}/",
    }


def _doc_compartilhado_dict(s):
    return {
        "id": s.id,
        "titulo": s.titulo,
        "documento_id": s.documento_id,
        "laudo_id": s.laudo_id,
        "compartilhado_em": s.compartilhado_em.isoformat(),
        "visualizado_em": s.visualizado_em.isoformat() if s.visualizado_em else None,
    }


# ── Lado gestão (consultoria) ────────────────────────────────────────────────

@api_requer_feature("sst.portal_cliente")
def api_sec_clientes(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import ClienteConsultoriaSST

    if request.method == "GET":
        try:
            qs = ClienteConsultoriaSST.objects.filter(empresa=empresa)
            return JsonResponse({"total": qs.count(), "clientes": [_cliente_dict(c, request) for c in qs[:100]]})
        except Exception:
            logger.exception("Erro ao listar clientes SEC")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("nome_cliente"):
                return JsonResponse({"erro": "nome_cliente é obrigatório"}, status=400)
            c = ClienteConsultoriaSST.objects.create(
                empresa=empresa,
                nome_cliente=data["nome_cliente"],
                cnpj_cliente=data.get("cnpj_cliente", ""),
                email_contato=data.get("email_contato", ""),
                pode_baixar=data.get("pode_baixar", True),
                token_acesso=secrets.token_urlsafe(24),
            )
            return JsonResponse({"ok": True, "data": _cliente_dict(c, request)}, status=201)
        except Exception:
            logger.exception("Erro ao criar cliente SEC")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.portal_cliente")
def api_sec_cliente_detalhe(request, cliente_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import ClienteConsultoriaSST
    try:
        c = ClienteConsultoriaSST.objects.get(id=cliente_id, empresa=empresa)
    except ClienteConsultoriaSST.DoesNotExist:
        return JsonResponse({"erro": "Cliente não encontrado"}, status=404)

    if request.method == "GET":
        d = _cliente_dict(c, request)
        d["documentos"] = [_doc_compartilhado_dict(s) for s in c.documentos.all()]
        return JsonResponse(d)

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("nome_cliente", "cnpj_cliente", "email_contato", "pode_baixar", "ativo"):
            if f in data:
                setattr(c, f, data[f])
        if data.get("regenerar_token"):
            c.token_acesso = secrets.token_urlsafe(24)
        c.save()
        return JsonResponse({"ok": True, "data": _cliente_dict(c, request)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        c.delete()
        return JsonResponse({"ok": True, "msg": "Cliente removido"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.portal_cliente")
def api_sec_cliente_documentos(request, cliente_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import ClienteConsultoriaSST, CompartilhamentoSEC, DocumentoSST, LaudoTecnicoSST
    try:
        c = ClienteConsultoriaSST.objects.get(id=cliente_id, empresa=empresa)
    except ClienteConsultoriaSST.DoesNotExist:
        return JsonResponse({"erro": "Cliente não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"documentos": [_doc_compartilhado_dict(s) for s in c.documentos.all()]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            documento = laudo = None
            titulo = data.get("titulo", "")
            # valida que o documento/laudo pertence à MESMA empresa (isolamento)
            if data.get("documento_id"):
                documento = DocumentoSST.objects.filter(id=data["documento_id"], empresa=empresa).first()
                if not documento:
                    return JsonResponse({"erro": "Documento não encontrado nesta empresa"}, status=404)
                titulo = titulo or documento.titulo
            elif data.get("laudo_id"):
                laudo = LaudoTecnicoSST.objects.filter(id=data["laudo_id"], empresa=empresa).first()
                if not laudo:
                    return JsonResponse({"erro": "Laudo não encontrado nesta empresa"}, status=404)
                titulo = titulo or getattr(laudo, "titulo", f"Laudo #{laudo.id}")
            else:
                return JsonResponse({"erro": "Informe documento_id ou laudo_id"}, status=400)

            s = CompartilhamentoSEC.objects.create(
                cliente=c, documento=documento, laudo=laudo, titulo=titulo or "Documento",
            )
            return JsonResponse({"ok": True, "data": _doc_compartilhado_dict(s)}, status=201)
        except Exception:
            logger.exception("Erro ao compartilhar documento SEC")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.portal_cliente")
def api_sec_compartilhamento_detalhe(request, comp_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import CompartilhamentoSEC
    try:
        s = CompartilhamentoSEC.objects.get(id=comp_id, cliente__empresa=empresa)
    except CompartilhamentoSEC.DoesNotExist:
        return JsonResponse({"erro": "Compartilhamento não encontrado"}, status=404)
    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        s.delete()
        return JsonResponse({"ok": True, "msg": "Compartilhamento removido"})
    return JsonResponse({"erro": "Método não permitido"}, status=405)


@requer_feature_pacote("sst.portal_cliente", "Portal do Cliente (SEC)")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_sec_gestao_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_sec_gestao.html", {"empresa_nome": empresa.nome})


# ── Lado cliente (público via token) ─────────────────────────────────────────

def _cliente_por_token(token):
    from .models import ClienteConsultoriaSST
    return ClienteConsultoriaSST.objects.filter(token_acesso=token, ativo=True).first()


def portal_sec_page(request, token):
    """Página pública do portal do cliente (sem login)."""
    from django.shortcuts import render
    c = _cliente_por_token(token)
    if not c:
        return render(request, "sec_portal.html", {"invalido": True, "token": ""})
    return render(request, "sec_portal.html", {
        "invalido": False, "token": token,
        "nome_cliente": c.nome_cliente, "consultoria": c.empresa.nome,
    })


def api_portal_sec_documentos(request, token):
    """Lista documentos compartilhados com o cliente autenticado pelo token."""
    c = _cliente_por_token(token)
    if not c:
        return JsonResponse({"erro": "Token inválido ou acesso desativado"}, status=403)
    from .models import AcessoSECLog
    try:
        c.ultimo_acesso = timezone.now()
        c.save(update_fields=["ultimo_acesso"])
        AcessoSECLog.objects.create(cliente=c, ip=_client_ip(request), acao="listar_documentos")
        docs = []
        for s in c.documentos.select_related("documento", "laudo"):
            item = {
                "id": s.id,
                "titulo": s.titulo,
                "compartilhado_em": s.compartilhado_em.strftime("%d/%m/%Y"),
                "tipo": "documento" if s.documento_id else ("laudo" if s.laudo_id else "—"),
            }
            if s.documento_id:
                item["status"] = s.documento.status
                item["data_validade"] = str(s.documento.data_validade) if s.documento.data_validade else None
            docs.append(item)
        return JsonResponse({
            "cliente": c.nome_cliente, "consultoria": c.empresa.nome,
            "pode_baixar": c.pode_baixar, "documentos": docs,
        })
    except Exception:
        logger.exception("Erro no portal SEC público")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)
