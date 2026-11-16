"""
Rotas públicas, webhooks e login sem tenant herdado.

Cada requisição começa sem tenant (_rls_limpar). O SQLite dos testes não tem
RLS, então `simular_rls` reproduz o Postgres no manager padrão dos modelos:
sem tenant fixado nenhuma linha aparece; com tenant, só as da empresa dele.
A busca "sem RLS" (api/services/rls.objetos_sem_rls) passa pelo _base_manager,
que não é simulado. Assim o código que dependia do tenant herdado falha aqui.
"""
import json
from contextlib import ExitStack, contextmanager
from unittest import mock

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import (
    ASOCompartilhamento, ASOOcupacional, Empresa, EmpresaUsuario, FinanceiroEventoSaaS,
    FuncionarioSST, IntegracaoIfood, PasswordResetToken, PedidoDelivery, RegistroSintoma,
)
from .services import rls


@contextmanager
def simular_rls(por_empresa=(), ocultos_sem_tenant=()):
    """por_empresa: tabelas com empresa_id (sem tenant: nada; com tenant: só as dele).
    ocultos_sem_tenant: tabelas que somem sem tenant por causa de um join com
    tabela sob RLS (ex.: token cujo select_related cai numa tabela de tenant)."""
    estado = {"tenant": None, "historico": []}

    def set_tenant(empresa_id):
        estado["tenant"] = int(empresa_id) if str(empresa_id).strip() else None
        estado["historico"].append(estado["tenant"])

    def envolver(model, filtrar_empresa):
        real = model.objects.get_queryset

        def get_queryset():
            qs = real()
            if estado["tenant"] is None:
                return qs.none()
            return qs.filter(empresa_id=estado["tenant"]) if filtrar_empresa else qs
        return mock.patch.object(model.objects, "get_queryset", side_effect=get_queryset)

    with ExitStack() as pilha:
        pilha.enter_context(mock.patch("api.middleware._rls_set_empresa", side_effect=set_tenant))
        pilha.enter_context(mock.patch.object(
            rls, "objetos_sem_rls", side_effect=lambda model: model._base_manager.using("default"),
        ))
        for model in por_empresa:
            pilha.enter_context(envolver(model, True))
        for model in ocultos_sem_tenant:
            pilha.enter_context(envolver(model, False))
        yield estado


def _empresa(email, **extra):
    dados = dict(nome=f"Empresa {email}", email=email, senha=make_password("123456"), ativo=True,
                 tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="sst_enterprise_10",
                 max_dispositivos=5, max_usuarios=5)
    dados.update(extra)
    return Empresa.objects.create(**dados)


def _sub_usuario(empresa, email="sub@teste.local", senha="123456"):
    return EmpresaUsuario.objects.create(
        empresa=empresa, nome="Sub Usuario", email=email, senha=make_password(senha), ativo=True,
    )


class SessaoPorTokenTests(TestCase):
    def test_tenant_vem_do_jwt_antes_de_ler_o_sub_usuario(self):
        from .services.auth_session import resolver_sessao_empresa_por_token
        empresa = _empresa("dono@teste.local")
        usuario = _sub_usuario(empresa)
        token = jwt.encode({
            "empresa_id": empresa.id, "principal_kind": "usuario_empresa",
            "principal_id": usuario.id, "session_key": "k",
        }, settings.JWT_SECRET_KEY, algorithm="HS256")

        with simular_rls(por_empresa=[EmpresaUsuario]) as rls_estado:
            _, emp, principal = resolver_sessao_empresa_por_token(token)
        self.assertEqual(emp, empresa)
        self.assertEqual(principal.pk, usuario.pk)
        self.assertEqual(rls_estado["tenant"], empresa.id)

    def test_set_empresa_auth_passa_pelo_middleware(self):
        from .services.auth_session import _rls_set_empresa_auth
        with mock.patch("api.middleware._rls_set_empresa") as set_mw:
            _rls_set_empresa_auth(77)
        set_mw.assert_called_once_with(77)


