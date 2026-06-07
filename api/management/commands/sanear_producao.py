from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import AlertaGovernamental, DispositivoAutorizado, Empresa, RegistroSintoma
from api.services.public_integrity import (
    q_alerta_governamental_sintetico,
    q_registro_sintoma_sintetico,
)


DEMO_EMAILS = {
    "demo.sst@soluscrt.com",
    "demo.farmacia@soluscrt.com",
    "demo.hospital@soluscrt.com",
    "demo.governo@soluscrt.com",
    "demo.plano@soluscrt.com",
    "empresa.demo@soluscrt.com",
}


class Command(BaseCommand):
    help = "Remove contas demo e residuos sintéticos explícitos da produção."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Executa a limpeza de verdade. Sem esta flag, apenas mostra o preview.",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        if self._is_production() and not apply:
            raise CommandError("Em producao use --apply para executar a limpeza.")

        preview = self._collect_preview()

        self.stdout.write("\n=== Sanear Produção ===\n")
        self.stdout.write(f"Contas demo encontradas: {preview['empresas_demo']}")
        self.stdout.write(f"Alertas sintéticos encontrados: {preview['alertas_sinteticos']}")
        self.stdout.write(f"Registros sintéticos encontrados: {preview['registros_sinteticos']}")
        self.stdout.write(f"Dispositivos sintéticos encontrados: {preview['dispositivos_sinteticos']}")

        if not apply:
            self.stdout.write(self.style.WARNING("\nPreview apenas. Use --apply para executar a limpeza."))
            return

        with transaction.atomic():
            removidos_empresas = Empresa.objects.filter(email__in=DEMO_EMAILS).delete()[0]
            removidos_alertas = AlertaGovernamental.objects.filter(q_alerta_governamental_sintetico()).delete()[0]
            removidos_registros = RegistroSintoma.objects.filter(q_registro_sintoma_sintetico()).delete()[0]
            removidos_dispositivos = DispositivoAutorizado.objects.filter(
                device_id__istartswith="stress-soluscrt-brasil"
            ).delete()[0]
            removidos_dispositivos += DispositivoAutorizado.objects.filter(device_id__istartswith="sim-br-").delete()[0]
            removidos_dispositivos += DispositivoAutorizado.objects.filter(device_id__istartswith="demo-").delete()[0]
            removidos_dispositivos += DispositivoAutorizado.objects.filter(device_id__istartswith="test-").delete()[0]
            removidos_dispositivos += DispositivoAutorizado.objects.filter(device_id__istartswith="fake-").delete()[0]

        self.stdout.write(self.style.SUCCESS("\nLimpeza concluída."))
        self.stdout.write(f"Empresas removidas: {removidos_empresas}")
        self.stdout.write(f"Alertas removidos: {removidos_alertas}")
        self.stdout.write(f"Registros removidos: {removidos_registros}")
        self.stdout.write(f"Dispositivos removidos: {removidos_dispositivos}")

    def _is_production(self) -> bool:
        from django.conf import settings

        return bool(getattr(settings, "IS_PRODUCTION", False))

    def _collect_preview(self):
        return {
            "empresas_demo": Empresa.objects.filter(email__in=DEMO_EMAILS).count(),
            "alertas_sinteticos": AlertaGovernamental.objects.filter(q_alerta_governamental_sintetico()).count(),
            "registros_sinteticos": RegistroSintoma.objects.filter(q_registro_sintoma_sintetico()).count(),
            "dispositivos_sinteticos": (
                DispositivoAutorizado.objects.filter(device_id__istartswith="stress-soluscrt-brasil").count()
                + DispositivoAutorizado.objects.filter(device_id__istartswith="sim-br-").count()
                + DispositivoAutorizado.objects.filter(device_id__istartswith="demo-").count()
                + DispositivoAutorizado.objects.filter(device_id__istartswith="test-").count()
                + DispositivoAutorizado.objects.filter(device_id__istartswith="fake-").count()
            ),
        }

