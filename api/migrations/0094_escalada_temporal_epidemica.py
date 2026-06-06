"""Escalada epidemiológica temporal para o app da população (demo/teste).

Cria ~5.000 registros de sintoma distribuídos nos ÚLTIMOS 14 DIAS, com
tendência crescente e VARIADA por região — surtos fortes, crescimento
moderado, focos estáveis e focos em queda. Assim:

  • o crescimento (7d vs 7d anteriores) fica realista e diferente por região;
  • a série histórica dos painéis sobe de forma natural;
  • todos os ambientes (Governo/Farmácia/Hospital/Plano) e o app refletem os
    mesmos focos, pois leem da mesma fonte (build_panorama_payload).

Roda no banco de produção via `manage.py migrate` (preDeploy), com acesso
total — sem depender de login, RLS, CSRF ou plano ativo. É ADITIVO e
idempotente: se a escalada já foi semeada (marcador device_id), não duplica.
Nunca levanta exceção — não pode quebrar o deploy.
"""
import random
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


PUBLIC_APP_EMAIL = "populacao@soluscrt.com"
SIM_TAG = "sim-escalada-14d"
DIAS = 14

SINTOMAS = {
    "Dengue":         {"febre": True, "dor_corpo": True, "dor_cabeca": True, "cansaco": True, "vomito_nausea": True},
    "Chikungunya":    {"febre": True, "dor_articular": True, "exantema": True, "dor_corpo": True, "cansaco": True},
    "Zika":           {"exantema": True, "conjuntivite": True, "febre": True, "dor_articular": True},
    "COVID-19":       {"febre": True, "tosse": True, "falta_ar": True, "perda_olfato_paladar": True, "cansaco": True},
    "Gripe":          {"febre": True, "tosse": True, "dor_corpo": True, "dor_cabeca": True, "cansaco": True},
    "Malária":        {"febre": True, "calafrios": True, "cansaco": True, "dor_corpo": True},
    "Resfriado Viral": {"coriza": True, "dor_garganta": True, "tosse": True},
}

