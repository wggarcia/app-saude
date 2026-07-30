"""
Smoke dos módulos hospitalares que antes mostravam "em construção" e agora
renderizam o template genérico (hospital_modulo_generico.html) consumindo as
APIs já existentes. Garante 200 + template certo + config injetada.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa_hospital(email, pacote="hospital_grupo"):
    return Empresa.objects.create(
        nome="Hospital Render", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


class HospitalModuloGenericoTests(TestCase):
    def test_qualidade_renderiza_template_generico(self):
        empresa = _empresa_hospital("hq@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/qualidade/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Qualidade (NSP)", html)
        # não é mais a tela "em construção"
        self.assertNotIn("em construção", html)
        # config data-driven injetada
        self.assertIn("/api/hospital/qualidade/kpis", html)
        self.assertIn("/api/hospital/qualidade/incidentes", html)
        self.assertIn('id="kpis"', html)

    def test_nutricao_renderiza_template_generico(self):
        empresa = _empresa_hospital("hn@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/nutricao/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Nutricao", html)
        self.assertIn("/api/hospital/nutricao/dietas", html)
        self.assertNotIn("em construção", html)
