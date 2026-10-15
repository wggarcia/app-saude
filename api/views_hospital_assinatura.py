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


# ── Prescrição de internação assinada ─────────────────────────────────────────
# A Resolução CFM 2.299/2021 lista "Prescrição" (art. 1º) entre os documentos
# médicos eletrônicos — não é privilégio de um módulo. Estes endpoints usam o
# certificado do PROFISSIONAL (`CertificadoAssinante`), que é o que o art. 4º
# exige, e caem para o certificado institucional apenas quando é o único
# disponível — informando que, nesse caso, não se cumpre o art. 4º para ato
# médico.
#
# Assina-se o CONJUNTO de itens ativos, porque prescrição é um documento: item
# a item, alguém poderia acrescentar uma linha depois sem invalidar nada.

def _provedor_do_documento(empresa, nome=None, cpf=None, registro=None):
    """Escolhe o certificado: do profissional primeiro, institucional depois."""
    from .services.assinatura_icp import (ProvedorCertificadoInstitucional,
                                          localizar_certificado, provedor_para)
    cfg = localizar_certificado(empresa, nome=nome, cpf=cpf, registro=registro)
    if cfg is not None:
        return cfg, provedor_para(cfg)
    institucional = ProvedorCertificadoInstitucional(empresa)
    if institucional.disponivel():
        return None, institucional
    return None, provedor_para(None)