# (bairro, cidade, estado, lat, lng, doenca, base_diaria, tendencia)
# tendencia: surto | crescente | estavel | queda
FOCOS = [
    # ── RIO DE JANEIRO — vários bairros e municípios, tendências variadas ──
    ("Copacabana",      "Rio de Janeiro", "Rio de Janeiro", -22.9711, -43.1835, "Dengue",        12, "surto"),
    ("Tijuca",          "Rio de Janeiro", "Rio de Janeiro", -22.9218, -43.2358, "Dengue",        10, "crescente"),
    ("Madureira",       "Rio de Janeiro", "Rio de Janeiro", -22.8762, -43.3340, "Dengue",         9, "surto"),
    ("Botafogo",        "Rio de Janeiro", "Rio de Janeiro", -22.9519, -43.1869, "Gripe",          7, "estavel"),
    ("Méier",           "Rio de Janeiro", "Rio de Janeiro", -22.8981, -43.2797, "Dengue",         8, "crescente"),
    ("Leblon",          "Rio de Janeiro", "Rio de Janeiro", -22.9842, -43.2247, "COVID-19",       6, "queda"),
    ("Barra da Tijuca", "Rio de Janeiro", "Rio de Janeiro", -22.9999, -43.3645, "Gripe",          7, "estavel"),
    ("Campo Grande",    "Rio de Janeiro", "Rio de Janeiro", -22.8740, -43.5580, "Dengue",        10, "surto"),
    ("Icaraí",          "Niterói",        "Rio de Janeiro", -22.8993, -43.1163, "Dengue",         9, "crescente"),
    ("Centro",          "Niterói",        "Rio de Janeiro", -22.8836, -43.1037, "Chikungunya",    6, "estavel"),
    ("Centro",          "Nova Iguaçu",    "Rio de Janeiro", -22.7596, -43.4505, "Dengue",        11, "surto"),
    ("Centro",          "Duque de Caxias", "Rio de Janeiro", -22.7853, -43.3115, "Dengue",        10, "crescente"),
    ("Centro",          "São Gonçalo",    "Rio de Janeiro", -22.8267, -43.0539, "Gripe",          7, "estavel"),
    ("Centro",          "Campos dos Goytacazes", "Rio de Janeiro", -21.7542, -41.3244, "Dengue",  6, "queda"),
    ("Centro",          "Petrópolis",     "Rio de Janeiro", -22.5043, -43.1820, "Resfriado Viral", 5, "queda"),
    # ── SÃO PAULO ──────────────────────────────────────────────────────────
    ("Pinheiros",       "São Paulo",      "São Paulo",      -23.5629, -46.6898, "Gripe",         11, "crescente"),
    ("Santana",         "São Paulo",      "São Paulo",      -23.4948, -46.6387, "Dengue",        10, "surto"),
    ("Centro",          "Campinas",       "São Paulo",      -22.9058, -47.0609, "COVID-19",       8, "estavel"),
    ("Centro",          "Ribeirão Preto", "São Paulo",      -21.1775, -47.8103, "Dengue",        12, "surto"),
    ("Centro",          "São José dos Campos", "São Paulo",  -23.1896, -45.8841, "Gripe",         7, "estavel"),
    # ── MINAS GERAIS ───────────────────────────────────────────────────────
    ("Savassi",         "Belo Horizonte", "Minas Gerais",   -19.9385, -43.9385, "Dengue",        12, "surto"),
    ("Centro",          "Uberlândia",     "Minas Gerais",   -18.9186, -48.2772, "Gripe",          8, "crescente"),
    # ── NORDESTE ───────────────────────────────────────────────────────────
    ("Boa Viagem",      "Recife",         "Pernambuco",     -8.1167,  -34.8993, "Dengue",        13, "surto"),
    ("Aldeota",         "Fortaleza",      "Ceará",          -3.7327,  -38.5024, "Chikungunya",   11, "crescente"),
    ("Pelourinho",      "Salvador",       "Bahia",          -12.9718, -38.5102, "Dengue",        10, "estavel"),
    ("Centro",          "São Luís",       "Maranhão",       -2.5283,  -44.3068, "Dengue",         9, "surto"),
    ("Centro",          "Natal",          "Rio Grande do Norte", -5.7945, -35.2110, "Zika",       7, "crescente"),
    # ── NORTE ──────────────────────────────────────────────────────────────
    ("Centro",          "Manaus",         "Amazonas",       -3.1190,  -60.0217, "Malária",       11, "surto"),
    ("Centro",          "Belém",          "Pará",           -1.4558,  -48.4902, "Dengue",         9, "crescente"),
    # ── CENTRO-OESTE ───────────────────────────────────────────────────────
    ("Asa Sul",         "Brasília",       "Distrito Federal", -15.7949, -47.8825, "Gripe",        9, "estavel"),
    ("Setor Central",   "Goiânia",        "Goiás",          -16.6869, -49.2648, "Dengue",        10, "surto"),
    ("Centro",          "Campo Grande",   "Mato Grosso do Sul", -20.4428, -54.6460, "Dengue",     8, "crescente"),
    # ── SUL ────────────────────────────────────────────────────────────────
    ("Centro",          "Curitiba",       "Paraná",         -25.4284, -49.2733, "Gripe",          9, "queda"),
    ("Centro Histórico", "Porto Alegre",  "Rio Grande do Sul", -30.0346, -51.2177, "Gripe",       8, "estavel"),
    ("Centro",          "Florianópolis",  "Santa Catarina", -27.5954, -48.5480, "COVID-19",       7, "crescente"),
]


def _fator(tendencia, d, total=DIAS):
    """Fator multiplicador do dia d (0=mais antigo, total-1=hoje)."""
    frac = d / max(total - 1, 1)  # 0..1
    if tendencia == "surto":
        return 0.25 + 2.4 * frac          # sobe forte
    if tendencia == "crescente":
        return 0.55 + 1.1 * frac          # sobe moderado
    if tendencia == "estavel":
        return 0.90 + 0.2 * frac          # quase plano
    if tendencia == "queda":
        return 1.45 - 0.95 * frac         # cai ao longo do tempo
    return 1.0


