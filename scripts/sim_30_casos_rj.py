"""
Simulação de 30 casos no Rio de Janeiro para visualização no mapa.

Como rodar no shell do Render:
    python manage.py shell < scripts/sim_30_casos_rj.py

Ou interativo:
    python manage.py shell
    >>> exec(open('scripts/sim_30_casos_rj.py').read())

Para apagar os casos de simulação depois:
        RegistroSintoma.objects.filter(device_id__startswith='sim-br-').delete()
"""

import uuid
import random
from django.contrib.auth.hashers import make_password
from api.models import Empresa, RegistroSintoma
from api.middleware import _rls_set_empresa as _set_rls
from api.classificador_doencas import classificar
from api.epidemiologia import clear_panorama_cache

random.seed(42)

# ── Empresa pública ───────────────────────────────────────────────────────────
empresa, _ = Empresa.objects.get_or_create(
    email="populacao@solocrt.com",
    defaults={
        "nome": "SoloCRT Populacao",
        "senha": make_password("publico_app"),
        "ativo": True,
        "plano": "publico",
        "pacote_codigo": "governo_estado",
        "max_usuarios": 1000,
        "max_dispositivos": 1000,
    },
)
_set_rls(empresa.id)

# ── Localizações ──────────────────────────────────────────────────────────────
# (bairro, cidade, estado, lat, lon)
LOCAIS = [
    ("Copacabana",     "Rio de Janeiro", "Rio de Janeiro", -22.9711, -43.1823),  # 0
    ("Ipanema",        "Rio de Janeiro", "Rio de Janeiro", -22.9838, -43.2096),  # 1
    ("Leblon",         "Rio de Janeiro", "Rio de Janeiro", -22.9860, -43.2247),  # 2
    ("Botafogo",       "Rio de Janeiro", "Rio de Janeiro", -22.9444, -43.1867),  # 3
    ("Flamengo",       "Rio de Janeiro", "Rio de Janeiro", -22.9333, -43.1770),  # 4
    ("Centro",         "Rio de Janeiro", "Rio de Janeiro", -22.9068, -43.1729),  # 5
    ("Tijuca",         "Rio de Janeiro", "Rio de Janeiro", -22.9274, -43.2348),  # 6
    ("Méier",          "Rio de Janeiro", "Rio de Janeiro", -22.8939, -43.2769),  # 7
    ("Madureira",      "Rio de Janeiro", "Rio de Janeiro", -22.8736, -43.3395),  # 8
    ("Penha",          "Rio de Janeiro", "Rio de Janeiro", -22.8369, -43.2705),  # 9
    ("Barra da Tijuca","Rio de Janeiro", "Rio de Janeiro", -23.0000, -43.3654),  # 10
    ("Jacarepaguá",    "Rio de Janeiro", "Rio de Janeiro", -22.9364, -43.3690),  # 11
    ("Campo Grande",   "Rio de Janeiro", "Rio de Janeiro", -22.9009, -43.5628),  # 12
    ("Realengo",       "Rio de Janeiro", "Rio de Janeiro", -22.8798, -43.4165),  # 13
    ("Bangu",          "Rio de Janeiro", "Rio de Janeiro", -22.8774, -43.4636),  # 14
    ("Santa Cruz",     "Rio de Janeiro", "Rio de Janeiro", -22.9065, -43.6876),  # 15
    ("Icaraí",         "Niterói",        "Rio de Janeiro", -22.8897, -43.1286),  # 16
    ("Centro",         "Niterói",        "Rio de Janeiro", -22.8983, -43.1185),  # 17
    ("Nova Iguaçu",    "Nova Iguaçu",    "Rio de Janeiro", -22.7594, -43.4511),  # 18
    ("Duque de Caxias","Duque de Caxias","Rio de Janeiro", -22.7856, -43.3116),  # 19
]

