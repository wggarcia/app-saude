"""
Testes de integração — Ordem de Produção Industrial (motor anti-erro).

Cobre o núcleo do desafio FIERGS/IEL:
  • validação de faixa no preenchimento (dentro → ok, fora → erro + desvio);
  • bloqueio de avanço de etapa incompleta / sem assinatura (guarda FSM);
  • assinatura de etapa (SHA-256 fallback) e avanço liberado após assinar;
  • fluxo completo até liberação e cálculo de RFT;
  • rejeição de transição inválida.
"""
import json
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (Empresa, EspecificacaoProducao, OrdemProducaoIndustrial,
                     DesvioProducao, RegistroCampoProducao)


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa",
        "principal_id": empresa.id, "session_key": empresa.sessao_ativa_chave,
        "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _farmacia(email="prod-farma@example.com"):
    return Empresa.objects.create(
        nome="Indústria Farma Teste", email=email, senha=make_password("123456"),
        ativo=True, tipo_conta=Empresa.TIPO_EMPRESA,
        pacote_codigo="farmacia_rede_regional", sessao_ativa_chave=f"sessao-{email}",
    )


ETAPAS = [
    {"chave": "pesagem", "rotulo": "Pesagem", "papel_assina": "operador"},
    {"chave": "compressao", "rotulo": "Compressão", "papel_assina": "supervisor"},
]
CAMPOS = [
    {"chave": "peso_ativo", "rotulo": "Peso do ativo", "etapa": "pesagem",
     "tipo": "numero", "obrigatorio": True, "min": 495, "max": 505, "unidade": "mg"},
    {"chave": "peso_nucleo", "rotulo": "Peso do núcleo", "etapa": "compressao",
     "tipo": "numero", "obrigatorio": True, "min": 580, "max": 620, "unidade": "mg"},
]