@csrf_exempt
@api_requer_permissao_modulo("hospital.clinico")
def api_prescricao_internacao_assinatura(request, internacao_id):
    """GET/POST /api/hospital/internacoes/<id>/prescricao/assinatura/"""
    if request.method not in ("GET", "POST"):
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import (AssinaturaDocumento, InternacaoHospital,
                         PrescricaoMedica)
    from .services.assinatura_icp import (
        AssinaturaIndisponivel, TIPO_PRESCRICAO_INTERNACAO, ALGORITMO_RESUMO,
        conteudo_canonico_prescricao_internacao,
        elementos_faltando_art2_internacao, resumo_sha256)

    internacao = InternacaoHospital.objects.filter(
        id=internacao_id, empresa=empresa
    ).select_related("paciente", "leito").first()
    if internacao is None:
        return JsonResponse({"erro": "Internação não encontrada"}, status=404)

    itens = list(PrescricaoMedica.objects.filter(
        internacao=internacao, status="ativa").order_by("id"))
    vigente = AssinaturaDocumento.objects.filter(
        empresa=empresa, tipo_documento=TIPO_PRESCRICAO_INTERNACAO,
        objeto_id=internacao.id).order_by("-criado_em").first()

    if request.method == "GET":
        cfg, provedor = _provedor_do_documento(
            empresa, nome=internacao.medico_responsavel)
        resposta = {
            "itens_ativos": len(itens),
            "provedor": provedor.nome,
            "provedor_rotulo": provedor.rotulo,
            "pode_assinar": provedor.disponivel(),
            "pendencias": provedor.requisitos_pendentes(),
            "elementos_faltando_art2": elementos_faltando_art2_internacao(
                internacao, cfg),
        }
        if vigente is None:
            resposta.update({"assinada": False, "assinatura": None})
            return JsonResponse(resposta)
        conferencia = _conferir_prescricao(internacao, itens, vigente)
        vigente.refresh_from_db()
        resposta.update({
            "assinada": vigente.status == "assinada",
            "assinatura": _assinatura_prescricao_dict(vigente, conferencia),
        })
        return JsonResponse(resposta)

    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"erro": "JSON inválido no corpo"}, status=400)

    if not itens:
        return JsonResponse(
            {"erro": "Não há itens ativos na prescrição para assinar.",
             "codigo": "prescricao_vazia"}, status=400)

    if vigente and vigente.status == "assinada":
        conferencia = _conferir_prescricao(internacao, itens, vigente)
        if conferencia["integro"]:
            return JsonResponse({
                "erro": "Esta prescrição já está assinada e íntegra.",
                "codigo": "ja_assinada",
                "assinatura": _assinatura_prescricao_dict(vigente, conferencia),
            }, status=409)

    signatario = (body.get("signatario_nome")
                  or internacao.medico_responsavel or "").strip()
    if not signatario:
        return JsonResponse(
            {"erro": "Informe quem está assinando a prescrição.",
             "codigo": "sem_signatario"}, status=400)

    cfg, provedor = _provedor_do_documento(
        empresa, nome=signatario, cpf=body.get("signatario_cpf"),
        registro=body.get("signatario_registro"))

    emitido_em = timezone.now()
    conteudo = conteudo_canonico_prescricao_internacao(
        internacao, itens, cfg=cfg, emitido_em=emitido_em)
    conteudo_hash = resumo_sha256(conteudo)
    faltando = elementos_faltando_art2_internacao(internacao, cfg)

    comuns = dict(
        empresa=empresa, tipo_documento=TIPO_PRESCRICAO_INTERNACAO,
        objeto_id=internacao.id, conteudo_hash=conteudo_hash,
        algoritmo=ALGORITMO_RESUMO,
        signatario_nome=signatario[:150],
        signatario_registro=(body.get("signatario_registro") or "").strip()[:40],
        certificado_config=cfg, documento_emitido_em=emitido_em)

    try:
        resultado = provedor.assinar(
            conteudo.encode("utf-8"),
            contexto={"tipo_documento": TIPO_PRESCRICAO_INTERNACAO})
    except AssinaturaIndisponivel as exc:
        # Registra como FALHA — nunca como assinada.
        AssinaturaDocumento.objects.create(
            status="falha", provedor=provedor.nome,
            motivo_falha=exc.mensagem, **comuns)
        return JsonResponse({
            "erro": exc.mensagem, "codigo": exc.codigo,
            "pendencias": exc.pendencias, "assinada": False,
            "documento_hash": conteudo_hash,
            "elementos_faltando_art2": faltando,
        }, status=503)

    cert = resultado.get("certificado") or {}
    a = AssinaturaDocumento.objects.create(
        status="assinada",
        certificado_titular=(cert.get("titular") or "")[:200],
        certificado_cpf_cnpj=(cert.get("cpf_cnpj") or "")[:20],
        certificado_emissor=(cert.get("emissor") or "")[:200],
        certificado_serie=(cert.get("numero_serie") or "")[:80],
        certificado_valido_de=cert.get("valido_de"),
        certificado_valido_ate=cert.get("valido_ate"),
        assinatura_b64=resultado.get("assinatura_b64", ""),
        provedor=resultado.get("provedor", provedor.nome),
        assinado_em=resultado.get("assinado_em") or timezone.now(),
        carimbo_tempo_em=resultado.get("carimbo_tempo_em"), **comuns)

    conforme_cfm = bool(resultado.get("conforme_cfm"))
    avisos = []
    if faltando:
        avisos.append("Documento incompleto para o art. 2º da Resolução CFM "
                      "2.299/2021 — falta: " + ", ".join(faltando) + ".")
    if not conforme_cfm:
        avisos.append("Assinado com certificado da INSTITUIÇÃO. O art. 4º exige "
                      "a assinatura do MÉDICO para ato médico — cadastre o "
                      "certificado do profissional.")
    return JsonResponse({
        "assinada": True,
        "assinatura": _assinatura_prescricao_dict(a, {
            "integro": True, "hash_atual": conteudo_hash,
            "hash_assinado": conteudo_hash,
            "mensagem": "Documento recém-assinado."}),
        "itens_assinados": len(itens),
        "formato": resultado.get("formato", ""),
        "conforme_cfm": conforme_cfm,
        "elementos_faltando_art2": faltando,
        "alerta": " ".join(avisos) or None,
    }, status=201)


def _conferir_prescricao(internacao, itens, assinatura):
    """Recalcula o resumo do CONJUNTO e compara com o que foi assinado."""
    from .services.assinatura_icp import (
        conteudo_canonico_prescricao_internacao, resumo_sha256)

    atual = resumo_sha256(conteudo_canonico_prescricao_internacao(
        internacao, itens, cfg=assinatura.certificado_config,
        emitido_em=assinatura.documento_emitido_em))
    integro = (atual == assinatura.conteudo_hash)
    if not integro and assinatura.status == "assinada":
        assinatura.status = "invalidada"
        assinatura.motivo_falha = (
            "A prescrição mudou depois da assinatura: o resumo recalculado não "
            "confere com o que foi assinado.")
        assinatura.save(update_fields=["status", "motivo_falha"])
    return {
        "integro": integro,
        "hash_atual": atual,
        "hash_assinado": assinatura.conteudo_hash,
        "mensagem": ("Documento íntegro: confere com o conteúdo assinado."
                     if integro else
                     "ATENÇÃO: a prescrição foi alterada após a assinatura. "
                     "A assinatura não cobre o conteúdo atual."),
    }


