"""
views_plano_portal_prestador.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PORTAL DO PRESTADOR (self-service) — o prestador credenciado, sem depender da
operadora, faz por conta própria:
  • envia lote TISS (upload) — cai direto na recepção com glosa+IA;
  • acompanha status/glosa de cada lote;
  • baixa o Demonstrativo de Análise de Conta;
  • ABRE RECURSO DE GLOSA — e a IA pré-pontua o mérito (0-100) pra triagem.

Acesso por token público (sem login), igual ao portal do beneficiário. O lado
operadora tem o inbox de recursos com a triagem por IA e a resposta.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import secrets
from datetime import date
from decimal import Decimal

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    contexto_navegacao_setorial, requer_operacao_page, requer_permissao_modulo,
    requer_setor,
)
from .models import (
    ItemContaTISS, LoteTISSRecebido, PortalPrestadorToken, PrestadorPlanoSaude,
    RecursoGlosa,
)
from .views_dashboard import _empresa_autenticada
from .views_plano_saude import _ps_auth
from .views_plano_tiss_recepcao import (
    gerar_demonstrativo_retorno, importar_lote_tiss, processar_lote,
)


# ── auth por token público ───────────────────────────────────────────────────
def _token_prestador(token):
    try:
        pt = PortalPrestadorToken.objects.select_related("prestador__empresa").get(token=token, ativo=True)
    except PortalPrestadorToken.DoesNotExist:
        return None, None
    if pt.expira_em and pt.expira_em < date.today():
        return None, None
    return pt.prestador, pt.prestador.empresa


def _f(v):
    return float(v or 0)


# ── IA de mérito do recurso (0-100 = chance de a glosa estar errada) ─────────
_KW_FORTE = ("horário", "horario", "data diferente", "datas diferentes", "distinto",
             "distintas", "atendimentos separados", "prontuário", "prontuario",
             "laudo anexo", "autorização prévia", "autorizacao previa", "guia autorizada")
_KW_MEDIO = ("protocolo", "diretriz", "conforme", "urgência", "urgencia", "emergência",
             "emergencia", "justifica", "necessário", "necessario")


def _ia_merito_recurso(codigo_glosa: str, justificativa: str):
    j = (justificativa or "").lower()
    n_forte = sum(1 for k in _KW_FORTE if k in j)
    n_medio = sum(1 for k in _KW_MEDIO if k in j)
    base = {
        "1403": 55,  # duplicidade — frequentemente é atendimento distinto
        "1704": 45,  # quantidade — pode ter respaldo clínico
        "1707": 30,  # código inválido — geralmente é erro do prestador mesmo
        "1401": 15,  # não credenciado — fato contratual, recurso raramente procede
    }.get((codigo_glosa or "").strip(), 40)
    score = base + n_forte * 18 + n_medio * 7
    if len(j) < 25:
        score -= 15  # justificativa vazia/curta enfraquece o recurso
    score = int(max(0, min(100, score)))
    if score >= 65:
        parecer = ("Mérito ALTO — a justificativa traz elementos objetivos que contrapõem a glosa. "
                   "Priorizar análise; provável deferimento.")
    elif score >= 35:
        parecer = ("Mérito MÉDIO — há argumento, mas exige conferência de documentação (laudo/guia). "
                   "Analisar com evidências.")
    else:
        parecer = ("Mérito BAIXO — glosa provavelmente correta ou justificativa insuficiente. "
                   "Tende a indeferimento, salvo documento novo.")
    return score, parecer


# ═══════════════════ PORTAL PÚBLICO (token) ═══════════════════
def portal_prestador_page(request, token):
    prestador, empresa = _token_prestador(token)
    if not prestador:
        return render(request, "plano_portal_beneficiario_invalido.html",
                      {"motivo": "expirado"}, status=404)
    return render(request, "plano_portal_prestador.html", {
        "prestador": prestador, "empresa": empresa, "token": token,
    })


def _lote_pub(l: LoteTISSRecebido) -> dict:
    return {
        "id": l.id, "numero_lote": l.numero_lote, "beneficiario": l.beneficiario_nome,
        "guia": l.guia_numero, "status": l.status,
        "valor_apresentado": _f(l.valor_apresentado), "valor_glosado": _f(l.valor_glosado),
        "valor_liberado": _f(l.valor_liberado), "ia_score_glosa": l.ia_score_glosa,
        "recebido_em": l.recebido_em.strftime("%d/%m/%Y"),
    }


@require_http_methods(["GET"])
def api_pp_dados(request, token):
    prestador, empresa = _token_prestador(token)
    if not prestador:
        return JsonResponse({"erro": "Token inválido ou expirado"}, status=403)
    lotes = LoteTISSRecebido.objects.filter(empresa=empresa, prestador=prestador)[:200]
    recursos = RecursoGlosa.objects.filter(empresa=empresa, prestador=prestador)[:100]
    return JsonResponse({
        "prestador": {"nome": prestador.nome_fantasia, "codigo": prestador.codigo_rede,
                      "status": prestador.status},
        "lotes": [_lote_pub(l) for l in lotes],
        "recursos": [{
            "id": r.id, "lote": r.lote_id, "codigo_glosa": r.codigo_glosa,
            "valor_contestado": _f(r.valor_contestado), "valor_deferido": _f(r.valor_deferido),
            "status": r.status, "criado_em": r.criado_em.strftime("%d/%m/%Y"),
            "resposta": r.resposta_operadora,
        } for r in recursos],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_pp_enviar_lote(request, token):
    prestador, empresa = _token_prestador(token)
    if not prestador:
        return JsonResponse({"erro": "Token inválido ou expirado"}, status=403)
    if prestador.status not in ("credenciado", "implantacao"):
        return JsonResponse({"erro": "Prestador não está ativo para envio de lotes."}, status=403)
    xml_str = request.body.decode("utf-8", "ignore") if request.body else ""
    if "mensagemTISS" not in xml_str:
        return JsonResponse({"erro": "XML TISS inválido ou vazio"}, status=400)
    try:
        lote = importar_lote_tiss(xml_str, empresa)
        # ISOLAMENTO: o lote pertence obrigatoriamente ao prestador do token,
        # independente do que o XML declara.
        lote.prestador = prestador
        lote.prestador_nome = prestador.nome_fantasia
        lote.prestador_codigo = prestador.codigo_rede or lote.prestador_codigo
        lote.save(update_fields=["prestador", "prestador_nome", "prestador_codigo"])
        processar_lote(lote)
    except Exception as e:  # noqa: BLE001
        return JsonResponse({"erro": f"Falha ao processar lote: {e}"}, status=400)
    return JsonResponse({"ok": True, "lote": _lote_pub(lote)})


@require_http_methods(["GET"])
def api_pp_lote_detalhe(request, token, lote_id):
    prestador, empresa = _token_prestador(token)
    if not prestador:
        return JsonResponse({"erro": "Token inválido ou expirado"}, status=403)
    try:
        lote = LoteTISSRecebido.objects.get(id=lote_id, empresa=empresa, prestador=prestador)
    except LoteTISSRecebido.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)
    itens = [{
        "id": it.id, "sequencial": it.sequencial, "codigo": it.codigo_procedimento,
        "descricao": it.descricao, "valor_apresentado": _f(it.valor_apresentado),
        "valor_glosado": _f(it.valor_glosado), "glosado": it.glosado,
        "codigo_glosa": it.codigo_glosa, "motivo_glosa": it.motivo_glosa,
    } for it in lote.itens.all()]
    return JsonResponse({"lote": _lote_pub(lote), "itens": itens})


@require_http_methods(["GET"])
def api_pp_demonstrativo(request, token, lote_id):
    prestador, empresa = _token_prestador(token)
    if not prestador:
        return JsonResponse({"erro": "Token inválido ou expirado"}, status=403)
    try:
        lote = LoteTISSRecebido.objects.get(id=lote_id, empresa=empresa, prestador=prestador)
    except LoteTISSRecebido.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)
    xml_out = gerar_demonstrativo_retorno(lote)
    resp = HttpResponse(xml_out, content_type="application/xml; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="demonstrativo_lote_{lote.id}.xml"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def api_pp_abrir_recurso(request, token):
    prestador, empresa = _token_prestador(token)
    if not prestador:
        return JsonResponse({"erro": "Token inválido ou expirado"}, status=403)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    lote_id = body.get("lote_id")
    item_id = body.get("item_id")
    justificativa = (body.get("justificativa") or "").strip()
    if not lote_id or not justificativa:
        return JsonResponse({"erro": "Informe lote_id e justificativa"}, status=400)
    try:
        lote = LoteTISSRecebido.objects.get(id=lote_id, empresa=empresa, prestador=prestador)
    except LoteTISSRecebido.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)
    item = None
    if item_id:
        item = ItemContaTISS.objects.filter(id=item_id, lote=lote).first()
    codigo_glosa = (item.codigo_glosa if item else "") or ""
    valor_contestado = (item.valor_glosado if item else lote.valor_glosado) or Decimal("0")
    if valor_contestado <= 0:
        return JsonResponse({"erro": "Não há valor glosado para contestar neste item/lote."}, status=400)
    score, parecer = _ia_merito_recurso(codigo_glosa, justificativa)
    rec = RecursoGlosa.objects.create(
        empresa=empresa, lote=lote, item=item, prestador=prestador,
        codigo_glosa=codigo_glosa, valor_contestado=valor_contestado,
        justificativa=justificativa[:4000], ia_merito_score=score, ia_merito_parecer=parecer,
        status="aberto",
    )
    return JsonResponse({"ok": True, "recurso": {"id": rec.id, "status": rec.status,
                                                 "ia_merito_score": score}})


# ═══════════════════ LADO OPERADORA ═══════════════════
@csrf_exempt
@require_http_methods(["POST"])
def api_pp_token_gerar(request, prestador_id):
    """Gera/rotaciona o token de portal de um prestador (dono)."""
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        prestador = PrestadorPlanoSaude.objects.get(id=prestador_id, empresa=empresa)
    except PrestadorPlanoSaude.DoesNotExist:
        return JsonResponse({"erro": "Prestador não encontrado"}, status=404)
    token = secrets.token_urlsafe(32)
    pt, _created = PortalPrestadorToken.objects.update_or_create(
        prestador=prestador, defaults={"token": token, "ativo": True},
    )
    url = request.build_absolute_uri(f"/portal-prestador/{pt.token}/")
    return JsonResponse({"ok": True, "token": pt.token, "url": url})


def _recurso_dict(r: RecursoGlosa) -> dict:
    return {
        "id": r.id, "prestador": r.prestador.nome_fantasia if r.prestador else "",
        "lote": r.lote_id, "numero_lote": r.lote.numero_lote,
        "beneficiario": r.lote.beneficiario_nome, "codigo_glosa": r.codigo_glosa,
        "motivo": (r.item.motivo_glosa if r.item else ""),
        "valor_contestado": _f(r.valor_contestado), "valor_deferido": _f(r.valor_deferido),
        "justificativa": r.justificativa, "ia_merito_score": r.ia_merito_score,
        "ia_merito_parecer": r.ia_merito_parecer, "status": r.status,
        "resposta_operadora": r.resposta_operadora,
        "criado_em": r.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


@require_http_methods(["GET"])
def api_recursos_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    qs = RecursoGlosa.objects.select_related("lote", "item", "prestador").filter(empresa=empresa)
    st = request.GET.get("status")
    if st:
        qs = qs.filter(status=st)
    # ordena por mérito IA desc dentro dos abertos (triagem)
    abertos = sorted([r for r in qs[:300] if r.status in ("aberto", "em_analise")],
                     key=lambda r: -r.ia_merito_score)
    outros = [r for r in qs[:300] if r.status not in ("aberto", "em_analise")]
    return JsonResponse({"recursos": [_recurso_dict(r) for r in abertos + outros]})


@csrf_exempt
@require_http_methods(["POST"])
def api_recurso_responder(request, recurso_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        rec = RecursoGlosa.objects.select_related("lote", "item").get(id=recurso_id, empresa=empresa)
    except RecursoGlosa.DoesNotExist:
        return JsonResponse({"erro": "Recurso não encontrado"}, status=404)
    if rec.status in ("deferido", "parcial", "indeferido"):
        return JsonResponse({"erro": "Recurso já respondido."}, status=400)
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    decisao = body.get("decisao")
    resposta = (body.get("resposta") or "").strip()
    if decisao not in ("deferido", "parcial", "indeferido"):
        return JsonResponse({"erro": "decisao inválida (deferido/parcial/indeferido)"}, status=400)
    valor_def = Decimal("0")
    if decisao == "deferido":
        valor_def = rec.valor_contestado
    elif decisao == "parcial":
        try:
            valor_def = Decimal(str(body.get("valor_deferido", "0"))).quantize(Decimal("0.01"))
        except Exception:  # noqa: BLE001
            return JsonResponse({"erro": "valor_deferido inválido"}, status=400)
        if valor_def <= 0 or valor_def >= rec.valor_contestado:
            return JsonResponse({"erro": "valor_deferido deve ser >0 e < contestado"}, status=400)
    # deferimento devolve valor à conta (reduz glosa do lote e libera)
    if valor_def > 0:
        lote = rec.lote
        lote.valor_glosado = max(Decimal("0"), lote.valor_glosado - valor_def)
        lote.valor_liberado = lote.valor_apresentado - lote.valor_glosado
        lote.save(update_fields=["valor_glosado", "valor_liberado"])
        if rec.item:
            rec.item.valor_glosado = max(Decimal("0"), rec.item.valor_glosado - valor_def)
            rec.item.valor_liberado = rec.item.valor_apresentado - rec.item.valor_glosado
            rec.item.glosado = rec.item.valor_glosado > 0
            rec.item.save(update_fields=["valor_glosado", "valor_liberado", "glosado"])
    rec.valor_deferido = valor_def
    rec.status = decisao
    rec.resposta_operadora = resposta[:4000]
    rec.respondido_em = timezone.now()
    rec.save(update_fields=["valor_deferido", "status", "resposta_operadora", "respondido_em"])
    return JsonResponse({"ok": True, "recurso": _recurso_dict(rec)})


# ── page operadora (gerar link do prestador + inbox de recursos) ─────────────
@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.rede_credenciada")
def plano_portal_prestador_admin_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    ctx["prestadores"] = PrestadorPlanoSaude.objects.filter(empresa=empresa)[:500]
    return render(request, "plano_portal_prestador_admin.html", ctx)
