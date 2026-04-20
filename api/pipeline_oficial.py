from __future__ import annotations

import csv
from collections import defaultdict
from io import StringIO

import requests
from django.utils import timezone

from .fontes_oficiais_brasil import OPENDATASUS_DATASUS_MANIFEST
from .models import FonteOficialAgregado, FonteOficialExecucao


MANIFEST_BY_ID = {item["id"]: item for item in OPENDATASUS_DATASUS_MANIFEST}

SIVEP_GRIPE_2026_CSV_URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SRAG/2026/INFLUD26-23-03-2026.csv"


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

    execucao.status = FonteOficialExecucao.STATUS_FALHOU
    execucao.mensagem = (
        "Download de microdados ainda nao habilitado. Ative somente apos definir fonte, "
        "limites de volume, armazenamento e janela de execucao."
    )
    execucao.finalizado_em = timezone.now()
    execucao.save(update_fields=["status", "mensagem", "finalizado_em"])
    return execucao
