"""
Anti-Glosa (lado PRESTADOR) — motor de crítica PRÉ-ENVIO de guias TISS.

Roda regras determinísticas sobre uma GuiaTISS ANTES de ela ir para a operadora,
pegando o que seria glosado (a maior dor de faturamento do hospital). É:
  • Isolado por tenant (todas as queries filtram empresa=guia.empresa).
  • Offline na hora do envio: usa só o banco local + o espelho TUSS nacional
    (TerminologiaTuss), nunca chama API externa no caminho do envio.
  • Determinístico e explicável: cada achado tem código, motivo e sugestão.

A IA de risco-de-glosa (Fase 2) entra como camada complementar, somando ao
score deste motor; a gestão de glosa recebida + recurso (Fase 3) reaproveita a
mesma taxonomia de códigos daqui.

Saída de `criticar_guia_tiss(guia)`:
  {
    "ocorrencias": [ {severidade, codigo, campo, item_idx, mensagem, sugestao}, ... ],
    "bloqueia": bool,          # há alguma ocorrência 'bloqueia'
    "total": int,
    "por_severidade": {"bloqueia": n, "alerta": n, "info": n},
    "score_risco": int,        # 0-100 (heurístico; Fase 2 refina com ML)
    "resumo": str,
  }

severidade:
  'bloqueia' — erro que quase certamente gera glosa/rejeição; impede o envio
               sem override explícito (forcar=True).
  'alerta'   — risco relevante; não impede, mas deve ser revisado.
  'info'     — observação de qualidade.
"""
import re
import statistics
from decimal import Decimal, InvalidOperation

# CID-10: uma letra (exceto U) + 2 dígitos, com subcategoria opcional (.0-.9[.9])
_CID10_RE = re.compile(r"^[A-TV-Z][0-9]{2}(\.?[0-9]{1,2})?$", re.IGNORECASE)

# Tipos de guia que exigem CID-10 informado (glosa clássica: "CID ausente").
_TIPOS_EXIGEM_CID = {"sadt", "sp_sadt", "internacao", "resumo"}

# Janela de histórico para duplicidade e outlier de valor.
_JANELA_HISTORICO_DIAS = 90
_MAX_GUIAS_HISTORICO = 400          # limita o custo do scan de JSON em Python
_OUTLIER_FATOR = 2.5                # valor_unitario > fator × mediana histórica → alerta
_TOLERANCIA_VALOR = Decimal("0.02")  # divergência aceitável entre total e soma dos itens

_PESO_SEVERIDADE = {"bloqueia": 40, "alerta": 15, "info": 4}


def _oc(severidade, codigo, mensagem, *, campo="", item_idx=None, sugestao=""):
    return {
        "severidade": severidade,
        "codigo": codigo,
        "campo": campo,
        "item_idx": item_idx,
        "mensagem": mensagem,
        "sugestao": sugestao,
    }


