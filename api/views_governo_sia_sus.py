"""
views_governo_sia_sus.py
SIA/SUS — Validação e Transmissão Formal de BPA-C e BPA-I ao DATASUS/SISAB.

Complementa views_governo_faturamento.py com fluxo formal SIA/SUS:
  validação SIGTAP + CID + CNS antes da transmissão;
  transmissão real quando CredenciaisIntegracoes.sus_configurado();
  gravação de lote como "pendente" quando credenciais ausentes.

Endpoints:
  GET  /api/governo/sia-sus/status
  GET  /api/governo/sia-sus/competencia/<comp>
  POST /api/governo/sia-sus/validar
  POST /api/governo/sia-sus/transmitir
  GET  /api/governo/sia-sus/historico
  POST /api/governo/sia-sus/reprocessar/<int:lote_id>

Auth: _gov(request) — empresa governo autenticada + operação setorial.

Refs:
  https://sisab.saude.gov.br/
  https://cnes.datasus.gov.br/
  https://sigtap.datasus.gov.br/
"""
import json
import logging
from datetime import date

from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_permissao_modulo,
    get_setor,
    principal_pode_operacao_setorial,
)
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)

# ── Endpoints SISAB ───────────────────────────────────────────────────────────
_SISAB_BPA = {
    "producao":    "https://sisab.saude.gov.br/api/v1/transmissao/bpa",
    "homologacao": "https://hom.sisab.saude.gov.br/api/v1/transmissao/bpa",
}

# ── Imports opcionais de models ───────────────────────────────────────────────
try:
    from .models import CredenciaisIntegracoes
except ImportError:
    CredenciaisIntegracoes = None  # type: ignore[assignment,misc]

try:
    from .models import FaturamentoSUSLote
except ImportError:
    FaturamentoSUSLote = None  # type: ignore[assignment,misc]

try:
    from .models import ProcedimentoSIGTAP
except ImportError:
    ProcedimentoSIGTAP = None  # type: ignore[assignment,misc]

try:
    from .models import ProcedimentoSIGTAPCID
except ImportError:
    ProcedimentoSIGTAPCID = None  # type: ignore[assignment,misc]


# ── Auth helper ───────────────────────────────────────────────────────────────

def _gov(request):
    """Retorna empresa governo autenticada ou None."""
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ── CNS — validação de formato (algoritmo Módulo 11 DATASUS) ─────────────────

def _cns_valido(cns: str) -> bool:
    """
    Valida o Cartão Nacional de Saúde (CNS) pelo algoritmo oficial DATASUS.

    CNS definitivo: começa com 1 ou 2.
    CNS provisório: começa com 7, 8 ou 9.
    Ambos devem ter 15 dígitos e passar a verificação de módulo 11.
    """
    cns = (cns or "").strip().replace(" ", "")
    if len(cns) != 15 or not cns.isdigit():
        return False
    if cns[0] not in ("1", "2", "7", "8", "9"):
        return False

    # Verificação pelo somatório ponderado (peso 15..1) mod 11 == 0
    soma = sum(int(cns[i]) * (15 - i) for i in range(15))
    return soma % 11 == 0


# ── Helpers de serialização ───────────────────────────────────────────────────

def _lote_dict(lote) -> dict:
    d = {
        "id":                   lote.id,
        "competencia":          lote.competencia,
        "tipo":                 lote.tipo,
        "tipo_label":           lote.get_tipo_display(),
        "estabelecimento_cnes": lote.estabelecimento_cnes,
        "total_registros":      lote.total_registros,
        "total_aprovado":       str(lote.total_aprovado),
        "enviado_cnes":         lote.enviado_cnes,
        "criado_em":            lote.criado_em.isoformat(),
    }
    # Campos extras opcionais que podem existir no model estendido
    for campo in ("status", "motivo_pendencia", "protocolo_sisab", "erro_transmissao"):
        if hasattr(lote, campo):
            valor = getattr(lote, campo)
            d[campo] = valor.isoformat() if hasattr(valor, "isoformat") else valor
    return d


