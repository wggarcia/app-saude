from django.test import TestCase
from django.test import override_settings

from .models import Empresa


class PagamentoRedirectTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Farmacia Teste",
            email="farmacia.tests@soluscrt.com.br",
            senha="x",
            plano="free",
            ativo=False,
        )

    def test_sucesso_aprovado_redireciona_dashboard_com_empresa_id(self):
        response = self.client.get(
            f"/sucesso/?status=approved&external_reference={self.empresa.id}"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/dashboard/?empresa_id={self.empresa.id}")
        self.assertIn("empresa_id", response.cookies)
        self.assertEqual(response.cookies["empresa_id"].value, str(self.empresa.id))

    def test_pendente_preserva_empresa_id_no_cookie(self):
        response = self.client.get(f"/pendente/?empresa_id={self.empresa.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("empresa_id", response.cookies)
        self.assertEqual(response.cookies["empresa_id"].value, str(self.empresa.id))


class DashboardValidationTests(TestCase):
    def setUp(self):
        self.empresa_ativa = Empresa.objects.create(
            nome="Ativa",
            email="ativa.tests@soluscrt.com.br",
            senha="x",
            plano="premium",
            ativo=True,
        )
        self.empresa_inativa = Empresa.objects.create(
            nome="Inativa",
            email="inativa.tests@soluscrt.com.br",
            senha="x",
            plano="free",
            ativo=False,
        )

    def test_dashboard_sem_empresa_id_redireciona_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_dashboard_empresa_inativa_redireciona_pagamento(self):
        response = self.client.get(f"/dashboard/?empresa_id={self.empresa_inativa.id}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/pagamento/")

    def test_dashboard_empresa_ativa_renderiza(self):
        response = self.client.get(f"/dashboard/?empresa_id={self.empresa_ativa.id}")
        self.assertEqual(response.status_code, 200)


class PacotesPagamentoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Teste Pacote",
            email="pacote.tests@soluscrt.com.br",
            senha="x",
            plano="free",
            ativo=False,
        )

    def test_planos_publicos_retorna_catalogo(self):
        response = self.client.get("/api/planos-publicos")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("packages", body)
        self.assertGreaterEqual(len(body["packages"]), 1)

    @override_settings(PAYMENT_PROVIDER="asaas")
    def test_criar_pagamento_bloqueia_pacote_invalido(self):
        response = self.client.post(
            f"/api/assinatura/{self.empresa.id}/",
            data='{"package_id":"pacote_inexistente","cycle":"MONTHLY"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("erro", response.json())
