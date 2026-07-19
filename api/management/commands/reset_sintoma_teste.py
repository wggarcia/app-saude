from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Remove registros de sintoma das últimas 24h para um device_id de teste (permite re-testar sem esperar 7 dias)"

    def add_arguments(self, parser):
        parser.add_argument("--device", required=True, type=str, help="device_id exato para resetar")
        parser.add_argument(
            "--dias",
            type=int,
            default=7,
            help="Janela em dias para remover (padrão: 7)",
        )

    def handle(self, *args, **options):
        from api.models import Empresa, RegistroSintoma
        from api.epidemiologia import PUBLIC_APP_EMAIL
        from django.utils import timezone
        from datetime import timedelta

        device_id = options["device"].strip()
        dias = options["dias"]

        if not device_id:
            raise CommandError("--device é obrigatório")

        empresa = Empresa.objects.using("owner").filter(email=PUBLIC_APP_EMAIL).first()
        if not empresa:
            empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
        if not empresa:
            raise CommandError(f"Empresa pública '{PUBLIC_APP_EMAIL}' não encontrada no banco")

        janela = timezone.now() - timedelta(days=dias)
        qs = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id=device_id,
            data_registro__gte=janela,
        )
        count = qs.count()

        if count == 0:
            self.stdout.write(self.style.WARNING(
                f"Nenhum registro encontrado para device '{device_id}' nos últimos {dias} dias."
            ))
            return

        self.stdout.write(f"Encontrados {count} registro(s) para deletar...")
        qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"OK — {count} registro(s) removido(s). Device '{device_id}' pode enviar novamente."
        ))
