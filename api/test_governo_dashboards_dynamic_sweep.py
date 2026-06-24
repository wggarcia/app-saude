"""
Regressão da varredura dinâmica do Governo (jun/2026): 214 rotas de
api/governo e governo/ percorridas com dados reais via test client após
checagem mecânica de campos + crawler com dados reais de todos os
submódulos. 3 bugs reais encontrados:

  - api_cnes_sincronizar_todas / api_cnes_status / api_cnes_kpis
    filtravam UnidadeSaude por um campo "ativo" que não existe no
    model (o campo real é "status", com choices "ativa"/"inativa"/...).
    Sem try/except em volta, isso quebrava as 3 rotas com 500 garantido
    a cada chamada — o módulo CNES estava 100% inoperante.
  - api_vigilancia_dashboard chamava .date() em cima do resultado de
    TruncWeek sobre um DateField — TruncWeek num DateField já devolve
    um date, não datetime, então .date() sempre lançava AttributeError.
  - api_urgencia_dashboard usava TruncDate sobre data_atendimento, que
    já é DateField (não DateTimeField) — TruncDate nesse caso quebrava
    a query no SQLite com "user-defined function raised exception".
"""
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, UnidadeSaude, NotificacaoCompulsoria, SurtoEpidemiologico, AtendimentoUrgencia,
)


def _empresa_governo(email):
    return Empresa.objects.create(
        nome="Governo Dashboards", email=email,
        senha=make_password("123456"), ativo=True, tipo_conta=Empresa.TIPO_GOVERNO,
        pacote_codigo="governo_estado", sessao_ativa_chave=f"sessao-{email}",
    )


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


class CnesFiltroCampoCorretoTests(TestCase):
    def test_cnes_status_nao_quebra_com_unidades_ativas(self):
        empresa = _empresa_governo("gov-cnes-status@example.com")
        UnidadeSaude.objects.create(empresa=empresa, nome="UBS1", tipo="ubs", municipio="Cidade", uf="SP", status="ativa")
        client = _client_for(empresa)
        r = client.get("/api/governo/cnes/status/")
        self.assertEqual(r.status_code, 200)

    def test_cnes_kpis_nao_quebra_com_unidades_ativas(self):
        empresa = _empresa_governo("gov-cnes-kpis@example.com")
        UnidadeSaude.objects.create(empresa=empresa, nome="UBS1", tipo="ubs", municipio="Cidade", uf="SP", status="ativa")
        client = _client_for(empresa)
        r = client.get("/api/governo/cnes/kpis/")
        self.assertEqual(r.status_code, 200)

    def test_cnes_sincronizar_todas_nao_quebra_com_unidades_ativas(self):
        empresa = _empresa_governo("gov-cnes-sync@example.com")
        UnidadeSaude.objects.create(
            empresa=empresa, nome="UBS1", tipo="ubs", municipio="Cidade", uf="SP",
            status="ativa", cnes="1234567",
        )
        client = _client_for(empresa)
        r = client.post("/api/governo/cnes/sincronizar-todas/")
        self.assertEqual(r.status_code, 200)


class VigilanciaDashboardTests(TestCase):
    def test_dashboard_com_notificacoes_recentes_nao_lanca_excecao(self):
        empresa = _empresa_governo("gov-vigilancia@example.com")
        surto = SurtoEpidemiologico.objects.create(
            empresa=empresa, doenca="Dengue", municipio="Cidade", uf="SP", data_inicio=date.today(),
        )
        NotificacaoCompulsoria.objects.create(
            empresa=empresa, doenca="Dengue", data_notificacao=date.today(),
            municipio_notificacao="Cidade", uf_notificacao="SP", surto=surto,
        )
        client = _client_for(empresa)
        r = client.get("/api/governo/vigilancia/dashboard/")
        self.assertEqual(r.status_code, 200)


class UrgenciaDashboardTests(TestCase):
    def test_dashboard_com_atendimentos_nao_lanca_excecao(self):
        empresa = _empresa_governo("gov-urgencia@example.com")
        AtendimentoUrgencia.objects.create(
            empresa=empresa, tipo_unidade="upa", data_atendimento=date.today(), total_atendimentos=10,
        )
        client = _client_for(empresa)
        r = client.get("/api/governo/urgencia/dashboard/")
        self.assertEqual(r.status_code, 200)
