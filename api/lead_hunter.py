"""
lead_hunter.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Módulo de captura de leads.

Estratégias:
1. Google Places API — busca farmácias e clínicas por cidade
2. CSV Import — importa lista de leads de planilha
3. Busca manual — cria lead avulso

Sem dependências novas — usa apenas requests (já instalado).
Requer GOOGLE_PLACES_API_KEY no .env para a busca automática.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import csv
import io
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Mapeamento de termos de busca por tipo de lead
_QUERIES_GOOGLE = {
    "farmacia_dispensacao":  ["farmácia", "drogaria"],
    "farmacia_manipulacao":  ["farmácia de manipulação", "farmácia magistral"],
    "rede_farmacia":         ["rede de farmácias"],
    "medico_trabalho":       ["médico do trabalho", "medicina ocupacional"],
    "clinica_ocupacional":   ["clínica de medicina do trabalho", "clínica ocupacional"],
    "engenheiro_sst":        ["engenheiro de segurança do trabalho"],
    # Hospital (enterprise)
    "hospital_geral":         ["hospital", "hospital geral"],
    "hospital_especializado": ["hospital especializado", "hospital oncológico", "hospital cardiológico", "maternidade"],
    "rede_hospitalar":        ["rede hospitalar", "grupo hospitalar"],
    "santa_casa":             ["santa casa de misericórdia", "hospital filantrópico"],
    # Plano de saúde / operadora (enterprise)
    "operadora_plano":    ["operadora de plano de saúde", "plano de saúde"],
    "cooperativa_medica": ["cooperativa médica", "cooperativa de saúde"],
    "autogestao":         ["autogestão em saúde", "caixa de assistência à saúde"],
    "seguradora_saude":   ["seguradora de saúde", "seguro saúde"],
    # Empresas com força de trabalho em campo (não prestadoras de serviço de
    # medicina do trabalho) — o público certo pro App Ocupacional, que liga
    # gerência/RH/administrativo ao colaborador em campo, de qualquer setor —
    # inclusive o caso extremo disso: trabalhador embarcado/offshore, que fica
    # fisicamente isolado da gestão por semanas. "SESMT empresa" sozinho não
    # traz nada disso no Google Places; os termos por setor abaixo trazem.
    "empresa_sesmt": [
        "construtora", "transportadora", "empresa de logística",
        "indústria metalúrgica", "indústria alimentícia", "frigorífico",
        "mineradora", "usina", "distribuidora atacado",
        "empresa de terceirização de mão de obra", "empresa de segurança patrimonial",
        "cooperativa agrícola", "agroindústria",
        # Offshore / embarcados (NR-30, NR-37) — colaborador isolado no mar
        "empresa offshore", "operadora de petróleo e gás", "plataforma de petróleo",
        "empresa de navegação", "empresa marítima", "estaleiro", "empresa de cabotagem",
        "empresa de mergulho industrial",
        # Setores adicionais com colaborador disperso/em campo
        "empresa de energia elétrica", "empresa de energia eólica", "empresa de telecomunicações",
        "empresa de saneamento", "operadora portuária", "empresa florestal", "empresa de celulose",
        "siderúrgica", "empresa de manutenção industrial", "rede varejista", "rede hoteleira",
        "empresa de call center", "supermercado", "rede de supermercados", "shopping center",
    ],
}


def buscar_google_places(tipo: str, cidade: str, estado: str, max_resultados: int = 20) -> list[dict]:
    """
    Busca leads via Google Places API (Text Search).

    Retorna lista de dicts com: nome, empresa, email, telefone, cidade, estado,
    website, origem='google_places', dados_adicionais.

    Requer GOOGLE_PLACES_API_KEY configurado.
    """
    api_key = getattr(settings, "GOOGLE_PLACES_API_KEY", "") or getattr(settings, "GOOGLE_MAPS_BROWSER_KEY", "")
    if not api_key:
        raise ValueError("GOOGLE_PLACES_API_KEY não configurado. Configure no .env do VPS e Render.")

    queries = _QUERIES_GOOGLE.get(tipo, [tipo.replace("_", " ")])
    resultados = []
    seen_ids = set()

    # Distribui o limite entre TODOS os termos de busca em vez de esgotar no
    # primeiro — sem isso, "construtora" sozinho já enche os 20 resultados em
    # quase qualquer cidade e os outros ~24 setores (indústria, mercado,
    # offshore, agro...) nunca chegam a ser buscados de verdade.
    limite_por_termo = max(1, max_resultados // len(queries)) if queries else max_resultados

    for query_term in queries:
        query = f"{query_term} {cidade} {estado}"

        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={
                    "query": query,
                    "language": "pt-BR",
                    "region": "br",
                    "key": api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("google_places query='%s' erro: %s", query, exc)
            continue

        encontrados_neste_termo = 0
        for place in data.get("results", []):
            place_id = place.get("place_id", "")
            if place_id in seen_ids:
                continue
            seen_ids.add(place_id)

            # Buscar detalhes do lugar (telefone, website, etc.)
            detalhes = _buscar_detalhes_place(place_id, api_key)

            nome_empresa = place.get("name", "")
            website = detalhes.get("website", "")
            telefone = detalhes.get("formatted_phone_number", "")
            email_encontrado = _extrair_email_do_site(website) if website else ""

            lead_dict = {
                "nome":             nome_empresa,  # será sobrescrito pelo usuário
                "empresa":          nome_empresa,
                "cargo":            "",
                "email":            email_encontrado,  # achado no site; vazio = usuário preenche
                "telefone":         _normalizar_telefone(telefone),
                "cidade":           cidade,
                "estado":           estado.upper()[:2],
                "website":          website,
                "linkedin_url":     "",
                "origem":           "google_places",
                "dados_adicionais": {
                    "place_id":       place_id,
                    "endereco":       place.get("formatted_address", ""),
                    "rating":         place.get("rating", 0),
                    "tipos_google":   place.get("types", []),
                    "query_usada":    query,
                },
            }
            resultados.append(lead_dict)
            encontrados_neste_termo += 1
            if encontrados_neste_termo >= limite_por_termo or len(resultados) >= max_resultados:
                break

        if len(resultados) >= max_resultados:
            break

    return resultados


_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_EMAIL_EXCLUIR = (
    "sentry.io", "wixpress.com", "png", "jpg", "jpeg", "gif", "webp", "svg",
    # Placeholders de template de site (nunca são caixa real) — inglês e português
    "@example.", "@domain.", "@dominio.", "@exemplo.", "exemplo@", "seuemail@", "seunome@",
    "nome@dominio", "email@email", "test@test", "teste@teste", "@empresa.com.br",
    "@seusite.com", "@seudominio.com", "voce@seusite", "seusite@", "youremail@",
    "yourname@", "yourdomain.com", "email@seusite", "nome@empresa.com",
    # Escape JSON vazado no HTML da página (ex: / = "/") — regex casa a forma
    # de email mas não é um endereço real, é lixo de script embutido na página
    "u002f", "u0026", "u003d",
    # Domínio genérico de construtor de site (nunca é o domínio próprio da empresa)
    "@sitevip.com",
    # Endereços de widgets/plugins (WhatsApp, formulário) capturados por engano do HTML
    "@whatsapp.com", "form-whats@", "noreply@", "no-reply@",
)
# Domínios reservados pra documentação/teste (RFC 2606) — pega "qualquercoisa@algo.example",
# não só "@example.com" exato. Site comprometido/scraper às vezes injeta isso no HTML.
_TLD_RESERVADO_SUFIXO = (".example", ".test", ".invalid", ".localhost")
_PREFERENCIA_PREFIXO = ("contato", "comercial", "vendas", "atendimento", "sac", "info")


def _extrair_email_do_site(website: str) -> str:
    """
    Tenta achar um email de contato PUBLICADO na home do site da empresa.

    Muita farmácia/clínica pequena põe um "contato@..." ou "vendas@..." no
    rodapé do próprio site — isso evita ter que preencher email na mão pra
    cada lead do Google Maps. Falha silenciosamente (retorna "") se o site
    não responder, não tiver email visível, ou o e-mail parecer spam/lixo.
    """
    if not website:
        return ""
    try:
        resp = requests.get(website, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return ""
        candidatos = set(_EMAIL_REGEX.findall(resp.text))
    except Exception:
        return ""

    candidatos = {
        e.lower() for e in candidatos
        if not any(lixo in e.lower() for lixo in _EMAIL_EXCLUIR)
        and not e.lower().split("@")[-1].endswith(_TLD_RESERVADO_SUFIXO)
    }
    if not candidatos:
        return ""

    # Prioriza email genérico de contato/comercial sobre email pessoal aleatório
    for prefixo in _PREFERENCIA_PREFIXO:
        for email in candidatos:
            if email.startswith(prefixo):
                return email

    return sorted(candidatos)[0]


def _buscar_detalhes_place(place_id: str, api_key: str) -> dict:
    """Busca detalhes de um place (telefone, website) — 1 crédito cada."""
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields":   "website,formatted_phone_number",
                "language": "pt-BR",
                "key":      api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
    except Exception:
        return {}


def _normalizar_telefone(telefone: str) -> str:
    if not telefone:
        return ""
    # Remove +55 e espaços/parênteses
    return re.sub(r"[^\d]", "", telefone.replace("+55", ""))[:15]


def importar_csv(conteudo: str) -> list[dict]:
    """
    Importa leads de um CSV.

    Colunas esperadas (case-insensitive, separador vírgula ou ponto-e-vírgula):
    nome, empresa, email, telefone, cidade, estado, segmento, tipo, cargo, website, linkedin_url, notas

    Colunas mínimas obrigatórias: email, nome, empresa, cidade, estado, segmento

    Retorna lista de dicts prontos para criar LeadComercial.
    """
    # Detectar separador
    sep = ";" if conteudo.count(";") > conteudo.count(",") else ","

    reader = csv.DictReader(io.StringIO(conteudo), delimiter=sep)

    # Normalizar nomes de colunas
    fieldnames_norm = {k.strip().lower().replace(" ", "_"): k for k in (reader.fieldnames or [])}

    def _get(row: dict, key: str, default: str = "") -> str:
        col = fieldnames_norm.get(key, "")
        return str(row.get(col, "")).strip() if col else default

    leads = []
    erros = []

    for i, row in enumerate(reader, start=2):  # linha 1 = cabeçalho
        email = _get(row, "email")
        nome = _get(row, "nome") or _get(row, "nome_contato")
        empresa = _get(row, "empresa") or _get(row, "farmacia") or _get(row, "clinica")
        cidade = _get(row, "cidade")
        estado = _get(row, "estado", "SP")[:2].upper()
        segmento = _get(row, "segmento", "farmacia").lower()

        if not email or "@" not in email:
            erros.append(f"Linha {i}: email inválido ('{email}')")
            continue
        if not nome:
            erros.append(f"Linha {i}: nome obrigatório")
            continue
        if not empresa:
            empresa = nome  # fallback

        def _int_ou_none(valor: str):
            valor = (valor or "").strip()
            return int(valor) if valor.isdigit() else None

        lead_dict = {
            "nome":          nome,
            "empresa":       empresa,
            "cargo":         _get(row, "cargo"),
            "email":         email.lower(),
            "telefone":      _normalizar_telefone(_get(row, "telefone")),
            "cidade":        cidade or "Não informado",
            "estado":        estado,
            "segmento":      segmento if segmento in ("sst", "farmacia", "hospital", "plano_saude") else "farmacia",
            "tipo":          _get(row, "tipo", "farmacia_dispensacao"),
            "website":       _get(row, "website"),
            "linkedin_url":  _get(row, "linkedin_url") or _get(row, "linkedin"),
            "funcionarios_estimados": _int_ou_none(_get(row, "funcionarios") or _get(row, "colaboradores")),
            "unidades_estimadas":     _int_ou_none(_get(row, "unidades") or _get(row, "lojas")),
            "notas":         _get(row, "notas") or _get(row, "observacoes"),
            "origem":        "csv",
            "dados_adicionais": {},
        }
        leads.append(lead_dict)

    return {"leads": leads, "erros": erros, "total": len(leads)}


def template_csv_exemplo() -> str:
    """Retorna string CSV de exemplo para download."""
    linhas = [
        "nome,empresa,email,telefone,cidade,estado,segmento,tipo,cargo,website,funcionarios,unidades,notas",
        "Maria Silva,Farmácia Saúde Total,maria@farmaciatotal.com.br,(11)99999-9999,São Paulo,SP,farmacia,farmacia_dispensacao,Proprietária,https://farmaciatotal.com.br,,1,Interessada em SNGPC",
        "Dr. João Souza,Clínica Ocupacional ABC,joao@clinicaabc.com.br,(21)98888-8888,Rio de Janeiro,RJ,sst,clinica_ocupacional,Médico do Trabalho,https://clinicaabc.com.br,80,,Via LinkedIn — 80 colaboradores",
        "Ana Farmácia,Magistral Plus,ana@magistralplus.com.br,(51)97777-7777,Porto Alegre,RS,farmacia,farmacia_manipulacao,Gerente,,,3,Rede de 3 lojas",
    ]
    return "\n".join(linhas)
