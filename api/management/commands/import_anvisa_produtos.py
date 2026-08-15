"""
import_anvisa_produtos — Sincroniza a base de produtos para saúde da ANVISA.

Dados abertos oficiais (sem autenticação):
  https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/TA_CONSULTA_PRODUTOS_SAUDE.CSV
  (~50 MB, ~191 mil linhas, atualizado diariamente, encoding Windows-1252, ';')

Uso:
  python manage.py import_anvisa_produtos                 # baixa e importa
  python manage.py import_anvisa_produtos --arquivo x.csv # arquivo local
  python manage.py import_anvisa_produtos --dry-run       # não grava
  python manage.py import_anvisa_produtos --afe           # importa também AFE

Gotcha resolvido: o servidor da ANVISA envia só o certificado folha, sem a
intermediária — `requests` falha com CERTIFICATE_VERIFY_FAILED. Baixamos a
intermediária Sectigo e a anexamos ao bundle de verificação (NUNCA verify=False).
"""
import csv
import io
import logging
import os
import ssl
import tempfile
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)

URL_PRODUTOS = ("https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/"
                "TA_CONSULTA_PRODUTOS_SAUDE.CSV")
URL_AFE = ("https://dados.anvisa.gov.br/dados/CONSULTAS/EMPRESA_FISCALIZACAO_PRODUTO/"
           "TA_CONSULTA_FUNCIONAMENTO_EMPRESA_NACIONAL.CSV")
# Intermediária que a ANVISA não envia na cadeia TLS.
URL_INTERMEDIARIA = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt"


def _situacao_valida(situacao):
    """Normaliza SITUACAO_REGISTRO da ANVISA para nosso vocabulário curto."""
    s = (situacao or "").strip().lower()
    if s.startswith("v"):
        return "Válido"
    if s.startswith("inv"):
        return "Inválido"
    if s.startswith("em"):
        return "Em validação"
    return situacao or ""


