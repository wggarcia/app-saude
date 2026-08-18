"""
email_ai.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Geração de emails de prospecção via Claude (Anthropic API).

Produz emails personalizados por segmento (SST / Farmácia) e por
sequência (1=inicial, 2=followup, 3=urgência, 4=despedida).
Sem custo adicional: usa o mesmo ANTHROPIC_API_KEY já configurado.

O CTA de todo email é o teste grátis self-service (/cadastro/?pacote=...),
NÃO uma call de demo — o lead entra sozinho no produto real, com o plano
certo pra ele já pré-selecionado. Preço vem sempre de api.planos.PACOTES_SAAS
(nunca hardcoded aqui), pra nunca ficar defasado do preço real cobrado.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging

from django.conf import settings

from .planos import PACOTES_SAAS

logger = logging.getLogger(__name__)

# Plano sugerido para o lead: se ele informou tamanho (funcionarios/unidades),
# usa o pacote que melhor comporta esse tamanho (LeadProspeccao.pacote_sugerido());
# senão cai no plano de entrada do segmento. O lead pode trocar de plano na
# própria tela de cadastro antes de confirmar.
def _base_url() -> str:
    # Mesmo padrão de api.email_service._base_url() — PUBLIC_BASE_URL é a
    # fonte única de verdade pro domínio onde este app Django está publicado
    # (app.solocrt.com.br), nunca hardcoded aqui.
    return getattr(settings, "PUBLIC_BASE_URL", "https://app.solocrt.com.br").rstrip("/")


def _link_trial(codigo: str) -> str:
    return f"{_base_url()}/cadastro/?pacote={codigo}"


def _preco_plano(codigo: str) -> str:
    pacote = PACOTES_SAAS.get(codigo, {})
    valor = pacote.get("mensal", 0)
    return f"R${valor:,.0f}".replace(",", ".")


def _label_plano(codigo: str) -> str:
    pacote = PACOTES_SAAS.get(codigo, {})
    return pacote.get("label", codigo)


def _link_whatsapp(lead) -> str:
    """
    Link wa.me — o LEAD é quem inicia a conversa ao clicar, então não exige
    API oficial do WhatsApp Business nem template aprovado pela Meta (isso
    só seria necessário pra ENVIAR mensagem pro número dele automaticamente,
    o que não fazemos).
    """
    import urllib.parse
    numero = getattr(settings, "WHATSAPP_COMERCIAL_NUMERO", "")
    if not numero:
        return ""
    texto = f"Olá! Vi o email sobre o SoloCRT Saúde e quero saber mais sobre o plano pra {lead.empresa}."
    return f"https://wa.me/{numero}?text={urllib.parse.quote(texto)}"

# ─── Textos de apoio por sequência ────────────────────────────────────────────

_SEQ_INSTRUCAO = {
    1: (
        "É o PRIMEIRO contato. Seja direto mas amigável. "
        "Mostre o problema que você resolve. "
        "Termine convidando para começar um teste grátis de 15 dias AGORA MESMO, "
        "sem cartão de crédito e sem precisar falar com ninguém — o link do email "
        "já leva direto pro cadastro com o plano certo pré-selecionado. "
        "NÃO peça uma call ou reunião de demonstração — o teste grátis É a demonstração. "
        "NÃO use palavras como 'Caro' ou 'Prezado'. "
        "Use 'Olá [Nome],'."
    ),
    2: (
        "É o PRIMEIRO FOLLOW-UP (3 dias após o primeiro email). "
        "Mencione que enviou um email antes. "
        "Apresente 3 benefícios concretos e mensuráveis. "
        "Seja mais curto que o primeiro email. "
        "Termine reforçando o link do teste grátis de 15 dias — não peça call."
    ),
    3: (
        "É o SEGUNDO FOLLOW-UP (7 dias após). "
        "Crie senso de urgência real: mencione que está montando "
        "lista de referência no estado do lead e tem vagas limitadas. "
        "Ofereça condição especial: 3 meses com 50%% de desconto "
        "para os primeiros 5 do estado que ativarem o teste grátis esta semana. "
        "Seja curto e direto. Termine com o link do teste grátis como CTA."
    ),
    4: (
        "É o EMAIL FINAL (14 dias após). "
        "Diga que é o último contato para não incomodar. "
        "Deixe a porta aberta: o link do teste grátis continua disponível quando "
        "ele quiser, sem compromisso e sem necessidade de falar com alguém antes. "
        "Seja humano e sem ressentimento. "
        "Termine com o link do teste grátis e o telefone/WhatsApp como alternativa "
        "só para quem preferir tirar dúvidas antes."
    ),
}

_PRODUTO_SST = """
O SoloCRT SST é um sistema completo de Saúde e Segurança do Trabalho que automatiza:
- PCMSO completo (Programa de Controle Médico de Saúde Ocupacional)
- PPP digital com assinatura eletrônica ICP-Brasil (exporta em 1 clique)
- eSocial SST: envio automático de S-2210 (CAT), S-2220 (ASO), S-2240 (FMA)
- PGR / GRO com mapeamento de riscos e inventário automático
- CAT eletrônica vinculada automaticamente ao INSS
- Laudos técnicos NR-01 a NR-36, LTCAT, LIPE
- Dashboard de indicadores de saúde ocupacional por empresa
Plano recomendado pro tamanho desta empresa: {plano_label} — {preco}/mês.
Teste grátis por 15 dias, sem cartão de crédito: {link}
Prefere tirar dúvida no WhatsApp antes? {whatsapp}
"""

_PRODUTO_FARMACIA = """
O SoloCRT Farmácia é um sistema de gestão completo para farmácias que cobre:
- PDV inteligente com controle de estoque em tempo real (método FEFO automático)
- SNGPC — envio automático para ANVISA sem erros manuais
- Manipulação magistral com rastreabilidade completa (lote, fornecedor, validade)
- Programa de fidelidade integrado ao PDV
- DRE e relatórios financeiros em tempo real
- IA que identifica produtos com risco de vencimento e oportunidades de venda cruzada
- Integração com distribuidores para pedido eletrônico
- e-commerce / vitrine digital
Plano recomendado pro tamanho desta farmácia: {plano_label} — {preco}/mês.
Teste grátis por 15 dias, sem cartão de crédito: {link}
Prefere tirar dúvida no WhatsApp antes? {whatsapp}
"""


def gerar_email(lead, numero_sequencia: int = 1) -> dict:
    """
    Gera assunto + corpo HTML + corpo texto para um email de prospecção.

    Retorna dict: {"assunto": str, "corpo_html": str, "corpo_texto": str}
    Lança ValueError se ANTHROPIC_API_KEY não estiver configurado.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY não configurado em settings.")

    seq = max(1, min(4, numero_sequencia))
    pacote_codigo = lead.pacote_sugerido()
    link = _link_trial(pacote_codigo)
    preco = _preco_plano(pacote_codigo)
    plano_label = _label_plano(pacote_codigo)
    whatsapp = _link_whatsapp(lead) or "não disponível"

    if lead.segmento == "sst":
        produto_desc = _PRODUTO_SST.format(preco=preco, link=link, plano_label=plano_label, whatsapp=whatsapp)
        contexto_lead = f"""
Nome: {lead.nome}
Empresa: {lead.empresa}
Cargo: {lead.cargo or 'profissional de SST'}
Email: {lead.email}
Cidade: {lead.cidade}/{lead.estado}
Tipo: {lead.get_tipo_display()}
Colaboradores estimados: {lead.funcionarios_estimados or 'não informado — considere uma empresa pequena/média'}
Telefone: {lead.telefone or 'não informado'}
Website: {lead.website or 'não informado'}
"""
    else:  # farmacia
        produto_desc = _PRODUTO_FARMACIA.format(preco=preco, link=link, plano_label=plano_label, whatsapp=whatsapp)
        contexto_lead = f"""
Nome: {lead.nome}
Farmácia: {lead.empresa}
Email: {lead.email}
Cidade: {lead.cidade}/{lead.estado}
Tipo: {lead.get_tipo_display()}
Unidades/lojas estimadas: {lead.unidades_estimadas or 'não informado — considere uma farmácia independente'}
Telefone: {lead.telefone or 'não informado'}
Website: {lead.website or 'não informado'}
"""

    instrucao_seq = _SEQ_INSTRUCAO[seq]

    system = (
        "Você é o fundador de uma startup de saúde brasileira chamada SoloCRT Saúde (site: solocrt.com.br). "
        "Você está escrevendo emails de prospecção para potenciais clientes do seu software. "
        "Escreva em português brasileiro, tom profissional mas próximo e humano. "
        "NUNCA invente dados ou casos de sucesso específicos que não foram fornecidos. "
        "Use apenas as informações fornecidas sobre o produto e o lead. "
        "O CTA principal é sempre o link de teste grátis fornecido — no CORPO_HTML ele deve "
        "aparecer como um botão/link clicável de verdade: <a href=\"LINK_EXATO\">texto</a>, "
        "usando a URL exatamente como foi fornecida, sem alterar nem inventar outra URL. "
        "Se um link de WhatsApp for fornecido (e não for 'não disponível'), inclua-o como CTA "
        "SECUNDÁRIO e discreto — algo como '<a href=\"LINK_EXATO\">falar no WhatsApp</a>' — nunca "
        "como opção principal, só pra quem prefere tirar dúvida antes de clicar no teste grátis. "
        "Se vier 'não disponível', simplesmente não mencione WhatsApp. "
        "NUNCA sugira agendar uma reunião, call ou demonstração ao vivo — o teste grátis "
        "self-service substitui isso completamente. "
        "Assine como: Wagner Garcia | SoloCRT Saúde | solocrt.com.br | comercial@solocrt.com"
    )

    user_msg = f"""
Produto:
{produto_desc}

Lead:
{contexto_lead}

Instrução para este email (sequência {seq}/4):
{instrucao_seq}

Por favor escreva:
1. ASSUNTO: (linha única, máx 60 caracteres, sem emojis)
2. CORPO_HTML: (HTML simples, sem CSS inline complexo, use <p>, <ul>, <li>, <strong>, <br>)
3. CORPO_TEXTO: (versão texto puro, sem tags HTML)

Separe cada seção com exatamente essas marcações:
---ASSUNTO---
(texto do assunto aqui)
---CORPO_HTML---
(html aqui)
---CORPO_TEXTO---
(texto puro aqui)
---FIM---
"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text

        # Parse sections
        assunto = _extract_section(raw, "---ASSUNTO---", "---CORPO_HTML---").strip()
        corpo_html = _extract_section(raw, "---CORPO_HTML---", "---CORPO_TEXTO---").strip()
        corpo_texto = _extract_section(raw, "---CORPO_TEXTO---", "---FIM---").strip()

        # Fallback if parsing fails
        if not assunto:
            assunto = f"SoloCRT Saúde — solução para {lead.get_tipo_display()}"
        if not corpo_html:
            corpo_html = f"<p>{corpo_texto or raw}</p>"

        logger.info("email_ai: gerado seq=%s lead=%s", seq, lead.email)
        return {"assunto": assunto, "corpo_html": corpo_html, "corpo_texto": corpo_texto}

    except Exception as exc:
        logger.error("email_ai error lead=%s: %s", lead.email, exc)
        raise


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    try:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        return text[start:end]
    except ValueError:
        return ""
