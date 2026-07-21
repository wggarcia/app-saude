"""
views_governo_pec.py
PEC — Prontuário Eletrônico do Cidadão / e-SUS Atenção Básica.
"""
import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_gerencia, api_requer_permissao_modulo,
    get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
)
from .models import ProntuarioCidadao, AtendimentoUBS
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .utils import validar_cpf_cadastro


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
@requer_permissao_modulo("governo.atencao_clinica")
def governo_pec_page(request):
    return render(request, "governo_pec.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_pec_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = date.today()
    total_pac = ProntuarioCidadao.objects.filter(empresa=e).count()
    atend_hoje = AtendimentoUBS.objects.filter(empresa=e, data_atendimento=hoje).count()
    nao_enviados = AtendimentoUBS.objects.filter(empresa=e, enviado_esus=False).count()
    total_atend = AtendimentoUBS.objects.filter(empresa=e).count()
    return JsonResponse({
        "total_pacientes": total_pac,
        "atendimentos_hoje": atend_hoje,
        "nao_enviados_esus": nao_enviados,
        "total_atendimentos": total_atend,
    })


# ── Pacientes ─────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_pec_lista(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    q = request.GET.get("q", "").strip()
    qs = ProntuarioCidadao.objects.filter(empresa=e)
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(nome_completo__icontains=q) | Q(cns__icontains=q) | Q(cpf__icontains=q))
    qs = qs[:100]
    return JsonResponse({"pacientes": [_pac_dict(p) for p in qs]})


@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_pec_novo(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf", ""), e)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    p = ProntuarioCidadao.objects.create(
        empresa=e,
        cns=data.get("cns", ""),
        cpf=data.get("cpf", ""),
        nome_completo=data.get("nome_completo", ""),
        data_nascimento=data.get("data_nascimento") or None,
        sexo=data.get("sexo", "M"),
        telefone=data.get("telefone", ""),
        unidade_saude=data.get("unidade_saude", ""),
        microarea=data.get("microarea", ""),
        acs_responsavel=data.get("acs_responsavel", ""),
        alergias=data.get("alergias", ""),
        condicoes_cronicas=data.get("condicoes_cronicas", ""),
    )
    return JsonResponse({"id": p.id, "nome_completo": p.nome_completo}, status=201)