class ProducaoIndustrialTest(TestCase):
    def setUp(self):
        self.empresa = _farmacia()
        self.client = _client_for(self.empresa)

    def _post(self, url, body):
        return self.client.post(url, data=json.dumps(body),
                                content_type="application/json")

    def _patch(self, url, body):
        return self.client.patch(url, data=json.dumps(body),
                                 content_type="application/json")

    def _criar_especificacao(self):
        r = self._post("/api/producao/especificacoes", {
            "codigo_produto": "PARA500", "nome": "Paracetamol 500mg",
            "forma_farmaceutica": "comprimido", "concentracao": "500 mg",
            "tamanho_lote_padrao": 100000, "rendimento_teorico": 100000,
            "faixa_rendimento_min": 98, "faixa_rendimento_max": 102,
            "etapas": ETAPAS, "campos": CAMPOS,
        })
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def _abrir_ordem(self, esp_id, numero="OP-001"):
        r = self._post("/api/producao/ordens", {
            "especificacao_id": esp_id, "numero_op": numero,
            "numero_lote_fabricacao": "L2608A", "tamanho_lote": 100000,
            "responsavel": "Fulano",
        })
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    # ── Testes ────────────────────────────────────────────────────────────────

    def test_validacao_faixa_dentro_e_fora(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        self._patch(f"/api/producao/ordens/{op}/avancar",
                    {"acao": "status", "novo": "em_producao"})

        # Dentro da faixa → ok, sem desvio.
        r = self._post(f"/api/producao/ordens/{op}/campo",
                       {"chave_campo": "peso_ativo", "valor": "500"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertFalse(r.json()["fora_faixa"])
        self.assertEqual(DesvioProducao.objects.filter(ordem_id=op, resolvido=False).count(), 0)

        # Fora da faixa → erro + desvio aberto.
        r = self._post(f"/api/producao/ordens/{op}/campo",
                       {"chave_campo": "peso_ativo", "valor": "600"})
        self.assertEqual(r.json()["status"], "erro")
        self.assertTrue(r.json()["fora_faixa"])
        self.assertEqual(
            DesvioProducao.objects.filter(ordem_id=op, tipo="faixa", resolvido=False).count(), 1)

        # Corrige → desvio resolve automaticamente.
        self._post(f"/api/producao/ordens/{op}/campo",
                   {"chave_campo": "peso_ativo", "valor": "498"})
        self.assertEqual(
            DesvioProducao.objects.filter(ordem_id=op, tipo="faixa", resolvido=False).count(), 0)

    def test_bloqueia_avanco_sem_assinatura_e_incompleto(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        self._patch(f"/api/producao/ordens/{op}/avancar",
                    {"acao": "status", "novo": "em_producao"})

        # Sem preencher nada: avançar é bloqueado (422).
        r = self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})
        self.assertEqual(r.status_code, 422, r.content)
        self.assertTrue(r.json()["motivos"])

        # Preenche o campo válido, mas ainda sem assinatura → continua bloqueado.
        self._post(f"/api/producao/ordens/{op}/campo",
                   {"chave_campo": "peso_ativo", "valor": "500"})
        r = self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(any("assinatura" in m.lower() for m in r.json()["motivos"]))

        # Assina a etapa → agora avança.
        r = self._post(f"/api/producao/ordens/{op}/assinar",
                       {"etapa": "pesagem", "papel": "operador", "assinante_nome": "Op 1"})
        self.assertEqual(r.status_code, 200, r.content)
        r = self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})
        self.assertEqual(r.status_code, 200, r.content)
        op_obj = OrdemProducaoIndustrial.objects.get(id=op)
        self.assertEqual(op_obj.etapa_atual, "compressao")

    def test_nao_assina_etapa_incompleta(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        self._patch(f"/api/producao/ordens/{op}/avancar",
                    {"acao": "status", "novo": "em_producao"})
        # Tenta assinar sem preencher o campo obrigatório.
        r = self._post(f"/api/producao/ordens/{op}/assinar",
                       {"etapa": "pesagem", "papel": "operador", "assinante_nome": "Op 1"})
        self.assertEqual(r.status_code, 422, r.content)

    def test_transicao_invalida_bloqueada(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        # rascunho → liberado é transição inválida.
        r = self._patch(f"/api/producao/ordens/{op}/avancar",
                        {"acao": "status", "novo": "liberado"})
        self.assertEqual(r.status_code, 422)

    def test_fluxo_completo_ate_liberado_e_rft(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        self._patch(f"/api/producao/ordens/{op}/avancar",
                    {"acao": "status", "novo": "em_producao"})

        # Pesagem
        self._post(f"/api/producao/ordens/{op}/campo",
                   {"chave_campo": "peso_ativo", "valor": "500"})
        self._post(f"/api/producao/ordens/{op}/assinar",
                   {"etapa": "pesagem", "papel": "operador", "assinante_nome": "Op 1"})
        self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})

        # Compressão
        self._post(f"/api/producao/ordens/{op}/campo",
                   {"chave_campo": "peso_nucleo", "valor": "600"})
        self._post(f"/api/producao/ordens/{op}/assinar",
                   {"etapa": "compressao", "papel": "supervisor", "assinante_nome": "Sup 1"})
        # Última etapa → vai para CQ.
        r = self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(OrdemProducaoIndustrial.objects.get(id=op).status, "controle_qualidade")

        # CQ → revisão (rendimento dentro da faixa: 99.500/100.000 = 99,5%)
        r = self._patch(f"/api/producao/ordens/{op}/avancar",
                        {"acao": "status", "novo": "revisao_qualidade",
                         "rendimento_real": 99500})
        self.assertEqual(r.status_code, 200, r.content)

        # Assinatura da GQ + liberação
        self._post(f"/api/producao/ordens/{op}/assinar",
                   {"etapa": "compressao", "papel": "farmaceutico_qa", "assinante_nome": "QA 1"})
        r = self._patch(f"/api/producao/ordens/{op}/avancar",
                        {"acao": "status", "novo": "liberado"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(OrdemProducaoIndustrial.objects.get(id=op).status, "liberado")

        # KPIs: RFT deve refletir a ordem liberada sem desvios.
        r = self.client.get("/api/producao/kpis")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["finalizadas"], 1)
        self.assertEqual(r.json()["rft_pct"], 100.0)

    def test_rendimento_fora_da_faixa_bloqueia_revisao(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        self._patch(f"/api/producao/ordens/{op}/avancar",
                    {"acao": "status", "novo": "em_producao"})
        for etapa, papel, chave, val in [
            ("pesagem", "operador", "peso_ativo", "500"),
            ("compressao", "supervisor", "peso_nucleo", "600"),
        ]:
            self._post(f"/api/producao/ordens/{op}/campo",
                       {"chave_campo": chave, "valor": val})
            self._post(f"/api/producao/ordens/{op}/assinar",
                       {"etapa": etapa, "papel": papel, "assinante_nome": "X"})
        self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})
        self._patch(f"/api/producao/ordens/{op}/avancar", {"acao": "proxima_etapa"})

        # Rendimento 80% (80.000/100.000) → fora da faixa 98–102% → bloqueia.
        r = self._patch(f"/api/producao/ordens/{op}/avancar",
                        {"acao": "status", "novo": "revisao_qualidade",
                         "rendimento_real": 80000})
        self.assertEqual(r.status_code, 422, r.content)

    def test_isolamento_por_empresa(self):
        esp = self._criar_especificacao()
        op = self._abrir_ordem(esp)
        # Outra farmácia não enxerga a ordem da primeira.
        outra = _farmacia("outra-farma@example.com")
        cli2 = _client_for(outra)
        r = cli2.get(f"/api/producao/ordens/{op}")
        self.assertEqual(r.status_code, 404)