class LoginSubUsuarioTests(TestCase):
    def test_sub_usuario_entra_sem_tenant_herdado(self):
        empresa = _empresa("dono-login@teste.local")
        _sub_usuario(empresa, email="sub-login@teste.local")
        with simular_rls(por_empresa=[EmpresaUsuario]) as rls_estado:
            resp = Client().post("/api/login-empresa", data=json.dumps({
                "email": "sub-login@teste.local", "senha": "123456", "device_id": "dev-sub",
            }), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertIn("token", resp.json())
        self.assertEqual(rls_estado["tenant"], empresa.id)


@override_settings(ASAAS_WEBHOOK_TOKEN="segredo-asaas")
class WebhookAsaasTests(TestCase):
    def test_duplicidade_e_registro_rodam_no_tenant_da_empresa(self):
        empresa = _empresa("cliente-asaas@teste.local", ativo=False)
        corpo = json.dumps({"event": "PAYMENT_CONFIRMED", "payment": {
            "id": "pay_123", "status": "CONFIRMED", "externalReference": str(empresa.id), "value": 99,
        }})
        with simular_rls(por_empresa=[FinanceiroEventoSaaS]) as rls_estado:
            for _ in range(2):  # o Asaas reenvia o mesmo evento
                resp = Client().post("/api/webhook", data=corpo, content_type="application/json",
                                     HTTP_ASAAS_ACCESS_TOKEN="segredo-asaas")
                self.assertEqual(resp.status_code, 200)
        self.assertEqual(rls_estado["tenant"], empresa.id)
        aprovados = FinanceiroEventoSaaS.objects.filter(empresa=empresa, status="aprovado")
        self.assertEqual(aprovados.count(), 1)


class ResetSenhaSubUsuarioTests(TestCase):
    def setUp(self):
        self.empresa = _empresa("dono-reset@teste.local")
        self.usuario = _sub_usuario(self.empresa, email="sub-reset@teste.local", senha="antiga123")

    def test_solicitar_gera_token_para_o_sub_usuario(self):
        with simular_rls(por_empresa=[EmpresaUsuario]), \
                mock.patch("api.views_reset_senha._enviar_email_reset"):
            Client().post("/solicitar-reset-senha/", {"email": "sub-reset@teste.local"})
        self.assertTrue(PasswordResetToken.objects.filter(usuario=self.usuario).exists())

    def test_redefinir_troca_a_senha_do_sub_usuario(self):
        tok = PasswordResetToken.objects.create(
            usuario=self.usuario, expira_em=timezone.now() + timezone.timedelta(hours=1),
        )
        with simular_rls(por_empresa=[EmpresaUsuario], ocultos_sem_tenant=[PasswordResetToken]) as rls_estado:
            resp = Client().post(f"/redefinir-senha/{tok.token}/",
                                 {"senha": "novaSenha123", "senha_confirm": "novaSenha123"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(rls_estado["tenant"], self.empresa.id)
        self.usuario.refresh_from_db()
        self.assertTrue(check_password("novaSenha123", self.usuario.senha))
        tok.refresh_from_db()
        self.assertTrue(tok.usado)

    def test_token_sem_conta_alvo_nao_finge_sucesso(self):
        tok = PasswordResetToken.objects.create(expira_em=timezone.now() + timezone.timedelta(hours=1))
        resp = Client().post(f"/redefinir-senha/{tok.token}/",
                             {"senha": "novaSenha123", "senha_confirm": "novaSenha123"})
        self.assertEqual(resp.status_code, 200)
        tok.refresh_from_db()
        self.assertFalse(tok.usado)


class PortalAsoTests(TestCase):
    def test_link_publico_abre_com_o_tenant_do_aso(self):
        from django.core.cache import cache
        cache.clear()
        empresa = _empresa("clinica-portal@teste.local")
        func = FuncionarioSST.objects.create(empresa=empresa, nome="Maria Portal", cargo="Op")
        aso = ASOOcupacional.objects.create(
            empresa=empresa, funcionario=func, tipo="admissional",
            data_emissao=timezone.now().date(), resultado="apto", medico_responsavel="Dr.",
        )
        ASOCompartilhamento.objects.create(
            aso=aso, empresa_origem=empresa, token="tok-portal-rls", max_acessos=5, acessos=0,
            expira_em=timezone.now() + timezone.timedelta(hours=2), ativo=True,
        )
        with simular_rls(ocultos_sem_tenant=[ASOCompartilhamento]) as rls_estado:
            resp = Client().get("/sst/aso/portal/tok-portal-rls/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Maria Portal")
        self.assertEqual(rls_estado["tenant"], empresa.id)


class WebhookIfoodTests(TestCase):
    def test_pedido_e_gravado_no_tenant_da_farmacia(self):
        farmacia = _empresa("farmacia-ifood@teste.local", pacote_codigo="farmacia_local")
        IntegracaoIfood.objects.create(
            empresa=farmacia, merchant_id="merch-1", webhook_signature_key="assina", ativo=True,
        )
        corpo = json.dumps({"merchantId": "merch-1", "orderId": "ord-9", "code": "PLACED",
                            "order": {"displayId": "9", "customer": {"name": "Cliente"}}})
        with simular_rls(por_empresa=[IntegracaoIfood]) as rls_estado:
            resp = Client().post("/api/farmacia/ifood/webhook/", data=corpo,
                                 content_type="application/json", HTTP_X_IFOOD_SIGNATURE="assina")
        self.assertIn(resp.status_code, (200, 201), resp.content[:300])
        self.assertEqual(rls_estado["tenant"], farmacia.id)
        self.assertTrue(PedidoDelivery.objects.filter(empresa=farmacia, id_externo="ord-9").exists())


class ApagarDadosLgpdTests(TestCase):
    def test_anonimiza_o_aparelho_em_todos_os_tenants(self):
        a, b = _empresa("pop-a@teste.local"), _empresa("pop-b@teste.local")
        for emp in (a, b):
            RegistroSintoma.objects.create(empresa=emp, device_id="aparelho-1", ip="10.0.0.1")
        outro = RegistroSintoma.objects.create(empresa=a, device_id="aparelho-2")
        with simular_rls(por_empresa=[RegistroSintoma]):
            resp = Client().post("/api/public/lgpd/apagar-meus-dados", data=json.dumps({}),
                                 content_type="application/json", HTTP_X_DEVICE_ID="aparelho-1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["detalhes"]["sintomas_anonimizados"], 2)
        self.assertFalse(RegistroSintoma.objects.filter(device_id="aparelho-1").exists())
        outro.refresh_from_db()
        self.assertEqual(outro.device_id, "aparelho-2")


class TenantTemporarioTests(SimpleTestCase):
    def _pg(self):
        conn = mock.MagicMock()
        conn.vendor = "postgresql"
        conn._rls_tenant = None
        return conn

    def test_restaura_o_tenant_do_chamador(self):
        conn = self._pg()
        with mock.patch("django.db.connection", conn):
            rls.fixar_tenant(5)
            with rls.tenant_temporario(9):
                self.assertEqual(rls.tenant_atual(), 9)
            self.assertEqual(rls.tenant_atual(), 5)

    def test_sem_tenant_anterior_volta_a_ficar_sem_tenant(self):
        conn = self._pg()
        with mock.patch("django.db.connection", conn):
            with rls.tenant_temporario(9):
                self.assertEqual(rls.tenant_atual(), 9)
            self.assertIsNone(rls.tenant_atual())

    def test_preservar_tenant_desfaz_troca_feita_dentro_do_bloco(self):
        conn = self._pg()
        with mock.patch("django.db.connection", conn):
            rls.fixar_tenant(3)
            with rls.preservar_tenant():
                rls.fixar_tenant(42)  # ex.: leitura da camada pública da população
            self.assertEqual(rls.tenant_atual(), 3)
