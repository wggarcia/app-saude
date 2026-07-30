"""
2FA/TOTP do console de TI: ciclo setup → confirmar → status → desativar,
incluindo backup code e rejeição de código inválido. TOTP real (RFC 6238),
sem pyotp.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, EmpresaUsuario, RBACAtribuicao, RBACPermissao, TwoFactorTOTP
from .services import stepup
from .services import totp as totp_service


def _empresa_ti(email):
    return Empresa.objects.create(
        nome="Empresa TI", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="empresa_starter_5",
        sessao_ativa_chave=f"sessao-{email}",
    )


def _client_for(empresa):
    c = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa_admin", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    c.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return c


class TwoFactorTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_ti("ti@example.com")
        self.client_ = _client_for(self.empresa)

    def _setup(self):
        r = self.client_.post("/api/gestao/2fa/setup", data={}, content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["secret"]

    def test_ciclo_completo(self):
        secret = self._setup()
        # ainda não está ativo até confirmar
        self.assertFalse(TwoFactorTOTP.objects.get(empresa=self.empresa).ativo)

        # código errado é rejeitado
        r_bad = self.client_.post("/api/gestao/2fa/confirmar", data={"codigo": "000000"},
                                  content_type="application/json", secure=True)
        self.assertEqual(r_bad.status_code, 400)

        # código correto ativa e devolve backup codes
        import time
        codigo = totp_service._codigo_no_tempo(secret, time.time())
        r_ok = self.client_.post("/api/gestao/2fa/confirmar", data={"codigo": codigo},
                                 content_type="application/json", secure=True)
        self.assertEqual(r_ok.status_code, 200, r_ok.content)
        body = r_ok.json()
        self.assertTrue(body["ativo"])
        self.assertEqual(len(body["backup_codes"]), 8)
        cfg = TwoFactorTOTP.objects.get(empresa=self.empresa)
        self.assertTrue(cfg.ativo)
        # o segredo cru dos backup codes NÃO é guardado — só hash
        self.assertNotIn(body["backup_codes"][0], cfg.backup_codes)

        # desativa com backup code (uso único)
        backup = body["backup_codes"][0]
        r_off = self.client_.post("/api/gestao/2fa/desativar", data={"codigo": backup},
                                  content_type="application/json", secure=True)
        self.assertEqual(r_off.status_code, 200, r_off.content)
        cfg.refresh_from_db()
        self.assertFalse(cfg.ativo)
        self.assertEqual(cfg.secret, "")

    def test_nao_reconfigura_se_ja_ativo(self):
        secret = self._setup()
        import time
        codigo = totp_service._codigo_no_tempo(secret, time.time())
        self.client_.post("/api/gestao/2fa/confirmar", data={"codigo": codigo},
                          content_type="application/json", secure=True)
        # tentar setup de novo com 2FA ativo → 400
        r = self.client_.post("/api/gestao/2fa/setup", data={}, content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 400)


class StepUpTests(TestCase):
    """Step-up na entrada do console de TI: só cobra de quem ativou o 2FA."""

    def setUp(self):
        self.empresa = _empresa_ti("stepup@example.com")
        self.client_ = _client_for(self.empresa)

    def _ativar_2fa(self):
        r = self.client_.post("/api/gestao/2fa/setup", data={},
                              content_type="application/json", secure=True)
        secret = r.json()["secret"]
        import time
        codigo = totp_service._codigo_no_tempo(secret, time.time())
        r2 = self.client_.post("/api/gestao/2fa/confirmar", data={"codigo": codigo},
                               content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 200, r2.content)
        return secret, r2.json()["backup_codes"]

    def _limpar_stepup(self):
        """Simula uma sessão nova (sem o cookie de step-up já confirmado)."""
        self.client_.cookies.pop(stepup.COOKIE, None)

    def test_sem_2fa_ativo_nada_e_exigido(self):
        # nunca ativou 2FA → nenhuma exigência de step-up
        cfg = stepup.config_ativa(self.empresa, None)
        self.assertIsNone(cfg)
        r = self.client_.get("/api/gestao/uso-api", secure=True)
        self.assertNotEqual(r.status_code, 403)

    def test_api_de_ti_bloqueada_ate_confirmar(self):
        secret, _ = self._ativar_2fa()
        self._limpar_stepup()

        r = self.client_.get("/api/gestao/uso-api", secure=True)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json().get("stepup_2fa"))

        import time
        codigo = totp_service._codigo_no_tempo(secret, time.time())
        r_ok = self.client_.post("/api/gestao/2fa/verificar", data={"codigo": codigo},
                                 content_type="application/json", secure=True)
        self.assertEqual(r_ok.status_code, 200, r_ok.content)
        self.assertIn(stepup.COOKIE, r_ok.cookies)

        # com o step-up confirmado a mesma API libera
        r_pos = self.client_.get("/api/gestao/uso-api", secure=True)
        self.assertNotEqual(r_pos.status_code, 403)

    def test_backup_code_e_de_uso_unico(self):
        _, backups = self._ativar_2fa()
        self._limpar_stepup()

        r1 = self.client_.post("/api/gestao/2fa/verificar", data={"codigo": backups[0]},
                               content_type="application/json", secure=True)
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertTrue(r1.json()["backup_usado"])
        self.assertEqual(r1.json()["backup_restantes"], 7)

        # o mesmo código não vale duas vezes
        self._limpar_stepup()
        r2 = self.client_.post("/api/gestao/2fa/verificar", data={"codigo": backups[0]},
                               content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 400)

    def test_bloqueio_por_forca_bruta(self):
        self._ativar_2fa()
        self._limpar_stepup()

        for _ in range(stepup.LIMITE_FALHAS):
            r = self.client_.post("/api/gestao/2fa/verificar", data={"codigo": "000000"},
                                  content_type="application/json", secure=True)
            self.assertEqual(r.status_code, 400)

        cfg = TwoFactorTOTP.objects.get(empresa=self.empresa)
        self.assertIsNotNone(cfg.bloqueado_ate)
        # bloqueado: nem o código certo passa enquanto o castigo durar
        r_block = self.client_.post("/api/gestao/2fa/verificar", data={"codigo": "111111"},
                                    content_type="application/json", secure=True)
        self.assertEqual(r_block.status_code, 429)

    def test_cookie_nao_vale_em_outra_sessao(self):
        """Novo login (session_key diferente) invalida o step-up anterior."""
        self._ativar_2fa()  # já deixa o cookie de step-up válido
        r = self.client_.get("/api/gestao/uso-api", secure=True)
        self.assertNotEqual(r.status_code, 403)

        # relogin: a chave de sessão ativa muda, o cookie antigo deixa de casar
        self.empresa.sessao_ativa_chave = "sessao-nova"
        self.empresa.save(update_fields=["sessao_ativa_chave"])
        novo = _client_for(self.empresa)
        novo.cookies[stepup.COOKIE] = self.client_.cookies[stepup.COOKIE].value
        r2 = novo.get("/api/gestao/uso-api", secure=True)
        self.assertEqual(r2.status_code, 403)
        self.assertTrue(r2.json().get("stepup_2fa"))

class StepUpPaginaTests(TestCase):
    """A página do console só é liberada com o step-up feito.

    Usa um EmpresaUsuario de TI com a permissão RBAC `plataforma_ti` — a conta
    admin da empresa não passa no gate da página (regra pré-existente: o console
    exige um login dedicado de TI)."""

    def setUp(self):
        self.empresa = _empresa_ti("console@example.com")
        self.usuario = EmpresaUsuario.objects.create(
            empresa=self.empresa, nome="TI Responsável", email="ti.user@example.com",
            senha=make_password("123456"), perfil=EmpresaUsuario.PERFIL_TI, ativo=True,
            sessao_ativa_chave="sessao-ti-user", sessao_ativa_em=timezone.now(),
        )
        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo="plataforma_ti",
            defaults={"descricao": "Console de TI", "modulo": "plataforma"},
        )
        RBACAtribuicao.objects.create(empresa=self.empresa, usuario=self.usuario, permissao=permissao)

        self.client_ = Client()
        payload = {
            "empresa_id": self.empresa.id, "principal_kind": "usuario_empresa",
            "principal_id": self.usuario.id, "session_key": self.usuario.sessao_ativa_chave,
            "exp": timezone.now() + timedelta(hours=1),
        }
        self.client_.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

    def test_console_abre_sem_2fa_e_pede_codigo_depois_de_ativar(self):
        # sem 2FA ativo o console abre direto (opt-in preservado)
        r0 = self.client_.get("/gestao/plataforma/", secure=True)
        self.assertEqual(r0.status_code, 200)
        self.assertNotContains(r0, "Confirme o código para entrar")

        # ativa o 2FA do usuário de TI
        secret = self.client_.post("/api/gestao/2fa/setup", data={},
                                   content_type="application/json", secure=True).json()["secret"]
        import time
        codigo = totp_service._codigo_no_tempo(secret, time.time())
        r_conf = self.client_.post("/api/gestao/2fa/confirmar", data={"codigo": codigo},
                                   content_type="application/json", secure=True)
        self.assertEqual(r_conf.status_code, 200, r_conf.content)
        # o 2FA ficou no usuário, não na conta da empresa
        self.assertTrue(TwoFactorTOTP.objects.filter(
            empresa=self.empresa, usuario=self.usuario, ativo=True).exists())

        # nova sessão (sem o cookie de step-up) → tela de desafio
        self.client_.cookies.pop(stepup.COOKIE, None)
        r1 = self.client_.get("/gestao/plataforma/", secure=True)
        self.assertContains(r1, "Confirme o código para entrar", status_code=200)

        # confirmado o código, o console abre
        codigo2 = totp_service._codigo_no_tempo(secret, time.time())
        r_ver = self.client_.post("/api/gestao/2fa/verificar", data={"codigo": codigo2},
                                  content_type="application/json", secure=True)
        self.assertEqual(r_ver.status_code, 200, r_ver.content)
        r2 = self.client_.get("/gestao/plataforma/", secure=True)
        self.assertEqual(r2.status_code, 200)
        self.assertNotContains(r2, "Confirme o código para entrar")