def _data(s):
    s = (s or "").strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = "Sincroniza a base ANVISA de produtos para saúde (e opcionalmente AFE)."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", help="CSV local (pula o download)")
        parser.add_argument("--afe", action="store_true",
                            help="Importa também a base de AFE de empresas")
        parser.add_argument("--dry-run", action="store_true",
                            help="Não grava — só conta")
        parser.add_argument("--limite", type=int, default=0,
                            help="Processa no máximo N linhas (teste)")

    # ── download com correção da cadeia TLS ──────────────────────────────────
    def _baixar(self, url):
        import requests
        try:
            # Monta um bundle: CA padrão do certifi + a intermediária faltante.
            import certifi
            inter = requests.get(URL_INTERMEDIARIA, timeout=60)
            inter.raise_for_status()
            der = inter.content
            pem_inter = ssl.DER_cert_to_PEM_cert(der)
            with open(certifi.where(), "r") as f:
                base = f.read()
            bundle = tempfile.NamedTemporaryFile(
                mode="w", suffix=".pem", delete=False)
            bundle.write(base + "\n" + pem_inter)
            bundle.close()
            verify = bundle.name
        except Exception as e:
            logger.warning("Não consegui montar bundle TLS (%s); usando verificação padrão.", e)
            verify = True

        self.stdout.write(f"Baixando {url} …")
        resp = requests.get(url, timeout=600, verify=verify, stream=True)
        resp.raise_for_status()
        conteudo = resp.content
        try:
            if isinstance(verify, str):
                os.unlink(verify)
        except OSError:
            pass
        return conteudo

    def _linhas(self, conteudo):
        texto = None
        for enc in ("cp1252", "latin-1", "utf-8-sig"):
            try:
                texto = conteudo.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if texto is None:
            raise CommandError("Não consegui decodificar o CSV da ANVISA.")
        return csv.DictReader(io.StringIO(texto), delimiter=";")

    def handle(self, *args, **opts):
        from api.models import RegistroAnvisaProdutoSaude, EmpresaAfeAnvisa

        # ── Produtos ──────────────────────────────────────────────────────────
        if opts.get("arquivo"):
            with open(opts["arquivo"], "rb") as f:
                conteudo = f.read()
        else:
            conteudo = self._baixar(URL_PRODUTOS)

        leitor = self._linhas(conteudo)
        limite = opts.get("limite") or 0
        dry = opts.get("dry_run")

        # Consolida por número de registro, preferindo a linha "Válido".
        melhor = {}
        n = 0
        for row in leitor:
            n += 1
            if limite and n > limite:
                break
            reg = (row.get("NU_REGISTRO_PRODUTO") or "").strip()
            if not reg:
                continue
            situacao = _situacao_valida(row.get("SITUACAO_REGISTRO"))
            atual = melhor.get(reg)
            # Válido ganha de qualquer outra situação.
            if atual and atual["situacao"] == "Válido" and situacao != "Válido":
                continue
            melhor[reg] = {
                "numero_registro": reg,
                "nome_produto": (row.get("NO_PRODUTO") or "").strip()[:300],
                "detentor": (row.get("NO_RAZAO_SOCIAL_EMPRESA") or "").strip()[:250],
                "cnpj_detentor": "".join(
                    ch for ch in (row.get("NU_CNPJ_EMPRESA") or "") if ch.isdigit())[:14],
                "classe_risco": (row.get("SG_RISCO_PRODUTO") or "").strip()[:4],
                "situacao": situacao,
                "data_vencimento": _data(row.get("DT_VENCIMENTO_REGISTRO")),
            }

        self.stdout.write(f"Linhas lidas: {n} · registros distintos: {len(melhor)}")
        if dry:
            validos = sum(1 for v in melhor.values() if v["situacao"] == "Válido")
            self.stdout.write(self.style.WARNING(
                f"[dry-run] gravaria {len(melhor)} registros ({validos} válidos)."))
        else:
            criados = atualizados = 0
            with transaction.atomic():
                existentes = set(
                    RegistroAnvisaProdutoSaude.objects.values_list("numero_registro", flat=True))
                novos, updates = [], []
                for reg, d in melhor.items():
                    if reg in existentes:
                        updates.append(d)
                    else:
                        novos.append(RegistroAnvisaProdutoSaude(**d))
                RegistroAnvisaProdutoSaude.objects.bulk_create(novos, batch_size=2000)
                criados = len(novos)
                for d in updates:
                    RegistroAnvisaProdutoSaude.objects.filter(
                        numero_registro=d["numero_registro"]).update(
                        **{k: v for k, v in d.items() if k != "numero_registro"})
                    atualizados += 1
            self.stdout.write(self.style.SUCCESS(
                f"Produtos: {criados} criados, {atualizados} atualizados."))

        # ── AFE (opcional) ────────────────────────────────────────────────────
        if opts.get("afe"):
            self.stdout.write("Baixando base de AFE (empresas nacionais) …")
            conteudo_afe = self._baixar(URL_AFE)
            leitor_afe = self._linhas(conteudo_afe)
            melhor_afe = {}
            m = 0
            for row in leitor_afe:
                m += 1
                if limite and m > limite:
                    break
                cnpj = "".join(ch for ch in (row.get("NU_CNPJ") or "") if ch.isdigit())[:14]
                if not cnpj:
                    continue
                ativo = (row.get("ATIVO") or "").strip().upper() == "SIM"
                atual = melhor_afe.get(cnpj)
                if atual and atual["ativo"] and not ativo:
                    continue
                melhor_afe[cnpj] = {
                    "cnpj": cnpj,
                    "razao_social": (row.get("NO_RAZAO_SOCIAL") or "").strip()[:250],
                    "numero_afe": (row.get("NU_AUTORIZACAO") or "").strip()[:40],
                    "uf": (row.get("UF") or "").strip()[:2],
                    "ativo": ativo,
                }
            self.stdout.write(f"AFE: {m} linhas · {len(melhor_afe)} CNPJs distintos")
            if not dry:
                with transaction.atomic():
                    existentes = set(EmpresaAfeAnvisa.objects.values_list("cnpj", flat=True))
                    novos = [EmpresaAfeAnvisa(**d) for c, d in melhor_afe.items()
                             if c not in existentes]
                    EmpresaAfeAnvisa.objects.bulk_create(novos, batch_size=2000)
                    for c, d in melhor_afe.items():
                        if c in existentes:
                            EmpresaAfeAnvisa.objects.filter(cnpj=c).update(
                                **{k: v for k, v in d.items() if k != "cnpj"})
                self.stdout.write(self.style.SUCCESS(f"AFE: {len(novos)} criadas."))
