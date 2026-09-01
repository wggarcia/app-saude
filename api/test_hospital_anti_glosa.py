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

from .models import Empresa, GuiaTISS, GlosaRecebida, RecursoGlosaPrestador
from .services.anti_glosa import criticar_guia_tiss, criticar_guia_completa, risco_glosa_ia


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


class AntiGlosaIATests(TestCase):
    """Fase 2 — IA de risco-de-glosa (motor ML por área, bootstrap sintético)."""

    def test_ia_infere_risco_alto_para_guia_problematica(self):
        empresa = _empresa_hospital("iag1@example.com")
        ruim = _guia_limpa(empresa, cid10="", beneficiario_carteirinha="", operadora_codigo="",
                           procedimentos=[{"tabela": "22", "codigo": "0", "descricao": "",
                                           "quantidade": 1, "valor_unitario": 0}],
                           valor_apresentado=0)
        r = risco_glosa_ia(ruim)
        self.assertIsNotNone(r)
        self.assertGreaterEqual(r["risco_ia"], 0)
        self.assertLessEqual(r["risco_ia"], 100)
        self.assertIn(r["decisao_ia"], {"glosada", "paga"})

    def test_ia_risco_maior_na_ruim_que_na_limpa(self):
        empresa = _empresa_hospital("iag2@example.com")
        limpa = _guia_limpa(empresa)
        ruim = _guia_limpa(empresa, cid10="", beneficiario_carteirinha="", operadora_codigo="",
                           procedimentos=[{"tabela": "22", "codigo": "0", "descricao": "",
                                           "quantidade": 1, "valor_unitario": 0}],
                           valor_apresentado=0)
        r_limpa = risco_glosa_ia(limpa)
        r_ruim = risco_glosa_ia(ruim)
        self.assertIsNotNone(r_limpa)
        self.assertIsNotNone(r_ruim)
        # o modelo bootstrap deve enxergar mais risco na guia com faltas graves
        self.assertGreater(r_ruim["risco_ia"], r_limpa["risco_ia"])

    def test_completa_inclui_ia_e_score_combinado(self):
        empresa = _empresa_hospital("iag3@example.com")
        g = _guia_limpa(empresa, cid10="")  # tem bloqueio determinístico
        full = criticar_guia_completa(g)
        self.assertIn("ia", full)
        self.assertIn("score_risco_combinado", full)
        self.assertTrue(full["bloqueia"])  # regra ainda manda no bloqueio
        self.assertGreaterEqual(full["score_risco_combinado"], full["score_risco"])

    def test_endpoint_criticar_traz_ia(self):
        empresa = _empresa_hospital("iag4@example.com")
        g = _guia_limpa(empresa)
        client = _client_for(empresa)
        r = client.get(f"/api/hospital/tiss/{g.id}/criticar/", secure=True)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("ia", body)
        self.assertIn("score_risco_combinado", body)


class GlosaRecebidaRecursoTests(TestCase):
    """Fase 3 — glosa recebida item-a-item + recurso com IA de mérito."""

    def _registrar_glosa(self, client, guia, valor=40.0, codigo_glosa="1403"):
        return client.post(
            f"/api/hospital/tiss/{guia.id}/glosa/",
            data=json.dumps({
                "protocolo_operadora": "PROT-1",
                "itens": [{"codigo": "10101012", "descricao": "Consulta",
                           "codigo_glosa": codigo_glosa, "motivo_glosa": "Duplicidade",
                           "valor_glosado": valor}],
            }),
            content_type="application/json", secure=True,
        )

    def test_registrar_glosa_reflete_na_guia(self):
        empresa = _empresa_hospital("gr1@example.com")
        g = _guia_limpa(empresa, valor_apresentado=Decimal("100.00"), status="enviada")
        client = _client_for(empresa)
        r = self._registrar_glosa(client, g, valor=40.0)
        self.assertEqual(r.status_code, 201)
        g.refresh_from_db()
        self.assertEqual(g.status, "glosada")
        self.assertEqual(float(g.valor_aprovado), 60.0)  # 100 - 40
        self.assertEqual(GlosaRecebida.objects.filter(empresa=empresa).count(), 1)

    def test_lista_glosas_e_kpis(self):
        empresa = _empresa_hospital("gr2@example.com")
        g = _guia_limpa(empresa, valor_apresentado=Decimal("100.00"), status="enviada")
        client = _client_for(empresa)
        self._registrar_glosa(client, g, valor=40.0, codigo_glosa="1403")
        r = client.get("/api/hospital/glosas/", secure=True)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["glosas"]), 1)
        self.assertEqual(body["kpis"]["total_glosado"], 40.0)
        self.assertTrue(any(m["codigo_glosa"] == "1403" for m in body["kpis"]["top_motivos"]))

    def test_sugerir_recurso_traz_merito_ia(self):
        empresa = _empresa_hospital("gr3@example.com")
        g = _guia_limpa(empresa, status="enviada")
        client = _client_for(empresa)
        gid = self._registrar_glosa(client, g).json()["glosa"]["id"]
        r = client.get(f"/api/hospital/glosa/{gid}/sugerir-recurso/", secure=True)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("ia_merito_score", body)
        self.assertTrue(body["texto_sugerido"])
        self.assertGreaterEqual(body["ia_merito_score"], 0)

    def test_abrir_recurso_e_deferir_recupera_valor(self):
        empresa = _empresa_hospital("gr4@example.com")
        g = _guia_limpa(empresa, valor_apresentado=Decimal("100.00"), status="enviada")
        client = _client_for(empresa)
        gid = self._registrar_glosa(client, g, valor=40.0).json()["glosa"]["id"]

        # abrir recurso
        r = client.post(
            f"/api/hospital/glosa/{gid}/recurso/",
            data=json.dumps({"codigo_glosa": "1403",
                             "justificativa": "Atendimentos distintos registrados em prontuário, com laudo anexo.",
                             "valor_recorrido": 40.0}),
            content_type="application/json", secure=True,
        )
        self.assertEqual(r.status_code, 201)
        rec = r.json()["recurso"]
        self.assertGreater(rec["ia_merito_score"], 0)
        GlosaRecebida.objects.get(pk=gid)
        self.assertEqual(GlosaRecebida.objects.get(pk=gid).status, "em_recurso")

        # deferir → recupera valor, guia volta a paga
        r = client.post(
            f"/api/hospital/recurso/{rec['id']}/status/",
            data=json.dumps({"status": "deferido"}),
            content_type="application/json", secure=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(float(r.json()["recurso"]["valor_recuperado"]), 40.0)
        g.refresh_from_db()
        self.assertEqual(float(g.valor_aprovado), 100.0)  # 60 + 40 recuperado
        self.assertEqual(g.status, "paga")
        self.assertEqual(GlosaRecebida.objects.get(pk=gid).status, "encerrada")

    def test_isolamento_tenant_glosa(self):
        emp_a = _empresa_hospital("grA@example.com")
        emp_b = _empresa_hospital("grB@example.com")
        g_b = _guia_limpa(emp_b, status="enviada")
        client_a = _client_for(emp_a)
        r = self._registrar_glosa(client_a, g_b)  # A tenta glosar guia de B
        self.assertEqual(r.status_code, 404)

    def test_gate_feature_tier_baixo(self):
        empresa = _empresa_hospital("grC@example.com", pacote="hospital_medio")
        client = _client_for(empresa)
        r = client.get("/api/hospital/glosas/", secure=True)
        self.assertEqual(r.status_code, 403)
