"""
Documento SST versionado — SoloCRT SST.

Controle de versão de documentos SST (PGR, PCMSO, LTCAT etc.) com histórico
imutável e vínculo de assinatura digital. Aditivo — usa DocumentoSST existente,
sem alterá-lo, mantendo o isolamento de segmento (não usa o GED do Governo).

Endpoints:
  GET/POST /api/sst/documentos/<doc_id>/versoes/     — lista / cria versão
  DELETE   /api/sst/documentos/versoes/<versao_id>/  — remove versão
"""
import base64
import hashlib
import json
import logging

from django.core.files.base import ContentFile
from django.http import JsonResponse

from .access_control import api_requer_feature, principal_pode_operacao_setorial

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


def _versao_dict(v):
    return {
        "id": v.id,
        "versao": v.versao,
        "nome_arquivo_original": v.nome_arquivo_original,
        "hash_sha256": v.hash_sha256,
        "tamanho_bytes": v.tamanho_bytes,
        "autor": v.autor,
        "nota": v.nota,
        "assinado": v.assinado,
        "arquivo_url": v.arquivo.url if v.arquivo else None,
        "criado_em": v.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


@api_requer_feature("sst.documentos_versao")
def api_doc_sst_versoes(request, doc_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import DocumentoSST, VersaoDocumentoSST
    try:
        doc = DocumentoSST.objects.get(id=doc_id, empresa=empresa)
    except DocumentoSST.DoesNotExist:
        return JsonResponse({"erro": "Documento não encontrado"}, status=404)

    if request.method == "GET":
        vs = doc.versoes.all()
        return JsonResponse({"documento": doc.titulo, "total": vs.count(), "versoes": [_versao_dict(v) for v in vs]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            ultima = doc.versoes.first()  # ordering=-versao
            proximo = (ultima.versao + 1) if ultima else 1

            v = VersaoDocumentoSST(
                documento=doc, versao=proximo,
                autor=data.get("autor", ""), nota=data.get("nota", ""),
            )
            b64 = data.get("arquivo_base64")
            if b64:
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                raw = base64.b64decode(b64)
                v.hash_sha256 = hashlib.sha256(raw).hexdigest()
                v.tamanho_bytes = len(raw)
                nome = data.get("nome_arquivo", f"{doc.titulo}_v{proximo}.pdf")
                v.nome_arquivo_original = nome
                v.arquivo.save(nome, ContentFile(raw), save=False)
            v.save()
            return JsonResponse({"ok": True, "data": _versao_dict(v)}, status=201)
        except Exception:
            logger.exception("Erro ao criar versão de documento SST")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.documentos_versao")
def api_doc_sst_versao_detalhe(request, versao_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import VersaoDocumentoSST
    try:
        v = VersaoDocumentoSST.objects.get(id=versao_id, documento__empresa=empresa)
    except VersaoDocumentoSST.DoesNotExist:
        return JsonResponse({"erro": "Versão não encontrada"}, status=404)
    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        v.delete()
        return JsonResponse({"ok": True, "msg": "Versão removida"})
    return JsonResponse({"erro": "Método não permitido"}, status=405)
