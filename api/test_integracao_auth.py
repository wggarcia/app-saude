"""
Autenticação das integrações externas (api/services/integracao_auth.py).

O SQLite dos testes não tem RLS. Para reproduzir o que acontece no Postgres de
produção — a conexão "default" sem app.empresa_id não enxerga nenhuma chave —
os testes fazem o gerenciador padrão devolver vazio: a busca só pode dar certo
se passar pela conexão "owner".
"""
import hashlib
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.test import Client, RequestFactory, TestCase

from .models import ApiKeyEmpresa, Empresa, LogIntegracaoSST, TokenIntegracaoSST, UsoApiEmpresa
from .services import integracao_auth, rls
from .services.integracao_auth import empresa_por_api_key, empresa_por_token_sst


class _BaseIntegracao(TestCase):
    # SQLite não aguenta duas conexões abertas no mesmo banco de teste; aqui a
    # busca roda na default (sem RLS). O uso do alias "owner" é provado à parte.
    def setUp(self):
        rls._OWNER.update(checked=True, ok=False)
        self.rf = RequestFactory()


def _empresa(email, pacote="sst_enterprise_10"):
    return Empresa.objects.create(
        nome=f"Empresa {email}", email=email, senha=make_password("x"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _hash(valor):
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _rls_esconde_tudo(model):
    """Simula o RLS do Postgres: pela conexão default, nenhuma linha aparece."""
    return mock.patch.object(model.objects, "filter", return_value=model.objects.none())


class ApiKeyIntegracaoTests(_BaseIntegracao):
    def setUp(self):
        super().setUp()
        self.emp_a = _empresa("a@teste.local")
        self.emp_b = _empresa("b@teste.local")
        self.key_a, self.chave_a = ApiKeyEmpresa.criar_para(self.emp_a, "BI")
        _, self.chave_b = ApiKeyEmpresa.criar_para(self.emp_b, "BI")

    def _req(self, chave, path="/api/v1/dados"):
        return self.rf.get(path, HTTP_AUTHORIZATION=f"ApiKey {chave}")

    def test_escolhe_owner_quando_acessivel_e_default_quando_nao(self):
        rls._OWNER.update(checked=False, ok=True)
        with mock.patch.object(ApiKeyEmpresa.objects, "using") as using:
            using.return_value.exists.return_value = False
            self.assertEqual(rls.alias_sem_rls(), "owner")
        rls._OWNER.update(checked=False, ok=True)
        with mock.patch.object(ApiKeyEmpresa.objects, "using", side_effect=Exception("sem GRANT")):
            self.assertEqual(rls.alias_sem_rls(), "default")

    def test_busca_da_chave_passa_pelo_alias_owner(self):
        usados = []
        using_real = ApiKeyEmpresa.objects.using

        def registrar(alias):
            usados.append(alias)
            return using_real("default")

        with mock.patch.object(integracao_auth, "alias_sem_rls", return_value="owner"), \
                mock.patch.object(ApiKeyEmpresa.objects, "using", side_effect=registrar):
            empresa, _ = empresa_por_api_key(self._req(self.chave_a))
        self.assertEqual(empresa, self.emp_a)
        self.assertTrue(usados)
        self.assertEqual(set(usados), {"owner"})

    def test_acha_chave_mesmo_com_rls_escondendo_a_default(self):
        with _rls_esconde_tudo(ApiKeyEmpresa):
            empresa, key = empresa_por_api_key(self._req(self.chave_a))
        self.assertEqual(empresa, self.emp_a)
        self.assertEqual(key.pk, self.key_a.pk)

    def test_fixa_rls_na_empresa_da_chave(self):
        with mock.patch("api.middleware._rls_set_empresa") as rls:
            empresa_por_api_key(self._req(self.chave_b))
        rls.assert_called_once_with(self.emp_b.id)

    def test_chave_de_a_nunca_resolve_b(self):
        empresa, _ = empresa_por_api_key(self._req(self.chave_a))
        self.assertEqual(empresa, self.emp_a)
        self.assertNotEqual(empresa, self.emp_b)

    def test_recusa_chave_revogada_empresa_inativa_e_header_errado(self):
        self.assertEqual(empresa_por_api_key(self._req("nao-existe")), (None, None))
        self.assertEqual(empresa_por_api_key(self.rf.get("/", HTTP_AUTHORIZATION=f"Bearer {self.chave_a}")),
                         (None, None))
        self.assertEqual(empresa_por_api_key(self.rf.get("/")), (None, None))

        Empresa.objects.filter(pk=self.emp_b.pk).update(ativo=False)
        self.assertEqual(empresa_por_api_key(self._req(self.chave_b)), (None, None))

        ApiKeyEmpresa.objects.filter(pk=self.key_a.pk).update(ativa=False)
        self.assertEqual(empresa_por_api_key(self._req(self.chave_a)), (None, None))

    def test_contadores_de_uso_somam_em_vez_de_zerar(self):
        for _ in range(3):
            empresa_por_api_key(self._req(self.chave_a))
        self.key_a.refresh_from_db()
        self.assertEqual(self.key_a.total_chamadas, 3)
        uso = UsoApiEmpresa.objects.get(empresa=self.emp_a, api_key=self.key_a, endpoint="/api/v1/dados")
        self.assertEqual(uso.chamadas, 3)

    def test_endpoint_dados_com_e_sem_chave(self):
        client = Client()
        with _rls_esconde_tudo(ApiKeyEmpresa):
            ok = client.get("/api/v1/dados", HTTP_AUTHORIZATION=f"ApiKey {self.chave_a}")
        self.assertEqual(ok.status_code, 200, ok.content[:300])
        self.assertEqual(ok.json()["empresa"], self.emp_a.nome)
        self.assertEqual(client.get("/api/v1/dados").status_code, 401)


class TokenIntegracaoSSTTests(_BaseIntegracao):
    def setUp(self):
        super().setUp()
        self.emp = _empresa("sst@teste.local")
        self.outra = _empresa("outra@teste.local")
        self.valor = "tok-" + "x" * 40
        self.token = TokenIntegracaoSST.objects.create(
            empresa=self.emp, nome="ERP", token_hash=_hash(self.valor), prefixo=self.valor[:8],
        )

    def test_acha_token_mesmo_com_rls_escondendo_a_default(self):
        req = self.rf.get("/api/integracao-sst/funcionarios/", HTTP_X_API_TOKEN=self.valor)
        with _rls_esconde_tudo(TokenIntegracaoSST), mock.patch("api.middleware._rls_set_empresa") as rls:
            empresa, token = empresa_por_token_sst(req, "funcionarios", _hash)
        self.assertEqual(empresa, self.emp)
        self.assertEqual(token.pk, self.token.pk)
        rls.assert_called_once_with(self.emp.id)
        self.assertEqual(LogIntegracaoSST.objects.filter(token=self.token, endpoint="funcionarios").count(), 1)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.ultimo_uso)

    def test_recusa_token_inativo_errado_ou_empresa_inativa(self):
        def chamar(valor):
            return empresa_por_token_sst(self.rf.get("/", HTTP_X_API_TOKEN=valor), "asos", _hash)

        self.assertEqual(chamar("errado"), (None, None))
        self.assertEqual(empresa_por_token_sst(self.rf.get("/"), "asos", _hash), (None, None))
        Empresa.objects.filter(pk=self.emp.pk).update(ativo=False)
        self.assertEqual(chamar(self.valor), (None, None))
        Empresa.objects.filter(pk=self.emp.pk).update(ativo=True)
        TokenIntegracaoSST.objects.filter(pk=self.token.pk).update(ativo=False)
        self.assertEqual(chamar(self.valor), (None, None))

    def test_endpoint_funcionarios_com_e_sem_token(self):
        client = Client()
        with _rls_esconde_tudo(TokenIntegracaoSST):
            ok = client.get("/api/integracao-sst/funcionarios/", HTTP_X_API_TOKEN=self.valor)
        self.assertEqual(ok.status_code, 200, ok.content[:300])
        self.assertEqual(client.get("/api/integracao-sst/funcionarios/").status_code, 401)
