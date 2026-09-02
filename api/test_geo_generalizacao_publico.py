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
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from .models import Empresa, RegistroSintoma
from .utils_geo import (
    generalizar_coordenada,
    geocode_externo_pendente,
    obter_endereco,
    refinar_geo_registro,
)


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


class RefinoGeoBackgroundTests(TestCase):
    """Geocodificação externa (Nominatim) tirada do caminho síncrono do envio:
    o envio resolve a região só por cache+base local; coordenadas remotas são
    refinadas depois pela fila (refinar_geo_registro)."""

    def setUp(self):
        cache.clear()  # geocode_externo_pendente consulta o cache

    def test_geocode_externo_pendente_perto_e_longe(self):
        # Perto de ponto conhecido (Rio) → base local resolve, sem pendência.
        self.assertFalse(geocode_externo_pendente(-22.9068, -43.1729))
        # Remoto (meio do Atlântico) → só o Nominatim resolveria → pendente.
        self.assertTrue(geocode_externo_pendente(0.0, -30.0))

    def test_envio_sincrono_nao_chama_nominatim(self):
        # No caminho do envio (permitir_externo=False), mesmo coordenada remota
        # NÃO pode disparar a chamada externa de 3s que prende um worker.
        with mock.patch("api.utils_geo.requests.get") as m:
            geo = obter_endereco(0.0, -30.0, permitir_externo=False)
        m.assert_not_called()
        self.assertIn("estado", geo)  # retorna aproximação local, não vazio

    def test_refinar_geo_registro_atualiza_regiao(self):
        emp = Empresa.objects.create(nome="Pop", email="populacao@solocrt.com", senha="x", ativo=True)
        reg = RegistroSintoma.objects.create(
            empresa=emp, febre=True,
            latitude=-3.2, longitude=-52.2,  # remoto (Altamira/PA)
            estado="Aproximado", cidade="Cidade Aproximada", bairro="Centro",
        )
        refino = {"estado": "Pará", "cidade": "Altamira", "bairro": "Centro", "pais": "Brasil"}
        with mock.patch("api.utils_geo.obter_endereco", return_value=refino):
            refinar_geo_registro(reg.pk)
        reg.refresh_from_db()
        self.assertEqual(reg.estado, "Pará")
        self.assertEqual(reg.cidade, "Altamira")
