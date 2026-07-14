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
    # ── GDELT (detecção por palavra-chave em notícias gerais) ──────────────────
    "gdelt-br":       ("gdelt", GDELT_URL_BR),
    "gdelt-intl":     ("gdelt", GDELT_URL_INTL),

    # ── Brasil ─────────────────────────────────────────────────────────────────
    "agbrasil":       ("rss", ("AgBrasil",  "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml")),
    "fiocruz":        ("rss", ("Fiocruz",   "https://agencia.fiocruz.br/rss.xml")),
    "g1":             ("rss", ("G1-Saude",  "https://g1.globo.com/rss/g1/ciencia-e-saude/")),
    "folha":          ("rss", ("Folha",     "https://feeds.folha.uol.com.br/equilibrioesaude/rss091.xml")),
    "svs":            ("rss", ("SVS-MS",    "https://www.gov.br/saude/pt-br/assuntos/noticias-ms/noticias-da-saude/RSS")),  # RSS 1.0/RDF — Notícias oficiais do Ministério da Saúde

    # ── Américas ───────────────────────────────────────────────────────────────
    "opas":           ("rss", ("OPAS",      "https://www.paho.org/pt/rss.xml")),
    "cdc-eid":        ("rss", ("CDC-EID",   "https://wwwnc.cdc.gov/eid/rss/expedited.xml")),
    "healio-id":      ("rss", ("Healio-ID", "https://www.healio.com/rss/infectious-disease")),

    # ── Europa ─────────────────────────────────────────────────────────────────
    "ecdc":           ("rss", ("ECDC",      "https://www.ecdc.europa.eu/en/rss.xml")),
    "bbc-health":     ("rss", ("BBC-Health","https://feeds.bbci.co.uk/news/health/rss.xml")),

    # ── África ─────────────────────────────────────────────────────────────────
    "who-africa":     ("rss", ("WHO-Africa","https://www.afro.who.int/rss.xml")),
    "nicd-za":        ("rss", ("NICD-ZA",   "https://www.nicd.ac.za/feed/")),
    "reliefweb":      ("rss", ("ReliefWeb", "https://reliefweb.int/updates/rss.xml?primary_country=0&topic=3&format=0")),

    # ── Ásia ───────────────────────────────────────────────────────────────────
    "india-pib":      ("rss", ("India-PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3")),
    "nhc-china":      ("rss", ("NHC-China", "http://en.nhc.gov.cn/rss.xml")),

    # ── Global ─────────────────────────────────────────────────────────────────
    "who":            ("rss", ("WHO",           "https://www.who.int/feeds/entity/csr/don/en/rss.xml")),
    "outbreaknews":   ("rss", ("OutbreakNews",  "https://outbreaknewstoday.com/feed/")),
    "sciencedaily":   ("rss", ("ScienceDaily",  "https://www.sciencedaily.com/rss/top/health.xml")),
}

# Fontes de saúde curadas — salvam todos os artigos sem exigir palavra-chave de doença
# Fontes de vigilância epidemiológica pura — salvam TODOS os artigos sem filtro de doença.
# NÃO incluir mídia geral (Folha, G1, BBC) mesmo com seção de saúde — publicam lifestyle/Copa etc.
FONTES_CURADAS = {
    "agbrasil", "fiocruz", "svs",          # Brasil — agências oficiais
    "opas", "cdc-eid", "healio-id",        # Américas — vigilância
    "ecdc",                                 # Europa — vigilância
    "who-africa", "nicd-za", "reliefweb",  # África
    "india-pib", "nhc-china",              # Ásia — ministérios de saúde
    "who", "outbreaknews", "sciencedaily", # Global — vigilância e ciência
}

# Cron BR — fontes nacionais + Américas + global diário
FONTES_PADRAO = "gdelt-br,agbrasil,folha,g1,opas,cdc-eid,outbreaknews"

# Cron Internacional — Europa, África, Ásia + global científico
FONTES_INTL   = "gdelt-intl,who,ecdc,bbc-health,who-africa,nicd-za,reliefweb,india-pib,nhc-china,sciencedaily,healio-id"


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
            curada = fonte_key in FONTES_CURADAS
            if tipo == "gdelt":
                novos = self._fetch_gdelt(params)
            else:
                nome, url = params
                novos = self._fetch_rss(nome, url)
            for a in novos:
                a["curada"] = curada
            artigos.extend(novos)

        self.stdout.write(f"Total bruto: {len(artigos)} artigos coletados.")

        corte = datetime.now(timezone.utc) - timedelta(days=7)

        def _dentro_janela(pub):
            if pub is None:
                return True
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            return pub >= corte

        artigos_relevantes = [
            a for a in artigos
            if _dentro_janela(a["publicado_em"])
            and (a["curada"] or a["doencas_detectadas"])
        ]
        self.stdout.write(f"Relevantes (saúde ou doença detectada, ≤7 dias): {len(artigos_relevantes)}")

        if dry_run:
            for a in artigos_relevantes:
                tag = "CURADA" if a["curada"] else ",".join(a["doencas_detectadas"])
                self.stdout.write(
                    f"  [{a['nivel_alerta'].upper()}] {a['titulo'][:80]} — {tag}"
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
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "rss1": "http://purl.org/rss/1.0/",
                "dc":   "http://purl.org/dc/elements/1.1/",
            }

            items = root.findall(".//item")
            if not items:
                items = root.findall(".//atom:entry", ns)
            if not items:
                items = root.findall(".//rss1:item", ns)

            for item in items[:30]:
                titulo  = _tag(item, ["title",      "atom:title",   "rss1:title"],   ns)
                url     = _tag(item, ["link",       "atom:link",    "rss1:link"],    ns)
                resumo  = _tag(item, ["description", "summary", "atom:summary", "rss1:description"], ns)
                pub_str = _tag(item, ["pubDate",     "published", "atom:published", "dc:date"], ns)

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
