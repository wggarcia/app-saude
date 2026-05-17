import hashlib
import json
from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    ASOOcupacional,
    AssinaturaDocumentoSST,
    CATOcupacional,
    ConfiguracaoSST,
    DocumentoSST,
    ExameOcupacional,
    AfastamentoSST,
    FuncionarioSST,
)
from .views_dashboard import _empresa_autenticada


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _document_payload(tipo_documento, objeto_id, empresa):
    if tipo_documento == "aso":
        aso = ASOOcupacional.objects.filter(id=objeto_id, empresa=empresa).select_related("funcionario").first()
        if not aso:
            return None
        return {
            "obj": aso,
            "funcionario": aso.funcionario,
            "titulo": f"ASO {aso.get_tipo_display()} - {aso.funcionario.nome}",
            "payload": {
                "tipo": "aso",
                "id": aso.id,
                "empresa_id": empresa.id,
                "funcionario_id": aso.funcionario_id,
                "funcionario_nome": aso.funcionario.nome,
                "data_emissao": str(aso.data_emissao),
                "data_validade": str(aso.data_validade) if aso.data_validade else None,
                "resultado": aso.resultado,
                "medico": aso.medico_responsavel,
                "crm": aso.crm,
            },
        }
    if tipo_documento == "cat":
        cat = CATOcupacional.objects.filter(id=objeto_id, empresa=empresa).select_related("funcionario").first()
        if not cat:
            return None
        return {
            "obj": cat,
            "funcionario": cat.funcionario,
            "titulo": f"CAT {cat.get_tipo_display()} - {cat.funcionario.nome}",
            "payload": {
                "tipo": "cat",
                "id": cat.id,
                "empresa_id": empresa.id,
                "funcionario_id": cat.funcionario_id,
                "funcionario_nome": cat.funcionario.nome,
                "data_acidente": str(cat.data_acidente),
                "tipo_cat": cat.tipo,
                "gravidade": cat.gravidade,
                "cid": cat.cid,
                "descricao": cat.descricao,
                "numero_cat": cat.numero_cat,
                "status_esocial": cat.status_esocial,
            },
        }
    if tipo_documento == "prontuario":
        funcionario = FuncionarioSST.objects.filter(id=objeto_id, empresa=empresa).first()
        if not funcionario:
            return None
        return {
            "obj": funcionario,
            "funcionario": funcionario,
            "titulo": f"Prontuário SST - {funcionario.nome}",
            "payload": {
                "tipo": "prontuario",
                "id": funcionario.id,
                "empresa_id": empresa.id,
                "funcionario_nome": funcionario.nome,
                "matricula": funcionario.matricula,
                "asos": list(funcionario.asos.values_list("id", "data_emissao", "data_validade", "resultado")),
                "exames": list(funcionario.exames.values_list("id", "tipo_exame", "data_realizacao", "data_validade", "status")),
                "cats": list(funcionario.cats.values_list("id", "data_acidente", "tipo", "status_esocial")),
            },
        }
    if tipo_documento == "documento_sst":
        documento = DocumentoSST.objects.filter(id=objeto_id, empresa=empresa).first()
        if not documento:
            return None
        return {
            "obj": documento,
            "funcionario": None,
            "titulo": documento.titulo,
            "payload": {
                "tipo": "documento_sst",
                "id": documento.id,
                "empresa_id": empresa.id,
                "tipo_documento": documento.tipo,
                "titulo": documento.titulo,
                "status": documento.status,
                "responsavel": documento.responsavel_tecnico,
                "registro": documento.registro_profissional,
                "data_emissao": str(documento.data_emissao) if documento.data_emissao else None,
                "data_validade": str(documento.data_validade) if documento.data_validade else None,
                "observacoes": documento.observacoes,
            },
        }
    return None


def _hash_payload(payload):
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _assinatura_to_dict(assinatura, request=None):
    base_url = request.build_absolute_uri("/")[:-1] if request else ""
    return {
        "id": assinatura.id,
        "token": assinatura.token,
        "tipo_documento": assinatura.tipo_documento,
        "tipo_documento_label": assinatura.get_tipo_documento_display(),
        "objeto_id": assinatura.objeto_id,
        "titulo": assinatura.titulo,
        "status": assinatura.status,
        "hash_documento": assinatura.hash_documento,
        "hash_assinatura": assinatura.hash_assinatura,
        "signatario_nome": assinatura.signatario_nome,
        "signatario_email": assinatura.signatario_email,
        "signatario_cpf": assinatura.signatario_cpf,
        "criado_em": assinatura.criado_em.strftime("%d/%m/%Y %H:%M"),
        "assinado_em": assinatura.assinado_em.strftime("%d/%m/%Y %H:%M") if assinatura.assinado_em else None,
        "expiracao_em": assinatura.expiracao_em.strftime("%d/%m/%Y %H:%M") if assinatura.expiracao_em else None,
        "link_assinatura": f"{base_url}/assinatura/sst/{assinatura.token}/" if base_url else f"/assinatura/sst/{assinatura.token}/",
        "link_validacao": f"{base_url}/validar-assinatura/{assinatura.token}/" if base_url else f"/validar-assinatura/{assinatura.token}/",
    }


