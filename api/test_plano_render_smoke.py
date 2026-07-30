"""
Smoke de renderização: garante que a página de gestão do plano de saúde e o
Portal RH renderizam server-side sem erro de template, e que as novas abas/JS
estão presentes no HTML entregue.
"""
from datetime import timedelta, date

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, PlanoSaude, ContratoGrupo, PortalRHToken


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa_plano(email):
    return Empresa.objects.create(
        nome="Operadora Render", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class RenderSmokeTests(TestCase):
    def test_gestao_page_renderiza_com_novas_abas(self):
        empresa = _empresa_plano("render@example.com")
        # cria uma modalidade para exercitar o rótulo dinâmico de identidade
        PlanoSaude.objects.create(empresa=empresa, nome="Plano X", modalidade="cooperativa")
        client = _client_for(empresa)
        r = client.get("/plano-saude/gestao/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        # rótulo de identidade dinâmico
        self.assertIn("Cooperativa Médica", html)
        # novas abas/painéis presentes
        for marcador in [
            'id="tab-atuarial"', 'id="tab-ressarcimento"', 'id="tab-nps"',
            'id="tab-intercambio"', 'id="tab-portalrh"', 'id="modalIDSS"',
            'function carregarAtuarial', 'function carregarPortalRh',
            'function carregarIntercambio', 'function verificarRol',
        ]:
            self.assertIn(marcador, html, f"faltou no HTML: {marcador}")

    def test_portal_rh_page_publico_renderiza(self):
        empresa = _empresa_plano("render-rh@example.com")
        plano = PlanoSaude.objects.create(empresa=empresa, nome="Plano X")
        hoje = date.today()
        contrato = ContratoGrupo.objects.create(
            empresa_operadora=empresa, plano=plano, razao_social="Cliente Render SA",
            data_inicio=hoje, data_renovacao=hoje + timedelta(days=365),
        )
        tok = PortalRHToken.objects.create(contrato=contrato, token="tok-render-123")
        # público, sem login
        r = Client().get(f"/plano-saude/portal-rh/{tok.token}/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Portal RH", r.content.decode())

    def test_portal_rh_token_invalido_pagina_404(self):
        r = Client().get("/plano-saude/portal-rh/inexistente/", secure=True)
        self.assertEqual(r.status_code, 404)
