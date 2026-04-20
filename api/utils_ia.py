def classificar_padrao(dados):

    febre = dados.get("febre")
    tosse = dados.get("tosse")
    falta_ar = dados.get("falta_ar")

    if febre and tosse and falta_ar:
        return "Respiratório", "Alta probabilidade"

    if febre and tosse:
        return "Viral", "Média probabilidade"

    return "Leve", "Baixa probabilidade"