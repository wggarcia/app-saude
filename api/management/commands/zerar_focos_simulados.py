from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from api.models import Empresa, RegistroSintoma


class Command(BaseCommand):
    help = (
        "Remove TODOS os focos/registros de sintomas (mapa + app), preservando "
        "contas, contratos e fontes oficiais. Respeita o RLS apagando por empresa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirma a limpeza dos focos.")

    def _set_rls(self, empresa_id):
        # Define o tenant boundary antes de apagar — sem isso, o usuário restrito
        # (APP_DATABASE_URL) não enxerga nem apaga os registros sob o RLS.
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(empresa_id)])

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Use --yes para confirmar a limpeza de todos os focos.")

        # A tabela Empresa não é protegida por RLS (é a própria tabela de tenants),
        # então conseguimos listar todos os IDs e apagar os registros de cada um.
        empresa_ids = list(Empresa.objects.values_list("id", flat=True))

        total_apagados = 0
        for empresa_id in empresa_ids:
            self._set_rls(empresa_id)
            apagados, _ = RegistroSintoma.objects.filter(empresa_id=empresa_id).delete()
            total_apagados += apagados

        self.stdout.write(self.style.SUCCESS(f"Focos removidos: {total_apagados}"))