def _assinatura_prescricao_dict(a, conferencia=None):
    d = {
        "id": a.id,
        "status": a.status,
        "status_display": a.get_status_display(),
        "conteudo_hash": a.conteudo_hash,
        "algoritmo": a.algoritmo,
        "signatario_nome": a.signatario_nome,
        "signatario_registro": a.signatario_registro,
        "certificado_titular": a.certificado_titular,
        "provedor": a.provedor,
        "assinado_em": a.assinado_em.isoformat() if a.assinado_em else None,
        # Sem carimbo de uma ACT externa a data é a do nosso relógio.
        "data_com_fe_publica": a.carimbo_tempo_em is not None,
        "motivo_falha": a.motivo_falha,
    }
    if conferencia is not None:
        d["conferencia"] = conferencia
    return d


# ── Roteiro de implantação ────────────────────────────────────────────────────
# Um hospital que acaba de contratar precisa saber O QUE fazer, NA ORDEM, e de
# quem é cada passo. Sem isso ele descobre na marra — ou descobre tarde, na
# frente do paciente, que a prescrição sai sem assinatura.
#
# O status de cada passo é CALCULADO do estado real do sistema, não é uma lista
# que alguém marca à mão. Checklist que o próprio usuário marca vira ficção.

def _passos_implantacao(empresa):
    """Monta o roteiro com o status real de cada passo."""
    from .models import (AssinaturaDocumento, CertificadoAssinante,
                         CredenciaisIntegracoes, ResponsabilidadeTecnica)
    from .services.assinatura_icp import status_assinatura

    rt = ResponsabilidadeTecnica.objects.filter(empresa=empresa).first()
    assinantes = list(CertificadoAssinante.objects.filter(empresa=empresa))

    from .services.assinatura_icp import provedor_para
    prontos = []
    for c in assinantes:
        # Avalia a configuração, independente do status administrativo.
        if c.provedor in ("vidaas", "birdid"):
            from .services.assinatura_icp import ProvedorNuvemICP
            p = ProvedorNuvemICP(c)
        elif c.provedor == "api_hospital":
            from .services.assinatura_icp import ProvedorApiHospital
            p = ProvedorApiHospital(c)
        elif c.provedor == "a1_local":
            from .services.assinatura_icp import ProvedorA1Local
            p = ProvedorA1Local(cfg=c)
        else:
            p = provedor_para(None)
        if p.disponivel():
            prontos.append(c)

    sem_dados_art2 = [c.profissional_nome for c in assinantes
                      if not c.profissional_registro or
                      not (c.profissional_endereco or (rt.endereco if rt else ""))]
    ja_assinou = AssinaturaDocumento.objects.filter(
        empresa=empresa, status="assinada").exists()
    cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    tem_institucional = bool(cred and getattr(cred, "rnds_certificado_pfx_b64", ""))

    from django.conf import settings
    cfm_ws = bool(getattr(settings, "CFM_WS_USUARIO", "")
                  and getattr(settings, "CFM_WS_SENHA", ""))

    passos = [
        {
            "id": "responsabilidade_tecnica",
            "titulo": "Registrar a responsabilidade técnica do hospital",
            "de_quem": "hospital",
            "obrigatorio": True,
            "concluido": bool(rt and not rt.pendencias()),
            "resumo": "Inscrição do estabelecimento no CRM da jurisdição da "
                      "sede e indicação de um Diretor Técnico médico.",
            "como_fazer": [
                "O hospital já é obrigado a ter inscrição no CRM e Diretor "
                "Técnico — aqui é só informar os dados que já existem.",
                "Preencher em Assinatura Digital → Responsabilidade técnica: "
                "inscrição, UF, Diretor Técnico com CRM, endereço e CNES.",
                "Informar os médicos usuários, por escrito, de que a "
                "plataforma atende às normas do CFM, e registrar a data.",
            ],
            "base": "Resolução CFM 2.299/2021, art. 5º e parágrafo único",
            "pendencias": rt.pendencias() if rt else [
                "Responsabilidade técnica ainda não cadastrada."],
        },
        {
            "id": "cadastrar_medicos",
            "titulo": "Cadastrar os médicos que vão prescrever",
            "de_quem": "hospital",
            "obrigatorio": True,
            "concluido": bool(assinantes) and not sem_dados_art2,
            "resumo": "Cada médico entra com nome, CPF, CRM, RQE quando "
                      "houver, e endereço profissional.",
            "como_fazer": [
                "Esses campos não são burocracia: o art. 2º exige que eles "
                "apareçam no documento emitido.",
                "Um hospital com 40 oncologistas cadastra 40 — a assinatura é "
                "de cada médico, não do hospital.",
            ],
            "base": "Resolução CFM 2.299/2021, art. 2º",
            "pendencias": ([] if assinantes else
                           ["Nenhum médico cadastrado."]) + (
                ["Sem CRM ou endereço: " + ", ".join(sem_dados_art2[:5])]
                if sem_dados_art2 else []),
        },
        {
            "id": "certificado_medico",
            "titulo": "Cada médico habilita o próprio certificado ICP-Brasil",
            "de_quem": "médico",
            "obrigatorio": True,
            "concluido": bool(prontos),
            "resumo": "O certificado é do médico, pessoa física, vinculado ao "
                      "CPF e ao CRM dele. Nem do hospital, nem de quem fornece "
                      "o software.",
            "como_fazer": [
                "Caminho recomendado: certificado em NUVEM. O VIDaaS é da "
                "própria CFM e já vem vinculado ao registro no CRM — muitos "
                "médicos já têm. O BirdID é a alternativa.",
                "Na nuvem a chave fica no cofre do provedor e o médico "
                "autoriza cada assinatura pelo celular: o sistema nunca vê a "
                "chave privada.",
                "Se o hospital já tem serviço próprio de assinatura, use a "
                "opção “API de assinatura do hospital” e informe a URL HTTPS.",
                "Arquivo A1 no servidor só em instalação dedicada: guardar o "
                "arquivo e a senha do médico equivale a guardar a identidade "
                "jurídica dele.",
            ],
            "base": "Resolução CFM 2.299/2021, art. 4º (ICP-Brasil, NGS2)",
            "pendencias": ([] if prontos else [
                "Nenhum certificado pronto para assinar."]),
        },
        {
            "id": "primeira_assinatura",
            "titulo": "Assinar um documento e conferir",
            "de_quem": "hospital",
            "obrigatorio": True,
            "concluido": ja_assinou,
            "resumo": "Emitir uma prescrição assinada e confirmar que ela "
                      "aparece como íntegra.",
            "como_fazer": [
                "Assine uma prescrição de teste e confira que o painel mostra "
                "“Documento íntegro”.",
                "Depois altere algo na prescrição: a assinatura tem de cair "
                "para inválida. É assim que se comprova que a garantia é real.",
                "Para validade perante terceiros, submeta a assinatura ao "
                "validador do ITI (validar.iti.gov.br) com um certificado "
                "ICP-Brasil de verdade.",
            ],
            "base": "Resolução CFM 2.299/2021, art. 4º, parágrafo único",
            "pendencias": [] if ja_assinou else [
                "Nenhum documento assinado ainda."],
        },
        {
            "id": "validacao_prescritor",
            "titulo": "Validação automática do prescritor no CFM",
            "de_quem": "hospital",
            "obrigatorio": False,
            "concluido": cfm_ws,
            "resumo": "Consulta automática ao Cadastro Nacional de Médicos "
                      "para confirmar que o prescritor está regular.",
            "como_fazer": [
                "O serviço é contratado e tarifado pelo CFM.",
                "Enquanto não houver, a regularidade do médico precisa ser "
                "conferida manualmente pelo hospital — o sistema não presume.",
            ],
            "base": "Resolução CFM 2.299/2021, art. 8º; Res. CFM 2.129/2015",
            "pendencias": [] if cfm_ws else [
                "Serviço do CFM não contratado/configurado."],
        },
        {
            "id": "eliminar_papel",
            "titulo": "Deixar de imprimir o prontuário (certificação NGS2)",
            "de_quem": "hospital",
            "obrigatorio": False,
            "concluido": False,
            "resumo": "Eliminar o papel exige sistema no Nível de Garantia de "
                      "Segurança 2, que é o nível que usa ICP-Brasil.",
            "como_fazer": [
                "Enquanto o sistema não estiver certificado em NGS2, o "
                "documento formal continua sendo a impressão assinada à mão.",
                "A certificação é do sistema, conduzida com a SBIS/CFM — fale "
                "com o fornecedor para saber o estágio.",
            ],
            "base": "Resolução CFM 1.821/2007, art. 4º; Manual SBIS/CFM",
            "pendencias": ["Certificação NGS2 não concluída."],
        },
        {
            "id": "sncr",
            "titulo": "Receituário de controlado eletrônico (SNCR)",
            "de_quem": "hospital",
            "obrigatorio": False,
            "concluido": False,
            "resumo": "Só necessário se o hospital quiser emitir receita de "
                      "controlado em meio eletrônico.",
            "como_fazer": [
                "Paciente INTERNADO não precisa de Notificação de Receita — a "
                "dispensação se faz com receita privativa do estabelecimento.",
                "A regra pega o que vai para casa: talidomida, tretinoína, "
                "opioides. Aí vale a RDC 1.000/2025 por inteiro.",
                "A emissão eletrônica é opcional. Mas se for eletrônica, "
                "precisa estar integrada ao SNCR — e sistema não integrado "
                "fica impedido de emitir.",
            ],
            "base": "RDC ANVISA 1.000/2025; Portaria SVS/MS 344/98",
            "pendencias": ["Integração com o SNCR não iniciada."],
        },
    ]

    # Um passo só libera depois do anterior: cadastrar certificado sem ter
    # cadastrado o médico não faz sentido, e mostrar tudo aberto de uma vez
    # faz o hospital começar pelo fim.
    liberado = True
    for p in passos:
        p["liberado"] = liberado or not p["obrigatorio"]
        if p["obrigatorio"] and not p["concluido"]:
            liberado = False

    return passos, {
        "assinantes": len(assinantes),
        "assinantes_prontos": len(prontos),
        "tem_certificado_institucional": tem_institucional,
    }


