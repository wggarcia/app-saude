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
    NotificacaoFuncionario,
)
from .services.employee_notifications import notificar_assinatura_sst
from .views_dashboard import _empresa_autenticada


ASSINATURA_SST_REGRAS = {
    "aso": {
        "papel": "funcionario",
        "finalidade": "ciencia_trabalhador",
        "titulo_acao": "Ciência do trabalhador sobre ASO",
        "quem_assina": "Funcionário / trabalhador vinculado ao ASO",
        "orientacao": (
            "Use este link para o trabalhador confirmar ciência e recebimento do ASO. "
            "Isso não substitui a emissão médica do ASO nem o evento eSocial S-2220."
        ),
        "aceite": "Declaro que li e recebi ciência do ASO identificado nesta página.",
    },
    "cat": {
        "papel": "funcionario",
        "finalidade": "ciencia_trabalhador",
        "titulo_acao": "Ciência do trabalhador sobre CAT",
        "quem_assina": "Funcionário acidentado ou representante autorizado",
        "orientacao": (
            "Use este link para registrar ciência do trabalhador sobre a CAT. "
            "A responsabilidade de emissão, correção e envio ao eSocial permanece com a empresa/SESMT."
        ),
        "aceite": "Declaro que li e recebi ciência das informações da CAT identificada nesta página.",
    },
    "prontuario": {
        "papel": "funcionario",
        "finalidade": "entrega_documento",
        "titulo_acao": "Entrega de prontuário SST",
        "quem_assina": "Funcionário / trabalhador",
        "orientacao": (
            "O prontuário SST desta empresa foi disponibilizado para você. "
            "Clique em Baixar PDF para acessar seu histórico de ASOs, exames, afastamentos e EPIs."
        ),
        "aceite": "",
    },
    "documento_sst": {
        "papel": "responsavel_tecnico",
        "finalidade": "validacao_tecnica",
        "titulo_acao": "Validação de documento SST",
        "quem_assina": "Responsável técnico ou representante legal autorizado",
        "orientacao": (
            "Use este link para validação técnica ou aceite formal de documento SST geral, "
            "como PGR, PCMSO, LTCAT, PPP, CIPA ou laudos. Para assinatura ICP-Brasil, conecte um provedor externo."
        ),
        "aceite": "Declaro que li, conferi e valido o documento SST identificado nesta página.",
    },
}


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


def _regra_assinatura(tipo_documento):
    return ASSINATURA_SST_REGRAS.get(tipo_documento, {
        "papel": "outro",
        "finalidade": "aceite_documento",
        "titulo_acao": "Assinatura eletrônica SST",
        "quem_assina": "Pessoa autorizada pela empresa",
        "orientacao": "Use este link para registrar aceite eletrônico auditável do documento SST.",
        "aceite": "Declaro que li o documento identificado acima e confirmo minha assinatura eletrônica neste registro.",
    })


def _assinatura_meta(assinatura):
    regra = _regra_assinatura(assinatura.tipo_documento)
    papel = assinatura.papel_signatario or regra["papel"]
    finalidade = assinatura.finalidade_assinatura or regra["finalidade"]
    papel_label = dict(AssinaturaDocumentoSST.PAPEL_SIGNATARIO_CHOICES).get(papel, regra["quem_assina"])
    finalidade_label = dict(AssinaturaDocumentoSST.FINALIDADE_CHOICES).get(finalidade, regra["titulo_acao"])
    return {
        **regra,
        "papel": papel,
        "papel_label": papel_label,
        "finalidade": finalidade,
        "finalidade_label": finalidade_label,
    }


def _assinatura_to_dict(assinatura, request=None):
    from django.conf import settings
    base_url = settings.PUBLIC_BASE_URL
    meta = _assinatura_meta(assinatura)
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
        "papel_signatario": meta["papel"],
        "papel_signatario_label": meta["papel_label"],
        "finalidade_assinatura": meta["finalidade"],
        "finalidade_assinatura_label": meta["finalidade_label"],
        "quem_deve_assinar": meta["quem_assina"],
        "orientacao_assinatura": meta["orientacao"],
        "aceite_texto": meta["aceite"],
        "criado_em": assinatura.criado_em.strftime("%d/%m/%Y %H:%M"),
        "assinado_em": assinatura.assinado_em.strftime("%d/%m/%Y %H:%M") if assinatura.assinado_em else None,
        "expiracao_em": assinatura.expiracao_em.strftime("%d/%m/%Y %H:%M") if assinatura.expiracao_em else None,
        "link_assinatura": f"{base_url}/assinatura/sst/{assinatura.token}/" if base_url else f"/assinatura/sst/{assinatura.token}/",
        "link_validacao": f"{base_url}/validar-assinatura/{assinatura.token}/" if base_url else f"/validar-assinatura/{assinatura.token}/",
    }


