import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from django.core.management.base import BaseCommand
from django.db import IntegrityError

from api.models import Empresa, NoticiaEpidemiologica

# ── Doenças monitoradas ────────────────────────────────────────────────────────

DOENCAS = {
    "dengue":         ["dengue"],
    "zika":           ["zika"],
    "chikungunya":    ["chikungunya"],
    "influenza":      ["influenza", "gripe", "h1n1", "h3n2"],
    "covid":          ["covid", "sars-cov", "coronavirus"],
    "febre_amarela":  ["febre amarela", "febre-amarela", "yellow fever"],
    "malaria":        ["malária", "malaria", "plasmodium"],
    "leptospirose":   ["leptospirose", "leptospira"],
    "mpox":           ["mpox", "monkeypox", "varíola dos macacos"],
    "sarampo":        ["sarampo", "measles"],
    "hepatite":       ["hepatite a", "hepatite b", "hepatite c", "hepatite e"],
    "hantavirus":     ["hantavírus", "hantavirus"],
    "leishmaniose":   ["leishmaniose", "leishmaniasis"],
    "coqueluche":     ["coqueluche", "pertussis"],
    "meningite":      ["meningite", "meningococo"],
    "botulismo":      ["botulismo"],
    "raiva":          ["raiva humana", "raiva animal"],
    "febre_tifoide":  ["febre tifoide", "typhoid"],
    "peste":          ["peste bubônica", "yersinia pestis"],
    "varicela":       ["varicela", "catapora"],
}

PALAVRAS_CRITICAS = [
    "surto", "epidemia", "pandemia", "alerta máximo",
    "emergência sanitária", "emergencia sanitaria",
    "outbreak", "epidemic", "pandemic",
]

PALAVRAS_ALERTA = [
    "aumento de casos", "elevação de casos", "crescimento de casos",
    "aumento significativo", "casos confirmados", "notificação compulsória",
    "rise in cases", "spike", "surge",
]

# ── URLs das fontes ────────────────────────────────────────────────────────────

GDELT_URL_BR = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query=epidemia+dengue+zika+gripe+surto+leptospirose+febre"
    "&mode=artlist&maxrecords=25&format=json"
    "&sourcelang=por&sourcecountry=BR"
)

GDELT_URL_INTL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query=epidemic+outbreak+disease+dengue+zika+fever+malaria+mpox"
    "&mode=artlist&maxrecords=25&format=json"
    "&sourcelang=eng"
)

# ── Catálogo de fontes disponíveis ─────────────────────────────────────────────
# Cada entrada: tipo ("gdelt" ou "rss") + configuração

FONTES_CATALOGO = {
    "gdelt-br":    ("gdelt", GDELT_URL_BR),
    "gdelt-intl":  ("gdelt", GDELT_URL_INTL),
    "opas":        ("rss",   ("OPAS",    "https://www.paho.org/pt/rss.xml")),
    "svs":         ("rss",   ("SVS",     "https://www.gov.br/saude/pt-br/assuntos/noticias/RSS")),
    # ProMED encerrou RSS público em 2025; substituído por CDC EID Expedited
    "cdc-eid":     ("rss",   ("CDC-EID", "https://wwwnc.cdc.gov/eid/rss/expedited.xml")),
    "who":         ("rss",   ("WHO",     "https://www.who.int/feeds/entity/csr/don/en/rss.xml")),
    "fiocruz":     ("rss",   ("Fiocruz", "https://agencia.fiocruz.br/rss.xml")),
    "ecdc":        ("rss",   ("ECDC",    "https://www.ecdc.europa.eu/en/rss.xml")),
}

FONTES_PADRAO = "gdelt-br,opas,svs,cdc-eid"


