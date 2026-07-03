"""
Simulação de pandemia em 3 fases — SolusCRT Demo

Uso no Render Shell:
    python manage.py simular_pandemia_brasil            # 5000 casos, 10 min
    python manage.py simular_pandemia_brasil --casos 2000 --duracao 5
    python manage.py simular_pandemia_brasil --limpar   # remove registros de simulação

FASES:
  1. SURTO    — casos 0-3 dias atrás → mapa aceso, pandemia ativa
  2. DECLÍNIO — registros movidos para 14 dias → mapa dimming (decaimento)
  3. SUMINDO  — registros movidos para 35 dias → fora da janela 30d → somem
"""

import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from api.epidemiologia import PUBLIC_APP_EMAIL, clear_panorama_cache
from api.models import Empresa, RegistroSintoma

DEVICE_PREFIX = "pandemia-br-"   # NÃO está em SYNTHETIC_DEVICE_PREFIXES

REGIOES = [
    # (cidade, estado, bairro, lat, lon, peso, perfil)
    ("São Paulo",       "São Paulo",           "Pinheiros",       -23.5614, -46.7016, 0.16, "arbovirose"),
    ("Rio de Janeiro",  "Rio de Janeiro",       "Centro",          -22.9068, -43.1729, 0.13, "arbovirose"),
    ("Recife",          "Pernambuco",           "Boa Vista",       -8.0476,  -34.8770, 0.10, "arbovirose"),
    ("Salvador",        "Bahia",                "Centro",          -12.9777, -38.5016, 0.09, "arbovirose"),
    ("Fortaleza",       "Ceara",                "Centro",          -3.7319,  -38.5267, 0.08, "arbovirose"),
    ("Belo Horizonte",  "Minas Gerais",         "Centro",          -19.9167, -43.9345, 0.08, "misto"),
    ("Manaus",          "Amazonas",             "Centro",          -3.1190,  -60.0217, 0.07, "arbovirose"),
    ("Curitiba",        "Parana",               "Centro",          -25.4284, -49.2733, 0.06, "misto"),
    ("Porto Alegre",    "Rio Grande do Sul",    "Centro Historico",-30.0346, -51.2177, 0.05, "respiratorio"),
    ("Belém",           "Para",                 "Centro",          -1.4558,  -48.5039, 0.05, "arbovirose"),
    ("Goiânia",         "Goias",                "Centro",          -16.6869, -49.2648, 0.04, "misto"),
    ("Brasília",        "Distrito Federal",     "Asa Sul",         -15.7801, -47.9292, 0.03, "misto"),
    ("Maceió",          "Alagoas",              "Centro",          -9.6658,  -35.7353, 0.03, "arbovirose"),
    ("Florianópolis",   "Santa Catarina",       "Centro",          -27.5945, -48.5477, 0.03, "respiratorio"),
    ("Natal",           "Rio Grande do Norte",  "Centro",          -5.7945,  -35.2110, 0.02, "arbovirose"),
    ("Teresina",        "Piaui",                "Centro",          -5.0892,  -42.8019, 0.02, "misto"),
    ("João Pessoa",     "Paraiba",              "Centro",          -7.1153,  -34.8641, 0.02, "arbovirose"),
    ("Campo Grande",    "Mato Grosso do Sul",   "Centro",          -20.4428, -54.6460, 0.02, "misto"),
    ("Porto Velho",     "Rondonia",             "Centro",          -8.7619,  -63.9039, 0.01, "arbovirose"),
    ("Belém",           "Para",                 "Guamá",           -1.4900,  -48.4900, 0.01, "arbovirose"),
]


def _sintomas(perfil):
    if perfil == "arbovirose":
        return {
            "febre":         True,
            "dor_corpo":     True,
            "dor_cabeca":    True,
            "dor_articular": random.random() < 0.70,
            "exantema":      random.random() < 0.52,
            "vomito_nausea": random.random() < 0.42,
            "cansaco":       True,
            "calafrios":     random.random() < 0.38,
        }
    if perfil == "respiratorio":
        return {
            "febre":        random.random() < 0.68,
            "tosse":        True,
            "coriza":       True,
            "dor_garganta": random.random() < 0.58,
            "cansaco":      True,
            "falta_ar":     random.random() < 0.20,
        }
    # misto
    return {
        "febre":     True,
        "dor_corpo": random.random() < 0.55,
        "tosse":     random.random() < 0.45,
        "exantema":  random.random() < 0.28,
        "cansaco":   True,
    }


def _set_rls(empresa_id):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(empresa_id)])


def _limpar(stdout, style):
    empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
    if empresa:
        _set_rls(empresa.id)
        n, _ = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id__startswith=DEVICE_PREFIX,
        ).delete()
        stdout.write(style.SUCCESS(f"  {n} registros removidos."))
    clear_panorama_cache()
    stdout.write(style.SUCCESS("  Cache limpo."))


