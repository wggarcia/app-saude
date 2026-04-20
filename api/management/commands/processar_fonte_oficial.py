from django.core.management.base import BaseCommand, CommandError

from api.pipeline_oficial import MANIFEST_BY_ID, preparar_execucao_fonte_oficial


class Command(BaseCommand):
    help = "Prepara ou executa pipelines oficiais OpenDataSUS/DATASUS em modo controlado."

    def add_arguments(self, parser):
        parser.add_argument("fonte_id", choices=sorted(MANIFEST_BY_ID.keys()))
        parser.add_argument("--uf", help="UF opcional para limitar a coleta, ex: RJ")
        parser.add_argument("--inicio", help="Periodo inicial opcional, ex: 2026-01")
        parser.add_argument("--fim", help="Periodo final opcional, ex: 2026-04")
        parser.add_argument(
            "--max-bytes",
            type=int,
            default=200_000,
            help="Limite maximo de bytes para amostra controlada.",
        )
        parser.add_argument(
            "--max-linhas",
            type=int,
            default=1000,
            help="Limite maximo de linhas para amostra controlada.",
        )
        parser.add_argument(
            "--incremental",
            action="store_true",
            help="Processa em blocos controlados por Range, sem baixar o arquivo completo.",
        )
        parser.add_argument(
            "--byte-start",
            type=int,
            default=0,
            help="Byte inicial para a coleta incremental.",
        )
        parser.add_argument(
            "--bloco-bytes",
            type=int,
            default=200_000,
            help="Tamanho de cada bloco incremental em bytes.",
        )
        parser.add_argument(
            "--max-blocos",
            type=int,
            default=1,
            help="Numero maximo de blocos incrementais nesta execucao.",
        )
        parser.add_argument(
            "--executar-download",
            action="store_true",
            help="Executa somente coleta controlada/amostral quando suportada.",
        )

    def handle(self, *args, **options):
        try:
            execucao = preparar_execucao_fonte_oficial(
                options["fonte_id"],
                uf=options.get("uf"),
                periodo_inicio=options.get("inicio"),
                periodo_fim=options.get("fim"),
                executar_download=options.get("executar_download", False),
                max_bytes=options.get("max_bytes", 200_000),
                max_linhas=options.get("max_linhas", 1000),
                incremental=options.get("incremental", False),
                byte_start=options.get("byte_start", 0),
                bloco_bytes=options.get("bloco_bytes", 200_000),
                max_blocos=options.get("max_blocos", 1),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Execucao {execucao.id} registrada: {execucao.fonte_id} / {execucao.status}"
            )
        )
        self.stdout.write(execucao.mensagem)
