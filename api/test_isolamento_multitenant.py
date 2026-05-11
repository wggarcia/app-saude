"""
Multi-tenant isolation tests.
Each empresa must only be able to read and write its own data.
"""
import json
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, RegistroSintoma


def _make_empresa(nome, email, pacote="empresa_profissional_25"):
    return Empresa.objects.create(
        nome=nome,
        email=email,
        senha=make_password("Senha@123"),
        ativo=True,
        pacote_codigo=pacote,
        sessao_ativa_chave=f"chave-{email}",
    )


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id,
        "principal_kind": "empresa",
        "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave,
        "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _sintoma(empresa, estado="SP", cidade="São Paulo", grupo="Dengue"):
    return RegistroSintoma.objects.create(
        empresa=empresa,
        estado=estado,
        cidade=cidade,
        grupo=grupo,
        febre=True,
    )


class IsolamentoLimparCasosTests(TestCase):
    """Empresa A cannot delete Empresa B's records via /api/limpar-casos."""

    def test_limpar_casos_so_apaga_da_propria_empresa(self):
        empresa_a = _make_empresa("Empresa A", "a@example.com")
        empresa_b = _make_empresa("Empresa B", "b@example.com")

        _sintoma(empresa_a)
        _sintoma(empresa_b)

        client_a = _client_for(empresa_a)
        response = client_a.post("/api/limpar-casos")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["apagados"], 1)
        # Empresa B's record must survive
        self.assertEqual(RegistroSintoma.objects.filter(empresa=empresa_b).count(), 1)
        # Empresa A's record must be gone
        self.assertEqual(RegistroSintoma.objects.filter(empresa=empresa_a).count(), 0)

    def test_limpar_casos_sem_autenticacao_retorna_401(self):
        response = self.client.post("/api/limpar-casos")
        self.assertIn(response.status_code, [401, 302])


class IsolamentoPainelTests(TestCase):
    """/api/painel cannot be queried for a foreign empresa via GET param."""

    def test_painel_retorna_apenas_dados_da_propria_empresa(self):
        empresa_a = _make_empresa("Empresa Painel A", "painel-a@example.com")
        empresa_b = _make_empresa("Empresa Painel B", "painel-b@example.com")

        _sintoma(empresa_a)
        _sintoma(empresa_a)
        _sintoma(empresa_b)

        client_a = _client_for(empresa_a)
        # Even if someone passes empresa_b's id, they should only see empresa_a's data
        response = client_a.get(f"/api/painel?empresa_id={empresa_b.id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # empresa_a has 2 records, empresa_b has 1
        self.assertEqual(data["total"], 2)

    def test_painel_sem_autenticacao_retorna_401_ou_redirect(self):
        response = self.client.get("/api/painel")
        self.assertIn(response.status_code, [401, 302])


class IsolamentoInsightsNacionalTests(TestCase):
    """/api/insights-nacional must not aggregate across companies."""

    def test_insights_nacional_so_retorna_dados_da_propria_empresa(self):
        empresa_a = _make_empresa("Empresa Insights A", "insights-a@example.com")
        empresa_b = _make_empresa("Empresa Insights B", "insights-b@example.com")

        _sintoma(empresa_a, grupo="Dengue")
        _sintoma(empresa_b, grupo="COVID-19")

        client_a = _client_for(empresa_a)
        response = client_a.get("/api/insights-nacional")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        grupos = [item["doenca"] for item in data]
        self.assertIn("Dengue", grupos)
        self.assertNotIn("COVID-19", grupos)

    def test_insights_nacional_sem_autenticacao_retorna_401_ou_redirect(self):
        response = self.client.get("/api/insights-nacional")
        self.assertIn(response.status_code, [401, 302])


class IsolamentoLogoutTests(TestCase):
    """Token must be rejected after logout (sessao_ativa_chave cleared)."""

    def test_token_invalido_apos_logout(self):
        empresa = _make_empresa("Empresa Logout", "logout@example.com")
        client = _client_for(empresa)

        # Simulate logout by clearing sessao_ativa_chave
        empresa.sessao_ativa_chave = None
        empresa.save(update_fields=["sessao_ativa_chave"])

        # The old token cookie is still set on the client, but should be rejected
        response = client.get("/api/empresa/resumo")
        self.assertIn(response.status_code, [401, 302])

    def test_token_com_session_key_errada_e_rejeitado(self):
        empresa = _make_empresa("Empresa SessionKey", "sessionkey@example.com")

        # Build token with a stale session_key
        client = Client()
        payload = {
            "empresa_id": empresa.id,
            "principal_kind": "empresa",
            "principal_id": empresa.id,
            "session_key": "chave-antiga-invalida",
            "exp": timezone.now() + timedelta(hours=1),
        }
        client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

        response = client.get("/api/empresa/resumo")
        self.assertIn(response.status_code, [401, 302])


class IsolamentoEmailUnicoPorEmpresaTests(TestCase):
    """Two different companies can have users with the same email."""

    def test_mesmo_email_em_duas_empresas_distintas(self):
        from .models import EmpresaUsuario

        empresa_a = _make_empresa("Empresa Email A", "emailteste-a@example.com")
        empresa_b = _make_empresa("Empresa Email B", "emailteste-b@example.com")

        EmpresaUsuario.objects.create(
            empresa=empresa_a,
            nome="Joao",
            email="joao@corp.com",
            senha=make_password("Senha@123"),
        )
        # Should NOT raise — same email, different empresa
        usuario_b = EmpresaUsuario.objects.create(
            empresa=empresa_b,
            nome="Joao",
            email="joao@corp.com",
            senha=make_password("Senha@123"),
        )
        self.assertIsNotNone(usuario_b.id)

    def test_mesmo_email_na_mesma_empresa_levanta_erro(self):
        from django.db import IntegrityError

        from .models import EmpresaUsuario

        empresa = _make_empresa("Empresa Email Dup", "emaildup@example.com")
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome="Maria",
            email="maria@corp.com",
            senha=make_password("Senha@123"),
        )
        with self.assertRaises(IntegrityError):
            EmpresaUsuario.objects.create(
                empresa=empresa,
                nome="Maria2",
                email="maria@corp.com",
                senha=make_password("Senha@123"),
            )
