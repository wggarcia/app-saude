import json
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from . import epidemiologia
from .command_ai import build_command_ai_payload
from .models import AuditoriaInstitucional, Empresa, RegistroSintoma


class CommandAITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Hospital Premium",
            email="hospital@example.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            sessao_ativa_chave="sessao-command-ai",
        )
        self._reset_panorama_cache()
        self._seed_sinais()

    def _reset_panorama_cache(self):
        epidemiologia._PANORAMA_CACHE["created_at"] = 0.0
        epidemiologia._PANORAMA_CACHE["payload"] = None

    def _seed_sinais(self):
        for index in range(8):
            RegistroSintoma.objects.create(
                empresa=self.empresa,
                febre=True,
                dor_corpo=True,
                cansaco=index % 2 == 0,
                latitude=-23.5505,
                longitude=-46.6333,
                estado="SP",
                cidade="Sao Paulo",
                bairro="Centro",
                confianca=0.92,
                suspeito=False,
            )

        antigos = []
        for _ in range(2):
            antigos.append(RegistroSintoma.objects.create(
                empresa=self.empresa,
                febre=True,
                dor_corpo=True,
                latitude=-23.5505,
                longitude=-46.6333,
                estado="SP",
                cidade="Sao Paulo",
                bairro="Centro",
                confianca=0.82,
                suspeito=False,
            ))
        RegistroSintoma.objects.filter(
            id__in=[registro.id for registro in antigos]
        ).update(data_registro=timezone.now() - timedelta(hours=30))
        self._reset_panorama_cache()

    def _autenticar(self):
        payload = {
            "empresa_id": self.empresa.id,
            "principal_kind": "empresa",
            "principal_id": self.empresa.id,
            "session_key": "sessao-command-ai",
            "exp": timezone.now() + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
        self.client.cookies["auth_token"] = token

    def test_motor_read_only_gera_recomendacao_setorial(self):
        payload = build_command_ai_payload(self.empresa)
        recomendacao = payload["recommendations"][0]

        self.assertEqual(payload["mode"], "read_only_decision_layer")
        self.assertEqual(payload["summary"]["setor"], "hospital")
        self.assertIn("Sala de Decisão IA", payload["summary"]["title"])
        self.assertGreaterEqual(len(payload["recommendations"]), 1)
        self.assertIn("recommended_action", recomendacao)
        self.assertIn("Triagem", " ".join(bloco["title"] for bloco in recomendacao["sector_playbook"]))
        self.assertIn("Não altera mapa", " ".join(payload["safeguards"]))

    def test_farmacia_recebe_direcao_de_abastecimento_e_laboratorio(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Premium",
            email="farmacia@example.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
        )

        payload = build_command_ai_payload(farmacia)
        recomendacao = payload["recommendations"][0]
        metricas = " ".join(item["label"] for item in recomendacao["sector_metrics"])
        playbook = " ".join(bloco["title"] for bloco in recomendacao["sector_playbook"])

        self.assertEqual(payload["summary"]["setor"], "farmacia")
        self.assertIn("Farmácias e Laboratórios", payload["summary"]["title"])
        self.assertIn("Pressão de estoque", metricas)
        self.assertIn("Janela de reposição", metricas)
        self.assertIn("Abastecimento", playbook)
        self.assertIn("Laboratórios", playbook)
        self.assertGreaterEqual(len(recomendacao["priority_items"]), 1)

    def test_api_command_ai_exige_autenticacao(self):
        response = self.client.get("/api/command-ai")

        self.assertEqual(response.status_code, 401)

    def test_api_command_ai_aceita_apenas_get(self):
        self._autenticar()

        response = self.client.post("/api/command-ai")

        self.assertEqual(response.status_code, 405)

    def test_api_command_ai_autenticada_entrega_payload(self):
        self._autenticar()

        response = self.client.get("/api/command-ai")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["setor"], "hospital")
        self.assertEqual(data["feature_status"], "premium_preview")

    def test_feedback_registra_auditoria_institucional(self):
        self._autenticar()

        response = self.client.post(
            "/api/command-ai/feedback",
            data=json.dumps({"insight_id": "hospital:bairro-1", "feedback": "util"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        auditoria = AuditoriaInstitucional.objects.get(acao="command_ai_feedback")
        self.assertEqual(auditoria.empresa, self.empresa)
        self.assertEqual(auditoria.detalhes["feedback"], "util")

    def test_tela_command_ai_renderiza_com_logout_do_portal(self):
        self._autenticar()

        response = self.client.get("/sala-decisao-ia/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SolusCRT Sala de Decisão IA")
        self.assertContains(response, "Ambiente Hospital")
        self.assertContains(response, 'href="/logout/"')

    def test_tela_command_ai_empresa_ganha_contexto_corporativo(self):
        empresa = Empresa.objects.create(
            nome="Empresa Premium",
            email="empresa-command@example.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="empresa_profissional_25",
            sessao_ativa_chave="sessao-command-ai-empresa",
        )

        payload = {
            "empresa_id": empresa.id,
            "principal_kind": "empresa",
            "principal_id": empresa.id,
            "session_key": "sessao-command-ai-empresa",
            "exp": timezone.now() + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
        self.client.cookies["auth_token"] = token

        response = self.client.get("/sala-decisao-ia/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sala de Decisão Saúde Corporativa")
        self.assertContains(response, "Voltar ao centro corporativo")
