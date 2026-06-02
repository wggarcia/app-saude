from __future__ import annotations

import csv
import zipfile
from collections import defaultdict
from io import BytesIO, StringIO, TextIOWrapper

import requests
from django.utils import timezone

from .fontes_oficiais_brasil import OPENDATASUS_DATASUS_MANIFEST, UF_CODES
from .models import FonteOficialAgregado, FonteOficialExecucao


MANIFEST_BY_ID = {item["id"]: item for item in OPENDATASUS_DATASUS_MANIFEST}

SIVEP_GRIPE_2026_CSV_URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2026/INFLUD26-23-03-2026.csv"

# Fontes oficiais publicadas como CSV puro em S3 (suporte a HTTP Range) que podem
# ser amostradas de forma controlada pelo mesmo mecanismo do SIVEP-Gripe.
# Cada config descreve como localizar territorio, periodo e valor sem baixar o
# arquivo completo. URLs verificadas em https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/.
FONTES_CSV_CONFIG = {
    "sim_mortalidade": {
        "url": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SIM/DO24OPEN.csv",
        "delimiter": ";",
        "encoding": "latin-1",
        "indicador": "obitos_sim_amostra",
        "unidade": "obitos",
        "fonte_nome": "SIM / Mortalidade",
        "versao_fonte": "DO24OPEN",
        "ibge_cols": ["CODMUNRES", "CODMUNOCOR"],
        "municipio_cols": [],
        "uf_cols": [],
        "uf_from_ibge": True,
        "periodo_date_col": "DTOBITO",
        "periodo_date_fmt": "ddmmyyyy",
        "valor_col": None,  # cada linha = 1 obito
    },
    "sih_internacoes": {
        "url": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/Leitos_SUS/Leitos_2025.csv",
        "delimiter": ",",
        "encoding": "latin-1",
        "indicador": "leitos_sus_disponiveis",
        "unidade": "leitos_sus",
        "fonte_nome": "Leitos SUS / CNES (capacidade hospitalar)",
        "versao_fonte": "Leitos_2025",
        "ibge_cols": [],
        "municipio_cols": ["MUNICIPIO"],
        "uf_cols": ["UF"],
        "uf_from_ibge": False,
        "periodo_comp_col": "COMP",  # YYYYMM
        "valor_col": "LEITOS_SUS",  # soma de leitos SUS instalados
    },
}

# Fontes oficiais publicadas apenas em .csv.zip (incompativel com HTTP Range).
# Exigem um worker que baixe o zip completo (com teto de tamanho), descompacte
# em streaming e agregue sem persistir microdados brutos.
FONTES_ZIP_CONFIG = {
    "sinan_agravos": {
        "url": "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR25.csv.zip",
        "delimiter": ",",
        "encoding": "latin-1",
        "indicador": "dengue_notificacoes_sinan",
        "unidade": "notificacoes",
        "fonte_nome": "SINAN / Dengue",
        "versao_fonte": "DENGBR25",
        "ibge_cols": ["ID_MUNICIP", "ID_MN_RESI"],
        "municipio_cols": [],
        "uf_cols": [],
        "uf_from_ibge": True,
        "periodo_sem_col": "SEM_NOT",  # YYYYWW (semana epidemiologica)
        "valor_col": None,  # cada linha = 1 notificacao
        "max_download_bytes": 250_000_000,  # teto de seguranca para o zip
    },
}


def _numero(valor):
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _primeiro_valor(row, cols):
    for col in cols or []:
        valor = (row.get(col) or "").strip()
        if valor:
            return valor
    return ""


def _periodo_de_data(valor, fmt):
    valor = (valor or "").strip()
    if fmt == "ddmmyyyy" and len(valor) == 8 and valor.isdigit():
        return f"{valor[4:8]}-{valor[2:4]}"
    return None


def _periodo_de_comp(valor):
    valor = (valor or "").strip()
    if len(valor) == 6 and valor.isdigit():
        return f"{valor[0:4]}-{valor[4:6]}"
    return valor or "competencia_nao_informada"


def _periodo_de_semana(valor):
    valor = (valor or "").strip()
    if len(valor) == 6 and valor.isdigit():
        return f"{valor[0:4]}-S{valor[4:6]}"
    return valor or "semana_nao_informada"


