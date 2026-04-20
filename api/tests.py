import json
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import AlertaGovernamental, Empresa, RegistroSintoma
from .views import _indice_temporal_publico


class AuthDeviceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa Teste",
            email="empresa@teste.com",
            senha=make_password("123456"),
            ativo=True,
            max_dispositivos=1,
            max_usuarios=1,
        )

    def _login(self, device_id):
        return self.client.post(
            "/api/login",
            data=json.dumps(
                {
                    "email": "empresa@teste.com",
                    "senha": "123456",
                    "device_id": device_id,
                    "device_name": "Teste",
                }
            ),
            content_type="application/json",
        )

    def test_relogin_mesmo_dispositivo_nao_gera_duplicidade(self):
        primeira = self._login("device-a")
        segunda = self._login("device-a")

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(self.empresa.dispositivos.count(), 1)

    def test_bloqueia_dispositivo_acima_do_pacote(self):
        primeira = self._login("device-a")
        segunda = self._login("device-b")

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 403)
        self.assertIn("Limite de dispositivos", segunda.json()["mensagem"])

    def test_portal_empresa_bloqueia_credencial_governo(self):
        Empresa.objects.create(
            nome="Governo Teste",
            email="governo@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
        )

        response = self.client.post(
            "/api/login-empresa",
            data=json.dumps({
                "email": "governo@teste.com",
                "senha": "123456",
                "device_id": "gov-no-company",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_portal_governo_bloqueia_credencial_empresa(self):
        response = self.client.post(
            "/api/login-governo",
            data=json.dumps({
                "email": "empresa@teste.com",
                "senha": "123456",
                "device_id": "company-no-gov",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)


class PublicApiTests(TestCase):
    def test_resumo_publico_responde_sem_autenticacao(self):
        response = Client().get("/api/public/resumo")

        self.assertEqual(response.status_code, 200)
        self.assertIn("resumo", response.json())

    def test_mapa_publico_responde_sem_autenticacao(self):
        response = Client().get("/api/public/mapa")

        self.assertEqual(response.status_code, 200)
        self.assertIn("hotspots", response.json())

    def test_alerta_governamental_so_aparece_quando_publicado(self):
        governo = Empresa.objects.create(
            nome="Governo Teste",
            email="governo@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            max_dispositivos=1,
            max_usuarios=1,
        )
        alerta = AlertaGovernamental.objects.create(
            empresa=governo,
            titulo="Alerta em revisão",
            mensagem="Mensagem ainda não publicada",
            status=AlertaGovernamental.STATUS_EM_REVISAO,
            ativo=False,
        )

        response_revisao = Client().get("/api/public/alertas")
        alerta.status = AlertaGovernamental.STATUS_PUBLICADO
        alerta.ativo = True
        alerta.save(update_fields=["status", "ativo"])
        response_publicado = Client().get("/api/public/alertas")

        self.assertEqual(response_revisao.json()["alertas"], [])
        self.assertEqual(len(response_publicado.json()["alertas"]), 1)

    def test_alerta_publico_casa_uf_e_nome_do_estado(self):
        governo = Empresa.objects.create(
            nome="Governo Teste",
            email="gov-alerta@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            max_dispositivos=1,
            max_usuarios=1,
        )
        AlertaGovernamental.objects.create(
            empresa=governo,
            titulo="Alerta RJ",
            mensagem="Mensagem para Rio de Janeiro",
            estado="RJ",
            cidade="Rio de Janeiro",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        response = Client().get("/api/public/alertas?estado=Rio%20de%20Janeiro&cidade=Rio%20de%20Janeiro")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["alertas"]), 1)


class GovernanceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.governo = Empresa.objects.create(
            nome="Governo Teste",
            email="governo@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            max_dispositivos=1,
            max_usuarios=1,
        )
        self.client.post(
            "/api/login",
            data=json.dumps(
                {
                    "email": "governo@teste.com",
                    "senha": "123456",
                    "device_id": "gov-device",
                }
            ),
            content_type="application/json",
        )

    def test_fluxo_alerta_exige_aprovacao_antes_de_publicar(self):
        criado = self.client.post(
            "/api/governo/alertas/criar",
            data=json.dumps({
                "titulo": "Alerta territorial",
                "mensagem": "Comunicado preventivo",
                "nivel": "alto",
                "justificativa": "Crescimento regional acima do esperado",
            }),
            content_type="application/json",
        )
        alerta_id = criado.json()["alerta_id"]
        publicar_antes = self.client.post(
            "/api/governo/alertas/fluxo",
            data=json.dumps({"alerta_id": alerta_id, "acao": "publicar"}),
            content_type="application/json",
        )
        aprovar = self.client.post(
            "/api/governo/alertas/fluxo",
            data=json.dumps({"alerta_id": alerta_id, "acao": "aprovar"}),
            content_type="application/json",
        )
        publicar = self.client.post(
            "/api/governo/alertas/fluxo",
            data=json.dumps({"alerta_id": alerta_id, "acao": "publicar"}),
            content_type="application/json",
        )

        alerta = AlertaGovernamental.objects.get(id=alerta_id)
        self.assertEqual(criado.status_code, 200)
        self.assertEqual(criado.json()["alerta_status"], AlertaGovernamental.STATUS_EM_REVISAO)
        self.assertEqual(publicar_antes.status_code, 400)
        self.assertEqual(aprovar.status_code, 200)
        self.assertEqual(publicar.status_code, 200)
        self.assertEqual(alerta.status, AlertaGovernamental.STATUS_PUBLICADO)
        self.assertTrue(alerta.ativo)

    def test_matriz_decisao_responde_para_governo_autenticado(self):
        response = self.client.get("/api/governanca/matriz-decisao")

        self.assertEqual(response.status_code, 200)
        self.assertIn("indicadores", response.json())


class TemporalDecayTests(TestCase):
    def test_indice_temporal_preserva_10_dias_e_cai_depois(self):
        empresa = Empresa.objects.create(
            nome="Populacao Teste",
            email="populacao-teste@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        agora = timezone.now()
        for dias in [0, 3, 7, 10, 15]:
            registro = RegistroSintoma.objects.create(
                empresa=empresa,
                febre=True,
                latitude=-22.9,
                longitude=-43.1,
                cidade="Rio de Janeiro",
                estado="Rio de Janeiro",
                bairro="Centro",
                grupo="Respiratório",
            )
            RegistroSintoma.objects.filter(id=registro.id).update(
                data_registro=agora - timedelta(days=dias)
            )

        qs = RegistroSintoma.objects.filter(empresa=empresa)
        atual = _indice_temporal_publico(qs, agora)
        dez_dias = _indice_temporal_publico(qs, agora + timedelta(days=10))
        vinte_dias = _indice_temporal_publico(qs, agora + timedelta(days=20))
        trinta_dias = _indice_temporal_publico(qs, agora + timedelta(days=30))

        self.assertEqual(atual, 4.75)
        self.assertEqual(dez_dias, 3.25)
        self.assertGreater(dez_dias, vinte_dias)
        self.assertEqual(trinta_dias, 0)
