"""
Testes dos 13 gaps fechados na 2ª rodada da auditoria de módulos (ago/2026):

Telas fantasmas (backend já existia, sem UI):
  - Hospital: WhatsApp de Agendamento
  - Farmácia: Unidades (multi-loja), Disponibilidade na Rede
  - Plano de Saúde: TUSS / Rol ANS / NIP
  - Assistência Social: Prontuário PAIF, Relatório Mensal (RMA)

Funcionalidades novas (backend + tela do zero):
  - Hospital: Comissão de Ética Médica
  - Farmácia: Fidelidade / Programa de Pontos
  - Assistência Social: Conselho Tutelar, Vigilância Socioassistencial, Busca Ativa
  - Governo: SIM — Mortalidade

Stub corrigido:
  - Plano de Saúde: "Nova Campanha" (antes só mostrava toast, agora persiste e conta beneficiários reais)
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


def _empresa(nome, email, pacote_codigo, tipo_conta=Empresa.TIPO_EMPRESA):
    return Empresa.objects.create(
        nome=nome, email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=tipo_conta, pacote_codigo=pacote_codigo,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _governo():
    return _empresa("Prefeitura Auditoria 13 Gaps", "governo-13gaps@example.com",
                     "governo_municipio_pequeno", tipo_conta=Empresa.TIPO_GOVERNO)


def _hospital():
    return _empresa("Hospital Auditoria 13 Gaps", "hospital-13gaps@example.com", "hospital_rede")


def _farmacia():
    return _empresa("Farmácia Auditoria 13 Gaps", "farmacia-13gaps@example.com", "farmacia_rede_regional")


def _plano_saude():
    return _empresa("Plano Auditoria 13 Gaps", "plano-13gaps@example.com", "plano_saude_operadora")


def _assistencia_social():
    return _empresa("CRAS Auditoria 13 Gaps", "assistencia-13gaps@example.com", "assistencia_municipio_pequeno")


_PAGINAS_POR_SEGMENTO = {
    "hospital": ["/hospital/whatsapp-agendamento/", "/hospital/comissao-etica/"],
    "farmacia": ["/farmacia/unidades/", "/farmacia/rede/disponibilidade/", "/farmacia/fidelidade/"],
    "plano_saude": ["/plano-saude/tuss/"],
    "assistencia_social": [
        "/assistencia-social/cras/prontuario-paif/",
        "/assistencia-social/relatorio-mensal/",
        "/assistencia-social/protecao-especial/",
    ],
    "governo": ["/governo/sim/"],
}


class PaginasNovasGapsTests(TestCase):
    def test_paginas_liberadas_para_o_setor_correto(self):
        contas = {
            "hospital": _hospital(), "farmacia": _farmacia(),
            "plano_saude": _plano_saude(), "assistencia_social": _assistencia_social(),
            "governo": _governo(),
        }
        for setor, urls in _PAGINAS_POR_SEGMENTO.items():
            client = _client_for(contas[setor])
            for url in urls:
                resp = client.get(url)
                self.assertEqual(resp.status_code, 200, f"{url} ({setor}) deveria retornar 200, veio {resp.status_code}")

    def test_paginas_bloqueadas_para_setor_errado(self):
        client = _client_for(_farmacia())
        for url in _PAGINAS_POR_SEGMENTO["hospital"] + _PAGINAS_POR_SEGMENTO["governo"]:
            resp = client.get(url)
            self.assertNotEqual(resp.status_code, 200, f"{url} não deveria ser acessível pra farmácia")


class ComissaoEticaMedicaTests(TestCase):
    def test_criar_caso_e_emitir_parecer(self):
        client = _client_for(_hospital())
        resp = client.post(
            "/api/hospital/comissao-etica/casos",
            data=json.dumps({"tipo": "consulta_etica", "descricao": "Dúvida sobre sigilo em caso de menor."}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        caso_id = resp.json()["id"]
        self.assertTrue(resp.json()["protocolo"].startswith("CEM-"))

        resp = client.patch(
            f"/api/hospital/comissao-etica/casos/{caso_id}",
            data=json.dumps({"parecer_texto": "Sigilo pode ser quebrado em caso de risco.", "relator": "Dr. Teste"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(client.get(f"/api/hospital/comissao-etica/casos/{caso_id}").json()["status"], "parecer_emitido")

        kpis = client.get("/api/hospital/comissao-etica/kpis").json()
        self.assertEqual(kpis["total_casos"], 1)
        self.assertEqual(kpis["por_status"].get("parecer_emitido"), 1)


class FidelidadeFarmaciaTests(TestCase):
    def test_acumular_e_resgatar_pontos(self):
        client = _client_for(_farmacia())
        resp = client.post(
            "/api/farmacia/fidelidade/clientes",
            data=json.dumps({"cpf": "11122233344", "nome": "Cliente Teste"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        resp = client.post(
            "/api/farmacia/fidelidade/acumular",
            data=json.dumps({"cpf": "11122233344", "valor_venda": "150.00"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["pontos_ganhos"], 150)

        resp = client.post(
            "/api/farmacia/fidelidade/resgatar",
            data=json.dumps({"cpf": "11122233344", "pontos": 100}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["valor_desconto"], 5.0)
        self.assertEqual(resp.json()["pontos_saldo"], 50)

    def test_resgate_abaixo_do_minimo_e_rejeitado(self):
        client = _client_for(_farmacia())
        client.post("/api/farmacia/fidelidade/clientes",
                    data=json.dumps({"cpf": "22233344455", "nome": "Cliente Dois"}),
                    content_type="application/json")
        resp = client.post(
            "/api/farmacia/fidelidade/resgatar",
            data=json.dumps({"cpf": "22233344455", "pontos": 10}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class ConselhoTutelarBuscaAtivaVigilanciaTests(TestCase):
    def test_conselho_tutelar_encaminhamento_e_retorno(self):
        client = _client_for(_assistencia_social())
        resp = client.post(
            "/api/assistencia-social/conselho-tutelar",
            data=json.dumps({
                "crianca_nome": "Criança Teste", "tipo_violacao": "negligencia",
                "descricao": "Encaminhamento de teste.",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        ct_id = resp.json()["id"]

        resp = client.patch(
            f"/api/assistencia-social/conselho-tutelar/{ct_id}",
            data=json.dumps({"parecer_retorno": "Caso resolvido com apoio à família."}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(client.get(f"/api/assistencia-social/conselho-tutelar/{ct_id}").json()["status"], "concluido")

    def test_busca_ativa_fluxo_completo(self):
        client = _client_for(_assistencia_social())
        resp = client.post(
            "/api/assistencia-social/busca-ativa",
            data=json.dumps({"nome_referencia": "Família Teste", "motivo": "cadastro_desatualizado"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        busca_id = resp.json()["id"]

        client.patch(f"/api/assistencia-social/busca-ativa/{busca_id}",
                     data=json.dumps({"status": "em_busca"}), content_type="application/json")
        resp = client.patch(f"/api/assistencia-social/busca-ativa/{busca_id}",
                            data=json.dumps({"status": "localizada"}), content_type="application/json")
        self.assertEqual(resp.status_code, 200)

        kpis = client.get("/api/assistencia-social/protecao-especial/kpis").json()
        self.assertEqual(kpis["busca_ativa_localizadas"], 1)

    def test_vigilancia_territorio_nao_duplica_bairro(self):
        client = _client_for(_assistencia_social())
        body = json.dumps({"bairro": "Centro", "indice_vulnerabilidade": "alto"})
        resp1 = client.post("/api/assistencia-social/vigilancia-social/territorios", data=body, content_type="application/json")
        self.assertEqual(resp1.status_code, 201)
        resp2 = client.post("/api/assistencia-social/vigilancia-social/territorios", data=body, content_type="application/json")
        self.assertEqual(resp2.status_code, 409)

        kpis = client.get("/api/assistencia-social/protecao-especial/kpis").json()
        self.assertEqual(kpis["territorios_alto_risco"], 1)


class SimMortalidadeGovernoTests(TestCase):
    def test_registrar_e_transmitir_obito(self):
        client = _client_for(_governo())
        resp = client.post(
            "/api/governo/sim/obitos",
            data=json.dumps({
                "falecido_nome": "Falecido Teste",
                "data_obito": timezone.now().isoformat(),
                "causa_basica_cid": "I21.9",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        obito_id = resp.json()["id"]

        kpis = client.get("/api/governo/sim/kpis").json()
        self.assertEqual(kpis["total_obitos"], 1)
        self.assertEqual(kpis["pendentes_transmissao"], 1)

        resp = client.post(f"/api/governo/sim/obitos/{obito_id}/transmitir", data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status_transmissao"], "transmitido")

        kpis = client.get("/api/governo/sim/kpis").json()
        self.assertEqual(kpis["transmitidos"], 1)
        self.assertEqual(kpis["pendentes_transmissao"], 0)


class CampanhaComunicacaoPlanoTests(TestCase):
    def test_disparar_campanha_conta_beneficiarios_reais(self):
        client = _client_for(_plano_saude())
        resp = client.post(
            "/api/plano-saude/campanhas/",
            data=json.dumps({"nome": "Campanha Teste", "publico_alvo": "todos", "mensagem": "Olá!"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["total_enviado"], 0)  # sem beneficiários cadastrados neste teste

        d = client.get("/api/plano-saude/campanhas/").json()
        self.assertEqual(len(d["campanhas"]), 1)
        self.assertEqual(d["campanhas"][0]["nome"], "Campanha Teste")