def _competencia_para_yyyymm(comp: str) -> str:
    """
    Aceita 'YYYY-MM' ou 'YYYYMM' e retorna sempre 'YYYYMM'.
    Levanta ValueError para formato inválido.
    """
    comp = (comp or "").strip()
    if len(comp) == 7 and comp[4] == "-":
        ano, mes = comp[:4], comp[5:]
        return f"{ano}{mes}"
    if len(comp) == 6 and comp.isdigit():
        return comp
    raise ValueError(f"Competência inválida: '{comp}'. Use YYYY-MM ou YYYYMM.")


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── GET /api/governo/sia-sus/status ──────────────────────────────────────────

@require_http_methods(["GET"])
def api_sia_sus_status(request):
    """
    Status das credenciais SISAB e informação da última transmissão BPA.

    Resposta:
      sus_configurado      bool
      cnes                 str
      ambiente             str  (producao | homologacao)
      ultima_transmissao   str|null  ISO-8601
      ultimo_protocolo     str
      modo                 str  (sisab_real | pendente_credenciais)
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if CredenciaisIntegracoes is None:
        return JsonResponse({"erro": "Módulo de credenciais indisponível"}, status=503)

    cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    sus_ok = cred.sus_configurado() if cred else False

    ultima_tx = None
    ultimo_prot = ""
    ambiente = "homologacao"
    cnes = ""

    if cred:
        ultima_tx   = cred.sus_ultima_transmissao.isoformat() if cred.sus_ultima_transmissao else None
        ultimo_prot = cred.sus_ultimo_protocolo or ""
        ambiente    = cred.sus_ambiente or "homologacao"
        cnes        = cred.sus_cnes or ""

    return JsonResponse({
        "sus_configurado":    sus_ok,
        "cnes":               cnes,
        "ambiente":           ambiente,
        "ultima_transmissao": ultima_tx,
        "ultimo_protocolo":   ultimo_prot,
        "modo":               "sisab_real" if sus_ok else "pendente_credenciais",
        "instrucao": (
            None if sus_ok else
            "Configure credenciais SCNES em POST /api/integracoes/credenciais/sus/"
        ),
    })


# ── GET /api/governo/sia-sus/competencia/<comp> ───────────────────────────────

@require_http_methods(["GET"])
def api_sia_sus_competencia(request, comp):
    """
    Resumo de produção para a competência YYYY-MM.

    Resposta:
      competencia       str  YYYYMM
      total_bpa_i       int
      total_bpa_c       int
      total_lotes       int
      total_registros   int
      total_aprovado    str  (Decimal como string)
      lotes_enviados    int
      lotes_pendentes   int
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if FaturamentoSUSLote is None:
        return JsonResponse({"erro": "Módulo de faturamento indisponível"}, status=503)

    try:
        competencia_mm = _competencia_para_yyyymm(comp)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=400)

    qs = FaturamentoSUSLote.objects.filter(empresa=empresa, competencia=competencia_mm)

    agregado = qs.aggregate(
        total_reg=Sum("total_registros"),
        total_apr=Sum("total_aprovado"),
    )

    # BPA-I e BPA-C são tipos distintos dentro do lote; filtra pelo campo `tipo`
    # Convenção vigente no model: tipo "bpa" abrange ambos — se houver tipos
    # separados ("bpa_i", "bpa_c") eles são contados individualmente.
    total_bpa_i = qs.filter(tipo__icontains="bpa_i").count()
    total_bpa_c = qs.filter(tipo__icontains="bpa_c").count()
    # Fallback: se ambos zerem, conta lotes tipo "bpa" genérico como BPA-C
    if total_bpa_i == 0 and total_bpa_c == 0:
        total_bpa_c = qs.filter(tipo="bpa").count()

    total_lotes    = qs.count()
    lotes_enviados = qs.filter(enviado_cnes=True).count()

    return JsonResponse({
        "competencia":      competencia_mm,
        "total_bpa_i":      total_bpa_i,
        "total_bpa_c":      total_bpa_c,
        "total_lotes":      total_lotes,
        "total_registros":  agregado["total_reg"] or 0,
        "total_aprovado":   str(agregado["total_apr"] or 0),
        "lotes_enviados":   lotes_enviados,
        "lotes_pendentes":  total_lotes - lotes_enviados,
    })


