from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from time import time

import requests
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone

from .models import FonteOficialAgregado, FonteOficialExecucao, RegistroSintoma
from .utils_cidades import carregar_base


_CACHE = {"created_at": 0.0, "payload": None}
_POP_CACHE = {}
_CACHE_TTL_SECONDS = 15 * 60
POPULATION_YEAR = datetime.now().year - 1
OFFICIAL_HTTP_TIMEOUT_SECONDS = 2.5
OFFICIAL_PANEL_TIME_BUDGET_SECONDS = 10
MUNICIPIOS_OFICIAIS_SENTINELA = [
    {"cidade": "Rio de Janeiro", "estado": "RJ", "total": 0},
    {"cidade": "São Paulo", "estado": "SP", "total": 0},
    {"cidade": "Belo Horizonte", "estado": "MG", "total": 0},
    {"cidade": "Salvador", "estado": "BA", "total": 0},
    {"cidade": "Recife", "estado": "PE", "total": 0},
    {"cidade": "Fortaleza", "estado": "CE", "total": 0},
    {"cidade": "Curitiba", "estado": "PR", "total": 0},
    {"cidade": "Manaus", "estado": "AM", "total": 0},
]

UF_CODES = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}

FONTES_OFICIAIS = [
    {
        "nome": "InfoDengue / Fiocruz",
        "tipo": "arboviroses",
        "cobertura": "municipal e semanal",
        "doencas": ["Dengue", "Chikungunya", "Zika"],
        "status": "integracao_api",
        "uso_no_saas": "Camada oficial para comparar sinais colaborativos com alertas e incidencia municipal.",
        "url": "https://info.dengue.mat.br/",
    },
    {
        "nome": "InfoGripe / Fiocruz",
        "tipo": "SRAG e sindromes respiratorias",
        "cobertura": "Brasil, estados e capitais",
        "doencas": ["SRAG", "Influenza", "COVID-19", "Virus respiratorios"],
        "status": "integracao_resiliente",
        "uso_no_saas": "Camada oficial respiratoria para apoiar hospitais e governo.",
        "url": "https://info.gripe.fiocruz.br/",
    },
    {
        "nome": "OpenDataSUS / Ministerio da Saude",
        "tipo": "microdados oficiais",
        "cobertura": "nacional",
        "doencas": ["COVID-19", "vacinacao", "SRAG", "agravos notificados", "Febre Amarela", "Leptospirose", "Malaria", "Sarampo", "Meningite"],
        "status": "catalogada_para_pipeline",
        "uso_no_saas": "Base oficial para historico, validacao e auditoria de indicadores.",
        "url": "https://opendatasus.saude.gov.br/",
    },
    {
        "nome": "DATASUS",
        "tipo": "sistemas nacionais de saude",
        "cobertura": "nacional",
        "doencas": ["SINAN", "SIM", "SIH", "SIVEP-Gripe", "Febre Amarela", "Leptospirose", "Malaria", "Sarampo", "Meningite"],
        "status": "catalogada_para_pipeline",
        "uso_no_saas": "Camada institucional para notificacao, mortalidade, internacao e series historicas.",
        "url": "https://datasus.saude.gov.br/",
    },
    {
        "nome": "IBGE",
        "tipo": "territorio e denominadores populacionais",
        "cobertura": "municipios, estados e Brasil",
        "doencas": [],
        "status": "integracao_api",
        "uso_no_saas": "Normalizacao de municipios, estados, geocodigos e calculo por 100 mil habitantes.",
        "url": "https://apisidra.ibge.gov.br/",
    },
]

