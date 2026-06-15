import random
import time
from collections import Counter
from datetime import timedelta
from itertools import cycle

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from api.epidemiologia import clear_panorama_cache
from api.models import RegistroSintoma
from api.views import _empresa_app_publico

from .stress_soluscrt_brasil import REGIOES_BRASIL


DEVICE_PREFIX = "reuniao-br-"
SOURCE_MARKER = "reuniao-soluscrt-brasil"

CORES_PERFIL = {
    "respiratorio": "Respiratorio",
    "arbovirose": "Arbovirose",
    "misto": "Monitoramento",
}


def _sintomas_por_perfil(perfil):
    if perfil == "respiratorio":
        return {
            "febre": random.random() < 0.62,
            "tosse": random.random() < 0.88,
            "dor_corpo": random.random() < 0.35,
            "cansaco": random.random() < 0.56,
            "falta_ar": random.random() < 0.14,
            "dor_garganta": random.random() < 0.72,
            "coriza": random.random() < 0.64,
        }
    if perfil == "arbovirose":
        return {
            "febre": random.random() < 0.84,
            "tosse": random.random() < 0.08,
            "dor_corpo": random.random() < 0.90,
            "cansaco": random.random() < 0.66,
            "falta_ar": random.random() < 0.03,
            "dor_articular": random.random() < 0.82,
            "exantema": random.random() < 0.44,
        }
    return {
        "febre": random.random() < 0.56,
        "tosse": random.random() < 0.44,
        "dor_corpo": random.random() < 0.48,
        "cansaco": random.random() < 0.52,
        "falta_ar": random.random() < 0.08,
        "dor_cabeca": random.random() < 0.42,
        "calafrios": random.random() < 0.22,
    }


