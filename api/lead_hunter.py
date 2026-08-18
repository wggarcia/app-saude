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
    "empresa_sesmt":         ["SESMT empresa"],
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

            lead_dict = {
                "nome":             nome_empresa,  # será sobrescrito pelo usuário
                "empresa":          nome_empresa,
                "cargo":            "",
                "email":            "",            # usuário preenche ou usa Hunter.io depois
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
            if len(resultados) >= max_resultados:
                break

        if len(resultados) >= max_resultados:
            break

    return resultados


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
    import re
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
            "segmento":      segmento if segmento in ("sst", "farmacia") else "farmacia",
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
