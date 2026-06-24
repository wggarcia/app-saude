"""
Teste de regressão do gerador de PGR (api/views_pgr_pcmso.py).

Bug encontrado em auditoria de NR-1 (jun/2026): api_pgr_gerar importava um
modelo inexistente (AgenteNocivoSST) e api_pgr_gerar/api_pgr_pdf consultavam
um campo inexistente em RiscoOcupacional ("tipo" em vez de "tipo_risco") —
toda chamada a "Gerar PGR" retornava 500 e o documento nunca era produzido.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, RiscoOcupacional


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


def _empresa():
    return Empresa.objects.create(
        nome="Empresa PGR Teste",
        email="pgr-teste@example.com",
        senha=make_password("123456"),
        ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA,
        pacote_codigo="empresa_profissional_25",
        sessao_ativa_chave="sessao-pgr-teste",
    )


class PGRGeracaoTests(TestCase):
    def test_gera_pgr_com_risco_psicossocial_no_inventario(self):
        empresa = _empresa()
        client = _client_for(empresa)

        RiscoOcupacional.objects.create(
            empresa=empresa,
            setor="Atendimento",
            tipo_risco="psicossocial",
            agente="Sobrecarga de trabalho",
            descricao="Metas inalcançáveis reportadas em pesquisa interna",
            nivel="IV",
        )
        RiscoOcupacional.objects.create(
            empresa=empresa,
            setor="Produção",
            tipo_risco="fisico",
            agente="Ruído",
        )

        r = client.post("/api/sst/pgr/gerar/", data="{}", content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["total_riscos"], 2)
        doc_id = body["data"]["id"]

        r = client.get(f"/api/sst/pgr/{doc_id}/pdf/")
        self.assertEqual(r.status_code, 200, getattr(r, "content", b"")[:300])
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertGreater(len(r.content), 500)
