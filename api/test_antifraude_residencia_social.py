"""
Testes do antifraude de Cadastro Social cross-município (CRAS/CadÚnico).

Ver api/services/antifraude_residencia.py para o comportamento completo.
Padrão de teste (empresa/auth) copiado de test_suas_caracterizacao.py.
"""
import json

from django.contrib.auth.hashers import make_password
from django.test import TestCase, RequestFactory

from .models import AlertaAntifraudeSocial, Empresa, FamiliaCRAS, IndiceCadastroSocial
from . import views_governo_suas_cras as gov
from . import views_assistencia_cras as ass
from .services.antifraude_residencia import contestar_suspensao, registrar_e_verificar_cadastro_social


def _empresa(email, pacote, cidade=""):
    return Empresa.objects.create(
        nome=f"Municipio {email}", email=email, senha=make_password("x"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote, cidade=cidade,
        sessao_ativa_chave=f"sessao-{email}",
    )


class _AuthMixin:
    def _get(self, empresa, query=""):
        r = self.rf.get("/" + ("?" + query if query else ""))
        r.empresa = empresa
        r.principal = None
        return r

    def _post(self, empresa, body):
        r = self.rf.post("/", data=json.dumps(body), content_type="application/json")
        r.empresa = empresa
        r.principal = None
        return r


class RegistroCrossMunicipioTests(_AuthMixin, TestCase):
    """Caso principal: a mesma pessoa se cadastra em dois municípios."""

    def setUp(self):
        self.rf = RequestFactory()
        self.muni_a = _empresa("a@t.com", "governo_municipio_pequeno", cidade="Município A")
        self.muni_b = _empresa("b@t.com", "governo_municipio_pequeno", cidade="Município B")

    def test_recadastro_em_outro_municipio_suspende_o_antigo(self):
        resp_a = gov.api_cras_familias(self._post(self.muni_a, {
            "responsavel_nome": "Maria Teste", "responsavel_cpf": "11144477735",
        }))
        self.assertEqual(resp_a.status_code, 201)
        familia_a_id = json.loads(resp_a.content)["id"]

        f_a = FamiliaCRAS.objects.get(id=familia_a_id)
        self.assertEqual(f_a.situacao, "em_acompanhamento")

        resp_b = gov.api_cras_familias(self._post(self.muni_b, {
            "responsavel_nome": "Maria Teste", "responsavel_cpf": "11144477735",
        }))
        self.assertEqual(resp_b.status_code, 201)

        f_a.refresh_from_db()
        self.assertEqual(f_a.situacao, "suspensa")
        self.assertIn("Município B", f_a.motivo_suspensao)
        self.assertIsNotNone(f_a.suspenso_em)

        indice = IndiceCadastroSocial.objects.get(cpf="11144477735")
        self.assertEqual(indice.empresa_ativa_id, self.muni_b.id)
        self.assertEqual(len(indice.historico), 3)  # ativado(A) + suspenso_por_recadastro + ativado(B)

        alerta_antigo = AlertaAntifraudeSocial.objects.filter(
            empresa=self.muni_a, tipo="suspensao_registro").first()
        self.assertIsNotNone(alerta_antigo)
        alerta_novo = AlertaAntifraudeSocial.objects.filter(
            empresa=self.muni_b, tipo="registro_anterior_detectado").first()
        self.assertIsNotNone(alerta_novo)

    def test_recadastro_por_nis_quando_cpf_ausente(self):
        resp_a = gov.api_cras_familias(self._post(self.muni_a, {
            "responsavel_nome": "Joao Teste", "responsavel_nis": "12345678901",
        }))
        self.assertEqual(resp_a.status_code, 201)
        familia_a_id = json.loads(resp_a.content)["id"]

        gov.api_cras_familias(self._post(self.muni_b, {
            "responsavel_nome": "Joao Teste", "responsavel_nis": "12345678901",
        }))

        f_a = FamiliaCRAS.objects.get(id=familia_a_id)
        self.assertEqual(f_a.situacao, "suspensa")

    def test_sem_cpf_e_sem_nis_nao_cruza(self):
        gov.api_cras_familias(self._post(self.muni_a, {"responsavel_nome": "Sem Documento"}))
        gov.api_cras_familias(self._post(self.muni_b, {"responsavel_nome": "Sem Documento"}))
        self.assertEqual(IndiceCadastroSocial.objects.count(), 0)


class EdicaoNaoDisparaSuspensaoTests(_AuthMixin, TestCase):
    """Editar o PRÓPRIO cadastro (mesma empresa) nunca deve suspender nada."""

    def setUp(self):
        self.rf = RequestFactory()
        self.muni_a = _empresa("a@t.com", "governo_municipio_pequeno", cidade="Município A")
        self.familia = FamiliaCRAS.objects.create(
            empresa=self.muni_a, responsavel_nome="Ana Teste", responsavel_cpf="22233344405",
        )

    def test_put_na_mesma_empresa_nao_suspende(self):
        r = self.rf.put("/", data=json.dumps({"observacoes": "atualizado"}), content_type="application/json")
        r.empresa = self.muni_a
        r.principal = None
        resp = gov.api_cras_familia_detalhe(r, self.familia.id)
        self.assertEqual(resp.status_code, 200)

        self.familia.refresh_from_db()
        self.assertEqual(self.familia.situacao, "em_acompanhamento")
        self.assertFalse(IndiceCadastroSocial.objects.filter(cpf="22233344405").exists())


class ContestarSuspensaoTests(_AuthMixin, TestCase):
    """Fluxo de contestação/reativação pelo gestor do município antigo."""

    def setUp(self):
        self.rf = RequestFactory()
        self.muni_a = _empresa("a@t.com", "governo_municipio_pequeno", cidade="Município A")
        self.muni_b = _empresa("b@t.com", "governo_municipio_pequeno", cidade="Município B")
        self.familia = FamiliaCRAS.objects.create(
            empresa=self.muni_a, responsavel_nome="Pedro Teste", responsavel_cpf="33322211169",
        )
        self.familia.situacao = "suspensa"
        self.familia.motivo_suspensao = "Recadastrado em Município B em 01/01/2026."
        self.familia.save()

    def test_reativar_via_endpoint(self):
        resp = gov.api_cras_familia_reativar(
            self._post(self.muni_a, {"revisado_por": "Gestor A"}), self.familia.id)
        self.assertEqual(resp.status_code, 200)

        self.familia.refresh_from_db()
        self.assertEqual(self.familia.situacao, "em_acompanhamento")
        self.assertEqual(self.familia.contestado_por, "Gestor A")
        self.assertIsNotNone(self.familia.contestado_em)

    def test_nao_reativa_se_nao_estiver_suspensa(self):
        self.familia.situacao = "em_acompanhamento"
        self.familia.save()
        resp = gov.api_cras_familia_reativar(self._post(self.muni_a, {}), self.familia.id)
        self.assertEqual(resp.status_code, 400)

    def test_outra_empresa_nao_reativa_cadastro_alheio(self):
        resp = gov.api_cras_familia_reativar(self._post(self.muni_b, {}), self.familia.id)
        self.assertEqual(resp.status_code, 404)

    def test_contestar_suspensao_service_direto(self):
        contestar_suspensao(familia=self.familia, revisado_por="Supervisor")
        self.familia.refresh_from_db()
        self.assertEqual(self.familia.situacao, "em_acompanhamento")
        self.assertEqual(self.familia.contestado_por, "Supervisor")


class CrossSegmentoGovernoAssistenciaTests(_AuthMixin, TestCase):
    """O índice cruza entre Governo e Assistência Social — mesmos models,
    duas portas de entrada diferentes (ver api/services/suas.py)."""

    def setUp(self):
        self.rf = RequestFactory()
        self.gov_emp = _empresa("gov@t.com", "governo_municipio_pequeno", cidade="Cidade Governo")
        self.ass_emp = _empresa("ass@t.com", "assistencia_municipio_pequeno", cidade="Cidade Assistencia")

    def test_cadastro_no_governo_depois_na_assistencia_de_outro_municipio_suspende(self):
        resp_gov = gov.api_cras_familias(self._post(self.gov_emp, {
            "responsavel_nome": "Carla Teste", "responsavel_cpf": "44455566619",
        }))
        familia_gov_id = json.loads(resp_gov.content)["id"]

        ass.api_ass_cras_familias(self._post(self.ass_emp, {
            "responsavel_nome": "Carla Teste", "responsavel_cpf": "44455566619",
        }))

        f_gov = FamiliaCRAS.objects.get(id=familia_gov_id)
        self.assertEqual(f_gov.situacao, "suspensa")


class AlertasAntifraudeEndpointTests(_AuthMixin, TestCase):
    """Listagem e marcação de leitura dos alertas — cada município só vê os seus."""

    def setUp(self):
        self.rf = RequestFactory()
        self.muni_a = _empresa("a@t.com", "governo_municipio_pequeno", cidade="Município A")
        self.muni_b = _empresa("b@t.com", "governo_municipio_pequeno", cidade="Município B")
        gov.api_cras_familias(self._post(self.muni_a, {
            "responsavel_nome": "Lia Teste", "responsavel_cpf": "11144477735"}))
        gov.api_cras_familias(self._post(self.muni_b, {
            "responsavel_nome": "Lia Teste", "responsavel_cpf": "11144477735"}))

    def _lista(self, view, empresa, query=""):
        resp = view(self._get(empresa, query))
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.content)["alertas"]

    def test_cada_municipio_ve_so_os_proprios_alertas(self):
        alertas_a = self._lista(gov.api_cras_alertas_antifraude, self.muni_a)
        alertas_b = self._lista(gov.api_cras_alertas_antifraude, self.muni_b)
        self.assertEqual([a["tipo"] for a in alertas_a], ["suspensao_registro"])
        self.assertEqual([a["tipo"] for a in alertas_b], ["registro_anterior_detectado"])
        ids_a = {a["id"] for a in alertas_a}
        self.assertTrue(ids_a.isdisjoint({a["id"] for a in alertas_b}))

    def test_lista_nao_expoe_cpf_nem_nis(self):
        alerta = self._lista(gov.api_cras_alertas_antifraude, self.muni_a)[0]
        self.assertNotIn("cpf", alerta)
        self.assertNotIn("nis", alerta)

    def test_marcar_lido_some_da_lista_padrao(self):
        alerta_id = self._lista(gov.api_cras_alertas_antifraude, self.muni_a)[0]["id"]
        resp = gov.api_cras_alerta_antifraude_lida(self._post(self.muni_a, {}), alerta_id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._lista(gov.api_cras_alertas_antifraude, self.muni_a), [])
        todas = self._lista(gov.api_cras_alertas_antifraude, self.muni_a, "todas=1")
        self.assertEqual(len(todas), 1)
        self.assertTrue(todas[0]["lida"])

    def test_outro_municipio_nao_marca_alerta_alheio(self):
        alerta_id = self._lista(gov.api_cras_alertas_antifraude, self.muni_a)[0]["id"]
        resp = gov.api_cras_alerta_antifraude_lida(self._post(self.muni_b, {}), alerta_id)
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(AlertaAntifraudeSocial.objects.get(id=alerta_id).lida)


