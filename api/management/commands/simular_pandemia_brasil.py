"""
Simulação de pandemia em 3 fases — SolusCRT Demo

Uso no Render Shell:
    python manage.py simular_pandemia_brasil            # 5000 casos, 10 min
    python manage.py simular_pandemia_brasil --casos 2000 --duracao 5
    python manage.py simular_pandemia_brasil --limpar   # remove registros de simulação

FASES:
  1. SURTO    — casos crescendo (0-3 dias atrás) → mapa aceso, pandemia
  2. DECLÍNIO — mesmos registros movidos para 12-15 dias → mapa diminuindo
  3. SUMINDO  — registros movidos para 32-38 dias → fora da janela de 30d → desaparecem
"""

import json
import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.test import Client
from django.utils import timezone

from api.models import RegistroSintoma

MARKER_PREFIX = "pandemia-sim-"

REGIOES = [
    # (cidade, estado, bairro, lat, lon, peso, perfil)
    ("São Paulo",        "São Paulo",            "Pinheiros",        -23.5614, -46.7016, 0.16, "arbovirose"),
    ("Rio de Janeiro",   "Rio de Janeiro",        "Centro",           -22.9068, -43.1729, 0.13, "arbovirose"),
    ("Recife",           "Pernambuco",            "Boa Vista",        -8.0476,  -34.8770, 0.10, "arbovirose"),
    ("Salvador",         "Bahia",                 "Centro",           -12.9777, -38.5016, 0.09, "arbovirose"),
    ("Fortaleza",        "Ceara",                 "Centro",           -3.7319,  -38.5267, 0.08, "arbovirose"),
    ("Belo Horizonte",   "Minas Gerais",          "Centro",           -19.9167, -43.9345, 0.08, "misto"),
    ("Manaus",           "Amazonas",              "Centro",           -3.1190,  -60.0217, 0.07, "arbovirose"),
    ("Curitiba",         "Parana",                "Centro",           -25.4284, -49.2733, 0.06, "misto"),
    ("Porto Alegre",     "Rio Grande do Sul",     "Centro Historico", -30.0346, -51.2177, 0.05, "respiratorio"),
    ("Belém",            "Para",                  "Centro",           -1.4558,  -48.5039, 0.05, "arbovirose"),
    ("Goiânia",          "Goias",                 "Centro",           -16.6869, -49.2648, 0.04, "misto"),
    ("Maceió",           "Alagoas",               "Centro",           -9.6658,  -35.7353, 0.03, "arbovirose"),
    ("Florianópolis",    "Santa Catarina",        "Centro",           -27.5945, -48.5477, 0.03, "misto"),
    ("Brasília",         "Distrito Federal",      "Asa Sul",          -15.7801, -47.9292, 0.03, "misto"),
    ("Campo Grande",     "Mato Grosso do Sul",    "Centro",           -20.4428, -54.6460, 0.02, "misto"),
    ("Porto Velho",      "Rondonia",              "Centro",           -8.7619,  -63.9039, 0.02, "arbovirose"),
    ("Natal",            "Rio Grande do Norte",   "Centro",           -5.7945,  -35.2110, 0.02, "arbovirose"),
    ("Teresina",         "Piaui",                 "Centro",           -5.0892,  -42.8019, 0.02, "misto"),
    ("João Pessoa",      "Paraiba",               "Centro",           -7.1153,  -34.8641, 0.01, "arbovirose"),
]


def _sintomas(perfil):
    if perfil == "arbovirose":
        return {
            "febre":        random.random() < 0.88,
            "dor_corpo":    random.random() < 0.82,
            "dor_cabeca":   random.random() < 0.78,
            "dor_articular": random.random() < 0.72,
            "exantema":     random.random() < 0.55,
            "vomito_nausea": random.random() < 0.42,
            "cansaco":      random.random() < 0.65,
            "calafrios":    random.random() < 0.38,
        }
    if perfil == "respiratorio":
        return {
            "febre":     random.random() < 0.65,
            "tosse":     random.random() < 0.88,
            "coriza":    random.random() < 0.72,
            "dor_garganta": random.random() < 0.58,
            "cansaco":   random.random() < 0.55,
            "falta_ar":  random.random() < 0.22,
        }
    return {
        "febre":     random.random() < 0.62,
        "dor_corpo": random.random() < 0.52,
        "tosse":     random.random() < 0.44,
        "cansaco":   random.random() < 0.58,
        "exantema":  random.random() < 0.30,
    }