# ── Casos ─────────────────────────────────────────────────────────────────────
# _local = índice em LOCAIS
CASOS = [
    # Dengue (8) — febre obrigatória
    {"febre":True,"dor_corpo":True,"dor_cabeca":True,"cansaco":True,"dor_articular":True,"_local":0},
    {"febre":True,"dor_corpo":True,"dor_cabeca":True,"exantema":True,"dor_articular":True,"cansaco":True,"_local":1},
    {"febre":True,"dor_articular":True,"dor_cabeca":True,"cansaco":True,"exantema":True,"_local":2},
    {"febre":True,"dor_corpo":True,"cansaco":True,"dor_cabeca":True,"vomito_nausea":True,"dor_articular":True,"_local":3},
    {"febre":True,"dor_cabeca":True,"dor_articular":True,"cansaco":True,"_local":4},
    {"febre":True,"conjuntivite":True,"exantema":True,"dor_articular":True,"cansaco":True,"_local":5},
    {"febre":True,"dor_corpo":True,"dor_articular":True,"sudorese":True,"cansaco":True,"_local":6},
    {"febre":True,"dor_cabeca":True,"dor_corpo":True,"calafrios":True,"cansaco":True,"_local":16},

    # Gastroenterite (6) — sem febre
    {"diarreia":True,"dor_abdominal":True,"vomito_nausea":True,"cansaco":True,"_local":5},
    {"diarreia":True,"dor_abdominal":True,"cansaco":True,"_local":8},
    {"diarreia":True,"vomito_nausea":True,"dor_abdominal":True,"dor_corpo":True,"_local":9},
    {"diarreia":True,"dor_abdominal":True,"_local":10},
    {"diarreia":True,"vomito_nausea":True,"cansaco":True,"_local":11},
    {"diarreia":True,"dor_abdominal":True,"vomito_nausea":True,"_local":12},

    # Gripe / Influenza (5)
    {"febre":True,"tosse":True,"dor_corpo":True,"cansaco":True,"dor_cabeca":True,"_local":13},
    {"febre":True,"tosse":True,"cansaco":True,"dor_corpo":True,"dor_garganta":True,"_local":14},
    {"febre":True,"tosse":True,"dor_corpo":True,"cansaco":True,"_local":17},
    {"febre":True,"tosse":True,"cansaco":True,"dor_garganta":True,"sudorese":True,"_local":18},
    {"febre":True,"tosse":True,"dor_corpo":True,"calafrios":True,"cansaco":True,"_local":19},

    # Resfriado viral (5) — sem febre
    {"tosse":True,"coriza":True,"dor_garganta":True,"_local":1},
    {"tosse":True,"coriza":True,"dor_garganta":True,"cansaco":True,"_local":7},
    {"tosse":True,"coriza":True,"_local":15},
    {"tosse":True,"dor_garganta":True,"cansaco":True,"_local":19},
    {"coriza":True,"dor_garganta":True,"tosse":True,"_local":6},

    # COVID-19 (3)
    {"febre":True,"tosse":True,"falta_ar":True,"perda_olfato_paladar":True,"cansaco":True,"_local":0},
    {"febre":True,"falta_ar":True,"perda_olfato_paladar":True,"cansaco":True,"_local":3},
    {"tosse":True,"perda_olfato_paladar":True,"cansaco":True,"falta_ar":True,"_local":8},

    # Bronquite / Respiratório (2)
    {"tosse":True,"falta_ar":True,"cansaco":True,"_local":9},
    {"tosse":True,"falta_ar":True,"cansaco":True,"dor_garganta":True,"_local":15},

    # Leptospirose (1)
    {"febre":True,"dor_corpo":True,"calafrios":True,"cansaco":True,
     "exposicao_agua_enchente":True,"_local":13},
]

CAMPOS_BOOL = [
    "febre","tosse","dor_corpo","cansaco","falta_ar",
    "dor_cabeca","dor_articular","exantema","conjuntivite",
    "vomito_nausea","diarreia","dor_abdominal","rigidez_nuca",
    "ictericia","manchas_hemorragicas","perda_olfato_paladar",
    "dor_garganta","coriza","calafrios","sudorese",
]

# ── Criação ───────────────────────────────────────────────────────────────────
criados = 0
for i, caso in enumerate(CASOS):
    idx = caso.get("_local", i % len(LOCAIS))
    bairro, cidade, estado, lat, lon = LOCAIS[idx]

    dados = {c: bool(caso.get(c, False)) for c in CAMPOS_BOOL}
    dados["estado"] = estado
    dados["cidade"] = cidade
    if caso.get("exposicao_agua_enchente"):
        dados["exposicao_agua_enchente"] = True

    res = classificar(dados, setor="governo", estado=estado)
    grupo         = res.get("grupo", "Indefinido")
    classificacao = res.get("primario", "Inconclusivo")

    lat_j = lat + random.uniform(-0.005, 0.005)
    lon_j = lon + random.uniform(-0.005, 0.005)

    RegistroSintoma.objects.create(
        id_anonimo=uuid.uuid4(),
        empresa=empresa,
        febre=dados["febre"],
        tosse=dados["tosse"],
        dor_corpo=dados["dor_corpo"],
        cansaco=dados["cansaco"],
        falta_ar=dados["falta_ar"],
        dor_cabeca=dados["dor_cabeca"],
        dor_articular=dados["dor_articular"],
        exantema=dados["exantema"],
        conjuntivite=dados["conjuntivite"],
        vomito_nausea=dados["vomito_nausea"],
        diarreia=dados["diarreia"],
        dor_abdominal=dados["dor_abdominal"],
        rigidez_nuca=dados["rigidez_nuca"],
        ictericia=dados["ictericia"],
        manchas_hemorragicas=dados["manchas_hemorragicas"],
        perda_olfato_paladar=dados["perda_olfato_paladar"],
        dor_garganta=dados["dor_garganta"],
        coriza=dados["coriza"],
        calafrios=dados["calafrios"],
        sudorese=dados["sudorese"],
        intensidade_febre="",
        intensidade_articular="",
        exposicao_agua_enchente=dados.get("exposicao_agua_enchente"),
        latitude=lat_j,
        longitude=lon_j,
        pais="Brasil",
        estado=estado,
        cidade=cidade,
        bairro=bairro,
        grupo=grupo,
        classificacao=classificacao,
        ip="203.0.113.1",
        device_id=f"sim-br-{i:03d}",
        confianca=0.95,
        suspeito=False,
    )
    criados += 1
    print(f"  [{criados:02d}] {bairro}/{cidade:15s} → {classificacao}")

# ── Invalida cache ────────────────────────────────────────────────────────────
try:
    clear_panorama_cache()
    print("\n✓ Cache invalidado.")
except Exception as e:
    print(f"\n⚠ Cache: {e}")

print(f"\n✓ {criados} casos criados. Abra o app — o mapa já deve mostrar os focos!")
print(f"\nPara limpar depois:\n  RegistroSintoma.objects.filter(device_id__startswith='sim-br-').delete()")