class AlertasAntifraudeAssistenciaTests(_AuthMixin, TestCase):
    """Mesmos endpoints na porta da Assistência Social."""

    def setUp(self):
        self.rf = RequestFactory()
        self.ass_a = _empresa("assa@t.com", "assistencia_municipio_pequeno", cidade="Assist A")
        self.ass_b = _empresa("assb@t.com", "assistencia_municipio_pequeno", cidade="Assist B")
        ass.api_ass_cras_familias(self._post(self.ass_a, {
            "responsavel_nome": "Rui Teste", "responsavel_cpf": "44455566619"}))
        ass.api_ass_cras_familias(self._post(self.ass_b, {
            "responsavel_nome": "Rui Teste", "responsavel_cpf": "44455566619"}))

    def test_lista_e_marca_lido(self):
        resp = ass.api_ass_cras_alertas_antifraude(self._get(self.ass_a))
        self.assertEqual(resp.status_code, 200)
        alertas = json.loads(resp.content)["alertas"]
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "suspensao_registro")

        resp = ass.api_ass_cras_alerta_antifraude_lida(self._post(self.ass_a, {}), alertas[0]["id"])
        self.assertEqual(resp.status_code, 200)
        resp = ass.api_ass_cras_alertas_antifraude(self._get(self.ass_a))
        self.assertEqual(json.loads(resp.content)["alertas"], [])

    def test_isolamento_entre_municipios(self):
        alerta_a = AlertaAntifraudeSocial.objects.get(empresa=self.ass_a)
        resp = ass.api_ass_cras_alerta_antifraude_lida(self._post(self.ass_b, {}), alerta_a.id)
        self.assertEqual(resp.status_code, 404)
        resp = ass.api_ass_cras_alertas_antifraude(self._get(self.ass_b))
        tipos = [a["tipo"] for a in json.loads(resp.content)["alertas"]]
        self.assertEqual(tipos, ["registro_anterior_detectado"])