OPENDATASUS_DATASUS_MANIFEST = [
    {
        "id": "sivep_gripe",
        "nome": "SIVEP-Gripe / SRAG",
        "fonte": "OpenDataSUS / Ministerio da Saude",
        "finalidade": "Historico oficial de SRAG, hospitalizacao, evolucao e classificacao final.",
        "indicadores": [
            "casos de SRAG por municipio/estado",
            "hospitalizacoes",
            "evolucao clinica",
            "classificacao final",
            "serie historica respiratoria",
        ],
        "periodicidade_recomendada": "diaria ou semanal",
        "estrategia": "coleta assíncrona incremental, agregacao por municipio/semana e cache para dashboard",
        "risco_operacional": "alto",
        "motivo_cuidado": "microdados grandes; nao devem ser baixados durante abertura do painel",
        "fonte_exata_inicial": "https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026",
        "recurso_inicial": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2026/INFLUD26-23-03-2026.csv",
        "status": "catalogado_sem_download",
    },
    {
        "id": "sim_mortalidade",
        "nome": "SIM / Mortalidade",
        "fonte": "DATASUS",
        "finalidade": "Mortalidade, letalidade e obitos por causa, localidade e periodo.",
        "indicadores": [
            "obitos por causa",
            "letalidade estimada",
            "mortalidade por 100 mil",
            "excesso de mortalidade quando aplicavel",
        ],
        "periodicidade_recomendada": "mensal ou conforme disponibilidade oficial",
        "estrategia": "amostra controlada por HTTP Range sobre o CSV oficial DO*OPEN; agregacao por municipio/competencia sem armazenar microdados",
        "risco_operacional": "alto",
        "motivo_cuidado": "dados sensiveis e historicos amplos; exige rastreabilidade e validacao",
        "fonte_exata_inicial": "https://opendatasus.saude.gov.br/dataset/sim",
        "recurso_inicial": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SIM/DO24OPEN.csv",
        "status": "download_habilitado",
    },
    {
        "id": "sih_internacoes",
        "nome": "SIH-CNES / Capacidade hospitalar",
        "fonte": "DATASUS / CNES",
        "finalidade": "Capacidade instalada, leitos SUS e leitos de UTI por municipio para medir pressao assistencial.",
        "indicadores": [
            "leitos SUS instalados por municipio/UF",
            "leitos de UTI SUS",
            "capacidade hospitalar regional",
            "denominador para pressao assistencial",
        ],
        "periodicidade_recomendada": "mensal por competencia",
        "estrategia": "amostra controlada por HTTP Range sobre o CSV oficial de Leitos SUS/CNES; agregacao por municipio/competencia",
        "risco_operacional": "medio",
        "motivo_cuidado": "microdados de internacao (RD/SIH) so existem como DBC na FTP; usamos a capacidade instalada (CNES) como camada oficial de pressao hospitalar",
        "fonte_exata_inicial": "https://opendatasus.saude.gov.br/dataset/",
        "recurso_inicial": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/Leitos_SUS/Leitos_2025.csv",
        "status": "download_habilitado",
    },
    {
        "id": "sinan_agravos",
        "nome": "SINAN / Agravos de notificacao",
        "fonte": "DATASUS / Ministerio da Saude",
        "finalidade": "Agravos notificados, investigacao epidemiologica e validacao institucional.",
        "indicadores": [
            "casos notificados por agravo",
            "serie historica por territorio",
            "comparacao com sinais antecipados do app",
        ],
        "periodicidade_recomendada": "conforme publicacao oficial",
        "estrategia": "worker baixa o .csv.zip oficial (com teto de tamanho), descompacta em streaming e agrega notificacoes por municipio/semana epidemiologica sem armazenar microdados",
        "risco_operacional": "medio_alto",
        "motivo_cuidado": "arquivo compactado de grande volume; processado em job controlado, nao no carregamento do painel",
        "fonte_exata_inicial": "https://opendatasus.saude.gov.br/dataset/arboviroses-dengue",
        "recurso_inicial": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR25.csv.zip",
        "status": "download_habilitado",
    },
    {
        "id": "sinan_chikungunya",
        "nome": "SINAN / Febre de Chikungunya",
        "fonte": "DATASUS / Ministerio da Saude",
        "finalidade": "Notificacoes de Chikungunya por territorio para vigilancia de arboviroses.",
        "indicadores": [
            "casos notificados de chikungunya por territorio",
            "serie historica por semana epidemiologica",
        ],
        "periodicidade_recomendada": "conforme publicacao oficial",
        "estrategia": "worker baixa o .csv.zip oficial (com teto de tamanho), descompacta em streaming e agrega notificacoes por municipio/semana epidemiologica sem armazenar microdados",
        "risco_operacional": "medio_alto",
        "motivo_cuidado": "arquivo compactado de grande volume; processado em job controlado, nao no carregamento do painel",
        "fonte_exata_inicial": "https://dadosabertos.saude.gov.br/dataset/arboviroses-febre-de-chikungunya",
        "recurso_inicial": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Chikungunya/csv/CHIKBR25.csv.zip",
        "status": "download_habilitado",
    },
    {
        "id": "sinan_zika",
        "nome": "SINAN / Virus Zika",
        "fonte": "DATASUS / Ministerio da Saude",
        "finalidade": "Notificacoes de Zika por territorio para vigilancia de arboviroses.",
        "indicadores": [
            "casos notificados de zika por territorio",
            "serie historica por semana epidemiologica",
        ],
        "periodicidade_recomendada": "conforme publicacao oficial",
        "estrategia": "worker baixa o .csv.zip oficial (com teto de tamanho), descompacta em streaming e agrega notificacoes por municipio/semana epidemiologica sem armazenar microdados",
        "risco_operacional": "medio_alto",
        "motivo_cuidado": "arquivo compactado de grande volume; processado em job controlado, nao no carregamento do painel",
        "fonte_exata_inicial": "https://dadosabertos.saude.gov.br/dataset/arboviroses-zika-virus",
        "recurso_inicial": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Zikavirus/csv/ZIKABR25.csv.zip",
        "status": "download_habilitado",
    },
    {
        "id": "vacinacao",
        "nome": "Vacinacao / Campanhas",
        "fonte": "OpenDataSUS / Ministerio da Saude",
        "finalidade": "Cobertura de acoes de controle e contexto para risco territorial.",
        "indicadores": [
            "cobertura vacinal",
            "campanhas por territorio",
            "relacao entre cobertura e risco",
        ],
        "periodicidade_recomendada": "semanal ou mensal",
        "estrategia": "particoes Spark com nome rotativo; a URL vigente e resolvida em tempo de execucao a partir da pagina oficial do recurso e amostrada por HTTP Range, agregando doses por municipio/mes sem armazenar microdados",
        "risco_operacional": "medio",
        "motivo_cuidado": "arquivos de grande volume e cuidado LGPD em granularidades menores; processado como amostra controlada, nao no carregamento do painel",
        "fonte_exata_inicial": "https://dadosabertos.saude.gov.br/dataset/covid-19-vacinacao",
        "recurso_inicial": "resolvido dinamicamente: SIPNI/COVID/completo/part-*.csv",
        "status": "download_habilitado",
    },
]


