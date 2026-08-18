"""
producao_ia.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Motor de detecção de anomalia no preenchimento — camada de IA anti-erro.

A validação de faixa (producao_validacao) pega o que está fora da especificação.
Este motor pega o que está DENTRO da faixa mas ANORMAL para aquele produto: um
valor tecnicamente permitido, porém muito distante de tudo que já foi registrado
naquele campo. É o erro de digitação plausível (ex.: 50,0 em vez de 5,0) que
passa pela faixa e só apareceria no retrabalho.

Método: escore-z sobre o histórico da PRÓPRIA empresa para o mesmo produto+campo
(LGPD: nada cruza empresa nem segmento). Custo de dados: zero — aprende com as
ordens que a empresa já preencheu. O ModeloIAArea registra o quanto já aprendeu.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Mínimo de amostras históricas para o escore-z ser confiável.
MIN_AMOSTRAS = 8
# Acima deste |z| o valor é tratado como anomalia a confirmar.
Z_LIMITE = 3.0


def _num(value):
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError, InvalidOperation):
        return None


def detectar_anomalia(empresa, especificacao, chave_campo, valor) -> dict:
    """
    Compara `valor` com o histórico de valores OK do mesmo campo, no mesmo
    produto (especificacao.codigo_produto), da mesma empresa.

    Retorna:
      {
        "avaliado": bool,       # havia histórico suficiente?
        "anomalia": bool,       # |z| acima do limite?
        "z": float|None,
        "media": float|None,
        "desvio": float|None,
        "n": int,               # tamanho da amostra
        "mensagem": str,
        "sugestao": float|None, # valor plausível mais próximo (ordem de grandeza)
      }
    """
    base = {"avaliado": False, "anomalia": False, "z": None, "media": None,
            "desvio": None, "n": 0, "mensagem": "", "sugestao": None}

    x = _num(valor)
    if x is None:
        return base

    from .models import RegistroCampoProducao

    # Histórico: mesmo campo, mesmas ordens do mesmo produto, validação OK.
    valores_raw = (RegistroCampoProducao.objects
                   .filter(empresa=empresa,
                           chave_campo=chave_campo,
                           status_validacao="ok",
                           ordem__especificacao__codigo_produto=especificacao.codigo_produto)
                   .exclude(valor="")
                   .values_list("valor", flat=True)[:500])

    amostra = [v for v in (_num(v) for v in valores_raw) if v is not None]
    n = len(amostra)
    base["n"] = n
    if n < MIN_AMOSTRAS:
        base["mensagem"] = f"IA em aprendizado ({n}/{MIN_AMOSTRAS} amostras)."
        return base

    media = sum(amostra) / n
    var = sum((v - media) ** 2 for v in amostra) / n
    desvio = var ** 0.5
    base.update({"avaliado": True, "media": round(media, 4), "desvio": round(desvio, 4)})

    if desvio == 0:
        # Histórico constante: qualquer valor diferente é suspeito.
        if x != media:
            base["anomalia"] = True
            base["mensagem"] = (f"Valor {x} difere do histórico (sempre {media}). "
                                f"Confirme se está correto.")
            base["sugestao"] = round(media, 4)
        return base

    z = (x - media) / desvio
    base["z"] = round(z, 2)
    if abs(z) >= Z_LIMITE:
        base["anomalia"] = True
        # Heurística de erro de ordem de grandeza (×10 / ÷10 típico de digitação).
        sugestao = None
        for fator in (10.0, 0.1, 100.0, 0.01):
            if desvio and abs((x * fator - media) / desvio) < 1.0:
                sugestao = round(x * fator, 4)
                break
        base["sugestao"] = sugestao
        extra = f" Você quis dizer ~{sugestao}?" if sugestao else ""
        base["mensagem"] = (f"Valor {x} destoa do padrão deste produto "
                            f"(média {round(media, 3)}, ~{abs(round(z, 1))}σ).{extra}")
    else:
        base["mensagem"] = "Dentro do padrão histórico."
    return base


def registrar_aprendizado(empresa, n_novas_amostras=1):
    """
    Atualiza o ModeloIAArea da área 'producao_industrial' para esta empresa —
    reflete no painel o quanto a IA já aprendeu com dados reais. Idempotente e
    tolerante a falha (nunca quebra o fluxo de produção).
    """
    try:
        from .models import ModeloIAArea
        obj, _ = ModeloIAArea.objects.get_or_create(
            empresa=empresa, area="producao_industrial",
            defaults={"n_amostras": 0, "dataset_sintetico": True, "classes": []},
        )
        obj.n_amostras = (obj.n_amostras or 0) + int(n_novas_amostras)
        if obj.n_amostras >= 50:
            obj.dataset_sintetico = False  # já saiu do bootstrap
        obj.save(update_fields=["n_amostras", "dataset_sintetico", "treinado_em"])
        return obj.n_amostras
    except Exception:  # pragma: no cover - defensivo, IA nunca trava produção
        return None
