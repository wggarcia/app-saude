"""
RLS nas tabelas de empresa_id anulável e liberação do console do dono.

O comportamento da policy foi validado no Postgres (tabela temporária, transação
desfeita). Aqui ficam o contrato do SQL gerado, o fluxo do middleware e o reset
de senha de sub-usuário — cujo token nascia sem empresa e era recusado pelo RLS.
"""
from unittest import mock

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from . import middleware as mw
from .management.commands import aplicar_rls_cobertura as cmd
from .models import DonoSaaS, Empresa, EmpresaUsuario, PasswordResetToken


def _conexao_pg():
    conn = mock.MagicMock()
    conn.vendor = "postgresql"
    conn._rls_tenant = None
    conn._rls_bypass = False
    return conn, conn.cursor.return_value.__enter__.return_value


class PolicySqlTests(SimpleTestCase):
    def test_policy_isola_por_tenant_e_aceita_so_a_liberacao_do_dono(self):
        sql = cmd._POLICY_SQL.format(tabela="api_x")
        self.assertIn("NULLIF(current_setting('app.empresa_id', true), '')::bigint", sql)
        self.assertIn("current_setting('app.rls_bypass', true) = 'dono'", sql)
        self.assertEqual(sql.count("current_setting('app.rls_bypass', true) = 'dono'"), 2)  # USING e WITH CHECK

    def test_anulaveis_isoladas_por_decisao_e_push_publico_fora(self):
        self.assertIn("api_planosaude", cmd.TABELAS_ANULAVEIS_ISOLADAS)
        self.assertIn("api_passwordresettoken", cmd.TABELAS_ANULAVEIS_ISOLADAS)
        self.assertNotIn("api_dispositivopushpublico", cmd.TABELAS_ANULAVEIS_ISOLADAS)

    def test_consulta_alvo_inclui_as_anulaveis_listadas(self):
        cur = mock.MagicMock()
        cur.fetchall.return_value = []
        cmd._tabelas_alvo(cur)
        sql, params = cur.execute.call_args.args
        self.assertIn("ANY(%s)", sql)
        self.assertEqual(params, [list(cmd.TABELAS_ANULAVEIS_ISOLADAS)])


class PolicyIndiretaSqlTests(SimpleTestCase):
    def test_filha_isola_pelo_pai_e_aceita_a_liberacao_do_dono(self):
        from .management.commands import aplicar_rls_indireto as ind
        sql = ind._policy_sql("api_filha", '"pai_id" IN (SELECT id FROM "api_pai" WHERE empresa_id = 1)')
        self.assertIn('("pai_id" IN (SELECT id FROM "api_pai" WHERE empresa_id = 1)) OR '
                      "current_setting('app.rls_bypass', true) = 'dono'", sql)
        self.assertEqual(sql.count("app.rls_bypass"), 2)  # USING e WITH CHECK

    def test_filhas_novas_de_setembro_sao_achadas_em_1_hop(self):
        from django.apps import apps
        from .management.commands import aplicar_rls_indireto as ind
        for nome in ("VotoCIPA", "VotanteCIPA", "CandidatoCIPA", "AcessoSECLog",
                     "CompartilhamentoSEC", "CotacaoFornecedorOPME", "LogIntegracaoSST"):
            _, _, hops = ind._descobrir_caminho(apps.get_model("api", nome))
            self.assertEqual(hops, 1, nome)


class LiberacaoDonoTests(SimpleTestCase):
    def test_liberar_dono_grava_e_marca(self):
        conn, cur = _conexao_pg()
        with mock.patch("django.db.connection", conn):
            mw._rls_liberar_dono()
        cur.execute.assert_called_once_with("SELECT set_config('app.rls_bypass', 'dono', false)")
        self.assertTrue(conn._rls_bypass)

    def test_proxima_requisicao_desfaz_a_liberacao(self):
        conn, cur = _conexao_pg()
        with mock.patch("django.db.connection", conn):
            mw._rls_liberar_dono()
            mw._rls_limpar()
        self.assertEqual(
            cur.execute.call_args.args[0],
            "SELECT set_config('app.empresa_id', '', false), set_config('app.rls_bypass', '', false)",
        )
        self.assertFalse(conn._rls_bypass)


class ConsoleDonoMiddlewareTests(TestCase):
    def setUp(self):
        self.dono = DonoSaaS.objects.create(
            nome="Dono", email="dono@plataforma.local", senha=make_password("x"),
            sessao_ativa_chave="sessao-dono",
        )
        self.rf = RequestFactory()

    def _req(self, session_key):
        token = jwt.encode({"owner_id": self.dono.id, "session_key": session_key},
                           settings.JWT_SECRET_KEY, algorithm="HS256")
        req = self.rf.get("/api/operacao-central/resumo")
        req.COOKIES["owner_token"] = token
        return req

    def test_dono_autenticado_libera_o_rls(self):
        middleware = mw.EmpresaMiddleware(lambda r: HttpResponse("ok"))
        with mock.patch.object(mw, "_rls_liberar_dono") as liberar:
            resp = middleware(self._req("sessao-dono"))
        self.assertEqual(resp.status_code, 200)
        liberar.assert_called_once_with()

    def test_sessao_do_dono_invalida_nao_libera(self):
        middleware = mw.EmpresaMiddleware(lambda r: HttpResponse("ok"))
        with mock.patch.object(mw, "_rls_liberar_dono") as liberar:
            resp = middleware(self._req("sessao-antiga"))
        self.assertEqual(resp.status_code, 401)
        liberar.assert_not_called()


class ResetSenhaSubusuarioTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Empresa Reset", email="dono@reset.local", senha=make_password("senha-do-dono"),
            ativo=True, tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="sst_enterprise_10",
        )
        self.usuario = EmpresaUsuario.objects.create(
            empresa=self.empresa, nome="Bia", email="bia@reset.local",
            senha=make_password("senha-antiga"), ativo=True,
        )
        self.client = Client()

    def test_token_de_subusuario_nasce_com_a_empresa_e_tenant_fixado(self):
        with mock.patch("api.middleware._rls_set_empresa") as rls:
            self.client.post("/solicitar-reset-senha/", {"email": "bia@reset.local"})
        token = PasswordResetToken.objects.get(usuario=self.usuario)
        self.assertEqual(token.empresa_id, self.empresa.id)
        rls.assert_any_call(self.empresa.id)

    def test_redefinir_troca_a_senha_do_subusuario_e_nao_a_do_dono(self):
        self.client.post("/solicitar-reset-senha/", {"email": "bia@reset.local"})
        token = PasswordResetToken.objects.get(usuario=self.usuario)
        resp = self.client.post(f"/redefinir-senha/{token.token}/",
                                {"senha": "senha-nova-123", "senha_confirm": "senha-nova-123"})
        self.assertEqual(resp.status_code, 302)
        self.usuario.refresh_from_db()
        self.empresa.refresh_from_db()
        self.assertTrue(check_password("senha-nova-123", self.usuario.senha))
        self.assertTrue(check_password("senha-do-dono", self.empresa.senha))
        token.refresh_from_db()
        self.assertTrue(token.usado)
