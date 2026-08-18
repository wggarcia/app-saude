"""
trial_nurture.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Demonstração" automática durante os 15 dias de trial self-service.

Como não há mais uma call de demo ao vivo (o CTA do agente de prospecção
manda o lead direto pro cadastro), esta sequência substitui o vendedor:
guia a empresa em trial pelas telas-chave do próprio segmento, checando
o que ela já fez (OnboardingPasso) pra não mandar mensagem repetida, e
no fim do trial empurra pra ativação do plano pago.

4 pontos de contato, disparados por dias desde TrialEmpresa.iniciado_em:
  dia 1  → boas-vindas + primeiro passo prático
  dia 4  → destaca o que falta fazer (se nada foi feito, reforça o básico)
  dia 9  → funcionalidade de maior impacto pro segmento (ROI)
  dia 13 → trial acabando, link direto pra ativar o plano
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Dias de trial em que disparamos contato, e o "tema" de cada um.
PONTOS_DE_CONTATO = {
    1:  "boas_vindas",
    4:  "checkin",
    9:  "valor",
    13: "ativacao",
}

_TEMA_INSTRUCAO = {
    "boas_vindas": (
        "É o email de boas-vindas, enviado no dia 1 do trial. "
        "Comemore a empresa ter começado o teste grátis. "
        "Indique O PRIMEIRO PASSO prático e concreto pra ela fazer agora "
        "(um único passo, não uma lista). "
        "Tom animado, curto, sem parecer robótico."
    ),
    "checkin": (
        "É um check-in no dia 4 do trial. "
        "Se a empresa AINDA NÃO completou o primeiro passo (ver 'progresso' abaixo), "
        "reforce esse mesmo passo de um jeito diferente, oferecendo ajuda. "
        "Se ela JÁ avançou, parabenize e sugira o PRÓXIMO passo lógico. "
        "Curto, direto, uma pergunta no final."
    ),
    "valor": (
        "É o email do dia 9, mostrando a funcionalidade de MAIOR IMPACTO "
        "do produto pro segmento dela — a que mais economiza tempo ou "
        "evita risco de multa/autuação. Seja específico e prático, "
        "com um exemplo concreto de uso."
    ),
    "ativacao": (
        "É o email do dia 13 — faltam só 2 dias de trial. "
        "Avise que o período está acabando. "
        "Convide a ativar o plano AGORA pra não perder acesso aos dados já cadastrados. "
        "Inclua o link de ativação como CTA principal. "
        "Ofereça ajuda por WhatsApp pra quem tiver dúvida antes de decidir. "
        "Tom de urgência gentil, não agressivo."
    ),
}

_LINK_ATIVACAO = "https://solocrt.com.br/pagamento/"


def gerar_nurture(empresa, tema: str, progresso: str) -> dict:
    """
    Gera assunto + HTML + texto para um ponto de contato do trial.

    `progresso` é uma descrição curta do que a empresa já fez (ou "nada ainda"),
    montada a partir de OnboardingPasso pelo chamador.

    Retorna dict {"assunto", "corpo_html", "corpo_texto"}.
    Lança ValueError se ANTHROPIC_API_KEY não configurado.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY não configurado em settings.")

    codigo = empresa.pacote_codigo or ""
    if codigo.startswith("empresa_"):
        setor_label = "SST / Medicina do Trabalho"
    elif codigo.startswith("farmacia_"):
        setor_label = "Farmácia"
    else:
        raise ValueError(
            f"trial_nurture só cobre SST/Farmácia — pacote '{codigo}' é de outro segmento."
        )
    instrucao = _TEMA_INSTRUCAO.get(tema, _TEMA_INSTRUCAO["checkin"])

    system = (
        "Você é o fundador do SoloCRT Saúde (solocrt.com.br), escrevendo para uma "
        "empresa que JÁ está usando o produto em período de teste gratuito — "
        "não é prospecção fria, é acompanhamento de quem já entrou. "
        "Tom próximo, prestativo, como quem realmente quer que a empresa tenha sucesso. "
        "NUNCA invente números ou casos que não foram fornecidos. "
        "Se houver um link de ativação, use <a href=\"LINK_EXATO\">texto</a> com a URL exata fornecida. "
        "Assine como: Wagner Garcia | SoloCRT Saúde"
    )

    user_msg = f"""
Empresa: {empresa.nome}
Segmento: {setor_label}
Progresso no trial até agora: {progresso}
Link de ativação do plano (usar só se a instrução pedir): {_LINK_ATIVACAO}

Instrução para este email:
{instrucao}

Escreva:
1. ASSUNTO: (linha única, máx 60 caracteres, sem emojis)
2. CORPO_HTML: (HTML simples: <p>, <ul>, <li>, <strong>, <br>, <a>)
3. CORPO_TEXTO: (texto puro)

Separe com exatamente:
---ASSUNTO---
(assunto)
---CORPO_HTML---
(html)
---CORPO_TEXTO---
(texto)
---FIM---
"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text

        assunto = _extract_section(raw, "---ASSUNTO---", "---CORPO_HTML---").strip()
        corpo_html = _extract_section(raw, "---CORPO_HTML---", "---CORPO_TEXTO---").strip()
        corpo_texto = _extract_section(raw, "---CORPO_TEXTO---", "---FIM---").strip()

        if not assunto:
            assunto = "Como está indo seu teste grátis no SoloCRT?"
        if not corpo_html:
            corpo_html = f"<p>{corpo_texto or raw}</p>"

        return {"assunto": assunto, "corpo_html": corpo_html, "corpo_texto": corpo_texto}

    except Exception as exc:
        logger.error("trial_nurture: erro ao gerar tema=%s empresa=%s: %s", tema, empresa.id, exc)
        raise


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    try:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        return text[start:end]
    except ValueError:
        return ""
