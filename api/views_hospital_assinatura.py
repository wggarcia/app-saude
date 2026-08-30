"""
Assinatura Digital de Prontuário — CFM Resolução 2.299/2021
Usa o certificado ICP-Brasil (PKCS#12) armazenado em CredenciaisIntegracoes
para assinar digitalmente evoluções clínicas e fechar prontuários.

GET  /api/hospital/assinatura/pendentes        Evoluções sem assinatura digital
POST /api/hospital/assinatura/assinar/<id>     Assina uma evolução com ICP-Brasil
POST /api/hospital/assinatura/assinar-lote     Assina múltiplas evoluções
GET  /api/hospital/assinatura/verificar/<id>   Verifica validade da assinatura
GET  /api/hospital/assinatura/kpis             Cobertura de assinaturas
"""
import base64
import hashlib
import json
import logging
import math
import tempfile
from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .services.auth_session import empresa_autenticada_from_request
from .assinatura_digital import assinar_conteudo, verificar_assinatura
from .access_control import (
    api_requer_permissao_modulo,
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)


def _hosp(request):
    emp = empresa_autenticada_from_request(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.assinatura_eletronica", "Assinatura Eletrônica")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_assinatura_page(request):
    return render(request, "hospital_assinatura.html")


def _get_cred(empresa):
    try:
        from .models import CredenciaisIntegracoes
        cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
        return cred
    except Exception:
        return None


# ── Evoluções pendentes de assinatura ─────────────────────────────────────────

@api_requer_feature("hospital.assinatura_eletronica")
@api_requer_permissao_modulo("hospital.clinico")
def api_assinatura_pendentes(request):
    """
    GET /api/hospital/assinatura/pendentes
    Lista evoluções clínicas que ainda não foram assinadas digitalmente.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import EvolucaoProntuario

    page = max(1, int(request.GET.get("page") or 1))
    ps   = 50
    profissional = (request.GET.get("profissional") or "").strip()

    qs = EvolucaoProntuario.objects.filter(
        prontuario__empresa=empresa,
        assinado_digitalmente=False,
    ).select_related("prontuario")

    if profissional:
        qs = qs.filter(profissional__icontains=profissional)

    total  = qs.count()
    items  = qs[(page - 1) * ps: page * ps]

    return JsonResponse({
        "total":   total,
        "pagina":  page,
        "paginas": math.ceil(total / ps) if total else 1,
        "pendentes": [_evolucao_dict(e) for e in items],
        "aviso": (
            "Conforme CFM Res. 2.299/2021, evoluções clínicas devem ser "
            "assinadas digitalmente com certificado ICP-Brasil para ter "
            "validade jurídica como prontuário eletrônico."
        ) if total > 0 else None,
    })


# ── Assinar uma evolução ──────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.assinatura_eletronica")
@api_requer_permissao_modulo("hospital.clinico")
def api_assinatura_assinar(request, evolucao_id):
    """
    POST /api/hospital/assinatura/assinar/<id>
    Body: {"crm_coren": "CRM/SP 123456", "senha_certificado": "opcional se diferente"}

    Assina digitalmente a evolução com o certificado ICP-Brasil do hospital.
    O profissional deve confirmar sua identidade (CRM/CRO/COREN).
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import EvolucaoProntuario

    try:
        evolucao = EvolucaoProntuario.objects.get(
            id=evolucao_id,
            prontuario__empresa=empresa,
        )
    except EvolucaoProntuario.DoesNotExist:
        return JsonResponse({"erro": "Evolução não encontrada"}, status=404)

    if evolucao.assinado_digitalmente:
        return JsonResponse({
            "aviso":      "Evolução já assinada digitalmente.",
            "assinado_em": evolucao.assinado_digitalmente_em.isoformat() if evolucao.assinado_digitalmente_em else None,
            "hash":       evolucao.assinatura_hash,
        })

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    crm_coren         = (body.get("crm_coren") or evolucao.crm_coren or "").strip()
    senha_override    = (body.get("senha_certificado") or "").strip()

    cred = _get_cred(empresa)
    # Usa o módulo de assinatura compartilhado: CAdES-BES real quando há
    # certificado ICP-Brasil; fallback SHA-256 quando não. O método retornado
    # é HONESTO (não mais rótulo "PKCS7" fixo).
    conteudo_canonical = _conteudo_canonical(evolucao)
    ok, assinatura, hash_doc, metodo, erro = assinar_conteudo(
        conteudo_canonical, cred, identificador=crm_coren, senha_override=senha_override
    )
    if not ok:
        return JsonResponse({"erro": f"Falha na assinatura: {erro}"}, status=422)

    evolucao.assinatura_icp           = assinatura
    evolucao.assinatura_hash          = hash_doc
    evolucao.assinado_digitalmente    = True
    evolucao.assinado_digitalmente_em = timezone.now()
    if crm_coren:
        evolucao.crm_coren = crm_coren
    evolucao.save(update_fields=[
        "assinatura_icp", "assinatura_hash",
        "assinado_digitalmente", "assinado_digitalmente_em", "crm_coren",
    ])

    return JsonResponse({
        "ok":           True,
        "evolucao_id":  evolucao_id,
        "hash":         hash_doc,
        "metodo":       metodo,
        "assinado_em":  evolucao.assinado_digitalmente_em.isoformat(),
        "profissional": evolucao.profissional,
        "crm_coren":    evolucao.crm_coren,
        "aviso": (
            "Assinatura aplicada como hash SHA-256 (modo operacional). "
            "Para validade jurídica plena (CFM Res. 2.299/2021), configure "
            "o certificado ICP-Brasil em Configurações → Integrações → RNDS."
        ) if metodo == "SHA256" else None,
    })


# ── Assinar em lote ───────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.assinatura_eletronica")
@api_requer_permissao_modulo("hospital.clinico")
def api_assinatura_assinar_lote(request):
    """
    POST /api/hospital/assinatura/assinar-lote
    Body: {"ids": [1, 2, 3], "crm_coren": "CRM/SP 123456"}
    Assina múltiplas evoluções de uma vez.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    ids        = body.get("ids") or []
    crm_coren  = (body.get("crm_coren") or "").strip()

    if not ids or len(ids) > 100:
        return JsonResponse({"erro": "Envie entre 1 e 100 IDs"}, status=400)

    from .models import EvolucaoProntuario

    evs = EvolucaoProntuario.objects.filter(
        id__in=ids,
        prontuario__empresa=empresa,
        assinado_digitalmente=False,
    )

    cred   = _get_cred(empresa)
    pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "") if cred else ""
    agora  = timezone.now()

    resultados   = []
    assinados    = 0
    erros_count  = 0
    metodo       = None

    for ev in evs:
        ok, assinatura, hash_doc, metodo, erro = assinar_conteudo(
            _conteudo_canonical(ev), cred, identificador=crm_coren
        )

        if ok:
            ev.assinatura_icp           = assinatura
            ev.assinatura_hash          = hash_doc
            ev.assinado_digitalmente    = True
            ev.assinado_digitalmente_em = agora
            if crm_coren:
                ev.crm_coren = crm_coren
            ev.save(update_fields=[
                "assinatura_icp", "assinatura_hash",
                "assinado_digitalmente", "assinado_digitalmente_em", "crm_coren",
            ])
            assinados += 1
            resultados.append({"id": ev.id, "ok": True, "hash": hash_doc})
        else:
            erros_count += 1
            resultados.append({"id": ev.id, "ok": False, "erro": erro})

    return JsonResponse({
        "total":     len(ids),
        "assinados": assinados,
        "erros":     erros_count,
        "metodo":    metodo,
        "resultados": resultados,
    }, status=200 if erros_count == 0 else 207)


# ── Verificar assinatura ──────────────────────────────────────────────────────

@api_requer_feature("hospital.assinatura_eletronica")
@api_requer_permissao_modulo("hospital.clinico")
def api_assinatura_verificar(request, evolucao_id):
    """
    GET /api/hospital/assinatura/verificar/<id>
    Verifica a integridade da assinatura digital de uma evolução.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import EvolucaoProntuario

    try:
        ev = EvolucaoProntuario.objects.get(id=evolucao_id, prontuario__empresa=empresa)
    except EvolucaoProntuario.DoesNotExist:
        return JsonResponse({"erro": "Evolução não encontrada"}, status=404)

    if not ev.assinado_digitalmente:
        return JsonResponse({
            "assinado":  False,
            "valido":    None,
            "mensagem":  "Evolução não possui assinatura digital.",
        })

    # Verificação REAL: integridade (hash) + autenticidade criptográfica
    # (assinatura confere com o certificado), não apenas comparação de hash.
    conteudo_canonical = _conteudo_canonical(ev)
    cred = _get_cred(empresa)
    v = verificar_assinatura(conteudo_canonical, ev.assinatura_icp, ev.assinatura_hash, cred)

    integro = v["integro"]
    autentico = v["autentico"]
    # "valido" só é True quando íntegro E (autenticidade confirmada OU não aplicável=SHA256)
    valido = integro and (autentico is not False)

    if not integro:
        msg = "⚠ ALERTA: documento alterado após a assinatura (hash divergente)."
    elif autentico is True:
        msg = "✓ Assinatura válida — íntegra e confere com o certificado ICP-Brasil."
    elif autentico is False:
        msg = "⚠ ALERTA: assinatura NÃO confere com o certificado."
    else:
        msg = "✓ Documento íntegro (assinatura SHA-256, sem validade jurídica plena)."

    return JsonResponse({
        "assinado":              True,
        "valido":                valido,
        "integro":               integro,
        "autentico":             autentico,
        "metodo":                v["metodo"],
        "hash_armazenado":       ev.assinatura_hash,
        "hash_calculado_agora":  v["hash_calculado"],
        "assinado_em":           ev.assinado_digitalmente_em.isoformat() if ev.assinado_digitalmente_em else None,
        "profissional":          ev.profissional,
        "crm_coren":             ev.crm_coren,
        "detalhe":               v["detalhe"],
        "mensagem":              msg,
    })


# ── KPIs ─────────────────────────────────────────────────────────────────────

@api_requer_feature("hospital.assinatura_eletronica")
@api_requer_permissao_modulo("hospital.clinico")
def api_assinatura_kpis(request):
    """GET /api/hospital/assinatura/kpis."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    from .models import EvolucaoProntuario

    qs    = EvolucaoProntuario.objects.filter(prontuario__empresa=empresa)
    total = qs.count()
    assinadas    = qs.filter(assinado_digitalmente=True).count()
    nao_assinadas = total - assinadas

    cred   = _get_cred(empresa)
    tem_cert = bool(getattr(cred, "rnds_certificado_pfx_b64", "")) if cred else False

    return JsonResponse({
        "total_evolucoes":     total,
        "assinadas":           assinadas,
        "pendentes":           nao_assinadas,
        "cobertura_pct":       round(assinadas / total * 100, 1) if total else 0,
        "certificado_icp_configurado": tem_cert,
        "modo_assinatura": "ICP-Brasil (validade jurídica plena)" if tem_cert else "SHA-256 (operacional)",
        "conformidade_cfm": assinadas == total and tem_cert,
    })


# ── Helpers de assinatura ─────────────────────────────────────────────────────

def _conteudo_canonical(evolucao):
    """
    Texto canônico para assinar — inclui todos os campos que não podem mudar.
    Qualquer alteração posterior tornará o hash inválido.
    """
    return (
        f"PRONTUARIO:{evolucao.prontuario_id}|"
        f"EVOLUCAO:{evolucao.id}|"
        f"PROFISSIONAL:{evolucao.profissional}|"
        f"CRM:{evolucao.crm_coren}|"
        f"TIPO:{evolucao.tipo}|"
        f"CID:{evolucao.cid10}|"
        f"TEXTO:{evolucao.texto}|"
        f"DATA:{evolucao.assinado_em.isoformat() if evolucao.assinado_em else ''}"
    )


def _evolucao_dict(e):
    return {
        "id":                    e.id,
        "prontuario_id":         e.prontuario_id,
        "paciente_nome":         e.prontuario.paciente_nome if e.prontuario_id else "",
        "profissional":          e.profissional,
        "crm_coren":             e.crm_coren,
        "tipo":                  e.tipo,
        "cid10":                 e.cid10,
        "texto_resumo":          e.texto[:120] + "…" if len(e.texto) > 120 else e.texto,
        "assinado_digitalmente": e.assinado_digitalmente,
        "assinado_em":           e.assinado_em.isoformat() if e.assinado_em else None,
        "assinado_digitalmente_em": e.assinado_digitalmente_em.isoformat() if e.assinado_digitalmente_em else None,
    }