# ── POST /api/governo/sia-sus/validar ────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_sia_sus_validar(request):
    """
    Valida lista de procedimentos antes de transmitir ao SISAB.

    Body JSON:
      {
        "procedimentos": [
          {
            "codigo_sigtap": "0101010010",   # obrigatório
            "cid":           "J180",         # opcional
            "cns_profissional": "700000000000000"  # opcional
          },
          ...
        ]
      }

    Resposta:
      {
        "valido": bool,
        "total":  int,
        "erros":  int,
        "itens": [
          {
            "index": 0,
            "codigo_sigtap": "...",
            "valido": bool,
            "erros": ["descrição do erro", ...]
          },
          ...
        ]
      }
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    procedimentos = data.get("procedimentos")
    if not isinstance(procedimentos, list) or not procedimentos:
        return JsonResponse({"erro": "'procedimentos' deve ser uma lista não vazia"}, status=400)

    if len(procedimentos) > 500:
        return JsonResponse({"erro": "Máximo de 500 procedimentos por requisição"}, status=400)

    if ProcedimentoSIGTAP is None or ProcedimentoSIGTAPCID is None:
        return JsonResponse({"erro": "Módulo SIGTAP indisponível"}, status=503)

    # Pré-carrega todos os códigos solicitados de uma vez para eficiência
    codigos_solicitados = {
        str(p.get("codigo_sigtap", "")).strip()
        for p in procedimentos
        if p.get("codigo_sigtap")
    }
    sigtap_map = {
        proc.codigo: proc
        for proc in ProcedimentoSIGTAP.objects.filter(
            codigo__in=codigos_solicitados, ativo=True
        ).prefetch_related("cids")
    }

    itens = []
    total_erros = 0

    for idx, item in enumerate(procedimentos):
        codigo = str(item.get("codigo_sigtap", "")).strip()
        cid    = str(item.get("cid", "")).strip().upper().replace(".", "")
        cns    = str(item.get("cns_profissional", "")).strip()
        erros_item = []

        # 1. Código SIGTAP presente e com 10 dígitos
        if not codigo:
            erros_item.append("codigo_sigtap é obrigatório")
        elif len(codigo) != 10 or not codigo.isdigit():
            erros_item.append(f"Código SIGTAP deve ter 10 dígitos numéricos (recebido: '{codigo}')")
        else:
            proc_obj = sigtap_map.get(codigo)
            if proc_obj is None:
                erros_item.append(f"Código SIGTAP '{codigo}' não encontrado na tabela vigente")
            else:
                # 2. CID compatível com o procedimento (se informado)
                if cid:
                    cids_validos = {c.cid for c in proc_obj.cids.all()}
                    if cids_validos and cid not in cids_validos:
                        erros_item.append(
                            f"CID '{cid}' não é compatível com o procedimento '{codigo}' no SIGTAP"
                        )

        # 3. CNS do profissional (se informado)
        if cns and not _cns_valido(cns):
            erros_item.append(f"CNS do profissional '{cns}' inválido (formato ou dígito verificador)")

        valido_item = len(erros_item) == 0
        if not valido_item:
            total_erros += 1

        itens.append({
            "index":          idx,
            "codigo_sigtap":  codigo,
            "cid":            cid or None,
            "cns_profissional": cns or None,
            "valido":         valido_item,
            "erros":          erros_item,
        })

    return JsonResponse({
        "valido": total_erros == 0,
        "total":  len(itens),
        "erros":  total_erros,
        "itens":  itens,
    })


# ── POST /api/governo/sia-sus/transmitir ─────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_sia_sus_transmitir(request):
    """
    Transmite BPA da competência ao SISAB.

    Body JSON:
      {
        "competencia":          "2026-01",          # YYYY-MM ou YYYYMM — obrigatório
        "tipo":                 "bpa",              # opcional, default "bpa"
        "estabelecimento_cnes": "1234567",           # opcional, usa cred.sus_cnes se ausente
        "total_registros":      42,                 # opcional
        "procedimentos":        [...]               # opcional — lista para transmissão
      }

    Comportamento:
      - CredenciaisIntegracoes.sus_configurado() → POST real ao SISAB.
      - Credenciais ausentes → salva lote como "pendente" com motivo.

    Resposta de sucesso (transmissão real):
      { "ok": true, "lote_id": int, "protocolo": str, "modo": "sisab_real" }

    Resposta de pendência:
      { "ok": false, "lote_id": int, "modo": "pendente_credenciais", "motivo": str }
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if FaturamentoSUSLote is None or CredenciaisIntegracoes is None:
        return JsonResponse({"erro": "Módulo de faturamento/credenciais indisponível"}, status=503)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    comp_raw = data.get("competencia", "")
    if not comp_raw:
        return JsonResponse({"erro": "'competencia' é obrigatório"}, status=400)

    try:
        competencia_mm = _competencia_para_yyyymm(comp_raw)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=400)

    tipo              = str(data.get("tipo", "bpa")).strip() or "bpa"
    total_registros   = int(data.get("total_registros", 0) or 0)
    estab_cnes        = str(data.get("estabelecimento_cnes", "") or "").strip()

    cred   = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    sus_ok = cred.sus_configurado() if cred else False

    # Usa CNES das credenciais como fallback
    if not estab_cnes and cred:
        estab_cnes = cred.sus_cnes or ""

    # Cria o lote de faturamento
    lote = FaturamentoSUSLote.objects.create(
        empresa=empresa,
        competencia=competencia_mm,
        tipo=tipo,
        estabelecimento_cnes=estab_cnes,
        total_registros=total_registros,
        total_aprovado=0,
        enviado_cnes=False,
    )

    if sus_ok:
        return _transmitir_bpa_sisab(empresa, lote, cred, data.get("procedimentos") or [])
    else:
        return _salvar_lote_pendente(lote)


