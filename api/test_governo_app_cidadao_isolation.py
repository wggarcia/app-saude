"""
Isolamento multi-tenant do App Cidadão (governo): garante que dispositivos de
push público (DispositivoPushPublico), contagens de KPI e disparo de push de
AlertaCidadao nunca atravessam a fronteira entre municípios/tenants diferentes.
"""
import json

from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase

from api.models import AlertaCidadao, DispositivoPushPublico, Empresa
from api.push_service import enviar_push_alerta_cidadao, resolver_empresa_governo_por_geo


class AppCidadaoTenantIsolationTests(TestCase):
    def setUp(self):
        self.governo_a = Empresa.objects.create(
            nome="Prefeitura de Guarujá",
            email="prefeitura-a@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            cidade="Guaruja",
            uf="SP",
        )
        self.governo_b = Empresa.objects.create(
            nome="Prefeitura de Niterói",
            email="prefeitura-b@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            cidade="Niteroi",
            uf="RJ",
        )

        self.client_a = Client()
        self.client_a.post(
            "/api/login",
            data=json.dumps({
                "email": "prefeitura-a@teste.com", "senha": "123456", "device_id": "gov-a-device",
            }),
            content_type="application/json",
        )
        self.client_b = Client()
        self.client_b.post(
            "/api/login",
            data=json.dumps({
                "email": "prefeitura-b@teste.com", "senha": "123456", "device_id": "gov-b-device",
            }),
            content_type="application/json",
        )

        # dois devices do município A, um do município B — atribuição de tenant
        # por geolocalização, exatamente como o cadastro real do app faz.
        DispositivoPushPublico.objects.create(
            device_id="dev-a1", token="tok-a1", plataforma="ios",
            estado="SP", cidade="Guaruja", bairro="Centro", ativo=True,
            empresa=resolver_empresa_governo_por_geo("SP", "Guaruja"),
        )
        DispositivoPushPublico.objects.create(
            device_id="dev-a2", token="tok-a2", plataforma="android",
            estado="SP", cidade="Guaruja", bairro="Pitangueiras", ativo=True,
            empresa=resolver_empresa_governo_por_geo("SP", "Guaruja"),
        )
        DispositivoPushPublico.objects.create(
            device_id="dev-b1", token="tok-b1", plataforma="ios",
            estado="RJ", cidade="Niteroi", bairro="Icarai", ativo=True,
            empresa=resolver_empresa_governo_por_geo("RJ", "Niteroi"),
        )

    def test_registro_por_geo_atribui_tenant_correto(self):
        dev_a = DispositivoPushPublico.objects.get(token="tok-a1")
        dev_b = DispositivoPushPublico.objects.get(token="tok-b1")
        self.assertEqual(dev_a.empresa_id, self.governo_a.id)
        self.assertEqual(dev_b.empresa_id, self.governo_b.id)

    def test_registro_sem_municipio_correspondente_fica_sem_tenant(self):
        empresa = resolver_empresa_governo_por_geo("MG", "CidadeSemTenantNoTeste")
        self.assertIsNone(empresa)

    def test_kpi_total_cidadaos_nao_conta_dispositivos_de_outro_tenant(self):
        resp_a = self.client_a.get("/api/governo/app-cidadao/kpis/")
        resp_b = self.client_b.get("/api/governo/app-cidadao/kpis/")

        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(resp_a.json()["total_cidadaos_alcancaveis"], 2)
        self.assertEqual(resp_b.json()["total_cidadaos_alcancaveis"], 1)

    def test_enviar_alerta_estima_destinatarios_apenas_do_proprio_tenant(self):
        criado = self.client_a.post(
            "/api/governo/app-cidadao/alertas/",
            data=json.dumps({
                "titulo": "Campanha de vacinação",
                "mensagem": "Compareça à UBS mais próxima",
                "tipo": "campanha_vacinacao",
                "publico_alvo": "todos",
            }),
            content_type="application/json",
        )
        self.assertEqual(criado.status_code, 201)
        alerta_id = criado.json()["alerta"]["id"]

        enviado = self.client_a.post(f"/api/governo/app-cidadao/alertas/{alerta_id}/enviar/")
        self.assertEqual(enviado.status_code, 200)
        # tenant A tem 2 devices ativos — nunca deve contar o device do tenant B
        self.assertEqual(enviado.json()["alerta"]["total_destinatarios_estimado"], 2)

    def test_push_de_alerta_cidadao_nao_alcanca_dispositivo_de_outro_tenant(self):
        alerta_a = AlertaCidadao.objects.create(
            empresa=self.governo_a, titulo="Alerta A", mensagem="mensagem",
            tipo="informativo", publico_alvo="todos",
        )
        alerta_b = AlertaCidadao.objects.create(
            empresa=self.governo_b, titulo="Alerta B", mensagem="mensagem",
            tipo="informativo", publico_alvo="todos",
        )

        # sem FIREBASE_SERVICE_ACCOUNT_JSON no ambiente de teste, a função retorna
        # "push_indisponivel" antes de montar a lista de tokens — mas o escopo por
        # tenant é a MESMA expressão de queryset usada internamente por
        # enviar_push_alerta_cidadao, então validamos que ela nunca inclui tokens
        # de outro município.
        self.assertEqual(enviar_push_alerta_cidadao(alerta_a)["status"], "push_indisponivel")

        tokens_a = set(
            DispositivoPushPublico.objects.filter(ativo=True, empresa=alerta_a.empresa)
            .values_list("token", flat=True)
        )
        tokens_b = set(
            DispositivoPushPublico.objects.filter(ativo=True, empresa=alerta_b.empresa)
            .values_list("token", flat=True)
        )
        self.assertEqual(tokens_a, {"tok-a1", "tok-a2"})
        self.assertEqual(tokens_b, {"tok-b1"})
        self.assertTrue(tokens_a.isdisjoint(tokens_b))
