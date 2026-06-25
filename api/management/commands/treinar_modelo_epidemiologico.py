from django.core.management.base import BaseCommand

from api.epidemiologia_ml import treinar_modelo_oficial


class Command(BaseCommand):
    help = (
        "Treina o modelo de ML de risco epidemiologico com dado oficial real "
        "ja importado em FonteOficialAgregado (ver processar_fonte_oficial). "
        "Recusa treinar (de forma transparente) quando nao ha amostras reais "
        "suficientes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fonte-id", default="sinan_agravos")
        parser.add_argument("--indicador", default="dengue_notificacoes_sinan")

    def handle(self, *args, **options):
        meta = treinar_modelo_oficial(fonte_id=options["fonte_id"], indicador=options["indicador"])

        if not meta.get("treinado"):
            self.stdout.write(self.style.WARNING(
                f"Nao treinado: {meta.get('motivo')} "
                f"({meta.get('n_amostras', 0)}/{meta.get('minimo_necessario')} amostras reais)."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Modelo treinado com {meta['n_amostras']} amostras oficiais reais "
            f"({meta['fonte_id']}/{meta['indicador']}) cobrindo estados: {', '.join(meta['estados'])}."
        ))
        self.stdout.write(f"F1 (cross-val): {meta['cv_f1_media']:.3f} +/- {meta['cv_f1_std']:.3f}")
