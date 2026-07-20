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
        parser.add_argument(
            "--auto",
            action="store_true",
            help=(
                "Modo automático/desassistido (cron): só PROMOVE um modelo novo se ele "
                "atingir o F1 mínimo e não regredir frente ao atual. Sem --auto, salva o "
                "resultado do treino normalmente (supervisionado)."
            ),
        )

    def _reportar(self, nome_doenca, meta):
        if not meta.get("treinado"):
            motivo = meta.get("motivo")
            if motivo == "qualidade_insuficiente":
                detalhe = (f"F1 {meta.get('cv_f1_media', 0):.3f} < mínimo {meta.get('minimo_f1')}. "
                           "Modelo atual MANTIDO (não promovido).")
            elif motivo == "regressao_vs_modelo_atual":
                detalhe = (f"F1 novo {meta.get('cv_f1_media', 0):.3f} < atual {meta.get('cv_f1_atual', 0):.3f}. "
                           "Modelo atual MANTIDO (evitou regressão).")
            else:
                detalhe = f"{meta.get('n_amostras', 0)}/{meta.get('minimo_necessario')} amostras reais."
            self.stdout.write(self.style.WARNING(f"[{nome_doenca}] Nao treinado: {motivo} — {detalhe}"))
            return
        self.stdout.write(self.style.SUCCESS(
            f"[{nome_doenca}] Modelo treinado com {meta['n_amostras']} amostras oficiais reais "
            f"({meta['fonte_id']}/{meta['indicador']}) cobrindo estados: {', '.join(meta['estados'])}."
        ))
        self.stdout.write(f"[{nome_doenca}] F1 (cross-val): {meta['cv_f1_media']:.3f} +/- {meta['cv_f1_std']:.3f}")

    def handle(self, *args, **options):
        auto = options.get("auto", False)
        if auto:
            self.stdout.write("Modo automático: só promove modelo que passar na validação (F1 mínimo + sem regressão).")
        if options.get("fonte_id") and options.get("indicador"):
            meta = treinar_modelo_oficial(
                fonte_id=options["fonte_id"], indicador=options["indicador"], validar_promocao=auto
            )
            self._reportar(options["indicador"], meta)
            return

        resultados = treinar_todas_doencas_registradas(validar_promocao=auto)
        for nome_doenca, meta in resultados.items():
            self._reportar(nome_doenca, meta)
