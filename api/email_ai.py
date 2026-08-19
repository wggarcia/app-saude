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


def _link_materiais(segmento: str) -> str:
    # Cada segmento tem sua página de material ("folder" de entregas).
    if segmento not in ("sst", "farmacia", "hospital", "plano_saude"):
        return ""
    return f"{_base_url()}/materiais/{segmento}/"


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
O SoloCRT SST é um sistema completo de Saúde e Segurança do Trabalho — e o
DIFERENCIAL real dele (não é só "mais um sistema de compliance"):

- Assistente de IA (Claude) integrado ao painel: o gestor pergunta em
  linguagem natural coisas como "quantos ASOs vencem esse mês?" ou "quem
  está afastado há mais de 15 dias?" e a IA responde na hora, já gerando
  gráfico ou PDF pronto — sem precisar rodar relatório manual.
- Detecção automática de Nexo Técnico Epidemiológico (NTEP): o sistema
  cruza CID-10 com CNAE (conforme o Decreto 6.042/2007) e avisa o gestor
  ANTES de o INSS questionar um afastamento como ocupacional — antecipa o
  risco jurídico em vez de só reagir depois do fato.
- App Ocupacional (check-in de bem-estar): o colaborador faz um check-in
  diário e semanal (humor, energia, estresse, sono) direto pelo celular; o
  sistema calcula um índice de bem-estar por setor, detecta risco de
  burnout e permite denúncia anônima de conflito — o gestor vê tudo isso
  num painel, sem precisar de pesquisa de clima manual. Já incluso em
  todos os planos, não é um módulo à parte.
Além disso, automatiza toda a base:
- PCMSO completo (Programa de Controle Médico de Saúde Ocupacional)
- PPP digital com assinatura eletrônica e trilha de auditoria completa (exporta em 1 clique)
- eSocial SST: geração automática do XML (S-2210 CAT, S-2220 ASO, S-2240 FMA) pronto pra transmissão
- PGR / GRO com mapeamento de riscos e inventário automático
- CAT eletrônica vinculada automaticamente ao INSS
- Laudos técnicos NR-01 a NR-36, LTCAT, LIPE
Plano recomendado pro tamanho desta empresa: {plano_label} — {preco}/mês.
Teste grátis por 15 dias, sem cartão de crédito: {link}
Prefere tirar dúvida no WhatsApp antes? {whatsapp}
Quer conhecer o produto com calma antes de decidir? {materiais}
"""

_PRODUTO_FARMACIA = """
O SoloCRT Farmácia é um sistema de gestão completo — e o DIFERENCIAL real
dele (nenhum concorrente de PDV/gestão de farmácia tem isso hoje):

- Alerta epidemiológico regional com IA: um modelo de machine learning
  (RandomForest + Gradient Boosting) treinado com dados oficiais do
  DATASUS/SINAN calcula, região por região, a probabilidade de surto
  (dengue, gripe, etc.) na área da farmácia.
- Isso vira sinal direto de reabastecimento: o painel cruza esse risco
  epidemiológico com o estoque real da farmácia e projeta a demanda dos
  próximos 7 dias, mostrando algo como "reforçar hidratação, analgesia e
  repelente" ANTES da procura explodir na loja — não é estimativa genérica,
  é a prateleira dela.
- Relatório executivo gerado por IA (Claude) analisando os últimos 30 dias
  de vendas e estoque de verdade: tendências, alerta de ruptura e
  recomendação — pronto, sem o gestor precisar montar planilha.
Além disso, cobre toda a operação:
- PDV inteligente com controle de estoque em tempo real (método FEFO automático)
- SNGPC — envio automático para ANVISA sem erros manuais
- Manipulação magistral com rastreabilidade completa (lote, fornecedor, validade)
- Programa de fidelidade integrado ao PDV
- DRE e relatórios financeiros em tempo real
- Integração com distribuidores para pedido eletrônico
- e-commerce / vitrine digital
Plano recomendado pro tamanho desta farmácia: {plano_label} — {preco}/mês.
Teste grátis por 15 dias, sem cartão de crédito: {link}
Prefere tirar dúvida no WhatsApp antes? {whatsapp}
Quer conhecer o produto com calma antes de decidir? {materiais}
"""


_PRODUTO_HOSPITAL = """
O SoloCRT Hospital é um sistema de gestão hospitalar completo — e o DIFERENCIAL
real dele (o que sistema hospitalar genérico não entrega):

