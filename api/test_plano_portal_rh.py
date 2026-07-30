"""
Portal RH B2B — empresa-contratante gerencia vidas via token; operadora aprova.
"""
from datetime import timedelta, date

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, PlanoSaude, ContratoGrupo, PortalRHToken,
    SolicitacaoVidaRH, BeneficiarioPlano,
)


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
        nome="Operadora RH", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


def _contrato(empresa, plano):
    hoje = date.today()
    return ContratoGrupo.objects.create(
        empresa_operadora=empresa, plano=plano, razao_social="Empresa Cliente SA",
        cnpj="11.111.111/0001-11", total_vidas=0, mensalidade_total=5000,
        data_inicio=hoje, data_renovacao=hoje + timedelta(days=365),
    )


class PortalRHTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_plano("prh@example.com")
        self.plano = PlanoSaude.objects.create(empresa=self.empresa, nome="Plano Empresarial")
        self.contrato = _contrato(self.empresa, self.plano)
        self.client_ = _client_for(self.empresa)

    def test_gerar_token_e_fluxo_inclusao(self):
        # operadora gera token
        r = self.client_.post("/api/plano-saude/rh/token",
                              data={"contrato_id": self.contrato.id}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        url = r.json()["portal_url"]
        token = url.rstrip("/").split("/")[-1]

        # portal público lê dados (sem login)
        pub = Client()
        rd = pub.get(f"/api/plano-saude/rh/portal/{token}/dados")
        self.assertEqual(rd.status_code, 200)
        self.assertEqual(rd.json()["contrato"]["razao_social"], "Empresa Cliente SA")

        # RH solicita inclusão
        rs = pub.post(f"/api/plano-saude/rh/portal/{token}/solicitar",
                      data={"tipo": "inclusao", "nome": "Novo Funcionario", "cpf": "123"},
                      content_type="application/json")
        self.assertEqual(rs.status_code, 201, rs.content)

        # operadora vê a solicitação pendente
        pend = self.client_.get("/api/plano-saude/rh/solicitacoes?status=pendente").json()
        self.assertEqual(len(pend["solicitacoes"]), 1)
        sol_id = pend["solicitacoes"][0]["id"]

        # operadora aprova → cria a vida ligada ao contrato
        ra = self.client_.put(f"/api/plano-saude/rh/solicitacoes/{sol_id}",
                              data={"acao": "aprovar"}, content_type="application/json")
        self.assertEqual(ra.json()["novo_status"], "aprovada")
        vida = BeneficiarioPlano.objects.get(nome="Novo Funcionario")
        self.assertEqual(vida.contrato_grupo_id, self.contrato.id)
        self.assertEqual(vida.plano_id, self.plano.id)
        self.assertEqual(vida.situacao, "ativo")

    def test_token_invalido(self):
        pub = Client()
        r = pub.get("/api/plano-saude/rh/portal/token-invalido/dados")
        self.assertEqual(r.status_code, 404)

    def test_isolamento_por_tenant(self):
        """Operadora não gera token para contrato de outra operadora."""
        outra = _empresa_plano("prh-outra@example.com")
        plano_o = PlanoSaude.objects.create(empresa=outra, nome="Plano Outra")
        contrato_o = _contrato(outra, plano_o)
        r = self.client_.post("/api/plano-saude/rh/token",
                              data={"contrato_id": contrato_o.id}, content_type="application/json")
        self.assertEqual(r.status_code, 404)