@api_requer_permissao_modulo("hospital.clinico")
def api_hospital_implantacao_assinatura(request):
    """GET /api/hospital/assinatura/implantacao — o caminho a seguir.

    Pensado para o hospital que acabou de contratar: mostra o que fazer, na
    ordem, de quem é cada passo e o que já está pronto.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    passos, resumo = _passos_implantacao(empresa)
    obrigatorios = [p for p in passos if p["obrigatorio"]]
    concluidos = [p for p in obrigatorios if p["concluido"]]
    proximo = next((p for p in obrigatorios if not p["concluido"]), None)

    return JsonResponse({
        "passos": passos,
        "total_obrigatorios": len(obrigatorios),
        "concluidos": len(concluidos),
        "percentual": (round(len(concluidos) / len(obrigatorios) * 100)
                       if obrigatorios else 100),
        "pronto_para_assinar": len(concluidos) == len(obrigatorios),
        "proximo_passo": proximo["id"] if proximo else None,
        "proximo_passo_titulo": proximo["titulo"] if proximo else None,
        **resumo,
        "quem_faz_o_que": {
            "hospital": "Registrar a responsabilidade técnica (inscrição no "
                        "CRM e Diretor Técnico, que o hospital já é obrigado a "
                        "ter) e cadastrar os médicos que prescrevem.",
            "medico": "Ter o próprio certificado ICP-Brasil, vinculado ao CPF "
                      "e ao CRM. O VIDaaS, da CFM, já é ligado ao registro.",
            "fornecedor_do_software": "Oferecer a estrutura: guardar os dados "
                                      "de cada cliente, assinar no padrão "
                                      "exigido e dizer o que falta. Não presta "
                                      "nem intermedeia assistência à saúde, "
                                      "então não se inscreve em conselho nem "
                                      "fornece certificado.",
        },
    })