- Gestão de OPME com inteligência: catálogo com validação de registro ANVISA e
  AFE do fornecedor, motor de melhor custo-benefício (aponta marca alternativa e
  a economia), detecção de padrão de fraude por médico solicitante e esteira de
  autorização com junta médica. OPME é onde o hospital perde (ou protege) margem
  — e é exatamente aí que o sistema atua.
- TUSS/ANS ao vivo cruzado com ANVISA: busca o código TUSS oficial da ANS e a
  situação do produto na ANVISA na mesma tela, sem pular entre sistemas.
- Oncologia de verdade: protocolos de quimioterapia com cálculo de dose por
  superfície corporal, alerta de dose cumulativa (ex. cardiotoxicidade), ciclos,
  toxicidade e APAC — a jornada clínica do paciente, não só uma agenda.
- Gestão de leitos em tempo real (ocupação e giro) e painel epidemiológico
  regional integrado, que antecipa pressão de demanda sobre o hospital.
Além disso cobre a operação inteira: custos e DRG (com envio ao Valor Saúde
Brasil), CME, farmácia, SAME, qualidade/NSP, telemedicina e mais.
Quer ver tudo que o SoloCRT Hospital entrega, com calma, antes de conversar? {materiais}
É um produto enterprise: a entrada é por uma conversa/demonstração com o cenário
real do hospital, não por teste self-service. O plano é desenhado sob medida pro
porte na conversa.
Chamar no WhatsApp pra agendar: {whatsapp}
"""

_PRODUTO_PLANO_SAUDE = """
O SoloCRT Plano de Saúde é um sistema de gestão para operadoras — e o
DIFERENCIAL real dele (além do que a ANS já exige):

- IDSS calculado dos seus dados reais: o sistema calcula os componentes do
  Índice de Desempenho da Saúde Suplementar (IDQS/IDGA/IDSF/IDGR) a partir das
  suas guias, beneficiários, sinistros e prestadores, com os pesos oficiais da
  ANS — você acompanha seu IDSS o ano todo, não só quando a ANS divulga.
- Ressarcimento ao SUS (art. 32): gestão de ABI, competência, prazo de
  impugnação e valor cobrado/recebido — um dos maiores ralos de dinheiro de
  operadora, controlado de ponta a ponta.
- IA de apoio à autorização de guias: analisa e recomenda a decisão (com
  fallback por regras quando a IA não está disponível), cruzando TUSS, Rol de
  Procedimentos (RN 465) e diretrizes de utilização — inclui gestão de NIP com
  prazo em dias úteis.
- NPS do beneficiário, núcleo familiar (titular/dependentes), rede credenciada,
  corretores/comissões e portal do beneficiário.
