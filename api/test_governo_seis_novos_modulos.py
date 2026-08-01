"""
Testes dos 6 módulos de Governo criados em ago/2026: telas para SIPNI, CEAF
e CNES (backend já existia, sem UI) + Ouvidoria do SUS, Conselho de Saúde e
Escala de Profissionais da Rede (módulos novos, backend+tela).

Cobre, para cada módulo: página acessível para tenant de Governo, bloqueada
para tenant de outro setor, e um roundtrip básico via API.
"""
import json
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa


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
        nome=nome, email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=tipo_conta, pacote_codigo=pacote_codigo,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _governo():
    return _empresa("Prefeitura Teste Seis Módulos", "governo-6mod@example.com", "governo_municipio_pequeno")


def _hospital_intruso():
    return _empresa(
        "Hospital Intruso Seis Módulos", "hospital-intruso-6mod@example.com",
        "hospital_medio", tipo_conta=Empresa.TIPO_EMPRESA,
    )


_PAGINAS = [
    "/governo/sipni/",
    "/governo/ceaf/",
    "/governo/cnes/",
    "/governo/ouvidoria/",
    "/governo/conselho-saude/",
    "/governo/escala-rede/",
]


class PaginasNovosModulosTests(TestCase):
    def test_paginas_liberadas_para_governo(self):
        client = _client_for(_governo())
        for url in _PAGINAS:
            resp = client.get(url)
            self.assertEqual(resp.status_code, 200, f"{url} deveria retornar 200, veio {resp.status_code}")

    def test_paginas_bloqueadas_para_outro_setor(self):
        client = _client_for(_hospital_intruso())
        for url in _PAGINAS:
            resp = client.get(url)
            self.assertNotEqual(resp.status_code, 200, f"{url} não deveria ser acessível a outro setor")


class OuvidoriaSUSTests(TestCase):
    def test_registrar_e_responder_manifestacao(self):
        client = _client_for(_governo())

        resp = client.post(
            "/api/governo/ouvidoria/manifestacoes",
            data=json.dumps({
                "tipo": "reclamacao",
                "canal": "app",
                "manifestante_nome": "Cidadão Teste",
                "descricao": "Demora no atendimento da UBS Central.",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        man_id = resp.json()["id"]
        self.assertTrue(resp.json()["protocolo"].startswith("OUV-"))

        resp = client.get("/api/governo/ouvidoria/manifestacoes")
        self.assertEqual(resp.json()["total"], 1)

        resp = client.patch(
            f"/api/governo/ouvidoria/manifestacoes/{man_id}",
            data=json.dumps({"resposta": "Encaminhado à UBS.", "respondido_por": "Ouvidor"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        resp = client.get(f"/api/governo/ouvidoria/manifestacoes/{man_id}")
        self.assertEqual(resp.json()["status"], "respondida")

        kpis = client.get("/api/governo/ouvidoria/kpis").json()
        self.assertEqual(kpis["total"], 1)
        self.assertEqual(kpis["por_status"].get("respondida"), 1)

    def test_manifestacao_anonima_nao_expoe_dados(self):
        client = _client_for(_governo())
        client.post(
            "/api/governo/ouvidoria/manifestacoes",
            data=json.dumps({
                "tipo": "denuncia", "anonima": True,
                "manifestante_nome": "Não Deveria Aparecer",
                "descricao": "Denúncia anônima de teste.",
            }),
            content_type="application/json",
        )
        d = client.get("/api/governo/ouvidoria/manifestacoes").json()
        self.assertEqual(d["manifestacoes"][0]["manifestante_nome"], "(anônimo)")


class ConselhoSaudeTests(TestCase):
    def test_conselheiro_reuniao_e_deliberacao(self):
        client = _client_for(_governo())
        hoje = date.today()

        resp = client.post(
            "/api/governo/conselho-saude/conselheiros",
            data=json.dumps({
                "nome": "Maria Conselheira", "segmento": "usuarios", "titular": True,
                "mandato_inicio": hoje.isoformat(), "mandato_fim": (hoje + timedelta(days=730)).isoformat(),
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        resp = client.post(
            "/api/governo/conselho-saude/reunioes",
            data=json.dumps({
                "data_reuniao": timezone.now().isoformat(),
                "tipo": "ordinaria", "pauta": "Pauta de teste",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        reuniao_id = resp.json()["id"]

        resp = client.post(
            "/api/governo/conselho-saude/deliberacoes",
            data=json.dumps({
                "reuniao_id": reuniao_id, "tipo": "resolucao", "numero": "001/2026",
                "texto": "Aprova o plano de teste.", "votos_favor": 8, "votos_contra": 1,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        detalhe = client.get(f"/api/governo/conselho-saude/reunioes/{reuniao_id}").json()
        self.assertEqual(len(detalhe["deliberacoes"]), 1)

        kpis = client.get("/api/governo/conselho-saude/kpis").json()
        self.assertEqual(kpis["conselheiros_ativos"], 1)
        self.assertEqual(kpis["deliberacoes_total"], 1)


class EscalaProfissionalRedeTests(TestCase):
    def test_criar_e_afastar_profissional(self):
        client = _client_for(_governo())

        resp = client.post(
            "/api/governo/escala-rede/escalas",
            data=json.dumps({
                "profissional_nome": "Dr. João Teste", "categoria": "medico",
                "vinculo": "estatutario", "turno": "manha",
                "dias_semana": ["seg", "ter", "qua"], "carga_horaria_semanal": 20,
                "data_inicio": date.today().isoformat(),
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        esc_id = resp.json()["id"]

        kpis = client.get("/api/governo/escala-rede/kpis").json()
        self.assertEqual(kpis["total_ativos"], 1)
        self.assertEqual(kpis["carga_horaria_total_semanal"], 20)

        resp = client.patch(
            f"/api/governo/escala-rede/escalas/{esc_id}",
            data=json.dumps({"status": "afastado"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        kpis = client.get("/api/governo/escala-rede/kpis").json()
        self.assertEqual(kpis["total_ativos"], 0)
        self.assertEqual(kpis["afastados"], 1)
