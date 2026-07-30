"""
Intercâmbio entre operadoras (GTO) — cooperativas / atendimento fora de praça.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, GuiaIntercambio


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa_plano(email):
    return Empresa.objects.create(
        nome="Cooperativa RN", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class IntercambioTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_plano("gto@example.com")
        self.client_ = _client_for(self.empresa)

    def test_criar_e_kpis_saldo(self):
        # emitida (a receber) 300 + recebida (a pagar) 100 → saldo 200
        self.client_.post("/api/plano-saude/intercambio", data={
            "tipo": "emitida", "operadora_correspondente": "Unimed Rio", "valor": 300,
        }, content_type="application/json")
        self.client_.post("/api/plano-saude/intercambio", data={
            "tipo": "recebida", "operadora_correspondente": "Unimed SP", "valor": 100,
        }, content_type="application/json")
        k = self.client_.get("/api/plano-saude/intercambio/kpis").json()
        self.assertEqual(k["total"], 2)
        self.assertEqual(k["a_receber"], 300.0)
        self.assertEqual(k["a_pagar"], 100.0)
        self.assertEqual(k["saldo"], 200.0)

    def test_transicao_status_liquida(self):
        r = self.client_.post("/api/plano-saude/intercambio", data={
            "tipo": "emitida", "operadora_correspondente": "Unimed BH", "valor": 500,
        }, content_type="application/json")
        gid = r.json()["intercambio"]["id"]
        r2 = self.client_.put(f"/api/plano-saude/intercambio/{gid}", data={"status": "paga"},
                              content_type="application/json")
        pago = r2.json()["intercambio"]
        self.assertEqual(pago["status"], "paga")
        self.assertIsNotNone(pago["data_liquidacao"])
        # após liquidar, não conta mais em "a_receber"
        k = self.client_.get("/api/plano-saude/intercambio/kpis").json()
        self.assertEqual(k["a_receber"], 0.0)

    def test_isolamento_por_tenant(self):
        outra = _empresa_plano("gto-outra@example.com")
        GuiaIntercambio.objects.create(empresa=outra, tipo="emitida", valor=999)
        d = self.client_.get("/api/plano-saude/intercambio").json()
        self.assertEqual(len(d["intercambios"]), 0)