def _catalogo_opendatasus_datasus():
    prioridade = {
        "sivep_gripe": 1,
        "sim_mortalidade": 2,
        "sih_internacoes": 3,
        "sinan_agravos": 4,
        "vacinacao": 5,
    }
    return {
        "status": "manifesto_seguro",
        "regra_operacional": "Nao baixar microdados no carregamento do dashboard. Usar tarefas assíncronas, cache e agregados.",
        "fontes": sorted(
            OPENDATASUS_DATASUS_MANIFEST,
            key=lambda item: prioridade.get(item["id"], 99),
        ),
        "proxima_etapa_tecnica": [
            "criar tabelas de agregados oficiais por municipio/semana",
            "criar job assíncrono por fonte e competencia",
            "registrar data de coleta, fonte, versao e status",
            "expor apenas indicadores agregados ao dashboard",
        ],
        "seguranca_download": {
            "sivep_gripe": "habilitado: amostra controlada via HTTP Range e limite de linhas (SRAG)",
            "sim_mortalidade": "habilitado: amostra controlada via HTTP Range sobre o CSV oficial DO*OPEN (obitos)",
            "sih_internacoes": "habilitado: amostra controlada via HTTP Range sobre o CSV de Leitos SUS/CNES (capacidade hospitalar)",
            "sinan_agravos": "habilitado: worker baixa e descompacta o .csv.zip oficial em streaming, agregando dengue por municipio/semana",
            "vacinacao": "habilitado: resolver dinamico extrai a particao vigente da pagina oficial e amostra por HTTP Range, agregando doses por municipio/mes",
            "microdados_completos": "persistencia de microdados brutos permanece bloqueada: gravamos somente agregados",
        },
    }


