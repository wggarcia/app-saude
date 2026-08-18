"""
instagram_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Postagem automática de conteúdo no Instagram (conta própria da SoloCRT
Saúde) — atrai lead organicamente, sem mandar mensagem pra ninguém.

Como é a PRÓPRIA conta do dono (não gerencia conta de terceiros), a Meta
não exige revisão de app: basta a conta estar como "Instagram Tester" no
app criado em developers.facebook.com, com token gerado no Graph API
Explorer (permissões instagram_business_basic + instagram_business_content_publish).

Fluxo:
  1. gerar_conteudo_post()  → Claude escreve título curto (vai na imagem)
                              e legenda longa (vai na legenda do post)
  2. gerar_imagem_post()    → Pillow desenha um card com o título, salvo
                              numa pasta PÚBLICA dedicada (nunca a mesma
                              pasta de arquivos clínicos)
  3. publicar_instagram()   → Graph API: cria o media container a partir
                              da URL pública da imagem, depois publica

Publicar exige 2 chamadas (padrão da Instagram Content Publishing API):
  POST /{ig-user-id}/media          → cria container, retorna creation_id
  POST /{ig-user-id}/media_publish  → publica o container
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
import os
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Conteúdo (Claude) ─────────────────────────────────────────────────────────

_TEMA_SST = [
    "um erro comum que gera autuação do Ministério do Trabalho por PPP/PCMSO atrasado",
    "como o eSocial SST (S-2210/S-2220/S-2240) evita multa por atraso de envio",
    "por que PGR desatualizado é motivo comum de autuação em fiscalização",
]
_TEMA_FARMACIA = [
    "um erro comum de SNGPC que gera autuação da Vigilância Sanitária",
    "como controle de validade por FEFO evita perda de estoque",
    "por que rastreabilidade de lote na manipulação magistral é obrigatória",
]


def gerar_conteudo_post(segmento: str) -> dict:
    """
    Gera título curto (pra imagem) + legenda (pro post) via Claude, sobre
    um tema de compliance do segmento. Retorna {"titulo": str, "legenda": str}.
    Lança ValueError se ANTHROPIC_API_KEY não configurado.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY não configurado em settings.")

    import random
    temas = _TEMA_SST if segmento == "sst" else _TEMA_FARMACIA
    tema = random.choice(temas)
    setor_label = "SST / Medicina do Trabalho" if segmento == "sst" else "Farmácia"

    system = (
        "Você escreve posts de Instagram pro SoloCRT Saúde (solocrt.com.br), "
        "um software de gestão pra "
        f"{setor_label}. Tom educativo, direto, sem jargão excessivo. "
        "NUNCA invente estatística ou caso específico que não foi fornecido. "
        "O objetivo é ensinar algo útil de verdade, não só vender."
    )
    user_msg = f"""
Tema deste post: {tema}

Escreva:
1. TITULO: frase curta de até 60 caracteres, pra aparecer GRANDE numa imagem (sem emoji, sem ponto final)
2. LEGENDA: 3-5 linhas explicando o tema de forma prática, terminando com uma
   chamada leve pro perfil/bio (não inclua link, links não funcionam em legenda
   do Instagram). Pode usar 2-3 hashtags relevantes no final.

Separe com exatamente:
---TITULO---
(titulo)
---LEGENDA---
(legenda)
---FIM---
"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text
        titulo = _extract_section(raw, "---TITULO---", "---LEGENDA---").strip()
        legenda = _extract_section(raw, "---LEGENDA---", "---FIM---").strip()
        if not titulo:
            titulo = "Compliance em dia evita multa"
        if not legenda:
            legenda = titulo
        return {"titulo": titulo, "legenda": legenda}
    except Exception as exc:
        logger.error("instagram_service: erro ao gerar conteúdo segmento=%s: %s", segmento, exc)
        raise


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    try:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        return text[start:end]
    except ValueError:
        return ""


# ─── Imagem (Pillow) ────────────────────────────────────────────────────────────

# Paleta idêntica à do site público (templates/cadastro.html :root) — fundo
# escuro sempre igual, cor de destaque por segmento (gold=SST, cyan=Farmácia),
# igual ao mod-card "selected"/"selected-cyan" da tela de cadastro.
_COR_BG = "#05070a"
_COR_INK = "#f7f2e9"
_COR_DESTAQUE = {"sst": "#d9b86f", "farmacia": "#45ead9"}

_FONTES_CANDIDATAS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _carregar_fonte(tamanho: int):
    from PIL import ImageFont
    for caminho in _FONTES_CANDIDATAS:
        if os.path.exists(caminho):
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default(size=tamanho)


def gerar_imagem_post(titulo: str, segmento: str) -> str:
    """
    Desenha um card 1080x1080 (formato quadrado padrão do Instagram) com o
    título centralizado, salva na pasta pública dedicada, e retorna o NOME
    do arquivo (não o caminho completo) — usar com _url_publica_imagem().
    """
    from PIL import Image, ImageDraw

    tamanho = 1080
    cor_destaque = _COR_DESTAQUE.get(segmento, _COR_DESTAQUE["sst"])
    img = Image.new("RGB", (tamanho, tamanho), color=_COR_BG)
    draw = ImageDraw.Draw(img)

    # Barra de destaque no topo — mesmo papel visual do "selected"/"selected-cyan"
    # da tela de cadastro (cor de módulo como sinal, fundo sempre escuro).
    draw.rectangle([(0, 0), (tamanho, 14)], fill=cor_destaque)

    fonte_titulo = _carregar_fonte(64)
    fonte_marca = _carregar_fonte(36)

    # Quebra o título em linhas que cabem na largura do card
    palavras = titulo.split()
    linhas, linha_atual = [], ""
    largura_max = tamanho - 160
    for palavra in palavras:
        teste = f"{linha_atual} {palavra}".strip()
        bbox = draw.textbbox((0, 0), teste, font=fonte_titulo)
        if bbox[2] - bbox[0] <= largura_max:
            linha_atual = teste
        else:
            linhas.append(linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(linha_atual)

    altura_linha = 78
    altura_total = len(linhas) * altura_linha
    y = (tamanho - altura_total) // 2

    for linha in linhas:
        bbox = draw.textbbox((0, 0), linha, font=fonte_titulo)
        x = (tamanho - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), linha, font=fonte_titulo, fill=cor_destaque)
        y += altura_linha

    marca = "SoloCRT Saúde"
    bbox = draw.textbbox((0, 0), marca, font=fonte_marca)
    draw.text((((tamanho - (bbox[2] - bbox[0])) // 2), tamanho - 100), marca, font=fonte_marca, fill=_COR_INK)

    pasta = settings.SOCIAL_MEDIA_CACHE_DIR
    os.makedirs(pasta, exist_ok=True)
    nome_arquivo = f"{uuid.uuid4().hex}.png"
    img.save(os.path.join(pasta, nome_arquivo), format="PNG")

    logger.info("instagram_service: imagem gerada %s (segmento=%s)", nome_arquivo, segmento)
    return nome_arquivo


# ─── Publicação (Graph API) ────────────────────────────────────────────────────

def publicar_instagram(imagem_url_publica: str, legenda: str) -> tuple[bool, str]:
    """
    Publica no Instagram via Graph API (2 chamadas: cria container, publica).

    `imagem_url_publica` precisa ser uma URL HTTPS acessível sem autenticação
    (o Instagram busca a imagem do lado deles, não aceita upload direto de
    arquivo neste fluxo simples).

    Retorna (sucesso, media_id_ou_mensagem_de_erro).
    """
    token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "")
    ig_user_id = getattr(settings, "INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    versao = getattr(settings, "INSTAGRAM_GRAPH_API_VERSION", "v21.0")

    if not token or not ig_user_id:
        return False, "INSTAGRAM_ACCESS_TOKEN ou INSTAGRAM_BUSINESS_ACCOUNT_ID não configurados."

    base = f"https://graph.facebook.com/{versao}/{ig_user_id}"

    try:
        resp = requests.post(
            f"{base}/media",
            data={"image_url": imagem_url_publica, "caption": legenda, "access_token": token},
            timeout=30,
        )
        data = resp.json()
        if resp.status_code != 200 or "id" not in data:
            erro = data.get("error", {}).get("message", resp.text[:300])
            logger.error("instagram_service: erro ao criar container: %s", erro)
            return False, erro
        creation_id = data["id"]
    except Exception as exc:
        logger.error("instagram_service: exceção ao criar container: %s", exc)
        return False, str(exc)

    try:
        resp = requests.post(
            f"{base}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=30,
        )
        data = resp.json()
        if resp.status_code != 200 or "id" not in data:
            erro = data.get("error", {}).get("message", resp.text[:300])
            logger.error("instagram_service: erro ao publicar: %s", erro)
            return False, erro
        logger.info("instagram_service: publicado media_id=%s", data["id"])
        return True, data["id"]
    except Exception as exc:
        logger.error("instagram_service: exceção ao publicar: %s", exc)
        return False, str(exc)