def _transmitir_bpa_sisab(empresa, lote, cred, procedimentos: list):
    """
    Transmissão real ao SISAB (DATASUS) via SCNES.

    Monta payload BPA e faz POST autenticado com login/senha SCNES.
    Atualiza lote e credenciais em caso de sucesso.
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
            "procedimentos":        procedimentos,
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

            logger.info(
                "SIA/SUS BPA lote %s (comp %s) transmitido — protocolo %s",
                lote.id, lote.competencia, protocolo,
            )
            return JsonResponse({
                "ok":        True,
                "lote_id":   lote.id,
                "protocolo": protocolo,
                "modo":      "sisab_real",
                "ambiente":  ambiente,
                "mensagem":  (
                    f"BPA competência {lote.competencia} transmitido ao SISAB com sucesso."
                ),
            })

        erro = f"SISAB retornou HTTP {resp.status_code}: {resp.text[:500]}"
        logger.error("Erro SIA/SUS BPA lote %s: %s", lote.id, erro)
        return JsonResponse({"ok": False, "lote_id": lote.id, "erro": erro}, status=502)

    except Exception as exc:
        msg = str(exc)[:500]
        logger.exception("Erro ao transmitir lote SIA/SUS %s: %s", lote.id, msg)
        return JsonResponse({"ok": False, "lote_id": lote.id, "erro": msg}, status=500)


def _salvar_lote_pendente(lote):
    """
    Credenciais não configuradas — salva lote como pendente e orienta o operador.
    NÃO marca o lote como enviado.
    """
    motivo = "credenciais não configuradas"
    logger.warning(
        "SIA/SUS BPA lote %s salvo como pendente — %s", lote.id, motivo
    )
    return JsonResponse({
        "ok":      False,
        "lote_id": lote.id,
        "modo":    "pendente_credenciais",
        "motivo":  motivo,
        "erro": (
            "Credenciais DATASUS/SCNES não configuradas para este estabelecimento."
        ),
        "instrucao": (
            "Configure login SCNES do estabelecimento em "
            "POST /api/integracoes/credenciais/sus/ — "
            "credenciais obtidas junto ao DATASUS/CNES da sua Secretaria de Saúde."
        ),
        "link": "/api/integracoes/credenciais/",
    }, status=202)


# ── GET /api/governo/sia-sus/historico ───────────────────────────────────────

@require_http_methods(["GET"])
def api_sia_sus_historico(request):
    """
    Histórico de FaturamentoSUSLote com status e erros.

    Query params opcionais:
      competencia  YYYYMM ou YYYY-MM
      tipo         bpa | apac | aih
      enviado      true | false
      page         int (default 1)
      page_size    int (default 50, max 200)

    Resposta:
      { "total": int, "page": int, "pages": int, "lotes": [...] }
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if FaturamentoSUSLote is None:
        return JsonResponse({"erro": "Módulo de faturamento indisponível"}, status=503)

    qs = FaturamentoSUSLote.objects.filter(empresa=empresa)

    # Filtros opcionais
    comp_raw = request.GET.get("competencia", "").strip()
    if comp_raw:
        try:
            qs = qs.filter(competencia=_competencia_para_yyyymm(comp_raw))
        except ValueError as exc:
            return JsonResponse({"erro": str(exc)}, status=400)

    tipo = request.GET.get("tipo", "").strip()
    if tipo:
        qs = qs.filter(tipo=tipo)

    enviado_str = request.GET.get("enviado", "").strip().lower()
    if enviado_str == "true":
        qs = qs.filter(enviado_cnes=True)
    elif enviado_str == "false":
        qs = qs.filter(enviado_cnes=False)

    # Paginação
    try:
        page      = max(1, int(request.GET.get("page", 1)))
        page_size = min(200, max(1, int(request.GET.get("page_size", 50))))
    except (ValueError, TypeError):
        return JsonResponse({"erro": "Parâmetros de paginação inválidos"}, status=400)

    total  = qs.count()
    offset = (page - 1) * page_size
    lotes  = list(qs[offset: offset + page_size])

    import math
    pages = math.ceil(total / page_size) if total else 1

    return JsonResponse({
        "total":  total,
        "page":   page,
        "pages":  pages,
        "lotes":  [_lote_dict(l) for l in lotes],
    })


