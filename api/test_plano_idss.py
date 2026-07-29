"""
Smoke test do IDSS (Índice de Desempenho da Saúde Suplementar) calculado a
partir dos dados reais da operadora — api_ps_idss.

Cobre:
  - operadora sem dados → nota None, faixa "Sem dados suficientes", 200 (não 500);
  - operadora com carteira + guias + faturamento + sinistro → nota calculada,
    4 dimensões presentes, isolamento por tenant (empresa) respeitado.
"""
from datetime import timedelta, date

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, PlanoSaude, BeneficiarioPlano, GuiaAutorizacao,
    Sinistro, FaturamentoBeneficiario,
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
        nome="Operadora Teste", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class IDSSVazioTests(TestCase):
    def test_operadora_sem_dados_retorna_sem_nota(self):
        empresa = _empresa_plano("idss-vazio@example.com")
        client = _client_for(empresa)
        r = client.get("/api/plano-saude/idss/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsNone(data["nota_final"])
        self.assertEqual(data["faixa"]["faixa"], 0)
        self.assertEqual(len(data["dimensoes"]), 4)


class IDSSComDadosTests(TestCase):
    def test_operadora_com_dados_calcula_nota_e_dimensoes(self):
        empresa = _empresa_plano("idss-dados@example.com")
        plano = PlanoSaude.objects.create(empresa=empresa, nome="Plano Ouro", modalidade="cooperativa")
        ben = BeneficiarioPlano.objects.create(plano=plano, nome="Fulano", situacao="ativo")
        # guia decidida (autorizada) → resolutividade
        GuiaAutorizacao.objects.create(
            plano=plano, beneficiario=ben, tipo="consulta", status="autorizada",
        )
        # faturamento + sinistro → sinistralidade (MLR)
        comp = date.today().strftime("%Y-%m")
        FaturamentoBeneficiario.objects.create(
            empresa=empresa, plano=plano, beneficiario=ben, competencia=comp, valor_mensalidade=1000,
        )
        Sinistro.objects.create(empresa=empresa, plano=plano, beneficiario=ben, valor_total=750)

        client = _client_for(empresa)
        r = client.get("/api/plano-saude/idss/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsNotNone(data["nota_final"])
        self.assertEqual(len(data["dimensoes"]), 4)
        codigos = {d["codigo"] for d in data["dimensoes"]}
        self.assertEqual(codigos, {"IDQS", "IDGA", "IDSF", "IDGR"})
        self.assertGreater(data["cobertura_pesos"], 0)

    def test_isolamento_por_tenant(self):
        """A nota de uma operadora não pode ver dados de outra (LGPD)."""
        emp_a = _empresa_plano("idss-a@example.com")
        emp_b = _empresa_plano("idss-b@example.com")
        plano_b = PlanoSaude.objects.create(empresa=emp_b, nome="Plano B")
        BeneficiarioPlano.objects.create(plano=plano_b, nome="Beltrano B", situacao="ativo")

        client_a = _client_for(emp_a)
        r = client_a.get("/api/plano-saude/idss/")
        data = r.json()
        # A não tem carteira → continuidade de cobertura indisponível pra A
        idqs = next(d for d in data["dimensoes"] if d["codigo"] == "IDQS")
        continuidade = next(c for c in idqs["componentes"] if c["codigo"] == "IDQS-3")
        self.assertFalse(continuidade["disponivel"])
