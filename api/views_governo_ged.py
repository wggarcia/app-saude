"""
views_governo_ged.py
GED — Gestão Eletrônica de Documentos (Governo).
"""
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .utils import validar_cpf_cadastro
from .access_control import (
    get_setor, principal_e_gerencia, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
    api_requer_permissao_modulo,
)
from .models import DocumentoGED, EmpresaUnidade
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB por documento


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.administrativo", "governo.secretaria_agendamento")
def governo_ged_page(request):
    return render(request, "governo_ged.html", contexto_navegacao_setorial(request, "governo"))


# ── Documentos (listar / upload) ───────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.administrativo", "governo.secretaria_agendamento")
def api_ged_documentos(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = DocumentoGED.objects.filter(empresa=e)
        if not principal_e_gerencia(request):
            qs = qs.filter(confidencial=False)
        categoria = request.GET.get("categoria")
        if categoria:
            qs = qs.filter(categoria=categoria)
        numero_processo = request.GET.get("numero_processo")
        if numero_processo:
            qs = qs.filter(numero_processo=numero_processo)
        q = request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(titulo__icontains=q) | Q(descricao__icontains=q) | Q(tags__icontains=q)
                | Q(paciente_nome__icontains=q) | Q(numero_processo__icontains=q)
            )
        return JsonResponse({"total": qs.count(), "documentos": [_doc_dict(d) for d in qs[:200]]})

    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        return JsonResponse({"erro": "Envie o arquivo no campo 'arquivo'"}, status=400)
    if arquivo.size > MAX_UPLOAD_BYTES:
        return JsonResponse({"erro": f"Arquivo maior que {MAX_UPLOAD_BYTES // (1024*1024)}MB"}, status=400)
    from .utils import validar_arquivo_upload
    erro_tipo = validar_arquivo_upload(arquivo)
    if erro_tipo:
        return JsonResponse({"erro": erro_tipo}, status=400)
    titulo = request.POST.get("titulo", "").strip()
    if not titulo:
        return JsonResponse({"erro": "titulo obrigatório"}, status=400)

    unidade = None
    unidade_id = request.POST.get("unidade_id")
    if unidade_id:
        unidade = EmpresaUnidade.objects.filter(pk=unidade_id, empresa=e).first()

    ok_cpf, erro_cpf = validar_cpf_cadastro(request.POST.get("paciente_cpf", ""), e)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    doc = DocumentoGED.objects.create(
        empresa=e, unidade=unidade,
        categoria=request.POST.get("categoria", "outro"),
        titulo=titulo,
        descricao=request.POST.get("descricao", ""),
        arquivo=arquivo,
        nome_arquivo_original=arquivo.name,
        tamanho_bytes=arquivo.size,
        paciente_nome=request.POST.get("paciente_nome", ""),
        paciente_cpf=request.POST.get("paciente_cpf", ""),
        numero_processo=request.POST.get("numero_processo", ""),
        tags=request.POST.get("tags", ""),
        confidencial=request.POST.get("confidencial") in ("1", "true", "True", "on"),
        criado_por=request.POST.get("criado_por", ""),
    )
    return JsonResponse(_doc_dict(doc), status=201)


# ── Documento individual (detalhe / excluir) ──────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "DELETE"])
@api_requer_permissao_modulo("governo.administrativo", "governo.secretaria_agendamento")
def api_ged_documento_detalhe(request, doc_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        doc = DocumentoGED.objects.get(pk=doc_id, empresa=e)
    except DocumentoGED.DoesNotExist:
        return JsonResponse({"erro": "Documento não encontrado"}, status=404)

    if doc.confidencial and not principal_e_gerencia(request):
        return JsonResponse({"erro": "Documento confidencial — acesso restrito à gerência"}, status=403)

    if request.method == "DELETE":
        doc.arquivo.delete(save=False)
        doc.delete()
        return JsonResponse({"ok": True})

    return JsonResponse(_doc_dict(doc, com_url=True))


def _doc_dict(d, com_url=False):
    out = {
        "id": d.id,
        "categoria": d.categoria,
        "categoria_display": d.get_categoria_display(),
        "titulo": d.titulo,
        "descricao": d.descricao,
        "nome_arquivo_original": d.nome_arquivo_original,
        "tamanho_bytes": d.tamanho_bytes,
        "paciente_nome": d.paciente_nome,
        "numero_processo": d.numero_processo,
        "tags": d.tags,
        "confidencial": d.confidencial,
        "criado_por": d.criado_por,
        "criado_em": d.criado_em.isoformat(),
    }
    if com_url:
        try:
            out["url"] = d.arquivo.url
        except ValueError:
            out["url"] = None
    return out