@require_http_methods(["GET", "PUT"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_pec_detalhe(request, pac_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        p = ProntuarioCidadao.objects.get(pk=pac_id, empresa=e)
    except ProntuarioCidadao.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "GET":
        return JsonResponse(_pac_dict(p))
    data = json.loads(request.body or "{}")
    campos = ["cns", "cpf", "nome_completo", "sexo", "telefone", "unidade_saude",
              "microarea", "acs_responsavel", "alergias", "condicoes_cronicas"]
    for campo in campos:
        if campo in data:
            setattr(p, campo, data[campo])
    if "data_nascimento" in data:
        p.data_nascimento = data["data_nascimento"] or None
    p.save()
    return JsonResponse({"ok": True})


# ── Atendimentos ──────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_pec_atendimentos(request, pac_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        prontuario = ProntuarioCidadao.objects.get(pk=pac_id, empresa=e)
    except ProntuarioCidadao.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "GET":
        atends = AtendimentoUBS.objects.filter(empresa=e, prontuario=prontuario)
        return JsonResponse({"atendimentos": [_atend_dict(a) for a in atends]})
    data = json.loads(request.body or "{}")
    a = AtendimentoUBS.objects.create(
        empresa=e,
        prontuario=prontuario,
        paciente_nome=data.get("paciente_nome", prontuario.nome_completo),
        cns=data.get("cns", prontuario.cns),
        profissional=data.get("profissional", ""),
        cbo=data.get("cbo", ""),
        procedimento_ab=data.get("procedimento_ab", ""),
        cid10=data.get("cid10", ""),
        unidade_saude=data.get("unidade_saude", ""),
        turno=data.get("turno", "M"),
        data_atendimento=data.get("data_atendimento", str(date.today())),
        texto_evolucao=data.get("texto_evolucao", ""),
        enviado_esus=False,
    )
    return JsonResponse({"id": a.id}, status=201)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pac_dict(p):
    return {
        "id": p.id,
        "cns": p.cns,
        "cpf": p.cpf,
        "nome_completo": p.nome_completo,
        "data_nascimento": str(p.data_nascimento) if p.data_nascimento else "",
        "sexo": p.sexo,
        "telefone": p.telefone,
        "unidade_saude": p.unidade_saude,
        "microarea": p.microarea,
        "acs_responsavel": p.acs_responsavel,
        "alergias": p.alergias,
        "condicoes_cronicas": p.condicoes_cronicas,
        "criado_em": p.criado_em.isoformat(),
    }


def _atend_dict(a):
    return {
        "id": a.id,
        "paciente_nome": a.paciente_nome,
        "cns": a.cns,
        "profissional": a.profissional,
        "cbo": a.cbo,
        "procedimento_ab": a.procedimento_ab,
        "cid10": a.cid10,
        "unidade_saude": a.unidade_saude,
        "turno": a.turno,
        "turno_label": a.get_turno_display(),
        "data_atendimento": str(a.data_atendimento),
        "texto_evolucao": a.texto_evolucao,
        "enviado_esus": a.enviado_esus,
        "assinado_digitalmente": a.assinado_digitalmente,
        "assinado_digitalmente_em": a.assinado_digitalmente_em.isoformat() if a.assinado_digitalmente_em else None,
        "assinatura_hash": a.assinatura_hash,
        "assinatura_metodo": a.assinatura_metodo,
        "assinatura_profissional": a.assinatura_profissional,
        "criado_em": a.criado_em.isoformat(),
    }


# ── Assinatura digital do atendimento (ICP-Brasil / CFM 2.299/2021) ────────────

def _conteudo_canonical_atend(a):
    """Texto canônico do atendimento — qualquer alteração invalida a assinatura."""
    return "|".join([
        f"ATEND:{a.id}",
        f"PAC:{a.paciente_nome}",
        f"CNS:{a.cns}",
        f"PROF:{a.profissional}",
        f"CBO:{a.cbo}",
        f"PROC:{a.procedimento_ab}",
        f"CID:{a.cid10}",
        f"DATA:{a.data_atendimento}",
        f"EVOL:{a.texto_evolucao}",
    ])


@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_pec_assinar_atendimento(request, atend_id):
    """
    POST /api/governo/pec/atendimentos/<id>/assinar
    Body: {"crm_coren": "CRM/PR 12345", "senha_certificado": "opcional"}

    Assina o registro clínico com o certificado ICP-Brasil da secretaria
    (quando configurado em CredenciaisIntegracoes). Sem certificado, aplica
    assinatura funcional SHA-256 (integridade, sem validade jurídica plena).
    """
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        a = AtendimentoUBS.objects.get(id=atend_id, empresa=e)
    except AtendimentoUBS.DoesNotExist:
        return JsonResponse({"erro": "Atendimento não encontrado"}, status=404)

    if a.assinado_digitalmente:
        return JsonResponse({
            "aviso": "Atendimento já assinado digitalmente.",
            "assinado_em": a.assinado_digitalmente_em.isoformat() if a.assinado_digitalmente_em else None,
            "hash": a.assinatura_hash,
            "metodo": a.assinatura_metodo,
        })

    try:
        body = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    crm_coren = (body.get("crm_coren") or a.profissional or "").strip()
    senha_override = (body.get("senha_certificado") or "").strip()

    from .assinatura_digital import assinar_conteudo
    from .models import CredenciaisIntegracoes
    cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=e)

    conteudo = _conteudo_canonical_atend(a)
    ok, assinatura, hash_doc, metodo, erro = assinar_conteudo(conteudo, cred, crm_coren, senha_override)
    if not ok:
        return JsonResponse({"erro": f"Falha na assinatura: {erro}"}, status=422)

    a.assinatura_icp = assinatura
    a.assinatura_hash = hash_doc
    a.assinatura_metodo = metodo
    a.assinatura_profissional = crm_coren
    a.assinado_digitalmente = True
    a.assinado_digitalmente_em = timezone.now()
    a.save(update_fields=[
        "assinatura_icp", "assinatura_hash", "assinatura_metodo",
        "assinatura_profissional", "assinado_digitalmente", "assinado_digitalmente_em",
    ])

    return JsonResponse({
        "ok": True,
        "atendimento_id": a.id,
        "hash": hash_doc,
        "metodo": metodo,
        "assinado_em": a.assinado_digitalmente_em.isoformat(),
        "profissional": crm_coren,
        "aviso": (
            "Assinatura aplicada como hash SHA-256 (modo operacional). Para "
            "validade jurídica plena (CFM Res. 2.299/2021), configure o "
            "certificado ICP-Brasil em Configurações → Integrações → RNDS."
        ) if metodo == "SHA256" else None,
    })