def _limpar(stdout, style):
    from django.db import connection
    from api.models import Empresa
    from api.epidemiologia import clear_panorama_cache

    apagados = 0
    for emp in Empresa.objects.all():
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(emp.id)])
        n, _ = RegistroSintoma.objects.filter(
            empresa=emp,
            device_id__startswith=MARKER_PREFIX,
        ).delete()
        apagados += n

    clear_panorama_cache()
    stdout.write(style.SUCCESS(f"  {apagados} registros de simulação removidos. Cache limpo."))


class Command(BaseCommand):
    help = "Simulação de pandemia em 3 fases para demo do mapa epidemiológico."

    def add_arguments(self, parser):
        parser.add_argument("--casos",    type=int, default=5000, help="Total de casos (padrão 5000)")
        parser.add_argument("--duracao",  type=int, default=10,   help="Duração total em minutos (padrão 10)")
        parser.add_argument("--seed",     type=int, default=7,    help="Seed aleatória")
        parser.add_argument("--limpar",   action="store_true",    help="Remove registros de simulação e sai")

    def handle(self, *args, **options):
        if options["limpar"]:
            self.stdout.write("Removendo registros de simulação...")
            _limpar(self.stdout, self.style)
            return

        random.seed(options["seed"])
        total     = options["casos"]
        duracao   = options["duracao"]  # minutos

        # Divide o tempo: 40% crescimento, 35% declínio, 25% desaparecimento
        t_fase1 = int(duracao * 0.40 * 60)  # segundos
        t_fase2 = int(duracao * 0.35 * 60)
        t_fase3 = int(duracao * 0.25 * 60)

        from api.epidemiologia import clear_panorama_cache

        self.stdout.write("\n" + "═" * 60)
        self.stdout.write("  SIMULAÇÃO DE PANDEMIA — SolusCRT")
        self.stdout.write(f"  {total} casos · {duracao} minutos · 3 fases")
        self.stdout.write("═" * 60)

        # ── FASE 1: SURTO ──────────────────────────────────────────
        self.stdout.write(self.style.WARNING("\n▶ FASE 1: SURTO — inserindo casos em todo o Brasil..."))
        agora = timezone.now()
        client = Client(HTTP_HOST="127.0.0.1:8000")

        cidades   = [r[0] for r in REGIOES]
        estados   = [r[1] for r in REGIOES]
        bairros   = [r[2] for r in REGIOES]
        lats      = [r[3] for r in REGIOES]
        lons      = [r[4] for r in REGIOES]
        pesos     = [r[5] for r in REGIOES]
        perfis    = [r[6] for r in REGIOES]

        indices = random.choices(range(len(REGIOES)), weights=pesos, k=total)

        enviados = 0
        device_ids_inseridos = []

        for i, idx in enumerate(indices):
            device_id = f"{MARKER_PREFIX}{i:05d}"
            payload = {
                **_sintomas(perfis[idx]),
                "latitude":       lats[idx] + random.uniform(-0.06, 0.06),
                "longitude":      lons[idx] + random.uniform(-0.06, 0.06),
                "location_source": "current",
                "bairro":  bairros[idx],
                "cidade":  cidades[idx],
                "estado":  estados[idx],
                "pais":    "Brasil",
            }
            resp = client.post(
                "/api/public/registrar",
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_DEVICE_ID=device_id,
                HTTP_X_FORWARDED_FOR=f"10.{i // 65000}.{(i // 255) % 255}.{i % 255}",
                HTTP_X_SOLUS_SIMULATION="true",
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not data.get("registro_id"):
                continue

            # Backdate: 0 a 4 dias atrás — pico da pandemia
            dias = random.choices([0, 1, 2, 3, 4], weights=[30, 25, 20, 15, 10])[0]
            RegistroSintoma.objects.filter(id_anonimo=data["registro_id"]).update(
                data_registro=agora - timedelta(days=dias, hours=random.randint(0, 20))
            )
            device_ids_inseridos.append(device_id)
            enviados += 1

            if enviados % 500 == 0:
                self.stdout.write(f"  {enviados}/{total} casos inseridos...")

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {enviados} casos inseridos. Mapa atualizado — PANDEMIA ATIVA."
        ))
        self.stdout.write(f"  ⏳ Aguardando {t_fase1 // 60}min {t_fase1 % 60}s para a próxima fase...")

        # Abre o mapa no servidor agora
        for restante in range(t_fase1, 0, -10):
            time.sleep(min(10, restante))
            if restante % 60 == 0:
                self.stdout.write(f"     {restante // 60}min restantes...")

        # ── FASE 2: DECLÍNIO ────────────────────────────────────────
        self.stdout.write(self.style.WARNING("\n▶ FASE 2: DECLÍNIO — 10+ dias sem novos casos..."))
        agora2 = timezone.now()

        from api.models import Empresa
        from django.db import connection

        for emp in Empresa.objects.all():
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(emp.id)])
            # Move registros para 12-16 dias atrás — zona de decaimento
            registros_qs = RegistroSintoma.objects.filter(
                empresa=emp, device_id__startswith=MARKER_PREFIX
            )
            count = registros_qs.count()
            if not count:
                continue
            for reg in registros_qs:
                dias = random.randint(12, 16)
                reg.data_registro = agora2 - timedelta(days=dias, hours=random.randint(0, 20))
            RegistroSintoma.objects.bulk_update(registros_qs, ["data_registro"])

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            "  ✓ Registros movidos para 12-16 dias atrás. Mapa em DECLÍNIO."
        ))
        self.stdout.write(f"  ⏳ Aguardando {t_fase2 // 60}min {t_fase2 % 60}s para a próxima fase...")

        for restante in range(t_fase2, 0, -10):
            time.sleep(min(10, restante))
            if restante % 60 == 0:
                self.stdout.write(f"     {restante // 60}min restantes...")

        # ── FASE 3: DESAPARECIMENTO ─────────────────────────────────
        self.stdout.write(self.style.WARNING("\n▶ FASE 3: DESAPARECIMENTO — 30+ dias, casos sumindo do mapa..."))
        agora3 = timezone.now()

        for emp in Empresa.objects.all():
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(emp.id)])
            registros_qs = RegistroSintoma.objects.filter(
                empresa=emp, device_id__startswith=MARKER_PREFIX
            )
            count = registros_qs.count()
            if not count:
                continue
            # Move para 32-38 dias atrás — fora da janela de 30 dias → peso 0 → sumem
            for reg in registros_qs:
                dias = random.randint(32, 38)
                reg.data_registro = agora3 - timedelta(days=dias, hours=random.randint(0, 20))
            RegistroSintoma.objects.bulk_update(registros_qs, ["data_registro"])

        clear_panorama_cache()
        self.stdout.write(self.style.SUCCESS(
            "  ✓ Registros movidos para 32-38 dias atrás. FORA DA JANELA DE 30 DIAS."
        ))
        self.stdout.write(self.style.SUCCESS(
            "  ✓ Mapa limpando — todos os focos desaparecem em até 5 min (TTL do cache)."
        ))
        self.stdout.write(f"  ⏳ Aguardando {t_fase3 // 60}min {t_fase3 % 60}s e limpando...")

        for restante in range(t_fase3, 0, -10):
            time.sleep(min(10, restante))
            if restante % 60 == 0:
                self.stdout.write(f"     {restante // 60}min restantes...")

        # ── LIMPEZA FINAL ────────────────────────────────────────────
        self.stdout.write("\n🧹 Removendo registros de simulação do banco...")
        _limpar(self.stdout, self.style)

        self.stdout.write("\n" + "═" * 60)
        self.stdout.write(self.style.SUCCESS(
            "  SIMULAÇÃO CONCLUÍDA — banco limpo, cache zerado."
        ))
        self.stdout.write("═" * 60 + "\n")