class Command(BaseCommand):
    help = (
        "Simula uma demonstracao nacional do app SolusCRT com foco ativo "
        "caindo ao longo de 30 dias e distribuicao por todo o Brasil."
    )

    def add_arguments(self, parser):
        parser.add_argument("--total", type=int, default=540)
        parser.add_argument("--dias-simulados", type=int, default=30)
        parser.add_argument("--dias-sem-novos", type=int, default=10)
        parser.add_argument("--duracao-minutos", type=float, default=5.0)
        parser.add_argument("--seed", type=int, default=20260615)
        parser.add_argument("--limpar-antes", action="store_true")
        parser.add_argument("--limpar-depois", action="store_true")
        parser.add_argument("--limpar-so", action="store_true")
        parser.add_argument(
            "--limpar-publico",
            action="store_true",
            help="Remove todos os registros da empresa publica antes/depois da demo.",
        )

    def handle(self, *args, **options):
        if options["dias_sem_novos"] >= options["dias_simulados"]:
            raise CommandError("--dias-sem-novos precisa ser menor que --dias-simulados.")

        random.seed(options["seed"])
        step_seconds = max((options["duracao_minutos"] * 60.0) / max(options["dias_simulados"], 1), 0.1)
        empresa = _empresa_app_publico()
        self._set_rls(empresa.id)

        if options["limpar_antes"]:
            self._limpar_demo(empresa, limpar_publico=options["limpar_publico"])

        if options["limpar_so"]:
            if options["limpar_publico"]:
                self._limpar_demo(empresa, limpar_publico=True)
            self.stdout.write(self.style.SUCCESS("Demo de reuniao removida."))
            return

        self.stdout.write(
            self.style.NOTICE(
                "Iniciando demo nacional: 10 dias com entrada de casos, depois decaimento "
                f"ate o dia {options['dias_simulados']}."
            )
        )

        day_weights = [i + 1 for i in range(options["dias_sem_novos"] + 1)]
        day_plan = Counter(random.choices(range(options["dias_sem_novos"] + 1), weights=day_weights, k=options["total"]))
        region_pool = list(REGIOES_BRASIL)
        random.shuffle(region_pool)
        region_iter = cycle(region_pool)
        created_total = 0

        for day in range(options["dias_simulados"] + 1):
            if day > 0:
                self._envelhecer_demo()

            created_today = 0
            if day <= options["dias_sem_novos"]:
                created_today = self._criar_lote(
                    empresa=empresa,
                    quantidade=day_plan.get(day, 0),
                    current_day=day,
                    region_iter=region_iter,
                )
                created_total += created_today

            target_total = self._target_total(created_total, day, options["dias_sem_novos"], options["dias_simulados"])
            atual_total = self._total_atual()
            if atual_total > target_total:
                self._reduzir_excesso(atual_total - target_total)

            clear_panorama_cache()
            indice_ativo = self._indice_atual()
            total_atual = self._total_atual()
            self.stdout.write(
                f"[dia {day:02d}/{options['dias_simulados']}] "
                f"novos={created_today} total={total_atual} ativo={indice_ativo:.2f}"
            )

            if day < options["dias_simulados"]:
                time.sleep(step_seconds)

        if options["limpar_depois"]:
            self._limpar_demo(empresa, limpar_publico=options["limpar_publico"])

        self.stdout.write(
            self.style.SUCCESS(
                "Demo nacional concluida. "
                f"Casos criados={created_total} | casos restantes={self._total_atual()}"
            )
        )

    def _criar_lote(self, empresa, quantidade, current_day, region_iter):
        if quantidade <= 0:
            return 0

        self._set_rls(empresa.id)
        agora = timezone.now()
        objetos = []
        for index in range(quantidade):
            _, estado, cidade, bairro, lat, lon, perfil = next(region_iter)
            sintomas = _sintomas_por_perfil(perfil)
            objetos.append(
                RegistroSintoma(
                    empresa=empresa,
                    **sintomas,
                    latitude=lat + random.uniform(-0.02, 0.02),
                    longitude=lon + random.uniform(-0.02, 0.02),
                    pais="Brasil",
                    estado=estado,
                    cidade=cidade,
                    bairro=bairro,
                    grupo=CORES_PERFIL.get(perfil, "Monitoramento"),
                    classificacao="simulacao_reuniao",
                    origem_dado=RegistroSintoma.ORIGEM_CIDADAO,
                    suspeito=False,
                    device_id=f"{DEVICE_PREFIX}{current_day:02d}-{index:04d}-{random.randint(1000, 9999)}",
                    fonte_referencia=SOURCE_MARKER,
                    data_registro=agora,
                )
            )
        RegistroSintoma.objects.bulk_create(objetos, batch_size=100)
        return len(objetos)

    def _envelhecer_demo(self):
        self._set_rls(_empresa_app_publico().id)
        RegistroSintoma.objects.filter(device_id__startswith=DEVICE_PREFIX).update(
            data_registro=F("data_registro") - timedelta(days=1)
        )

    def _reduzir_excesso(self, excesso):
        if excesso <= 0:
            return
        self._set_rls(_empresa_app_publico().id)
        ids = list(
            RegistroSintoma.objects.filter(device_id__startswith=DEVICE_PREFIX)
            .order_by("data_registro", "id")
            .values_list("id", flat=True)[:excesso]
        )
        if ids:
            RegistroSintoma.objects.filter(id__in=ids).delete()

    def _target_total(self, criado_total, dia, dias_sem_novos, dias_simulados):
        if criado_total <= 0:
            return 0
        if dia <= dias_sem_novos:
            return criado_total
        janela_queda = max(dias_simulados - dias_sem_novos, 1)
        progresso = min(max(dia - dias_sem_novos, 0), janela_queda)
        ratio = 1.0 - (0.9 * (progresso / janela_queda))
        return max(1, round(criado_total * ratio))

    def _indice_atual(self):
        self._set_rls(_empresa_app_publico().id)
        qs = RegistroSintoma.objects.filter(device_id__startswith=DEVICE_PREFIX)
        from api.views import _indice_temporal_publico

        return _indice_temporal_publico(qs, timezone.now()) if qs.exists() else 0.0

    def _total_atual(self):
        self._set_rls(_empresa_app_publico().id)
        return RegistroSintoma.objects.filter(device_id__startswith=DEVICE_PREFIX).count()

    def _limpar_demo(self, empresa, limpar_publico=False):
        self._set_rls(empresa.id)
        qs = RegistroSintoma.objects.filter(empresa=empresa)
        if not limpar_publico:
            qs = qs.filter(
                Q(device_id__startswith=DEVICE_PREFIX) | Q(fonte_referencia__icontains=SOURCE_MARKER)
            )
        removidos = qs.delete()[0]
        clear_panorama_cache()
        if limpar_publico:
            self.stdout.write(self.style.WARNING(f"Demo nacional removida: {removidos} registros publicos."))
        else:
            self.stdout.write(self.style.WARNING(f"Demo nacional removida: {removidos} registros."))

    def _set_rls(self, empresa_id):
        from django.db import connection

        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(empresa_id)])
