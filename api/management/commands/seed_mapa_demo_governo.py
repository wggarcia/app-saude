"""
Popula o MAPA de demonstração do Governo com um panorama epidemiológico
nacional realista — SEM tocar nos dados reais.

Contexto (importante):
  O cockpit /governo/ (Sala de Situação) lê /api/epidemiologia, que agrega o
  tenant PÚBLICO global (populacao@solocrt.com). Sinais sintéticos/demo são
  EXCLUÍDOS desse panorama por design (antifraude, api/services/public_integrity).
  Por isso o mapa do demo fica vazio/esparso — e é correto que fique, porque a
  plataforma não exibe dado epidemiológico falso como real.

  A trilha de demonstração com mapa CHEIO usa um tenant ISOLADO
  (demo.simulacao@soluscrt.com) via build_demo_panorama_payload(), que retorna
  {"demo": true}. As contas de governo demo são roteadas para esse payload
  (ver _render_dashboard + dashboard_governo.html). Os sinais ficam nesse
  tenant e NUNCA entram no panorama real.

Uso:
    python manage.py seed_mapa_demo_governo            # ~520 sinais, últimos 10 dias
    python manage.py seed_mapa_demo_governo --total 800
    python manage.py seed_mapa_demo_governo --limpar   # remove os sinais demo

Idempotente: limpa os sinais demo anteriores (device_id 'natdemo-') antes de
recriar, então pode rodar quantas vezes quiser.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Empresa, RegistroSintoma
from api.epidemiologia import DEMO_APP_EMAIL, clear_panorama_cache

DEVICE_PREFIX = "natdemo-"  # fora de SYNTHETIC_DEVICE_PREFIXES: aparece no payload demo

# Capitais/regiões com foco epidemiológico plausível por perfil de doença.
# perfil: arbovirose (dengue/zika/chik) | respiratorio (gripe/covid)
REGIOES = [
    dict(cidade="São Paulo",      estado="São Paulo",         bairro="Zona Leste",    lat=-23.57, lon=-46.52, peso=0.15, perfil="arbovirose"),
    dict(cidade="Rio de Janeiro", estado="Rio de Janeiro",    bairro="Campo Grande",  lat=-22.90, lon=-43.56, peso=0.13, perfil="arbovirose"),
    dict(cidade="Belo Horizonte", estado="Minas Gerais",      bairro="Venda Nova",    lat=-19.81, lon=-43.95, peso=0.10, perfil="arbovirose"),
    dict(cidade="Recife",         estado="Pernambuco",        bairro="Boa Viagem",    lat=-8.12,  lon=-34.90, peso=0.11, perfil="arbovirose"),
    dict(cidade="Salvador",       estado="Bahia",             bairro="Cajazeiras",    lat=-12.90, lon=-38.42, peso=0.09, perfil="arbovirose"),
    dict(cidade="Fortaleza",      estado="Ceará",             bairro="Barra do Ceará",lat=-3.70,  lon=-38.59, peso=0.09, perfil="arbovirose"),
    dict(cidade="Manaus",         estado="Amazonas",          bairro="Cidade Nova",   lat=-3.04,  lon=-59.98, peso=0.07, perfil="arbovirose"),
    dict(cidade="Goiânia",        estado="Goiás",             bairro="Campinas",      lat=-16.67, lon=-49.28, peso=0.06, perfil="arbovirose"),
    dict(cidade="Curitiba",       estado="Paraná",            bairro="CIC",           lat=-25.49, lon=-49.34, peso=0.06, perfil="respiratorio"),
    dict(cidade="Porto Alegre",   estado="Rio Grande do Sul", bairro="Restinga",      lat=-30.15, lon=-51.16, peso=0.05, perfil="respiratorio"),
    dict(cidade="Brasília",       estado="Distrito Federal",  bairro="Ceilândia",     lat=-15.82, lon=-48.11, peso=0.05, perfil="respiratorio"),
    dict(cidade="Belém",          estado="Pará",              bairro="Icoaraci",      lat=-1.30,  lon=-48.48, peso=0.04, perfil="arbovirose"),
]


def _sintomas(perfil):
    if perfil == "arbovirose":
        return dict(
            doenca="dengue",
            febre=random.random() < 0.85,
            dor_corpo=random.random() < 0.88,
            dor_cabeca=random.random() < 0.72,
            tosse=random.random() < 0.08,
            falta_ar=random.random() < 0.03,
        )
    return dict(
        doenca="influenza",
        febre=random.random() < 0.55,
        tosse=random.random() < 0.86,
        dor_corpo=random.random() < 0.35,
        dor_cabeca=random.random() < 0.30,
        falta_ar=random.random() < 0.15,
    )


class Command(BaseCommand):
    help = "Popula o mapa de demonstração do Governo (tenant isolado, nunca afeta dados reais)."

    def add_arguments(self, parser):
        parser.add_argument("--total", type=int, default=520)
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument("--limpar", action="store_true", help="Só remove os sinais demo e sai.")

    def handle(self, *args, **options):
        demo = Empresa.objects.filter(email=DEMO_APP_EMAIL).first()
        if demo is None:
            self.stderr.write(self.style.ERROR(
                f"Tenant de simulação '{DEMO_APP_EMAIL}' não existe. Abortado."))
            return

        # Limpeza idempotente (sempre remove os sinais demo anteriores).
        removidos, _ = RegistroSintoma.objects.filter(
            empresa=demo, device_id__startswith=DEVICE_PREFIX).delete()

        if options["limpar"]:
            clear_panorama_cache()
            self.stdout.write(self.style.SUCCESS(f"Sinais demo removidos: {removidos}."))
            return

        random.seed(options["seed"])
        total = options["total"]
        agora = timezone.now()
        regioes = random.choices(REGIOES, weights=[r["peso"] for r in REGIOES], k=total)

        criados = 0
        for i, reg in enumerate(regioes):
            s = _sintomas(reg["perfil"])
            try:
                obj = RegistroSintoma.objects.create(
                    empresa=demo,
                    device_id=f"{DEVICE_PREFIX}{i}",
                    latitude=reg["lat"] + random.uniform(-0.05, 0.05),
                    longitude=reg["lon"] + random.uniform(-0.05, 0.05),
                    cidade=reg["cidade"], estado=reg["estado"], bairro=reg["bairro"],
                    pais="Brasil", origem_dado="cidadao",
                    **s,
                )
                # backdate: mais denso nos últimos dias (curva de surto)
                dias = min(9, int(abs(random.gauss(0, 3))))
                RegistroSintoma.objects.filter(id=obj.id).update(
                    data_registro=agora - timedelta(days=dias, hours=random.randint(0, 23)))
                criados += 1
            except Exception:
                pass

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Mapa demo populado: {criados} sinais em {len(REGIOES)} capitais "
            f"(tenant isolado {DEMO_APP_EMAIL}). Removidos antes: {removidos}."))
