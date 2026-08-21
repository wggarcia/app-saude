"""
Motor de coparticipação — cálculo com teto ANS (RN 507, 40%), isenção
preventiva, teto mensal do plano, auditoria de conformidade e consolidação.
"""
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.test import TestCase

from .models import (
    BeneficiarioPlano, CoparticipacaoRegra, Empresa, EventoCoparticipacao,
    FaturamentoBeneficiario, PlanoSaude,
)
from .views_plano_coparticipacao import (
    auditar_regras_ans, calcular_coparticipacao, consolidar_competencia,
    registrar_evento,
)


def _empresa(email):
    return Empresa.objects.create(
        nome="Operadora Copart", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class CoparticipacaoTests(TestCase):
    def setUp(self):
        self.op = _empresa("copart@example.com")
        self.plano = PlanoSaude.objects.create(empresa=self.op, nome="Plano Copart")
        self.benef = BeneficiarioPlano.objects.create(plano=self.plano, nome="Fulano")

    def test_percentual_simples(self):
        regra = CoparticipacaoRegra(plano=self.plano, tipo_atendimento="consulta",
                                    percentual=Decimal("30"), ativo=True)
        c = calcular_coparticipacao(regra, Decimal("100.00"), False, Decimal("0"))
        self.assertEqual(c["valor"], Decimal("30.00"))
        self.assertFalse(c["isento"])

    def test_teto_ans_40(self):
        # regra de 30% mas valor fixo alto não pode ultrapassar 40% do procedimento
        regra = CoparticipacaoRegra(plano=self.plano, tipo_atendimento="exame",
                                    percentual=Decimal("0"), valor_fixo=Decimal("80.00"), ativo=True)
        c = calcular_coparticipacao(regra, Decimal("100.00"), False, Decimal("0"))
        self.assertEqual(c["valor"], Decimal("40.00"))  # capado em 40% de 100
        self.assertIn("teto ANS", c["motivo"])

    def test_preventivo_isento(self):
        regra = CoparticipacaoRegra(plano=self.plano, tipo_atendimento="consulta",
                                    percentual=Decimal("30"), ativo=True)
        c = calcular_coparticipacao(regra, Decimal("200.00"), True, Decimal("0"))
        self.assertEqual(c["valor"], Decimal("0.00"))
        self.assertTrue(c["isento"])

    def test_sem_regra_sem_cobranca(self):
        c = calcular_coparticipacao(None, Decimal("100.00"), False, Decimal("0"))
        self.assertEqual(c["valor"], Decimal("0.00"))
        self.assertTrue(c["isento"])

    def test_teto_mensal(self):
        regra = CoparticipacaoRegra(plano=self.plano, tipo_atendimento="exame",
                                    percentual=Decimal("30"), teto_mensal=Decimal("50.00"), ativo=True)
        # já acumulou 40 no mês; novo evento de 30% de 100 = 30, mas só cabem 10
        c = calcular_coparticipacao(regra, Decimal("100.00"), False, Decimal("40.00"))
        self.assertEqual(c["valor"], Decimal("10.00"))
        self.assertIn("teto mensal", c["motivo"].lower())

    def test_registrar_evento_persiste_e_respeita_teto_mensal(self):
        CoparticipacaoRegra.objects.create(plano=self.plano, tipo_atendimento="consulta",
                                           percentual=Decimal("50"), teto_mensal=Decimal("60.00"), ativo=True)
        # nota: 50% mas ANS capa em 40% → cada consulta de 100 = 40
        e1 = registrar_evento(self.op, self.benef, "consulta", Decimal("100.00"), competencia="2026-08")
        e2 = registrar_evento(self.op, self.benef, "consulta", Decimal("100.00"), competencia="2026-08")
        self.assertEqual(e1.valor_coparticipacao, Decimal("40.00"))
        # segundo: acumulado 40, teto 60 → só 20
        self.assertEqual(e2.valor_coparticipacao, Decimal("20.00"))

    def test_consolidar_gera_fatura(self):
        CoparticipacaoRegra.objects.create(plano=self.plano, tipo_atendimento="exame",
                                           percentual=Decimal("20"), ativo=True)
        registrar_evento(self.op, self.benef, "exame", Decimal("100.00"), competencia="2026-08")
        registrar_evento(self.op, self.benef, "exame", Decimal("50.00"), competencia="2026-08")
        fatura = consolidar_competencia(self.op, self.benef, "2026-08")
        self.assertEqual(fatura.valor_coparticipacao, Decimal("30.00"))  # 20 + 10
        self.assertTrue(FaturamentoBeneficiario.objects.filter(
            beneficiario=self.benef, competencia="2026-08").exists())

    def test_auditoria_ans_detecta_violacao(self):
        CoparticipacaoRegra.objects.create(plano=self.plano, tipo_atendimento="consulta",
                                           percentual=Decimal("50"), ativo=True)  # > 40%
        achados = auditar_regras_ans(self.op)
        self.assertEqual(len(achados), 1)
        self.assertIn("40%", achados[0]["problemas"][0])
