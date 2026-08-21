"""
TISS Operadora — recepção de lote.

Round-trip real: o gerador do lado PRESTADOR (Hospital, gerar_xml_tiss_3_05)
produz o XML → o lado OPERADORA (importar_lote_tiss) parseia e reconstrói o
lote com os mesmos valores. Depois: motor de glosa + IA de risco + geração do
Demonstrativo de Análise de Conta (retorno).
"""
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.test import TestCase

from .models import (
    Empresa, GuiaTISS, LoteTISSRecebido, ItemContaTISS, PrestadorPlanoSaude,
)
from .views_hospital_tiss import gerar_xml_tiss_3_05
from .views_plano_tiss_recepcao import (
    importar_lote_tiss, processar_lote, gerar_demonstrativo_retorno,
)


def _empresa(email, nome="Operadora TISS"):
    return Empresa.objects.create(
        nome=nome, email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


def _guia(empresa, procedimentos, **kw):
    return GuiaTISS.objects.create(
        empresa=empresa, tipo="sp_sadt", numero_guia=kw.get("numero_guia", "G-001"),
        operadora_codigo="123456", operadora_nome="SoloCRT Saúde",
        beneficiario_nome=kw.get("ben", "Maria Souza"),
        beneficiario_carteirinha=kw.get("cart", "00099988877"),
        cid10=kw.get("cid", "A90"),  # dengue
        procedimentos=procedimentos,
        valor_apresentado=kw.get("valor", Decimal("0")),
    )


class TISSRecepcaoRoundTripTests(TestCase):
    def setUp(self):
        self.op = _empresa("op-tiss@example.com")

    def test_round_trip_import(self):
        """XML gerado pelo Hospital volta a virar lote+itens com os mesmos valores."""
        procs = [
            {"tabela": "22", "codigo": "40304361", "descricao": "Hemograma completo",
             "quantidade": 1, "valor_unitario": 18.50},
            {"tabela": "22", "codigo": "40302040", "descricao": "Sorologia dengue",
             "quantidade": 2, "valor_unitario": 45.00},
        ]
        guia = _guia(self.op, procs)
        xml = gerar_xml_tiss_3_05(guia, self.op)

        lote = importar_lote_tiss(xml, self.op)
        self.assertEqual(lote.itens.count(), 2)
        self.assertEqual(lote.beneficiario_nome, "Maria Souza")
        self.assertEqual(lote.cid10, "A90")
        # 18.50 + 2*45.00 = 108.50
        self.assertEqual(lote.valor_apresentado, Decimal("108.50"))
        item2 = lote.itens.get(codigo_procedimento="40302040")
        self.assertEqual(item2.quantidade, Decimal("2.00"))
        self.assertEqual(item2.valor_apresentado, Decimal("90.00"))

    def test_glosa_quantidade_e_duplicidade(self):
        procs = [
            {"tabela": "22", "codigo": "40304361", "descricao": "Hemograma",
             "quantidade": 1, "valor_unitario": 20.00},
            {"tabela": "22", "codigo": "40304361", "descricao": "Hemograma repetido",
             "quantidade": 1, "valor_unitario": 20.00},  # duplicidade
        ]
        guia = _guia(self.op, procs)
        lote = processar_lote(importar_lote_tiss(gerar_xml_tiss_3_05(guia, self.op), self.op))
        self.assertEqual(lote.status, "processado")
        # segundo item glosado por duplicidade
        glosados = lote.itens.filter(glosado=True)
        self.assertEqual(glosados.count(), 1)
        self.assertEqual(glosados.first().codigo_glosa, "1403")
        self.assertEqual(lote.valor_glosado, Decimal("20.00"))
        self.assertEqual(lote.valor_liberado, Decimal("20.00"))

    def test_glosa_prestador_nao_credenciado(self):
        prest = PrestadorPlanoSaude.objects.create(
            empresa=self.op, nome_fantasia="Lab X", codigo_rede="LABX",
            status=PrestadorPlanoSaude.STATUS_SUSPENSO,
        )
        procs = [{"tabela": "22", "codigo": "40304361", "descricao": "Exame",
                  "quantidade": 1, "valor_unitario": 100.00}]
        guia = _guia(self.op, procs)
        xml = gerar_xml_tiss_3_05(guia, self.op)
        # força o código do prestador no XML a casar com o cadastro suspenso
        xml = xml.replace("<ans:codigoPrestadorNaOperadora></ans:codigoPrestadorNaOperadora>",
                          "<ans:codigoPrestadorNaOperadora>LABX</ans:codigoPrestadorNaOperadora>")
        lote = importar_lote_tiss(xml, self.op)
        # se o replace não achou (empresa tem cnpj), seta manualmente p/ testar a regra
        if lote.prestador is None:
            lote.prestador = prest
            lote.save(update_fields=["prestador"])
        processar_lote(lote)
        if lote.prestador:
            self.assertEqual(lote.valor_glosado, Decimal("100.00"))
            self.assertEqual(lote.itens.first().codigo_glosa, "1401")

    def test_ia_score_e_parecer_presentes(self):
        procs = [{"tabela": "22", "codigo": "40304361", "descricao": "Exame",
                  "quantidade": 1, "valor_unitario": 30.00}]
        lote = processar_lote(importar_lote_tiss(
            gerar_xml_tiss_3_05(_guia(self.op, procs), self.op), self.op))
        self.assertIsInstance(lote.ia_score_glosa, int)
        self.assertTrue(0 <= lote.ia_score_glosa <= 100)
        self.assertTrue(lote.ia_parecer)

    def test_demonstrativo_retorno_xml(self):
        procs = [
            {"tabela": "22", "codigo": "40304361", "descricao": "A",
             "quantidade": 1, "valor_unitario": 50.00},
            {"tabela": "22", "codigo": "40304361", "descricao": "A dup",
             "quantidade": 1, "valor_unitario": 50.00},
        ]
        lote = processar_lote(importar_lote_tiss(
            gerar_xml_tiss_3_05(_guia(self.op, procs), self.op), self.op))
        xml = gerar_demonstrativo_retorno(lote)
        self.assertIn("DEMONSTRATIVO_ANALISE_CONTA", xml)
        self.assertIn("valorGlosaLote", xml)
        self.assertIn("1403", xml)  # código de glosa aparece
        self.assertIn("<ans:hash>", xml)
