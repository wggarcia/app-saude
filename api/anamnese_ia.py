"""
Fase 1 — Cérebro LLM de anamnese (ADITIVO).

Reavalia o quadro clínico de um RegistroSintoma com Claude, FUNDAMENTADO em:
  • o diferencial que o motor bayesiano já calculou (trava anti-ancoragem — o
    modelo recebe o ranking inteiro, não só a queixa principal);
  • a lista fechada de doenças conhecidas (não pode inventar doença);
  • o contexto local (estado/cidade).

O que este módulo NÃO faz, de propósito:
  • NÃO substitui `grupo`/`classificacao` — esses campos continuam vindo do
    classificador determinístico, porque os painéis do gestor agregam por eles.
    A hipótese do LLM vai para os campos `hipotese_ia*`, à parte.
  • NÃO decide emergência. Urgência absoluta (rigidez de nuca, falta de ar,
    manchas hemorrágicas) continua em regra fixa no classificador.
  • NÃO bloqueia o registro. Roda em BACKGROUND (fila RQ). Se a IA estiver
    indisponível (sem chave, billing, timeout), o registro segue com o
    resultado do motor — fail-open, sem erro para o cidadão.

Triagem, não diagnóstico.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("api")

# Modelo, por setting — para trocar sem deploy e medir Haiku contra Sonnet nos
# seus próprios casos. Haiku 5.5 é ~20x mais barato ($0,10/$0,50 contra $2/$10);
# a tarefa aqui é escolher dentro de uma lista fechada que o motor já ranqueou,
# não redigir parecer, então ele tem boa chance de dar conta. Medir antes de
# confiar: ANAMNESE_IA_MODELO=claude-haiku-5-5 no .env.
MODELO_RACIOCINIO = getattr(settings, "ANAMNESE_IA_MODELO", "") or "claude-sonnet-5-5"

# Modelo caro, chamado SÓ quando o barato dá sinal de que o caso é difícil.
# A bateria de 20 casos mostrou onde o barato quebra: ele rebaixa doença rara
# para doença comum (disse Varicela onde havia os quatro achados de Mpox, o
# mesmo erro do registro 168884). O que esses casos têm em comum é serem
# justamente os que o barato NÃO consegue resolver sozinho — e ele avisa,
# discordando do motor. Daí a escalada: paga-se caro só onde o barato
# levantou a mão. Vazio = sem escalada, roda só o barato.
MODELO_DIFICIL = getattr(settings, "ANAMNESE_IA_MODELO_DIFICIL", "") or ""

# Teto de saída, não alvo: cobra-se o que é gerado, não o que é reservado. A
# resposta real tem ~180 a 300 tokens, então a folga aqui não custa nada — ela
# existe como rede de segurança caso o desligamento do pensamento não pegue
# (SDK antigo, modelo que ignore o campo). Com 350 e pensamento ligado, o
# modelo gastou tudo pensando e devolveu vazio.
# Subiu de 900 para 1600 depois que um caso de dengue voltou com o JSON cortado
# no meio da frase: a resposta foi descartada inteira e o registro ficou sem
# hipótese. Teto curto não economiza nada e transforma resposta boa em perda.
MAX_TOKENS = 1600

# Qual valor de "thinking" cada modelo aceita, descoberto na primeira chamada.
# Sem esta memória o Sonnet gasta um 400 em TODO envio antes da chamada boa:
# medido na bateria de 20 casos, foram 20 idas e voltas desperdiçadas.
_MODO_THINKING: dict[str, str] = {}

# ── Quando NÃO vale chamar a IA ───────────────────────────────────────────────
# A maior economia não é o modelo: é não chamar. Num quadro onde o motor já
# decidiu com folga (febre + tosse + coriza → resfriado disparado), a IA custa e
# não acrescenta. Ela ganha o pão onde o motor fica em dúvida — que é o caso do
# registro 168882: Gripe 63 contra Mpox 60, quase empate, e a segunda hipótese
# mudava a conduta.
#
# Com estes limiares, só a minoria ambígua é enviada. É também a decisão
# clinicamente correta, não só a barata.
# Os dois números abaixo foram MEDIDOS, não escolhidos. A primeira versão usava
# confiança < 70, e a medição mostrou que isso era inútil: a confiança do líder
# vai de 49 a 67 nos dados reais (mediana 58), então "< 70" era sempre verdade e
# o portão nunca dispensava ninguém. Economia que não existia.
#
# O que de fato discrimina é a disputa entre 1º e 2º. Distribuição medida sobre
# 2.167 diferenciais: p25=0,60 · mediana=0,81 · p75=0,90. Ou seja, na metade dos
# casos o 2º lugar tem 81%+ da pontuação do 1º — o motor vive em dúvida.
#
# 0,80 corta metade do volume. E é o teto que ainda deixa passar o caso que
# motivou tudo isto: o registro 168882 (Gripe 63 x Mpox 60) tem razão 0,83. Em
# 0,85 a IA nunca veria o Mpox — economia que custaria exatamente o achado.
#
# Ressalva honesta: a amostra medida é majoritariamente sintética (simulação e
# seed), não tráfego real. Revisar quando houver envio de gente de verdade.
CONFIANCA_DISPENSA_IA = 52     # abaixo disto o motor está perdido: manda ver
RAZAO_DISPUTA = 0.80           # 2º a 80%+ do 1º: disputa real, vale a chamada


# Doenças em que ERRAR CUSTA CARO, mesmo quando o motor não as põe em primeiro.
#
# Vieram de um teste real que reprovou o portão: um caso com lesão vesicular
# trouxe Gripe > COVID > Mpox, e a disputa entre 1º e 2º (0,499) ficou abaixo do
# limiar — então a IA foi dispensada e ninguém olhou o Mpox, que estava em 3º
# com 38% da pontuação do líder. Economizei US$ 0,0002 e descartei exatamente o
# caso que motivou este sistema.
#
# O erro de desenho era tratar "vale chamar a IA?" como questão de EMPATE. Em
# saúde é questão de CONSEQUÊNCIA: gripe contra COVID empatados importam pouco,
# porque a conduta é parecida; Mpox em terceiro importa muito, porque é
# notificação compulsória e muda isolamento e rastreio de contatos.
#
# Lista: notificação compulsória e/ou alta letalidade. Fora dela ficam as
# comuns de fundo (gripe, resfriado, COVID, viroses), cuja presença não
# qualifica caso nenhum como digno de atenção extra.
from .classificador_doencas import DOENCAS_SENTINELA  # fonte única

# Piso para a sentinela contar: abaixo disto é ruído de cauda, não hipótese.
PARTICIPACAO_SENTINELA = 0.20


def _tem_sentinela_relevante(diferencial) -> bool:
    """Alguma doença de alta consequência aparece com peso real no diferencial?"""
    try:
        score_lider = diferencial[0].get("score") or 0
        if score_lider <= 0:
            return False
        for item in diferencial:
            if item.get("doenca") in DOENCAS_SENTINELA:
                if (item.get("score") or 0) / score_lider >= PARTICIPACAO_SENTINELA:
                    return True
    except (AttributeError, IndexError, TypeError):
        return False
    return False


def vale_chamar_ia(diferencial) -> bool:
    """Decide se o caso merece uma chamada paga.

    Três portas, nesta ordem de importância:
      1. Alguma doença de alta consequência (DOENCAS_SENTINELA) aparece com
         peso real — chama, por mais isolado que esteja o líder.
      2. O motor está inseguro (confiança baixa) — chama.
      3. O 2º está colado no 1º — chama.

    A primeira existe porque as outras duas, sozinhas, descartaram um caso com
    lesão vesicular e Mpox em terceiro. Empate não é o que define relevância
    clínica; consequência é.

    Na dúvida (diferencial ausente ou malformado), chama — perder um caso
    ambíguo é pior que gastar uma fração de centavo.
    """
    # Porta 0 — o dono pediu a IA em todo envio, depois de o portão ter
    # descartado um caso com lesão vesicular e Mpox no diferencial. Entre pagar
    # por todos e arriscar perder um, ele escolheu pagar. Decisão dele, e o
    # custo cabe: dobra o volume, mas segue na casa de US$ 8,5 mil para 50
    # milhões de envios.
    if getattr(settings, "ANAMNESE_IA_SEMPRE", True):
        return True

    if not isinstance(diferencial, list) or not diferencial:
        return True

    primeiro = diferencial[0]
    if not isinstance(primeiro, dict):
        return True

    # Porta 1 — consequência antes de empate.
    if _tem_sentinela_relevante(diferencial):
        return True

    confianca = primeiro.get("confianca") or 0
    if confianca < CONFIANCA_DISPENSA_IA:
        return True

    if len(diferencial) < 2 or not isinstance(diferencial[1], dict):
        return False  # líder confiante e sem concorrente

    score_1 = primeiro.get("score") or 0
    score_2 = diferencial[1].get("score") or 0
    if score_1 <= 0:
        return True

    return (score_2 / score_1) >= RAZAO_DISPUTA

# Comorbidades granulares da Fase 0 — não estão em CAMPOS_ANAMNESE.
_COMORBIDADES = ("tem_diabetes", "tem_hipertensao", "tem_doenca_pulmonar", "tem_imunossupressao")

_ROTULOS = {
    "tem_diabetes": "diabetes",
    "tem_hipertensao": "hipertensão",
    "tem_doenca_pulmonar": "doença pulmonar/asma/DPOC",
    "tem_imunossupressao": "imunossupressão ou tratamento oncológico",
    "viagem_area_endemica": "viagem a área endêmica (Amazônia/pantanal/mata)",
    "exposicao_agua_enchente": "contato com água de enchente ou esgoto",
    "contato_roedores": "contato com roedores ou animais silvestres",
    "contato_caso_confirmado": "contato próximo com caso confirmado",
    "vacinado_febre_amarela": "vacinado para febre amarela",
    "exposicao_carrapato": "contato com carrapato",
    "exposicao_triatomideo": "contato com barbeiro (triatomíneo)",
    "inicio_abrupto": "início abrupto dos sintomas",
    # Desempate vesicular. Sem estes rótulos o modelo não enxerga as
    # respostas e reclama do que lhe foi informado: no registro 168884 a
    # pessoa respondeu que TEM íngua e o modelo escreveu "linfadenopatia...
    # não relatada" para justificar Varicela.
    "vesicula_dolorosa": "lesão vesicular que dói mais do que coça",
    "linfonodo_aumentado": "linfonodo aumentado (íngua) em pescoço, axila ou virilha",
    "lesao_face_palmas": "lesões iniciadas na face ou acometendo palmas/plantas",
    "vesiculas_estagios_variados": "vesículas em estágios simultâneos diferentes",
    # Desempate das demais portas. Sem rótulo o campo não aparece no bloco de
    # dados e o modelo reclama de informação que, na verdade, foi coletada.
    "exantema_craniocaudal": "exantema iniciado na face com progressão craniocaudal",
    "exantema_pruriginoso": "exantema intensamente pruriginoso",
    "exantema_palmo_plantar": "exantema em palmas e plantas",
    "exantema_apos_febre": "exantema surgido na defervescência",
    "tosse_mais_3_semanas": "tosse há mais de 3 semanas",
    "tosse_paroxistica": "tosse paroxística com guincho ou vômito pós-tussígeno",
    "sudorese_noturna": "sudorese noturna que encharca as roupas",
    "urina_escura_fezes_claras": "colúria com acolia fecal",
    "dor_panturrilha": "mialgia intensa de panturrilhas",
    "fezes_agua_arroz": "fezes aquosas em água de arroz",
    "fezes_com_sangue": "fezes com sangue ou muco",
    "febre_alta_prolongada": "febre alta contínua por mais de uma semana",
    "artralgia_simetrica": "artralgia simétrica (mesmas articulações bilateralmente)",
    "artralgia_mais_2_semanas": "artralgia persistente há mais de 2 semanas",
    "dispneia_subita_pos_febre": "dispneia de instalação súbita dias após a febre",
    "dispneia_piora_deitado": "ortopneia (dispneia que piora em decúbito)",
    "barriga_inchada": "distensão abdominal ou massa em hipocôndrio esquerdo",
    "ulcera_indolor_bordas": "úlcera indolor de bordas elevadas",
    "ulcera_mais_1_mes": "úlcera aberta há mais de um mês",
    "febre_ciclica": "febre cíclica com calafrio e sudorese (acesso malárico)",
    "febre_bifasica": "curva febril bifásica (remissão seguida de recrudescência)",
    "placa_na_garganta": "placa branco-acinzentada aderente em orofaringe",
    "pescoco_inchado": "edema cervical difuso (pescoço de touro)",
    "mordedura_animal": "mordedura, arranhadura ou lambedura por mamífero",
}


def _norm(texto: str) -> str:
    s = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _e_indisponibilidade_ia(exc) -> bool:
    """Billing/quota/rate-limit/timeout — não é erro de dado, é IA fora do ar."""
    m = str(exc).lower()
    return any(t in m for t in (
        "credit balance", "plans & billing", "spend limit", "quota",
        "rate limit", "insufficient", "authentication", "permission",
        "overloaded", "timeout", "connection",
    ))


def reconstruir_dados(registro) -> dict[str, Any]:
    """Monta o dict classificável a partir do registro, incluindo as
    comorbidades granulares da Fase 0 (que o helper padrão não cobre)."""
    from .classificador_doencas import sintomas_do_registro

    dados = sintomas_do_registro(registro)
    for campo in _COMORBIDADES:
        dados[campo] = getattr(registro, campo, None)
    return dados


def _system_prompt() -> str:
    return (
        "Você é um apoio de TRIAGEM clínica para um sistema de vigilância "
        "epidemiológica no Brasil. Você NÃO emite diagnóstico, laudo nem "
        "prescrição: você levanta a hipótese sindrômica mais provável para "
        "orientar o encaminhamento e a vigilância.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Escolha a hipótese APENAS dentro da lista de doenças fornecida. "
        "Se nenhuma se sustentar, responda exatamente \"Inconclusivo\".\n"
        "2. NUNCA invente uma doença fora da lista.\n"
        "3. Integre TODA a evidência apresentada — sintomas presentes, "
        "sintomas negados, exposições, comorbidades, tempo de doença e o "
        "contexto local. NÃO se fixe apenas na queixa mais chamativa: "
        "um achado isolado não decide o quadro.\n"
        "3b. \"concorda_com_motor\" significa UMA coisa só: a sua hipótese é "
        "a mesma que o motor colocou em primeiro lugar. É true quando o nome "
        "coincide, mesmo que a sua confiança seja diferente da dele; é false "
        "quando você escolhe outra doença ou Inconclusivo. Não use este campo "
        "para expressar dúvida — para isso existe a confiança.\n"
        "4. Você recebe o diferencial já calculado por um motor bayesiano. "
        "Use-o como referência, mas discorde dele quando a evidência clínica "
        "mandar — e explique por quê.\n"
        "5. Pese as exposições epidemiológicas: elas mudam a probabilidade "
        "mais que um sintoma isolado.\n"
        "6. Imunossupressão muda gravidade e conduta — considere-a sempre que "
        "estiver presente.\n"
        "7. Responda SOMENTE com um objeto JSON válido, sem texto ao redor, "
        "sem markdown, no formato:\n"
        '{"hipotese": "<nome exato da lista ou Inconclusivo>", '
        '"confianca": <inteiro 0-100>, '
        '"concorda_com_motor": <true|false>, '
        '"raciocinio": "<2 a 3 frases, em português, no máximo 450 caracteres, '
        'citando os achados que sustentam e os que afastam>"}'
    )


def _bloco_dados(dados: dict[str, Any]) -> str:
    from .classificador_doencas import TODOS_SINTOMAS

    presentes = [s for s in TODOS_SINTOMAS if dados.get(s) is True]
    negados = [s for s in TODOS_SINTOMAS if dados.get(s) is False]

    linhas = []
    linhas.append("SINTOMAS PRESENTES: " + (", ".join(presentes) if presentes else "nenhum"))
    if negados:
        linhas.append("SINTOMAS NEGADOS: " + ", ".join(negados))

    intens = []
    if dados.get("intensidade_febre"):
        intens.append(f"febre {dados['intensidade_febre']}")
    if dados.get("intensidade_articular"):
        intens.append(f"dor articular {dados['intensidade_articular']}")
    if intens:
        linhas.append("INTENSIDADE: " + ", ".join(intens))

    if dados.get("dias_sintomas") is not None:
        linhas.append(f"TEMPO DE SINTOMAS: {dados['dias_sintomas']} dia(s)")

    sim, nao = [], []
    for campo, rotulo in _ROTULOS.items():
        valor = dados.get(campo)
        if valor is True:
            sim.append(rotulo)
        elif valor is False:
            nao.append(rotulo)
    if sim:
        linhas.append("EXPOSIÇÕES/CONDIÇÕES CONFIRMADAS: " + ", ".join(sim))
    if nao:
        linhas.append("EXPLICITAMENTE NEGADAS: " + ", ".join(nao))

    local = ", ".join(x for x in (dados.get("cidade"), dados.get("estado")) if x)
    if local:
        linhas.append(f"LOCAL: {local}")
    return "\n".join(linhas)


def _bloco_ranking(ranking: list[dict]) -> str:
    if not ranking:
        return "DIFERENCIAL DO MOTOR: vazio (nenhuma hipótese pontuou)."
    itens = [
        f"{i+1}. {r.get('doenca')} (confiança {r.get('confianca')}%)"
        for i, r in enumerate(ranking)
    ]
    return "DIFERENCIAL JÁ CALCULADO PELO MOTOR:\n" + "\n".join(itens)


def _extrair_json(raw: str) -> dict | None:
    if not raw:
        return None
    texto = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(texto)
    except Exception:
        pass
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio != -1 and fim > inicio:
        trecho = texto[inicio:fim + 1]
        try:
            return json.loads(trecho)
        except Exception:
            pass
        # Última tentativa: strict=False aceita quebra de linha e tabulação
        # DENTRO da string. O modelo às vezes escreve o raciocínio em duas
        # linhas, e o parser padrão recusa — a resposta estava correta e era
        # descartada inteira. Custou um caso na bateria: o Sonnet acertou a
        # Zika, o JSON não passou, e ficou valendo a Varicela errada do Haiku.
        try:
            return json.loads(trecho, strict=False)
        except Exception:
            return None
    return None


def _casar_doenca(nome: str, conhecidas: set[str]) -> str:
    """Fundamentação: só aceita doença da lista fechada; senão, Inconclusivo."""
    if not nome:
        return "Inconclusivo"
    if nome in conhecidas:
        return nome
    alvo = _norm(nome)
    if alvo == "inconclusivo":
        return "Inconclusivo"
    for conhecida in conhecidas:
        if _norm(conhecida) == alvo:
            return conhecida
    return "Inconclusivo"


# Viroses banais. A divergência entre duas delas não muda conduta nenhuma:
# gripe ou resfriado, o encaminhamento é o mesmo e nenhuma vigilância é
# acionada. Medido na bateria: o caso-controle escalava por "Resfriado" contra
# "Gripe" e gastava o modelo caro para trocar seis por meia dúzia.
_COMUNS_DE_FUNDO = {
    "Gripe (Influenza)", "Resfriado Viral", "COVID-19",
    "Gastroenterite Viral", "Bronquite / DPOC Agudização",
}


def _merece_segunda_opiniao(avaliacao: dict | None, ranking: list[dict]) -> bool:
    """Escala quando o barato DISCORDA do motor e a divergência tem consequência.

    O sinal é a discordância, e ele sai de graça da chamada já feita. Quando os
    dois concordam, o caso é fácil e pagar de novo não compra nada — na bateria
    de 20 casos o modelo caro confirmou todos os concordantes, um por um.
    Quando discordam, alguém está errado, e foi exatamente aí que o barato
    falhou: Mpox virando Varicela, Zika virando Varicela.

    A exceção são as viroses de fundo: trocar gripe por resfriado não muda
    conduta nem aciona vigilância, então não vale a chamada cara.

    Sem avaliação (IA fora do ar, resposta inválida) não escala: o problema não
    era o modelo, e repetir num modelo caro só multiplica a falha.
    """
    if not avaliacao:
        return False
    if not ranking:
        return False
    lider = ranking[0].get("doenca")
    hipotese = avaliacao.get("hipotese")

    # Sinal 2: sentinela forte que ninguém escolheu.
    # O sinal da discordância não cobre o caso em que o barato CONCORDA com o
    # motor e os dois passam por cima de uma doença de alta consequência que
    # está logo atrás. Aconteceu na bateria: Peste em 5º com 56% do líder, o
    # Haiku repetiu "Leptospirose" e ninguém conferiu.
    # O corte em 55% do líder foi medido: acrescenta 5,8% de escalada em 600
    # casos. "Sentinela em qualquer posição" custaria 62% e "no top-3", 26%.
    # Note que NÃO se dispensa o caso em que o líder já é sentinela: duas
    # sentinelas diferentes pedem condutas diferentes. Leptospirose e Peste
    # lideravam juntas no caso da bateria, e tratar uma como se fosse a outra
    # erra isolamento e rastreio de contatos.
    lider_score = ranking[0].get("score") or 0.0
    if lider_score > 0:
        for x in ranking[1:]:
            if (x.get("doenca") in DOENCAS_SENTINELA
                    and x.get("doenca") != hipotese
                    and (x.get("score") or 0.0) >= 0.55 * lider_score):
                return True

    # Sinal 1: discordância com consequência.
    if hipotese == lider:
        return False
    return not (hipotese in _COMUNS_DE_FUNDO and lider in _COMUNS_DE_FUNDO)


def avaliar_com_escalada(dados: dict[str, Any], ranking: list[dict],
                         conhecidas: set[str]) -> dict | None:
    """Barato em todo envio; caro só onde o barato não basta.

    Medido: o modelo caro acertou os 20 casos da bateria e o barato errou 2,
    mas custa ~20x. Rodar o caro em tudo seria pagar R$ 20 por mil envios para
    corrigir uma minoria. Aqui o barato faz a triagem da própria triagem.
    """
    avaliacao = avaliar(dados, ranking, conhecidas)
    if not MODELO_DIFICIL or MODELO_DIFICIL == MODELO_RACIOCINIO:
        return avaliacao
    if not _merece_segunda_opiniao(avaliacao, ranking):
        return avaliacao

    forte = avaliar(dados, ranking, conhecidas, modelo=MODELO_DIFICIL)
    if not forte:
        # O caro falhou (billing, timeout). A opinião do barato continua
        # valendo mais que nenhuma — nunca descartar o que já se pagou.
        return avaliacao
    logger.info("anamnese_ia: caso escalado de %s para %s (%s → %s).",
                MODELO_RACIOCINIO, MODELO_DIFICIL,
                avaliacao.get("hipotese"), forte.get("hipotese"))
    return forte


def avaliar(dados: dict[str, Any], ranking: list[dict], conhecidas: set[str],
            modelo: str | None = None) -> dict | None:
    """Chama o LLM. Devolve dict com a hipótese, ou None se a IA não puder rodar
    (sem chave, billing, timeout, resposta inválida) — o chamador segue com o motor."""
    _modelo = modelo or MODELO_RACIOCINIO
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.info("anamnese_ia: ANTHROPIC_API_KEY ausente — mantendo só o motor.")
        return None

    # Fase 3 — fundamentação: critério oficial do MS para as hipóteses do topo.
    # Só as 3 primeiras: mandar 30 protocolos num caso de 3 candidatos é gasto
    # sem ganho. Vazio quando nenhuma delas tem protocolo verificado, e aí o
    # prompt não muda em nada.
    from .protocolos_ms import bloco_protocolos
    _protocolos = bloco_protocolos([x.get("doenca") for x in ranking if x.get("doenca")])

    conteudo = (
        f"{_bloco_dados(dados)}\n\n"
        f"{_bloco_ranking(ranking)}\n\n"
        + (f"{_protocolos}\n\n" if _protocolos else "")
        + "LISTA FECHADA DE DOENÇAS PERMITIDAS:\n"
        + ", ".join(sorted(conhecidas))
        + "\n\nResponda apenas o JSON."
    )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        # Pensamento desligado de propósito. Os modelos atuais pensam por
        # padrão, e os tokens de pensamento saem do MESMO orçamento do
        # max_tokens — no primeiro teste real o Haiku gastou os 350 inteiros
        # pensando, parou em stop_reason=max_tokens e não escreveu uma linha.
        # Aqui o raciocínio pesado já foi feito: o motor bayesiano entrega o
        # diferencial pronto, e a tarefa é escolher dentro dele e justificar
        # em três frases. Não precisa deliberar, precisa responder.
        #
        # Vai por extra_body porque o SDK fixado no projeto (anthropic
        # 0.40.0) não conhece o parâmetro `thinking` e rejeita de cara —
        # assim o campo chega à API sem exigir upgrade do SDK, que mexeria
        # com os outros onze serviços de uma vez.
        def _chamar(modo_thinking: str):
            return client.messages.create(
                model=_modelo,
                max_tokens=MAX_TOKENS,
                system=_system_prompt(),
                messages=[{"role": "user", "content": conteudo}],
                extra_body={"thinking": {"type": modo_thinking}},
            )

        _modo = _MODO_THINKING.get(_modelo, "disabled")

        # Duas tentativas. A primeira falha de parse é intermitente e barata de
        # refazer: medido no caso de dengue da bateria, o modelo devolvia JSON
        # inutilizável em parte das execuções e a mesma chamada passava na
        # seguinte. Sem a repetição, o registro fica sem hipótese por um
        # sorteio — e o custo de repetir no modelo barato é R$ 0,001.
        # Só repete quando o problema é o FORMATO. Erro de API (billing,
        # timeout, 400) sobe para o except de fora e não vira duas cobranças.
        obj = None
        bruto = None
        for _tentativa in (1, 2):
            try:
                resposta = _chamar(_modo)
            except Exception as exc:
                # Nem todo modelo aceita o mesmo valor: o Sonnet 5.5 recusa
                # "disabled" com 400 e diz, na própria mensagem, para mandar
                # "between_tools". Sem este fallback, trocar ANAMNESE_IA_MODELO
                # de Haiku para Sonnet derruba a anamnese inteira em silêncio
                # (fail-open: o registro fica só com o motor do Bayes).
                if "between_tools" not in str(exc):
                    raise
                logger.info("anamnese_ia: %s exige thinking=between_tools — "
                            "memorizando para não repetir a cada envio.", _modelo)
                _MODO_THINKING[_modelo] = "between_tools"
                _modo = "between_tools"
                resposta = _chamar(_modo)

            # Nunca assumir que o primeiro bloco é texto: com pensamento ligado
            # o primeiro é o bloco de thinking, e `content[0].text` lê o lugar
            # errado (ou None). Procurar o bloco de texto explicitamente.
            bruto = next(
                (b.text for b in (resposta.content or [])
                 if getattr(b, "type", None) == "text" and getattr(b, "text", None)),
                None,
            )
            if bruto:
                obj = _extrair_json(bruto)
                if isinstance(obj, dict):
                    break

            # O motivo importa: resposta CORTADA (max_tokens) é problema de
            # teto; JSON malformado com stop_reason=end_turn é problema de
            # formato. A mensagem antiga não distinguia os dois.
            logger.warning(
                "anamnese_ia: tentativa %d sem JSON utilizável (modelo=%s, "
                "stop_reason=%s, %d caracteres): %r",
                _tentativa, _modelo, getattr(resposta, "stop_reason", "?"),
                len(bruto or ""), (bruto or "")[:200],
            )
            obj = None

        if not isinstance(obj, dict):
            logger.warning("anamnese_ia: %s não devolveu JSON utilizável em 2 "
                           "tentativas — registro segue só com o motor.", _modelo)
            return None

        try:
            confianca = int(obj.get("confianca") or 0)
        except (TypeError, ValueError):
            confianca = 0

        return {
            "hipotese": _casar_doenca(str(obj.get("hipotese") or ""), conhecidas),
            "confianca": max(0, min(confianca, 100)),
            "concorda": bool(obj.get("concorda_com_motor")),
            "raciocinio": str(obj.get("raciocinio") or "")[:1000],
            "modelo": _modelo,
        }
    except Exception as exc:
        if _e_indisponibilidade_ia(exc):
            logger.warning("anamnese_ia: IA indisponível — segue só o motor: %s", exc)
        else:
            logger.error("anamnese_ia: erro ao avaliar: %s", exc)
        return None


def refinar_hipotese_ia(registro_id):
    """Task de BACKGROUND (fila RQ), enfileirada por registrar_sintoma_publico.

    Fail-open: qualquer falha deixa o registro exatamente como o motor gravou.
    """
    from .services.rls import preservar_tenant

    with preservar_tenant():
        _refinar(registro_id)


def _refinar(registro_id):
    try:
        # Interruptor (defesa em profundidade: o enfileiramento já checa, mas
        # uma chamada direta ao módulo também precisa respeitar a flag).
        if not getattr(settings, "ANAMNESE_IA_ATIVA", False):
            return

        from .models import Empresa, RegistroSintoma
        from .classificador_doencas import DOENCAS_BRASIL, classificar

        # Respeita o tenant público (mesmo do INSERT), como a task de geo.
        try:
            from .middleware import _rls_set_empresa

            emp = Empresa.objects.filter(email="populacao@solocrt.com").first()
            if emp:
                _rls_set_empresa(emp.id)
        except Exception:
            pass

        registro = RegistroSintoma.objects.filter(pk=registro_id).first()
        if not registro:
            return

        dados = reconstruir_dados(registro)
        resultado = classificar(dados, setor="governo", estado=dados.get("estado") or "")
        ranking = (resultado.get("ranking") or [])[:5]

        avaliacao = avaliar_com_escalada(dados, ranking, set(DOENCAS_BRASIL.keys()))
        if not avaliacao:
            return  # fail-open: grupo/classificacao do motor permanecem

        # update() direto: não dispara save() nem toca em grupo/classificacao.
        RegistroSintoma.objects.filter(pk=registro_id).update(
            hipotese_ia=avaliacao["hipotese"][:80],
            hipotese_ia_confianca=avaliacao["confianca"],
            hipotese_ia_concorda=avaliacao["concorda"],
            hipotese_ia_raciocinio=avaliacao["raciocinio"],
            hipotese_ia_modelo=avaliacao["modelo"][:60],
            hipotese_ia_em=timezone.now(),
        )
        logger.info(
            "anamnese_ia: registro=%s hipotese=%s (%s%%) concorda=%s",
            registro_id, avaliacao["hipotese"], avaliacao["confianca"], avaliacao["concorda"],
        )
    except Exception:
        logger.exception("anamnese_ia: refinar_hipotese_ia falhou (registro=%s)", registro_id)
