"""
import_sigtap — Importa a Tabela de Procedimentos SUS (SIGTAP/DATASUS).

Uso:
    python manage.py import_sigtap --competencia 202601
    python manage.py import_sigtap --arquivo /tmp/sigtap_202601.zip
    python manage.py import_sigtap --competencia 202601 --dry-run

Fontes aceitas:
  1. Arquivo ZIP local com os arquivos TXT do SIGTAP
  2. Download automático do DATASUS via URL pública
  3. Arquivos TXT individuais na pasta corrente (TB_PROCEDIMENTO.txt, etc.)

Formato SIGTAP (DATASUS):
  TB_PROCEDIMENTO.txt  — largura fixa, sem header
    CO_PROCEDIMENTO      char(10)
    NO_PROCEDIMENTO      char(255)
    CO_GRUPO             char(2)
    CO_SUBGRUPO          char(2)
    CO_FORMA_ORGANIZACAO char(2)
    CO_TIPO_FINANCIAMENTO char(2)
    CO_COMPLEXIDADE      char(2)
    CO_INSTRUMENTO_REGISTRO_PRODUCAO char(4)
    QT_MAXIMA_EXECUCAO   numeric(10)
    VL_SERVICO_HOSPITALAR decimal(10,2)
    VL_SERVICO_AMBULATORIAL decimal(10,2)
    VL_SERVICO_PROFISSIONAL decimal(10,2)
    DT_COMPETENCIA       char(6)  AAAAMM
    ST_FINANCIAMENTO_MAC char(1)
    ST_INSTRUMENTO_REGISTRO_PRODUCAO char(1)
"""

import csv
import io
import logging
import os
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)

# ── Mapeamentos SIGTAP ────────────────────────────────────────────────────────

_COMPLEXIDADE = {
    "01": "AB",
    "02": "MC",
    "03": "AC",
    "07": "SE",
    "": "",
}

_INSTRUMENTO = {
    "01": "BPA-I",
    "02": "BPA-C",
    "03": "APAC",
    "04": "AIH",
    "05": "BPA-I",   # consolidado por procedimento
    "06": "RAAS",
    "": "",
}

# URL DATASUS para competência — padrão público
_URL_SIGTAP_BASE = (
    "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/"
    "procedimento_download.faces"
)