def api_public_prontuario_pdf(request, token):
    """GET /api/public/sst/prontuario/<token>/pdf/ — serve o PDF do prontuário via token público."""
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_prontuario
    from .models import ASOOcupacional, ExameOcupacional, CATOcupacional, AfastamentoSST

    assinatura = AssinaturaDocumentoSST.objects.filter(
        token=token, tipo_documento="prontuario"
    ).select_related("funcionario", "empresa").first()

    if not assinatura:
        return JsonResponse({"erro": "link não encontrado"}, status=404)
    if assinatura.expiracao_em and assinatura.expiracao_em < timezone.now():
        return JsonResponse({"erro": "link expirado"}, status=410)

    func = assinatura.funcionario
    empresa = assinatura.empresa
    if not func:
        return JsonResponse({"erro": "funcionário não encontrado"}, status=404)

    asos         = ASOOcupacional.objects.filter(funcionario=func, empresa=empresa).order_by("-data_emissao")
    exames       = ExameOcupacional.objects.filter(funcionario=func, empresa=empresa).order_by("-data_realizacao")
    cats         = CATOcupacional.objects.filter(funcionario=func, empresa=empresa).order_by("-data_acidente")
    afastamentos = AfastamentoSST.objects.filter(funcionario=func, empresa=empresa).order_by("-data_inicio")

    pdf_bytes = gerar_pdf_prontuario(func, list(asos), list(exames), list(cats), list(afastamentos), empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="prontuario_{func.matricula or func.id}.pdf"'
    return resp


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
        regra = _regra_assinatura(tipo_documento)
        funcionario = doc["funcionario"]
        signatario_nome = data.get("signatario_nome", "")
        signatario_cpf = data.get("signatario_cpf", "")
        if regra["papel"] == "funcionario" and funcionario:
            signatario_nome = signatario_nome or funcionario.nome
            signatario_cpf = signatario_cpf or funcionario.cpf
        assinatura = AssinaturaDocumentoSST.objects.create(
            empresa=empresa,
            funcionario=funcionario,
            tipo_documento=tipo_documento,
            objeto_id=int(objeto_id),
            titulo=data.get("titulo") or doc["titulo"],
            hash_documento=hash_documento,
            signatario_nome=signatario_nome,
            signatario_email=data.get("signatario_email", ""),
            signatario_cpf=signatario_cpf,
            papel_signatario=data.get("papel_signatario") or regra["papel"],
            finalidade_assinatura=data.get("finalidade_assinatura") or regra["finalidade"],
            solicitado_por=data.get("solicitado_por", empresa.email or empresa.nome),
            ip_solicitacao=_client_ip(request),
            expiracao_em=timezone.now() + timedelta(days=int(data.get("validade_dias") or 15)),
        )
        if funcionario and assinatura.papel_signatario == "funcionario":
            notificar_assinatura_sst(assinatura)
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
        "meta": _assinatura_meta(assinatura) if assinatura else None,
        "modo": "assinar",
        "token": token,
    })


def pagina_validar_assinatura(request, token):
    assinatura = AssinaturaDocumentoSST.objects.filter(token=token).select_related("empresa", "funcionario").first()
    return render(request, "assinatura_sst.html", {
        "assinatura": assinatura,
        "meta": _assinatura_meta(assinatura) if assinatura else None,
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
    if assinatura.status == "assinado":
        return JsonResponse({"erro": "assinatura já concluída"}, status=409)
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
    if assinatura.funcionario_id:
        NotificacaoFuncionario.objects.filter(
            empresa_id=assinatura.empresa_id,
            funcionario_id=assinatura.funcionario_id,
            tipo=NotificacaoFuncionario.TIPO_ASSINATURA_SST,
            referencia_id=assinatura.id,
        ).update(lida=True)
    return JsonResponse({"ok": True, "assinatura": _assinatura_to_dict(assinatura, request)})
