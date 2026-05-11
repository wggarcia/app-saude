import json
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa
from .models import (
    CompetenciaItemCorporativo,
    EmpresaCargoCorporativo,
    EmpresaSetor,
    EmpresaUnidade,
    TrilhaCompetenciaCorporativa,
)


class DashboardCorporativoTests(TestCase):
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

    def test_empresa_acessa_dashboard_corporativo(self):
        empresa = self._empresa("Empresa Corporativa", "empresa-corp@example.com", "empresa_profissional_25")
        client = self._client_for(empresa)

        response = client.get("/dashboard-empresa/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SolusCRT")
        self.assertContains(response, "Saúde e Segurança do Trabalho")
        self.assertContains(response, 'href="/logout/"')

    def test_hospital_nao_acessa_dashboard_corporativo(self):
        hospital = self._empresa("Hospital Cliente", "hospital-corp@example.com", "hospital_medio")
        client = self._client_for(hospital)

        response = client.get("/dashboard-empresa/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/dashboard-hospital/")

    def test_api_empresa_corporativo_resumo(self):
        empresa = self._empresa("Empresa Corporativa", "empresa-corp-api@example.com", "empresa_profissional_25")
        client = self._client_for(empresa)

        response = client.get("/api/empresa/resumo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product"]["name"], "SolusCRT Corporativo")

    def test_api_empresa_corporativo_resumo_expone_snapshot_de_competencia(self):
        empresa = self._empresa("Empresa Competencia", "empresa-competencia@example.com", "empresa_profissional_25")
        unidade = EmpresaUnidade.objects.create(empresa=empresa, nome="Base Offshore")
        setor = EmpresaSetor.objects.create(empresa=empresa, unidade=unidade, nome="Eletrica")
        cargo = EmpresaCargoCorporativo.objects.create(empresa=empresa, setor=setor, nome="Eletricista de Sonda")
        trilha = TrilhaCompetenciaCorporativa.objects.create(
            empresa=empresa,
            cargo=cargo,
            titulo="Trilha Eletrica de Campo",
            nivel_alvo="pleno",
        )
        CompetenciaItemCorporativo.objects.create(
            empresa=empresa,
            trilha=trilha,
            titulo="Manutencao preventiva em painel de potencia",
            tipo=CompetenciaItemCorporativo.TIPO_PRATICA,
        )
        client = self._client_for(empresa)

        response = client.get("/api/empresa/resumo")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["competence"]["tracks_count"], 1)
        self.assertEqual(data["competence"]["roles_count"], 1)
        self.assertEqual(data["competence"]["critical_functions_count"], 0)

    def test_colaborador_app_publico_abre_para_empresa(self):
        empresa = self._empresa("Empresa Corporativa", "empresa-colab@example.com", "empresa_profissional_25")

        response = self.client.get(f"/colaborador-mobile/c/{empresa.codigo_acesso_corporativo}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check-ins seguros")
        self.assertContains(response, "SolusCRT Colaborador")

    def test_checkin_diario_alimenta_resumo_corporativo(self):
        empresa = self._empresa("Empresa Corporativa", "empresa-checkin@example.com", "empresa_profissional_25")
        corporate_client = self._client_for(empresa)

        for idx in range(8):
            response = self.client.post(
                f"/api/corporativo/{empresa.codigo_acesso_corporativo}/checkin-diario",
                data=json.dumps({
                    "alias_code": f"anon-{idx}",
                    "unit_name": "Matriz",
                    "sector_name": "Operacao",
                    "shift_name": "Manha",
                    "mood": 4,
                    "energy": 4,
                    "stress": 2,
                    "sleep_quality": 4,
                    "physical_pain": 2,
                    "fatigue": 2,
                    "anxiety": 2,
                }),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)

        resumo = corporate_client.get("/api/empresa/resumo")

        self.assertEqual(resumo.status_code, 200)
        self.assertEqual(resumo.json()["summary"]["respondents"], 8)
        self.assertTrue(resumo.json()["privacy"]["ready"])
        self.assertEqual(resumo.json()["top_units"][0]["name"], "Matriz")
