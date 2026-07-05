from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from api.models import NoticiaEpidemiologica


class Command(BaseCommand):
    help = "Remove notícias epidemiológicas com mais de 7 dias do banco."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=7,
            help="Número de dias de retenção (padrão: 7).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Exibe quantas seriam removidas sem deletar.",
        )

    def handle(self, *args, **options):
        dias    = options["dias"]
        dry_run = options["dry_run"]
        corte   = datetime.now(timezone.utc) - timedelta(days=dias)

        qs = NoticiaEpidemiologica.objects.filter(criado_em__lt=corte)
        total = qs.count()

        if total == 0:
            self.stdout.write("Nenhuma notícia antiga para remover.")
            return

        if dry_run:
            self.stdout.write(f"[dry-run] {total} notícias seriam removidas (anteriores a {corte.date()}).")
            return

        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"{total} notícias antigas removidas (anteriores a {corte.date()})."))
