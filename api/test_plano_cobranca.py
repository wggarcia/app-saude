"""
Cobrança de mensalidade — PIX (EMV+CRC16), boleto Febraban (DVs) e
round-trip CNAB 240 remessa → retorno → baixa (conciliação).
"""
from datetime import date, timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    BeneficiarioPlano, Empresa, FaturamentoBeneficiario, PlanoSaude,
)
from .views_plano_cobranca import (
    _crc16, _mod10, _mod11_barcode, conciliar_retorno_cnab, emitir_cobranca,
    gerar_boleto, gerar_faturas_competencia, gerar_pix_copia_cola,
    gerar_remessa_cnab240, gerar_retorno_cnab240,
)


def _empresa(email):
    return Empresa.objects.create(
        nome="Operadora Cobranca", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


def _client_for(empresa):
    c = Client()
    payload = {"empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
               "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1)}
    c.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return c


class CobrancaTests(TestCase):
    def setUp(self):
        self.op = _empresa("cobranca@example.com")
        self.plano = PlanoSaude.objects.create(empresa=self.op, nome="Plano Cob")
        self.titular = BeneficiarioPlano.objects.create(
            plano=self.plano, nome="Titular Silva", situacao="ativo",
            tipo_vinculo="titular", valor_mensalidade=Decimal("300.00"))
        self.dep = BeneficiarioPlano.objects.create(
            plano=self.plano, nome="Dep Silva", situacao="ativo",
            tipo_vinculo="dependente", titular=self.titular, valor_mensalidade=Decimal("150.00"))

    # ── PIX ──
    def test_pix_crc_valido_e_estrutura(self):
        pix = gerar_pix_copia_cola("teste@pix.com", "Operadora Cob", "Sao Paulo",
                                   Decimal("450.00"), "MENS2026080001")
        self.assertTrue(pix.startswith("000201"))
        self.assertIn("br.gov.bcb.pix", pix)
        self.assertIn("5303986", pix)     # moeda BRL
        self.assertIn("5406450.00", pix)   # valor
        # CRC: recomputar sobre tudo menos os 4 últimos deve bater
        corpo, crc = pix[:-4], pix[-4:]
        self.assertEqual(_crc16(corpo), crc)

    # ── Boleto ──
    def test_boleto_dvs_febraban(self):
        barcode, linha = gerar_boleto("341", date(2026, 9, 10), Decimal("450.00"),
                                      "0000123456789000000000000")
        self.assertEqual(len(barcode), 44)
        # DV geral (posição 5) confere por mod11 sobre os outros 43
        sem_dv = barcode[0:4] + barcode[5:44]
        self.assertEqual(_mod11_barcode(sem_dv), int(barcode[4]))
        # linha digitável: campos com DV mod10
        campos = linha.replace(".", "").split(" ")
        c1 = campos[0]  # 10 dígitos (9 + dv)
        self.assertEqual(_mod10(c1[:9]), int(c1[9]))

    def test_boleto_valor_no_codigo(self):
        barcode, _ = gerar_boleto("001", date(2026, 9, 10), Decimal("450.00"), "0" * 25)
        # valor em centavos nas posições 10-19
        self.assertEqual(barcode[9:19], "0000045000")

    # ── Faturas ──
    def test_gerar_faturas_soma_nucleo(self):
        faturas = gerar_faturas_competencia(self.op, "2026-08", dia_vencimento=10)
        self.assertEqual(len(faturas), 1)  # só o titular vira fatura
        f = faturas[0]
        self.assertEqual(f.valor_mensalidade, Decimal("450.00"))  # 300 + 150
        self.assertEqual(f.vencimento, date(2026, 8, 10))

    def test_emitir_cobranca_ambos(self):
        f = gerar_faturas_competencia(self.op, "2026-08")[0]
        emitir_cobranca(f, "ambos", chave_pix="chave@x.com", codigo_banco="341")
        f.refresh_from_db()
        self.assertTrue(f.pix_copia_cola.startswith("000201"))
        self.assertEqual(len(f.codigo_barras), 44)
        self.assertTrue(f.nosso_numero)

    # ── CNAB round-trip ──
    def test_remessa_e_conciliacao(self):
        f = gerar_faturas_competencia(self.op, "2026-08")[0]
        emitir_cobranca(f, "boleto", codigo_banco="341")
        texto, total = gerar_remessa_cnab240(self.op, [f], "341")
        self.assertEqual(total, Decimal("450.00"))
        self.assertTrue(all(len(l) == 240 for l in texto.split("\r\n")))
        # gera retorno com liquidação e concilia
        retorno = gerar_retorno_cnab240(self.op, [f], "341", ocorrencia="06")
        pagos = conciliar_retorno_cnab(self.op, retorno, "2026-08")
        self.assertEqual(pagos, 1)
        f.refresh_from_db()
        self.assertEqual(f.status, "pago")
        self.assertIsNotNone(f.pago_em)

    def test_conciliacao_nao_paga_sem_ocorrencia_06(self):
        f = gerar_faturas_competencia(self.op, "2026-08")[0]
        emitir_cobranca(f, "boleto")
        retorno = gerar_retorno_cnab240(self.op, [f], "000", ocorrencia="02")  # entrada confirmada, não liquidação
        pagos = conciliar_retorno_cnab(self.op, retorno, "2026-08")
        self.assertEqual(pagos, 0)
        f.refresh_from_db()
        self.assertEqual(f.status, "pendente")

    # ── API ──
    def test_api_gerar_e_listar(self):
        c = _client_for(self.op)
        r = c.post("/api/plano-saude/cobranca/gerar-faturas/",
                   data='{"competencia":"2026-08","dia_vencimento":10}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["geradas"], 1)
        r2 = c.get("/api/plano-saude/cobranca/faturas/?competencia=2026-08")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["resumo"]["qtd"], 1)
        self.assertEqual(r2.json()["resumo"]["total"], 450.0)
