import json

from django.contrib.auth.hashers import make_password
from django.test import Client, TransactionTestCase

from .models import Empresa, FuncionarioSST


class FuncionarioPortalCpfTests(TransactionTestCase):
    databases = {"default", "owner"}

    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.using("owner").create(
            nome="Empresa SST",
            email="empresa-sst@example.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        self.funcionario = FuncionarioSST.objects.using("owner").create(
            empresa=self.empresa,
            nome="Ana Operadora",
            cpf="123.456.789-00",
            cargo="Operadora",
            ativo=True,
        )

    def test_buscar_cpf_encontra_funcionario_com_cpf_formatado_no_sst(self):
        response = self.client.post(
            "/api/funcionario/buscar-cpf",
            data=json.dumps({"cpf": "12345678900"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["funcionario_id"], self.funcionario.id)
        self.assertEqual(body["empresa_nome"], self.empresa.nome)

    def test_login_legado_por_cpf_encontra_funcionario_com_cpf_formatado_no_sst(self):
        response = self.client.post(
            "/api/funcionario/login",
            data=json.dumps({"cpf": "12345678900"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["funcionario_id"], self.funcionario.id)