def _status_execucoes_oficiais():
    execucoes = FonteOficialExecucao.objects.all()[:8]
    agregados_total = FonteOficialAgregado.objects.count()
    return {
        "agregados_disponiveis": agregados_total,
        "ultimas_execucoes": [
            {
                "id": item.id,
                "fonte_id": item.fonte_id,
                "fonte_nome": item.fonte_nome,
                "status": item.status,
                "modo": item.modo,
                "uf": item.uf,
                "periodo_inicio": item.periodo_inicio,
                "periodo_fim": item.periodo_fim,
                "registros_lidos": item.registros_lidos,
                "agregados_gerados": item.agregados_gerados,
                "mensagem": item.mensagem,
                "criado_em": item.criado_em.isoformat(),
            }
            for item in execucoes
        ],
    }


def _safe_rate(value, population):
    try:
        value = float(value or 0)
        population = int(population or 0)
    except (TypeError, ValueError):
        return None
    if population <= 0:
        return None
    return round((value / population) * 100000, 2)


def _municipios_por_sinal(limit=8):
    recentes = RegistroSintoma.objects.filter(
        data_registro__gte=timezone.now() - timezone.timedelta(days=14),
    )
    rows = (
        recentes.exclude(cidade__isnull=True)
        .exclude(cidade="")
        .values("cidade", "estado")
        .annotate(total=Count("id"))
        .order_by("-total")[:limit]
    )
    municipios = list(rows)
    existentes = {
        (
            str(item.get("cidade") or "").strip().lower(),
            _normalizar_estado(item.get("estado")),
        )
        for item in municipios
    }

    for item in MUNICIPIOS_OFICIAIS_SENTINELA:
        key = (item["cidade"].strip().lower(), _normalizar_estado(item["estado"]))
        if key not in existentes:
            municipios.append(item)
            existentes.add(key)
        if len(municipios) >= limit:
            break

    return municipios[:limit]


def _normalizar_estado(valor):
    raw = (valor or "").strip()
    if len(raw) == 2:
        return raw.upper()
    nomes = {
        "rio de janeiro": "RJ",
        "sao paulo": "SP",
        "são paulo": "SP",
        "minas gerais": "MG",
        "bahia": "BA",
        "parana": "PR",
        "paraná": "PR",
        "rio grande do sul": "RS",
        "santa catarina": "SC",
        "goias": "GO",
        "goiás": "GO",
        "distrito federal": "DF",
    }
    return nomes.get(raw.lower(), raw.upper())


def _municipio_ibge(cidade, estado):
    cidade_norm = (cidade or "").strip().lower()
    estado_norm = _normalizar_estado(estado)
    if not cidade_norm or not estado_norm:
        return None

    for item in carregar_base():
        uf = UF_CODES.get(item.get("codigo_uf"))
        if uf == estado_norm and str(item.get("nome", "")).strip().lower() == cidade_norm:
            return item
    return None


