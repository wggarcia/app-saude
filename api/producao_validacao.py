"""
producao_validacao.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Motor de validação anti-erro da Ordem de Produção Industrial.

É o coração do desafio "prevenção de erros no preenchimento de ordens de
produção": valida cada valor no momento em que é digitado, contra a faixa de
aceitação declarada na EspecificacaoProducao, e impede que uma etapa incompleta
ou fora de especificação seja considerada pronta.

Puro Python/Decimal — sem I/O, sem banco (exceto leituras já carregadas). Assim
é testável isoladamente e usado tanto pelo endpoint em tempo real quanto pela
máquina de estados.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation


# Status possíveis de um campo após validação.
OK = "ok"
ALERTA = "alerta"
ERRO = "erro"
PENDENTE = "pendente"


def _to_decimal(value):
    """Converte para Decimal aceitando vírgula decimal brasileira. None se falhar."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    s = s.replace(" ", "").replace(".", "") if s.count(",") == 1 and s.count(".") > 1 else s
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, TypeError, ValueError):
        return None


def validar_valor_campo(campo_spec: dict, valor) -> dict:
    """
    Valida um único valor contra a especificação do campo.

    campo_spec: {"chave","rotulo","tipo","unidade","obrigatorio","min","max", ...}
    valor: valor digitado (string, número ou vazio).

    Retorna dict:
      {
        "status": ok | alerta | erro | pendente,
        "fora_faixa": bool,
        "mensagem": str,
        "min": str, "max": str,          # snapshot da faixa (para auditoria)
        "valor_normalizado": str,
      }
    """
    tipo = str(campo_spec.get("tipo", "numero")).lower()
    obrigatorio = bool(campo_spec.get("obrigatorio", False))
    rotulo = campo_spec.get("rotulo") or campo_spec.get("chave") or "campo"
    unidade = campo_spec.get("unidade", "")

    vazio = valor is None or str(valor).strip() == ""

    resultado = {
        "status": PENDENTE,
        "fora_faixa": False,
        "mensagem": "",
        "min": "" if campo_spec.get("min") in (None, "") else str(campo_spec.get("min")),
        "max": "" if campo_spec.get("max") in (None, "") else str(campo_spec.get("max")),
        "valor_normalizado": "" if vazio else str(valor).strip(),
    }

    if vazio:
        if obrigatorio:
            resultado["status"] = ERRO
            resultado["mensagem"] = f"{rotulo}: campo obrigatório não preenchido."
        else:
            resultado["status"] = PENDENTE
        return resultado

    # ── Numérico: valida faixa min/max ────────────────────────────────────────
    if tipo in ("numero", "number", "decimal", "inteiro"):
        num = _to_decimal(valor)
        if num is None:
            resultado["status"] = ERRO
            resultado["mensagem"] = f"{rotulo}: valor não é um número válido."
            resultado["fora_faixa"] = True
            return resultado

        vmin = _to_decimal(campo_spec.get("min"))
        vmax = _to_decimal(campo_spec.get("max"))

        if vmin is not None and num < vmin:
            resultado["status"] = ERRO
            resultado["fora_faixa"] = True
            resultado["mensagem"] = (
                f"{rotulo}: {num} {unidade} abaixo do mínimo ({vmin} {unidade})."
            )
            return resultado
        if vmax is not None and num > vmax:
            resultado["status"] = ERRO
            resultado["fora_faixa"] = True
            resultado["mensagem"] = (
                f"{rotulo}: {num} {unidade} acima do máximo ({vmax} {unidade})."
            )
            return resultado

        # Alerta de borda: dentro da faixa mas a ≤5% de um limite.
        if vmin is not None and vmax is not None and vmax > vmin:
            margem = (vmax - vmin) * Decimal("0.05")
            if num <= vmin + margem or num >= vmax - margem:
                resultado["status"] = ALERTA
                resultado["mensagem"] = f"{rotulo}: valor próximo do limite — confira."
                return resultado

        resultado["status"] = OK
        return resultado

    # ── Data ──────────────────────────────────────────────────────────────────
    if tipo == "data":
        s = str(valor).strip()
        ok = False
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                datetime.strptime(s, fmt)
                ok = True
                break
            except ValueError:
                continue
        if not ok:
            resultado["status"] = ERRO
            resultado["mensagem"] = f"{rotulo}: data inválida (use AAAA-MM-DD)."
            return resultado
        resultado["status"] = OK
        return resultado

    # ── Booleano ──────────────────────────────────────────────────────────────
    if tipo in ("booleano", "bool", "checkbox"):
        s = str(valor).strip().lower()
        if s in ("true", "1", "sim", "s", "on"):
            resultado["status"] = OK
        elif s in ("false", "0", "nao", "não", "n", "off"):
            # Se for obrigatório marcar (ex.: "confirmo conferência"), negar é erro.
            if campo_spec.get("exige_verdadeiro"):
                resultado["status"] = ERRO
                resultado["mensagem"] = f"{rotulo}: confirmação obrigatória não marcada."
            else:
                resultado["status"] = OK
        else:
            resultado["status"] = ERRO
            resultado["mensagem"] = f"{rotulo}: valor booleano inválido."
        return resultado

    # ── Seleção (lista de opções permitidas) ──────────────────────────────────
    if tipo in ("selecao", "select", "opcoes"):
        opcoes = campo_spec.get("opcoes") or []
        if opcoes and str(valor).strip() not in [str(o) for o in opcoes]:
            resultado["status"] = ERRO
            resultado["mensagem"] = f"{rotulo}: opção fora da lista permitida."
            return resultado
        resultado["status"] = OK
        return resultado

    # ── Texto: valida comprimento mínimo se exigido ───────────────────────────
    min_len = campo_spec.get("min_len")
    if min_len and len(str(valor).strip()) < int(min_len):
        resultado["status"] = ERRO
        resultado["mensagem"] = f"{rotulo}: texto muito curto (mín. {min_len} caracteres)."
        return resultado

    resultado["status"] = OK
    return resultado


