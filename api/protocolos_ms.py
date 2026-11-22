# -*- coding: utf-8 -*-
"""Protocolos oficiais do Ministério da Saúde — Fase 3 da especificação.

Por que isto existe
-------------------
O LLM conhece as doenças, mas raciocina com conhecimento geral. Vigilância
epidemiológica não funciona com conhecimento geral: funciona com a DEFINIÇÃO DE
CASO do Ministério da Saúde, que é o que determina se um caso é notificado, em
que prazo, e o que a equipe faz em seguida. Duas pessoas com o mesmo quadro
podem gerar condutas diferentes só porque uma atende o critério oficial e a
outra não.

Este módulo é o lugar desse texto. O conteúdo entra no prompt do
`anamnese_ia` apenas para as doenças que aparecem no topo do diferencial — não
faz sentido mandar 30 protocolos quando o caso tem 3 candidatos.

Regra de ouro deste arquivo
---------------------------
**Nada aqui pode ser escrito de memória, nem parafraseado de fonte não oficial.**
Cada entrada carrega a URL de onde veio. Doença sem fonte verificada fica
AUSENTE do dicionário — e ausente é um estado correto: o modelo simplesmente
não recebe protocolo para ela e segue com o resto da evidência. Um protocolo
inventado é pior que protocolo nenhum, porque ganha a autoridade do rótulo
"Ministério da Saúde" sem ter a procedência.

Estado em 21/11/2026
--------------------
Tentei quatro caminhos para obter as definições de caso e a lista de notificação
compulsória: as páginas por doença do gov.br, a central de publicações da SVSA,
o Guia de Vigilância em Saúde no bvsms, e a Portaria GM/MS nº 10.175/2026 no
Diário Oficial. Só as páginas por doença abriram, e a maioria não traz definição
de caso. O Guia (que é a fonte real) retornou 404 nas URLs que conheço, e o DOU
derrubou a conexão.

Por isso o dicionário abaixo está quase vazio, de propósito. O que falta deve
ser preenchido a partir do Guia de Vigilância em Saúde, e o melhor momento é a
revisão clínica que já está pendente — quem for revisar as perguntas tem o Guia
e a habilitação para transcrever. A tabela em branco está em
`REVISAO_CLINICA_PERGUNTAS.md`.
"""

from __future__ import annotations

# Chave: nome exato em DOENCAS_BRASIL (classificador_doencas.py).
# Campos:
#   caso_suspeito : transcrição da definição oficial. "" = ainda não obtida.
#   parcial       : True quando o texto está truncado e precisa ser completado.
#   notificacao   : "imediata" (24h), "semanal", ou "" quando a fonte não diz.
#   fonte         : URL de onde o texto veio. Sem URL, a entrada não entra.
PROTOCOLOS: dict[str, dict] = {
    "Mpox": {
        "caso_suspeito": (
            "Indivíduo de qualquer idade que apresente início súbito de lesão "
            "em mucosas e/ou erupção cutânea aguda sugestiva de mpox"
        ),
        "parcial": True,  # o texto oficial segue além disto — completar da fonte
        "notificacao": "imediata",
        "fonte": "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/m/mpox/definicao-de-caso",
    },
    "Hantavirose": {
        "caso_suspeito": "",
        "parcial": False,
        "notificacao": "imediata",
        "fonte": "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/h/hantavirose",
    },
    # Febre Maculosa: a página oficial afirma notificação obrigatória e
    # investigação em até 48 horas, mas não classifica o prazo da notificação em
    # si. Fica sem o campo, em vez de ser adivinhado.
    "Febre Maculosa": {
        "caso_suspeito": "",
        "parcial": False,
        "notificacao": "",
        "fonte": "https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/f/febre-maculosa",
    },
}

# Doenças cuja definição oficial ainda falta. Existe só para a revisão clínica
# saber o tamanho do trabalho, e para o teste conseguir cobrar a lacuna.
PENDENTES = [
    "Sarampo", "Difteria", "Coqueluche", "Cólera", "Peste", "Raiva Humana",
    "Febre Amarela", "Malaria", "Leptospirose", "Febre Tifoide", "Meningite",
    "Tuberculose", "Hanseníase", "Leishmaniose Visceral",
    "Leishmaniose Tegumentar", "Doença de Chagas", "Esquistossomose",
    "Varicela", "Dengue", "Chikungunya", "Zika", "Hepatite A/B",
]


def bloco_protocolos(doencas: list[str], limite: int = 3) -> str:
    """Monta o trecho de protocolo para as doenças do topo do diferencial.

    Devolve "" quando nenhuma das doenças tem protocolo verificado — e nesse
    caso o prompt não ganha seção nenhuma, em vez de ganhar uma seção vazia que
    só gastaria tokens e sugeriria ausência de critério.
    """
    linhas = []
    for nome in doencas[:limite]:
        p = PROTOCOLOS.get(nome)
        if not p:
            continue
        partes = []
        if p.get("caso_suspeito"):
            txt = p["caso_suspeito"]
            if p.get("parcial"):
                txt += " [...] (transcrição parcial da definição oficial)"
            partes.append(f"caso suspeito: {txt}")
        if p.get("notificacao"):
            partes.append(f"notificação {p['notificacao']}")
        if partes:
            linhas.append(f"- {nome}: " + "; ".join(partes))
    if not linhas:
        return ""
    return (
        "CRITÉRIOS OFICIAIS (Ministério da Saúde) para as hipóteses do topo:\n"
        + "\n".join(linhas)
        + "\nUse-os como referência do que o sistema de vigilância considera "
          "caso. Onde não houver critério listado, raciocine pela clínica."
    )
