"""
Previsibilidade de consumo de OPME — motor de previsão TRANSPARENTE.

Métrica de sucesso da Unimed (desafio de OPME): "aumentar a previsibilidade de
consumo por especialidade e procedimento". Aqui a previsão é deliberadamente
EXPLICÁVEL (média móvel recente + tendência linear por mínimos quadrados,
amortecida) e não um modelo caixa-preta — porque para a auditoria de uma
operadora, uma previsão que ela entende e consegue justificar vale mais do que
um número mágico. Cada resposta carrega o método e a base (quantos meses de
histórico) para leitura honesta.

Nada aqui toca no banco: recebe uma série mensal (lista de quantidades, do mês
mais antigo ao mais recente) e devolve a previsão. Quem monta a série a partir
das autorizações é a view — assim o motor é puro e testável.
"""
from statistics import mean, pstdev


def _tendencia_slope(serie):
    """Inclinação (unidades/mês) por mínimos quadrados sobre a série mensal.
    Retorna 0.0 quando há menos de 2 pontos. Puro Python, sem numpy."""
    n = len(serie)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = mean(xs)
    my = mean(serie)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, serie))
    den = sum((x - mx) ** 2 for x in xs)
    return (num / den) if den else 0.0


def _rotulo_confianca(n_meses):
    if n_meses < 3:
        return "dados insuficientes"
    if n_meses < 6:
        return "baixa"
    if n_meses < 12:
        return "média"
    return "alta"


def _rotulo_tendencia(slope, media):
    """Classifica a tendência em relação ao patamar médio (evita chamar de 'alta'
    uma variação irrelevante). Limiar: 10% da média por mês."""
    if media <= 0:
        return "estavel"
    rel = slope / media
    if rel >= 0.10:
        return "alta"
    if rel <= -0.10:
        return "baixa"
    return "estavel"


def prever_serie(serie_mensal, meses_frente=3):
    """Prevê o consumo dos próximos `meses_frente` meses a partir da série mensal
    histórica (lista de quantidades, do mês mais ANTIGO ao mais RECENTE).

    Método (transparente):
      - base recente = média dos últimos até 6 meses (patamar atual de consumo);
      - tendência = inclinação por mínimos quadrados sobre toda a série,
        AMORTECIDA a 50% para não extrapolar demais em série curta/ruidosa;
      - previsão[m] = max(0, base + slope_amortecida * m), arredondada.

    Previsibilidade (0-100): quanto MENOR a variação relativa (coeficiente de
    variação = desvio/média), mais previsível é a demanda. Série vazia/curta ou
    média zero → previsibilidade 0 e método sinalizando a limitação.

    Retorna dict pronto para serializar. Nunca lança.
    """
    serie_raw = [float(max(0.0, v or 0.0)) for v in (serie_mensal or [])]
    meses_frente = max(1, min(int(meses_frente or 3), 12))

    # Apara os meses zerados ANTES do primeiro consumo: são meses em que o item
    # simplesmente ainda não existia na operação, não demanda "baixa". Deixá-los
    # inflaria a variância (parecendo imprevisível) e diluiria a tendência de um
    # item que na verdade só começou a ser usado há poucos meses. Zeros NO MEIO
    # da série são mantidos (aí sim é demanda intermitente real).
    primeiro = next((i for i, v in enumerate(serie_raw) if v > 0), None)
    serie = serie_raw[primeiro:] if primeiro is not None else []
    n = len(serie)

    if n == 0:
        return {
            "consumo_medio_mensal": 0.0,
            "previsao": [0] * meses_frente,
            "total_previsto": 0,
            "tendencia": "estavel",
            "slope_mensal": 0.0,
            "previsibilidade": 0,
            "coef_variacao": None,
            "meses_historico": 0,
            "confianca": _rotulo_confianca(0),
            "metodo": "Sem histórico de consumo — previsão indisponível.",
        }

    recentes = serie[-6:]
    base = mean(recentes)
    slope_raw = _tendencia_slope(serie)          # direção real da demanda
    slope_prev = slope_raw * 0.5                  # amortecido só para projetar

    previsao = []
    for m in range(1, meses_frente + 1):
        val = base + slope_prev * m
        previsao.append(int(round(max(0.0, val))))

    # Previsibilidade: 1 - coeficiente de variação, saturado em [0,1] → 0-100.
    media_total = mean(serie)
    desvio = pstdev(serie) if n >= 2 else 0.0
    cv = (desvio / media_total) if media_total > 0 else None
    if cv is None:              # 1 único mês de histórico: sem base p/ variância
        previsibilidade = 50
    else:
        previsibilidade = int(round(max(0.0, min(1.0, 1.0 - cv)) * 100))

    return {
        "consumo_medio_mensal": round(base, 1),
        "previsao": previsao,
        "total_previsto": int(sum(previsao)),
        "tendencia": _rotulo_tendencia(slope_raw, base),
        "slope_mensal": round(slope_raw, 2),
        "previsibilidade": previsibilidade,
        "coef_variacao": round(cv, 2) if cv is not None else None,
        "meses_historico": n,
        "confianca": _rotulo_confianca(n),
        "metodo": (f"Média dos últimos {len(recentes)} mês(es) + tendência linear "
                   f"amortecida, sobre {n} mês(es) de consumo real."),
    }