class Command(BaseCommand):
    help = "Importa a Tabela de Procedimentos SUS (SIGTAP) para o banco local."

    def add_arguments(self, parser):
        parser.add_argument(
            "--competencia",
            type=str,
            default="",
            help="Competência AAAAMM a importar (ex: 202601). "
                 "Padrão: competência atual.",
        )
        parser.add_argument(
            "--arquivo",
            type=str,
            default="",
            help="Caminho para o arquivo ZIP do SIGTAP (opcional).",
        )
        parser.add_argument(
            "--pasta",
            type=str,
            default="",
            help="Pasta com os arquivos TXT do SIGTAP descompactados.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Só conta os registros, não salva no banco.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Reimporta mesmo que a competência já exista.",
        )

    def handle(self, *args, **options):
        from api.models import SIGTAPImportacao

        competencia = options["competencia"] or datetime.now().strftime("%Y%m")
        dry_run     = options["dry_run"]
        force       = options["force"]

        self.stdout.write(self.style.NOTICE(
            f"\n{'='*60}\n  SIGTAP — competência {competencia}\n{'='*60}"
        ))

        # Verifica se já foi importada
        if not force and not dry_run:
            if SIGTAPImportacao.objects.filter(competencia=competencia, sucesso=True).exists():
                self.stdout.write(self.style.WARNING(
                    f"Competência {competencia} já importada. "
                    "Use --force para reimportar."
                ))
                return

        # Resolve fonte dos dados
        pasta = self._resolver_fonte(options, competencia)

        # Importa TB_PROCEDIMENTO.txt
        proc_path = self._find_file(pasta, ["TB_PROCEDIMENTO.txt", "tb_procedimento.txt"])
        if not proc_path:
            raise CommandError(
                "Arquivo TB_PROCEDIMENTO.txt não encontrado. "
                "Forneça --arquivo <zip> ou --pasta <pasta_sigtap>."
            )

        proc_count, cid_count = self._importar(proc_path, pasta, competencia, dry_run)

        if not dry_run:
            SIGTAPImportacao.objects.update_or_create(
                competencia=competencia,
                defaults={
                    "total_procedimentos": proc_count,
                    "total_cids":          cid_count,
                    "sucesso":             True,
                    "importado_por":       "import_sigtap",
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ {proc_count} procedimentos | {cid_count} CIDs"
            f"{'  [DRY-RUN — nada salvo]' if dry_run else ' importados.'}"
        ))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolver_fonte(self, options, competencia):
        """Retorna o caminho da pasta com os TXTs do SIGTAP."""
        if options["pasta"]:
            pasta = options["pasta"]
            if not os.path.isdir(pasta):
                raise CommandError(f"Pasta não encontrada: {pasta}")
            return pasta

        if options["arquivo"]:
            arq = options["arquivo"]
            if not os.path.exists(arq):
                raise CommandError(f"Arquivo não encontrado: {arq}")
            return self._descompactar(arq)

        # Tenta pasta corrente
        if os.path.exists("TB_PROCEDIMENTO.txt"):
            return "."

        # Tenta download
        self.stdout.write("Tentando download do DATASUS…")
        try:
            return self._baixar_sigtap(competencia)
        except Exception as e:
            raise CommandError(
                f"Não foi possível baixar o SIGTAP: {e}\n"
                "Baixe manualmente em http://sigtap.datasus.gov.br e use "
                "--arquivo <zip> ou --pasta <pasta>."
            )

    def _descompactar(self, zip_path):
        tmp = tempfile.mkdtemp(prefix="sigtap_")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        self.stdout.write(f"  Descompactado em {tmp}")
        return tmp

    def _baixar_sigtap(self, competencia):
        """
        Tenta baixar o ZIP do SIGTAP do DATASUS.
        O DATASUS disponibiliza via FTP:
          ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Auxiliar/
        Arquivo: SIGTAP<AAAAMM>.zip  (ex: SIGTAP202601.zip)
        """
        import urllib.request
        ftp_url = (
            f"ftp://ftp.datasus.gov.br/dissemin/publicos/SIGTAP/"
            f"tabela_unificada/competencia_{competencia}.zip"
        )
        tmp_zip = tempfile.mktemp(suffix=".zip")
        try:
            urllib.request.urlretrieve(ftp_url, tmp_zip)
            return self._descompactar(tmp_zip)
        except Exception:
            # Fallback — tenta URL alternativa do FTP DATASUS
            alt_url = (
                f"ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/"
                f"Auxiliar/TABELAS_{competencia}.zip"
            )
            urllib.request.urlretrieve(alt_url, tmp_zip)
            return self._descompactar(tmp_zip)

    def _find_file(self, pasta, nomes):
        """Procura arquivo por lista de nomes (case-insensitive) na pasta."""
        for nome in nomes:
            candidato = os.path.join(pasta, nome)
            if os.path.exists(candidato):
                return candidato
        # Busca recursiva para ZIPs aninhados
        for root, _, files in os.walk(pasta):
            for f in files:
                if f.lower() in [n.lower() for n in nomes]:
                    return os.path.join(root, f)
        return None

    @transaction.atomic
    def _importar(self, proc_path, pasta, competencia, dry_run):
        from api.models import ProcedimentoSIGTAP, ProcedimentoSIGTAPCID

        proc_count = 0
        cid_count  = 0
        batch      = []
        batch_size = 500

        # Determina encoding (SIGTAP usa ISO-8859-1 / latin-1)
        with open(proc_path, "r", encoding="latin-1", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if len(line) < 10:
                    continue

                codigo      = line[0:10].strip()
                descricao   = line[10:265].strip() if len(line) > 10 else ""
                grupo       = line[265:267].strip() if len(line) > 265 else ""
                subgrupo    = line[267:269].strip() if len(line) > 267 else ""
                forma_org   = line[269:271].strip() if len(line) > 269 else ""
                # tipo_finan  = line[271:273]  # não usado diretamente
                complexidade_cod = line[273:275].strip() if len(line) > 273 else ""
                instrumento_cod  = line[275:279].strip() if len(line) > 275 else ""
                qt_max      = line[279:289].strip() if len(line) > 279 else "0"
                vl_sh       = line[289:299].strip() if len(line) > 289 else "0"
                vl_sa       = line[299:309].strip() if len(line) > 299 else "0"
                vl_sp       = line[309:319].strip() if len(line) > 309 else "0"
                comp_proc   = line[319:325].strip() if len(line) > 319 else competencia

                def _dec(s):
                    try:
                        return Decimal(s.replace(",", ".")) if s else Decimal("0")
                    except InvalidOperation:
                        return Decimal("0")

                def _int(s):
                    try:
                        return int(s) if s else 0
                    except ValueError:
                        return 0

                proc_obj = ProcedimentoSIGTAP(
                    codigo               = codigo,
                    descricao            = descricao[:255],
                    grupo                = grupo,
                    subgrupo             = subgrupo,
                    forma_organizacao    = forma_org,
                    competencia          = comp_proc or competencia,
                    complexidade         = _COMPLEXIDADE.get(complexidade_cod, ""),
                    instrumento_registro = _INSTRUMENTO.get(instrumento_cod[:2], ""),
                    valor_sh             = _dec(vl_sh),
                    valor_sa             = _dec(vl_sa),
                    valor_sp             = _dec(vl_sp),
                    valor_total          = _dec(vl_sh) + _dec(vl_sa) + _dec(vl_sp),
                    quantidade_maxima    = _int(qt_max),
                    ativo                = True,
                )
                batch.append(proc_obj)
                proc_count += 1

                if len(batch) >= batch_size and not dry_run:
                    ProcedimentoSIGTAP.objects.bulk_create(
                        batch,
                        update_conflicts=True,
                        update_fields=[
                            "descricao", "complexidade", "instrumento_registro",
                            "valor_sh", "valor_sa", "valor_sp", "valor_total",
                            "quantidade_maxima", "competencia", "ativo",
                        ],
                        unique_fields=["codigo"],
                    )
                    batch = []
                    self.stdout.write(f"  {proc_count} procedimentos…", ending="\r")

        if batch and not dry_run:
            ProcedimentoSIGTAP.objects.bulk_create(
                batch,
                update_conflicts=True,
                update_fields=[
                    "descricao", "complexidade", "instrumento_registro",
                    "valor_sh", "valor_sa", "valor_sp", "valor_total",
                    "quantidade_maxima", "competencia", "ativo",
                ],
                unique_fields=["codigo"],
            )

        # Importa CIDs (rl_procedimento_cid.txt ou RL_PROCEDIMENTO_CID.txt)
        cid_path = self._find_file(pasta, [
            "rl_procedimento_cid.txt",
            "RL_PROCEDIMENTO_CID.txt",
            "tb_procedimento_cid.txt",
        ])
        if cid_path:
            cid_count = self._importar_cids(cid_path, dry_run)

        return proc_count, cid_count

    def _importar_cids(self, cid_path, dry_run):
        from api.models import ProcedimentoSIGTAP, ProcedimentoSIGTAPCID

        count  = 0
        batch  = []

        # Cache dos procedimentos existentes
        proc_map = {p.codigo: p.pk for p in ProcedimentoSIGTAP.objects.only("codigo", "pk")}

        with open(cid_path, "r", encoding="latin-1", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if len(line) < 14:
                    continue
                codigo_proc = line[0:10].strip()
                cid         = line[10:14].strip()

                if not codigo_proc or not cid:
                    continue

                pk = proc_map.get(codigo_proc)
                if not pk:
                    continue

                batch.append(ProcedimentoSIGTAPCID(procedimento_id=pk, cid=cid))
                count += 1

                if len(batch) >= 1000 and not dry_run:
                    ProcedimentoSIGTAPCID.objects.bulk_create(
                        batch, ignore_conflicts=True
                    )
                    batch = []

        if batch and not dry_run:
            ProcedimentoSIGTAPCID.objects.bulk_create(batch, ignore_conflicts=True)

        return count
