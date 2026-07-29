"""
Ressarcimento ao SUS (ABI/GRU) e NPS do beneficiário — Plano de Saúde.

Cobre:
  - Ressarcimento: criar ABI, transição de status (impugnar → pagar), KPIs,
    isolamento por tenant (uma operadora não vê ABI de outra);
  - NPS: registrar avaliações e conferir o cálculo (%promotores - %detratores),
    e que o dashboard-exec passa a expor o NPS real.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, PlanoSaude, RessarcimentoSUS, AvaliacaoNPS


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
        nome="Operadora RN", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class RessarcimentoSUSTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_plano("rs@example.com")
        self.client_ = _client_for(self.empresa)

    def test_criar_e_transicao_status(self):
        r = self.client_.post(
            "/api/plano-saude/ressarcimento-sus",
            data={"beneficiario_nome": "José Silva", "valor_cobrado": 1200.50,
                  "tipo_atendimento": "internacao", "numero_abi": "2026.001"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["ressarcimento"]["id"]

        # impugnar
        r2 = self.client_.put(
            f"/api/plano-saude/ressarcimento-sus/{rid}",
            data={"status": "impugnado", "justificativa_impugnacao": "atendimento não coberto"},
            content_type="application/json",
        )
        self.assertEqual(r2.json()["ressarcimento"]["status"], "impugnado")

        # marcar pago → preenche data_pagamento e valor_pago automaticamente
        r3 = self.client_.put(
            f"/api/plano-saude/ressarcimento-sus/{rid}",
            data={"status": "pago"},
            content_type="application/json",
        )
        pago = r3.json()["ressarcimento"]
        self.assertEqual(pago["status"], "pago")
        self.assertIsNotNone(pago["data_pagamento"])
        self.assertEqual(pago["valor_pago"], 1200.50)

    def test_kpis(self):
        RessarcimentoSUS.objects.create(empresa=self.empresa, valor_cobrado=100, status="recebido")
        RessarcimentoSUS.objects.create(empresa=self.empresa, valor_cobrado=200, status="deferido")
        k = self.client_.get("/api/plano-saude/ressarcimento-sus/kpis").json()
        self.assertEqual(k["total_abis"], 2)
        self.assertEqual(k["economia_impugnacao"], 200.0)

    def test_isolamento_por_tenant(self):
        outra = _empresa_plano("rs-outra@example.com")
        RessarcimentoSUS.objects.create(empresa=outra, valor_cobrado=999, status="recebido")
        d = self.client_.get("/api/plano-saude/ressarcimento-sus").json()
        self.assertEqual(len(d["ressarcimentos"]), 0)


class NPSTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_plano("nps@example.com")
        self.client_ = _client_for(self.empresa)

    def test_calculo_nps(self):
        # 3 promotores (10), 1 detrator (3) → NPS = (3-1)/4 = 50
        for nota in (10, 10, 10, 3):
            r = self.client_.post("/api/plano-saude/nps", data={"nota": nota}, content_type="application/json")
            self.assertEqual(r.status_code, 201, r.content)
        d = self.client_.get("/api/plano-saude/nps").json()
        self.assertEqual(d["total_respostas"], 4)
        self.assertEqual(d["promotores"], 3)
        self.assertEqual(d["detratores"], 1)
        self.assertEqual(d["nps"], 50)

    def test_nota_invalida_rejeitada(self):
        r = self.client_.post("/api/plano-saude/nps", data={"nota": 11}, content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_dashboard_exec_expoe_nps_real(self):
        AvaliacaoNPS.objects.create(empresa=self.empresa, nota=9)
        AvaliacaoNPS.objects.create(empresa=self.empresa, nota=2)
        d = self.client_.get("/api/plano-saude/dashboard-exec/").json()
        self.assertEqual(d["nps"], 0)  # (1 promotor - 1 detrator)/2 = 0
        self.assertEqual(d["nps_fonte"], "calculado_dados_reais")
