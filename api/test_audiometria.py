"""Testes do motor de interpretação de audiometria (NR-07). Função pura, sem banco."""
from django.test import SimpleTestCase

from api.audiometria_interpretacao import (
    classificar_orelha, interpretar, comparar_sequencial,
)


def _normal():
    return {str(f): 10 for f in (500, 1000, 2000, 3000, 4000, 6000, 8000)}


def _pair():
    # entalhe clássico em 4k, recuperando em 8k, fala preservada
    return {"500": 10, "1000": 10, "2000": 15, "3000": 30, "4000": 55, "6000": 40, "8000": 20}


class ClassificarOrelhaTest(SimpleTestCase):
    def test_normal(self):
        r = classificar_orelha(_normal())
        self.assertEqual(r["grau"], "normal")
        self.assertFalse(r["alterada"])
        self.assertFalse(r["sugestivo_pair"])

    def test_media_fala(self):
        r = classificar_orelha(_normal())
        self.assertEqual(r["media_fala"], 10.0)

    def test_pair_detectado(self):
        r = classificar_orelha(_pair())
        self.assertTrue(r["sugestivo_pair"])
        self.assertTrue(r["alterada"])

    def test_perda_leve_plana_nao_e_pair(self):
        # perda plana leve (todas ~35) sem entalhe → alterada mas não PAIR
        lim = {str(f): 35 for f in (500, 1000, 2000, 3000, 4000, 6000, 8000)}
        r = classificar_orelha(lim)
        self.assertFalse(r["sugestivo_pair"])
        self.assertTrue(r["alterada"])

    def test_dados_ausentes(self):
        r = classificar_orelha({})
        self.assertIsNone(r["media_fala"])
        self.assertEqual(r["grau"], "indeterminado")


class InterpretarTest(SimpleTestCase):
    def test_normal_bilateral(self):
        r = interpretar({"od_aerea": _normal(), "oe_aerea": _normal()})
        self.assertEqual(r["classificacao"], "normal")
        self.assertFalse(r["alterada"])

    def test_pair_unilateral(self):
        r = interpretar({"od_aerea": _pair(), "oe_aerea": _normal()})
        self.assertEqual(r["classificacao"], "sugestivo_pair")
        self.assertTrue(r["sugestivo_pair"])
        self.assertTrue(r["alterada"])


class ComparacaoSequencialTest(SimpleTestCase):
    def test_referencia_sem_anterior(self):
        r = comparar_sequencial({"od_aerea": _normal(), "oe_aerea": _normal()}, None)
        self.assertEqual(r["classificacao_sequencial"], "referencia")
        self.assertFalse(r["reteste_indicado"])

    def test_estavel(self):
        base = {"od_aerea": _normal(), "oe_aerea": _normal()}
        r = comparar_sequencial(base, base)
        self.assertEqual(r["classificacao_sequencial"], "estavel")
        self.assertFalse(r["reteste_indicado"])

    def test_agravamento_dispara_reteste(self):
        anterior = {"od_aerea": _pair(), "oe_aerea": _normal()}
        # piora >=10 dB nas altas da OD
        atual = {"od_aerea": {"500": 10, "1000": 10, "2000": 15, "3000": 45, "4000": 70, "6000": 55, "8000": 20},
                 "oe_aerea": _normal()}
        r = comparar_sequencial(atual, anterior)
        self.assertIn(r["classificacao_sequencial"], ("agravamento", "desencadeamento"))
        self.assertTrue(r["reteste_indicado"])

    def test_desencadeamento_de_normal_para_alterada(self):
        anterior = {"od_aerea": _normal(), "oe_aerea": _normal()}
        atual = {"od_aerea": _pair(), "oe_aerea": _normal()}
        r = comparar_sequencial(atual, anterior)
        self.assertEqual(r["classificacao_sequencial"], "desencadeamento")
        self.assertTrue(r["novo_caso"])

    def test_melhora(self):
        anterior = {"od_aerea": {"3000": 40, "4000": 50, "6000": 45},
                    "oe_aerea": {"3000": 40, "4000": 50, "6000": 45}}
        atual = {"od_aerea": {"3000": 20, "4000": 25, "6000": 20},
                 "oe_aerea": {"3000": 20, "4000": 25, "6000": 20}}
        r = comparar_sequencial(atual, anterior)
        self.assertEqual(r["classificacao_sequencial"], "melhora")
