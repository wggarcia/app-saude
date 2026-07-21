from django.test import SimpleTestCase

from api.utils import cpf_valido, validar_cpf_cadastro


class _EmpresaFake:
    def __init__(self, email):
        self.email = email


class CpfValidoTests(SimpleTestCase):
    def test_cpfs_validos(self):
        for cpf in ["529.982.247-25", "111.444.777-35", "12345678909"]:
            self.assertTrue(cpf_valido(cpf), cpf)

    def test_cpfs_invalidos(self):
        for cpf in ["111.111.111-11", "000.000.000-00", "123.456.789-00", "12345", "", None]:
            self.assertFalse(cpf_valido(cpf), repr(cpf))


class ValidarCpfCadastroTests(SimpleTestCase):
    def test_conta_real_rejeita_cpf_fake(self):
        emp = _EmpresaFake("cliente.real@empresa.com")
        ok, erro = validar_cpf_cadastro("111.111.111-11", emp)
        self.assertFalse(ok)
        self.assertIn("CPF inválido", erro)

    def test_conta_real_aceita_cpf_verdadeiro(self):
        emp = _EmpresaFake("cliente.real@empresa.com")
        ok, erro = validar_cpf_cadastro("529.982.247-25", emp)
        self.assertTrue(ok)
        self.assertIsNone(erro)

    def test_conta_demo_aceita_cpf_fake(self):
        emp = _EmpresaFake("demo.sst@soluscrt.com")
        ok, erro = validar_cpf_cadastro("111.111.111-11", emp)
        self.assertTrue(ok)  # demo pode usar fake para demonstração

    def test_cpf_vazio_e_permitido(self):
        emp = _EmpresaFake("cliente.real@empresa.com")
        ok, _ = validar_cpf_cadastro("", emp)
        self.assertTrue(ok)  # campo opcional na maioria dos cadastros
