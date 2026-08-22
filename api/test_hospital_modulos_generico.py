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

    def test_nutricao_cockpit_e_encerrar_dieta(self):
        empresa = _empresa_hospital("hn@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/nutricao/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Nutrição", html)
        self.assertIn("/api/hospital/nutricao/dietas", html)
        self.assertIn("Nova dieta", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/nutricao/dietas",
                          data=json.dumps({"tipo_dieta": "enteral", "via_administracao": "sonda_nasoenteral",
                                            "data_inicio": timezone.now().strftime("%Y-%m-%d")}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        pk = r2.json()["dieta"]["id"]
        r3 = client.patch(f"/api/hospital/nutricao/dietas/{pk}",
                           data=json.dumps({"ativa": False}), content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 200)

    def test_cme_cockpit_e_registrar_uso(self):
        empresa = _empresa_hospital("hcme@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/cme/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("CME", html)
        self.assertIn("Registrar uso", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/cme/instrumentais",
                          data=json.dumps({"nome": "Caixa de laparotomia"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        inst_id = r2.json()["id"]

        r3 = client.post("/api/hospital/cme/ciclos",
                          data=json.dumps({"instrumental_id": inst_id, "numero_ciclo": "C-001",
                                            "data_esterilizacao": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                                            "validade_ate": (timezone.now() + timedelta(days=30)).strftime("%Y-%m-%d")}),
                          content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 201)
        ciclo_id = r3.json()["id"]

        r4 = client.post(f"/api/hospital/cme/ciclos/{ciclo_id}/uso",
                          data=json.dumps({"paciente_uso": "Paciente Teste"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r4.status_code, 200)

    def test_radioterapia_cockpit_e_progresso(self):
        empresa = _empresa_hospital("hrt@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/radioterapia/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("em construção", r.content.decode())

        r2 = client.post("/api/hospital/radioterapia/sessoes",
                          data=json.dumps({"paciente": "Paciente RT", "dose_prescrita_gy": 60,
                                            "numero_fracoes_total": 30}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        pk = r2.json()["sessao"]["id"]

        r3 = client.patch(f"/api/hospital/radioterapia/sessoes/{pk}",
                           data=json.dumps({"status": "em_andamento", "numero_fracoes_realizadas": 1}),
                           content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 200)

    def test_rhc_cockpit_e_adicionar_tratamento(self):
        empresa = _empresa_hospital("hrhc@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/rhc/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("RHC", html)
        self.assertIn("Exportar RHCNET", html)
        self.assertNotIn("em construção", html)

        hoje = timezone.now().strftime("%Y-%m-%d")
        r2 = client.post("/api/hospital/rhc/registros",
                          data=json.dumps({"nome_paciente": "Paciente Onco", "data_nascimento": "1970-01-01",
                                            "sexo": "F", "cid_topografia": "C50", "estadiamento": "II",
                                            "data_primeiro_atendimento": hoje}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        pk = r2.json()["id"]
        r3 = client.post(f"/api/hospital/rhc/registros/{pk}/tratar",
                          data=json.dumps({"tratamento": "quimio"}), content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 200)

    def test_nhve_cockpit_e_confirmar(self):
        empresa = _empresa_hospital("hnhve@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/nhve/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("NHVE", html)
        self.assertIn("Notificar SINAN", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/nhve/notificacoes",
                          data=json.dumps({"doenca_cid": "A90", "data_notificacao": timezone.now().strftime("%Y-%m-%d")}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        pk = r2.json()["id"]
        r3 = client.post(f"/api/hospital/nhve/notificacoes/{pk}/confirmar", secure=True)
        self.assertEqual(r3.status_code, 200)
        r4 = client.post(f"/api/hospital/nhve/notificacoes/{pk}/notificar-sinan", secure=True)
        self.assertEqual(r4.status_code, 200)

    def test_same_cockpit_e_devolver_emprestimo(self):
        empresa = _empresa_hospital("hsame@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/same/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("SAME", html)
        self.assertIn("Devolver", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/same/pacientes",
                          data=json.dumps({"prontuario": "PRT-001", "nome_paciente": "Paciente SAME"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        codigo_id = r2.json()["codigo_same"]["id"]

        r3 = client.post("/api/hospital/same/emprestimos",
                          data=json.dumps({"codigo_same_id": codigo_id, "solicitante": "Dr. Fulano",
                                            "setor": "Ambulatório",
                                            "data_prevista_devolucao": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%d")}),
                          content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 201)
        emprestimo_id = r3.json()["emprestimo"]["id"]

        r4 = client.post(f"/api/hospital/same/emprestimos/{emprestimo_id}/devolver", secure=True)
        self.assertEqual(r4.status_code, 200)

    def test_telemedicina_cockpit_e_iniciar_encerrar(self):
        empresa = _empresa_hospital("htele@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/telemedicina/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Telemedicina", html)
        self.assertIn("Agendar consulta", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/telemedicina/consultas",
                          data=json.dumps({"paciente_nome": "Paciente Tele", "especialidade": "Clínica Geral",
                                            "medico": "Dra. Teste"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        pk = r2.json()["id"]
        r3 = client.post(f"/api/hospital/telemedicina/consultas/{pk}/iniciar", secure=True)
        self.assertEqual(r3.status_code, 200)
        r4 = client.post(f"/api/hospital/telemedicina/consultas/{pk}/encerrar", secure=True)
        self.assertEqual(r4.status_code, 200)

    def test_manutencao_cockpit_e_concluir_os(self):
        empresa = _empresa_hospital("hman@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/manutencao/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Manutenção", html)
        self.assertIn("Abrir OS", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/manutencao/ordens",
                          data=json.dumps({"descricao": "Ar-condicionado com vazamento", "setor": "UTI"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        pk = r2.json()["ordem"]["id"]
        r3 = client.post(f"/api/hospital/manutencao/ordens/{pk}/concluir",
                          data=json.dumps({"custo_real": 350.0}), content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 200)

    def test_lavanderia_cockpit_e_registrar_ciclo(self):
        empresa = _empresa_hospital("hlav@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/lavanderia/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Lavanderia", html)
        self.assertIn("Registrar ciclo", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/lavanderia/itens",
                          data=json.dumps({"descricao": "Lençol", "quantidade_total": 100, "setor": "Central"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        item_id = r2.json()["item"]["id"]
        r3 = client.post("/api/hospital/lavanderia/ciclos",
                          data=json.dumps({"item_id": item_id, "quantidade": 20, "tipo": "entrada_sujo"}),
                          content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 201)

    def test_epimed_cockpit_e_gerar_lote(self):
        empresa = _empresa_hospital("hepi@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/epimed/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Epimed", html)
        self.assertIn("Gerar lote", html)
        self.assertNotIn("em construção", html)

        r2 = client.post("/api/hospital/epimed/gerar", data="{}", content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)

    def test_betha_cockpit_e_status(self):
        empresa = _empresa_hospital("hbetha@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/betha/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Betha", html)
        self.assertIn("Sincronizar Almoxarifado", html)
        self.assertNotIn("em construção", html)

        r2 = client.get("/api/hospital/betha/status", secure=True)
        self.assertEqual(r2.status_code, 200)
        self.assertIn("credencial_configurada", r2.json())

    def test_drg_cockpit_e_classificar(self):
        empresa = _empresa_hospital("hdrg@example.com")
        client = _client_for(empresa)
        r = client.get("/hospital/drg/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("DRG", html)
        self.assertIn("Classificar internação", html)
        self.assertNotIn("em construção", html)

        r2 = client.get("/api/hospital/drg/status", secure=True)
        self.assertEqual(r2.status_code, 200)