def _dec(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


# ── Regras de conteúdo (só a guia em si) ─────────────────────────────────────

def _regra_cabecalho(guia, ocs):
    if not (guia.beneficiario_carteirinha or "").strip():
        ocs.append(_oc("bloqueia", "GLOSA_CARTEIRINHA_AUSENTE",
                       "Beneficiário sem número de carteirinha.",
                       campo="beneficiario_carteirinha",
                       sugestao="Preencha a carteirinha do beneficiário (TISS: numeroCarteira)."))
    if not (guia.operadora_codigo or "").strip():
        ocs.append(_oc("bloqueia", "GLOSA_REGISTRO_ANS_AUSENTE",
                       "Operadora sem registro ANS (registroANS).",
                       campo="operadora_codigo",
                       sugestao="Informe o registro ANS da operadora de destino."))
    cid = (guia.cid10 or "").strip()
    if guia.tipo in _TIPOS_EXIGEM_CID and not cid:
        ocs.append(_oc("bloqueia", "GLOSA_CID_AUSENTE",
                       f"CID-10 obrigatório para guia do tipo '{guia.tipo}' e não informado.",
                       campo="cid10",
                       sugestao="Informe o CID-10 principal do atendimento."))
    elif cid and not _CID10_RE.match(cid):
        ocs.append(_oc("alerta", "GLOSA_CID_INVALIDO",
                       f"CID-10 '{cid}' fora do formato válido (ex.: J06, I10, S72.0).",
                       campo="cid10",
                       sugestao="Corrija o CID-10 para o padrão letra+2 dígitos (subcategoria opcional)."))


def _regra_itens(guia, ocs, codigos_tuss_validos):
    procs = guia.procedimentos or []
    if not procs:
        ocs.append(_oc("bloqueia", "GLOSA_SEM_PROCEDIMENTO",
                       "Guia sem nenhum procedimento.",
                       campo="procedimentos",
                       sugestao="Adicione ao menos um procedimento à guia."))
        return

    vistos = set()
    for i, proc in enumerate(procs):
        codigo = str(proc.get("codigo", "") or "").strip()
        descr = str(proc.get("descricao", "") or "").strip()
        qtd = _num(proc.get("quantidade", 1))
        vu = _num(proc.get("valor_unitario", 0))
        tabela = str(proc.get("tabela", "22") or "22").strip()

        if not codigo or codigo == "0":
            ocs.append(_oc("bloqueia", "GLOSA_ITEM_SEM_CODIGO",
                           f"Item {i + 1} sem código de procedimento.",
                           campo="procedimentos", item_idx=i,
                           sugestao="Informe o código TUSS do procedimento."))
        else:
            # Duplicidade DENTRO da própria guia (mesmo código repetido).
            chave = (tabela, codigo)
            if chave in vistos:
                ocs.append(_oc("alerta", "GLOSA_ITEM_DUPLICADO_NA_GUIA",
                               f"Procedimento {codigo} aparece mais de uma vez na guia.",
                               campo="procedimentos", item_idx=i,
                               sugestao="Unifique a quantidade em um único item ou remova a duplicata."))
            vistos.add(chave)
            # Código não consta no espelho TUSS nacional (best-effort).
            if codigos_tuss_validos is not None and (tabela, codigo) not in codigos_tuss_validos:
                ocs.append(_oc("alerta", "GLOSA_TUSS_INEXISTENTE",
                               f"Código {codigo} (tabela {tabela}) não encontrado na TUSS/ANS vigente.",
                               campo="procedimentos", item_idx=i,
                               sugestao="Confira o código TUSS na terminologia oficial da ANS."))

        if not descr:
            ocs.append(_oc("alerta", "GLOSA_ITEM_SEM_DESCRICAO",
                           f"Item {i + 1} sem descrição do procedimento.",
                           campo="procedimentos", item_idx=i,
                           sugestao="Descreva o procedimento (facilita a análise da operadora)."))
        if qtd <= 0:
            ocs.append(_oc("bloqueia", "GLOSA_QUANTIDADE_INVALIDA",
                           f"Item {i + 1} com quantidade {qtd:g} (deve ser > 0).",
                           campo="procedimentos", item_idx=i,
                           sugestao="Informe uma quantidade executada maior que zero."))
        if vu <= 0:
            ocs.append(_oc("alerta", "GLOSA_VALOR_ZERADO",
                           f"Item {i + 1} com valor unitário zerado.",
                           campo="procedimentos", item_idx=i,
                           sugestao="Informe o valor unitário do procedimento."))


def _regra_coerencia_valor(guia, ocs):
    procs = guia.procedimentos or []
    soma = Decimal("0")
    for proc in procs:
        soma += _dec(proc.get("quantidade", 1)) * _dec(proc.get("valor_unitario", 0))
    apresentado = _dec(guia.valor_apresentado)
    if apresentado > 0 and soma > 0 and abs(apresentado - soma) > max(_TOLERANCIA_VALOR, soma * Decimal("0.01")):
        ocs.append(_oc("alerta", "GLOSA_VALOR_INCOERENTE",
                       f"Valor apresentado (R$ {apresentado:.2f}) diverge da soma dos itens "
                       f"(R$ {soma:.2f}).",
                       campo="valor_apresentado",
                       sugestao="Acerte o valor apresentado para bater com a soma dos procedimentos."))
    elif apresentado <= 0 and soma <= 0:
        ocs.append(_oc("alerta", "GLOSA_VALOR_AUSENTE",
                       "Guia sem valor apresentado e sem valores nos itens.",
                       campo="valor_apresentado",
                       sugestao="Informe os valores dos procedimentos."))


# ── Regras que olham o histórico do prestador (mesmo tenant) ─────────────────

def _historico_guias(guia):
    """Guias recentes da MESMA empresa (exclui a própria), já enviadas/pagas/glosadas."""
    from datetime import timedelta
    from django.utils import timezone
    from api.models import GuiaTISS
    desde = timezone.now() - timedelta(days=_JANELA_HISTORICO_DIAS)
    qs = (GuiaTISS.objects
          .filter(empresa=guia.empresa, criado_em__gte=desde)
          .exclude(pk=guia.pk)
          .exclude(status="elaborada")
          .order_by("-criado_em")[:_MAX_GUIAS_HISTORICO])
    return list(qs)


def _regra_duplicidade_e_outlier(guia, ocs, historico):
    if not historico:
        return
    cart = (guia.beneficiario_carteirinha or "").strip()
    # Índice de valores históricos por código (para mediana) e conjunto de
    # (carteirinha, código) já faturados recentemente (para duplicidade).
    valores_por_codigo = {}
    faturados = set()
    for h in historico:
        h_cart = (h.beneficiario_carteirinha or "").strip()
        for proc in (h.procedimentos or []):
            cod = str(proc.get("codigo", "") or "").strip()
            if not cod:
                continue
            vu = _num(proc.get("valor_unitario", 0))
            if vu > 0:
                valores_por_codigo.setdefault(cod, []).append(vu)
            if h_cart:
                faturados.add((h_cart, cod))

    for i, proc in enumerate(guia.procedimentos or []):
        cod = str(proc.get("codigo", "") or "").strip()
        if not cod:
            continue
        vu = _num(proc.get("valor_unitario", 0))
        if cart and (cart, cod) in faturados:
            ocs.append(_oc("alerta", "GLOSA_DUPLICIDADE_HISTORICA",
                           f"Procedimento {cod} já faturado para esta carteirinha nos últimos "
                           f"{_JANELA_HISTORICO_DIAS} dias.",
                           campo="procedimentos", item_idx=i,
                           sugestao="Confirme se não é cobrança em duplicidade (glosa por repetição)."))
        amostra = valores_por_codigo.get(cod, [])
        if vu > 0 and len(amostra) >= 4:
            mediana = statistics.median(amostra)
            if mediana > 0 and vu > mediana * _OUTLIER_FATOR:
                ocs.append(_oc("alerta", "GLOSA_VALOR_OUTLIER",
                               f"Valor unitário de {cod} (R$ {vu:.2f}) muito acima do seu "
                               f"histórico (mediana R$ {mediana:.2f}).",
                               campo="procedimentos", item_idx=i,
                               sugestao="Revise o valor; operadoras glosam itens acima da tabela pactuada."))


# ── Espelho TUSS (best-effort, sem rede) ─────────────────────────────────────

def _codigos_tuss_validos(guia):
    """Conjunto de (tabela, codigo) válidos no espelho TUSS nacional para os
    códigos presentes na guia. Best-effort: se o espelho estiver vazio/indisponível,
    retorna None (a regra de TUSS inexistente é pulada, não gera falso positivo)."""
    try:
        from api.models import TerminologiaTuss
        pares = set()
        for proc in (guia.procedimentos or []):
            cod = str(proc.get("codigo", "") or "").strip()
            tab = str(proc.get("tabela", "22") or "22").strip()
            if cod:
                pares.add((tab, cod))
        if not pares:
            return None
        # Se o espelho está vazio, não dá pra afirmar nada → None.
        if not TerminologiaTuss.objects.exists():
            return None
        validos = set()
        for tab, cod in pares:
            # guia guarda "22"; espelho guarda "tuss-22".
            tabela_espelho = tab if tab.startswith("tuss-") else f"tuss-{tab}"
            if TerminologiaTuss.objects.filter(tabela=tabela_espelho, codigo=cod).exists():
                validos.add((tab, cod))
        return validos
    except Exception:
        return None


# ── Entrada principal ────────────────────────────────────────────────────────

def criticar_guia_tiss(guia):
    """Roda todas as regras de crítica pré-envio sobre uma GuiaTISS.
    Não levanta exceção: qualquer regra que falhe é ignorada (best-effort)."""
    ocs = []
    try:
        _regra_cabecalho(guia, ocs)
    except Exception:
        pass
    try:
        codigos_validos = _codigos_tuss_validos(guia)
    except Exception:
        codigos_validos = None
    try:
        _regra_itens(guia, ocs, codigos_validos)
    except Exception:
        pass
    try:
        _regra_coerencia_valor(guia, ocs)
    except Exception:
        pass
    try:
        _regra_duplicidade_e_outlier(guia, ocs, _historico_guias(guia))
    except Exception:
        pass

    por_sev = {"bloqueia": 0, "alerta": 0, "info": 0}
    score = 0
    for o in ocs:
        sev = o["severidade"]
        por_sev[sev] = por_sev.get(sev, 0) + 1
        score += _PESO_SEVERIDADE.get(sev, 0)
    score = min(100, score)
    bloqueia = por_sev["bloqueia"] > 0

    if bloqueia:
        resumo = (f"{por_sev['bloqueia']} problema(s) que bloqueiam o envio e "
                  f"{por_sev['alerta']} alerta(s).")
    elif por_sev["alerta"]:
        resumo = f"Sem bloqueios, mas {por_sev['alerta']} alerta(s) de risco de glosa."
    else:
        resumo = "Nenhum problema encontrado — guia pronta para envio."

    return {
        "ocorrencias": ocs,
        "bloqueia": bloqueia,
        "total": len(ocs),
        "por_severidade": por_sev,
        "score_risco": score,
        "resumo": resumo,
    }


# ── Fase 2: IA de risco-de-glosa (motor ML por área, isolado por tenant) ─────

def risco_glosa_ia(guia):
    """Score PREDITIVO de risco de glosa (0-100) via IA por área, treinada com o
    histórico de guias pagas x glosadas do próprio hospital. Best-effort: retorna
    None se o motor de IA não estiver disponível ou os dados forem insuficientes."""
    try:
        from api.services.ia_areas import inferir
        dados = {
            "procedimentos": guia.procedimentos or [],
            "cid10": guia.cid10,
            "beneficiario_carteirinha": guia.beneficiario_carteirinha,
            "operadora_codigo": guia.operadora_codigo,
            "valor_apresentado": float(guia.valor_apresentado or 0),
        }
        r = inferir("risco_glosa", guia.empresa_id, dados)
        prob_glosa = float(r.get("scores_por_classe", {}).get("glosada", 0.0))
        return {
            "risco_ia": round(prob_glosa * 100),
            "decisao_ia": r.get("decisao"),
            "justificativa_ia": r.get("justificativa_ia", ""),
            "modelo": r.get("modelo", ""),
        }
    except Exception:
        return None


def criticar_guia_completa(guia):
    """Crítica determinística (Fase 1) + risco preditivo por IA (Fase 2).
    As REGRAS bloqueiam o envio; a IA apenas prioriza (advisory)."""
    base = criticar_guia_tiss(guia)
    ia = risco_glosa_ia(guia)
    base["ia"] = ia
    base["score_risco_combinado"] = max(base["score_risco"], ia["risco_ia"]) if ia else base["score_risco"]
    return base
