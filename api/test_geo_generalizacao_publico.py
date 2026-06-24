"""
Pedido do usuário ao revisar o app de população (app_saude): o app envia GPS
exato (até erro de 500m, normalmente 5-20m em área aberta — ver
LocationService) e isso era salvo sem alteração em RegistroSintoma, criando
risco real de reidentificação ("o vizinho vê de qual casa o sinal saiu").

Corrigido: api/utils_geo.py::generalizar_coordenada arredonda lat/lon para o
centro de uma célula de grade de ~200m antes de persistir, aplicado em
registrar_sintoma_publico (api/views.py) logo após a geocodificação (que usa
a coordenada precisa original — só o dado armazenado é generalizado).
"""
from django.test import TestCase

from .models import RegistroSintoma
from .utils_geo import generalizar_coordenada


class GeneralizarCoordenadaTests(TestCase):
    def test_arredonda_para_grade_de_200m(self):
        lat, lon = generalizar_coordenada(-22.9068, -43.1729, raio_metros=200)
        self.assertNotEqual((lat, lon), (-22.9068, -43.1729))

    def test_pontos_dentro_da_mesma_celula_colapsam(self):
        # Deslocamento minúsculo (~3m) garante ficar na mesma célula de 200m,
        # longe de qualquer borda de grade — diferente de pontos a ~10m que
        # podem cair em células vizinhas se estiverem perto da borda.
        a = generalizar_coordenada(-22.970834, -43.183532, raio_metros=200)
        b = generalizar_coordenada(-22.970837, -43.183535, raio_metros=200)
        # delta pequeno (~1m) absorve ruído de arredondamento de ponto
        # flutuante na 6a casa decimal — irrelevante para fins de privacidade.
        self.assertAlmostEqual(a[0], b[0], delta=1e-5)
        self.assertAlmostEqual(a[1], b[1], delta=1e-5)

    def test_desvio_da_coordenada_real_e_limitado(self):
        # Garantia de privacidade: o ponto generalizado nunca se afasta mais
        # que a diagonal da célula (~141m para uma grade de 200m).
        lat, lon = -22.970834, -43.183532
        lat_g, lon_g = generalizar_coordenada(lat, lon, raio_metros=200)
        self.assertAlmostEqual(lat, lat_g, delta=0.0025)
        self.assertAlmostEqual(lon, lon_g, delta=0.0025)

    def test_e_deterministico(self):
        a = generalizar_coordenada(-22.970834, -43.183532, raio_metros=200)
        b = generalizar_coordenada(-22.970834, -43.183532, raio_metros=200)
        self.assertEqual(a, b)


class RegistrarSintomaPublicoGeneralizaCoordenadaTests(TestCase):
    def test_envio_publico_nao_persiste_coordenada_exata(self):
        lat_exata, lon_exata = -22.970834, -43.183532
        resp = self.client.post(
            "/api/public/registrar",
            data={
                "febre": True,
                "latitude": lat_exata,
                "longitude": lon_exata,
                "location_source": "current",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        registro = RegistroSintoma.objects.latest("data_registro")
        self.assertNotEqual(registro.latitude, lat_exata)
        self.assertNotEqual(registro.longitude, lon_exata)
        # ainda deve estar na vizinhança (a generalização é de ~200m, não de km)
        self.assertAlmostEqual(registro.latitude, lat_exata, delta=0.0025)
        self.assertAlmostEqual(registro.longitude, lon_exata, delta=0.0025)
