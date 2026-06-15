from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from api.epidemiologia import clear_panorama_cache
from api.models import DispositivoAutorizado, DispositivoPushPublico, RegistroSintoma
from api.views import _empresa_app_publico


DEVICE_PREFIX = "reuniao-br-"
SOURCE_MARKER = "reuniao-soluscrt-brasil"


class Command(BaseCommand):
    help = "Remove focos simulados da demo de reuniao SolusCRT."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirma a limpeza da demo.")
        parser.add_argument(
            "--publico",
            action="store_true",
            help="Remove todos os registros da empresa publica do app.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Use --yes para confirmar a limpeza da demo de reuniao.")

        empresa = _empresa_app_publico()
        self._set_rls(empresa.id)

        qs_registros = RegistroSintoma.objects.filter(empresa=empresa)
        if not options["publico"]:
            qs_registros = qs_registros.filter(
                Q(device_id__startswith=DEVICE_PREFIX) | Q(fonte_referencia__icontains=SOURCE_MARKER)
            )
        registros_apagados = qs_registros.delete()[0]

        if options["publico"]:
            dispositivos_apagados = DispositivoAutorizado.objects.filter(empresa=empresa).delete()[0]
            push_apagados = DispositivoPushPublico.objects.all().delete()[0]
        else:
            dispositivos_apagados = DispositivoAutorizado.objects.filter(
                empresa=empresa,
                device_id__startswith=DEVICE_PREFIX
            ).delete()[0]
            push_apagados = DispositivoPushPublico.objects.filter(
                device_id__startswith=DEVICE_PREFIX
            ).delete()[0]

        clear_panorama_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo de reuniao removida: registros={registros_apagados}, "
                f"dispositivos={dispositivos_apagados}, push={push_apagados}, "
                f"empresa={empresa.email}, em={timezone.now().isoformat()}"
            )
        )

    def _set_rls(self, empresa_id):
        from django.db import connection

        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(empresa_id)])