Pra operadora maior tem ainda sinistralidade com IA e faturamento integrado.
Quer ver tudo que o SoloCRT Plano de Saúde entrega, com calma, antes de conversar? {materiais}
É um produto enterprise: a entrada é por uma conversa/demonstração com o cenário
real da operadora, não por teste self-service. O plano é desenhado sob medida na conversa.
Chamar no WhatsApp pra agendar: {whatsapp}
"""

# Instruções de sequência para segmentos ENTERPRISE (hospital, plano de saúde):
# a venda é consultiva e de ticket alto — o CTA é agendar uma conversa/demonstração,
# NUNCA um teste grátis self-service (um hospital não compra sistema de dezenas de
# milhares por mês clicando sozinho num "teste grátis").
_SEQ_INSTRUCAO_ENTERPRISE = {
    1: (
        "É o PRIMEIRO contato com um decisor de uma organização de grande porte. "
        "Tom consultivo, respeitoso e direto. Mostre que você entende a dor específica "
        "do setor dele e ABRA com o diferencial mais relevante. O CTA é convidar para "
        "uma CONVERSA/DEMONSTRAÇÃO com o cenário real da organização — via WhatsApp ou "
        "respondendo o email pra agendar. NÃO prometa teste grátis de 15 dias nem "
        "cadastro self-service — é enterprise, a entrada é por conversa. "
        "NÃO use 'Caro'/'Prezado'; use 'Olá [Nome],'."
    ),
    2: (
        "É o PRIMEIRO FOLLOW-UP (3 dias depois). Mencione o email anterior. Traga 2-3 "
        "benefícios concretos e mensuráveis pro tipo de organização dele. Seja mais "
        "curto. Reforce o convite pra uma conversa/demonstração — não teste grátis."
    ),
    3: (
        "É o SEGUNDO FOLLOW-UP (7 dias depois). Traga um ângulo de urgência real e "
        "específico do setor (ciclo de contratação, exigência regulatória, perda "
        "financeira recorrente que o produto resolve). Ofereça uma conversa curta e "
        "objetiva. CTA = agendar conversa."
    ),
    4: (
        "É o EMAIL FINAL (14 dias depois). Diga que é o último contato pra não insistir. "
        "Deixe a porta aberta pra quando fizer sentido, com o convite pra conversa. "
        "Seja humano e sem ressentimento."
    ),
}


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
    materiais = _link_materiais(lead.segmento)

    # Segmentos enterprise: venda consultiva de ticket alto (hospital, operadora de
    # plano de saúde). CTA = conversa/demonstração, nunca teste grátis self-service.
    is_enterprise = lead.segmento in ("hospital", "plano_saude")

    if lead.segmento == "sst":
        produto_desc = _PRODUTO_SST.format(preco=preco, link=link, plano_label=plano_label, whatsapp=whatsapp, materiais=materiais)
        if lead.tipo == "empresa_sesmt":
            perfil_lead = (
                "Empresa com colaboradores em campo (obra, rua, unidade, planta, embarcação/"
                "plataforma offshore) — NÃO é prestadora de serviço de medicina do trabalho. "
                "A dor dela é distância entre gerência/RH/administrativo e o colaborador que "
                "está em campo — em casos como offshore/embarcados essa distância é extrema "
                "(colaborador isolado por semanas). O App Ocupacional (conecta gestão ao "
                "colaborador em campo via celular, sem precisar de pesquisa de clima manual) "
                "é o encaixe perfeito pra ABRIR o email — não a lista de compliance. Se o nome/"
                "site da empresa sugerir operação offshore, marítima ou portuária, mencione "
                "esse cenário especificamente (colaborador embarcado) em vez de um exemplo genérico."
            )
        elif lead.tipo == "clinica_ocupacional":
            perfil_lead = (
                "Clínica/prestadora de serviço de medicina do trabalho — o cliente dela são "
                "OUTRAS empresas (ela emite ASO/PCMSO para os clientes dela). A dor é gerenciar "
                "o compliance de uma carteira de empresas-clientes, não força de trabalho própria "
                "em campo — foque em NTEP, PCMSO, eSocial ou o assistente de IA pra abrir o email."
            )
        else:
            perfil_lead = "Profissional de SST/medicina do trabalho — escolha o diferencial mais relevante pro cargo dele."
        contexto_lead = f"""
Nome: {lead.nome}
Empresa: {lead.empresa}
Cargo: {lead.cargo or 'profissional de SST'}
Email: {lead.email}
Cidade: {lead.cidade}/{lead.estado}
Tipo: {lead.get_tipo_display()}
Perfil do lead: {perfil_lead}
Colaboradores estimados: {lead.funcionarios_estimados or 'não informado — considere uma empresa pequena/média'}
Telefone: {lead.telefone or 'não informado'}
Website: {lead.website or 'não informado'}
"""
    elif lead.segmento == "farmacia":
        produto_desc = _PRODUTO_FARMACIA.format(preco=preco, link=link, plano_label=plano_label, whatsapp=whatsapp, materiais=materiais)
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
    elif lead.segmento == "hospital":
        produto_desc = _PRODUTO_HOSPITAL.format(whatsapp=whatsapp, materiais=materiais)
        contexto_lead = f"""
Nome: {lead.nome}
Hospital/organização: {lead.empresa}
Cargo: {lead.cargo or 'gestor/diretor'}
Email: {lead.email}
Cidade: {lead.cidade}/{lead.estado}
Tipo: {lead.get_tipo_display()}
Telefone: {lead.telefone or 'não informado'}
Website: {lead.website or 'não informado'}
Perfil: organização hospitalar de grande porte, venda consultiva/enterprise. Se o
cargo indicar área clínica, priorize OPME/oncologia; se for gestão/diretoria,
priorize custo/DRG/OPME (margem) e gestão de leitos.
"""
    else:  # plano_saude
        produto_desc = _PRODUTO_PLANO_SAUDE.format(whatsapp=whatsapp, materiais=materiais)
        contexto_lead = f"""
