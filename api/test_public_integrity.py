from io import StringIO

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.test import Client, TestCase

from api.models import AlertaGovernamental, DispositivoAutorizado, Empresa, RegistroSintoma
from api.views import _empresa_app_publico


class PublicIntegrityTests(TestCase):
    def setUp(self):
        self.client = Client()
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