@csrf_exempt
def api_sst_assinaturas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    if request.method == "GET":
        qs = AssinaturaDocumentoSST.objects.filter(empresa=empresa)
        tipo = request.GET.get("tipo_documento")
        status = request.GET.get("status")
        objeto_id = request.GET.get("objeto_id")
        if tipo:
            qs = qs.filter(tipo_documento=tipo)
        if status:
            qs = qs.filter(status=status)
        if objeto_id:
            qs = qs.filter(objeto_id=objeto_id)
        return JsonResponse({"assinaturas": [_assinatura_to_dict(item, request) for item in qs[:100]]})

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        tipo_documento = data.get("tipo_documento")
        objeto_id = data.get("objeto_id")
        if tipo_documento not in dict(AssinaturaDocumentoSST.TIPO_CHOICES):
            return JsonResponse({"erro": "tipo_documento inválido"}, status=400)
        if not objeto_id:
            return JsonResponse({"erro": "objeto_id obrigatório"}, status=400)

        doc = _document_payload(tipo_documento, objeto_id, empresa)
        if not doc:
            return JsonResponse({"erro": "documento não encontrado"}, status=404)

        hash_documento = _hash_payload(doc["payload"])
        assinatura = AssinaturaDocumentoSST.objects.create(
            empresa=empresa,
            funcionario=doc["funcionario"],
            tipo_documento=tipo_documento,
            objeto_id=int(objeto_id),
            titulo=data.get("titulo") or doc["titulo"],
            hash_documento=hash_documento,
            signatario_nome=data.get("signatario_nome", ""),
            signatario_email=data.get("signatario_email", ""),
            signatario_cpf=data.get("signatario_cpf", ""),
            solicitado_por=data.get("solicitado_por", empresa.email or empresa.nome),
            ip_solicitacao=_client_ip(request),
            expiracao_em=timezone.now() + timedelta(days=int(data.get("validade_dias") or 15)),
        )
        return JsonResponse({"assinatura": _assinatura_to_dict(assinatura, request)}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_sst_assinatura_detalhe(request, token):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    assinatura = AssinaturaDocumentoSST.objects.filter(token=token, empresa=empresa).first()
    if not assinatura:
        return JsonResponse({"erro": "assinatura não encontrada"}, status=404)
    return JsonResponse({"assinatura": _assinatura_to_dict(assinatura, request)})


def pagina_assinatura_sst(request, token):
    assinatura = AssinaturaDocumentoSST.objects.filter(token=token).select_related("empresa", "funcionario").first()
    return render(request, "assinatura_sst.html", {
        "assinatura": assinatura,
        "modo": "assinar",
        "token": token,
    })


def pagina_validar_assinatura(request, token):
    assinatura = AssinaturaDocumentoSST.objects.filter(token=token).select_related("empresa", "funcionario").first()
    return render(request, "assinatura_sst.html", {
        "assinatura": assinatura,
        "modo": "validar",
        "token": token,
    })


def api_public_validar_assinatura_sst(request, token):
    assinatura = AssinaturaDocumentoSST.objects.filter(token=token).select_related("empresa", "funcionario").first()
    if not assinatura:
        return JsonResponse({"valida": False, "erro": "assinatura não encontrada"}, status=404)
    return JsonResponse({
        "valida": assinatura.status == "assinado",
        "assinatura": _assinatura_to_dict(assinatura, request),
        "empresa": assinatura.empresa.nome,
        "funcionario": assinatura.funcionario.nome if assinatura.funcionario else None,
    })


@csrf_exempt
def api_public_assinar_sst(request, token):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)
    assinatura = AssinaturaDocumentoSST.objects.filter(token=token).select_related("empresa").first()
    if not assinatura:
        return JsonResponse({"erro": "assinatura não encontrada"}, status=404)
    if assinatura.status == "cancelado":
        return JsonResponse({"erro": "assinatura cancelada"}, status=409)
    if assinatura.expiracao_em and assinatura.expiracao_em < timezone.now():
        return JsonResponse({"erro": "solicitação expirada"}, status=410)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    if not data.get("aceite"):
        return JsonResponse({"erro": "aceite obrigatório"}, status=400)

    nome = (data.get("nome") or assinatura.signatario_nome or "").strip()
    cpf = (data.get("cpf") or assinatura.signatario_cpf or "").strip()
    email = (data.get("email") or assinatura.signatario_email or "").strip()
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)

    assinado_em = timezone.now()
    ip = _client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
    assinatura.signatario_nome = nome
    assinatura.signatario_cpf = cpf
    assinatura.signatario_email = email
    assinatura.ip_assinatura = ip
    assinatura.user_agent_assinatura = user_agent
    assinatura.assinado_em = assinado_em
    assinatura.status = "assinado"
    assinatura.hash_assinatura = hashlib.sha256(
        f"{assinatura.token}:{assinatura.hash_documento}:{nome}:{cpf}:{email}:{ip}:{assinado_em.isoformat()}".encode("utf-8")
    ).hexdigest()
    assinatura.save(update_fields=[
        "signatario_nome",
        "signatario_cpf",
        "signatario_email",
        "ip_assinatura",
        "user_agent_assinatura",
        "assinado_em",
        "status",
        "hash_assinatura",
        "atualizado_em",
    ])
    return JsonResponse({"ok": True, "assinatura": _assinatura_to_dict(assinatura, request)})