class Command(BaseCommand):
    help = "Simulação de pandemia em 3 fases para demo do mapa epidemiológico."

    def add_arguments(self, parser):
        parser.add_argument("--casos",   type=int, default=5000)
        parser.add_argument("--duracao", type=int, default=10, help="Duração total em minutos")
        parser.add_argument("--seed",    type=int, default=7)
        parser.add_argument("--limpar",  action="store_true", help="Remove registros e sai")

    def handle(self, *args, **options):
        if options["limpar"]:
            self.stdout.write("Removendo registros de simulação...")
            _limpar(self.stdout, self.style)
            return

        random.seed(options["seed"])
        total   = options["casos"]
        duracao = options["duracao"]

        t_fase1 = int(duracao * 0.40 * 60)
        t_fase2 = int(duracao * 0.35 * 60)
        t_fase3 = int(duracao * 0.25 * 60)

        empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
        if not empresa:
            self.stdout.write(self.style.ERROR(
                f"Empresa pública não encontrada (email={PUBLIC_APP_EMAIL}). Abortando."
            ))
            return

        _set_rls(empresa.id)

        self.stdout.write("\n" + "═" * 58)
        self.stdout.write("  SIMULAÇÃO DE PANDEMIA — SolusCRT")
        self.stdout.write(f"  {total} casos · {duracao} minutos · 3 fases")
        self.stdout.write(f"  Empresa: {empresa.nome} (id={empresa.id})")
        self.stdout.write("═" * 58)

        # ── FASE 1: SURTO ─────────────────────────────────────────
        self.stdout.write(self.style.WARNING(
            f"\n▶ FASE 1: SURTO — inserindo {total} casos direto no banco..."
        ))

        pesos   = [r[5] for r in REGIOES]
        indices = random.choices(range(len(REGIOES)), weights=pesos, k=total)
        agora   = timezone.now()

        records = []
        for i, idx in enumerate(indices):
            r = REGIOES[idx]
            records.append(RegistroSintoma(
                empresa=empresa,
                device_id=f"{DEVICE_PREFIX}{i:05d}",
                latitude=r[3]  + random.uniform(-0.08, 0.08),
                longitude=r[4] + random.uniform(-0.08, 0.08),
                pais="Brasil",
                estado=r[1],
                cidade=r[0],
                bairro=r[2],
                origem_dado=RegistroSintoma.ORIGEM_CIDADAO,
                **_sintomas(r[6]),
            ))

        BATCH = 500
        criados = 0
        for j in range(0, len(records), BATCH):
            RegistroSintoma.objects.bulk_create(records[j:j + BATCH])
            criados += len(records[j:j + BATCH])
            self.stdout.write(f"  {criados}/{total} inseridos...")

        # Backdate: 0-3 dias atrás — peso máximo no mapa
        RegistroSintoma.objects.filter(
            empresa=empresa, device_id__startswith=DEVICE_PREFIX
        ).update(data_registro=agora - timedelta(days=2))

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {criados} casos no banco. Cache limpo — PANDEMIA ATIVA no mapa!"
        ))
        self.stdout.write(f"  ⏳ Próxima fase em {t_fase1 // 60}min {t_fase1 % 60}s...")

        self._esperar(t_fase1)

        # ── FASE 2: DECLÍNIO ──────────────────────────────────────
        self.stdout.write(self.style.WARNING(
            "\n▶ FASE 2: DECLÍNIO — 10+ dias sem novos casos..."
        ))
        _set_rls(empresa.id)
        RegistroSintoma.objects.filter(
            empresa=empresa, device_id__startswith=DEVICE_PREFIX
        ).update(data_registro=agora - timedelta(days=14))

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            "  ✓ Registros em 14 dias atrás — zona de decaimento. Mapa DIMMING."
        ))
        self.stdout.write(f"  ⏳ Próxima fase em {t_fase2 // 60}min {t_fase2 % 60}s...")

        self._esperar(t_fase2)

        # ── FASE 3: DESAPARECIMENTO ────────────────────────────────
        self.stdout.write(self.style.WARNING(
            "\n▶ FASE 3: DESAPARECIMENTO — 35 dias, fora da janela de 30 dias..."
        ))
        _set_rls(empresa.id)
        RegistroSintoma.objects.filter(
            empresa=empresa, device_id__startswith=DEVICE_PREFIX
        ).update(data_registro=agora - timedelta(days=35))

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            "  ✓ Registros em 35 dias atrás — peso 0 — SUMINDO DO MAPA."
        ))
        self.stdout.write(f"  ⏳ Aguardando {t_fase3 // 60}min {t_fase3 % 60}s antes de limpar...")

        self._esperar(t_fase3)

        # ── LIMPEZA ────────────────────────────────────────────────
        self.stdout.write("\n🧹 Removendo registros de simulação...")
        _limpar(self.stdout, self.style)

        self.stdout.write("\n" + "═" * 58)
        self.stdout.write(self.style.SUCCESS(
            "  SIMULAÇÃO CONCLUÍDA — banco limpo, cache zerado."
        ))
        self.stdout.write("═" * 58 + "\n")

    def _esperar(self, segundos):
        for restante in range(segundos, 0, -15):
            time.sleep(min(15, restante))
            if restante % 60 == 0 and restante > 0:
                self.stdout.write(f"     {restante // 60}min restantes...")
