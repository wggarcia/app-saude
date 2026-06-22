"""
Plano de Saúde — Portal do Beneficiário.
Admin: gerencia tokens de acesso dos beneficiários.
Público: página acessada via token, sem autenticação.
"""
import json
import secrets
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .access_control import contexto_navegacao_setorial, requer_setor, requer_operacao_page, requer_permissao_modulo
from .models import (
    BeneficiarioPlano, PortalBeneficiarioToken,
    RedeCredenciadaPlano, IAAutorizacaoGuia,
    GuiaAutorizacao,
)
from .views_dashboard import _empresa_autenticada


# ── helpers ──────────────────────────────────────────────────────────────────

def _ps_auth(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return empresa, None


def _gerar_token():
    return secrets.token_urlsafe(32)


def _benef_dict(b, token_obj=None):
    return {
        "id": b.id,
        "nome": b.nome,
        "cpf": b.cpf,
        "numero_carteirinha": b.numero_carteirinha,
        "plano_nome": b.plano.nome,
        "plano_tipo": b.plano_tipo,
        "situacao": b.situacao,
        "data_inicio_vigencia": b.data_inicio_vigencia.strftime("%d/%m/%Y") if b.data_inicio_vigencia else None,
        "data_fim_vigencia": b.data_fim_vigencia.strftime("%d/%m/%Y") if b.data_fim_vigencia else None,
        "portal_token": token_obj.token if token_obj else None,
        "portal_ativo": token_obj.ativo if token_obj else False,
        "portal_expira_em": token_obj.expira_em.strftime("%d/%m/%Y") if (token_obj and token_obj.expira_em) else None,
    }


# ── Admin page ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.autorizacao")
def plano_portal_admin_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_portal_admin.html", ctx)


# ── API: lista de beneficiários com status de acesso ─────────────────────────

def api_portal_beneficiarios_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "GET":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    # Busca todos os beneficiários da empresa (via planos da empresa)
    benefs = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa
    ).select_related("plano").prefetch_related("portal_token")

    busca = request.GET.get("q", "").strip()
    if busca:
        benefs = benefs.filter(nome__icontains=busca)

    tem_portal = request.GET.get("portal")
    if tem_portal == "1":
        benefs = benefs.filter(portal_token__ativo=True)
    elif tem_portal == "0":
        benefs = benefs.exclude(portal_token__ativo=True)

    result = []
    for b in benefs[:200]:
        token_obj = None
        try:
            token_obj = b.portal_token
        except PortalBeneficiarioToken.DoesNotExist:
            pass
        result.append(_benef_dict(b, token_obj))

    return JsonResponse({"beneficiarios": result})


# ── API: gerar token de acesso ────────────────────────────────────────────────

@csrf_exempt
def api_portal_token_gerar(request, benef_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    try:
        b = BeneficiarioPlano.objects.get(id=benef_id, plano__empresa=empresa)
    except BeneficiarioPlano.DoesNotExist:
        return JsonResponse({"erro": "Beneficiário não encontrado"}, status=404)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    validade_dias = int(data.get("validade_dias") or 365)
    expira_em = date.today() + timedelta(days=validade_dias)

    # Cria ou renova o token
    try:
        pt = b.portal_token
        pt.token = _gerar_token()
        pt.ativo = True
        pt.expira_em = expira_em
        pt.save()
    except PortalBeneficiarioToken.DoesNotExist:
        pt = PortalBeneficiarioToken.objects.create(
            beneficiario=b,
            token=_gerar_token(),
            ativo=True,
            expira_em=expira_em,
        )

    return JsonResponse({
        "token": pt.token,
        "portal_url": f"/beneficiario/{pt.token}/",
        "expira_em": pt.expira_em.strftime("%d/%m/%Y"),
        "beneficiario": _benef_dict(b, pt),
    }, status=201)


# ── Página pública do beneficiário ────────────────────────────────────────────

def plano_portal_beneficiario_page(request, token):
    """Página pública acessada via token — sem autenticação."""
    try:
        pt = PortalBeneficiarioToken.objects.select_related(
            "beneficiario__plano__empresa"
        ).get(token=token, ativo=True)
    except PortalBeneficiarioToken.DoesNotExist:
        return render(request, "plano_portal_beneficiario_invalido.html", {}, status=404)

    # Verifica expiração
    if pt.expira_em and pt.expira_em < date.today():
        return render(request, "plano_portal_beneficiario_invalido.html", {
            "motivo": "expirado"
        }, status=403)

    b = pt.beneficiario
    empresa = b.plano.empresa

    # Rede credenciada da empresa
    rede = RedeCredenciadaPlano.objects.filter(empresa=empresa, ativo=True)
    tipo_filtro = request.GET.get("tipo")
    cidade_filtro = request.GET.get("cidade", "").strip()
    if tipo_filtro:
        rede = rede.filter(tipo=tipo_filtro)
    if cidade_filtro:
        rede = rede.filter(cidade__icontains=cidade_filtro)

    # Autorizações recentes do beneficiário (pelo nome)
    autorizacoes = IAAutorizacaoGuia.objects.filter(
        empresa=empresa,
        beneficiario__icontains=b.nome.split()[0],  # busca pelo primeiro nome
    ).order_by("-criado_em")[:10]

    # Tipos disponíveis para filtro
    tipos_rede = list(
        RedeCredenciadaPlano.objects.filter(empresa=empresa, ativo=True)
        .values_list("tipo", flat=True)
        .distinct()
    )
    tipo_choices = {t: l for t, l in RedeCredenciadaPlano.TIPO_CHOICES}

    ctx = {
        "beneficiario": b,
        "plano": b.plano,
        "empresa": empresa,
        "rede": rede[:100],
        "autorizacoes": autorizacoes,
        "tipos_rede": [{"tipo": t, "label": tipo_choices.get(t, t)} for t in tipos_rede],
        "tipo_filtro": tipo_filtro or "",
        "cidade_filtro": cidade_filtro,
    }
    return render(request, "plano_portal_beneficiario.html", ctx)
