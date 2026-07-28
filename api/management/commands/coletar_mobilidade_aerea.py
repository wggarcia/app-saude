"""
Coleta o fluxo de voos entre municípios brasileiros (OpenSky) e grava em
MatrizMobilidade. Alimenta o modelo de dispersão (api/modelo_dispersao.py).

Uso:
    python manage.py coletar_mobilidade_aerea            # últimas 24h
    python manage.py coletar_mobilidade_aerea --dias 3   # últimos 3 dias
    python manage.py coletar_mobilidade_aerea --dry-run  # não grava, só reporta

Roda como cron (1x/dia). Sem credencial OpenSky (OPENSKY_CLIENT_ID/SECRET no
ambiente) usa acesso anônimo, com rate limit menor — suficiente para o MVP.
Se a API não responder, o comando termina sem erro e sem gravar lixo: a
matriz do dia anterior continua valendo.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api import pipeline_mobilidade as pm
from api.models import MatrizMobilidade


class Command(BaseCommand):
    help = "Coleta fluxo de voos entre municípios (OpenSky) para MatrizMobilidade."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=1, help="Janela em dias (default 1).")
        parser.add_argument("--dry-run", action="store_true", help="Não grava, só reporta.")

    def handle(self, *args, **opts):
        dias = max(1, opts["dias"])
        dry = opts["dry_run"]

        problemas = pm.validar_aeroportos()
        if problemas:
            self.stderr.write(self.style.ERROR("Tabela de aeroportos inconsistente:"))
            for p in problemas:
                self.stderr.write(f"  - {p}")
            return

        fim = timezone.now()
        inicio = fim - timedelta(days=dias)
        periodo = fim.date().isoformat()
        self.stdout.write(f"Coletando voos de {inicio:%Y-%m-%d %H:%M} a {fim:%Y-%m-%d %H:%M} (UTC)...")

        matriz = pm.coletar_matriz_nacional(pm.epoch_utc(inicio), pm.epoch_utc(fim))
        if not matriz:
            self.stdout.write(self.style.WARNING(
                "Nenhum voo retornado (API indisponível ou sem credencial/rate limit). "
                "Nada foi gravado — a matriz anterior continua válida."
            ))
            return

        normalizada = pm.matriz_para_pesos_normalizados(matriz)
        total_pares = len(matriz)
        total_voos = sum(matriz.values())
        self.stdout.write(f"{total_pares} rotas, {total_voos} voos agregados.")

        if dry:
            top = sorted(matriz.items(), key=lambda kv: kv[1], reverse=True)[:10]
            self.stdout.write("Top 10 rotas (dry-run, nada gravado):")
            for (o, d), n in top:
                go, gd = pm.geo_municipio(o), pm.geo_municipio(d)
                on = go["nome"] if go else o
                dn = gd["nome"] if gd else d
                self.stdout.write(f"  {on} → {dn}: {n} voos")
            return

        gravados = 0
        with transaction.atomic():
            for (o, d), n in matriz.items():
                go, gd = pm.geo_municipio(o), pm.geo_municipio(d)
                peso = normalizada.get(o, {}).get(d, 0.0)
                MatrizMobilidade.objects.update_or_create(
                    origem_ibge=str(o), destino_ibge=str(d),
                    modo=MatrizMobilidade.MODO_AEREO, periodo=periodo,
                    defaults={
                        "origem_nome": go["nome"] if go else "",
                        "destino_nome": gd["nome"] if gd else "",
                        "origem_uf": go["uf"] if go else "",
                        "destino_uf": gd["uf"] if gd else "",
                        "viagens": n,
                        "peso": peso,
                        "fonte": "opensky",
                        "metadados": {"janela_dias": dias, "coletado_em": fim.isoformat()},
                    },
                )
                gravados += 1
        self.stdout.write(self.style.SUCCESS(f"OK: {gravados} rotas gravadas em MatrizMobilidade (período {periodo})."))
