import os
import django
import time
import uuid
import random

# 🔥 CONFIGURA DJANGO
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from api.models import RegistroSintoma, Empresa

empresa = Empresa.objects.first()

cidades = [
    ("São Paulo", "SP", -23.55, -46.63),
    ("Rio de Janeiro", "RJ", -22.90, -43.20),
    ("Belo Horizonte", "MG", -19.92, -43.94),
    ("Salvador", "BA", -12.97, -38.50),
    ("Brasília", "DF", -15.79, -47.88),
    ("Curitiba", "PR", -25.42, -49.27),
    ("Fortaleza", "CE", -3.73, -38.52),
    ("Manaus", "AM", -3.10, -60.02),
    ("Recife", "PE", -8.05, -34.88),
    ("Porto Alegre", "RS", -30.03, -51.23)
]

print("🔥 Iniciando simulação tipo pandemia...")

for ciclo in range(60):

    print(f"📊 Ciclo {ciclo+1}")

    for cidade, estado, lat, lon in cidades:

        quantidade = random.randint(20, 60 + ciclo)

        for i in range(quantidade):
            RegistroSintoma.objects.create(
                id_anonimo=uuid.uuid4(),
                febre=True,
                tosse=random.choice([True, False]),
                dor_corpo=True,
                cansaco=True,
                falta_ar=random.choice([True, False]),
                latitude=lat,
                longitude=lon,
                pais="Brasil",
                estado=estado,
                cidade=cidade,
                empresa=empresa
            )

    time.sleep(10)  # ⏱️ 10 segundos = 1 "mês"

print("🔥 Simulação finalizada")