def _escalada(apps, schema_editor):
    Empresa = apps.get_model("api", "Empresa")
    RegistroSintoma = apps.get_model("api", "RegistroSintoma")

    empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
    if not empresa:
        return

    # Idempotência: se a escalada já existe, não duplica.
    if RegistroSintoma.objects.filter(empresa=empresa, device_id=SIM_TAG).exists():
        return

    agora = timezone.now()
    rnd = random.Random(20260606)  # determinístico
    registros = []
    timestamps = []  # guardamos o ts pretendido separadamente

    for (bairro, cidade, estado, lat, lng, doenca, base, tend) in FOCOS:
        sint = SINTOMAS.get(doenca, {})
        for d in range(DIAS):
            n = max(0, round(base * _fator(tend, d) * rnd.uniform(0.8, 1.2)))
            dia_offset = (DIAS - 1) - d  # d=DIAS-1 => hoje (offset 0)
            for _ in range(n):
                ts = agora - timedelta(
                    days=dia_offset,
                    hours=rnd.uniform(0, 23),
                    minutes=rnd.uniform(0, 59),
                )
                timestamps.append(ts)
                registros.append(RegistroSintoma(
                    empresa=empresa,
                    latitude=lat + rnd.uniform(-0.01, 0.01),
                    longitude=lng + rnd.uniform(-0.01, 0.01),
                    cidade=cidade, bairro=bairro, estado=estado, pais="Brasil",
                    grupo=doenca,
                    febre=sint.get("febre", False),
                    tosse=sint.get("tosse", False),
                    dor_corpo=sint.get("dor_corpo", False),
                    cansaco=sint.get("cansaco", False),
                    falta_ar=sint.get("falta_ar", False),
                    dor_cabeca=sint.get("dor_cabeca", False),
                    dor_articular=sint.get("dor_articular", False),
                    exantema=sint.get("exantema", False),
                    vomito_nausea=sint.get("vomito_nausea", False),
                    calafrios=sint.get("calafrios", False),
                    conjuntivite=sint.get("conjuntivite", False),
                    perda_olfato_paladar=sint.get("perda_olfato_paladar", False),
                    coriza=sint.get("coriza", False),
                    dor_garganta=sint.get("dor_garganta", False),
                    confianca=1.0,
                    origem_dado="cidadao",
                    suspeito=False,
                    device_id=SIM_TAG,
                    data_registro=ts,
                ))

    if not registros:
        return

    # Fase 1: INSERT em lotes. O campo data_registro tem auto_now_add=True,
    # então o banco grava "agora" — corrigimos na fase 2.
    BATCH = 500
    criados = []
    for i in range(0, len(registros), BATCH):
        criados.extend(
            RegistroSintoma.objects.bulk_create(registros[i:i + BATCH])
        )

    # Fase 2: backdate real via bulk_update (UPDATE cru ignora auto_now_add),
    # aplicando a distribuição temporal pretendida nos 14 dias.
    for obj, ts in zip(criados, timestamps):
        obj.data_registro = ts
    for i in range(0, len(criados), BATCH):
        RegistroSintoma.objects.bulk_update(
            criados[i:i + BATCH], ["data_registro"]
        )

    try:
        from api.epidemiologia import clear_panorama_cache
        clear_panorama_cache()
    except Exception:
        pass


def _remove(apps, schema_editor):
    Empresa = apps.get_model("api", "Empresa")
    RegistroSintoma = apps.get_model("api", "RegistroSintoma")
    empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
    if empresa:
        RegistroSintoma.objects.filter(empresa=empresa, device_id=SIM_TAG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0093_regeocodifica_focos_publicos"),
    ]

    operations = [
        migrations.RunPython(_escalada, _remove),
    ]
