"""
Pipeline One Health — sinal de saúde animal como alerta precoce de doença humana.

Primeira fonte (Módulo 4): EPIZOOTIAS DE PRIMATAS NÃO-HUMANOS (PNH) para FEBRE
AMARELA, do Ministério da Saúde via API oficial de Dados Abertos (DEMAS).

Por que isso é One Health de verdade: no ciclo silvestre da febre amarela, os
macacos adoecem e morrem ANTES do primeiro caso humano. A morte de primatas
(epizootia) é, na prática, o sistema de alerta precoce mais confiável do país —
o Ministério da Saúde trata epizootia de PNH como evento de notificação
imediata justamente por isso. Trazer esse sinal para o Detector de Surto (IA #5)
permite ao gestor agir na janela entre "macaco morreu" e "humano adoeceu".

Fonte (oficial, pública, dado aberto do governo BR — sem licença comercial):
  GET https://apidadosabertos.saude.gov.br/arboviroses/febre-amarela-epzootias
  params: ano_ocor, uf_ocor, mes_ocor, macrorreg_ocor, limit, offset
  campos: uf_ocor, cod_uf_ocor, mun_ocor, cod_mun_ocor, data_ocor (DD/MM/AAAA),
          se_ocor (semana epi), mes_ocor, ano_ocor, macrorreg_ocor

Grava em FonteOficialAgregado no MESMO formato que pipeline_oficial.py, para que
o Detector de Surto (api/epidemiologia_ml.py) consuma sem qualquer adaptação:
  fonte_id  = "ms_epizootias_fa"
  indicador = "febre_amarela_epizootias_pnh"
  estado    = UF de ocorrência
  periodo   = "AAAA-Mmm" (mês; mais denso que semana para série esparsa)
  valor     = nº de epizootias de PNH notificadas naquela UF/mês
  unidade   = "epizootias"

NÃO inventa dado: se a API não responder, aborta e reporta — nada é gravado.
"""
import logging
import time
from collections import defaultdict

import requests

from .models import FonteOficialAgregado

logger = logging.getLogger(__name__)

DEMAS_EPIZOOTIAS_URL = (
    "https://apidadosabertos.saude.gov.br/arboviroses/febre-amarela-epzootias"
)
RESPONSE_KEY = "febre_amarela_epzootias"

FONTE_ID = "ms_epizootias_fa"
INDICADOR = "febre_amarela_epizootias_pnh"
FONTE_NOME = "MS / Epizootias PNH — Febre Amarela (Dados Abertos DEMAS)"
DOENCA = "Febre Amarela"  # precisa bater com DISEASE_WEIGHTS (api/epidemiologia.py)


def _get(params, *, tentativas=3, backoff=2.0):
    """GET com retry exponencial — a API pública oscila."""
    ultimo_erro = None
    for i in range(tentativas):
        try:
            r = requests.get(DEMAS_EPIZOOTIAS_URL, params=params, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 — rede pública instável
            ultimo_erro = exc
            espera = backoff * (i + 1)
            logger.warning("DEMAS epizootias falhou (%s/%s): %s — aguardando %ss",
                           i + 1, tentativas, exc, espera)
            time.sleep(espera)
    raise RuntimeError(f"DEMAS epizootias falhou definitivamente: {ultimo_erro}")


def coletar_epizootias(ano, *, limit=500, max_paginas=200):
    """Todas as epizootias de PNH de um ano, paginando a API. Lista de dicts crus."""
    registros = []
    offset = 0
    for _ in range(max_paginas):
        payload = _get({"ano_ocor": ano, "limit": limit, "offset": offset})
        lote = payload.get(RESPONSE_KEY, []) if isinstance(payload, dict) else []
        if not lote:
            break
        registros.extend(lote)
        if len(lote) < limit:
            break
        offset += limit
    return registros


def agregar_por_uf_mes(registros):
    """{(uf, "AAAA-Mmm"): contagem} — só registros com UF, ano e mês válidos."""
    agregado = defaultdict(int)
    for r in registros:
        uf = (r.get("uf_ocor") or "").strip().upper()
        ano = r.get("ano_ocor")
        mes = r.get("mes_ocor")
        if not uf or not ano or not mes:
            continue
        try:
            periodo = f"{int(ano)}-M{int(mes):02d}"
        except (TypeError, ValueError):
            continue
        agregado[(uf, periodo)] += 1
    return dict(agregado)


def persistir(agregado):
    """Grava/atualiza FonteOficialAgregado. Retorna nº de linhas gravadas."""
    gravados = 0
    for (uf, periodo), total in agregado.items():
        FonteOficialAgregado.objects.update_or_create(
            fonte_id=FONTE_ID,
            indicador=INDICADOR,
            estado=uf,
            cidade=None,
            codigo_ibge=None,
            periodo=periodo,
            defaults={
                "valor": float(total),
                "unidade": "epizootias",
                "fonte_nome": FONTE_NOME,
                "versao_fonte": "demas-v1",
                "metadados": {
                    "tipo": "one_health",
                    "sinal": "epizootia_pnh",
                    "doenca_humana": DOENCA,
                    "fonte_url": DEMAS_EPIZOOTIAS_URL,
                },
            },
        )
        gravados += 1
    return gravados


def atualizar_epizootias_fa(anos):
    """Coleta + agrega + persiste os anos pedidos. Retorna estatísticas."""
    total_registros = 0
    agregado_geral = {}
    for ano in anos:
        regs = coletar_epizootias(ano)
        total_registros += len(regs)
        for chave, valor in agregar_por_uf_mes(regs).items():
            agregado_geral[chave] = agregado_geral.get(chave, 0) + valor
    gravados = persistir(agregado_geral)
    ufs = sorted({uf for (uf, _p) in agregado_geral})
    return {
        "anos": list(anos),
        "epizootias_lidas": total_registros,
        "linhas_gravadas": gravados,
        "ufs": ufs,
    }
