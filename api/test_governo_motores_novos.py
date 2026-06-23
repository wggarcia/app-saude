"""
Testes dos 7 motores de Governo construídos na auditoria de jun/2026:
Painel Eletrônico de Chamado, GED, TFD/Veículos, Almoxarifado, Laboratório
(LIS), Sala de Situação Epidemiológica e App Cidadão.

Cobre, para cada módulo: página acessível para tenant de Governo, bloqueada
para tenant de outro setor, e um roundtrip básico de criação via API.
"""
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, EmpresaUnidade


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


def _empresa(nome, email, pacote_codigo, tipo_conta=Empresa.TIPO_GOVERNO):
    return Empresa.objects.create(
        nome=nome,
        email=email,
        senha=make_password("123456"),
        ativo=True,
        tipo_conta=tipo_conta,
        pacote_codigo=pacote_codigo,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _governo():
    return _empresa("Prefeitura Teste", "governo-teste@example.com", "governo_municipio_pequeno")


def _hospital_intruso():
    return _empresa(
        "Hospital Intruso", "hospital-intruso@example.com", "hospital_medio", tipo_conta=Empresa.TIPO_EMPRESA
    )


class PainelChamadoTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/painel-chamado/").status_code, 302)

    def test_pagina_liberada_e_gera_senha(self):
        client = _client_for(_governo())
        self.assertEqual(client.get("/governo/painel-chamado/").status_code, 200)

        r = client.post(
            "/api/governo/painel-chamado/gerar/",
            data={"tipo": "normal"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["senha"])


class GEDTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/ged/").status_code, 302)

    def test_pagina_liberada_e_lista_documentos(self):
        client = _client_for(_governo())
        self.assertEqual(client.get("/governo/ged/").status_code, 200)

        r = client.get("/api/governo/ged/documentos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("total", len(r.json().get("documentos", []))), 0)


class TFDTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/tfd/").status_code, 302)

    def test_pagina_liberada_e_cria_veiculo_e_viagem(self):
        client = _client_for(_governo())
        self.assertEqual(client.get("/governo/tfd/").status_code, 200)

        r = client.post(
            "/api/governo/tfd/veiculos/",
            data={"placa": "ABC1D23", "modelo": "Sprinter", "tipo": "van"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        veiculo_id = r.json()["id"]

        r = client.post(
            "/api/governo/tfd/viagens/",
            data={
                "paciente_nome": "Paciente TFD",
                "destino_cidade": "Capital",
                "data_viagem": timezone.now().isoformat(),
                "veiculo_id": veiculo_id,
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)


class AlmoxarifadoTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/almoxarifado/").status_code, 302)

    def test_pagina_liberada_e_cria_produto_e_lote(self):
        empresa = _governo()
        client = _client_for(empresa)
        self.assertEqual(client.get("/governo/almoxarifado/").status_code, 200)

        r = client.post(
            "/api/governo/almoxarifado/produtos/",
            data={"nome": "Dipirona 500mg"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        produto_id = r.json()["id"]

        unidade = EmpresaUnidade.objects.create(empresa=empresa, nome="UBS Central")

        r = client.post(
            "/api/governo/almoxarifado/lotes/",
            data={
                "unidade_id": unidade.id,
                "produto_id": produto_id,
                "quantidade": "100",
                "data_validade": (date.today() + timedelta(days=180)).isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)


class LaboratorioTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/laboratorio/").status_code, 302)

    def test_pagina_liberada_e_cria_exame_e_solicitacao(self):
        empresa = _governo()
        client = _client_for(empresa)
        self.assertEqual(client.get("/governo/laboratorio/").status_code, 200)

        r = client.post(
            "/api/governo/laboratorio/catalogo/",
            data={"nome": "Hemograma Completo"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        exame_id = r.json()["id"]

        r = client.post(
            "/api/governo/laboratorio/solicitacoes/",
            data={"exame_id": exame_id, "paciente_nome": "Paciente Lab"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["protocolo"])


class SalaSituacaoTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/sala-situacao/").status_code, 302)

    def test_pagina_e_api_liberadas_para_governo(self):
        client = _client_for(_governo())
        self.assertEqual(client.get("/governo/sala-situacao/").status_code, 200)

        r = client.get("/api/governo/sala-situacao/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("nivel_situacional", r.json())


class AppCidadaoTests(TestCase):
    def test_pagina_bloqueada_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        self.assertEqual(client.get("/governo/app-cidadao/").status_code, 302)

    def test_pagina_liberada_e_cria_alerta(self):
        client = _client_for(_governo())
        self.assertEqual(client.get("/governo/app-cidadao/").status_code, 200)

        r = client.post(
            "/api/governo/app-cidadao/alertas/",
            data={"titulo": "Campanha de Vacinação", "mensagem": "Compareça à UBS mais próxima."},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["alerta"]["status"], "rascunho")