# ── POST /api/governo/sia-sus/reprocessar/<lote_id> ──────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_sia_sus_reprocessar(request, lote_id):
    """
    Tenta retransmitir lote com erro ou pendente.

    Rejeita lotes já transmitidos com sucesso (enviado_cnes=True).
    Verifica credenciais novamente; se configuradas, faz POST real ao SISAB.
    Se ainda sem credenciais, mantém pendente e retorna instrução.

    POST /api/governo/sia-sus/reprocessar/<int:lote_id>
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if FaturamentoSUSLote is None or CredenciaisIntegracoes is None:
        return JsonResponse({"erro": "Módulo de faturamento/credenciais indisponível"}, status=503)

    try:
        lote = FaturamentoSUSLote.objects.get(pk=lote_id, empresa=empresa)
    except FaturamentoSUSLote.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado."}, status=404)

    if lote.enviado_cnes:
        return JsonResponse(
            {"erro": "Lote já foi transmitido com sucesso — reprocessamento não necessário."},
            status=400,
        )

    cred   = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    sus_ok = cred.sus_configurado() if cred else False

    if sus_ok:
        logger.info("SIA/SUS: reprocessando lote %s para empresa %s", lote_id, empresa)
        return _transmitir_bpa_sisab(empresa, lote, cred, [])
    else:
        return _salvar_lote_pendente(lote)
