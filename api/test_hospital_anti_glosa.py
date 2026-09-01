"""
Fase 1 do módulo Faturamento & Anti-Glosa (lado prestador, Hospital).

Cobre:
  • o motor puro `criticar_guia_tiss` (regras determinísticas de crítica pré-envio);
  • o endpoint GET /api/hospital/tiss/<id>/criticar/;
  • o bloqueio de envio (status→enviada) quando há ocorrência que bloqueia, e o
    override via forcar=True;
  • o gate por feature (hospital.anti_glosa só no tier REDE/GRUPO).
"""
import json
from datetime import timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, GuiaTISS
from .services.anti_glosa import criticar_guia_tiss


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa_hospital(email, pacote="hospital_grupo"):
    return Empresa.objects.create(
        nome="Hospital Render", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _guia_limpa(empresa, **over):
    dados = dict(
        empresa=empresa,
        numero_guia="G-1001",
        tipo="sp_sadt",
        operadora_codigo="123456",
        operadora_nome="Operadora X",
        beneficiario_nome="Fulano de Tal",
        beneficiario_carteirinha="9988776655",
        cid10="J06",
        procedimentos=[
            {"tabela": "22", "codigo": "10101012", "descricao": "Consulta",
             "quantidade": 1, "valor_unitario": 100.0},
        ],
        valor_apresentado=Decimal("100.00"),
        status="elaborada",
    )
    dados.update(over)
    return GuiaTISS.objects.create(**dados)


class AntiGlosaMotorTests(TestCase):
    def test_guia_limpa_nao_bloqueia(self):
        empresa = _empresa_hospital("ag1@example.com")
        g = _guia_limpa(empresa)
        r = criticar_guia_tiss(g)
        self.assertFalse(r["bloqueia"], r)
        self.assertEqual(r["por_severidade"]["bloqueia"], 0)

    def test_cid_ausente_bloqueia(self):
        empresa = _empresa_hospital("ag2@example.com")
        g = _guia_limpa(empresa, cid10="")
        r = criticar_guia_tiss(g)
        self.assertTrue(r["bloqueia"])
        self.assertTrue(any(o["codigo"] == "GLOSA_CID_AUSENTE" for o in r["ocorrencias"]))

    def test_carteirinha_e_item_sem_codigo_bloqueiam(self):
        empresa = _empresa_hospital("ag3@example.com")
        g = _guia_limpa(
            empresa, beneficiario_carteirinha="",
            procedimentos=[{"tabela": "22", "codigo": "0", "descricao": "",
                            "quantidade": 0, "valor_unitario": 0}],
        )
        r = criticar_guia_tiss(g)
        codigos = {o["codigo"] for o in r["ocorrencias"]}
        self.assertTrue(r["bloqueia"])
        self.assertIn("GLOSA_CARTEIRINHA_AUSENTE", codigos)
        self.assertIn("GLOSA_ITEM_SEM_CODIGO", codigos)
        self.assertIn("GLOSA_QUANTIDADE_INVALIDA", codigos)

    def test_valor_incoerente_alerta(self):
        empresa = _empresa_hospital("ag4@example.com")
        # soma dos itens = 100, mas apresentado = 250 → divergência
        g = _guia_limpa(empresa, valor_apresentado=Decimal("250.00"))
        r = criticar_guia_tiss(g)
        self.assertFalse(r["bloqueia"])  # é alerta, não bloqueio
        self.assertTrue(any(o["codigo"] == "GLOSA_VALOR_INCOERENTE" for o in r["ocorrencias"]))

    def test_duplicidade_historica_alerta(self):
        empresa = _empresa_hospital("ag5@example.com")
        # guia já enviada com o mesmo procedimento p/ a mesma carteirinha
        _guia_limpa(empresa, numero_guia="G-ant", status="enviada")
        nova = _guia_limpa(empresa, numero_guia="G-nova")
        r = criticar_guia_tiss(nova)
        self.assertTrue(any(o["codigo"] == "GLOSA_DUPLICIDADE_HISTORICA" for o in r["ocorrencias"]))

    def test_isolamento_por_tenant_no_historico(self):
        # duplicidade não deve cruzar empresas diferentes
        emp_a = _empresa_hospital("agA@example.com")
        emp_b = _empresa_hospital("agB@example.com")
        _guia_limpa(emp_b, numero_guia="G-b", status="enviada")
        nova = _guia_limpa(emp_a, numero_guia="G-a")
        r = criticar_guia_tiss(nova)
        self.assertFalse(any(o["codigo"] == "GLOSA_DUPLICIDADE_HISTORICA" for o in r["ocorrencias"]))


class AntiGlosaEndpointTests(TestCase):
    def test_endpoint_criticar_retorna_ocorrencias(self):
        empresa = _empresa_hospital("age1@example.com")
        g = _guia_limpa(empresa, cid10="")
        client = _client_for(empresa)
        r = client.get(f"/api/hospital/tiss/{g.id}/criticar/", secure=True)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["bloqueia"])
        self.assertIn("ocorrencias", body)

    def test_envio_bloqueado_e_forcado(self):
        empresa = _empresa_hospital("age2@example.com")
        g = _guia_limpa(empresa, cid10="")  # CID ausente → bloqueia
        client = _client_for(empresa)

        # 1) tentar enviar → 422 bloqueado
        r = client.post(
            f"/api/hospital/tiss/{g.id}/status/",
            data=json.dumps({"status": "enviada"}), content_type="application/json", secure=True,
        )
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.json().get("pode_forcar"))
        g.refresh_from_db()
        self.assertEqual(g.status, "elaborada")  # não mudou

        # 2) forçar → passa
        r = client.post(
            f"/api/hospital/tiss/{g.id}/status/",
            data=json.dumps({"status": "enviada", "forcar": True}),
            content_type="application/json", secure=True,
        )
        self.assertEqual(r.status_code, 200)
        g.refresh_from_db()
        self.assertEqual(g.status, "enviada")

    def test_guia_limpa_envia_sem_bloqueio(self):
        empresa = _empresa_hospital("age3@example.com")
        g = _guia_limpa(empresa)
        client = _client_for(empresa)
        r = client.post(
            f"/api/hospital/tiss/{g.id}/status/",
            data=json.dumps({"status": "enviada"}), content_type="application/json", secure=True,
        )
        self.assertEqual(r.status_code, 200)
        g.refresh_from_db()
        self.assertEqual(g.status, "enviada")

    def test_gate_feature_tier_baixo_nao_acessa(self):
        # hospital_medio não tem hospital.anti_glosa → 403 no endpoint de crítica
        # (o gate mantém o módulo exclusivo do tier REDE/GRUPO).
        empresa = _empresa_hospital("age4@example.com", pacote="hospital_medio")
        g = _guia_limpa(empresa)
        client = _client_for(empresa)
        r = client.get(f"/api/hospital/tiss/{g.id}/criticar/", secure=True)
        self.assertEqual(r.status_code, 403)
