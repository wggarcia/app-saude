"""
Smoke dos módulos hospitalares que antes mostravam "em construção" e agora
renderizam o template genérico (hospital_modulo_generico.html) consumindo as
APIs já existentes. Garante 200 + template certo + config injetada.
"""
import json
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa


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


class HospitalModuloGenericoTests(TestCase):
    def test_qualidade_renderiza_cockpit_nsp(self):
        # Qualidade foi promovida do template genérico para o cockpit NSP real.
        empresa = _empresa_hospital("hq@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/qualidade/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Segurança do Paciente", html)
        self.assertNotIn("em construção", html)
        # wired aos endpoints reais + ação de notificar (o fluxo em 3 cliques)
        self.assertIn("/api/hospital/qualidade/kpis", html)
        self.assertIn("/api/hospital/qualidade/incidentes", html)
        self.assertIn("Notificar incidente", html)
        self.assertIn('id="kpis"', html)

    def test_qualidade_ia_analise_causa_raiz(self):
        # O diferencial NSP: análise de causa-raiz. Sem ANTHROPIC_API_KEY nos
        # testes, cai no fallback determinístico — que nunca falha e traz Ishikawa,
        # 5 porquês e risco de recorrência.
        empresa = _empresa_hospital("hia@example.com")
        client = _client_for(empresa)
        r = client.post(
            "/api/hospital/qualidade/incidentes",
            data=json.dumps({"tipo": "queda", "gravidade": "dano_grave",
                             "setor": "UTI Adulto",
                             "descricao": "Paciente caiu da maca durante o transporte."}),
            content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 201)
        pk = r.json()["id"]

        r2 = client.post(f"/api/hospital/qualidade/incidentes/{pk}/ia-analise",
                         data="{}", content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 200)
        a = r2.json()["analise"]
        self.assertIn("classificacao", a)
        self.assertEqual(len(a["ishikawa"]), 4)
        self.assertEqual(len(a["cinco_porques"]), 5)
        self.assertEqual(a["risco_recorrencia"], "alto")  # dano_grave → alto
        self.assertTrue(a["acoes_preventivas"])

    def test_custos_renderiza_cockpit_margem_drg(self):
        # Custos Hospitalares foi promovido do template genérico para o cockpit
        # com apuração por categoria e margem por DRG (custo real x reembolso estimado).
        empresa = _empresa_hospital("hc@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/custos/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Margem por DRG", html)
        self.assertNotIn("em construção", html)
        self.assertIn("/api/hospital/custos/margem", html)
        self.assertIn("/api/hospital/custos/lancamentos", html)
        self.assertIn("Novo lançamento", html)

    def test_custos_margem_ia_analise_causa_raiz(self):
        # O diferencial de Custos: cruzar custo real lançado com o peso relativo
        # do DRG para estimar margem, e a IA explica a causa da margem negativa.
        # Sem ANTHROPIC_API_KEY nos testes, cai no fallback determinístico.
        empresa = _empresa_hospital("hcm@example.com")
        client = _client_for(empresa)
        comp = timezone.now().strftime("%Y-%m")

        r = client.post(
            "/api/hospital/custos/lancamentos",
            data=json.dumps({"competencia": comp, "categoria": "material",
                             "descricao": "OPME prótese", "valor": 50000,
                             "drg_codigo": "004"}),
            content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 201)

        r2 = client.post(
            "/api/hospital/custos/drg",
            data=json.dumps({"codigo_drg": "004", "descricao_drg": "Cirurgia ortopédica",
                             "peso_relativo": 1.5, "competencia": comp}),
            content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)

        r3 = client.get(f"/api/hospital/custos/margem?competencia={comp}", secure=True)
        self.assertEqual(r3.status_code, 200)
        margem = r3.json()
        linha = next(x for x in margem["drgs"] if x["drg_codigo"] == "004")
        self.assertLess(linha["margem"], 0)  # custo de 50k >> reembolso estimado

        r4 = client.post(
            "/api/hospital/custos/margem/ia-analise",
            data=json.dumps({"drg_codigo": "004", "competencia": comp}),
            content_type="application/json", secure=True)
        self.assertEqual(r4.status_code, 200)
        a = r4.json()["analise"]
        self.assertIn("diagnostico", a)
        self.assertTrue(a["causas_provaveis"])
        self.assertTrue(a["acoes_recomendadas"])

    def test_nutricao_renderiza_template_generico(self):
        empresa = _empresa_hospital("hn@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/nutricao/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Nutricao", html)
        self.assertIn("/api/hospital/nutricao/dietas", html)
        self.assertNotIn("em construção", html)
