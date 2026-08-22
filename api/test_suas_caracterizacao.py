"""
Testes de CARACTERIZAÇÃO do SUAS — rede de segurança antes de deduplicar o código.

O SUAS existe em DOIS lados (decisão de produto — duas ofertas):
  • Governo   → views_governo_suas_* (setor "governo", feature governo.suas)
  • Assistência isolada → views_assistencia_* (setor "assistencia_social", feature assistencia.cras_paif)

Ambos operam sobre os MESMOS models (UnidadeCRAS, FamiliaCRAS, ...). Estes testes
capturam o comportamento ATUAL de cada lado — inclusive as diferenças sutis de
contrato de resposta — para que a futura extração de um núcleo comum
(api/services/suas.py) não altere nada sem o teste acusar.

NÃO refatore o SUAS sem estes testes verdes antes e depois.
"""
import json
from datetime import date

from django.contrib.auth.hashers import make_password
from django.test import TestCase, RequestFactory

from .models import (
    Empresa, UnidadeCRAS, FamiliaCRAS, AtendimentoCRAS, VisitaDomiciliarSocial,
)
from . import views_governo_suas_cras as gov
from . import views_assistencia_cras as ass


def _empresa(email, pacote):
    return Empresa.objects.create(
        nome=f"Test {email}", email=email, senha=make_password("x"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


class _AuthMixin:
    """Monta um request com a empresa já autenticada (simula o middleware:
    request.empresa setado; sem principal → conta principal = gerência → passa
    na operação setorial)."""
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


class SuasSetorGateTests(_AuthMixin, TestCase):
    """O gate de setor (_gov/_assoc) isola os dois ambientes."""
    def setUp(self):
        self.rf = RequestFactory()
        self.gov_emp = _empresa("gov@t.com", "governo_municipio_pequeno")
        self.ass_emp = _empresa("ass@t.com", "assistencia_municipio_pequeno")

    def test_governo_acessa_endpoint_governo(self):
        resp = gov.api_cras_unidades(self._get(self.gov_emp))
        self.assertEqual(resp.status_code, 200)

    def test_assistencia_nao_acessa_endpoint_governo(self):
        # empresa de assistência batendo no endpoint do governo → 403
        resp = gov.api_cras_unidades(self._get(self.ass_emp))
        self.assertEqual(resp.status_code, 403)

    def test_assistencia_acessa_endpoint_assistencia(self):
        resp = ass.api_ass_cras_unidades(self._get(self.ass_emp))
        self.assertEqual(resp.status_code, 200)

    def test_governo_nao_acessa_endpoint_assistencia(self):
        resp = ass.api_ass_cras_unidades(self._get(self.gov_emp))
        self.assertEqual(resp.status_code, 403)


class SuasCrasUnidadesContratoTests(_AuthMixin, TestCase):
    """Trava o contrato de resposta de CADA lado — eles são diferentes de
    propósito e a refatoração NÃO pode uniformizá-los."""
    def setUp(self):
        self.rf = RequestFactory()
        self.gov_emp = _empresa("gov@t.com", "governo_municipio_pequeno")
        self.ass_emp = _empresa("ass@t.com", "assistencia_municipio_pequeno")
        self.outro_gov = _empresa("gov2@t.com", "governo_municipio_pequeno")
        self.u_gov = UnidadeCRAS.objects.create(
            empresa=self.gov_emp, nome="CRAS Centro", codigo_cras="C1",
            municipio="Campo Grande", uf="MS")
        self.u_ass = UnidadeCRAS.objects.create(
            empresa=self.ass_emp, nome="CRAS Norte", codigo_cras="N1",
            municipio="Dourados", uf="MS")
        # unidade de OUTRO tenant governo — nunca deve vazar
        UnidadeCRAS.objects.create(empresa=self.outro_gov, nome="CRAS Alheio")

    def test_governo_envelope_tem_total_e_unidades(self):
        resp = gov.api_cras_unidades(self._get(self.gov_emp))
        data = json.loads(resp.content)
        self.assertIn("total", data)          # ← contrato do Governo TEM "total"
        self.assertIn("unidades", data)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["unidades"]), 1)
        self.assertEqual(data["unidades"][0]["nome"], "CRAS Centro")

    def test_assistencia_envelope_tem_unidades_sem_total(self):
        resp = ass.api_ass_cras_unidades(self._get(self.ass_emp))
        data = json.loads(resp.content)
        self.assertIn("unidades", data)
        self.assertNotIn("total", data)       # ← contrato da Assistência NÃO tem "total"
        self.assertEqual(len(data["unidades"]), 1)
        self.assertEqual(data["unidades"][0]["nome"], "CRAS Norte")

    def test_cras_dict_campos_identicos_nos_dois_lados(self):
        # o serializador _cras_dict é o mesmo objeto compartilhável — trava as chaves
        campos = {"id", "nome", "codigo_cras", "cnes", "endereco", "bairro",
                  "municipio", "uf", "cep", "telefone", "email",
                  "responsavel_tecnico", "ativo"}
        g = json.loads(gov.api_cras_unidades(self._get(self.gov_emp)).content)["unidades"][0]
        a = json.loads(ass.api_ass_cras_unidades(self._get(self.ass_emp)).content)["unidades"][0]
        self.assertEqual(set(g.keys()), campos)
        self.assertEqual(set(a.keys()), campos)

    def test_isolamento_tenant_governo(self):
        # gov_emp só vê a sua unidade, nunca a do outro_gov
        data = json.loads(gov.api_cras_unidades(self._get(self.gov_emp)).content)
        nomes = [u["nome"] for u in data["unidades"]]
        self.assertIn("CRAS Centro", nomes)
        self.assertNotIn("CRAS Alheio", nomes)

    def test_detalhe_governo_retorna_cras_dict_puro(self):
        resp = gov.api_cras_unidade_detalhe(self._get(self.gov_emp), self.u_gov.id)
        data = json.loads(resp.content)
        self.assertEqual(data["nome"], "CRAS Centro")
        self.assertEqual(data["codigo_cras"], "C1")

    def test_detalhe_governo_404_para_unidade_de_outro_tenant(self):
        resp = gov.api_cras_unidade_detalhe(self._get(self.gov_emp), 999999)
        self.assertEqual(resp.status_code, 404)


