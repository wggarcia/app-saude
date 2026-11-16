"""
/api/login-modulo exige a sessão já aberta (request.empresa). Ele ficava atrás
do prefixo público "/api/login" do EmpresaMiddleware, que pulava a leitura da
sessão — e a view respondia 401 sempre.
"""
import json

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase

from .models import Empresa, EmpresaUsuario, RBACAtribuicao, RBACPermissao
from .services.auth_session import criar_token

MODULO = "teste.login_modulo"


class LoginModuloTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Empresa Modulo", email="dono@modulo.local", senha=make_password("senha-dono"),
            ativo=True, tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="sst_enterprise_10",
            sessao_ativa_chave="sessao-dono",
        )
        self.usuario = EmpresaUsuario.objects.create(
            empresa=self.empresa, nome="Ana RH", email="ana@modulo.local",
            senha=make_password("senha-ana"), ativo=True,
        )
        permissao = RBACPermissao.objects.create(codigo=MODULO, descricao="Teste", modulo="teste")
        RBACAtribuicao.objects.create(empresa=self.empresa, usuario=self.usuario, permissao=permissao)
        self.client = Client()

    def _logar_como_dono(self):
        token = criar_token(self.empresa, "sessao-dono", "empresa_admin", self.empresa.id)
        self.client.cookies["auth_token"] = token

    def _entrar(self, senha="senha-ana", modulo=MODULO):
        return self.client.post(
            "/api/login-modulo",
            data=json.dumps({
                "email": "ana@modulo.local", "senha": senha,
                "codigo_modulo": modulo, "device_id": "dev-teste-1", "device_name": "Teste",
            }),
            content_type="application/json",
        )

    def test_com_sessao_aberta_promove_o_subusuario(self):
        self._logar_como_dono()
        resp = self._entrar()
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json().get("ok"))

    def test_modulo_sem_permissao_e_recusado(self):
        RBACAtribuicao.objects.filter(usuario=self.usuario).update(ativo=False)
        self.empresa.rbac_estrito = True
        self.empresa.save(update_fields=["rbac_estrito"])
        self._logar_como_dono()
        self.assertEqual(self._entrar().status_code, 403)

    def test_senha_errada_recusa_com_credenciais_invalidas(self):
        self._logar_como_dono()
        resp = self._entrar(senha="errada")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json().get("erro"), "Credenciais inválidas")

    def test_sem_sessao_recusa_no_middleware(self):
        resp = self._entrar()
        self.assertEqual(resp.status_code, 401)
        self.assertNotEqual(resp.json().get("erro"), "Credenciais inválidas")

    def test_logins_publicos_continuam_abertos(self):
        for path in ("/api/login", "/api/login-empresa", "/api/login-empresa-api", "/api/login-governo"):
            resp = self.client.post(path, data=json.dumps({"email": "x@y.z", "senha": "errada"}),
                                    content_type="application/json")
            corpo = resp.json() if resp.get("Content-Type", "").startswith("application/json") else {}
            self.assertNotEqual(corpo.get("erro"), "não autenticado", path)
