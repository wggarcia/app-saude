"""
Agente 3 — Gerador de Alertas Epidemiológicos.

Lê notícias analisadas pelo Agente 2 (ia_analisado=True, alerta_disparado=False)
e aplica o nível de alerta baseado no score de risco.

Este agente é exclusivo do segmento Governo / Vigilância Epidemiológica.
NÃO usa modelos SST (FuncionarioSST, NotificacaoFuncionario).

Os alertas ficam disponíveis via endpoint REST:
  GET /api/governo/noticias-epidemiologicas/?nivel=critico
  GET /api/governo/noticias-epidemiologicas/?nivel=alerta

O dashboard de governo consome esse endpoint e exibe em tempo real.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import NoticiaEpidemiologica

SCORE_ALERTA  = 4.0
SCORE_ALTO    = 7.0
SCORE_CRITICO = 9.0


class Command(BaseCommand):
    help = "Agente 3: consolida níveis de alerta das notícias analisadas para o dashboard de governo."

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, help="Limita a uma empresa.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Exibe os alertas sem salvar.")

    def handle(self, *args, **options):
        dry_run    = options["dry_run"]
        empresa_id = options.get("empresa_id")

        qs = NoticiaEpidemiologica.objects.filter(
            ia_analisado=True,
            alerta_disparado=False,
        )
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        pendentes = list(qs.select_related("empresa").order_by("-ia_score_risco"))

        if not pendentes:
            self.stdout.write("Nenhuma notícia pendente de consolidação de alerta.")
            return

        criticos  = 0
        alertas   = 0
        infos     = 0

        for noticia in pendentes:
            score = noticia.ia_score_risco or 0

            if score >= SCORE_CRITICO:
                nivel = "critico"
                criticos += 1
            elif score >= SCORE_ALERTA:
                nivel = "alerta"
                alertas += 1
            else:
                nivel = "informativo"
                infos += 1

            if dry_run:
                self.stdout.write(
                    f"  [{nivel.upper()}][score={score:.1f}] "
                    f"{noticia.empresa.nome}: {noticia.titulo[:70]}"
                )
                continue

            with transaction.atomic():
                noticia.nivel_alerta     = nivel
                noticia.alerta_disparado = True
                noticia.save(update_fields=["nivel_alerta", "alerta_disparado"])

        sufixo = " (DRY-RUN)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Alertas{sufixo}: {criticos} críticos | {alertas} alertas | {infos} informativos. "
                f"Disponíveis em /api/governo/noticias-epidemiologicas/"
            )
        )
