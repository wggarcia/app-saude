"""
RPC — Rol de Procedimentos (RN 465): checador de cobertura sobre o catálogo
TUSS da operadora, com cruzamento contra as guias emitidas.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, PlanoSaude, BeneficiarioPlano, GuiaAutorizacao, ProcedimentoTUSS,
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
        nome="Operadora RPC", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


class RPCTests(TestCase):
    def setUp(self):
        self.empresa = _empresa_plano("rpc@example.com")
        self.plano = PlanoSaude.objects.create(empresa=self.empresa, nome="Plano RPC")
        self.client_ = _client_for(self.empresa)
        ProcedimentoTUSS.objects.create(
            empresa=self.empresa, codigo_tuss="10101012", descricao="Consulta médica",
            segmento="consulta", cobertura_obrigatoria=True, prazo_atendimento=7,
        )

    def test_checar_codigo_coberto(self):
        d = self.client_.get("/api/plano-saude/rpc?codigo=10101012").json()
        self.assertTrue(d["encontrado"])
        self.assertTrue(d["cobertura_obrigatoria"])
        self.assertEqual(d["prazo_atendimento_dias"], 7)

    def test_checar_codigo_inexistente(self):
        d = self.client_.get("/api/plano-saude/rpc?codigo=99999999").json()
        self.assertFalse(d["encontrado"])

    def test_panorama_e_alerta_fora_do_rol(self):
        ben = BeneficiarioPlano.objects.create(plano=self.plano, nome="Fulano")
        # guia com procedimento NÃO catalogado → deve virar alerta
        GuiaAutorizacao.objects.create(
            plano=self.plano, beneficiario=ben, tipo="exame",
            descricao_procedimento="Exame raro", codigo_procedimento="88888888",
        )
        d = self.client_.get("/api/plano-saude/rpc").json()
        self.assertEqual(d["catalogo_total"], 1)
        self.assertEqual(d["cobertura_obrigatoria"], 1)
        self.assertEqual(d["total_alertas"], 1)
        self.assertEqual(d["alertas_fora_do_rol"][0]["codigo"], "88888888")

    def test_isolamento_por_tenant(self):
        outra = _empresa_plano("rpc-outra@example.com")
        ProcedimentoTUSS.objects.create(
            empresa=outra, codigo_tuss="20202020", descricao="Alheio",
            segmento="exame", cobertura_obrigatoria=True,
        )
        # operadora atual não enxerga código da outra
        d = self.client_.get("/api/plano-saude/rpc?codigo=20202020").json()
        self.assertFalse(d["encontrado"])