Nome: {lead.nome}
Operadora: {lead.empresa}
Cargo: {lead.cargo or 'gestor/diretor'}
Email: {lead.email}
Cidade: {lead.cidade}/{lead.estado}
Tipo: {lead.get_tipo_display()}
Telefone: {lead.telefone or 'não informado'}
Website: {lead.website or 'não informado'}
Perfil: operadora de plano de saúde, venda consultiva/enterprise. Ganchos mais
fortes: IDSS calculado dos dados reais e ressarcimento ao SUS (dinheiro direto).
"""

    instrucao_seq = _SEQ_INSTRUCAO_ENTERPRISE[seq] if is_enterprise else _SEQ_INSTRUCAO[seq]

    _base_system = (
        "Você é o fundador de uma startup de saúde brasileira chamada SoloCRT Saúde (site: solocrt.com.br). "
        "Você está escrevendo emails de prospecção para potenciais clientes do seu software. "
        "Escreva em português brasileiro, tom profissional mas próximo e humano. "
        "NUNCA invente dados ou casos de sucesso específicos que não foram fornecidos. "
        "Use apenas as informações fornecidas sobre o produto e o lead. "
        "IMPORTANTE sobre o que destacar: a descrição do produto abaixo tem alguns itens "
        "marcados como DIFERENCIAL real (coisa que nenhum concorrente genérico de gestão tem). "
        "Escolha o diferencial mais relevante pro tipo de lead e ABRA o email com ele — não com "
        "a lista de funcionalidades básicas/compliance, que qualquer sistema já oferece e não "
        "convence ninguém a trocar de fornecedor. O gancho tem que ser especificamente o que só "
        "o SoloCRT faz. Não cite todos os diferenciais de uma vez — email longo não é lido; "
        "escolha 1 pra abrir, cite outros de passagem se fizer sentido. "
    )
    if is_enterprise:
        _cta_system = (
            "Este é um produto ENTERPRISE de ticket alto (dezenas de milhares por mês) vendido a "
            "hospitais e operadoras — a compra é consultiva, passa por diretoria e processo formal. "
            "Por isso o CTA NÃO é teste grátis nem cadastro self-service: é convidar para uma "
            "CONVERSA/DEMONSTRAÇÃO com o cenário real da organização. Se um link de WhatsApp for "
            "fornecido (e não for 'não disponível'), use-o como forma de agendar: no CORPO_HTML como "
            "'<a href=\"LINK_EXATO\">agendar uma conversa no WhatsApp</a>', com a URL exatamente como "
            "foi fornecida. Também convide a pessoa a simplesmente responder o email pra marcar. "
            "NUNCA prometa teste grátis de 15 dias, 'comece agora' ou cadastro sem falar com ninguém. "
            "NÃO cite preço nem valores em reais — o desenho e o valor do plano são tratados na conversa. "
            "Um link de materiais é fornecido (o 'folder' com tudo que o produto entrega). Se ele não "
            "for vazio, inclua-o como CTA SECUNDÁRIO e discreto, algo como '<a href=\"LINK_EXATO\">ver "
            "tudo que o SoloCRT entrega</a>', usando a URL exatamente como fornecida — pra quem quer "
            "conhecer antes de agendar. Se vier vazio, não mencione. "
            "Assine como: Wagner Garcia, CEO | SoloCRT Saúde | solocrt.com.br | comercial@solocrt.com"
        )
    else:
        _cta_system = (
            "O CTA principal é sempre o link de teste grátis fornecido — no CORPO_HTML ele deve "
            "aparecer como um botão/link clicável de verdade: <a href=\"LINK_EXATO\">texto</a>, "
            "usando a URL exatamente como foi fornecida, sem alterar nem inventar outra URL. "
            "Se um link de WhatsApp for fornecido (e não for 'não disponível'), inclua-o como CTA "
            "SECUNDÁRIO e discreto — algo como '<a href=\"LINK_EXATO\">falar no WhatsApp</a>' — nunca "
            "como opção principal, só pra quem prefere tirar dúvida antes de clicar no teste grátis. "
            "Se vier 'não disponível', simplesmente não mencione WhatsApp. "
            "Um link de materiais também pode ser fornecido — ele leva pra uma página de apresentação "
            "do produto (não direto pros planos). Se e SÓ se ele for fornecido (não vazio), inclua-o "
            "como CTA TERCIÁRIO, ainda mais discreto, algo como '<a href=\"LINK_EXATO\">conhecer o "
            "produto</a>' ou '<a href=\"LINK_EXATO\">ver como funciona</a>'. NUNCA use a frase 'ver "
            "todos os planos' ou 'ver todos os módulos' pra esse link. Se o link de materiais vier "
            "vazio, simplesmente não mencione materiais. "
            "NUNCA sugira agendar uma reunião, call ou demonstração ao vivo — o teste grátis "
            "self-service substitui isso completamente. "
            "Assine como: Wagner Garcia, CEO | SoloCRT Saúde | solocrt.com.br | comercial@solocrt.com"
        )
    system = _base_system + _cta_system

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
