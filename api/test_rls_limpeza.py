"""
Limpeza do tenant RLS entre requisições (api/middleware.py).

app.empresa_id é gravado com escopo de sessão e a conexão é reaproveitada, então
cada requisição precisa começar sem tenant. O SQLite dos testes não tem RLS:
aqui a conexão Postgres é simulada e conferimos o SQL enviado.
"""
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from . import middleware as mw
from .models import Empresa, TotemDispositivo


def _conexao_pg():
    conn = mock.MagicMock()
    conn.vendor = "postgresql"
    conn._rls_tenant = None
    conn._rls_bypass = False
    cursor = conn.cursor.return_value.__enter__.return_value
    return conn, cursor


_SQL_LIMPAR = "SELECT set_config('app.empresa_id', '', false), set_config('app.rls_bypass', '', false)"


class RlsLimparTests(SimpleTestCase):
    def test_set_marca_a_conexao_e_grava_o_tenant(self):
        conn, cur = _conexao_pg()
        with mock.patch("django.db.connection", conn):
            mw._rls_set_empresa(42)
        self.assertEqual(conn._rls_tenant, 42)
        cur.execute.assert_called_once_with("SELECT set_config('app.empresa_id', %s, false)", ["42"])

    def test_limpar_zera_quando_a_conexao_carrega_tenant(self):
        conn, cur = _conexao_pg()
        conn._rls_tenant = 7
        with mock.patch("django.db.connection", conn):
            mw._rls_limpar()
        cur.execute.assert_called_once_with(_SQL_LIMPAR)
        self.assertIsNone(conn._rls_tenant)

    def test_limpar_nao_consulta_o_banco_sem_tenant(self):
        conn, cur = _conexao_pg()
        with mock.patch("django.db.connection", conn):
            mw._rls_limpar()
        cur.execute.assert_not_called()

    def test_limpar_que_falha_fecha_a_conexao(self):
        conn, cur = _conexao_pg()
        conn._rls_tenant = 7
        cur.execute.side_effect = Exception("conexão caiu")
        with mock.patch("django.db.connection", conn):
            mw._rls_limpar()
        conn.close.assert_called_once()
        self.assertIsNone(conn._rls_tenant)

    def test_sequencia_de_requisicoes_nao_herda_tenant(self):
        conn, cur = _conexao_pg()
        with mock.patch("django.db.connection", conn):
            mw._rls_limpar()          # requisição 1 começa
            mw._rls_set_empresa(11)   # requisição 1 autentica o cliente 11
            mw._rls_limpar()          # requisição 2 (pública) começa
        enviados = [c.args for c in cur.execute.call_args_list]
        self.assertEqual(enviados[-1], (_SQL_LIMPAR,))
        self.assertIsNone(conn._rls_tenant)


class MiddlewareChamaLimpezaTests(TestCase):
    def test_rota_publica_e_rota_autenticada_comecam_limpas(self):
        rf = RequestFactory()
        for path in ("/healthz", "/api/v1/dados", "/api/qualquer"):
            middleware = mw.EmpresaMiddleware(lambda r: HttpResponse("ok"))
            with mock.patch.object(mw, "_rls_limpar") as limpar:
                middleware(rf.get(path))
            limpar.assert_called_once_with()


class TotemSemTenantTests(TestCase):
    def setUp(self):
        self.hospital = Empresa.objects.create(
            nome="Hospital Teste", email="hosp@teste.local", senha=make_password("x"), ativo=True,
            tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="hospital_rede",
            sessao_ativa_chave="sessao-hosp",
        )
        self.disp = TotemDispositivo.objects.create(
            empresa=self.hospital, nome="Recepção", token="tok-totem-123",
        )

    def test_token_do_totem_e_achado_mesmo_com_rls_escondendo_a_default(self):
        visto = {}

        def view(request):
            visto["empresa"] = getattr(request, "empresa", None)
            return HttpResponse("ok")

        middleware = mw.EmpresaMiddleware(view)
        req = RequestFactory().get("/hospital/totem/", HTTP_X_TOTEM_TOKEN="tok-totem-123")
        with mock.patch.object(TotemDispositivo.objects, "filter",
                               return_value=TotemDispositivo.objects.none()), \
                mock.patch.object(mw, "_rls_set_empresa") as rls:
            resp = middleware(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(visto["empresa"], self.hospital)
        rls.assert_called_with(self.hospital.id)
