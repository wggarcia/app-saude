import random
import time
from collections import Counter
from datetime import timedelta
from itertools import cycle

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from api.epidemiologia import clear_panorama_cache
from api.models import Empresa, RegistroSintoma
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
        "Simula uma demonstracao nacional do app SoloCRT com foco ativo "
        "caindo ao longo de 30 dias e distribuicao por todo o Brasil."
    )

    def add_arguments(self, parser):
        parser.add_argument("--total", type=int, default=540)
        parser.add_argument("--dias-simulados", type=int, default=30)
        parser.add_argument("--dias-sem-novos", type=int, default=10)
        parser.add_argument(
            "--dias-zerar",
            type=int,
            default=41,
            help="Dia em que os focos somem totalmente da tela/mapa (decai de 10%% ate 0%%).",
        )
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
        if options["dias_simulados"] >= options["dias_zerar"]:
            raise CommandError("--dias-simulados precisa ser menor que --dias-zerar.")

        random.seed(options["seed"])
        # A duracao total cobre todo o arco ate o sumiço (dias_zerar), para que a
        # demonstracao inteira caiba no tempo pedido (ex.: 5 min ate o dia 41).
        step_seconds = max((options["duracao_minutos"] * 60.0) / max(options["dias_zerar"], 1), 0.1)
        empresa = self._empresa_owner_publica()

        if options["limpar_antes"]:
            self._limpar_demo(empresa, limpar_publico=options["limpar_publico"])

        if options["limpar_so"]:
            if options["limpar_publico"]:
                self._limpar_demo(empresa, limpar_publico=True)
            self.stdout.write(self.style.SUCCESS("Demo de reuniao removida."))
            return

        self.stdout.write(
            self.style.NOTICE(
                f"Iniciando demo nacional: {options['dias_sem_novos']} dias com entrada de casos, "
                f"queda ate ~10% no dia {options['dias_simulados']} e sumiço total no dia "
                f"{options['dias_zerar']} (os registros permanecem na trilha, mas saem da janela ativa)."
            )
        )

        day_weights = [i + 1 for i in range(options["dias_sem_novos"] + 1)]
        day_plan = Counter(random.choices(range(options["dias_sem_novos"] + 1), weights=day_weights, k=options["total"]))
        region_pool = list(REGIOES_BRASIL)
        random.shuffle(region_pool)
        region_iter = cycle(region_pool)
        created_total = 0

        for day in range(options["dias_zerar"] + 1):
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

            target_total = self._target_total(
                created_total,
                day,
                options["dias_sem_novos"],
                options["dias_simulados"],
                options["dias_zerar"],
            )
            atual_total = self._total_atual()
            if atual_total > target_total:
                self._reduzir_excesso(atual_total - target_total)

            clear_panorama_cache()
            indice_ativo = self._indice_atual()
            total_atual = self._total_atual()
            self.stdout.write(
                f"[dia {day:02d}/{options['dias_zerar']}] "
                f"novos={created_today} total={total_atual} ativo={indice_ativo:.2f}"
            )

            if day < options["dias_zerar"]:
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

        qs = RegistroSintoma.objects.using("owner")
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
        qs.bulk_create(objetos, batch_size=100)
        return len(objetos)

    def _envelhecer_demo(self):
        RegistroSintoma.objects.using("owner").filter(device_id__startswith=DEVICE_PREFIX).update(
            data_registro=F("data_registro") - timedelta(days=1)
        )

    def _reduzir_excesso(self, excesso):
        if excesso <= 0:
            return
        qs = RegistroSintoma.objects.using("owner")
        ids = list(
            qs.filter(device_id__startswith=DEVICE_PREFIX)
            .order_by("data_registro", "id")
            .values_list("id", flat=True)[:excesso]
        )
        if ids:
            qs.filter(id__in=ids).delete()

    def _target_total(self, criado_total, dia, dias_sem_novos, dias_simulados, dias_zerar):
        if criado_total <= 0:
            return 0
        if dia <= dias_sem_novos:
            return criado_total
        if dia <= dias_simulados:
            # Fase 1: do fim das entradas (ex.: dia 10) ate o dia 30 → cai de 100% a 10%.
            janela_queda = max(dias_simulados - dias_sem_novos, 1)
            progresso = min(max(dia - dias_sem_novos, 0), janela_queda)
            ratio = 1.0 - (0.9 * (progresso / janela_queda))
            return max(1, round(criado_total * ratio))
        # Fase 2: do dia 30 ao dia 41 → cai dos 10% restantes a 0% (sumiço total).
        janela_zero = max(dias_zerar - dias_simulados, 1)
        progresso = min(max(dia - dias_simulados, 0), janela_zero)
        ratio = 0.1 * (1.0 - (progresso / janela_zero))
        return max(0, round(criado_total * ratio))

    def _indice_atual(self):
        qs = RegistroSintoma.objects.using("owner").filter(device_id__startswith=DEVICE_PREFIX)
        from api.views import _indice_temporal_publico

        return _indice_temporal_publico(qs, timezone.now()) if qs.exists() else 0.0

    def _total_atual(self):
        return RegistroSintoma.objects.using("owner").filter(device_id__startswith=DEVICE_PREFIX).count()

    def _limpar_demo(self, empresa, limpar_publico=False):
        qs = RegistroSintoma.objects.using("owner").filter(empresa=empresa)
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

    def _empresa_owner_publica(self):
        empresa = _empresa_app_publico()
        if empresa is None:
            raise CommandError("Empresa pública não encontrada.")
        owner_qs = Empresa.objects.using("owner")
        owner_empresa = owner_qs.filter(pk=empresa.pk).first()
        if owner_empresa:
            return owner_empresa
        owner_empresa, _ = owner_qs.get_or_create(
            pk=empresa.pk,
            defaults={
                "nome": empresa.nome,
                "email": empresa.email,
                "senha": empresa.senha,
                "tipo_conta": empresa.tipo_conta,
                "pacote_codigo": empresa.pacote_codigo,
                "plano": empresa.plano,
                "ativo": empresa.ativo,
                "acesso_governo": empresa.acesso_governo,
                "max_dispositivos": empresa.max_dispositivos,
                "max_usuarios": empresa.max_usuarios,
                "sessao_ativa_chave": empresa.sessao_ativa_chave,
                "sessao_ativa_device_id": empresa.sessao_ativa_device_id,
                "sessao_ativa_em": empresa.sessao_ativa_em,
                "data_pagamento": empresa.data_pagamento,
                "data_expiracao": empresa.data_expiracao,
                "codigo_acesso_corporativo": empresa.codigo_acesso_corporativo,
            },
        )
        return owner_empresa
