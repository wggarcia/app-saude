"""
views_governo_faturamento.py
Faturamento SUS — BPA / APAC / AIH.

Transmissão real ao DATASUS/SISAB via credenciais SCNES por empresa.

Quando credenciais SUS configuradas em CredenciaisIntegracoes:
  → transmissão real ao DATASUS via SISAB REST + login SCNES
Quando não configuradas:
  → modo registro local (lote salvo, aguardando credenciais)

Credenciais: nunca em settings globais — sempre por empresa no banco,
Fernet-encrypted. Configurar em POST /api/integracoes/credenciais/sus/

Ref: https://sisab.saude.gov.br/
     https://cnes.datasus.gov.br/
"""
import json
import logging
from datetime import date

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import get_setor, principal_pode_operacao_setorial
from .models import CredenciaisIntegracoes, FaturamentoSUSLote
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial
from .access_control import requer_setor, requer_operacao_page

logger = logging.getLogger(__name__)

# ── Endpoints DATASUS / SISAB ─────────────────────────────────────────────────
_SISAB_BPA = {
    "producao":    "https://sisab.saude.gov.br/api/v1/transmissao/bpa",
    "homologacao": "https://hom.sisab.saude.gov.br/api/v1/transmissao/bpa",
}


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
def governo_faturamento_sus_page(request):
    return render(request, "governo_faturamento_sus.html", contexto_navegacao_setorial(request, "governo"))


# ── KPIs ──────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_faturamento_sus_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    competencia_atual = hoje.strftime("%Y%m")
    qs = FaturamentoSUSLote.objects.filter(empresa=e, competencia=competencia_atual)
    total_registros = qs.aggregate(t=Sum("total_registros"))["t"] or 0
    total_aprovado  = qs.aggregate(t=Sum("total_aprovado"))["t"] or 0
    total_lotes     = qs.count()
    enviados        = qs.filter(enviado_cnes=True).count()

    cred   = CredenciaisIntegracoes.objects.filter(empresa=e).first()
    sus_ok = cred.sus_configurado() if cred else False

    return JsonResponse({
        "competencia_atual":       competencia_atual,
        "total_lotes":             total_lotes,
        "total_registros":         total_registros,
        "total_aprovado":          str(total_aprovado),
        "lotes_enviados":          enviados,
        "lotes_pendentes":         total_lotes - enviados,
        "sus_configurado":         sus_ok,
        "modo":                    "datasus_real" if sus_ok else "registro_local",
        "instrucao_configuracao":  (
            None if sus_ok else
            "Configure credenciais SCNES em POST /api/integracoes/credenciais/sus/"
        ),
    })


# ── Lotes ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def api_faturamento_sus_lotes(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        competencia = request.GET.get("competencia", "")
        qs = FaturamentoSUSLote.objects.filter(empresa=e)
        if competencia:
            qs = qs.filter(competencia=competencia)
        return JsonResponse({"lotes": [_lote_dict(l) for l in qs[:200]]})

    data = json.loads(request.body or "{}")
    lote = FaturamentoSUSLote.objects.create(
        empresa=e,
        competencia=data.get("competencia", ""),
        tipo=data.get("tipo", "bpa"),
        estabelecimento_cnes=data.get("estabelecimento_cnes", ""),
        total_registros=int(data.get("total_registros", 0)),
        total_aprovado=data.get("total_aprovado", 0) or 0,
        enviado_cnes=False,
    )
    return JsonResponse({"id": lote.id}, status=201)


# ── Transmitir ────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def api_faturamento_sus_transmitir(request, lote_id):
    """
    Transmite lote BPA/APAC/AIH ao DATASUS/SISAB.

    Com credenciais SCNES configuradas: transmissão real via SISAB REST API.
    Sem credenciais: orienta configuração — NÃO marca o lote como enviado.

    POST /api/governo/faturamento/<lote_id>/transmitir/
    """
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        lote = FaturamentoSUSLote.objects.get(pk=lote_id, empresa=e)
    except FaturamentoSUSLote.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado."}, status=404)

    if lote.enviado_cnes:
        return JsonResponse({"erro": "Lote já foi transmitido."}, status=400)

    cred = CredenciaisIntegracoes.objects.filter(empresa=e).first()
    if cred and cred.sus_configurado():
        return _transmitir_lote_datasus_real(e, lote, cred)
    else:
        return _transmitir_lote_registro_local(lote)


