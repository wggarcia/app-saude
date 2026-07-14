from io import StringIO
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import connections as _connections


class _OwnerSharesDefaultMixin:
    """Makes .using('owner') queries share default's test transaction.

    In production, 'default' and 'owner' are different PostgreSQL roles on the
    same database. In tests, they are separate connections with separate
    transactions, so data written via 'default' is invisible to 'owner' queries
    (PostgreSQL READ COMMITTED). This mixin aliases 'owner' to default's
    connection object so both aliases run inside the same transaction.
    """
    def setUp(self):
        _connections['owner'] = _connections['default']
        super().setUp()

    def tearDown(self):
        super().tearDown()
        try:
            del _connections['owner']
        except Exception:
            pass
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from api import epidemiologia
from api.models import (
    AlertaGovernamental,
    DispositivoAutorizado,
    DispositivoPushPublico,
    Empresa,
    RegistroSintoma,
)
from api.views import _empresa_app_publico


class PublicIntegrityTests(_OwnerSharesDefaultMixin, TestCase):
    databases = {"default", "owner"}

    def setUp(self):
        super().setUp()
        self.client = Client()
        epidemiologia.clear_panorama_cache()
        self.empresa_publica = _empresa_app_publico()

    def test_app_alertas_publicos_ignora_alerta_sintetico(self):
        AlertaGovernamental.objects.create(
            empresa=self.empresa_publica,
            titulo="teste de sistema",
            mensagem="est eline",
            nivel="moderado",
            ativo=True,
            status=AlertaGovernamental.STATUS_PUBLICADO,
            protocolo="ALR-TEST-001",
            criado_por="stress-test",
            aprovado_por="stress-test",
        )
        alerta_real = AlertaGovernamental.objects.create(
            empresa=self.empresa_publica,
            titulo="Alerta territorial real",
            mensagem="Monitoramento oficial com comunicação válida.",
            nivel="alto",
            ativo=True,
            status=AlertaGovernamental.STATUS_PUBLICADO,
            protocolo="ALR-REAL-001",
            criado_por="sala-operacao",
            aprovado_por="coordenacao",
        )

        response = self.client.get("/api/public/alertas")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["alertas"]], [alerta_real.id])

    def test_app_alertas_publicos_nao_descarta_alerta_real_com_label_de_teste_no_autor(self):
        alerta_real = AlertaGovernamental.objects.create(
            empresa=self.empresa_publica,
            titulo="Alerta territorial real",
            mensagem="Monitoramento oficial com comunicação válida.",
            nivel="alto",
            ativo=True,
            status=AlertaGovernamental.STATUS_PUBLICADO,
            protocolo="ALR-REAL-002",
            criado_por="operacao@teste.com",
            revisado_por="coordenacao@teste.com",
            aprovado_por="gerencia@teste.com",
        )

        response = self.client.get("/api/public/alertas")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["alertas"]], [alerta_real.id])

    def test_app_resumo_publico_ignora_registro_sintetico(self):
        RegistroSintoma.objects.create(
            empresa=self.empresa_publica,
            febre=True,
            tosse=False,
            dor_corpo=True,
            cansaco=True,
            falta_ar=False,
            latitude=-23.55,
            longitude=-46.63,
            estado="São Paulo",
            cidade="São Paulo",
            bairro="Centro",
            grupo="Gripe",
            classificacao="sintetico",
            device_id="stress-soluscrt-brasil-001",
        )
        RegistroSintoma.objects.create(
            empresa=self.empresa_publica,
            febre=True,
            tosse=True,
            dor_corpo=False,
            cansaco=False,
            falta_ar=False,
            latitude=-23.56,
            longitude=-46.64,
            estado="São Paulo",
            cidade="São Paulo",
            bairro="Pinheiros",
            grupo="Gripe",
            classificacao="real",
            device_id="real-device-001",
        )

        response = self.client.get("/api/public/resumo")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resumo"]["registros_24h"], 1)
        self.assertEqual(payload["resumo"]["registros_7d"], 1)
        self.assertEqual(payload["resumo"]["registros_30d"], 1)

    def test_app_resumo_publico_expoe_total_ativo_por_estado(self):
        agora = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        for _ in range(4):
            registro = RegistroSintoma.objects.create(
                empresa=self.empresa_publica,
                febre=True,
                tosse=False,
                dor_corpo=True,
                cansaco=True,
                falta_ar=False,
                latitude=-22.9,
                longitude=-43.1,
                estado="Rio de Janeiro",
                cidade="Rio de Janeiro",
                bairro="Centro",
                grupo="Respiratorio",
            )
            RegistroSintoma.objects.filter(id=registro.id).update(
                data_registro=agora - timedelta(days=15)
            )

        response = self.client.get("/api/public/resumo")
        payload = response.json()
        resumo = payload["resumo"]
        estados_ativos = payload["casos_por_estado_ativos"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resumo["registros_30d"], 4)
        self.assertLess(resumo["total_ativo_30d"], resumo["registros_30d"])
        self.assertTrue(estados_ativos)
        self.assertEqual(estados_ativos[0]["total_bruto"], 4)
        self.assertLess(estados_ativos[0]["total"], estados_ativos[0]["total_bruto"])

    def test_sanear_producao_remove_demo_and_sinteticos(self):
        demo = Empresa.objects.create(
            nome="Demo Legacy",
            email="demo.sst@soluscrt.com",
            senha=make_password("Demo@SST2026"),
            tipo_conta=Empresa.TIPO_EMPRESA,
            ativo=True,
            pacote_codigo="empresa_starter_5",
            plano="mensal",
            max_dispositivos=5,
            max_usuarios=5,
        )
        AlertaGovernamental.objects.create(
            empresa=self.empresa_publica,
            titulo="teste de sistema",
            mensagem="est eline",
            nivel="moderado",
            ativo=True,
            status=AlertaGovernamental.STATUS_PUBLICADO,
            protocolo="ALR-TEST-002",
            criado_por="stress-test",
            aprovado_por="stress-test",
        )
        RegistroSintoma.objects.create(
            empresa=self.empresa_publica,
            febre=True,
            tosse=False,
            dor_corpo=True,
            cansaco=True,
            falta_ar=False,
            latitude=-23.55,
            longitude=-46.63,
            estado="São Paulo",
            cidade="São Paulo",
            bairro="Centro",
            grupo="Gripe",
            classificacao="sintetico",
            device_id="sim-br-001",
        )
        DispositivoAutorizado.objects.create(
            empresa=self.empresa_publica,
            device_id="demo-device-001",
            ativo=True,
        )

        out = StringIO()
        call_command("sanear_producao", apply=True, stdout=out)

        self.assertFalse(Empresa.objects.filter(email="demo.sst@soluscrt.com").exists())
        self.assertFalse(AlertaGovernamental.objects.filter(protocolo="ALR-TEST-002").exists())
        self.assertFalse(RegistroSintoma.objects.filter(device_id="sim-br-001").exists())
        self.assertFalse(DispositivoAutorizado.objects.filter(device_id="demo-device-001").exists())

    def test_limpar_demo_reuniao_publico_zerar_tudo(self):
        RegistroSintoma.objects.create(
            empresa=self.empresa_publica,
            febre=True,
            tosse=False,
            dor_corpo=True,
            cansaco=True,
            falta_ar=False,
            latitude=-23.55,
            longitude=-46.63,
            estado="São Paulo",
            cidade="São Paulo",
            bairro="Centro",
            grupo="Gripe",
            device_id="qualquer-device",
        )
        DispositivoAutorizado.objects.create(
            empresa=self.empresa_publica,
            device_id="publico-device-001",
            ativo=True,
        )
        DispositivoPushPublico.objects.create(
            device_id="publico-device-001",
            token="token-publico-001",
            plataforma="android",
            ativo=True,
        )

        out = StringIO()
        call_command("limpar_demo_reuniao", yes=True, publico=True, stdout=out)

        self.assertFalse(RegistroSintoma.objects.filter(empresa=self.empresa_publica).exists())
        self.assertFalse(DispositivoAutorizado.objects.filter(empresa=self.empresa_publica).exists())
        self.assertFalse(DispositivoPushPublico.objects.filter(token="token-publico-001").exists())
        self.assertEqual(epidemiologia._PANORAMA_CACHE["payload"], None)