def _localizar_territorio(row, config):
    codigo_ibge = _primeiro_valor(row, config.get("ibge_cols"))
    if config.get("uf_from_ibge") and len(codigo_ibge) >= 2 and codigo_ibge[:2].isdigit():
        uf = UF_CODES.get(int(codigo_ibge[:2]), "")
    else:
        uf = _primeiro_valor(row, config.get("uf_cols")).upper()
    cidade = _primeiro_valor(row, config.get("municipio_cols"))
    return uf, cidade, codigo_ibge


def _localizar_periodo(row, config):
    if config.get("periodo_date_col"):
        periodo = _periodo_de_data(
            row.get(config["periodo_date_col"]),
            config.get("periodo_date_fmt"),
        )
        if periodo:
            return periodo
    if config.get("periodo_sem_col"):
        return _periodo_de_semana(row.get(config["periodo_sem_col"]))
    if config.get("periodo_comp_col"):
        return _periodo_de_comp(row.get(config["periodo_comp_col"]))
    return "periodo_nao_informado"


def _processar_csv_oficial(execucao, fonte_id, config, *, max_bytes, max_linhas):
    response = requests.get(
        config["url"],
        headers={"Range": f"bytes=0-{max_bytes - 1}"},
        timeout=30,
    )
    response.raise_for_status()
    content = response.content.decode(config.get("encoding", "latin-1"), errors="ignore")
    lines = content.splitlines()
    if len(lines) > 1 and not content.endswith(("\n", "\r")):
        lines = lines[:-1]

    reader = csv.DictReader(StringIO("\n".join(lines)), delimiter=config["delimiter"])
    target_uf = (execucao.uf or "").strip().upper()
    aggregations = defaultdict(float)
    registros = 0

    for row in reader:
        if registros >= max_linhas:
            break
        uf, cidade, codigo_ibge = _localizar_territorio(row, config)
        if target_uf and target_uf != (uf or "").upper():
            continue
        periodo = _localizar_periodo(row, config)
        valor_col = config.get("valor_col")
        incremento = _numero(row.get(valor_col)) if valor_col else 1
        aggregations[(uf or "", cidade or "", codigo_ibge or "", periodo)] += incremento
        registros += 1

    agregados = 0
    for (uf, cidade, codigo_ibge, periodo), total in aggregations.items():
        FonteOficialAgregado.objects.update_or_create(
            fonte_id=fonte_id,
            indicador=config["indicador"],
            codigo_ibge=codigo_ibge or None,
            estado=uf or None,
            cidade=cidade or None,
            periodo=periodo,
            defaults={
                "valor": round(total, 2),
                "unidade": config["unidade"],
                "fonte_nome": config["fonte_nome"],
                "versao_fonte": config["versao_fonte"],
                "metadados": {
                    "tipo": "amostra_controlada",
                    "fonte_url": config["url"],
                },
            },
        )
        agregados += 1

    execucao.status = FonteOficialExecucao.STATUS_CONCLUIDA
    execucao.registros_lidos = registros
    execucao.agregados_gerados = agregados
    execucao.mensagem = (
        f"Amostra controlada {config['fonte_nome']} processada com sucesso. "
        "Foram gravados somente agregados oficiais, sem armazenar microdados brutos."
    )
    execucao.metadados = {
        **execucao.metadados,
        "fonte_amostra": {
            "url": config["url"],
            "http_status": response.status_code,
            "content_range": response.headers.get("content-range"),
            "max_bytes": max_bytes,
            "max_linhas": max_linhas,
        },
    }
    execucao.finalizado_em = timezone.now()
    execucao.save(
        update_fields=[
            "status",
            "registros_lidos",
            "agregados_gerados",
            "mensagem",
            "metadados",
            "finalizado_em",
        ]
    )
    return execucao


