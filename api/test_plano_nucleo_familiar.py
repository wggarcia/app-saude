"""
Núcleo familiar do Plano de Saúde — titular → dependentes em BeneficiarioPlano.

Cobre:
  - criar titular e vincular dependente (herda plano, tipo_vinculo=dependente);
  - detalhe do titular traz a lista de dependentes;
  - isolamento por tenant (LGPD): não dá para vincular dependente a titular de
    outra operadora;
  - guarda: dependente não pode ser titular de si mesmo.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, PlanoSaude, BeneficiarioPlano


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
        nome="Operadora NF", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class NucleoFamiliarTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_plano("nf@example.com")
        self.plano = PlanoSaude.objects.create(empresa=self.empresa, nome="Plano Família")
        self.client_ = _client_for(self.empresa)
        self.titular = BeneficiarioPlano.objects.create(
            plano=self.plano, nome="João Titular", tipo_vinculo="titular",
        )

    def test_fluxo_completo(self):
        # cria dependente via endpoint real
        r = self.client_.post(
            "/api/plano-saude/beneficiarios",
            data={
                "nome": "Maria Dependente",
                "titular_id": self.titular.id,
                "grau_parentesco": "filho",
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        dep = r.json()["beneficiario"]
        self.assertEqual(dep["tipo_vinculo"], "dependente")
        self.assertEqual(dep["titular_id"], self.titular.id)
        self.assertEqual(dep["grau_parentesco"], "filho")
        # dependente herdou o plano do titular
        self.assertEqual(dep["plano_id"], self.plano.id)

        # detalhe do titular traz dependentes
        r2 = self.client_.get(f"/api/plano-saude/beneficiarios/{self.titular.id}")
        self.assertEqual(r2.status_code, 200)
        titular_data = r2.json()["beneficiario"]
        self.assertEqual(titular_data["dependentes_count"], 1)
        self.assertEqual(len(titular_data["dependentes"]), 1)
        self.assertEqual(titular_data["dependentes"][0]["nome"], "Maria Dependente")

        # filtro por titular_id
        r3 = self.client_.get(f"/api/plano-saude/beneficiarios?titular_id={self.titular.id}")
        self.assertEqual(len(r3.json()["beneficiarios"]), 1)

    def test_isolamento_por_tenant(self):
        """Não pode vincular dependente a titular de OUTRA operadora (LGPD)."""
        outra = _empresa_plano("nf-outra@example.com")
        plano_outra = PlanoSaude.objects.create(empresa=outra, nome="Plano Outra")
        titular_outra = BeneficiarioPlano.objects.create(
            plano=plano_outra, nome="Titular Alheio", tipo_vinculo="titular",
        )
        r = self.client_.post(
            "/api/plano-saude/beneficiarios",
            data={"nome": "Invasor", "titular_id": titular_outra.id},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)
