from django.core.management.base import BaseCommand, CommandError

from api.models import RegistroSintoma


class Command(BaseCommand):
    help = "Remove focos/registros de sintomas simulados preservando contas, contratos e fontes oficiais."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirma a limpeza dos focos.")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Use --yes para confirmar a limpeza dos focos simulados.")

        total = RegistroSintoma.objects.count()
        RegistroSintoma.objects.all()._raw_delete(RegistroSintoma.objects.db)
        self.stdout.write(self.style.SUCCESS(f"Focos removidos: {total}"))
