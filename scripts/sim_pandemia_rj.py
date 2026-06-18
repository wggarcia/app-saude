"""
Simulação de PANDEMIA no Rio de Janeiro — 120 casos concentrados.
Dengue em surto + gastro + gripe para acionar alertas no mapa.

Rodar no shell do Render:
    curl -s https://raw.githubusercontent.com/wggarcia/app-saude/sim/pandemia/scripts/sim_pandemia_rj.py > /tmp/pan.py
    python manage.py shell < /tmp/pan.py

Limpar depois:
    RegistroSintoma.objects.filter(device_id__startswith='pan_').delete()
"""

import uuid, random
from django.contrib.auth.hashers import make_password
from api.models import Empresa, RegistroSintoma
from api.middleware import _rls_set_empresa as _set_rls
from api.classificador_doencas import classificar
from api.epidemiologia import clear_panorama_cache

random.seed(77)

empresa, _ = Empresa.objects.get_or_create(
    email="populacao@soluscrt.com",
    defaults={
        "nome": "SolusCRT Populacao",
        "senha": make_password("publico_app"),
        "ativo": True, "plano": "publico",
        "pacote_codigo": "governo_estado",
        "max_usuarios": 1000, "max_dispositivos": 1000,
    },
)
_set_rls(empresa.id)

BAIRROS = [
    ("Copacabana",      "Rio de Janeiro", "Rio de Janeiro", -22.9711, -43.1823),
    ("Ipanema",         "Rio de Janeiro", "Rio de Janeiro", -22.9838, -43.2096),
    ("Botafogo",        "Rio de Janeiro", "Rio de Janeiro", -22.9444, -43.1867),
    ("Centro",          "Rio de Janeiro", "Rio de Janeiro", -22.9068, -43.1729),
    ("Tijuca",          "Rio de Janeiro", "Rio de Janeiro", -22.9274, -43.2348),
    ("Méier",           "Rio de Janeiro", "Rio de Janeiro", -22.8939, -43.2769),
    ("Madureira",       "Rio de Janeiro", "Rio de Janeiro", -22.8736, -43.3395),
    ("Penha",           "Rio de Janeiro", "Rio de Janeiro", -22.8369, -43.2705),
    ("Barra da Tijuca", "Rio de Janeiro", "Rio de Janeiro", -23.0000, -43.3654),
    ("Bangu",           "Rio de Janeiro", "Rio de Janeiro", -22.8774, -43.4636),
    ("Nova Iguaçu",     "Nova Iguaçu",    "RJ", -22.7594, -43.4511),
    ("Duque de Caxias", "Duque de Caxias","RJ", -22.7856, -43.3116),
    ("Icaraí",          "Niterói",        "RJ", -22.8897, -43.1286),
    ("São Gonçalo",     "São Gonçalo",    "RJ", -22.8268, -43.0549),
]

F = ["febre","tosse","dor_corpo","cansaco","falta_ar","dor_cabeca","dor_articular",
     "exantema","conjuntivite","vomito_nausea","diarreia","dor_abdominal",
     "rigidez_nuca","ictericia","manchas_hemorragicas","perda_olfato_paladar",
     "dor_garganta","coriza","calafrios","sudorese"]

# 80 Dengue + 20 Chikungunya + 10 Gastroenterite + 10 Gripe = 120
LOTES = [
    # (qtd, sintomas, variante_label)
    (40, {"febre":True,"dor_articular":True,"dor_cabeca":True,"cansaco":True,"dor_corpo":True},                          "dengue_A"),
    (20, {"febre":True,"dor_articular":True,"dor_cabeca":True,"cansaco":True,"exantema":True},                           "dengue_B"),
    (20, {"febre":True,"dor_articular":True,"exantema":True,"conjuntivite":True,"cansaco":True},                         "chikungunya"),
    (10, {"febre":True,"dor_articular":True,"dor_cabeca":True,"cansaco":True,"dor_corpo":True,"manchas_hemorragicas":True}, "dengue_grave"),
    (10, {"diarreia":True,"dor_abdominal":True,"vomito_nausea":True,"cansaco":True},                                     "gastro"),
    (10, {"febre":True,"tosse":True,"dor_corpo":True,"cansaco":True,"dor_cabeca":True},                                  "gripe"),
    (10, {"febre":True,"dor_corpo":True,"calafrios":True,"cansaco":True,"exposicao_agua_enchente":True},                 "lepto"),
]

n = 0
for qtd, sint, label in LOTES:
    for i in range(qtd):
        b, ci, es, la, lo = BAIRROS[(n) % len(BAIRROS)]
        d = {f: bool(sint.get(f, False)) for f in F}
        d["estado"] = es; d["cidade"] = ci
        if sint.get("exposicao_agua_enchente"):
            d["exposicao_agua_enchente"] = True
        r = classificar(d, setor="governo", estado=es)
        RegistroSintoma.objects.create(
            id_anonimo=uuid.uuid4(), empresa=empresa,
            **{f: d[f] for f in F},
            intensidade_febre="", intensidade_articular="",
            exposicao_agua_enchente=d.get("exposicao_agua_enchente"),
            latitude=la + random.uniform(-0.012, 0.012),
            longitude=lo + random.uniform(-0.012, 0.012),
            pais="Brasil", estado=es, cidade=ci, bairro=b,
            grupo=r.get("grupo", "Indefinido"),
            classificacao=r.get("primario", "Inconclusivo"),
            ip="203.0.113.1",
            device_id=f"pan_{n:03d}",
            confianca=0.95, suspeito=False,
        )
        n += 1
    print(f"  ✓ {qtd}x {label} criados")

try:
    clear_panorama_cache()
    print("\n✓ Cache invalidado.")
except Exception as e:
    print(f"\n⚠ Cache: {e}")

print(f"\n✓ {n} casos de surto criados no RJ!")
print("Limpar: RegistroSintoma.objects.filter(device_id__startswith='pan_').delete()")
