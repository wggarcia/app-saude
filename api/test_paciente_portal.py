"""
Portal do Paciente Hospitalar (Onda 1) — login por CPF+nascimento, criação de
conta, login por e-mail e leitura dos próprios exames com a regra de liberação
clínica. Valida também o isolamento: paciente de um hospital não vê exame de
outro, e resultado 'critico'/'pendente' não vaza em detalhe.
"""
import json
from datetime import date, timedelta

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from . import views_paciente_portal as vpp
from .models import (
    Empresa, IdentidadePaciente, PacienteInternado, LeitoHospitalar,
    PedidoExame, ResultadoExame, CredencialAppPaciente,
)

# Em produção o portal usa a conexão "owner" (papel dono, bypassa RLS) nos
# lookups cross-tenant. Nos testes, "owner" espelha "default" (mesmo banco), e
# ter duas conexões no mesmo SQLite in-memory quebra o flush do TransactionTestCase.
# Apontamos o alias da view para "default" e rodamos numa só conexão — TestCase
# transacional, rápido e sem lock. A lógica testada é idêntica (owner==default).
_DB = "default"


def _empresa_hospital(email, pacote="hospital_grupo"):
    return Empresa.objects.create(
        nome=f"Hospital {email}", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _paciente(empresa, nome="Maria Souza", cpf="39053344705", nasc="1980-05-10"):
    return PacienteInternado.objects.create(
        empresa=empresa, nome=nome, cpf=cpf,
        data_nascimento=date.fromisoformat(nasc),
        data_internacao=date.today(), status="internado",
    )


def _resultado(empresa, paciente, interpretacao="normal", laudo="Hemograma dentro da normalidade."):
    pedido = PedidoExame.objects.create(
        empresa=empresa, paciente=paciente, tipo="laboratorial",
        exames=[{"nome": "Hemograma completo"}],
    )
    return ResultadoExame.objects.create(
        pedido=pedido, paciente=paciente, interpretacao=interpretacao, laudo=laudo,
        resultados_json=[{"exame": "Hemoglobina", "valor": "14.2", "unidade": "g/dL",
                          "referencia": "12-16", "status": "normal"}],
    )


class PortalPacienteTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._owner_db_orig = vpp._OWNER_DB
        vpp._OWNER_DB = "default"  # uma só conexão no teste (ver nota acima)

    @classmethod
    def tearDownClass(cls):
        vpp._OWNER_DB = cls._owner_db_orig
        super().tearDownClass()

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # zera o rate-limit de /acessar entre testes (10/min por IP)
        self.client = Client()
        self.emp = _empresa_hospital("hosp-a@example.com")
        self.pac = _paciente(self.emp)

    # ── acesso + registro + login ──────────────────────────────────────────
    def _acessar(self, cpf="390.533.447-05", nasc="1980-05-10"):
        return self.client.post("/api/paciente/acessar",
                                data=json.dumps({"cpf": cpf, "data_nascimento": nasc}),
                                content_type="application/json", secure=True)

    def test_acessar_encontra_paciente(self):
        r = self._acessar()
        self.assertEqual(r.status_code, 200)
        ops = r.json()["opcoes"]
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["hospital_nome"], self.emp.nome)
        self.assertFalse(ops[0]["tem_conta"])
        self.assertTrue(ops[0]["registro_token"])
        # criou a identidade MPI
        self.assertTrue(IdentidadePaciente.objects.using(_DB).filter(empresa=self.emp, cpf="39053344705").exists())

    def test_acessar_cpf_ou_nascimento_errado_nega(self):
        self.assertEqual(self._acessar(nasc="1990-01-01").status_code, 404)
        self.assertEqual(self._acessar(cpf="11144477735").status_code, 404)

    def test_registrar_e_login(self):
        token_reg = self._acessar().json()["opcoes"][0]["registro_token"]
        r = self.client.post("/api/paciente/registrar",
                             data=json.dumps({"registro_token": token_reg,
                                              "email": "maria@example.com", "senha": "segredo123"}),
                             content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["token"])
        self.assertTrue(CredencialAppPaciente.objects.using(_DB).filter(email="maria@example.com").exists())

        # segundo registro com mesmo CPF é bloqueado
        token_reg2 = self._acessar().json()["opcoes"][0]["registro_token"]
        r2 = self.client.post("/api/paciente/registrar",
                              data=json.dumps({"registro_token": token_reg2,
                                               "email": "outro@example.com", "senha": "segredo123"}),
                              content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 409)

        # login por e-mail
        r3 = self.client.post("/api/paciente/login",
                             data=json.dumps({"email": "maria@example.com", "senha": "segredo123"}),
                             content_type="application/json", secure=True)
        self.assertEqual(r3.status_code, 200)
        self.assertTrue(r3.json()["token"])

        # senha errada
        r4 = self.client.post("/api/paciente/login",
                             data=json.dumps({"email": "maria@example.com", "senha": "errada"}),
                             content_type="application/json", secure=True)
        self.assertEqual(r4.status_code, 401)

    def test_registro_token_invalido_nega(self):
        r = self.client.post("/api/paciente/registrar",
                            data=json.dumps({"registro_token": "lixo",
                                             "email": "x@example.com", "senha": "segredo123"}),
                            content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 401)

    # ── meus exames + liberação clínica ────────────────────────────────────
    def _logar(self):
        token_reg = self._acessar().json()["opcoes"][0]["registro_token"]
        r = self.client.post("/api/paciente/registrar",
                            data=json.dumps({"registro_token": token_reg,
                                             "email": "maria@example.com", "senha": "segredo123"}),
                            content_type="application/json", secure=True)
        return r.json()["token"]

    def test_meus_exames_mostra_normal_oculta_critico(self):
        _resultado(self.emp, self.pac, interpretacao="normal", laudo="Tudo certo.")
        _resultado(self.emp, self.pac, interpretacao="critico", laudo="ACHADO GRAVE — sigiloso")
        _resultado(self.emp, self.pac, interpretacao="pendente", laudo="")
        tok = self._logar()

        r = self.client.get("/api/paciente/meus-exames", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["exames"]), 3)
        self.assertEqual(data["aviso_oculto"], 2)  # critico + pendente

        visiveis = [e for e in data["exames"] if e["visivel"]]
        self.assertEqual(len(visiveis), 1)
        self.assertIn("Tudo certo.", visiveis[0]["laudo"])
        # o laudo grave NUNCA aparece em nenhum item
        blob = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("ACHADO GRAVE", blob)

    def test_meus_exames_exige_auth(self):
        self.assertEqual(self.client.get("/api/paciente/meus-exames", secure=True).status_code, 401)

    def test_isolamento_entre_hospitais(self):
        # paciente com MESMO CPF internado noutro hospital, com exame
        emp_b = _empresa_hospital("hosp-b@example.com")
        pac_b = _paciente(emp_b)
        _resultado(emp_b, pac_b, interpretacao="normal", laudo="Exame do hospital B — não deve vazar.")
        _resultado(self.emp, self.pac, interpretacao="normal", laudo="Exame do hospital A.")

        tok = self._logar()  # loga no hospital A (self.emp)
        r = self.client.get("/api/paciente/meus-exames", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        blob = json.dumps(r.json(), ensure_ascii=False)
        self.assertIn("hospital A", blob)
        self.assertNotIn("hospital B", blob)

    def test_explicar_fallback_sem_ia(self):
        res = _resultado(self.emp, self.pac, interpretacao="normal")
        tok = self._logar()
        r = self.client.post(f"/api/paciente/exames/{res.id}/explicar",
                            data="{}", content_type="application/json", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("explicacao", r.json())
        self.assertTrue(r.json()["explicacao"])

    def test_explicar_bloqueado_para_critico(self):
        res = _resultado(self.emp, self.pac, interpretacao="critico")
        tok = self._logar()
        r = self.client.post(f"/api/paciente/exames/{res.id}/explicar",
                            data="{}", content_type="application/json", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 403)

    def test_resumo_traz_stats_e_saude(self):
        # o motor do painel inicial + aba Minha Saúde
        self.pac.diagnostico_cid = "J18"
        self.pac.diagnostico_descricao = "Pneumonia"
        self.pac.alergias = "Dipirona"
        self.pac.tipo_sanguineo = "O+"
        self.pac.prescricao_atual = {"medicamentos": [{"nome": "Amoxicilina", "dose": "500mg 8/8h"}]}
        self.pac.save(using=_DB)
        _resultado(self.emp, self.pac, interpretacao="normal")
        _resultado(self.emp, self.pac, interpretacao="critico")
        tok = self._logar()

        r = self.client.get("/api/paciente/resumo", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["stats"]["exames_disponiveis"], 1)
        self.assertEqual(d["stats"]["exames_reservados"], 1)
        self.assertEqual(d["saude"]["diagnostico_descricao"], "Pneumonia")
        self.assertEqual(d["saude"]["alergias"], "Dipirona")
        self.assertEqual(d["saude"]["tipo_sanguineo"], "O+")
        self.assertTrue(any("Amoxicilina" in m for m in d["saude"]["medicacoes"]))

    def test_resumo_exige_auth(self):
        self.assertEqual(self.client.get("/api/paciente/resumo", secure=True).status_code, 401)

    def test_exportar_dados_lgpd(self):
        _resultado(self.emp, self.pac, interpretacao="normal")
        tok = self._logar()
        r = self.client.get("/api/paciente/exportar", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        d = json.loads(r.content)
        self.assertEqual(d["titular"]["nome"], self.pac.nome)
        self.assertTrue(d["exames"])

    def test_excluir_conta_remove_so_credencial(self):
        tok = self._logar()
        self.assertTrue(CredencialAppPaciente.objects.using(_DB).filter(email="maria@example.com").exists())
        r = self.client.post("/api/paciente/excluir-conta", secure=True,
                             HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        # credencial some, mas o paciente (prontuário) permanece
        self.assertFalse(CredencialAppPaciente.objects.using(_DB).filter(email="maria@example.com").exists())
        self.assertTrue(PacienteInternado.objects.using(_DB).filter(id=self.pac.id).exists())

    def test_compartilhar_gera_link_e_pagina_publica(self):
        res = _resultado(self.emp, self.pac, interpretacao="normal", laudo="Tudo certo.")
        tok = self._logar()
        r = self.client.post(f"/api/paciente/exames/{res.id}/compartilhar", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        url = r.json()["url"]
        self.assertIn("/exame-compartilhado/", url)
        token_share = url.split("/exame-compartilhado/")[1]
        # página pública abre sem login e mostra o resultado
        pg = self.client.get(f"/exame-compartilhado/{token_share}", secure=True)
        self.assertEqual(pg.status_code, 200)
        self.assertIn("Tudo certo.", pg.content.decode())

    def test_compartilhar_bloqueado_para_critico(self):
        res = _resultado(self.emp, self.pac, interpretacao="critico")
        tok = self._logar()
        r = self.client.post(f"/api/paciente/exames/{res.id}/compartilhar", secure=True,
                            HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 403)

    def test_exame_compartilhado_token_invalido(self):
        pg = self.client.get("/exame-compartilhado/lixo", secure=True)
        self.assertEqual(pg.status_code, 200)
        self.assertIn("Link indisponível", pg.content.decode())

    def _cookie_empresa(self, empresa):
        import jwt as _jwt
        from django.conf import settings as _s
        payload = {"empresa_id": empresa.id, "principal_kind": "empresa",
                   "principal_id": empresa.id, "session_key": empresa.sessao_ativa_chave,
                   "exp": timezone.now() + timedelta(hours=1)}
        c = Client()
        c.cookies["auth_token"] = _jwt.encode(payload, _s.JWT_SECRET_KEY, algorithm="HS256")
        return c

    def test_agenda_lista_e_confirma(self):
        from .models import AgendamentoPaciente
        tok = self._logar()  # cria a identidade (MPI)
        ident = IdentidadePaciente.objects.using(_DB).get(empresa=self.emp, cpf="39053344705")
        AgendamentoPaciente.objects.using(_DB).create(
            empresa=self.emp, identidade=ident, tipo="consulta", especialidade="Cardiologia",
            data_hora=timezone.now() + timedelta(days=3), status="agendado")
        r = self.client.get("/api/paciente/agenda", secure=True, HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200)
        prox = r.json()["proximas"]
        self.assertEqual(len(prox), 1)
        self.assertEqual(prox[0]["especialidade"], "Cardiologia")
        pk = prox[0]["id"]
        r2 = self.client.post(f"/api/paciente/agenda/{pk}/confirmar", secure=True, HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["agendamento"]["status"], "confirmado")

    def test_mensagens_paciente_envia_e_equipe_responde(self):
        from .models import IdentidadePaciente as IP
        tok = self._logar()
        # paciente envia
        r = self.client.post("/api/paciente/mensagens",
                             data=json.dumps({"texto": "Doutor, posso tomar o remédio em jejum?"}),
                             content_type="application/json", secure=True, HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 201)
        ident = IP.objects.using(_DB).filter(empresa=self.emp, cpf="39053344705").first()
        # equipe responde (lado hospital, auth de empresa por cookie)
        ec = self._cookie_empresa(self.emp)
        r2 = ec.post(f"/api/hospital/paciente-mensagens/{ident.id}/responder",
                     data=json.dumps({"texto": "Pode sim, com água.", "autor_nome": "Dra. Ana"}),
                     content_type="application/json", secure=True)
        self.assertEqual(r2.status_code, 201)
        # paciente vê a conversa
        r3 = self.client.get("/api/paciente/mensagens", secure=True, HTTP_AUTHORIZATION=f"Bearer {tok}")
        msgs = r3.json()["mensagens"]
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["autor"], "paciente")
        self.assertEqual(msgs[1]["autor"], "equipe")

    def test_hospital_cria_agendamento(self):
        from .models import IdentidadePaciente as IP, AgendamentoPaciente
        # garante identidade
        self._logar()
        ident = IP.objects.using(_DB).filter(empresa=self.emp, cpf="39053344705").first()
        ec = self._cookie_empresa(self.emp)
        r = ec.post("/api/hospital/paciente-agenda",
                    data=json.dumps({"identidade_id": ident.id, "tipo": "retorno",
                                     "especialidade": "Ortopedia",
                                     "data_hora": (timezone.now() + timedelta(days=5)).isoformat()}),
                    content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(AgendamentoPaciente.objects.using(_DB).filter(identidade=ident, especialidade="Ortopedia").exists())

    def test_pagina_portal_publica(self):
        r = self.client.get("/paciente/", secure=True)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Portal do Paciente", html)
        self.assertIn("Primeiro acesso", html)
