"""Testes do motor de interpretação de espirometria (NR-07). Função pura."""
from django.test import SimpleTestCase

from api.espirometria_interpretacao import interpretar, comparar_sequencial


class InterpretarTest(SimpleTestCase):
    def test_normal(self):
        r = interpretar({"cvf": 5.0, "vef1": 4.0, "cvf_prev": 95, "vef1_prev": 92})
        self.assertEqual(r["padrao"], "normal")
        self.assertFalse(r["alterada"])

    def test_obstrutivo(self):
        # VEF1/CVF = 3.0/5.0 = 0.60 < 0.70
        r = interpretar({"cvf": 5.0, "vef1": 3.0, "cvf_prev": 95, "vef1_prev": 65})
        self.assertEqual(r["padrao"], "obstrutivo")
        self.assertTrue(r["obstrucao"])
        self.assertEqual(r["grau"], "moderado")

    def test_restritivo(self):
        # relação preservada (0.85) mas CVF 70% do previsto
        r = interpretar({"cvf": 3.0, "vef1": 2.55, "cvf_prev": 70, "vef1_prev": 72})
        self.assertEqual(r["padrao"], "restritivo")
        self.assertTrue(r["reducao_volume"])

    def test_misto(self):
        r = interpretar({"cvf": 3.0, "vef1": 1.8, "cvf_prev": 70, "vef1_prev": 55})
        self.assertEqual(r["padrao"], "misto")

    def test_indice_percentual_normalizado(self):
        # vef1_cvf informado como 65 (%) deve virar 0.65
        r = interpretar({"vef1_cvf": 65, "cvf_prev": 90, "vef1_prev": 70})
        self.assertEqual(r["padrao"], "obstrutivo")

    def test_indeterminado(self):
        r = interpretar({})
        self.assertEqual(r["padrao"], "indeterminado")


class SequencialTest(SimpleTestCase):
    def test_referencia(self):
        r = comparar_sequencial({"vef1_prev": 90}, None)
        self.assertEqual(r["classificacao_sequencial"], "referencia")

    def test_declinio(self):
        r = comparar_sequencial({"vef1_prev": 70}, {"vef1_prev": 85})
        self.assertEqual(r["classificacao_sequencial"], "declinio")
        self.assertTrue(r["declinio_indicado"])

    def test_estavel(self):
        r = comparar_sequencial({"vef1_prev": 88}, {"vef1_prev": 90})
        self.assertEqual(r["classificacao_sequencial"], "estavel")

    def test_melhora(self):
        r = comparar_sequencial({"vef1_prev": 92}, {"vef1_prev": 80})
        self.assertEqual(r["classificacao_sequencial"], "melhora")
