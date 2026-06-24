"""
Teste do alerta de vencimento de PGR/PCMSO — exigência da NR-1 (PGR) e
NR-7 (PCMSO). Antes desta auditoria, o sistema de alertas (api/views_alertas.py)
verificava ASO, EPI, treinamento NR e agendamento, mas nunca a validade do
PGR/PCMSO em si — uma empresa podia ficar anos com o documento vencido sem
nenhum aviso.
"""
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, DocumentoSST


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


def _empresa(email):
    return Empresa.objects.create(
        nome="Empresa Alertas Teste",
        email=email,
        senha=make_password("123456"),
        ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA,
        pacote_codigo="empresa_profissional_25",
        sessao_ativa_chave=f"sessao-{email}",
    )


class AlertaPGRVencidoTests(TestCase):
    def test_sem_pgr_gera_alerta_critico(self):
        empresa = _empresa("alerta-sem-pgr@example.com")
        client = _client_for(empresa)

        r = client.get("/api/alertas/")
        self.assertEqual(r.status_code, 200)
        titulos = [a["titulo"] for a in r.json()["alertas"]]
        self.assertIn("PGR não gerado", titulos)
        self.assertIn("PCMSO não gerado", titulos)

    def test_pgr_vencido_gera_alerta_critico(self):
        empresa = _empresa("alerta-pgr-vencido@example.com")
        DocumentoSST.objects.create(
            empresa=empresa, tipo="PGR", titulo="PGR antigo",
            data_emissao=date.today() - timedelta(days=800),
            data_validade=date.today() - timedelta(days=70),
        )
        client = _client_for(empresa)

        r = client.get("/api/alertas/")
        body = r.json()
        alerta_pgr = next(a for a in body["alertas"] if a["titulo"] == "PGR vencido")
        self.assertEqual(alerta_pgr["severidade"], "critico")

    def test_pgr_valido_nao_gera_alerta(self):
        empresa = _empresa("alerta-pgr-valido@example.com")
        DocumentoSST.objects.create(
            empresa=empresa, tipo="PGR", titulo="PGR vigente",
            data_emissao=date.today(),
            data_validade=date.today() + timedelta(days=400),
        )
        DocumentoSST.objects.create(
            empresa=empresa, tipo="PCMSO", titulo="PCMSO vigente",
            data_emissao=date.today(),
            data_validade=date.today() + timedelta(days=300),
        )
        client = _client_for(empresa)

        r = client.get("/api/alertas/")
        titulos = [a["titulo"] for a in r.json()["alertas"]]
        self.assertNotIn("PGR não gerado", titulos)
        self.assertNotIn("PGR vencido", titulos)
        self.assertNotIn("PCMSO não gerado", titulos)
        self.assertNotIn("PCMSO vencido", titulos)
