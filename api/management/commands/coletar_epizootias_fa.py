"""
Coleta epizootias de primatas não-humanos (PNH) para Febre Amarela — o sinal
One Health de alerta precoce (IA #5). Fonte oficial MS/DEMAS.

Grava em FonteOficialAgregado (fonte_id=ms_epizootias_fa,
indicador=febre_amarela_epizootias_pnh) por UF/mês. Opcionalmente treina o
modelo do Detector de Surto sobre a série.

Uso:
    python manage.py coletar_epizootias_fa                 # 2010..ano atual
    python manage.py coletar_epizootias_fa --desde 2000
    python manage.py coletar_epizootias_fa --anos 2024 2025
    python manage.py coletar_epizootias_fa --treinar       # treina a IA #5 depois

Roda como cron (ex.: junto do monitor epidemiológico). Sem dado real na API,
não grava nada — não simula.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from api import pipeline_one_health as oh


class Command(BaseCommand):
    help = "Coleta epizootias de PNH (Febre Amarela) do MS/DEMAS — sinal One Health da IA #5."

    def add_arguments(self, parser):
        parser.add_argument("--anos", type=int, nargs="+",
                            help="Anos específicos (ex.: --anos 2024 2025).")
        parser.add_argument("--desde", type=int,
                            help="Ano inicial; vai até o ano atual (default 2010).")
        parser.add_argument("--treinar", action="store_true",
                            help="Treina o modelo da IA #5 sobre a série após coletar.")

    def handle(self, *args, **opts):
        ano_atual = timezone.now().year
        if opts.get("anos"):
            anos = sorted(set(opts["anos"]))
        else:
            inicio = opts.get("desde") or 2010
            anos = list(range(inicio, ano_atual + 1))

        self.stdout.write(f"Coletando epizootias de PNH (Febre Amarela) — anos {anos[0]}..{anos[-1]}...")
        try:
            stats = oh.atualizar_epizootias_fa(anos)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.ERROR(f"Falha na coleta (nada gravado): {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"OK: {stats['epizootias_lidas']} epizootias lidas → "
            f"{stats['linhas_gravadas']} linhas (UF/mês) gravadas. "
            f"UFs com sinal: {', '.join(stats['ufs']) or '—'}"
        ))
        if stats["linhas_gravadas"] == 0:
            self.stdout.write(self.style.WARNING(
                "Nenhuma epizootia no período — sem sinal a gravar (esperado em anos calmos)."
            ))
            return

        if opts.get("treinar"):
            self.stdout.write("Treinando modelo da IA #5 sobre a série de epizootias...")
            try:
                from api.epidemiologia_ml import treinar_modelo_oficial
                res = treinar_modelo_oficial(oh.FONTE_ID, oh.INDICADOR)
                self.stdout.write(self.style.SUCCESS(f"Treino: {res}"))
            except Exception as exc:  # noqa: BLE001 — série esparsa pode recusar treino
                self.stdout.write(self.style.WARNING(
                    f"Treino não concluído (série provavelmente esparsa demais): {exc}. "
                    "O dado segue disponível como sinal no mapa de risco oficial."
                ))
