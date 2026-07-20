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


class FuncionarioRegistroSegurancaTests(TransactionTestCase):
    """Regressão da vuln crítica de account-takeover cross-tenant no registro do
    portal do funcionário. A etapa 2 (registrar) NÃO pode confiar em
    funcionario_id cru: exige o registro_token assinado emitido na etapa 1
    (buscar-cpf), que prova a posse do CPF. Sem isso, um atacante enumeraria ids
    e criaria credencial para funcionário de qualquer tenant/segmento."""

    databases = {"default", "owner"}

    def setUp(self):
        self.client = Client()
        self.empresa_a = Empresa.objects.using("owner").create(
            nome="Empresa A", email="empa@example.com", senha=make_password("x"), ativo=True,
        )
        self.func_a = FuncionarioSST.objects.using("owner").create(
            empresa=self.empresa_a, nome="Ana", cpf="111.444.777-35", cargo="Op", ativo=True,
        )
        self.empresa_b = Empresa.objects.using("owner").create(
            nome="Empresa B", email="empb@example.com", senha=make_password("x"), ativo=True,
        )
        self.func_b = FuncionarioSST.objects.using("owner").create(
            empresa=self.empresa_b, nome="Bruno", cpf="222.333.444-05", cargo="Tec", ativo=True,
        )

    def _registrar(self, payload):
        return self.client.post(
            "/api/funcionario/registrar",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _credencial_existe(self, funcionario):
        from .models import CredencialAppFuncionario
        return CredencialAppFuncionario.objects.using("owner").filter(funcionario=funcionario).exists()

    def test_registrar_sem_token_com_id_cru_e_rejeitado(self):
        # Ataque antigo: manda funcionario_id de OUTRO tenant, sem registro_token.
        resp = self._registrar({
            "funcionario_id": self.func_b.id,
            "email": "atacante@example.com",
            "senha": "senha123",
        })
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(self._credencial_existe(self.func_b))

    def test_registrar_com_token_invalido_e_rejeitado(self):
        resp = self._registrar({
            "registro_token": "token.forjado.invalido",
            "email": "x@example.com",
            "senha": "senha123",
        })
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(self._credencial_existe(self.func_a))

    def test_fluxo_valido_com_token_cria_credencial(self):
        busca = self.client.post(
            "/api/funcionario/buscar-cpf",
            data=json.dumps({"cpf": "11144477735"}),
            content_type="application/json",
        )
        self.assertEqual(busca.status_code, 200)
        token = busca.json()["registro_token"]

        resp = self._registrar({
            "registro_token": token,
            "email": "ana@example.com",
            "senha": "senha123",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self._credencial_existe(self.func_a))
        # E nada foi criado para o funcionário do outro tenant.
        self.assertFalse(self._credencial_existe(self.func_b))
