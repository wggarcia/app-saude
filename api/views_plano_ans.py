"""
Plano de Saúde — Obrigações ANS (DIOPS + SIB).
DIOPS: declaração trimestral de informações de saúde suplementar.
SIB:   sistema de informação de beneficiários (mensal).
"""
import json
import re
from datetime import date

from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .access_control import api_requer_gerencia, contexto_navegacao_setorial, requer_setor, requer_operacao_page, requer_permissao_modulo, get_setor
from .models import CredenciaisIntegracoes, DIOPSDeclaracao, SIBRegistro
from .views_dashboard import _empresa_autenticada
from .views_diops_real import gerar_diops_3_0


# ── helpers ──────────────────────────────────────────────────────────────────

def _ps_auth(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "plano_saude":
        return None, JsonResponse({"erro": "Módulo Plano de Saúde não disponível para este plano."}, status=403)
    return empresa, None


def _diops_dict(d):
    return {
        "id": d.id,
        "trimestre": d.trimestre,
        "registro_ans": d.registro_ans,
        "receita_operacional": float(d.receita_operacional),
        "despesa_assistencial": float(d.despesa_assistencial),
        "despesa_administrativa": float(d.despesa_administrativa),
        "resultado_periodo": float(d.resultado_periodo),
        "vidas_ativas": d.vidas_ativas,
        "status": d.status,
        "status_label": dict(DIOPSDeclaracao.STATUS_CHOICES).get(d.status, d.status),
        "xml_gerado": bool(d.xml_gerado),
        "enviado_em": d.enviado_em.strftime("%d/%m/%Y %H:%M") if d.enviado_em else None,
        "criado_em": d.criado_em.strftime("%d/%m/%Y"),
    }


def _sib_dict(s):
    return {
        "id": s.id,
        "competencia": s.competencia,
        "registro_ans": s.registro_ans,
        "vidas_incluidas": s.vidas_incluidas,
        "vidas_excluidas": s.vidas_excluidas,
        "vidas_alteradas": s.vidas_alteradas,
        "total_vidas": s.total_vidas,
        "enviado": s.enviado,
        "enviado_em": s.enviado_em.strftime("%d/%m/%Y %H:%M") if s.enviado_em else None,
        "criado_em": s.criado_em.strftime("%d/%m/%Y"),
    }



# ── page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.compliance_ans")
def plano_ans_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_ans_obrigacoes.html", ctx)


# ── API: DIOPS ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_diops_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = DIOPSDeclaracao.objects.filter(empresa=empresa)
        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        try:
            limit = min(max(int(request.GET.get("limit", 50)), 1), 200)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 50, 0
        total = qs.count()
        return JsonResponse({
            "declaracoes": [_diops_dict(d) for d in qs.order_by("-trimestre")[offset: offset + limit]],
            "total": total, "limit": limit, "offset": offset,
            "has_more": (offset + limit) < total,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        trimestre = (data.get("trimestre") or "").strip()
        if not trimestre:
            return JsonResponse({"erro": "trimestre obrigatório (AAAAQ)"}, status=400)
        if not re.fullmatch(r"\d{4}[1-4]", trimestre):
            return JsonResponse({"erro": "trimestre deve estar no formato AAAAQ, ex: 20242"}, status=400)

        # Validação ANS IN 77/2022
        from .models import DIOPSDeclaracao as _DIOPS
        _TIPOS_VALIDOS = {c[0] for c in _DIOPS.TIPO_OPERADORA_CHOICES} if hasattr(_DIOPS, "TIPO_OPERADORA_CHOICES") else set()
        _MODAL_VALIDOS = {c[0] for c in _DIOPS.MODALIDADE_CHOICES} if hasattr(_DIOPS, "MODALIDADE_CHOICES") else set()
        tipo_op = data.get("tipo_operadora", "1")
        modal_ass = data.get("modalidade_assistencial", "02")
        if _TIPOS_VALIDOS and tipo_op not in _TIPOS_VALIDOS:
            return JsonResponse({"erro": f"tipo_operadora inválido. Valores aceitos: {sorted(_TIPOS_VALIDOS)}"}, status=400)
        if _MODAL_VALIDOS and modal_ass not in _MODAL_VALIDOS:
            return JsonResponse({"erro": f"modalidade_assistencial inválida. Valores aceitos: {sorted(_MODAL_VALIDOS)}"}, status=400)

        d = DIOPSDeclaracao.objects.create(
            empresa=empresa,
            trimestre=trimestre,
            registro_ans=data.get("registro_ans", ""),
            receita_operacional=float(data.get("receita_operacional") or 0),
            despesa_assistencial=float(data.get("despesa_assistencial") or 0),
            despesa_administrativa=float(data.get("despesa_administrativa") or 0),
            resultado_periodo=float(data.get("resultado_periodo") or 0),
            vidas_ativas=int(data.get("vidas_ativas") or 0),
            tipo_operadora=tipo_op,
            modalidade_assistencial=modal_ass,
            status=data.get("status", "em_elaboracao"),
        )
        return JsonResponse({"declaracao": _diops_dict(d)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_diops_detalhe(request, decl_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        d = DIOPSDeclaracao.objects.get(id=decl_id, empresa=empresa)
    except DIOPSDeclaracao.DoesNotExist:
        return JsonResponse({"erro": "Declaração não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"declaracao": _diops_dict(d)})

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for field in ("registro_ans", "status"):
            if field in data:
                setattr(d, field, data[field])
        for field in ("receita_operacional", "despesa_assistencial", "despesa_administrativa", "resultado_periodo"):
            if field in data:
                setattr(d, field, float(data[field]))
        if "vidas_ativas" in data:
            d.vidas_ativas = int(data["vidas_ativas"])
        # Marcar como enviada
        if data.get("status") == "enviada" and not d.enviado_em:
            d.enviado_em = timezone.now()
        d.save()
        return JsonResponse({"declaracao": _diops_dict(d)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


def api_diops_gerar_xml(request, decl_id):
    """
    Gera e faz download do XML DIOPS 3.0 real (conforme IN ANS nº 77/2022).
    Usa gerar_diops_3_0 — mesmo gerador da transmissão real.
    GET /api/plano-saude/ans/diops/<id>/xml/
    """
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        d = DIOPSDeclaracao.objects.get(id=decl_id, empresa=empresa)
    except DIOPSDeclaracao.DoesNotExist:
        return JsonResponse({"erro": "Declaração não encontrada"}, status=404)

    if not re.fullmatch(r"\d{4}[1-4]", d.trimestre or ""):
        return JsonResponse(
            {"erro": f"Trimestre '{d.trimestre}' em formato inválido (esperado AAAAQ, ex: 20242)"},
            status=422,
        )

    xml_content = gerar_diops_3_0(d, empresa)
    d.xml_gerado = xml_content
    if d.status == "em_elaboracao":
        d.status = "validada"
    d.save()

    response = HttpResponse(xml_content, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="DIOPS_{d.trimestre}_{empresa.id}.xml"'
    return response


# ── API: SIB ─────────────────────────────────────────────────────────────────

@csrf_exempt
def api_sib_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method == "GET":
        qs = SIBRegistro.objects.filter(empresa=empresa)
        try:
            limit = min(max(int(request.GET.get("limit", 50)), 1), 200)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 50, 0
        total = qs.count()
        return JsonResponse({
            "registros": [_sib_dict(s) for s in qs.order_by("-competencia")[offset: offset + limit]],
            "total": total, "limit": limit, "offset": offset,
            "has_more": (offset + limit) < total,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        competencia = (data.get("competencia") or "").strip()
        if not competencia:
            return JsonResponse({"erro": "competencia obrigatória (AAAAMM)"}, status=400)
        incluidas = int(data.get("vidas_incluidas") or 0)
        excluidas = int(data.get("vidas_excluidas") or 0)
        alteradas = int(data.get("vidas_alteradas") or 0)
        total_vidas = int(data.get("total_vidas") or 0)
        s = SIBRegistro.objects.create(
            empresa=empresa,
            competencia=competencia,
            registro_ans=data.get("registro_ans", ""),
            vidas_incluidas=incluidas,
            vidas_excluidas=excluidas,
            vidas_alteradas=alteradas,
            total_vidas=total_vidas,
        )
        return JsonResponse({"registro": _sib_dict(s)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_sib_detalhe(request, sib_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        s = SIBRegistro.objects.get(id=sib_id, empresa=empresa)
    except SIBRegistro.DoesNotExist:
        return JsonResponse({"erro": "Registro SIB não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"registro": _sib_dict(s)})

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for field in ("vidas_incluidas", "vidas_excluidas", "vidas_alteradas", "total_vidas"):
            if field in data:
                setattr(s, field, int(data[field]))
        if "registro_ans" in data:
            s.registro_ans = data["registro_ans"]
        if data.get("enviado"):
            s.enviado = True
            s.enviado_em = timezone.now()
        s.save()
        return JsonResponse({"registro": _sib_dict(s)})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── API: SIB Transmissão ──────────────────────────────────────────────────────

_SIB_ENDPOINT = {
    "producao":    "https://sipweb.ans.gov.br/sipweb/sib/envio",
    "homologacao": "https://sipweb-hml.ans.gov.br/sipweb/sib/envio",
}


@csrf_exempt
def api_sib_transmitir(request, sib_id):
    """
    Transmite registro SIB ao webservice ANS SIPWeb.

    Com credenciais ANS configuradas: POST real ao SIPWeb (multipart/form-data).
    Sem credenciais: orienta configuração — NÃO marca como enviado.

    POST /api/plano-saude/ans/sib/<id>/transmitir/
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    empresa, err = _ps_auth(request)
    if err:
        return err

    # Rate limiting: max 1 transmissão SIB por registro por hora (evita DoS no SIPWeb ANS)
    rl_key = f"sib_transmit:{sib_id}"
    if cache.get(rl_key):
        return JsonResponse(
            {"erro": "Este registro SIB já foi transmitido recentemente. Aguarde 1 hora antes de retransmitir."},
            status=429,
        )
    cache.set(rl_key, True, timeout=3600)

    try:
        s = SIBRegistro.objects.get(id=sib_id, empresa=empresa)
    except SIBRegistro.DoesNotExist:
        return JsonResponse({"erro": "Registro SIB não encontrado"}, status=404)

    if s.enviado:
        return JsonResponse({"erro": "Registro já foi transmitido à ANS."}, status=400)

    cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    if not cred or not cred.ans_configurado():
        return JsonResponse({
            "ok":    False,
            "erro":  "Credenciais ANS SIPWeb não configuradas.",
            "instrucao": (
                "Configure usuário e senha ANS SIPWeb em "
                "POST /api/integracoes/credenciais/ans/ — "
                "credenciais obtidas diretamente na ANS pelo Registro de Operadora."
            ),
            "link": "/api/integracoes/credenciais/",
        }, status=400)

    try:
        import requests as req

        ambiente = cred.ans_ambiente or "homologacao"
        url      = _SIB_ENDPOINT.get(ambiente, _SIB_ENDPOINT["homologacao"])

        # Payload SIB conforme layout ANS
        payload = {
            "registroANS":    s.registro_ans or cred.ans_registro,
            "competencia":    s.competencia,
            "vidasIncluidas": s.vidas_incluidas,
            "vidasExcluidas": s.vidas_excluidas,
            "vidasAlteradas": s.vidas_alteradas,
            "totalVidas":     s.total_vidas,
        }

        resp = req.post(
            url,
            json=payload,
            auth=(cred.ans_usuario, cred.get_ans_senha()),
            timeout=60,
            verify=True,
        )

        retorno = {}
        try:
            retorno = resp.json()
        except Exception:
            retorno = {"texto": resp.text[:500]}

        if resp.status_code in (200, 201):
            s.enviado    = True
            s.enviado_em = timezone.now()
            s.retorno_ans = retorno
            s.save(update_fields=["enviado", "enviado_em", "retorno_ans"])

            # Atualiza data de última transmissão ANS
            cred.ans_ultima_transmissao = timezone.now()
            cred.save(update_fields=["ans_ultima_transmissao"])

            protocolo = retorno.get("protocolo") or retorno.get("nrProtocolo", "")
            return JsonResponse({
                "ok":         True,
                "sib_id":     s.id,
                "competencia": s.competencia,
                "protocolo":  protocolo,
                "modo":       "ans_real",
                "ambiente":   ambiente,
                "mensagem":   f"SIB {s.competencia} transmitido à ANS com sucesso.",
            })

        else:
            return JsonResponse({
                "ok":          False,
                "status_http": resp.status_code,
                "erro":        f"ANS SIPWeb retornou HTTP {resp.status_code}: {resp.text[:400]}",
                "retorno":     retorno,
            }, status=502)

    except Exception as ex:
        import logging
        logging.getLogger(__name__).exception("Erro ao transmitir SIB %s", s.id)
        return JsonResponse({"ok": False, "erro": str(ex)[:400]}, status=500)


# ── API: KPIs ANS ─────────────────────────────────────────────────────────────

def api_ans_kpis(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    hoje = date.today()
    mes_atual = hoje.strftime("%Y%m")

    # DIOPS — pendentes (em elaboração ou validadas, mas não enviadas)
    diops_pendentes = DIOPSDeclaracao.objects.filter(
        empresa=empresa,
        status__in=["em_elaboracao", "validada"],
    ).count()
    diops_enviadas = DIOPSDeclaracao.objects.filter(
        empresa=empresa, status="enviada"
    ).count()

    # SIB do mês atual
    sib_mes = SIBRegistro.objects.filter(
        empresa=empresa, competencia=mes_atual
    ).first()

    # Prazo próximo: DIOPS (até dia 30 do mês após o trimestre), SIB (dia 10)
    # Informamos como texto orientativo
    if hoje.day <= 10:
        prazo_sib = f"SIB vence dia 10/{hoje.month:02d}/{hoje.year} (hoje!)"
    else:
        proximo_mes = hoje.month % 12 + 1
        ano = hoje.year if proximo_mes > 1 else hoje.year + 1
        prazo_sib = f"SIB — próximo vence dia 10/{proximo_mes:02d}/{ano}"

    return JsonResponse({
        "diops_pendentes": diops_pendentes,
        "diops_enviadas": diops_enviadas,
        "sib_mes_atual": _sib_dict(sib_mes) if sib_mes else None,
        "sib_mes_enviado": sib_mes.enviado if sib_mes else False,
        "prazo_sib": prazo_sib,
        "info_prazos": {
            "diops": "Até dia 30 do mês seguinte ao trimestre de referência",
            "sib": "Até dia 10 do mês seguinte à competência",
        },
    })
