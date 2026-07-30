"""
Análise atuarial do Plano de Saúde — PMPM por faixa etária/produto e reajuste.
"""
from datetime import timedelta, date

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, PlanoSaude, BeneficiarioPlano, Sinistro, FaturamentoBeneficiario,
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
        nome="Operadora Atuarial", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class AtuarialTests(TestCase):
    def test_pmpm_por_faixa_e_reajuste(self):
        empresa = _empresa_plano("atu@example.com")
        plano = PlanoSaude.objects.create(empresa=empresa, nome="Plano Base")
        hoje = date.today()
        # Beneficiário de ~40 anos → faixa 39-43
        ben = BeneficiarioPlano.objects.create(
            plano=plano, nome="Quarentao", situacao="ativo",
            data_nascimento=date(hoje.year - 40, 1, 1),
        )
        FaturamentoBeneficiario.objects.create(
            empresa=empresa, plano=plano, beneficiario=ben,
            competencia=hoje.strftime("%Y-%m"), valor_mensalidade=1000,
        )
        # sinistro alto → MLR > 70 → reajuste técnico sugerido > 0
        Sinistro.objects.create(empresa=empresa, plano=plano, beneficiario=ben, valor_total=900)

        client = _client_for(empresa)
        r = client.get("/api/plano-saude/atuarial?meses=1")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(d["vidas_ativas"], 1)
        self.assertEqual(len(d["pmpm_por_faixa"]), 10)  # 10 faixas RN63
        faixa_40 = next(f for f in d["pmpm_por_faixa"] if f["faixa"] == "39-43")
        self.assertEqual(faixa_40["vidas"], 1)
        self.assertGreater(faixa_40["pmpm"], 0)
        self.assertIsNotNone(d["mlr"])
        self.assertGreater(d["reajuste_tecnico_sugerido"], 0)  # MLR 90% > meta 70%

    def test_isolamento_por_tenant(self):
        empresa = _empresa_plano("atu-a@example.com")
        outra = _empresa_plano("atu-b@example.com")
        plano_b = PlanoSaude.objects.create(empresa=outra, nome="Plano B")
        BeneficiarioPlano.objects.create(plano=plano_b, nome="Alheio", situacao="ativo")
        client = _client_for(empresa)
        d = client.get("/api/plano-saude/atuarial").json()
        self.assertEqual(d["vidas_ativas"], 0)