def validar_etapa(especificacao, registros_por_chave: dict, etapa_chave: str) -> dict:
    """
    Valida se uma etapa está COMPLETA e SEM ERROS.

    especificacao: EspecificacaoProducao
    registros_por_chave: {chave_campo: valor} — o que já foi preenchido.
    etapa_chave: chave da etapa a validar.

    Retorna:
      {
        "completa": bool,          # todos os obrigatórios preenchidos e válidos
        "faltando": [rotulos],     # obrigatórios ainda vazios
        "com_erro": [mensagens],   # campos preenchidos fora da faixa
        "total_campos": int,
        "ok": int,
      }
    """
    campos = especificacao.campos_da_etapa(etapa_chave)
    faltando, com_erro = [], []
    ok = 0

    for campo in campos:
        chave = campo.get("chave")
        if not chave:
            continue
        valor = registros_por_chave.get(chave)
        res = validar_valor_campo(campo, valor)
        rotulo = campo.get("rotulo") or chave

        if res["status"] == ERRO:
            if valor is None or str(valor).strip() == "":
                faltando.append(rotulo)
            else:
                com_erro.append(res["mensagem"])
        elif res["status"] == OK:
            ok += 1
        elif res["status"] == PENDENTE and bool(campo.get("obrigatorio")):
            faltando.append(rotulo)

    completa = not faltando and not com_erro
    return {
        "completa": completa,
        "faltando": faltando,
        "com_erro": com_erro,
        "total_campos": len(campos),
        "ok": ok,
    }


def validar_rendimento(especificacao, tamanho_lote, rendimento_real) -> dict:
    """
    Reconciliação de rendimento (BPF). Compara o rendimento real com o teórico
    escalonado pelo tamanho do lote desta ordem e verifica a janela de aceitação.

    Retorna:
      {"aplicavel": bool, "pct": Decimal|None, "dentro_faixa": bool,
       "esperado": Decimal|None, "mensagem": str}
    """
    teorico_padrao = _to_decimal(especificacao.rendimento_teorico)
    lote_padrao = _to_decimal(especificacao.tamanho_lote_padrao)
    lote = _to_decimal(tamanho_lote)
    real = _to_decimal(rendimento_real)

    if not teorico_padrao or not lote_padrao or lote_padrao == 0 or lote is None:
        return {"aplicavel": False, "pct": None, "dentro_faixa": True,
                "esperado": None, "mensagem": "Rendimento teórico não parametrizado."}

    esperado = (teorico_padrao / lote_padrao) * lote  # rendimento teórico deste lote
    if real is None:
        return {"aplicavel": True, "pct": None, "dentro_faixa": True,
                "esperado": esperado, "mensagem": "Rendimento real ainda não informado."}

    if esperado == 0:
        return {"aplicavel": False, "pct": None, "dentro_faixa": True,
                "esperado": esperado, "mensagem": "Rendimento esperado zero."}

    pct = (real / esperado) * Decimal("100")
    fmin = _to_decimal(especificacao.faixa_rendimento_min) or Decimal("0")
    fmax = _to_decimal(especificacao.faixa_rendimento_max) or Decimal("999")
    dentro = fmin <= pct <= fmax

    if dentro:
        msg = f"Rendimento {pct.quantize(Decimal('0.01'))}% — dentro da faixa ({fmin}–{fmax}%)."
    else:
        msg = (f"Rendimento {pct.quantize(Decimal('0.01'))}% FORA da faixa "
               f"({fmin}–{fmax}%). Desvio requer justificativa (BPF).")
    return {"aplicavel": True, "pct": pct.quantize(Decimal("0.01")),
            "dentro_faixa": dentro, "esperado": esperado.quantize(Decimal("0.001")),
            "mensagem": msg}


def derivar_resultado_cq(criterios: list, medidas: dict) -> dict:
    """
    Deriva aprovado/reprovado do controle de qualidade a partir dos VALORES
    medidos — não aceita o resultado enviado pelo cliente. Cada critério é um
    campo com faixa; se qualquer um estiver fora, o CQ é reprovado.

    criterios: lista de campos_spec do CQ (com min/max).
    medidas: {chave: valor_medido}.

    Retorna {"resultado": "aprovado"|"reprovado", "reprovas": [mensagens]}.
    """
    reprovas = []
    for c in criterios:
        chave = c.get("chave")
        if not chave:
            continue
        res = validar_valor_campo(c, medidas.get(chave))
        if res["status"] == ERRO:
            reprovas.append(res["mensagem"])
    return {"resultado": "reprovado" if reprovas else "aprovado", "reprovas": reprovas}