class Command(BaseCommand):
    help = (
        "Coleta notícias epidemiológicas de GDELT e RSS — armazena em NoticiaEpidemiologica. "
        f"Fontes padrão: {FONTES_PADRAO}."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--empresa-id",
            type=int,
            help="Limita a coleta a uma única empresa (ID). Padrão: todas as ativas.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Exibe as notícias encontradas sem salvar no banco.",
        )
        parser.add_argument(
            "--fontes",
            default=FONTES_PADRAO,
            help=(
                f"Fontes separadas por vírgula. Padrão: {FONTES_PADRAO}. "
                f"Disponíveis: {', '.join(FONTES_CATALOGO)}."
            ),
        )

    def handle(self, *args, **options):
        empresa_id = options.get("empresa_id")
        dry_run    = options["dry_run"]
        fontes_raw = options.get("fontes") or FONTES_PADRAO
        fontes     = [f.strip() for f in fontes_raw.split(",") if f.strip()]

        empresas = (
            Empresa.objects.filter(pk=empresa_id, ativo=True)
            if empresa_id
            else Empresa.objects.filter(ativo=True)
        )

        if not empresas.exists():
            self.stdout.write(self.style.WARNING("Nenhuma empresa ativa encontrada."))
            return

        self.stdout.write(f"Fontes ativas: {', '.join(fontes)}")

        artigos = []
        for fonte_key in fontes:
            config = FONTES_CATALOGO.get(fonte_key)
            if not config:
                self.stderr.write(f"Fonte desconhecida: '{fonte_key}' — ignorada.")
                continue
            tipo, params = config
            if tipo == "gdelt":
                artigos.extend(self._fetch_gdelt(params))
            else:
                nome, url = params
                artigos.extend(self._fetch_rss(nome, url))

        self.stdout.write(f"Total bruto: {len(artigos)} artigos coletados.")

        corte = datetime.now(timezone.utc) - timedelta(days=7)
        artigos_relevantes = [
            a for a in artigos
            if a["doencas_detectadas"]
            and (a["publicado_em"] is None or a["publicado_em"] >= corte)
        ]
        self.stdout.write(f"Relevantes (com doença identificada, ≤7 dias): {len(artigos_relevantes)}")

        if dry_run:
            for a in artigos_relevantes:
                self.stdout.write(
                    f"  [{a['nivel_alerta'].upper()}] {a['titulo'][:80]} — {a['doencas_detectadas']}"
                )
            return

        salvos = 0
        for empresa in empresas:
            for a in artigos_relevantes:
                try:
                    NoticiaEpidemiologica.objects.create(
                        empresa=empresa,
                        titulo=a["titulo"],
                        fonte=a["fonte"],
                        url=a["url"],
                        resumo=a["resumo"],
                        doencas_detectadas=a["doencas_detectadas"],
                        nivel_alerta=a["nivel_alerta"],
                        publicado_em=a["publicado_em"],
                    )
                    salvos += 1
                except IntegrityError:
                    pass  # unique_together (empresa, url) — já existe, ignora

        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído: {salvos} notícias salvas para {empresas.count()} empresa(s)."
            )
        )

    # ── Coleta GDELT ──────────────────────────────────────────────────────────

    def _fetch_gdelt(self, url):
        results = []
        for attempt in range(2):
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 429:
                    if attempt == 0:
                        time.sleep(5)
                        continue
                    self.stderr.write("GDELT indisponível (rate limit) — pulando.")
                    break
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("articles", []):
                    titulo       = item.get("title", "").strip()
                    url_artigo   = item.get("url", "").strip()
                    resumo       = item.get("seendate", "")[:20]
                    pub_str      = item.get("seendate", "")
                    publicado_em = _parse_gdelt_date(pub_str)

                    texto   = (titulo + " " + resumo).lower()
                    doencas = _detectar_doencas(texto)
                    nivel   = _nivel_alerta(texto)

                    if titulo and url_artigo:
                        results.append({
                            "fonte": "GDELT",
                            "titulo": titulo,
                            "url": url_artigo,
                            "resumo": resumo,
                            "doencas_detectadas": doencas,
                            "nivel_alerta": nivel,
                            "publicado_em": publicado_em,
                        })
                break  # sucesso
            except Exception as exc:
                self.stderr.write(f"GDELT erro: {exc}")
                break
        return results

    # ── Coleta RSS ────────────────────────────────────────────────────────────

    def _fetch_rss(self, nome_fonte, feed_url):
        results = []
        try:
            resp = requests.get(feed_url, timeout=15, headers={"User-Agent": "SolusCRT/2.0"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            ns   = {"atom": "http://www.w3.org/2005/Atom"}

            items = root.findall(".//item")
            if not items:
                items = root.findall(".//atom:entry", ns)

            for item in items[:30]:
                titulo  = _tag(item, ["title",       "atom:title"],   ns)
                url     = _tag(item, ["link",         "atom:link"],    ns)
                resumo  = _tag(item, ["description",  "summary",  "atom:summary"], ns)
                pub_str = _tag(item, ["pubDate",      "published", "atom:published"], ns)

                if not titulo or not url:
                    continue

                publicado_em = _parse_rss_date(pub_str)
                texto        = (titulo + " " + resumo).lower()
                doencas      = _detectar_doencas(texto)
                nivel        = _nivel_alerta(texto)

                results.append({
                    "fonte": nome_fonte,
                    "titulo": titulo[:500],
                    "url": url[:900],
                    "resumo": resumo[:2000],
                    "doencas_detectadas": doencas,
                    "nivel_alerta": nivel,
                    "publicado_em": publicado_em,
                })
        except Exception as exc:
            self.stderr.write(f"RSS [{nome_fonte}] erro: {exc}")
        return results


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tag(element, tag_names, ns):
    for name in tag_names:
        child = element.find(name, ns)
        if child is not None:
            if name == "atom:link":
                return child.get("href", "")
            return (child.text or "").strip()
    return ""


def _detectar_doencas(texto: str) -> list:
    encontradas = []
    for doenca, palavras in DOENCAS.items():
        if any(p in texto for p in palavras):
            encontradas.append(doenca)
    return encontradas


def _nivel_alerta(texto: str) -> str:
    if any(p in texto for p in PALAVRAS_CRITICAS):
        return "critico"
    if any(p in texto for p in PALAVRAS_ALERTA):
        return "alerta"
    return "informativo"


def _parse_gdelt_date(s: str):
    try:
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _parse_rss_date(s: str):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:25], fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            continue
    return None