def _parse_sivep_blocks(
    *,
    byte_start: int,
    bloco_bytes: int,
    max_blocos: int,
    max_linhas: int,
    uf: str | None = None,
):
    header_response = requests.get(
        SIVEP_GRIPE_2026_CSV_URL,
        headers={"Range": "bytes=0-8191"},
        timeout=20,
    )
    header_response.raise_for_status()
    header_text = header_response.content.decode("latin-1", errors="ignore")
    header_line = header_text.splitlines()[0]
    fieldnames = next(csv.reader([header_line], delimiter=";"))

    aggregations = defaultdict(int)
    registros = 0
    bytes_lidos = 0
    blocos_lidos = 0
    target_uf = (uf or "").strip().upper()
    last_content_range = None

    for block_index in range(max_blocos):
        if registros >= max_linhas:
            break

        start = byte_start + (block_index * bloco_bytes)
        end = start + bloco_bytes - 1
        response = requests.get(
            SIVEP_GRIPE_2026_CSV_URL,
            headers={"Range": f"bytes={start}-{end}"},
            timeout=25,
        )
        response.raise_for_status()
        bytes_lidos += len(response.content)
        blocos_lidos += 1
        last_content_range = response.headers.get("content-range")

        content = response.content.decode("latin-1", errors="ignore")
        lines = content.splitlines()
        if not lines:
            continue

        if start > 0:
            lines = lines[1:]
        if len(lines) > 1 and not content.endswith(("\n", "\r")):
            lines = lines[:-1]

        reader = csv.DictReader(StringIO("\n".join(lines)), fieldnames=fieldnames, delimiter=";")
        for row in reader:
            if registros >= max_linhas:
                break

            row_uf = (row.get("SG_UF_NOT") or row.get("SG_UF") or "").strip()
            if target_uf and target_uf != row_uf.upper():
                continue
            cidade = (row.get("ID_MUNICIP") or row.get("ID_MN_RESI") or "").strip()
            codigo_ibge = (row.get("CO_MUN_NOT") or row.get("CO_MU_RES") or "").strip()
            periodo = (row.get("SEM_NOT") or row.get("SEM_PRI") or "").strip() or "semana_nao_informada"

            aggregations[(row_uf, cidade, codigo_ibge, periodo)] += 1
            registros += 1

    return registros, aggregations, {
        "url": SIVEP_GRIPE_2026_CSV_URL,
        "content_range": last_content_range,
        "byte_start": byte_start,
        "bloco_bytes": bloco_bytes,
        "max_blocos": max_blocos,
        "blocos_lidos": blocos_lidos,
        "bytes_lidos": bytes_lidos,
        "max_linhas": max_linhas,
    }


def _parse_sivep_sample(max_bytes: int, max_linhas: int, uf: str | None = None):
    response = requests.get(
        SIVEP_GRIPE_2026_CSV_URL,
        headers={"Range": f"bytes=0-{max_bytes - 1}"},
        timeout=25,
    )
    response.raise_for_status()
    content = response.content.decode("latin-1", errors="ignore")
    lines = content.splitlines()
    if len(lines) > 1 and not content.endswith(("\n", "\r")):
        lines = lines[:-1]

    reader = csv.DictReader(StringIO("\n".join(lines)), delimiter=";")
    aggregations = defaultdict(int)
    registros = 0
    target_uf = (uf or "").strip().upper()

    for row in reader:
        if registros >= max_linhas:
            break

        row_uf = (row.get("SG_UF_NOT") or row.get("SG_UF") or "").strip()
        if target_uf and target_uf != row_uf.upper():
            continue
        cidade = (row.get("ID_MUNICIP") or row.get("ID_MN_RESI") or "").strip()
        codigo_ibge = (row.get("CO_MUN_NOT") or row.get("CO_MU_RES") or "").strip()
        periodo = (row.get("SEM_NOT") or row.get("SEM_PRI") or "").strip()
        if not periodo:
            periodo = "semana_nao_informada"

        aggregations[(row_uf, cidade, codigo_ibge, periodo)] += 1
        registros += 1

    return registros, aggregations, {
        "url": SIVEP_GRIPE_2026_CSV_URL,
        "http_status": response.status_code,
        "content_range": response.headers.get("content-range"),
        "content_length": response.headers.get("content-length"),
        "max_bytes": max_bytes,
        "max_linhas": max_linhas,
    }


