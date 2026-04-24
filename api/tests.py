import json
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.template.loader import render_to_string
from django.utils import timezone

from .models import AceiteLegalPublico, AlertaGovernamental, DispositivoAutorizado, DispositivoPushPublico, DonoSaaS, Empresa, RegistroSintoma
from .epidemiologia import DISEASE_WEIGHTS
from .planos import PACOTES_SAAS, detalhes_pacote, normalizar_codigo_pacote, pacotes_por_setor
from .push_service import _tokens_para_alerta
from .views import _indice_temporal_publico


class PlanosSaasTests(TestCase):
    def test_catalogo_empresarial_chega_a_mil_maquinas(self):
        pacotes_empresa = pacotes_por_setor(incluir_governo=False)

        self.assertIn("empresa_nacional_1000", pacotes_empresa)
        self.assertEqual(pacotes_empresa["empresa_nacional_1000"]["dispositivos"], 1000)
        self.assertEqual(max(pacote["dispositivos"] for pacote in pacotes_empresa.values()), 1000)

    def test_governo_continua_anual_e_separado(self):
        pacote = PACOTES_SAAS["governo_estado"]

        self.assertEqual(pacote["ciclos"], ["anual"])
        self.assertEqual(pacote["dispositivos"], 1000)
        self.assertNotIn("governo_estado", pacotes_por_setor(incluir_governo=False))

    def test_codigos_legados_nao_viram_governo_por_engano(self):
        self.assertEqual(normalizar_codigo_pacote("grid_500"), "empresa_nacional_500")
        self.assertEqual(normalizar_codigo_pacote("national_1000"), "empresa_nacional_1000")
        self.assertEqual(detalhes_pacote("national_1000")["dispositivos"], 1000)

    def test_template_pagamento_entrega_valores_js_sem_virgula(self):
        html = render_to_string("pagamento.html", {"pacotes": pacotes_por_setor(incluir_governo=False)})

        self.assertIn('value="farmacia_rede_regional"', html)
        self.assertIn('data-anual="60000.000000"', html)
        self.assertNotIn('data-anual="60000,000000"', html)


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

    def test_contrato_governo_abre_sem_cair_no_login_empresa(self):
        response = self.client.get("/contrato-governo/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contrato anual fechado para governo")

    def test_logout_governo_retorna_para_login_governo(self):
        governo = Empresa.objects.create(
            nome="Governo Teste",
            email="governo-logout@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
        )
        login = self.client.post(
            "/api/login-governo",
            data=json.dumps({
                "email": governo.email,
                "senha": "123456",
                "device_id": "gov-logout",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.get("/logout-governo/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login-governo/")

    def test_logout_governo_libera_dispositivo_autorizado(self):
        governo = Empresa.objects.create(
            nome="Governo Dispositivo",
            email="governo-dispositivo@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
        )
        login = self.client.post(
            "/api/login-governo",
            data=json.dumps({
                "email": governo.email,
                "senha": "123456",
                "device_id": "gov-device-a",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertTrue(
            DispositivoAutorizado.objects.filter(
                empresa=governo,
                device_id="gov-device-a",
                ativo=True,
            ).exists()
        )

        response = self.client.get("/logout-governo/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            DispositivoAutorizado.objects.filter(
                empresa=governo,
                device_id="gov-device-a",
                ativo=True,
            ).exists()
        )

    def test_logout_libera_dispositivo_autorizado_da_empresa(self):
        login = self._login("device-a")

        self.assertEqual(login.status_code, 200)
        self.assertTrue(
            DispositivoAutorizado.objects.filter(
                empresa=self.empresa,
                device_id="device-a",
                ativo=True,
            ).exists()
        )

        response = self.client.get("/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            DispositivoAutorizado.objects.filter(
                empresa=self.empresa,
                device_id="device-a",
                ativo=True,
            ).exists()
        )

    def test_login_recicla_dispositivo_ocioso_antes_de_bloquear(self):
        login = self._login("device-a")

        self.assertEqual(login.status_code, 200)
        DispositivoAutorizado.objects.filter(
            empresa=self.empresa,
            device_id="device-a",
        ).update(ultimo_acesso=timezone.now() - timedelta(days=1))
        Empresa.objects.filter(id=self.empresa.id).update(
            sessao_ativa_em=timezone.now() - timedelta(days=1)
        )

        novo_login = self._login("device-b")

        self.assertEqual(novo_login.status_code, 200)
        self.assertTrue(
            DispositivoAutorizado.objects.filter(
                empresa=self.empresa,
                device_id="device-b",
                ativo=True,
            ).exists()
        )

    def test_dispositivo_revogado_bloqueia_reuso_do_cookie(self):
        login = self._login("device-a")

        self.assertEqual(login.status_code, 200)
        DispositivoAutorizado.objects.filter(
            empresa=self.empresa,
            device_id="device-a",
        ).update(ativo=False)

        response = self.client.get("/api/dispositivos")

        self.assertEqual(response.status_code, 401)

    def test_requisicao_autenticada_renova_atividade_de_sessao_e_dispositivo(self):
        login = self._login("device-a")

        self.assertEqual(login.status_code, 200)
        momento_antigo = timezone.now() - timedelta(minutes=10)
        Empresa.objects.filter(id=self.empresa.id).update(sessao_ativa_em=momento_antigo)
        DispositivoAutorizado.objects.filter(
            empresa=self.empresa,
            device_id="device-a",
        ).update(ultimo_acesso=momento_antigo)

        response = self.client.get("/api/dispositivos")

        self.assertEqual(response.status_code, 200)
        self.empresa.refresh_from_db()
        dispositivo = DispositivoAutorizado.objects.get(empresa=self.empresa, device_id="device-a")
        self.assertGreater(self.empresa.sessao_ativa_em, momento_antigo)
        self.assertGreater(dispositivo.ultimo_acesso, momento_antigo)

    def test_login_operacao_permite_console_operacional(self):
        DonoSaaS.objects.create(
            nome="Operacao SolusCRT",
            email="owner@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )

        login = self.client.post(
            "/api/operacao-central/login",
            data=json.dumps({
                "email": "owner@teste.com",
                "senha": "123456",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)

        response = self.client.get("/console-operacional/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operacao SolusCRT")

    def test_home_publica_abre_site_principal_no_dominio_institucional(self):
        response = Client(HTTP_HOST="soluscrt.com.br").get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "IA epidemiologica para antecipar surtos")
        self.assertNotContains(response, "sistema nervoso")
        self.assertNotContains(response, "empresa.soluscrt.com.br")
        self.assertNotContains(response, "governo.soluscrt.com.br")
        self.assertContains(response, "/apresentacao/")
        self.assertContains(response, "https://play.google.com/store/apps/details?id=com.soluscrt.saude")
        self.assertContains(response, "Valores SolusCRT")

    def test_subdominios_raiz_separam_ambientes(self):
        empresa = Client(HTTP_HOST="empresa.soluscrt.com.br").get("/")
        governo = Client(HTTP_HOST="governo.soluscrt.com.br").get("/")
        admin = Client(HTTP_HOST="admin.soluscrt.com.br").get("/")

        self.assertEqual(empresa.status_code, 200)
        self.assertContains(empresa, "Acesso empresarial")
        self.assertEqual(governo.status_code, 200)
        self.assertContains(governo, "Acesso governamental")
        self.assertEqual(admin.status_code, 302)
        self.assertEqual(admin["Location"], "/operacao-central/")

    def test_documentos_publicos_abrem_sem_autenticacao(self):
        for rota, texto in [
            ("/privacidade/", "Politica de Privacidade"),
            ("/termos/", "Termos de Uso"),
            ("/seguranca-lgpd/", "Seguranca, LGPD e Governanca"),
            ("/metodologia/", "Metodologia Epidemiologica"),
            ("/suporte/", "Suporte e Atendimento"),
        ]:
            response = Client(HTTP_HOST="soluscrt.com.br").get(rota)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, texto)

    def test_apresentacao_comercial_abre_sem_autenticacao(self):
        response = Client(HTTP_HOST="soluscrt.com.br").get("/apresentacao/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saude populacional precisa de radar")
        self.assertContains(response, "Google Play")
        self.assertContains(response, "Valores que fazem a tecnologia merecer confianca")
        self.assertNotContains(response, "Slide 01")
        self.assertNotContains(response, "Slide 09")


class PublicApiTests(TestCase):
    def test_catalogo_epidemiologico_inclui_doencas_prioritarias(self):
        for doenca in [
            "Febre Amarela",
            "Leptospirose",
            "Malaria",
            "Sarampo",
            "Meningite",
        ]:
            self.assertIn(doenca, DISEASE_WEIGHTS)

    def test_resumo_publico_responde_sem_autenticacao(self):
        response = Client().get("/api/public/resumo")

        self.assertEqual(response.status_code, 200)
        self.assertIn("resumo", response.json())

    def test_mapa_publico_responde_sem_autenticacao(self):
        response = Client().get("/api/public/mapa")

        self.assertEqual(response.status_code, 200)
        self.assertIn("hotspots", response.json())

    def test_aceite_legal_publico_registra_auditoria(self):
        response = Client(
            HTTP_X_DEVICE_ID="device-legal",
            HTTP_USER_AGENT="SolusCRT-Test",
            REMOTE_ADDR="127.0.0.1",
        ).post(
            "/api/public/legal-consent",
            data=json.dumps({
                "versao": "2026.04.23",
                "plataforma": "app",
                "termos": True,
                "privacidade": True,
                "saude_localizacao": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        aceite = AceiteLegalPublico.objects.get(device_id="device-legal")
        self.assertEqual(aceite.versao, "2026.04.23")
        self.assertTrue(aceite.metadados["termos"])

    def test_mapa_publico_entrega_doencas_provaveis_por_foco(self):
        empresa = Empresa.objects.create(
            nome="Populacao Teste",
            email="populacao-mapa@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        RegistroSintoma.objects.create(
            empresa=empresa,
            febre=True,
            dor_corpo=True,
            cansaco=True,
            latitude=-23.5505,
            longitude=-46.6333,
            cidade="São Paulo",
            estado="SP",
            bairro="Centro",
            grupo="Arbovirose",
        )

        response = Client().get("/api/public/mapa?cidade=São Paulo&estado=SP")
        hotspot = response.json()["hotspots"][0]

        self.assertEqual(response.status_code, 200)
        self.assertIn("doenca_dominante", hotspot)
        self.assertIn("doencas_provaveis", hotspot)
        self.assertTrue(hotspot["doencas_provaveis"])

    def test_envios_publicos_de_dispositivos_distintos_na_mesma_rede_nao_bloqueiam_primeiro_volume(self):
        payload = {
            "febre": True,
            "tosse": True,
            "latitude": -22.9068,
            "longitude": -43.1729,
            "location_source": "current",
        }

        primeiro = Client(HTTP_X_DEVICE_ID="public-device-a").post(
            "/api/public/registrar",
            data=json.dumps(payload),
            content_type="application/json",
        )
        segundo = Client(HTTP_X_DEVICE_ID="public-device-b").post(
            "/api/public/registrar",
            data=json.dumps({**payload, "dor_corpo": True}),
            content_type="application/json",
        )

        self.assertEqual(primeiro.status_code, 200)
        self.assertEqual(segundo.status_code, 200)
        self.assertEqual(primeiro.json()["status"], "ok")
        self.assertEqual(segundo.json()["status"], "ok")

    def test_envio_publico_rejeita_localizacao_que_nao_e_atual(self):
        payload = {
            "febre": True,
            "latitude": -22.9068,
            "longitude": -43.1729,
            "location_source": "base",
        }

        response = Client(HTTP_X_DEVICE_ID="public-device-gps-old").post(
            "/api/public/registrar",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["codigo"], "gps_atual_obrigatorio")

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

    def test_alerta_publico_local_inclui_comunicado_geral_por_padrao(self):
        governo = Empresa.objects.create(
            nome="Governo Geral",
            email="gov-alerta-geral@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            max_dispositivos=1,
            max_usuarios=1,
        )
        AlertaGovernamental.objects.create(
            empresa=governo,
            titulo="Alerta Brasil",
            mensagem="Mensagem geral para a população",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        response_padrao = Client().get("/api/public/alertas?estado=RJ&cidade=Rio%20de%20Janeiro")
        response_restrita = Client().get("/api/public/alertas?estado=RJ&cidade=Rio%20de%20Janeiro&incluir_gerais=0")

        self.assertEqual(len(response_padrao.json()["alertas"]), 1)
        self.assertEqual(response_restrita.json()["alertas"], [])

    def test_alerta_publico_estadual_lista_alerta_municipal_do_estado(self):
        governo = Empresa.objects.create(
            nome="Governo RJ",
            email="gov-alerta-niteroi@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            max_dispositivos=1,
            max_usuarios=1,
        )
        AlertaGovernamental.objects.create(
            empresa=governo,
            titulo="Alerta Niteroi",
            mensagem="Mensagem para Niteroi",
            estado="RJ",
            cidade="Niterói",
            bairro="Icaraí",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        response_estado = Client().get("/api/public/alertas?estado=RJ")
        response_outra_cidade = Client().get("/api/public/alertas?estado=RJ&cidade=Rio%20de%20Janeiro")

        self.assertEqual(len(response_estado.json()["alertas"]), 1)
        self.assertEqual(response_outra_cidade.json()["alertas"], [])


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

    def test_fluxo_alerta_revogado_pode_ser_excluido(self):
        alerta = AlertaGovernamental.objects.create(
            empresa=self.governo,
            titulo="Alerta revogado",
            mensagem="Comunicado encerrado",
            status=AlertaGovernamental.STATUS_REVOGADO,
            ativo=False,
        )

        response = self.client.post(
            "/api/governo/alertas/fluxo",
            data=json.dumps({"alerta_id": alerta.id, "acao": "excluir"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["alerta_status"], "excluido")
        self.assertFalse(AlertaGovernamental.objects.filter(id=alerta.id).exists())

    def test_fluxo_alerta_publicado_nao_pode_ser_excluido(self):
        alerta = AlertaGovernamental.objects.create(
            empresa=self.governo,
            titulo="Alerta ativo",
            mensagem="Comunicado ainda em vigor",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        response = self.client.post(
            "/api/governo/alertas/fluxo",
            data=json.dumps({"alerta_id": alerta.id, "acao": "excluir"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(AlertaGovernamental.objects.filter(id=alerta.id).exists())

    def test_matriz_decisao_responde_para_governo_autenticado(self):
        response = self.client.get("/api/governanca/matriz-decisao")

        self.assertEqual(response.status_code, 200)
        self.assertIn("indicadores", response.json())

    def test_push_governamental_aceita_fallback_estadual(self):
        DispositivoPushPublico.objects.create(
            device_id="ios-sp",
            token="token-sp-1",
            plataforma="ios",
            estado="SP",
            cidade="",
            bairro="",
            ativo=True,
        )
        alerta = AlertaGovernamental.objects.create(
            empresa=self.governo,
            titulo="Alerta Guaruja",
            mensagem="Comunicado local",
            estado="SP",
            cidade="Guarujá",
            bairro="Pitangueiras",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        tokens, total, estrategia = _tokens_para_alerta(alerta)

        self.assertEqual(total, 1)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(estrategia, "recorte_direto")

    def test_push_governamental_sem_recorte_vira_nacional(self):
        DispositivoPushPublico.objects.create(
            device_id="ios-sp-1",
            token="token-sp-1",
            plataforma="ios",
            estado="SP",
            cidade="Guaruja",
            bairro="Pitangueiras",
            ativo=True,
        )
        DispositivoPushPublico.objects.create(
            device_id="ios-rj-1",
            token="token-rj-1",
            plataforma="ios",
            estado="RJ",
            cidade="Niteroi",
            bairro="Icarai",
            ativo=True,
        )
        alerta = AlertaGovernamental.objects.create(
            empresa=self.governo,
            titulo="Alerta nacional",
            mensagem="Comunicado geral para todo o pais",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        tokens, total, estrategia = _tokens_para_alerta(alerta)

        self.assertEqual(total, 2)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(estrategia, "nacional_total")

    def test_push_governamental_normaliza_acentos(self):
        DispositivoPushPublico.objects.create(
            device_id="ios-guaruja",
            token="token-sp-2",
            plataforma="ios",
            estado="SP",
            cidade="Guaruja",
            bairro="Pitangueiras",
            ativo=True,
        )
        alerta = AlertaGovernamental.objects.create(
            empresa=self.governo,
            titulo="Alerta Guarujá",
            mensagem="Comunicado local",
            estado="São Paulo",
            cidade="Guarujá",
            bairro="Pitangueiras",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        tokens, total, estrategia = _tokens_para_alerta(alerta)

        self.assertEqual(total, 1)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(estrategia, "recorte_direto")

    def test_push_governamental_prioriza_token_mais_recente_por_device(self):
        antigo = DispositivoPushPublico.objects.create(
            device_id="iphone-principal",
            token="token-antigo",
            plataforma="ios",
            estado="SP",
            cidade="Guaruja",
            bairro="Pitangueiras",
            ativo=True,
        )
        novo = DispositivoPushPublico.objects.create(
            device_id="iphone-principal",
            token="token-novo",
            plataforma="ios",
            estado="SP",
            cidade="Guaruja",
            bairro="Pitangueiras",
            ativo=True,
        )
        DispositivoPushPublico.objects.filter(id=antigo.id).update(
            atualizado_em=timezone.now() - timedelta(days=1)
        )
        DispositivoPushPublico.objects.filter(id=novo.id).update(
            atualizado_em=timezone.now()
        )
        alerta = AlertaGovernamental.objects.create(
            empresa=self.governo,
            titulo="Alerta Guaruja",
            mensagem="Comunicado local",
            estado="SP",
            cidade="Guarujá",
            bairro="Pitangueiras",
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )

        tokens, total, estrategia = _tokens_para_alerta(alerta)

        self.assertEqual(total, 1)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].token, "token-novo")
        self.assertEqual(estrategia, "recorte_direto")

    def test_registrar_push_publico_desativa_tokens_antigos_do_mesmo_device(self):
        DispositivoPushPublico.objects.create(
            device_id="iphone-principal",
            token="token-antigo",
            plataforma="ios",
            estado="SP",
            cidade="Guaruja",
            bairro="Pitangueiras",
            ativo=True,
        )

        response = self.client.post(
            "/api/public/push-token",
            data=json.dumps(
                {
                    "device_id": "iphone-principal",
                    "token": "token-novo",
                    "plataforma": "ios",
                    "estado": "SP",
                    "cidade": "Guaruja",
                    "bairro": "Pitangueiras",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DispositivoPushPublico.objects.filter(
                device_id="iphone-principal",
                ativo=True,
            ).count(),
            1,
        )
        self.assertTrue(DispositivoPushPublico.objects.get(token="token-novo").ativo)
        self.assertFalse(DispositivoPushPublico.objects.get(token="token-antigo").ativo)


class TemporalDecayTests(TestCase):
    def test_indice_temporal_preserva_10_dias_e_cai_depois(self):
        empresa = Empresa.objects.create(
            nome="Populacao Teste",
            email="populacao-teste@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        agora = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
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
        self.assertEqual(dez_dias, 3.27)
        self.assertGreater(dez_dias, vinte_dias)
        self.assertEqual(trinta_dias, 0.05)
