import os
import django
import random
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from api.models import RegistroSintoma, Empresa

empresa = Empresa.objects.first()

# 🌎 CIDADES MAIS DISTRIBUÍDAS
cidades = [
    ("São Paulo", "SP", -23.55, -46.63),
    ("Guarulhos", "SP", -23.45, -46.53),
    ("Campinas", "SP", -22.90, -47.06),

    ("Rio de Janeiro", "RJ", -22.90, -43.20),
    ("Niterói", "RJ", -22.88, -43.10),
    ("Duque de Caxias", "RJ", -22.78, -43.30),

    ("Belo Horizonte", "MG", -19.92, -43.94),
    ("Uberlândia", "MG", -18.91, -48.27),

    ("Salvador", "BA", -12.97, -38.50),
    ("Feira de Santana", "BA", -12.25, -38.96),

    ("Porto Alegre", "RS", -30.03, -51.23),
    ("Caxias do Sul", "RS", -29.17, -51.18),
]

TOTAL = 5000

print("🔥 Iniciando simulação REALISTA...\n")

for i in range(TOTAL):

    # 🔥 CRIAR SURTO EM UMA REGIÃO (70% chance)
    if random.random() < 0.7:
        cidade, estado, lat, lon = random.choice([
            ("Rio de Janeiro", "RJ", -22.90, -43.20),
            ("São Paulo", "SP", -23.55, -46.63),
        ])
    else:
        cidade, estado, lat, lon = random.choice(cidades)

    # 🌍 ESPALHAR MAIS OS PONTOS (REALISTA)
    latitude = lat + random.uniform(-0.2, 0.2)
    longitude = lon + random.uniform(-0.2, 0.2)

    RegistroSintoma.objects.create(
        id_anonimo=str(uuid.uuid4()),

        febre=random.random() < 0.6,
        tosse=random.random() < 0.7,
        dor_corpo=random.random() < 0.5,
        cansaco=random.random() < 0.5,
        falta_ar=random.random() < 0.3,

        latitude=latitude,
        longitude=longitude,

        pais="Brasil",
        estado=estado,
        cidade=cidade,
        bairro="Centro",

        empresa=empresa
    )

    if i % 500 == 0:
        print(f"📊 {i} registros criados...")

print("\n✅ SIMULAÇÃO FINALIZADA COM SUCESSO")