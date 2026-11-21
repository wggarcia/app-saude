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

# Teto de saída, não alvo: cobra-se o que é gerado, não o que é reservado. A
# resposta real tem ~180 tokens, então a folga aqui não custa nada — ela existe
# como rede de segurança caso o desligamento do pensamento não pegue (SDK
# antigo, modelo que ignore o campo). Com 350 e pensamento ligado, o modelo
# gastou tudo pensando e devolveu vazio; essa folga impede que isso se repita
# em silêncio.
MAX_TOKENS = 900

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


def vale_chamar_ia(diferencial) -> bool:
    """Decide se o caso merece uma chamada paga.

    Chama quando o motor está inseguro (confiança baixa) ou quando o 2º lugar
    está colado no 1º. Caso contrário, o motor já respondeu.

    Na dúvida (diferencial ausente ou malformado), chama — perder um caso
    ambíguo é pior que gastar uma fração de centavo.
    """
    if not isinstance(diferencial, list) or not diferencial:
        return True

    primeiro = diferencial[0]
    if not isinstance(primeiro, dict):
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
        '"raciocinio": "<2 a 3 frases, em português, citando os achados que '
        'sustentam e os que afastam>"}'
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
        try:
            return json.loads(texto[inicio:fim + 1])
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


def avaliar(dados: dict[str, Any], ranking: list[dict], conhecidas: set[str]) -> dict | None:
    """Chama o LLM. Devolve dict com a hipótese, ou None se a IA não puder rodar
    (sem chave, billing, timeout, resposta inválida) — o chamador segue com o motor."""
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.info("anamnese_ia: ANTHROPIC_API_KEY ausente — mantendo só o motor.")
        return None

    conteudo = (
        f"{_bloco_dados(dados)}\n\n"
        f"{_bloco_ranking(ranking)}\n\n"
        "LISTA FECHADA DE DOENÇAS PERMITIDAS:\n"
        + ", ".join(sorted(conhecidas))
        + "\n\nResponda apenas o JSON."
    )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        resposta = client.messages.create(
            model=MODELO_RACIOCINIO,
            max_tokens=MAX_TOKENS,
            system=_system_prompt(),
            messages=[{"role": "user", "content": conteudo}],
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
            extra_body={"thinking": {"type": "disabled"}},
        )

        # Nunca assumir que o primeiro bloco é texto: com pensamento ligado o
        # primeiro é o bloco de thinking, e `content[0].text` lê o lugar errado
        # (ou None). Procurar o bloco de texto explicitamente.
        bruto = next(
            (b.text for b in (resposta.content or [])
             if getattr(b, "type", None) == "text" and getattr(b, "text", None)),
            None,
        )
        if not bruto:
            logger.warning(
                "anamnese_ia: resposta sem texto (stop_reason=%s). Sem hipótese para este caso.",
                getattr(resposta, "stop_reason", "?"),
            )
            return None

        obj = _extrair_json(bruto)
        if not isinstance(obj, dict):
            logger.warning("anamnese_ia: resposta sem JSON utilizável: %r", bruto[:200])
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
            "modelo": MODELO_RACIOCINIO,
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

        avaliacao = avaliar(dados, ranking, set(DOENCAS_BRASIL.keys()))
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
