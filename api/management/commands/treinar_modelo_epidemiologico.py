from django.core.management.base import BaseCommand

from api.epidemiologia_ml import treinar_modelo_oficial, treinar_todas_doencas_registradas


class Command(BaseCommand):
    help = (
        "Treina o(s) modelo(s) de ML de risco epidemiologico com dado oficial real "
        "ja importado em FonteOficialAgregado (ver processar_fonte_oficial). "
        "Sem --fonte-id/--indicador, treina TODAS as doencas registradas "
        "(api.epidemiologia_ml.DOENCAS_REGISTRADAS). Recusa treinar (de forma "
        "transparente) quando nao ha amostras reais suficientes para uma doenca."
    )

    def add_arguments(self, parser):
        parser.add_argument("--fonte-id", default=None)
        parser.add_argument("--indicador", default=None)

    def _reportar(self, nome_doenca, meta):
        if not meta.get("treinado"):
            self.stdout.write(self.style.WARNING(
                f"[{nome_doenca}] Nao treinado: {meta.get('motivo')} "
                f"({meta.get('n_amostras', 0)}/{meta.get('minimo_necessario')} amostras reais)."
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"[{nome_doenca}] Modelo treinado com {meta['n_amostras']} amostras oficiais reais "
            f"({meta['fonte_id']}/{meta['indicador']}) cobrindo estados: {', '.join(meta['estados'])}."
        ))
        self.stdout.write(f"[{nome_doenca}] F1 (cross-val): {meta['cv_f1_media']:.3f} +/- {meta['cv_f1_std']:.3f}")

    def handle(self, *args, **options):
        if options.get("fonte_id") and options.get("indicador"):
            meta = treinar_modelo_oficial(fonte_id=options["fonte_id"], indicador=options["indicador"])
            self._reportar(options["indicador"], meta)
            return

        resultados = treinar_todas_doencas_registradas()
        for nome_doenca, meta in resultados.items():
            self._reportar(nome_doenca, meta)