def _transmitir_lote_datasus_real(empresa, lote, cred):
    """
    Transmissão real ao SISAB (DATASUS) via SCNES.

    Usa credenciais por empresa armazenadas em CredenciaisIntegracoes
    (sus_login_scnes + Fernet-encrypted sus_senha_cripto).

    Endpoint: SISAB REST API v1 /transmissao/bpa
    Auth: HTTP Basic com login/senha SCNES do estabelecimento
    """
    try:
        import requests as req

        ambiente = cred.sus_ambiente or "producao"
        url      = _SISAB_BPA.get(ambiente, _SISAB_BPA["producao"])

        payload = {
            "cnes":                 cred.sus_cnes,
            "ibge":                 cred.sus_ibge or "",
            "uf":                   cred.sus_uf   or "",
            "competencia":          lote.competencia,
            "tipo":                 lote.tipo,
            "estabelecimento_cnes": lote.estabelecimento_cnes or cred.sus_cnes,
            "total_registros":      lote.total_registros,
        }

        resp = req.post(
            url,
            json=payload,
            auth=(cred.sus_login_scnes, cred.get_sus_senha()),
            timeout=60,
            verify=True,
        )

        if resp.status_code in (200, 201):
            protocolo = ""
            try:
                rdata     = resp.json()
                protocolo = (
                    rdata.get("protocolo")
                    or rdata.get("nrProtocolo")
                    or rdata.get("numero_protocolo", "")
                )
            except Exception:
                pass

            lote.enviado_cnes = True
            lote.save(update_fields=["enviado_cnes"])

            cred.sus_ultima_transmissao = timezone.now()
            if protocolo:
                cred.sus_ultimo_protocolo = str(protocolo)[:100]
            cred.save(update_fields=["sus_ultima_transmissao", "sus_ultimo_protocolo"])

            logger.info("SUS BPA lote %s transmitido — protocolo %s", lote.id, protocolo)
            return JsonResponse({
                "ok":        True,
                "lote_id":   lote.id,
                "protocolo": protocolo,
                "modo":      "datasus_real",
                "ambiente":  ambiente,
                "mensagem":  f"Lote {lote.competencia} transmitido ao DATASUS com sucesso.",
            })

        else:
            erro = f"DATASUS retornou HTTP {resp.status_code}: {resp.text[:500]}"
            logger.error("Erro SUS BPA lote %s: %s", lote.id, erro)
            return JsonResponse({"ok": False, "erro": erro}, status=502)

    except Exception as ex:
        msg = str(ex)[:500]
        logger.exception("Erro ao transmitir lote SUS %s: %s", lote.id, msg)
        return JsonResponse({"ok": False, "erro": msg}, status=500)


def _transmitir_lote_registro_local(lote):
    """Retorna erro orientando configuração — credenciais SCNES não configuradas."""
    return JsonResponse({
        "ok":       False,
        "lote_id":  lote.id,
        "modo":     "registro_local",
        "erro":     "Credenciais DATASUS/SCNES não configuradas.",
        "instrucao": (
            "Configure login SCNES do estabelecimento em "
            "POST /api/integracoes/credenciais/sus/ — "
            "credenciais obtidas junto ao DATASUS/CNES da sua Secretaria de Saúde."
        ),
        "link": "/api/integracoes/credenciais/",
    }, status=400)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lote_dict(l):
    return {
        "id":                    l.id,
        "competencia":           l.competencia,
        "tipo":                  l.tipo,
        "tipo_label":            l.get_tipo_display(),
        "estabelecimento_cnes":  l.estabelecimento_cnes,
        "total_registros":       l.total_registros,
        "total_aprovado":        str(l.total_aprovado),
        "enviado_cnes":          l.enviado_cnes,
        "criado_em":             l.criado_em.isoformat(),
    }