def _processar_sivep_amostra(
    execucao,
    max_bytes: int,
    max_linhas: int,
    *,
    incremental: bool = False,
    byte_start: int = 0,
    bloco_bytes: int = 200_000,
    max_blocos: int = 1,
):
    if incremental:
        registros, aggregations, source_meta = _parse_sivep_blocks(
            byte_start=byte_start,
            bloco_bytes=bloco_bytes,
            max_blocos=max_blocos,
            max_linhas=max_linhas,
            uf=execucao.uf,
        )
    else:
        registros, aggregations, source_meta = _parse_sivep_sample(
            max_bytes,
            max_linhas,
            uf=execucao.uf,
        )
    agregados = 0

    for (uf, cidade, codigo_ibge, periodo), total in aggregations.items():
        FonteOficialAgregado.objects.update_or_create(
            fonte_id="sivep_gripe",
            indicador="srag_notificacoes_incremental" if incremental else "srag_notificacoes_amostra",
            codigo_ibge=codigo_ibge or None,
            estado=uf or None,
            cidade=cidade or None,
            periodo=periodo,
            defaults={
                "valor": total,
                "unidade": "notificacoes",
                "fonte_nome": "SIVEP-Gripe / SRAG",
                "versao_fonte": "INFLUD26-23-03-2026",
                "metadados": {
                    "tipo": "amostra_controlada",
                    "fonte_url": SIVEP_GRIPE_2026_CSV_URL,
                    "incremental": incremental,
                },
            },
        )
        agregados += 1

    execucao.status = FonteOficialExecucao.STATUS_CONCLUIDA
    execucao.registros_lidos = registros
    execucao.agregados_gerados = agregados
    execucao.mensagem = (
        "Coleta incremental controlada SIVEP-Gripe processada com sucesso. "
        if incremental
        else "Amostra controlada SIVEP-Gripe processada com sucesso. "
    ) + (
        "Foram gravados somente agregados, sem armazenar microdados brutos."
    )
    execucao.metadados = {**execucao.metadados, "fonte_amostra": source_meta}
    execucao.finalizado_em = timezone.now()
    execucao.save(
        update_fields=[
            "status",
            "registros_lidos",
            "agregados_gerados",
            "mensagem",
            "metadados",
            "finalizado_em",
        ]
    )
    return execucao


def _processar_zip_oficial(execucao, fonte_id, config, *, max_linhas, max_download_bytes):
    # Baixa o zip completo com teto de tamanho, descompacta em streaming e agrega.
    # Nada de microdados brutos e persistido: somente contagens/somas por territorio/periodo.
    with requests.get(config["url"], stream=True, timeout=300) as response:
        response.raise_for_status()
        buffer = BytesIO()
        baixado = 0
        for chunk in response.iter_content(chunk_size=1 << 20):
            if not chunk:
                continue
            baixado += len(chunk)
            if baixado > max_download_bytes:
                raise ValueError(
                    f"Arquivo zip excede o teto de seguranca de {max_download_bytes} bytes."
                )
            buffer.write(chunk)

    buffer.seek(0)
    arquivo_zip = zipfile.ZipFile(buffer)
    membro = next((n for n in arquivo_zip.namelist() if n.lower().endswith(".csv")), None)
    if not membro:
        raise ValueError("Arquivo zip oficial nao contem CSV interno.")

    target_uf = (execucao.uf or "").strip().upper()
    aggregations = defaultdict(float)
    registros = 0

    with arquivo_zip.open(membro) as raw:
        texto = TextIOWrapper(raw, encoding=config.get("encoding", "latin-1"), errors="ignore")
        reader = csv.DictReader(texto, delimiter=config["delimiter"])
        for row in reader:
            if registros >= max_linhas:
                break
            uf, cidade, codigo_ibge = _localizar_territorio(row, config)
            if target_uf and target_uf != (uf or "").upper():
                continue
            periodo = _localizar_periodo(row, config)
            valor_col = config.get("valor_col")
            incremento = _numero(row.get(valor_col)) if valor_col else 1
            aggregations[(uf or "", cidade or "", codigo_ibge or "", periodo)] += incremento
            registros += 1

    agregados = 0
    for (uf, cidade, codigo_ibge, periodo), total in aggregations.items():
        FonteOficialAgregado.objects.update_or_create(
            fonte_id=fonte_id,
            indicador=config["indicador"],
            codigo_ibge=codigo_ibge or None,
            estado=uf or None,
            cidade=cidade or None,
            periodo=periodo,
            defaults={
                "valor": round(total, 2),
                "unidade": config["unidade"],
                "fonte_nome": config["fonte_nome"],
                "versao_fonte": config["versao_fonte"],
                "metadados": {
                    "tipo": "amostra_controlada_zip",
                    "fonte_url": config["url"],
                },
            },
        )
        agregados += 1

    execucao.status = FonteOficialExecucao.STATUS_CONCLUIDA
    execucao.registros_lidos = registros
    execucao.agregados_gerados = agregados
    execucao.mensagem = (
        f"Coleta controlada {config['fonte_nome']} (.csv.zip) processada com sucesso. "
        "Zip descompactado em streaming; gravados somente agregados oficiais, sem microdados brutos."
    )
    execucao.metadados = {
        **execucao.metadados,
        "fonte_amostra": {
            "url": config["url"],
            "membro": membro,
            "bytes_baixados": baixado,
            "max_linhas": max_linhas,
        },
    }
    execucao.finalizado_em = timezone.now()
    execucao.save(
        update_fields=[
            "status",
            "registros_lidos",
            "agregados_gerados",
            "mensagem",
            "metadados",
            "finalizado_em",
        ]
    )
    return execucao


