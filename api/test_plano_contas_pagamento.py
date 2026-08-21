"""
Contas médicas + pagamento a prestador.

Cobre: fechamento de conta (agrega lotes TISS processados em repasse),
IA de anomalia de faturamento (z-score vs histórico do prestador), e o
fluxo de pagamento (aprovar → pagar → lotes marcados).
"""
from datetime import timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, LotePagamentoPrestador, LoteTISSRecebido, PrestadorPlanoSaude,
)
from .views_plano_contas_pagamento import (
    contas_abertas, fechar_conta, _ia_anomalia,
)


def _empresa(email):
    return Empresa.objects.create(
        nome="Operadora Contas", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


def _client_for(empresa):
    c = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    c.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return c


def _lote(empresa, prestador, apres, glosa):
    liberado = Decimal(apres) - Decimal(glosa)
    return LoteTISSRecebido.objects.create(
        empresa=empresa, prestador=prestador, prestador_nome=prestador.nome_fantasia,
        numero_lote="L", status="processado",
        valor_apresentado=Decimal(apres), valor_glosado=Decimal(glosa), valor_liberado=liberado,
    )


class ContasPagamentoTests(TestCase):
    def setUp(self):
        self.op = _empresa("contas@example.com")
        self.prest = PrestadorPlanoSaude.objects.create(
            empresa=self.op, nome_fantasia="Hospital São Lucas", codigo_rede="HSL",
            status=PrestadorPlanoSaude.STATUS_CREDENCIADO, score_qualidade=82,
        )
        self.comp = timezone.now().strftime("%Y-%m")

    def test_contas_abertas_agrega(self):
        _lote(self.op, self.prest, "1000.00", "100.00")
        _lote(self.op, self.prest, "500.00", "0.00")
        ab = contas_abertas(self.op, self.comp)
        self.assertEqual(len(ab), 1)
        self.assertEqual(ab[0]["qtd_lotes"], 2)
        self.assertEqual(ab[0]["valor_bruto"], 1500.0)
        self.assertEqual(ab[0]["valor_liquido"], 1400.0)

    def test_fechar_gera_repasse_e_vincula_lotes(self):
        l1 = _lote(self.op, self.prest, "1000.00", "100.00")
        l2 = _lote(self.op, self.prest, "500.00", "0.00")
        pag = fechar_conta(self.op, self.prest.id, self.comp)
        self.assertEqual(pag.qtd_lotes, 2)
        self.assertEqual(pag.valor_liquido, Decimal("1400.00"))
        self.assertEqual(pag.status, "fechado")
        l1.refresh_from_db(); l2.refresh_from_db()
        self.assertEqual(l1.pagamento_id, pag.id)
        self.assertEqual(l2.pagamento_id, pag.id)
        # não sobra conta aberta depois do fechamento
        self.assertEqual(len(contas_abertas(self.op, self.comp)), 0)

    def test_fechar_sem_lotes_erro(self):
        with self.assertRaises(ValueError):
            fechar_conta(self.op, self.prest.id, self.comp)

    def test_ia_anomalia_detecta_pico(self):
        # histórico ~R$1.000/mês
        for i, c in enumerate(["2026-01", "2026-02", "2026-03"]):
            LotePagamentoPrestador.objects.create(
                empresa=self.op, prestador=self.prest, prestador_nome=self.prest.nome_fantasia,
                competencia=c, valor_liquido=Decimal("1000.00"), status="pago",
            )
        score, parecer = _ia_anomalia(self.op, self.prest, self.comp, Decimal("5000.00"))
        self.assertGreaterEqual(score, 60)
        self.assertIn("auditoria", parecer.lower())

    def test_ia_anomalia_sem_historico(self):
        score, parecer = _ia_anomalia(self.op, self.prest, self.comp, Decimal("1000.00"))
        self.assertEqual(score, 0)
        self.assertIn("baseline", parecer.lower())

    def test_fluxo_pagamento_via_api(self):
        _lote(self.op, self.prest, "2000.00", "200.00")
        pag = fechar_conta(self.op, self.prest.id, self.comp)
        c = _client_for(self.op)
        # aprovar
        r = c.post(f"/api/plano-saude/contas/pagamentos/{pag.id}/acao/",
                   data='{"acao":"aprovar"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pagamento"]["status"], "aprovado")
        # pagar
        r = c.post(f"/api/plano-saude/contas/pagamentos/{pag.id}/acao/",
                   data='{"acao":"pagar","forma_pagamento":"pix"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pagamento"]["status"], "pago")
        pag.refresh_from_db()
        self.assertEqual(pag.forma_pagamento, "pix")
        self.assertIsNotNone(pag.data_pagamento)
        # lotes incluídos marcados como retornado/liquidados
        self.assertTrue(all(l.status == "retornado" for l in pag.lotes_incluidos.all()))

    def test_cancelar_devolve_lotes(self):
        l1 = _lote(self.op, self.prest, "300.00", "0.00")
        pag = fechar_conta(self.op, self.prest.id, self.comp)
        c = _client_for(self.op)
        r = c.post(f"/api/plano-saude/contas/pagamentos/{pag.id}/acao/",
                   data='{"acao":"cancelar"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        l1.refresh_from_db()
        self.assertIsNone(l1.pagamento_id)
        # lote volta a aparecer em aberto
        self.assertEqual(len(contas_abertas(self.op, self.comp)), 1)
