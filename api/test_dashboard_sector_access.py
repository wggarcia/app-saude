from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa


class DashboardSectorAccessTests(TestCase):
    def _client_for(self, empresa):
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

    def _empresa(self, nome, email, pacote_codigo):
        return Empresa.objects.create(
            nome=nome,
            email=email,
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo=pacote_codigo,
            sessao_ativa_chave=f"sessao-{pacote_codigo}",
        )

    def test_farmacia_so_acessa_ambiente_farmacia(self):
        farmacia = self._empresa("Farmacia Cliente", "farmacia-setor@example.com", "farmacia_rede_regional")
        client = self._client_for(farmacia)

        self.assertEqual(client.get("/dashboard/").status_code, 302)
        self.assertEqual(client.get("/dashboard/")["Location"], "/dashboard-farmacia/")
        self.assertEqual(client.get("/dashboard-hospital/").status_code, 302)
        self.assertEqual(client.get("/dashboard-hospital/")["Location"], "/dashboard-farmacia/")

        response = client.get("/dashboard-farmacia/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SolusCRT Farmácia")
        self.assertContains(response, "Central de Inteligência Farmacêutica")
        self.assertNotContains(response, "Hub Hospitalar")

    def test_hospital_so_acessa_ambiente_hospital(self):
        hospital = self._empresa("Hospital Cliente", "hospital-setor@example.com", "hospital_medio")
        client = self._client_for(hospital)

        self.assertEqual(client.get("/dashboard/").status_code, 302)
        self.assertEqual(client.get("/dashboard/")["Location"], "/dashboard-hospital/")
        self.assertEqual(client.get("/dashboard-farmacia/").status_code, 302)
        self.assertEqual(client.get("/dashboard-farmacia/")["Location"], "/dashboard-hospital/")

        response = client.get("/dashboard-hospital/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SolusCRT Hospital")
        self.assertContains(response, "Centro de Inteligência Assistencial")
        self.assertNotContains(response, "Hub Farmacia")

    def test_empresa_comum_nao_acessa_ambientes_setoriais(self):
        empresa = self._empresa("Empresa Cliente", "empresa-setor@example.com", "empresa_profissional_25")
        client = self._client_for(empresa)

        self.assertEqual(client.get("/dashboard-farmacia/").status_code, 302)
        self.assertEqual(client.get("/dashboard-farmacia/")["Location"], "/dashboard-empresa/")
        self.assertEqual(client.get("/dashboard-hospital/").status_code, 302)
        self.assertEqual(client.get("/dashboard-hospital/")["Location"], "/dashboard-empresa/")
        self.assertEqual(client.get("/dashboard/").status_code, 302)
        self.assertEqual(client.get("/dashboard/")["Location"], "/dashboard-empresa/")

        response = client.get("/dashboard-empresa/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SolusCRT")
        self.assertContains(response, "Saúde e Segurança do Trabalho")
