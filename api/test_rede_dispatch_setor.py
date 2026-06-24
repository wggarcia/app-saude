"""
Achado ao investigar por que uma conta de Rede de Saúde caía no painel
genérico de Empresa/SST após o login, em vez do painel próprio
(/rede/gestao/). Causa raiz: 3 funções de despacho por setor tratavam
explicitamente "farmacia"/"hospital"/"governo"/"plano_saude" mas nunca
ganharam um branch para "rede" — então toda conta de Rede caía no
default, igual a uma conta de SST/Empresa qualquer:

  - api/services/auth_session.py::destino_conta (usado no login)
  - api/views_corporativo.py::dashboard_empresa_corporativo (a view de
    /dashboard-empresa/, que é o "default" acima)
  - api/services/dashboard_core.py::dashboard_url_por_setor / setor_label
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa
from .services.auth_session import destino_conta
from .services.dashboard_core import dashboard_url_por_setor, setor_label


def _empresa_rede(email):
    return Empresa.objects.create(
        nome="Rede Teste", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="rede_nacional",
        sessao_ativa_chave="", max_dispositivos=10, max_usuarios=10,
    )


class DestinoContaRedeTests(TestCase):
    def test_destino_conta_de_rede_aponta_para_rede_gestao(self):
        empresa = _empresa_rede("rede-destino@example.com")
        self.assertEqual(destino_conta(empresa), "/rede/gestao/")


class DashboardCoreRedeTests(TestCase):
    def test_dashboard_url_por_setor_rede(self):
        self.assertEqual(dashboard_url_por_setor("rede"), "/rede/gestao/")

    def test_setor_label_rede(self):
        self.assertEqual(setor_label("rede"), "Rede de Saúde")


class DashboardEmpresaCorporativoRedeTests(TestCase):
    def test_login_de_conta_rede_redireciona_para_rede_gestao(self):
        empresa = _empresa_rede("rede-dashboard@example.com")
        client = Client()
        payload = {
            "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
            "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
        }
        client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
        r = client.get("/dashboard-empresa/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/rede/gestao/")
