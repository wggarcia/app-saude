import json
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.test import Client
from django.utils import timezone

from api.models import RegistroSintoma


REGIOES = [
    {
        "cidade": "São Paulo",
        "estado": "São Paulo",
        "bairro": "Pinheiros",
        "lat": -23.5614,
        "lon": -46.7016,
        "peso": 0.16,
        "perfil": "respiratorio",
    },
    {
        "cidade": "Rio de Janeiro",
        "estado": "Rio de Janeiro",
        "bairro": "Centro",
        "lat": -22.9068,
        "lon": -43.1729,
        "peso": 0.14,
        "perfil": "respiratorio",
    },
    {
        "cidade": "Recife",
        "estado": "Pernambuco",
        "bairro": "Boa Vista",
        "lat": -8.0476,
        "lon": -34.8770,
        "peso": 0.15,
        "perfil": "arbovirose",
    },
    {
        "cidade": "Salvador",
        "estado": "Bahia",
        "bairro": "Centro",
        "lat": -12.9777,
        "lon": -38.5016,
        "peso": 0.12,
        "perfil": "arbovirose",
    },
    {
        "cidade": "Belo Horizonte",
        "estado": "Minas Gerais",
        "bairro": "Centro",
        "lat": -19.9167,
        "lon": -43.9345,
        "peso": 0.11,
        "perfil": "misto",
    },
    {
        "cidade": "Manaus",
        "estado": "Amazonas",
        "bairro": "Centro",
        "lat": -3.1190,
        "lon": -60.0217,
        "peso": 0.10,
        "perfil": "respiratorio",
    },
    {
        "cidade": "Curitiba",
        "estado": "Parana",
        "bairro": "Centro",
        "lat": -25.4284,
        "lon": -49.2733,
        "peso": 0.08,
        "perfil": "misto",
    },
    {
        "cidade": "Fortaleza",
        "estado": "Ceara",
        "bairro": "Centro",
        "lat": -3.7319,
        "lon": -38.5267,
        "peso": 0.08,
        "perfil": "arbovirose",
    },
    {
        "cidade": "Porto Alegre",
        "estado": "Rio Grande do Sul",
        "bairro": "Centro Historico",
        "lat": -30.0346,
        "lon": -51.2177,
        "peso": 0.06,
        "perfil": "respiratorio",
    },
]


def sintomas_por_perfil(perfil):
    if perfil == "respiratorio":
        return {
            "febre": random.random() < 0.58,
            "tosse": random.random() < 0.86,
            "dor_corpo": random.random() < 0.35,
            "cansaco": random.random() < 0.52,
            "falta_ar": random.random() < 0.18,
        }
    if perfil == "arbovirose":
        return {
            "febre": random.random() < 0.82,
            "tosse": random.random() < 0.08,
            "dor_corpo": random.random() < 0.88,
            "cansaco": random.random() < 0.62,
            "falta_ar": random.random() < 0.03,
        }
    return {
        "febre": random.random() < 0.55,
        "tosse": random.random() < 0.42,
        "dor_corpo": random.random() < 0.46,
        "cansaco": random.random() < 0.48,
        "falta_ar": random.random() < 0.08,
    }


class Command(BaseCommand):
    help = "Simula envios populacionais pelo endpoint publico em varias regioes do Brasil."

    def add_arguments(self, parser):
        parser.add_argument("--total", type=int, default=900)
        parser.add_argument(
            "--cenario",
            choices=["queda", "crescimento", "estavel"],
            default="queda",
            help="Distribuicao temporal para testar decaimento ou crescimento dos focos.",
        )
        parser.add_argument("--seed", type=int, default=42)

    def _dia_para_cenario(self, cenario):
        if cenario == "crescimento":
            return random.choices([6, 5, 4, 3, 2, 1, 0], weights=[2, 3, 5, 8, 12, 18, 28])[0]
        if cenario == "estavel":
            return random.choice([6, 5, 4, 3, 2, 1, 0])
        return random.choices([6, 5, 4, 3, 2, 1, 0], weights=[28, 22, 18, 12, 7, 4, 2])[0]

    def handle(self, *args, **options):
        random.seed(options["seed"])
        total = options["total"]
        cenario = options["cenario"]
        client = Client(HTTP_HOST="127.0.0.1:8000")
        enviados = 0
        bloqueados = 0
        agora = timezone.now()

        regioes = random.choices(REGIOES, weights=[item["peso"] for item in REGIOES], k=total)
        for index, regiao in enumerate(regioes):
            sintomas = sintomas_por_perfil(regiao["perfil"])
            payload = {
                **sintomas,
                "latitude": regiao["lat"] + random.uniform(-0.018, 0.018),
                "longitude": regiao["lon"] + random.uniform(-0.018, 0.018),
                "location_source": "current",
                "bairro": regiao["bairro"],
                "cidade": regiao["cidade"],
                "estado": regiao["estado"],
                "pais": "Brasil",
            }
            response = client.post(
                "/api/public/registrar",
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_DEVICE_ID=f"sim-br-{cenario}-{index}",
                HTTP_X_FORWARDED_FOR=f"10.{index // 65000}.{(index // 255) % 255}.{index % 255}",
                HTTP_X_SOLUS_SIMULATION="true",
            )
            if response.status_code != 200:
                bloqueados += 1
                continue

            data = response.json()
            if data.get("registro_id"):
                dias_atras = self._dia_para_cenario(cenario)
                RegistroSintoma.objects.filter(id_anonimo=data["registro_id"]).update(
                    data_registro=agora - timedelta(days=dias_atras, hours=random.randint(0, 22))
                )
                enviados += 1
            else:
                bloqueados += 1

        self.stdout.write(self.style.SUCCESS(
            f"Simulacao concluida: enviados={enviados}, bloqueados={bloqueados}, cenario={cenario}"
        ))
