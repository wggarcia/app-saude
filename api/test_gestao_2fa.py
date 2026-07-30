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

from .models import Empresa, TwoFactorTOTP
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
