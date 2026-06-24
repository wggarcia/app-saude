"""
Testes de regressão da varredura dinâmica completa do SST (jun/2026):
239 rotas de api/sst e sst/ foram percorridas com dados reais via test
client, revelando 6 bugs adicionais que a auditoria estática não cobria.

  - api_laudo_pdf / api_ppp_pdf / api_ppp_status_esocial: ID inexistente
    devia voltar 404, mas o "except Exception" genérico engolia o
    DoesNotExist específico do model e devolvia 500.
  - api_esocial_registrar_cat / _aso / _afastamento: não verificavam
    request.method, então um GET (não só POST) já criava de fato um
    evento eSocial — quebra a garantia de que GET é uma operação segura.
"""
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, FuncionarioSST, LaudoTecnicoSST, CATOcupacional, ASOOcupacional, AfastamentoSST


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
        nome="Empresa Robustez SST",
        email=email,
        senha=make_password("123456"),
        ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA,
        pacote_codigo="empresa_nacional_500",
        sessao_ativa_chave=f"sessao-{email}",
    )


class IdInexistenteRetorna404Tests(TestCase):
    def test_laudo_pdf_id_inexistente_e_404_nao_500(self):
        empresa = _empresa("robustez-laudo@example.com")
        client = _client_for(empresa)
        r = client.get("/api/sst/laudos/999999/pdf/")
        self.assertEqual(r.status_code, 404)

    def test_ppp_pdf_id_inexistente_e_404_nao_500(self):
        empresa = _empresa("robustez-ppp-pdf@example.com")
        client = _client_for(empresa)
        r = client.get("/api/sst/ppp/999999/pdf/")
        self.assertEqual(r.status_code, 404)

    def test_ppp_status_esocial_id_inexistente_e_404_nao_500(self):
        empresa = _empresa("robustez-ppp-status@example.com")
        client = _client_for(empresa)
        r = client.get("/api/sst/ppp/999999/status-esocial/")
        self.assertEqual(r.status_code, 404)


class EsocialExigePostTests(TestCase):
    def _funcionario(self, empresa):
        return FuncionarioSST.objects.create(
            empresa=empresa, nome="Func", cpf="12312312312", cargo="Op",
            data_admissao=date.today(), ativo=True,
        )

    def test_registrar_cat_via_get_e_rejeitado(self):
        empresa = _empresa("robustez-cat@example.com")
        f = self._funcionario(empresa)
        cat = CATOcupacional.objects.create(
            empresa=empresa, funcionario=f, tipo="tipico", data_acidente=date.today(),
            descricao="x", parte_corpo="mao", cod_parte_corpo="1", cod_agente_causador="1",
        )
        client = _client_for(empresa)
        r = client.get(f"/api/sst/cats/{cat.id}/esocial/")
        self.assertEqual(r.status_code, 405)

    def test_registrar_aso_via_get_e_rejeitado(self):
        empresa = _empresa("robustez-aso@example.com")
        f = self._funcionario(empresa)
        aso = ASOOcupacional.objects.create(
            empresa=empresa, funcionario=f, tipo="periodico",
            data_emissao=date.today(), resultado="apto",
        )
        client = _client_for(empresa)
        r = client.get(f"/api/sst/asos/{aso.id}/esocial/")
        self.assertEqual(r.status_code, 405)

    def test_registrar_afastamento_via_get_e_rejeitado(self):
        empresa = _empresa("robustez-afastamento@example.com")
        f = self._funcionario(empresa)
        af = AfastamentoSST.objects.create(
            empresa=empresa, funcionario=f, motivo="doenca_comum", data_inicio=date.today(),
        )
        client = _client_for(empresa)
        r = client.get(f"/api/sst/afastamentos/{af.id}/esocial/")
        self.assertEqual(r.status_code, 405)

    def test_registrar_cat_via_post_continua_funcionando(self):
        empresa = _empresa("robustez-cat-post@example.com")
        f = self._funcionario(empresa)
        cat = CATOcupacional.objects.create(
            empresa=empresa, funcionario=f, tipo="tipico", data_acidente=date.today(),
            descricao="x", parte_corpo="mao", cod_parte_corpo="1", cod_agente_causador="1",
        )
        client = _client_for(empresa)
        r = client.post(f"/api/sst/cats/{cat.id}/esocial/")
        self.assertEqual(r.status_code, 201)