def preparar_execucao_fonte_oficial(
    fonte_id: str,
    *,
    uf: str | None = None,
    periodo_inicio: str | None = None,
    periodo_fim: str | None = None,
    executar_download: bool = False,
    max_bytes: int = 200_000,
    max_linhas: int = 1000,
    incremental: bool = False,
    byte_start: int = 0,
    bloco_bytes: int = 200_000,
    max_blocos: int = 1,
) -> FonteOficialExecucao:
    manifesto = MANIFEST_BY_ID.get(fonte_id)
    if not manifesto:
        raise ValueError(f"Fonte oficial nao catalogada: {fonte_id}")

    execucao = FonteOficialExecucao.objects.create(
        fonte_id=fonte_id,
        fonte_nome=manifesto["nome"],
        status=FonteOficialExecucao.STATUS_EXECUTANDO,
        modo=(
            "incremental_controlado"
            if incremental
            else "download_controlado"
            if executar_download
            else "catalogo_seguro"
        ),
        uf=(uf or "").upper()[:2] or None,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        iniciado_em=timezone.now(),
        metadados={
            "fonte": manifesto["fonte"],
            "finalidade": manifesto["finalidade"],
            "indicadores": manifesto["indicadores"],
            "periodicidade_recomendada": manifesto["periodicidade_recomendada"],
            "estrategia": manifesto["estrategia"],
            "risco_operacional": manifesto["risco_operacional"],
            "motivo_cuidado": manifesto["motivo_cuidado"],
        },
    )

    if not executar_download:
        execucao.status = FonteOficialExecucao.STATUS_SEM_DADOS
        execucao.mensagem = (
            "Execucao preparada em modo seguro. Nenhum microdado foi baixado; "
            "o proximo passo e configurar coleta assíncrona controlada por UF/periodo."
        )
        execucao.finalizado_em = timezone.now()
        execucao.save(update_fields=["status", "mensagem", "finalizado_em"])
        return execucao

    if fonte_id == "sivep_gripe":
        return _processar_sivep_amostra(
            execucao,
            max_bytes=min(max(max_bytes, 20_000), 2_000_000),
            max_linhas=min(max(max_linhas, 10), 5000),
            incremental=incremental,
            byte_start=max(byte_start, 0),
            bloco_bytes=min(max(bloco_bytes, 20_000), 1_000_000),
            max_blocos=min(max(max_blocos, 1), 20),
        )

    config = FONTES_CSV_CONFIG.get(fonte_id)
    if config:
        return _processar_csv_oficial(
            execucao,
            fonte_id,
            config,
            max_bytes=min(max(max_bytes, 20_000), 3_000_000),
            max_linhas=min(max(max_linhas, 10), 20_000),
        )

    zip_config = FONTES_ZIP_CONFIG.get(fonte_id)
    if zip_config:
        return _processar_zip_oficial(
            execucao,
            fonte_id,
            zip_config,
            # Default da CLI e 1000; para o zip usamos um piso maior porque a fonte
            # nacional nao e ordenada por UF (amostra inicial ja cobre as 27 UFs).
            max_linhas=min(max(max_linhas, 50_000), 3_000_000),
            max_download_bytes=zip_config.get("max_download_bytes", 250_000_000),
        )

    execucao.status = FonteOficialExecucao.STATUS_FALHOU
    execucao.mensagem = (
        "Esta fonte oficial e publicada em arquivos segmentados de grande volume com nomes "
        "rotativos (particoes Spark) e listagem de bucket bloqueada, o que impede a coleta "
        "deterministica por HTTP Range. A ingestao exige resolver o link de download dinamico "
        "do portal a cada publicacao (worker dedicado)."
    )
    execucao.finalizado_em = timezone.now()
    execucao.save(update_fields=["status", "mensagem", "finalizado_em"])
    return execucao