class SuasCrasDominioTests(_AuthMixin, TestCase):
    """Smoke + isolamento dos demais endpoints CRAS dos dois lados: famílias,
    atendimentos, visitas e KPIs respondem 200 com dado do próprio tenant."""
    def setUp(self):
        self.rf = RequestFactory()
        self.gov_emp = _empresa("gov@t.com", "governo_municipio_pequeno")
        self.ass_emp = _empresa("ass@t.com", "assistencia_municipio_pequeno")
        for emp in (self.gov_emp, self.ass_emp):
            unidade = UnidadeCRAS.objects.create(empresa=emp, nome="CRAS", municipio="CG", uf="MS")
            fam = FamiliaCRAS.objects.create(
                empresa=emp, unidade_cras=unidade, responsavel_nome="Maria Silva",
                numero_prontuario="P1", num_integrantes=3)
            AtendimentoCRAS.objects.create(
                empresa=emp, familia=fam, unidade_cras=unidade,
                tecnico_nome="Ana", data_atendimento=date(2026, 8, 1), tipo="individual")
            VisitaDomiciliarSocial.objects.create(
                empresa=emp, familia=fam, tecnico_nome="João", data_visita=date(2026, 8, 2))

    def test_governo_familias_lista(self):
        resp = gov.api_cras_familias(self._get(self.gov_emp))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(json.loads(resp.content), dict)

    def test_assistencia_familias_lista(self):
        resp = ass.api_ass_cras_familias(self._get(self.ass_emp))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(json.loads(resp.content), dict)

    def test_governo_atendimentos_lista(self):
        resp = gov.api_cras_atendimentos(self._get(self.gov_emp))
        self.assertEqual(resp.status_code, 200)

    def test_assistencia_atendimentos_lista(self):
        resp = ass.api_ass_cras_atendimentos(self._get(self.ass_emp))
        self.assertEqual(resp.status_code, 200)

    def test_atendimento_dict_divergencia_tipo_display(self):
        # DIVERGÊNCIA INTENCIONAL: o Governo expõe "tipo_display", a Assistência NÃO.
        # A extração de núcleo comum NÃO pode uniformizar isto.
        g = json.loads(gov.api_cras_atendimentos(self._get(self.gov_emp)).content)["atendimentos"][0]
        a = json.loads(ass.api_ass_cras_atendimentos(self._get(self.ass_emp)).content)["atendimentos"][0]
        self.assertIn("tipo_display", g)       # ← Governo TEM
        self.assertNotIn("tipo_display", a)    # ← Assistência NÃO tem

    def test_governo_visitas_lista(self):
        resp = gov.api_cras_visitas(self._get(self.gov_emp))
        self.assertEqual(resp.status_code, 200)

    def test_assistencia_visitas_lista(self):
        resp = ass.api_ass_cras_visitas(self._get(self.ass_emp))
        self.assertEqual(resp.status_code, 200)

    def test_governo_kpis(self):
        resp = gov.api_cras_kpis(self._get(self.gov_emp))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(json.loads(resp.content), dict)

    def test_assistencia_kpis(self):
        resp = ass.api_ass_cras_kpis(self._get(self.ass_emp))
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(json.loads(resp.content), dict)
