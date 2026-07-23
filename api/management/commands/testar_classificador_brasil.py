"""
Teste sistêmico do classificador de doenças — SoloCRT

USO NO RENDER SHELL:
    python manage.py testar_classificador_brasil               # relatório puro (sem DB)
    python manage.py testar_classificador_brasil --mapa        # insere casos no mapa + relatório
    python manage.py testar_classificador_brasil --limpar      # remove casos de teste

MODO PURO  (default):
    - Chama _build_disease_probabilities() diretamente com taxas 100%
    - Sem prior geográfico (estado_uf=None): testa só a pontuação de sintomas
    - Com prior geográfico (estado ótimo): testa o sistema completo
    - Zero efeito no banco — apenas leitura

MODO MAPA (--mapa):
    - Insere casos reais no banco por ORM direto (sem HTTP)
    - Cada cluster de doença fica numa cidade/estado com prior alto
    - Permite verificar visualmente no mapa que cada região mostra a doença correta
    - Prefixo: "clf-br-" (NÃO está em SYNTHETIC_DEVICE_PREFIXES)
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

DEVICE_PREFIX = "clf-br-"

# ─── Perfis de doença ───────────────────────────────────────────────────────
# Cada perfil define:
#   sintomas: dict campo→bool a passar para RegistroSintoma
#   estado_uf: UF onde o prior geográfico favoreça a doença
#   cidade/estado: strings do banco (para GROUP BY correto)
#   lat/lon: coordenadas base
#   casos_mapa: quantos inserir no modo --mapa
#   esperado_puro: doença que deve ganhar SEM prior geográfico
#   esperado_geo:  doença que deve ganhar COM prior do estado_uf
# ─────────────────────────────────────────────────────────────────────────────
PERFIS = [
    {
        "nome": "Dengue",
        "estado_uf": "PE",
        "cidade": "Recife", "estado": "Pernambuco", "bairro": "Boa Vista",
        "lat": -8.0476, "lon": -34.8770,
        "casos_mapa": 250,
        "sintomas": {
            "febre": True, "dor_corpo": True, "dor_cabeca": True,
            "cansaco": True, "vomito_nausea": True, "exantema": True,
            "dor_abdominal": True,
            # negativos fortes para dengue
            "tosse": False, "falta_ar": False, "coriza": False,
            "perda_olfato_paladar": False, "rigidez_nuca": False,
        },
        "esperado_puro": "Dengue",
        "esperado_geo":  "Dengue",
    },
    {
        "nome": "Chikungunya",
        "estado_uf": "BA",
        "cidade": "Salvador", "estado": "Bahia", "bairro": "Centro",
        "lat": -12.9777, "lon": -38.5016,
        "casos_mapa": 200,
        "sintomas": {
            "febre": True, "dor_articular": True, "exantema": True,
            "dor_corpo": True, "cansaco": True, "dor_cabeca": True,
            # chikungunya: articular intenso + exantema + SEM respiratório
            "tosse": False, "falta_ar": False, "coriza": False,
            "perda_olfato_paladar": False, "ictericia": False,
        },
        "esperado_puro": "Chikungunya",
        "esperado_geo":  "Chikungunya",
    },
    {
        "nome": "Zika",
        "estado_uf": "PE",
        "cidade": "João Pessoa", "estado": "Paraíba", "bairro": "Centro",
        "lat": -7.1153, "lon": -34.8641,
        "casos_mapa": 180,
        "sintomas": {
            # Zika: exantema + conjuntivite (patognomônico) + febre baixa
            "exantema": True, "conjuntivite": True, "febre": True,
            "dor_articular": True, "cansaco": True, "dor_corpo": True,
            "tosse": False, "falta_ar": False, "manchas_hemorragicas": False,
            "perda_olfato_paladar": False, "dor_abdominal": False,
        },
        "esperado_puro": "Zika",
        "esperado_geo":  "Zika",
    },
    {
        "nome": "Malária",
        "estado_uf": "AM",
        "cidade": "Manaus", "estado": "Amazonas", "bairro": "Centro",
        "lat": -3.1190, "lon": -60.0217,
        "casos_mapa": 200,
        "sintomas": {
            # tríade patognomônica malária: febre cíclica + calafrios + sudorese
            "febre": True, "calafrios": True, "sudorese": True,
            "cansaco": True, "dor_corpo": True, "dor_cabeca": True,
            "vomito_nausea": True, "viagem_area_endemica": True,
            "tosse": False, "falta_ar": False, "exantema": False,
            "coriza": False, "perda_olfato_paladar": False,
        },
        "esperado_puro": "Malaria",
        "esperado_geo":  "Malaria",
    },
    {
        "nome": "Febre Amarela",
        "estado_uf": "MG",
        "cidade": "Belo Horizonte", "estado": "Minas Gerais", "bairro": "Centro",
        "lat": -19.9167, "lon": -43.9345,
        "casos_mapa": 150,
        "sintomas": {
            # FA: febre + icterícia + hemorragia + vômito (tríade clínica)
            "febre": True, "ictericia": True, "manchas_hemorragicas": True,
            "vomito_nausea": True, "dor_corpo": True, "cansaco": True,
            "dor_abdominal": True, "calafrios": True,
            "tosse": False, "coriza": False, "perda_olfato_paladar": False,
        },
        "esperado_puro": "Febre Amarela",
        "esperado_geo":  "Febre Amarela",
    },
    {
        "nome": "Leptospirose",
        "estado_uf": "RS",
        "cidade": "Porto Alegre", "estado": "Rio Grande do Sul", "bairro": "Centro Histórico",
        "lat": -30.0346, "lon": -51.2177,
        "casos_mapa": 150,
        "sintomas": {
            # Lepto: febre + dor muscular intensa + icterícia (síndrome de Weil)
            "febre": True, "dor_corpo": True, "ictericia": True,
            "calafrios": True, "vomito_nausea": True, "dor_abdominal": True,
            "dor_cabeca": True, "cansaco": True,
            "exposicao_agua_enchente": True,
            "tosse": False, "exantema": False, "perda_olfato_paladar": False,
        },
        "esperado_puro": "Leptospirose",
        "esperado_geo":  "Leptospirose",
    },
    {
        "nome": "Hantavirose",
        "estado_uf": "SC",
        "cidade": "Florianópolis", "estado": "Santa Catarina", "bairro": "Centro",
        "lat": -27.5945, "lon": -48.5477,
        "casos_mapa": 100,
        "sintomas": {
            # Hantavirose: falta_ar obrigatória (síndrome cardiopulmonar) + hemoptise
            "falta_ar": True, "febre": True, "cansaco": True,
            "dor_corpo": True, "tosse": True, "calafrios": True,
            "hemoptise": True, "contato_roedores": True,
            "exantema": False, "coriza": False, "perda_olfato_paladar": False,
        },
        "esperado_puro": "Hantavirose",
        "esperado_geo":  "Hantavirose",
    },
    {
        "nome": "Meningite",
        "estado_uf": "SP",
        "cidade": "Campinas", "estado": "São Paulo", "bairro": "Centro",
        "lat": -22.9099,
        "lon": -47.0626,
        "casos_mapa": 120,
        "sintomas": {
            # Meningite: rigidez_nuca patognomônico + petéquias + cefaleia
            "rigidez_nuca": True, "febre": True, "dor_cabeca": True,
            "manchas_hemorragicas": True, "vomito_nausea": True, "cansaco": True,
            "tosse": False, "exantema": False, "perda_olfato_paladar": False,
        },
        "esperado_puro": "Meningite",
        "esperado_geo":  "Meningite",
    },
    {
        "nome": "COVID-19",
        "estado_uf": "DF",
        "cidade": "Brasília", "estado": "Distrito Federal", "bairro": "Asa Sul",
        "lat": -15.7801, "lon": -47.9292,
        "casos_mapa": 200,
        "sintomas": {
            # COVID: perda_olfato_paladar + falta_ar (diferenciadores únicos)
            "perda_olfato_paladar": True, "tosse": True, "falta_ar": True,
            "febre": True, "cansaco": True, "dor_corpo": True,
            "dor_cabeca": True, "dor_garganta": True,
            "exantema": False, "ictericia": False, "rigidez_nuca": False,
        },
        "esperado_puro": "COVID-19",
        "esperado_geo":  "COVID-19",
    },
    {
        "nome": "Gripe",
        "estado_uf": "RS",
        "cidade": "Caxias do Sul", "estado": "Rio Grande do Sul", "bairro": "Centro",
        "lat": -29.1681, "lon": -51.1793,
        "casos_mapa": 180,
        "sintomas": {
            # Gripe: febre + tosse + dor_corpo + calafrios + coriza (síndrome gripal clássica)
            "febre": True, "tosse": True, "dor_corpo": True,
            "dor_cabeca": True, "cansaco": True, "calafrios": True,
            "coriza": True, "dor_garganta": True,
            "perda_olfato_paladar": False, "exantema": False,
            "ictericia": False, "rigidez_nuca": False,
        },
        "esperado_puro": "Gripe",
        "esperado_geo":  "Gripe",
    },
    {
        "nome": "Gastroenterite Viral",
        "estado_uf": "CE",
        "cidade": "Teresina", "estado": "Piauí", "bairro": "Centro",
        "lat": -5.0892, "lon": -42.8019,
        "casos_mapa": 150,
        "sintomas": {
            # Gastro: vômito + diarreia (diferenciadores) + dor abdominal
            "vomito_nausea": True, "diarreia": True, "dor_abdominal": True,
            "febre": True, "cansaco": True,
            "tosse": False, "falta_ar": False, "exantema": False,
            "ictericia": False, "dor_corpo": False,
        },
        "esperado_puro": "Gastroenterite Viral",
        "esperado_geo":  "Gastroenterite Viral",
    },
    {
        "nome": "Hepatite A/B",
        "estado_uf": "AM",
        "cidade": "Belém", "estado": "Pará", "bairro": "Guamá",
        "lat": -1.4900, "lon": -48.4900,
        "casos_mapa": 120,
        "sintomas": {
            # Hepatite: icterícia (1.0) + vômito + cansaco intenso — SEM dor articular ou exantema
            "ictericia": True, "vomito_nausea": True, "cansaco": True,
            "dor_abdominal": True, "febre": False,
            "tosse": False, "coriza": False, "perda_olfato_paladar": False,
            "dor_corpo": False, "calafrios": False, "exantema": False,
        },
        "esperado_puro": "Hepatite A/B",
        "esperado_geo":  "Hepatite A/B",  # nota: prior baixo; pode perder para Dengue
    },
    {
        "nome": "Sarampo",
        "estado_uf": "PA",
        "cidade": "Santarém", "estado": "Pará", "bairro": "Centro",
        "lat": -2.4407, "lon": -54.7082,
        "casos_mapa": 100,
        "sintomas": {
            # Sarampo: exantema + conjuntivite + tosse + coriza + febre (pentacardinal)
            "febre": True, "exantema": True, "conjuntivite": True,
            "tosse": True, "coriza": True, "dor_cabeca": True,
            "perda_olfato_paladar": False, "ictericia": False,
        },
        "esperado_puro": "Sarampo",
        "esperado_geo":  "Sarampo",  # nota: prior baixo; pode perder para Dengue
    },
    {
        "nome": "Bronquite",
        "estado_uf": "PR",
        "cidade": "Curitiba", "estado": "Paraná", "bairro": "Centro",
        "lat": -25.4284, "lon": -49.2733,
        "casos_mapa": 120,
        "sintomas": {
            # Bronquite: tosse crônica (1.0) + falta_ar sem febre
            "tosse": True, "falta_ar": True, "cansaco": True, "coriza": True,
            "febre": False, "exantema": False, "ictericia": False,
            "dor_corpo": False,
        },
        "esperado_puro": "Bronquite",
        "esperado_geo":  "Bronquite",
    },
]


def _set_rls(empresa_id):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.empresa_id', %s, false)", [str(empresa_id)])


def _run_pure_test(stdout, style):
    """Testa _build_disease_probabilities() com taxas 100% — sem DB, sem prior."""
    from api.epidemiologia import _build_disease_probabilities, DISEASE_WEIGHTS

    LINHA = "─" * 72
    stdout.write("\n" + "═" * 72)
    stdout.write("  MODO 1: SINTOMAS PUROS (sem prior geográfico)")
    stdout.write("  Cada doença testada com 100% de taxa nos seus sintomas-chave.")
    stdout.write("═" * 72)
    stdout.write(f"  {'Doença':<22} {'Esperado':<20} {'#1 (puro)':<20} {'#2':<20} OK?")
    stdout.write(LINHA)

    acertos = 0
    for perfil in PERFIS:
        nome = perfil["nome"]
        sintomas_raw = perfil["sintomas"]

        # Monta symptom_counts com taxa 1.0 para todos os True
        n_casos = 100
        symptom_counts = {s: (n_casos if v else 0) for s, v in sintomas_raw.items()
                          if s in {c for d in DISEASE_WEIGHTS.values() for c in d}}

        resultado = _build_disease_probabilities(
            symptom_counts, n_casos,
            risco_oficial_doenca_map=None,
            estado_uf=None,  # sem prior geográfico
        )

        r1 = resultado[0]["name"] if resultado else "—"
        r2 = resultado[1]["name"] if len(resultado) > 1 else "—"
        p1 = resultado[0]["probability"] if resultado else 0
        esperado = perfil["esperado_puro"]
        ok = "✓" if r1 == esperado else "✗"
        if r1 == esperado:
            acertos += 1

        linha = f"  {nome:<22} {esperado:<20} {r1:<20} {r2:<20} {ok}"
        if ok == "✓":
            stdout.write(style.SUCCESS(linha))
        else:
            stdout.write(style.ERROR(linha))
            stdout.write(style.WARNING(f"    → P1={p1:.1f}% (esperado {esperado})"))

    stdout.write(LINHA)
    msg = f"  Resultado: {acertos}/{len(PERFIS)} corretos"
    if acertos == len(PERFIS):
        stdout.write(style.SUCCESS(msg))
    else:
        stdout.write(style.WARNING(msg))
    stdout.write("")


def _run_geo_test(stdout, style):
    """Testa com prior geográfico no estado ótimo de cada doença."""
    from api.epidemiologia import _build_disease_probabilities, DISEASE_WEIGHTS

    LINHA = "─" * 80
    stdout.write("\n" + "═" * 80)
    stdout.write("  MODO 2: COM PRIOR GEOGRÁFICO (estado ótimo por doença)")
    stdout.write("  O prior reflete a realidade epidemiológica — doenças raras podem")
    stdout.write("  perder para Dengue em regiões onde Dengue domina.")
    stdout.write("═" * 80)
    stdout.write(f"  {'Doença':<22} {'UF':<4} {'Esperado':<20} {'#1 (geo)':<20} {'#1 %':>6}  OK?")
    stdout.write(LINHA)

    acertos = 0
    avisos = []
    for perfil in PERFIS:
        nome = perfil["nome"]
        sintomas_raw = perfil["sintomas"]
        uf = perfil["estado_uf"]

        n_casos = 100
        symptom_counts = {s: (n_casos if v else 0) for s, v in sintomas_raw.items()
                          if s in {c for d in DISEASE_WEIGHTS.values() for c in d}}

        resultado = _build_disease_probabilities(
            symptom_counts, n_casos,
            risco_oficial_doenca_map=None,
            estado_uf=uf,
        )

        r1 = resultado[0]["name"] if resultado else "—"
        p1 = resultado[0]["probability"] if resultado else 0
        esperado = perfil["esperado_geo"]
        ok = "✓" if r1 == esperado else "⚠"
        if r1 == esperado:
            acertos += 1

        linha = f"  {nome:<22} {uf:<4} {esperado:<20} {r1:<20} {p1:>5.1f}%  {ok}"
        if ok == "✓":
            stdout.write(style.SUCCESS(linha))
        else:
            stdout.write(style.WARNING(linha))
            r2 = resultado[1]["name"] if len(resultado) > 1 else "—"
            p2 = resultado[1]["probability"] if len(resultado) > 1 else 0
            avisos.append(f"  ⚠ {nome} em {uf}: prior geográfico favorece '{r1}' ({p1:.1f}%) — esperado '{esperado}'. #2={r2} ({p2:.1f}%)")

    stdout.write(LINHA)
    msg = f"  Resultado: {acertos}/{len(PERFIS)} corretos com prior geográfico"
    if acertos == len(PERFIS):
        stdout.write(style.SUCCESS(msg))
    else:
        stdout.write(style.WARNING(msg))

    if avisos:
        stdout.write(style.WARNING("\n  Detalhes dos desvios (⚠ = prior geográfico esperado):"))
        for a in avisos:
            stdout.write(style.WARNING(a))
        stdout.write(style.WARNING("  Nota: desvios com prior geográfico são CORRETOS epidemiologicamente."))
        stdout.write(style.WARNING("  Em regiões endêmicas de Dengue, sintomas inespecíficos devem"))
        stdout.write(style.WARNING("  apontar Dengue — não Hepatite ou Sarampo sem evidência adicional."))
    stdout.write("")


def _inserir_mapa(stdout, style):
    """Insere casos reais no banco para verificação visual no mapa."""
    from api.epidemiologia import PUBLIC_APP_EMAIL, clear_panorama_cache
    from api.models import Empresa, RegistroSintoma

    empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
    if not empresa:
        stdout.write(style.ERROR(f"Empresa pública não encontrada ({PUBLIC_APP_EMAIL}). Abortando."))
        return

    _set_rls(empresa.id)
    agora = timezone.now()

    LINHA = "─" * 60
    stdout.write("\n" + "═" * 60)
    stdout.write("  MODO MAPA: inserindo clusters por doença no banco")
    stdout.write("═" * 60)

    total_inserido = 0
    for perfil in PERFIS:
        nome = perfil["nome"]
        n = perfil["casos_mapa"]
        sintomas = {k: v for k, v in perfil["sintomas"].items()
                    if hasattr(RegistroSintoma, k.replace(".", "_"))}

        records = []
        for i in range(n):
            device_id = f"{DEVICE_PREFIX}{nome.lower().replace(' ', '-')[:10]}-{i:04d}"
            records.append(RegistroSintoma(
                empresa=empresa,
                device_id=device_id,
                latitude=perfil["lat"] + random.uniform(-0.06, 0.06),
                longitude=perfil["lon"] + random.uniform(-0.06, 0.06),
                pais="Brasil",
                estado=perfil["estado"],
                cidade=perfil["cidade"],
                bairro=perfil["bairro"],
                origem_dado=RegistroSintoma.ORIGEM_CIDADAO,
                **sintomas,
            ))

        BATCH = 200
        criados = 0
        for j in range(0, len(records), BATCH):
            RegistroSintoma.objects.bulk_create(records[j:j + BATCH])
            criados += len(records[j:j + BATCH])

        RegistroSintoma.objects.filter(
            empresa=empresa, device_id__startswith=f"{DEVICE_PREFIX}{nome.lower().replace(' ', '-')[:10]}-"
        ).update(data_registro=agora - timedelta(days=1))

        total_inserido += criados
        stdout.write(style.SUCCESS(f"  ✓ {nome:<22} {criados:>4} casos → {perfil['cidade']}/{perfil['estado_uf']}"))

    _set_rls(empresa.id)
    clear_panorama_cache()

    stdout.write(LINHA)
    stdout.write(style.SUCCESS(f"  Total: {total_inserido} casos inseridos. Cache limpo."))
    stdout.write(style.WARNING("  Abra o mapa e verifique se cada cidade mostra a doença esperada."))
    stdout.write(style.WARNING("  Use --limpar para remover os casos após a validação."))
    stdout.write("")


def _limpar(stdout, style):
    from api.epidemiologia import PUBLIC_APP_EMAIL, clear_panorama_cache
    from api.models import Empresa, RegistroSintoma

    empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
    if empresa:
        _set_rls(empresa.id)
        n, _ = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id__startswith=DEVICE_PREFIX,
        ).delete()
        stdout.write(style.SUCCESS(f"  {n} registros de teste removidos."))
    clear_panorama_cache()
    stdout.write(style.SUCCESS("  Cache limpo."))


class Command(BaseCommand):
    help = "Teste sistêmico do classificador de doenças — verifica sintomas e priors geográficos."

    def add_arguments(self, parser):
        parser.add_argument("--mapa", action="store_true",
                            help="Insere casos no banco para verificação visual no mapa")
        parser.add_argument("--limpar", action="store_true",
                            help="Remove todos os casos de teste do banco")
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        random.seed(options["seed"])

        if options["limpar"]:
            self.stdout.write("Removendo casos de teste...")
            _limpar(self.stdout, self.style)
            return

        self.stdout.write("\n" + "═" * 72)
        self.stdout.write("  TESTE SISTÊMICO — CLASSIFICADOR DE DOENÇAS SoloCRT")
        self.stdout.write(f"  {len(PERFIS)} doenças · sintomas 100% · priors por UF")
        self.stdout.write("═" * 72)

        _run_pure_test(self.stdout, self.style)
        _run_geo_test(self.stdout, self.style)

        if options["mapa"]:
            _inserir_mapa(self.stdout, self.style)

        self.stdout.write("  Para teste visual no mapa: --mapa")
        self.stdout.write("  Para limpar após o teste:  --limpar\n")