def _fetch_populacao_ibge(codigo_ibge):
    cache_key = f"{codigo_ibge}:{POPULATION_YEAR}"
    if cache_key in _POP_CACHE:
        return _POP_CACHE[cache_key]

    url = f"https://apisidra.ibge.gov.br/values/t/6579/n6/{codigo_ibge}/v/9324/p/{POPULATION_YEAR}"
    response = requests.get(url, timeout=OFFICIAL_HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()

    population = None
    if isinstance(data, list) and len(data) > 1:
        raw_value = data[1].get("V")
        if raw_value not in {None, "...", "-"}:
            population = int(float(str(raw_value).replace(",", ".")))

    _POP_CACHE[cache_key] = population
    return population


def _fetch_infodengue(codigo_ibge, disease, ano):
    params = {
        "geocode": codigo_ibge,
        "disease": disease,
        "format": "json",
        "ew_start": 1,
        "ew_end": 53,
        "ey_start": ano,
        "ey_end": ano,
    }
    response = requests.get(
        "https://info.dengue.mat.br/api/alertcity",
        params=params,
        timeout=OFFICIAL_HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        return None

    latest = data[-1]
    return {
        "doenca": disease,
        "semana_epidemiologica": latest.get("SE"),
        "casos_notificados": latest.get("casos"),
        "casos_estimados": latest.get("casos_est"),
        "incidencia_100k": latest.get("p_inc100k"),
        "nivel_alerta": latest.get("nivel"),
        "rt": latest.get("Rt"),
        "versao_modelo": latest.get("versao_modelo"),
        "fonte": "InfoDengue / Fiocruz",
    }


def _parse_float(value):
    if value in {None, "", "NA", "NaN", "...", "-"}:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _fetch_infogripe_brasil():
    ano = datetime.now().year
    url = f"https://info.gripe.fiocruz.br/data/detailed/1/2/{ano}/52/Brasil/weekly-incidence-curve"
    try:
        response = requests.get(url, timeout=OFFICIAL_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:
        return {
            "fonte": "InfoGripe / Fiocruz",
            "status": "temporariamente_indisponivel",
            "motivo": type(exc).__name__,
            "url": url,
            "resumo": "A fonte oficial respiratoria esta catalogada, mas nao respondeu dentro do tempo limite.",
        }

    text = response.text.strip()
    if not text:
        return {
            "fonte": "InfoGripe / Fiocruz",
            "status": "sem_dados",
            "url": url,
            "resumo": "A fonte respondeu sem registros no periodo consultado.",
        }

    delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    rows = list(csv.DictReader(StringIO(text), delimiter=delimiter))
    if not rows:
        return {
            "fonte": "InfoGripe / Fiocruz",
            "status": "sem_dados",
            "url": url,
            "resumo": "A fonte respondeu sem registros estruturados.",
        }

    numeric_columns = {}
    for key in rows[0].keys():
        values = [_parse_float(row.get(key)) for row in rows[-8:]]
        values = [value for value in values if value is not None]
        if values:
            numeric_columns[key] = values

    top_columns = sorted(
        numeric_columns.items(),
        key=lambda item: sum(item[1]),
        reverse=True,
    )[:5]

    latest = rows[-1]
    return {
        "fonte": "InfoGripe / Fiocruz",
        "status": "ativo",
        "url": url,
        "ano": ano,
        "registros": len(rows),
        "ultima_semana": latest,
        "series_relevantes": [
            {
                "campo": key,
                "soma_ultimas_8_semanas": round(sum(values), 2),
                "ultimo_valor": round(values[-1], 2),
            }
            for key, values in top_columns
        ],
    }


def _arboviroses_oficiais(municipios):
    ano = datetime.now().year
    resultado = []
    started_at = time()

    for row in municipios[:3]:
        if time() - started_at > OFFICIAL_PANEL_TIME_BUDGET_SECONDS:
            break

        municipio = _municipio_ibge(row.get("cidade"), row.get("estado"))
        if not municipio:
            continue

        populacao = None
        populacao_fonte = None
        try:
            populacao = _fetch_populacao_ibge(municipio["codigo_ibge"])
            populacao_fonte = f"IBGE/SIDRA {POPULATION_YEAR}"
        except Exception:
            populacao = None

        doencas = []
        for disease in ["dengue", "chikungunya", "zika"]:
            if time() - started_at > OFFICIAL_PANEL_TIME_BUDGET_SECONDS:
                break
            try:
                item = _fetch_infodengue(municipio["codigo_ibge"], disease, ano)
            except Exception:
                item = None
            if item:
                if populacao is None and item.get("pop"):
                    try:
                        populacao = int(float(item.get("pop")))
                        populacao_fonte = "InfoDengue / Fiocruz"
                    except (TypeError, ValueError):
                        pass
                doencas.append(item)

        resultado.append({
            "cidade": municipio["nome"],
            "estado": UF_CODES.get(municipio.get("codigo_uf")),
            "codigo_ibge": municipio["codigo_ibge"],
            "latitude": municipio["latitude"],
            "longitude": municipio["longitude"],
            "populacao": populacao,
            "populacao_fonte": populacao_fonte,
            "sinais_app_14d": row.get("total", 0),
            "sinais_app_14d_por_100k": _safe_rate(row.get("total", 0), populacao),
            "arboviroses": doencas,
        })

    return resultado


def panorama_brasil_oficial_payload(force=False):
    now = time()
    if (
        not force
        and _CACHE["payload"] is not None
        and now - _CACHE["created_at"] < _CACHE_TTL_SECONDS
    ):
        return _CACHE["payload"]

    municipios = _municipios_por_sinal()
    arboviroses = _arboviroses_oficiais(municipios)
    respiratorio = _fetch_infogripe_brasil()
    catalogo_datasus = _catalogo_opendatasus_datasus()
    status_execucoes = _status_execucoes_oficiais()
    municipios_com_populacao = [item for item in arboviroses if item.get("populacao")]
    sinais_com_taxa = [item for item in arboviroses if item.get("sinais_app_14d_por_100k") is not None]

    payload = {
        "generated_at": timezone.now().isoformat(),
        "pais": "Brasil",
        "principio": (
            "Separar sinais colaborativos em tempo real de dados oficiais confirmados. "
            "O app antecipa sinais; as bases oficiais validam, contextualizam e auditam."
        ),
        "fontes": FONTES_OFICIAIS,
        "camadas": {
            "colaborativa_tempo_real": {
                "origem": "App SolusCRT Saude",
                "uso": "captar sinais iniciais por bairro, municipio e estado",
                "controle": "antifraude, limite por rede/aparelho e confianca do sinal",
            },
            "oficial_confirmada": {
                "origem": "Fiocruz, Ministerio da Saude, DATASUS, OpenDataSUS e IBGE",
                "uso": "validar tendencia, incidencia, historico, gravidade e denominadores",
                "controle": "rastreabilidade de fonte e data de atualizacao",
            },
        },
        "indicadores_brasil": {
            "municipios_com_populacao": len(municipios_com_populacao),
            "municipios_com_taxa_colaborativa": len(sinais_com_taxa),
            "ano_populacao_padrao": POPULATION_YEAR,
            "fonte_populacao_prioritaria": "IBGE/SIDRA tabela 6579 variavel 9324",
            "formula": "casos ou sinais / populacao * 100000",
        },
        "arboviroses_municipais": arboviroses,
        "respiratorio_oficial": respiratorio,
        "opendatasus_datasus": catalogo_datasus,
        "execucoes_oficiais": status_execucoes,
        "pipelines_automatizados": [
            {
                "nome": "IBGE/SIDRA populacao municipal",
                "status": "ativo",
                "entrega": "denominadores populacionais e taxas por 100 mil habitantes",
            },
            {
                "nome": "InfoDengue arboviroses municipais",
                "status": "ativo",
                "entrega": "casos, incidencia, nivel de alerta, Rt e semana epidemiologica",
            },
            {
                "nome": "InfoGripe respiratorio",
                "status": "ativo" if respiratorio.get("status") == "ativo" else "resiliente",
                "entrega": "SRAG e sinais respiratorios oficiais quando a fonte responde; queda controlada quando indisponivel",
            },
            {
                "nome": "SIM/Mortalidade (OpenDataSUS DO*OPEN)",
                "status": "ativo",
                "entrega": "obitos oficiais por municipio/competencia via amostra controlada por HTTP Range",
            },
            {
                "nome": "SIH-CNES capacidade hospitalar (Leitos SUS)",
                "status": "ativo",
                "entrega": "leitos SUS e de UTI por municipio/competencia como camada oficial de pressao assistencial",
            },
            {
                "nome": "SINAN/Dengue notificacoes (worker .csv.zip)",
                "status": "ativo",
                "entrega": "notificacoes de dengue por municipio/semana epidemiologica via download e descompactacao controlada do zip oficial",
            },
            {
                "nome": "SI-PNI/Vacinacao COVID-19 (resolver dinamico)",
                "status": "ativo",
                "entrega": "doses aplicadas por municipio/mes, com a particao vigente resolvida da pagina oficial e amostrada por HTTP Range",
            },
            {
                "nome": "OpenDataSUS/DATASUS historico institucional",
                "status": "manifesto_seguro",
                "entrega": "catalogo de microdados, regras de coleta segura e preparo para jobs assíncronos",
            },
        ],
        "lacunas_controladas": [
            "Internacoes individuais (RD/SIH microdados) so existem como DBC na FTP do DATASUS; usamos a capacidade instalada (CNES) como camada oficial de pressao hospitalar.",
            "Amostras controladas leem um recorte inicial de cada fonte; a cobertura nacional completa exige ampliar os limites de bytes/linhas em janelas operacionais dedicadas.",
            "Perfis sociodemograficos completos exigem bases oficiais e governanca LGPD.",
        ],
    }

    _CACHE.update({"created_at": now, "payload": payload})
    return payload


def api_brasil_fontes_oficiais(request):
    force = request.GET.get("force") == "1"
    return JsonResponse(panorama_brasil_oficial_payload(force=force))