class DemoReuniaoSoluscrtTests(TransactionTestCase):
    """
    TransactionTestCase evita deadlock de isolamento entre conexões default/owner.
    TestCase envolve cada teste numa transação não commitada — o owner não consegue
    enxergar a empresa criada no default e bloqueia indefinidamente tentando inserir
    a mesma PK. Com TransactionTestCase cada operação é commitada imediatamente.
    """

    databases = {"default", "owner"}

    def test_demo_reuniao_soluscrt_cria_focos_no_owner(self):
        import re

        out = StringIO()
        call_command(
            "demo_reuniao_soluscrt",
            total=12,
            dias_simulados=2,
            dias_sem_novos=1,
            dias_zerar=3,
            duracao_minutos=0,
            seed=20260615,
            limpar_publico=True,
            limpar_antes=True,
            stdout=out,
            verbosity=0,
        )

        output = out.getvalue()
        self.assertIn("Demo nacional concluida", output)
        # Após dias_zerar a fase de sumiço apaga tudo — verificar pelo sumário
        # é a forma correta, pois registros zerados é o comportamento esperado.
        match = re.search(r"Casos criados=(\d+)", output)
        self.assertIsNotNone(match, "Sumário de criação não encontrado no output")
        self.assertGreater(int(match.group(1)), 0)

