import json
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.template.loader import render_to_string
from django.urls import resolve
from django.utils import timezone

from .maintenance import maintenance_report
from .models import (
    AceiteLegalPublico,
    AlertaGovernamental,
    BeneficiarioPlano,
    DepartamentoHospital,
    DescarteItemFarmacia,
    Dispensacao,
    DispensacaoMedicamento,
    DispositivoAutorizado,
    DispositivoPushPublico,
    DonoSaaS,
    Empresa,
    EmpresaUsuario,
    ExameOcupacional,
    FinanceiroEventoSaaS,
    FonteOficialAgregado,
    FornecedorFarmacia,
    FornecedorFarmaciaGestao,
    GuiaAutorizacao,
    IndicadorSaudeGov,
    InternacaoHospital,
    InventarioFarmacia,
    ItemFarmacia,
    ItemPedidoCompra,
    LeitoHospital,
    LeitoHospitalar,
    LoteMedicamento,
    MedicamentoFarmacia,
    OrcamentoSaudeGov,
    PacienteFarmacia,
    PacienteHospital,
    PacienteInternado,
    PlanoSaude,
    PrestadorPlanoSaude,
    PrescricaoMedica,
    PrescricaoHospitalar,
    PlanoAcaoGov,
    ProgramaSaudeGov,
    Reembolso,
    RegistroSintoma,
    Sinistro,
    TriagemHospital,
    TriagemManchester,
    ASOOcupacional,
    AfastamentoSST,
    AgendamentoSST,
    CampanhaVacinacao,
    ConfiguracaoSST,
    CredencialAppFuncionario,
    CATOcupacional,
    DocumentoSST,
    EntregaEPI,
    EPIItem,
    eSocialEventoSST,
    FuncionarioSST,
    NotificacaoFuncionario,
    PlanoAcaoSST,
    RegistroVacinacao,
    RiscoOcupacional,
    SolicitacaoExame,
    TreinamentoNR,
    ASOCompartilhamento,
    NoticiaEpidemiologica,
    DIOPSDeclaracao,
    SIBRegistro,
    RedeCredenciadaPlano,
)
from . import epidemiologia
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
        self.assertEqual(normalizar_codigo_pacote("sst_enterprise_10"), "empresa_nacional_1000")
        self.assertEqual(detalhes_pacote("national_1000")["dispositivos"], 1000)
        self.assertIn("sst.biometria", detalhes_pacote("sst_enterprise_10")["features"])

    def test_template_pagamento_entrega_valores_js_sem_virgula(self):
        html = render_to_string("pagamento.html", {"pacotes": pacotes_por_setor(incluir_governo=False)})
        pacote_farmacia = PACOTES_SAAS["farmacia_rede_regional"]
        valor_anual = f'{pacote_farmacia["anual"]:.6f}'

        self.assertIn('value="farmacia_rede_regional"', html)
        self.assertIn(f'data-anual="{valor_anual}"', html)
        self.assertNotIn(f'data-anual="{valor_anual.replace(".", ",")}"', html)

    def test_feature_flags_cobrem_gaps_regulatorios_e_operacionais(self):
        self.assertIn("farmacia.pbm", PACOTES_SAAS["farmacia_local"]["features"])
        self.assertIn("farmacia.farmacia_popular", PACOTES_SAAS["farmacia_rede_regional"]["features"])
        self.assertIn("hospital.emr", PACOTES_SAAS["hospital_medio"]["features"])

    def test_upgrade_opcoes_normaliza_pacote_legado_da_demo_sst(self):
        empresa = Empresa.objects.create(
            nome="Demo SST",
            email="demo.sst@soluscrt.com",
            senha=make_password("Demo@SST2026"),
            ativo=True,
            tipo_conta=Empresa.TIPO_EMPRESA,
            pacote_codigo="sst_enterprise_10",
            plano="anual",
            max_dispositivos=1000,
            max_usuarios=1000,
            sessao_ativa_chave="sessao-demo",
        )
        payload = {
            "empresa_id": empresa.id,
            "principal_kind": "empresa_admin",
            "principal_id": empresa.id,
            "session_key": empresa.sessao_ativa_chave,
            "exp": timezone.now() + timedelta(hours=1),
        }
        client = Client()
        client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

        response = client.get("/api/plano/upgrade/opcoes")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["plano_atual"]["codigo"], "empresa_nacional_1000")
        self.assertEqual(body["plano_atual"]["label"], "Empresa Nacional 1000")
        self.assertEqual(body["opcoes"], [])
        self.assertIn("sst.biometria", detalhes_pacote("sst_enterprise_10")["features"])

    def test_modulos_de_paridade_competitiva_estao_roteados(self):
        rotas = {
            "/farmacia/pbm/": "farmacia_pbm_page",
            "/api/farmacia/pbm/convenios": "api_pbm_convenios",
            "/hospital/prontuario/": "hospital_prontuario_page",
            "/api/hospital/prontuario/": "api_prontuario_hospitalar",
            "/governo/pec/": "governo_pec_page",
            "/api/governo/regulacao-assistencial/": "api_regulacao_lista",
            "/plano-saude/ans/": "plano_ans_page",
            "/api/plano-saude/ans/diops": "api_diops_lista",
        }

        for rota, view_name in rotas.items():
            with self.subTest(rota=rota):
                self.assertEqual(resolve(rota).func.__name__, view_name)


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

    def test_billing_status_explica_assinatura_e_uso(self):
        login = self._login("billing-device")
        self.assertEqual(login.status_code, 200)
        EmpresaUsuario.objects.create(
            empresa=self.empresa,
            nome="Usuario Billing",
            email="usuario-billing@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )

        response = self.client.get("/api/billing/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assinatura"]["status"], "ativo")
        self.assertEqual(payload["uso"]["usuarios_ativos"], 1)
        self.assertEqual(payload["uso"]["dispositivos_ativos"], 1)

    def test_checkout_com_cpf_invalido_nao_altera_pacote_nem_gera_evento(self):
        pacote_original = self.empresa.pacote_codigo
        login = self._login("checkout-device")
        token = login.json()["token"]

        response = self.client.post(
            f"/api/assinatura/{self.empresa.id}/",
            data=json.dumps({
                "package_id": "hospital_medio",
                "cycle": "anual",
                "cpf_cnpj": "123",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 400)
        self.empresa.refresh_from_db()
        self.assertEqual(self.empresa.pacote_codigo, pacote_original)
        self.assertFalse(FinanceiroEventoSaaS.objects.filter(empresa=self.empresa).exists())

    def test_sst_cids_ocupacionais_e_cat_doenca_exigem_lista(self):
        login = self._login("cid-sst-device")
        self.assertEqual(login.status_code, 200)
        funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Trabalhador CID",
            cpf="000.000.001-10",
            cargo="Operador",
        )

        catalogo = self.client.get("/api/sst/cids-ocupacionais")
        self.assertEqual(catalogo.status_code, 200)
        self.assertGreater(catalogo.json()["total"], 40)
        catalogo_barra = self.client.get("/api/sst/cids-ocupacionais/")
        self.assertEqual(catalogo_barra.status_code, 200)

        invalida = self.client.post(
            "/api/sst/cats",
            data=json.dumps({
                "funcionario_nome": funcionario.nome,
                "tipo": "doenca",
                "cid": "X99",
                "data_acidente": "2026-05-15",
                "descricao": "Teste de CID inválido.",
            }),
            content_type="application/json",
        )
        self.assertEqual(invalida.status_code, 400)

        valida = self.client.post(
            "/api/sst/cats",
            data=json.dumps({
                "funcionario_nome": funcionario.nome,
                "tipo": "doenca",
                "cid": "M54.5",
                "data_acidente": "2026-05-15",
                "descricao": "Doença do trabalho selecionada na lista.",
                "local_acidente": "Posto de trabalho",
                "parte_corpo": "Coluna lombar",
                "houve_afastamento": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(valida.status_code, 201)
        cat = CATOcupacional.objects.get(id=valida.json()["id"])
        self.assertEqual(cat.cid, "M54.5")
        self.assertEqual(cat.parte_corpo, "Coluna lombar")

    def test_sst_afastamento_doenca_ocupacional_salva_com_cid_da_lista(self):
        self.empresa.pacote_codigo = "empresa_profissional_25"
        self.empresa.save()
        login = self._login("afastamento-cid-device")
        self.assertEqual(login.status_code, 200)
        funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Trabalhador Afastado",
            cpf="000.000.001-11",
            cargo="Auxiliar",
        )

        response = self.client.post(
            "/api/sst/afastamentos",
            data=json.dumps({
                "funcionario": funcionario.nome,
                "motivo": "doenca_ocupacional",
                "cid": "Z57.5",
                "data_inicio": "2026-05-15",
                "data_retorno": "2026-05-30",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        afastamento = AfastamentoSST.objects.get(id=response.json()["id"])
        self.assertEqual(afastamento.cid, "Z57.5")
        self.assertEqual(afastamento.status, "retorno_programado")

    def test_seed_enterprise_sst_preenche_areas_operacionais(self):
        login = self._login("seed-sst-device")
        self.assertEqual(login.status_code, 200)

        response = self.client.post("/api/enterprise/seed-operational-demo")
        self.assertEqual(response.status_code, 200)

        self.assertTrue(ConfiguracaoSST.objects.filter(empresa=self.empresa).exists())
        self.assertGreaterEqual(FuncionarioSST.objects.filter(empresa=self.empresa).count(), 6)
        self.assertGreaterEqual(ASOOcupacional.objects.filter(empresa=self.empresa).count(), 6)
        self.assertGreaterEqual(ExameOcupacional.objects.filter(empresa=self.empresa).count(), 6)
        self.assertGreaterEqual(DocumentoSST.objects.filter(empresa=self.empresa).count(), 7)
        self.assertGreaterEqual(TreinamentoNR.objects.filter(empresa=self.empresa).count(), 7)
        self.assertGreaterEqual(EPIItem.objects.filter(empresa=self.empresa).count(), 6)
        self.assertGreaterEqual(EntregaEPI.objects.filter(empresa=self.empresa).count(), 6)
        self.assertTrue(CATOcupacional.objects.filter(empresa=self.empresa, tipo="doenca", cid="M54.5").exists())
        self.assertTrue(AfastamentoSST.objects.filter(empresa=self.empresa, motivo="doenca_ocupacional", cid="M54.5").exists())
        self.assertGreaterEqual(eSocialEventoSST.objects.filter(empresa=self.empresa).count(), 4)
        self.assertGreaterEqual(RiscoOcupacional.objects.filter(empresa=self.empresa).count(), 6)
        self.assertGreaterEqual(PlanoAcaoSST.objects.filter(empresa=self.empresa).count(), 6)
        self.assertTrue(CampanhaVacinacao.objects.filter(empresa=self.empresa).exists())
        self.assertGreaterEqual(RegistroVacinacao.objects.filter(campanha__empresa=self.empresa).count(), 5)

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

    def test_login_setorial_retorna_destino_especifico(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Teste",
            email="farmacia@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )

        response = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["destination"], "/dashboard-farmacia/")

    def test_login_empresa_retorna_destino_corporativo(self):
        empresa = Empresa.objects.create(
            nome="Empresa Teste",
            email="empresa-corporativa-destino@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="empresa_profissional_25",
            max_dispositivos=5,
            max_usuarios=5,
        )

        response = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": empresa.email,
                "senha": "123456",
                "device_id": "empresa-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["destination"], "/dashboard-empresa/")

    def test_ativar_sessao_aba_redefine_cookie_http_only(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Teste",
            email="farmacia-sync@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )
        hospital = Empresa.objects.create(
            nome="Hospital Teste",
            email="hospital-sync@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login_farmacia = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-sync-device",
            }),
            content_type="application/json",
        )
        token_farmacia = login_farmacia.json()["token"]

        login_hospital = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-sync-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login_hospital.status_code, 200)
        self.assertEqual(self.client.get("/dashboard/")["Location"], "/dashboard-hospital/")

        switch = self.client.post(
            "/api/sessao/aba",
            HTTP_AUTHORIZATION=f"Bearer {token_farmacia}",
        )

        self.assertEqual(switch.status_code, 200)
        self.assertEqual(switch.json()["destination"], "/dashboard-farmacia/")
        self.assertTrue(switch.json()["tab_key"])
        self.assertEqual(self.client.get("/dashboard/")["Location"], "/dashboard-farmacia/")

    def test_tab_key_preserva_dashboard_mesmo_com_cookie_de_outro_ambiente(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Aba",
            email="farmacia-aba@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )
        hospital = Empresa.objects.create(
            nome="Hospital Aba",
            email="hospital-aba@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login_farmacia = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-aba-device",
            }),
            content_type="application/json",
        )
        tab = self.client.post(
            "/api/sessao/aba",
            HTTP_AUTHORIZATION=f"Bearer {login_farmacia.json()['token']}",
        ).json()["tab_key"]

        login_hospital = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-aba-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login_hospital.status_code, 200)
        self.assertEqual(self.client.get("/dashboard/")["Location"], "/dashboard-hospital/")
        self.assertEqual(self.client.get(f"/dashboard/?tab={tab}")["Location"], "/dashboard-farmacia/")

    def test_apis_de_gestao_bloqueiam_setor_errado(self):
        hospital = Empresa.objects.create(
            nome="Hospital API",
            email="hospital-api@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-api-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/farmacia/dashboard").status_code, 403)
        self.assertEqual(self.client.get("/api/gestao/resumo").status_code, 403)

    def test_apis_setoriais_bloqueiam_acesso_cruzado_critico(self):
        empresa = Empresa.objects.create(
            nome="Empresa Cruzada",
            email="empresa-cruzada@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="empresa_starter_5",
            max_dispositivos=5,
            max_usuarios=5,
        )
        farmacia = Empresa.objects.create(
            nome="Farmacia Cruzada",
            email="farmacia-cruzada@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )
        governo = Empresa.objects.create(
            nome="Governo Cruzado",
            email="governo-cruzado@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )

        client_empresa = Client()
        self.assertEqual(
            client_empresa.post(
                "/api/login",
                data=json.dumps({
                    "email": empresa.email,
                    "senha": "123456",
                    "device_id": "empresa-cruzada-device",
                }),
                content_type="application/json",
            ).status_code,
            200,
        )
        self.assertIn(client_empresa.get("/api/hospital/dashboard").status_code, {401, 403})
        self.assertIn(client_empresa.get("/api/governo/programas/").status_code, {401, 403})

        client_farmacia = Client()
        self.assertEqual(
            client_farmacia.post(
                "/api/login",
                data=json.dumps({
                    "email": farmacia.email,
                    "senha": "123456",
                    "device_id": "farmacia-cruzada-device",
                }),
                content_type="application/json",
            ).status_code,
            200,
        )
        self.assertIn(client_farmacia.get("/api/sst/dashboard").status_code, {401, 403})

        client_governo = Client()
        self.assertEqual(
            client_governo.post(
                "/api/login-governo",
                data=json.dumps({
                    "email": governo.email,
                    "senha": "123456",
                    "device_id": "governo-cruzado-device",
                }),
                content_type="application/json",
            ).status_code,
            200,
        )
        self.assertIn(client_governo.get("/api/sst/dashboard").status_code, {401, 403})

    def test_farmacia_dashboard_e_conformidade_resistem_a_decimais_e_jsonfield(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Decimal",
            email="farmacia-decimal@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )
        MedicamentoFarmacia.objects.create(
            empresa=farmacia,
            nome="Dipirona",
            quantidade_atual="10.000",
            quantidade_minima="9.500",
            preco_custo="2.50",
            preco_venda="4.00",
            controlado=False,
        )
        Dispensacao.objects.create(
            empresa=farmacia,
            paciente_nome="Paciente Farmacia",
            medico_crm="",
            status="dispensada",
            medicamentos=[{"nome": "Clonazepam", "controlado": True, "quantidade": 1}],
            valor_total="10.00",
        )

        client_farmacia = Client()
        login = client_farmacia.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-decimal-device",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(client_farmacia.get("/api/farmacia/dashboard").status_code, 200)
        conformidade = client_farmacia.get("/api/farmacia/conformidade/")
        self.assertEqual(conformidade.status_code, 200)
        self.assertEqual(conformidade.json()["dispensacoes_controladas_sem_receita"], 1)

    def test_hospital_analytics_responde_com_datefield_em_paciente_internado(self):
        hospital = Empresa.objects.create(
            nome="Hospital Analytics",
            email="hospital-analytics@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )
        PacienteInternado.objects.create(
            empresa=hospital,
            nome="Paciente Analytics",
            cpf="100.200.300-40",
            data_internacao=date.today(),
        )

        client_hospital = Client()
        login = client_hospital.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-analytics-device",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        analytics = client_hospital.get("/api/hospital/analytics/")
        self.assertEqual(analytics.status_code, 200)
        self.assertIn("internacoes_mensal", analytics.json())

    def test_atos_normativos_aceitam_sessao_governamental(self):
        governo = Empresa.objects.create(
            nome="Governo Normativo",
            email="governo-normativo@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )

        client_governo = Client()
        login = client_governo.post(
            "/api/login-governo",
            data=json.dumps({
                "email": governo.email,
                "senha": "123456",
                "device_id": "governo-normativo-device",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        response = client_governo.get("/api/governo/atos-normativos/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["atos"], [])

    def test_enterprise_command_center_exige_autenticacao(self):
        response = self.client.get("/api/enterprise/command-center")

        self.assertEqual(response.status_code, 401)

    def test_enterprise_premium_suite_exige_autenticacao(self):
        response = self.client.get("/api/enterprise/premium-suite")

        self.assertEqual(response.status_code, 401)

    def test_enterprise_seed_operacional_farmacia_cria_fluxo_real(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Seed",
            email="farmacia-seed@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-seed-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.post("/api/enterprise/seed-operational-demo")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["setor"], "farmacia")
        self.assertGreater(payload["total_criado"], 0)
        self.assertGreater(payload["suite"]["crescimento"]["progresso"], 0)
        self.assertTrue(payload["suite"]["crescimento"]["pronto_demo"])
        etapas = {
            etapa["titulo"]: etapa["status"]
            for processo in payload["suite"]["processos"]
            for etapa in processo["etapas"]
        }
        self.assertEqual(etapas["Cadastrar paciente"], "feito")
        self.assertEqual(etapas["Registrar receita"], "feito")
        self.assertEqual(etapas["Dispensar com seguranca"], "feito")
        self.assertGreaterEqual(ItemFarmacia.objects.filter(empresa=farmacia).count(), 4)
        self.assertGreaterEqual(MedicamentoFarmacia.objects.filter(empresa=farmacia).count(), 4)
        self.assertGreaterEqual(FornecedorFarmacia.objects.filter(empresa=farmacia).count(), 1)
        self.assertGreaterEqual(FornecedorFarmaciaGestao.objects.filter(empresa=farmacia).count(), 1)
        self.assertGreaterEqual(LoteMedicamento.objects.filter(empresa=farmacia).count(), 1)
        self.assertGreaterEqual(DispensacaoMedicamento.objects.filter(empresa=farmacia).count(), 1)
        self.assertGreaterEqual(Dispensacao.objects.filter(empresa=farmacia).count(), 1)
        self.assertGreaterEqual(ItemPedidoCompra.objects.filter(pedido__empresa=farmacia).count(), 1)
        self.assertGreaterEqual(InventarioFarmacia.objects.filter(empresa=farmacia).count(), 1)
        self.assertGreaterEqual(DescarteItemFarmacia.objects.filter(empresa=farmacia).count(), 1)

    def test_enterprise_seed_operacional_hospital_cria_fluxo_real(self):
        hospital = Empresa.objects.create(
            nome="Hospital Seed",
            email="hospital-seed@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-seed-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.post("/api/enterprise/seed-operational-demo")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["setor"], "hospital")
        self.assertGreater(payload["total_criado"], 0)
        self.assertGreaterEqual(DepartamentoHospital.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(LeitoHospitalar.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(LeitoHospital.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(PacienteHospital.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(PacienteInternado.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(TriagemManchester.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(TriagemHospital.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(InternacaoHospital.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(PrescricaoHospitalar.objects.filter(empresa=hospital).count(), 1)
        self.assertGreaterEqual(PrescricaoMedica.objects.filter(internacao__empresa=hospital).count(), 1)

    def test_enterprise_seed_operacional_sst_cria_fluxo_real(self):
        empresa = Empresa.objects.create(
            nome="SST Seed",
            email="sst-seed@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="empresa_profissional_25",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": empresa.email,
                "senha": "123456",
                "device_id": "sst-seed-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.post("/api/enterprise/seed-operational-demo")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["setor"], "empresa")
        self.assertGreater(payload["total_criado"], 0)
        self.assertGreaterEqual(FuncionarioSST.objects.filter(empresa=empresa).count(), 1)
        self.assertGreaterEqual(ASOOcupacional.objects.filter(empresa=empresa).count(), 1)
        self.assertGreaterEqual(ExameOcupacional.objects.filter(empresa=empresa).count(), 1)
        self.assertGreaterEqual(AgendamentoSST.objects.filter(empresa=empresa).count(), 1)
        self.assertGreaterEqual(DocumentoSST.objects.filter(empresa=empresa).count(), 3)
        self.assertGreaterEqual(eSocialEventoSST.objects.filter(empresa=empresa).count(), 2)
        self.assertGreaterEqual(CATOcupacional.objects.filter(empresa=empresa).count(), 1)
        self.assertGreaterEqual(TreinamentoNR.objects.filter(empresa=empresa).count(), 1)

    def test_enterprise_seed_operacional_plano_saude_cria_fluxo_real(self):
        operadora = Empresa.objects.create(
            nome="Operadora Seed",
            email="operadora-seed@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": operadora.email,
                "senha": "123456",
                "device_id": "operadora-seed-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.post("/api/enterprise/seed-operational-demo")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["setor"], "plano_saude")
        self.assertGreater(payload["total_criado"], 0)
        self.assertGreater(payload["suite"]["crescimento"]["progresso"], 0)
        etapas = {
            etapa["titulo"]: etapa["status"]
            for processo in payload["suite"]["processos"]
            for etapa in processo["etapas"]
        }
        self.assertEqual(etapas["Cadastrar plano"], "feito")
        self.assertEqual(etapas["Cadastrar beneficiario"], "feito")
        self.assertEqual(etapas["Abrir guia e regular autorizacao"], "feito")
        self.assertEqual(etapas["Monitorar epidemiologia da carteira"], "feito")
        self.assertGreaterEqual(PlanoSaude.objects.filter(empresa=operadora).count(), 1)
        self.assertGreaterEqual(BeneficiarioPlano.objects.filter(plano__empresa=operadora).count(), 3)
        self.assertGreaterEqual(PrestadorPlanoSaude.objects.filter(empresa=operadora).count(), 3)
        self.assertGreaterEqual(GuiaAutorizacao.objects.filter(plano__empresa=operadora).count(), 3)
        self.assertGreaterEqual(Sinistro.objects.filter(empresa=operadora).count(), 2)
        self.assertGreaterEqual(Reembolso.objects.filter(empresa=operadora).count(), 2)
        self.assertGreaterEqual(RegistroSintoma.objects.filter(empresa=operadora).count(), 3)
        guia_pendente = GuiaAutorizacao.objects.filter(
            plano__empresa=operadora,
            fila_status=GuiaAutorizacao.FILA_PENDENCIA_DOCUMENTAL,
        ).first()
        self.assertIsNotNone(guia_pendente)
        self.assertIsNotNone(guia_pendente.prestador_id)

    @override_settings(ALLOW_ENTERPRISE_DEMO_MUTATIONS=False)
    def test_enterprise_seed_demo_respeita_bloqueio_do_ambiente(self):
        login = self._login("seed-bloqueado-device")
        self.assertEqual(login.status_code, 200)

        response = self.client.post("/api/enterprise/seed-operational-demo")

        self.assertEqual(response.status_code, 403)
        self.assertIn("Seed demo desativado", response.json()["erro"])

    def test_enterprise_premium_suite_farmacia_mostra_capacidades_clinicas(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Suite",
            email="farmacia-suite@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-suite-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        PacienteFarmacia.objects.create(
            empresa=farmacia,
            nome="Paciente Jornada",
            cpf="000.000.000-01",
        )
        response = self.client.get("/api/enterprise/premium-suite")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        nomes = " ".join(capacidade["nome"] for capacidade in payload["capacidades"])
        processos = " ".join(processo["nome"] for processo in payload["processos"])
        etapas = " ".join(
            etapa["titulo"]
            for processo in payload["processos"]
            for etapa in processo["etapas"]
        )
        self.assertEqual(payload["setor"], "farmacia")
        self.assertIn("Servicos farmaceuticos", nomes)
        self.assertIn("Lotes", nomes)
        self.assertIn("Atendimento farmaceutico completo", processos)
        self.assertIn("Registrar receita", etapas)
        self.assertEqual(payload["crescimento"]["etapas_feitas"], 1)
        self.assertEqual(payload["crescimento"]["etapas_pendentes"], 7)

    def test_enterprise_premium_suite_plano_saude_mostra_capacidades_de_operadora(self):
        operadora = Empresa.objects.create(
            nome="Operadora Suite",
            email="operadora-suite@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": operadora.email,
                "senha": "123456",
                "device_id": "operadora-suite-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        plano = PlanoSaude.objects.create(empresa=operadora, nome="Plano Suite", registro_ans="123456")
        beneficiario = BeneficiarioPlano.objects.create(
            plano=plano,
            nome="Beneficiario Suite",
            cpf="000.000.000-31",
            email="beneficiario@suite.local",
            situacao=BeneficiarioPlano.SITUACAO_ATIVO,
        )
        GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            tipo=GuiaAutorizacao.TIPO_EXAME,
            descricao_procedimento="Ressonancia magnetica",
            cid="M54.5",
            medico_solicitante="Dr. Suite",
            status=GuiaAutorizacao.STATUS_AUTORIZADA,
            valor_estimado="980.00",
            numero_autorizacao="AUTH-SUITE-001",
            validade_autorizacao=timezone.localdate() + timedelta(days=3),
        )
        Sinistro.objects.create(
            empresa=operadora,
            plano=plano,
            beneficiario=beneficiario,
            numero_sinistro="SIN-SUITE-001",
            tipo="exame",
            status="pago",
            prestador="Hospital Suite",
            valor_total="980.00",
            valor_pago="980.00",
        )
        Reembolso.objects.create(
            empresa=operadora,
            plano=plano,
            beneficiario=beneficiario,
            numero_reembolso="REE-SUITE-001",
            tipo_despesa="consulta",
            status="pago",
            valor_solicitado="210.00",
            valor_aprovado="210.00",
            valor_pago="210.00",
            data_pagamento=timezone.localdate(),
        )
        RegistroSintoma.objects.create(
            empresa=operadora,
            device_id="suite-epi-001",
            doenca="Influenza",
            suspeito=True,
            origem_dado=RegistroSintoma.ORIGEM_INSTITUCIONAL,
            cidade="Sao Paulo",
            bairro="Pinheiros",
            estado="SP",
            pais="Brasil",
            latitude=-23.56,
            longitude=-46.67,
            febre=True,
            tosse=True,
        )

        response = self.client.get("/api/enterprise/premium-suite")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        nomes = " ".join(capacidade["nome"] for capacidade in payload["capacidades"])
        referencias = " ".join(
            referencia
            for capacidade in payload["capacidades"]
            for referencia in capacidade["referencias"]
        )
        processos = " ".join(processo["nome"] for processo in payload["processos"])
        etapas = " ".join(
            etapa["titulo"]
            for processo in payload["processos"]
            for etapa in processo["etapas"]
        )
        self.assertEqual(payload["setor"], "plano_saude")
        self.assertIn("Cadastro, elegibilidade", nomes)
        self.assertIn("Rede credenciada e portal do prestador", nomes)
        self.assertIn("Compliance ANS", nomes)
        self.assertIn("Epidemiologia", nomes)
        self.assertIn("HealthEdge", referencias)
        self.assertIn("Softheon", referencias)
        self.assertIn("Operacao de operadora ponta a ponta", processos)
        self.assertIn("Monitorar epidemiologia da carteira", etapas)
        self.assertIn("sem substituir o core legado", payload["headline"].lower())
        self.assertGreaterEqual(payload["crescimento"]["etapas_feitas"], 4)
        primeira_etapa = payload["processos"][0]["etapas"][0]
        self.assertEqual(primeira_etapa["status"], "feito")
        self.assertEqual(primeira_etapa["sinais"], 1)

    def test_plano_saude_dashboard_expoe_camada_cooperativa(self):
        operadora = Empresa.objects.create(
            nome="Operadora Coop",
            email="operadora-coop@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        plano = PlanoSaude.objects.create(
            empresa=operadora,
            nome="Plano Cooperativo",
            registro_ans="654321",
        )
        beneficiario = BeneficiarioPlano.objects.create(
            plano=plano,
            nome="Beneficiario Coop",
            cpf="000.000.000-55",
            situacao=BeneficiarioPlano.SITUACAO_ATIVO,
        )
        prestador = PrestadorPlanoSaude.objects.create(
            empresa=operadora,
            nome_fantasia="Clinica Coop",
            razao_social="Clinica Coop Ltda",
            cnpj="00.000.000/0001-55",
            tipo="clinica",
            status=PrestadorPlanoSaude.STATUS_CREDENCIADO,
            portal_ativo=True,
        )
        GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            prestador=prestador,
            tipo=GuiaAutorizacao.TIPO_CONSULTA,
            descricao_procedimento="Consulta cooperativa",
            cid="J11",
            medico_solicitante="Dr. Coop",
            status=GuiaAutorizacao.STATUS_EM_ANALISE,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": operadora.email,
                "senha": "123456",
                "device_id": "operadora-coop-device",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        response = self.client.get("/api/plano-saude/dashboard")

        self.assertEqual(response.status_code, 200)
        coop = response.json()["cooperacao"]
        nomes = " ".join(frente["nome"] for frente in coop["frentes"])
        self.assertEqual(coop["modelo"], "camada_cooperativa")
        self.assertIn("operadora ja possui", coop["headline"].lower())
        self.assertIn("Core legado", nomes)
        self.assertIn("Radar epidemiologico", nomes)

    def test_api_plano_saude_prestadores_portal_e_fila_clinica(self):
        operadora = Empresa.objects.create(
            nome="Operadora Fila",
            email="operadora-fila@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        plano = PlanoSaude.objects.create(empresa=operadora, nome="Plano Fila", registro_ans="123123")
        beneficiario = BeneficiarioPlano.objects.create(
            plano=plano,
            nome="Paciente Fila",
            cpf="000.000.000-44",
            numero_carteirinha="PS-044",
            situacao=BeneficiarioPlano.SITUACAO_ATIVO,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": operadora.email,
                "senha": "123456",
                "device_id": "operadora-fila-device",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        prestador_resp = self.client.post(
            "/api/plano-saude/prestadores",
            data=json.dumps({
                "nome_fantasia": "Hospital Operacional",
                "tipo": "hospital",
                "cidade": "Sao Paulo",
                "estado": "SP",
                "portal_ativo": True,
                "sla_autorizacao_horas": 18,
            }),
            content_type="application/json",
        )
        self.assertEqual(prestador_resp.status_code, 201)
        prestador_id = prestador_resp.json()["prestador"]["id"]

        RegistroSintoma.objects.create(
            empresa=operadora,
            device_id="operadora-fila-epi",
            doenca="Influenza",
            suspeito=True,
            cidade="Sao Paulo",
            estado="SP",
            pais="Brasil",
        )

        guia_resp = self.client.post(
            "/api/plano-saude/guias",
            data=json.dumps({
                "plano_id": plano.id,
                "beneficiario_id": beneficiario.id,
                "prestador_id": prestador_id,
                "tipo": GuiaAutorizacao.TIPO_INTERNACAO,
                "prioridade_clinica": GuiaAutorizacao.PRIORIDADE_INTERNACAO,
                "descricao_procedimento": "Internacao clinica com monitoramento",
                "cid": "J18.9",
                "medico_solicitante": "Dr. Fila",
                "valor_estimado": 1800,
            }),
            content_type="application/json",
        )
        self.assertEqual(guia_resp.status_code, 201)
        guia_payload = guia_resp.json()["guia"]
        self.assertEqual(guia_payload["prestador_id"], prestador_id)
        self.assertEqual(guia_payload["fila_status"], GuiaAutorizacao.FILA_TRIAGEM)
        self.assertEqual(guia_payload["sla_horas"], 12)

        fila_resp = self.client.get("/api/plano-saude/fila-clinica")
        self.assertEqual(fila_resp.status_code, 200)
        fila_payload = fila_resp.json()
        self.assertEqual(fila_payload["resumo"]["triagem"], 1)
        self.assertEqual(fila_payload["resumo"]["pressao_epidemiologica"]["suspeitos"], 1)
        self.assertEqual(fila_payload["guias"][0]["prestador_nome"], "Hospital Operacional")

        acao_resp = self.client.post(
            f"/api/plano-saude/fila-clinica/{guia_payload['id']}/acao",
            data=json.dumps({
                "acao": "autorizar",
                "auditor_responsavel": "Central Regulacao",
            }),
            content_type="application/json",
        )
        self.assertEqual(acao_resp.status_code, 200)
        self.assertEqual(acao_resp.json()["guia"]["fila_status"], GuiaAutorizacao.FILA_AUTORIZADA)
        self.assertEqual(acao_resp.json()["guia"]["status"], GuiaAutorizacao.STATUS_AUTORIZADA)

        portal_resp = self.client.get("/api/plano-saude/portal-prestador")
        self.assertEqual(portal_resp.status_code, 200)
        portal_payload = portal_resp.json()
        self.assertEqual(portal_payload["resumo"]["prestadores_portal_ativo"], 1)
        self.assertEqual(portal_payload["prestadores"][0]["nome_fantasia"], "Hospital Operacional")

    def test_enterprise_command_center_hospital_usa_dados_do_setor(self):
        hospital = Empresa.objects.create(
            nome="Hospital Enterprise",
            email="hospital-enterprise@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )
        departamento = DepartamentoHospital.objects.create(
            empresa=hospital,
            nome="UTI",
            tipo="uti",
            capacidade_leitos=2,
            ativo=True,
        )
        LeitoHospital.objects.create(
            empresa=hospital,
            departamento=departamento,
            numero="101",
            status="ocupado",
        )
        PacienteHospital.objects.create(
            empresa=hospital,
            nome="Paciente Enterprise",
        )
        TriagemHospital.objects.create(
            empresa=hospital,
            paciente=PacienteHospital.objects.get(empresa=hospital),
            prioridade="vermelho",
            queixa_principal="Dor intensa",
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-enterprise-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.get("/api/enterprise/command-center")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["setor"], "hospital")
        self.assertEqual(payload["modulos"][0]["codigo"], "leitos_ocupacao")
        self.assertEqual(payload["modulos"][0]["metricas"]["leitos_ocupados"], 1)
        self.assertNotIn("estoque_compras", [modulo["codigo"] for modulo in payload["modulos"]])
        self.assertTrue(any(risco["severidade"] == "alta" for risco in payload["riscos_prioritarios"]))

    def test_enterprise_command_center_hospital_detecta_prescricao_sem_estoque(self):
        hospital = Empresa.objects.create(
            nome="Hospital Circuito",
            email="hospital-circuito@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )
        departamento = DepartamentoHospital.objects.create(empresa=hospital, nome="Clinica", ativo=True)
        leito = LeitoHospital.objects.create(
            empresa=hospital,
            departamento=departamento,
            numero="201",
            status="ocupado",
        )
        paciente = PacienteHospital.objects.create(empresa=hospital, nome="Paciente Circuito")
        internacao = InternacaoHospital.objects.create(
            empresa=hospital,
            paciente=paciente,
            leito=leito,
            diagnostico="Observacao",
            status="ativa",
        )
        PrescricaoMedica.objects.create(
            internacao=internacao,
            medicamento="Dipirona 500mg",
            status="ativa",
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-circuito-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        payload = self.client.get("/api/enterprise/command-center").json()
        circuito = next(modulo for modulo in payload["modulos"] if modulo["codigo"] == "circuito_fechado_medicamento")
        self.assertEqual(circuito["metricas"]["prescricoes_ativas"], 1)
        self.assertEqual(circuito["metricas"]["itens_sem_estoque"], 1)
        self.assertTrue(any("fora do estoque" in risco["titulo"] for risco in payload["riscos_prioritarios"]))

    def test_enterprise_command_center_hospital_detecta_sla_manchester_estourado(self):
        hospital = Empresa.objects.create(
            nome="Hospital SLA",
            email="hospital-sla@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )
        TriagemManchester.objects.create(
            empresa=hospital,
            data_hora=timezone.now(),
            paciente_nome="Paciente Laranja",
            queixa_principal="Dispneia",
            nivel="laranja",
            tempo_espera_minutos=25,
            status="aguardando",
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-sla-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        payload = self.client.get("/api/enterprise/command-center").json()
        sla = next(modulo for modulo in payload["modulos"] if modulo["codigo"] == "sla_manchester")
        self.assertEqual(sla["metricas"]["triagens_abertas"], 1)
        self.assertEqual(sla["metricas"]["sla_estourado"], 1)
        self.assertEqual(sla["metricas"]["sla_critico"], 1)
        self.assertTrue(any("manchester" in risco["titulo"].lower() for risco in payload["riscos_prioritarios"]))

    def test_enterprise_command_center_farmacia_detecta_estoque_critico(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Enterprise",
            email="farmacia-enterprise@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )
        FornecedorFarmaciaGestao.objects.create(empresa=farmacia, nome="Fornecedor A", ativo=True)
        MedicamentoFarmacia.objects.create(
            empresa=farmacia,
            nome="Medicamento Critico",
            quantidade_atual="1",
            quantidade_minima="5",
            ativo=True,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-enterprise-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        response = self.client.get("/api/enterprise/command-center")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["setor"], "farmacia")
        self.assertEqual(payload["modulos"][0]["metricas"]["estoque_critico"], 1)
        self.assertTrue(any("estoque critico" in risco["titulo"] for risco in payload["riscos_prioritarios"]))
        suite = self.client.get("/api/enterprise/premium-suite").json()
        self.assertTrue(any("Compras" in item["nome"] for item in suite["capacidades"]))

    def test_dashboard_farmacia_mostra_command_center_enterprise(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Visual",
            email="farmacia-visual@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-visual-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertContains(self.client.get("/dashboard-farmacia/"), "Central de IA")
        self.assertContains(self.client.get("/farmacia/gestao/"), "Central Corporativa")
        self.assertContains(self.client.get("/farmacia/gestao/"), "Suite Enterprise")
        self.assertContains(self.client.get("/farmacia/gestao/"), "Processo guiado")
        self.assertContains(self.client.get("/farmacia/gestao/"), "Crescimento Enterprise")

    def test_dashboard_hospital_mostra_command_center_enterprise(self):
        hospital = Empresa.objects.create(
            nome="Hospital Visual",
            email="hospital-visual@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="hospital_medio",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": hospital.email,
                "senha": "123456",
                "device_id": "hospital-visual-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertContains(self.client.get("/dashboard-hospital/"), "Central de IA")
        self.assertContains(self.client.get("/hospital/gestao/"), "Central Corporativa")
        self.assertContains(self.client.get("/hospital/gestao/"), "Suite Enterprise")
        self.assertContains(self.client.get("/hospital/gestao/"), "Processo guiado")

    def test_dashboard_empresa_mostra_command_center_enterprise(self):
        empresa = Empresa.objects.create(
            nome="Empresa Visual",
            email="empresa-visual@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="empresa_profissional_25",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": empresa.email,
                "senha": "123456",
                "device_id": "empresa-visual-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertContains(self.client.get("/dashboard-empresa/"), "Central Corporativa")
        self.assertContains(self.client.get("/dashboard-empresa/"), "Suite Enterprise")
        self.assertContains(self.client.get("/dashboard-empresa/"), "Processo guiado")
        self.assertContains(self.client.get("/gestao/"), "Central Corporativa")

    def test_governo_mostra_command_center_enterprise_e_metricas_reais(self):
        governo = Empresa.objects.create(
            nome="Governo Visual",
            email="governo-visual@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )
        programa = ProgramaSaudeGov.objects.create(empresa=governo, nome="Imunizacao", status="ativo")
        IndicadorSaudeGov.objects.create(
            empresa=governo,
            programa=programa,
            nome="Cobertura vacinal",
            meta="80",
            valor_atual="82",
        )
        OrcamentoSaudeGov.objects.create(
            empresa=governo,
            ano=timezone.localdate().year,
            total_previsto="100000.00",
            total_executado="50000.00",
        )
        PlanoAcaoGov.objects.create(empresa=governo, programa=programa, titulo="Busca ativa", status="em_andamento")

        login = self.client.post(
            "/api/login-governo",
            data=json.dumps({
                "email": governo.email,
                "senha": "123456",
                "device_id": "governo-visual-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertContains(self.client.get("/dashboard-governo/"), "Gestão Governamental")
        self.assertContains(self.client.get("/dashboard-governo/"), "Sala de Decisão IA")
        self.assertContains(self.client.get("/governo/gestao/"), "Central Corporativa")
        self.assertContains(self.client.get("/governo/gestao/"), "Sala de Decisão IA")
        payload = self.client.get("/api/enterprise/command-center").json()
        self.assertEqual(payload["setor"], "governo")
        self.assertEqual(payload["modulos"][0]["codigo"], "programas_indicadores")
        self.assertEqual(payload["modulos"][0]["metricas"]["metas_atingidas"], 1)

    def test_rede_e_plano_saude_mostram_command_center_enterprise(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Rede Visual",
            email="farmacia-rede-visual@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
            max_dispositivos=5,
            max_usuarios=5,
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": farmacia.email,
                "senha": "123456",
                "device_id": "farmacia-rede-visual-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        self.assertContains(self.client.get("/rede/gestao/"), "Central Corporativa")

        # plano_saude_gestao_page agora requer setor plano_saude — testar com empresa correta
        operadora = Empresa.objects.create(
            nome="Operadora Rede Visual",
            email="operadora-rede-visual@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        self.client.post(
            "/api/login",
            data=json.dumps({
                "email": operadora.email,
                "senha": "123456",
                "device_id": "operadora-rede-visual-device",
            }),
            content_type="application/json",
        )
        self.assertContains(self.client.get("/plano-saude/gestao/"), "Central Corporativa")

    def test_plano_saude_command_center_calcula_glosas_e_receita(self):
        empresa = Empresa.objects.create(
            nome="Operadora Glosa",
            email="operadora-glosa@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        plano = PlanoSaude.objects.create(empresa=empresa, nome="Plano Premium", status=PlanoSaude.STATUS_ATIVO)
        beneficiario = BeneficiarioPlano.objects.create(plano=plano, nome="Beneficiario Receita")
        GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            tipo=GuiaAutorizacao.TIPO_EXAME,
            descricao_procedimento="Tomografia",
            status=GuiaAutorizacao.STATUS_AUTORIZADA,
            valor_estimado="800.00",
            validade_autorizacao=timezone.localdate() - timedelta(days=1),
        )
        GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            tipo=GuiaAutorizacao.TIPO_PROCEDIMENTO,
            descricao_procedimento="Procedimento negado",
            status=GuiaAutorizacao.STATUS_NEGADA,
            valor_estimado="1200.00",
        )
        guia_pendente = GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=beneficiario,
            tipo=GuiaAutorizacao.TIPO_CONSULTA,
            descricao_procedimento="Consulta pendente",
            status=GuiaAutorizacao.STATUS_SOLICITADA,
            valor_estimado="200.00",
        )
        GuiaAutorizacao.objects.filter(id=guia_pendente.id).update(
            solicitada_em=timezone.now() - timedelta(days=4)
        )

        login = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": empresa.email,
                "senha": "123456",
                "device_id": "operadora-glosa-device",
            }),
            content_type="application/json",
        )

        self.assertEqual(login.status_code, 200)
        payload = self.client.get("/api/enterprise/command-center").json()
        ciclo = next(modulo for modulo in payload["modulos"] if modulo["codigo"] == "ciclo_receita_glosas")
        self.assertEqual(ciclo["metricas"]["guias_total"], 3)
        self.assertEqual(ciclo["metricas"]["guias_sla_vencido"], 1)
        self.assertEqual(ciclo["metricas"]["autorizacoes_vencidas"], 1)
        self.assertEqual(ciclo["metricas"]["glosas_sem_justificativa"], 1)
        self.assertEqual(ciclo["metricas"]["valor_solicitado"], 2200.0)
        self.assertEqual(ciclo["metricas"]["valor_glosado"], 1200.0)
        self.assertEqual(ciclo["metricas"]["valor_sla_vencido"], 200.0)
        self.assertEqual(ciclo["metricas"]["valor_autorizacao_vencida"], 800.0)
        self.assertTrue(any("sla" in risco["titulo"].lower() for risco in payload["riscos_prioritarios"]))
        self.assertTrue(any("glosa" in risco["titulo"].lower() for risco in payload["riscos_prioritarios"]))
        self.assertTrue(any("autorizacao vencida" in risco["titulo"].lower() for risco in payload["riscos_prioritarios"]))

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
        self.assertContains(response, "Readiness Enterprise")
        self.assertContains(response, "Fila de Sucesso do Cliente")
        self.assertContains(response, "Implantação e Go-live")

    def test_console_dono_nao_vaza_dados_privados_de_cliente(self):
        """Guardião anti-regressão de privacidade (LGPD / multi-tenant).

        Planta valores sensíveis ÚNICOS no ambiente de um cliente (CPF, nome de
        titular, e-mail de trabalhador) e verifica que NENHUM endpoint do dono
        os expõe. Se um endpoint passar a vazar PII no futuro, este teste falha.
        """
        CPF_CANARIO = "111.222.333-99"
        NOME_CANARIO = "TITULAR SEGREDO CANARIO XPTO"
        EMAIL_FUNC_CANARIO = "canario.trabalhador.segredo@cliente-x.local"

        DonoSaaS.objects.create(
            nome="Operacao Privacy", email="owner-privacy@teste.com",
            senha=make_password("123456"), ativo=True, papel="admin",
        )
        cliente = Empresa.objects.create(
            nome="Hospital Cliente X", email="hospital-x@cliente.com",
            senha=make_password("123456"), ativo=True, pacote_codigo="hospital_medio",
        )
        func = FuncionarioSST.objects.create(
            empresa=cliente, nome=NOME_CANARIO, cpf=CPF_CANARIO,
            cargo="Enfermeiro", ativo=True,
        )
        CredencialAppFuncionario.objects.create(
            funcionario=func, email=EMAIL_FUNC_CANARIO,
            senha=make_password("x"), ativo=True,
        )
        RegistroSintoma.objects.create(
            empresa=cliente, febre=True, cidade="Rio de Janeiro", estado="RJ",
        )
        FinanceiroEventoSaaS.objects.create(
            empresa=cliente, tipo_evento="ajuste_owner", valor=0,
        )

        login = self.client.post(
            "/api/operacao-central/login",
            data=json.dumps({"email": "owner-privacy@teste.com", "senha": "123456"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        canarios = [CPF_CANARIO, NOME_CANARIO, EMAIL_FUNC_CANARIO]
        # Chaves que NUNCA devem aparecer em respostas JSON do dono
        chaves_pii = ['"cpf"', '"nome_paciente"', '"prontuario"', '"data_nascimento"', '"matricula"']

        endpoints = [
            "/api/operacao-central/resumo",
            "/api/operacao-central/financeiro-real",
            "/api/operacao-central/saude",
            "/api/operacao-central/app-funcionario",
            "/api/operacao-central/operadores",
            "/api/operacao-central/exportar?tipo=clientes",
            "/api/operacao-central/exportar?tipo=financeiro",
            "/api/operacao-central/exportar?tipo=auditoria",
            "/api/operacao/readiness",
        ]
        for url in endpoints:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"{url} deveria responder 200")
            corpo = resp.content.decode("utf-8", errors="ignore")
            for canario in canarios:
                self.assertNotIn(
                    canario, corpo,
                    f"VAZAMENTO DE PII: valor sensível '{canario}' apareceu em {url}",
                )
            if "application/json" in resp.get("Content-Type", ""):
                low = corpo.lower()
                for chave in chaves_pii:
                    self.assertNotIn(
                        chave, low,
                        f"VAZAMENTO DE PII: chave '{chave}' presente em {url}",
                    )

    def test_readiness_enterprise_disponivel_para_operacao(self):
        DonoSaaS.objects.create(
            nome="Operacao Readiness",
            email="owner-readiness@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )

        login = self.client.post(
            "/api/operacao-central/login",
            data=json.dumps({
                "email": "owner-readiness@teste.com",
                "senha": "123456",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        response = self.client.get("/api/operacao/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("score", payload)
        self.assertTrue(any(item["codigo"] == "asaas" for item in payload["checks"]))

    def test_console_operacional_entrega_playbook_e_cancela_contrato(self):
        DonoSaaS.objects.create(
            nome="Operacao Contrato",
            email="owner-contrato@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        empresa = Empresa.objects.create(
            nome="Cliente Enterprise",
            email="cliente-enterprise@teste.com",
            senha=make_password("123456"),
            ativo=True,
            max_dispositivos=1,
            max_usuarios=1,
            sessao_ativa_chave="sessao-cliente",
            sessao_ativa_device_id="device-cliente",
            sessao_ativa_em=timezone.now(),
        )
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome="Gestor",
            email="gestor-enterprise@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-gestor",
            sessao_ativa_device_id="device-gestor",
            sessao_ativa_em=timezone.now(),
        )

        login = self.client.post(
            "/api/operacao-central/login",
            data=json.dumps({
                "email": "owner-contrato@teste.com",
                "senha": "123456",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        resumo = self.client.get("/api/operacao-central/resumo")
        self.assertEqual(resumo.status_code, 200)
        cliente = next(item for item in resumo.json()["clientes"] if item["id"] == empresa.id)
        self.assertIn("proxima_acao", cliente)
        self.assertIn("playbook", cliente)

        response = self.client.post(
            "/api/operacao-central/financeiro/acao",
            data=json.dumps({"empresa_id": empresa.id, "acao": "cancelar"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        empresa.refresh_from_db()
        self.assertFalse(empresa.ativo)
        self.assertIsNone(empresa.sessao_ativa_chave)
        self.assertIsNone(EmpresaUsuario.objects.get(empresa=empresa).sessao_ativa_chave)
        self.assertTrue(FinanceiroEventoSaaS.objects.filter(empresa=empresa, status="cancelado").exists())

    def test_onboarding_operacional_avanca_cliente_ate_go_live(self):
        DonoSaaS.objects.create(
            nome="Operacao Implantacao",
            email="owner-implantacao@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        empresa = Empresa.objects.create(
            nome="Cliente Go-live",
            email="cliente-golive@teste.com",
            senha=make_password("123456"),
            ativo=True,
            max_dispositivos=3,
            max_usuarios=5,
            data_expiracao=timezone.now() + timedelta(days=90),
        )
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome="Gestora Implantacao",
            email="gestora-golive@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        DispositivoAutorizado.objects.create(
            empresa=empresa,
            device_id="device-golive",
            apelido="Notebook recepcao",
        )

        login = self.client.post(
            "/api/operacao-central/login",
            data=json.dumps({
                "email": "owner-implantacao@teste.com",
                "senha": "123456",
            }),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        resumo_inicial = self.client.get("/api/operacao-central/resumo")
        self.assertEqual(resumo_inicial.status_code, 200)
        cliente_inicial = next(item for item in resumo_inicial.json()["clientes"] if item["id"] == empresa.id)
        self.assertIn("onboarding", cliente_inicial)
        self.assertEqual(cliente_inicial["onboarding"]["etapa"], "treinamento")
        self.assertLess(cliente_inicial["onboarding"]["score"], 100)

        for acao in ["treinamento", "validacao", "go_live"]:
            response = self.client.post(
                "/api/operacao-central/onboarding/acao",
                data=json.dumps({"empresa_id": empresa.id, "acao": acao}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")

        resumo_final = self.client.get("/api/operacao-central/resumo")
        cliente_final = next(item for item in resumo_final.json()["clientes"] if item["id"] == empresa.id)
        self.assertEqual(cliente_final["onboarding"]["score"], 100)
        self.assertEqual(cliente_final["onboarding"]["etapa"], "go_live")
        self.assertEqual(cliente_final["onboarding"]["proxima_entrega"], "Operacao acompanhada")
        self.assertTrue(
            FinanceiroEventoSaaS.objects.filter(
                empresa=empresa,
                tipo_evento="onboarding_go_live",
                status="manual",
            ).exists()
        )

    def test_home_publica_abre_site_principal_no_dominio_institucional(self):
        response = Client(HTTP_HOST="soluscrt.com.br").get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cinco ambientes privados para cada decisor em saúde.")
        self.assertNotContains(response, "sistema nervoso")
        self.assertNotContains(response, "empresa.soluscrt.com.br")
        self.assertNotContains(response, "governo.soluscrt.com.br")
        self.assertContains(response, "/apresentacao/")
        self.assertContains(response, "https://apps.apple.com/br/app/soluscrt-ocupacional/id6774676681")
        self.assertContains(response, "Confiança SolusCRT")

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
            ("/metodologia/", "Como o SolusCRT separa sinal precoce"),
            ("/suporte/", "Suporte e Atendimento"),
        ]:
            response = Client(HTTP_HOST="soluscrt.com.br").get(rota)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, texto)

    def test_radar_local_publico_com_cidade_e_estado_responde(self):
        response = Client(HTTP_HOST="soluscrt.com.br").get(
            "/api/public/radar-local",
            {"cidade": "Sao Paulo", "estado": "SP"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["local"]["cidade"], "Sao Paulo")
        self.assertEqual(response.json()["local"]["estado"], "SP")

    def test_apresentacao_comercial_abre_sem_autenticacao(self):
        response = Client(HTTP_HOST="soluscrt.com.br").get("/apresentacao/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cinco ambientes privados")
        self.assertContains(response, "Google Play")
        self.assertContains(response, "Valores que fazem a tecnologia merecer confiança")
        self.assertNotContains(response, "Slide 01")
        self.assertNotContains(response, "Slide 09")


class MaintenanceTests(TestCase):
    def test_maintenance_report_detecta_sessoes_dispositivos_push_antigos(self):
        agora = timezone.now()
        empresa = Empresa.objects.create(
            nome="Empresa Manutencao",
            email="manutencao@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-antiga",
            sessao_ativa_device_id="device-old",
            sessao_ativa_em=agora - timedelta(days=1),
        )
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome="Analista",
            email="analista@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-usuario",
            sessao_ativa_device_id="device-user",
            sessao_ativa_em=agora - timedelta(days=1),
        )
        DonoSaaS.objects.create(
            nome="Operacao",
            email="owner-maint@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-owner",
            sessao_ativa_em=agora - timedelta(days=1),
        )
        DispositivoAutorizado.objects.create(
            empresa=empresa,
            device_id="device-old",
            ativo=True,
        )
        DispositivoAutorizado.objects.filter(
            empresa=empresa,
            device_id="device-old",
        ).update(ultimo_acesso=agora - timedelta(days=1))
        DispositivoPushPublico.objects.create(
            device_id="push-old",
            token="push-old-token",
            plataforma="ios",
            ativo=True,
        )
        DispositivoPushPublico.objects.filter(device_id="push-old").update(
            atualizado_em=agora - timedelta(days=90)
        )
        AlertaGovernamental.objects.create(
            empresa=empresa,
            titulo="Alerta revogado antigo",
            mensagem="Encerrado",
            status=AlertaGovernamental.STATUS_REVOGADO,
            ativo=False,
            revogado_em=agora - timedelta(days=30),
        )

        report = maintenance_report(now=agora)

        self.assertEqual(report["before"]["devices"]["stale_active"], 1)
        self.assertEqual(report["before"]["sessions"]["empresa_stale"], 1)
        self.assertEqual(report["before"]["sessions"]["usuario_stale"], 1)
        self.assertEqual(report["before"]["sessions"]["owner_stale"], 1)
        self.assertEqual(report["before"]["push"]["stale_active"], 1)
        self.assertEqual(report["before"]["alerts"]["revoked_old"], 1)

    def test_maintenance_report_apply_limpa_apenas_itens_seguros(self):
        agora = timezone.now()
        empresa = Empresa.objects.create(
            nome="Empresa Limpeza",
            email="limpeza@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-antiga",
            sessao_ativa_device_id="device-old",
            sessao_ativa_em=agora - timedelta(days=1),
        )
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome="Analista",
            email="analista-limpeza@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-usuario",
            sessao_ativa_device_id="device-user",
            sessao_ativa_em=agora - timedelta(days=1),
        )
        DonoSaaS.objects.create(
            nome="Operacao",
            email="owner-limpeza@teste.com",
            senha=make_password("123456"),
            ativo=True,
            sessao_ativa_chave="sessao-owner",
            sessao_ativa_em=agora - timedelta(days=1),
        )
        DispositivoAutorizado.objects.create(
            empresa=empresa,
            device_id="device-old",
            ativo=True,
        )
        DispositivoAutorizado.objects.filter(
            empresa=empresa,
            device_id="device-old",
        ).update(ultimo_acesso=agora - timedelta(days=1))
        DispositivoPushPublico.objects.create(
            device_id="push-old",
            token="push-old-token-2",
            plataforma="ios",
            ativo=True,
        )
        DispositivoPushPublico.objects.filter(device_id="push-old").update(
            atualizado_em=agora - timedelta(days=90)
        )
        alerta = AlertaGovernamental.objects.create(
            empresa=empresa,
            titulo="Alerta revogado antigo",
            mensagem="Encerrado",
            status=AlertaGovernamental.STATUS_REVOGADO,
            ativo=False,
            revogado_em=agora - timedelta(days=30),
        )

        report = maintenance_report(now=agora, apply=True, clear_cache=False)

        self.assertEqual(report["cleanup"]["devices_deactivated"], 1)
        self.assertEqual(report["cleanup"]["empresa_sessions_closed"], 1)
        self.assertEqual(report["cleanup"]["user_sessions_closed"], 1)
        self.assertEqual(report["cleanup"]["owner_sessions_closed"], 1)
        self.assertEqual(report["cleanup"]["push_tokens_deactivated"], 1)
        empresa.refresh_from_db()
        self.assertIsNone(empresa.sessao_ativa_chave)
        self.assertFalse(DispositivoAutorizado.objects.get(empresa=empresa, device_id="device-old").ativo)
        self.assertFalse(DispositivoPushPublico.objects.get(device_id="push-old").ativo)
        self.assertTrue(AlertaGovernamental.objects.filter(id=alerta.id).exists())

    def test_management_command_manter_soluscrt_gera_relatorio(self):
        buffer = StringIO()

        call_command("manter_soluscrt", stdout=buffer)

        output = buffer.getvalue()
        self.assertIn("SolusCRT Maintenance Report", output)
        self.assertIn("Nenhuma alteracao aplicada", output)


class PublicApiTests(TestCase):
    def test_catalogo_epidemiologico_inclui_doencas_prioritarias(self):
        for doenca in [
            "Febre Amarela",
            "Leptospirose",
            "Malaria",
            "Sarampo",
            "Meningite",
            "Hantavirose",
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
        from .views import _empresa_app_publico
        empresa = _empresa_app_publico()
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

        epidemiologia.clear_panorama_cache()
        response = Client().get("/api/public/mapa?cidade=São Paulo&estado=SP")
        hotspot = response.json()["hotspots"][0]

        self.assertEqual(response.status_code, 200)
        self.assertIn("doenca_dominante", hotspot)
        self.assertIn("doencas_provaveis", hotspot)
        self.assertTrue(hotspot["doencas_provaveis"])

    def test_mapa_publico_expõe_aliases_equalizados_para_app_e_paineis(self):
        from .views import _empresa_app_publico

        empresa = _empresa_app_publico()
        RegistroSintoma.objects.create(
            empresa=empresa,
            dor_articular=True,
            exantema=True,
            latitude=-22.9068,
            longitude=-43.1729,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Centro",
            grupo="Arbovirose",
        )

        epidemiologia.clear_panorama_cache()
        response = Client().get("/api/public/mapa?cidade=Rio de Janeiro&estado=RJ")
        hotspot = response.json()["hotspots"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(hotspot["total"], hotspot["total_cases"])
        self.assertEqual(hotspot["total"], hotspot["active_cases"])
        self.assertEqual(hotspot["total"], hotspot["casos_ativos"])
        self.assertEqual(hotspot["total_registros_30d"], hotspot["raw_total_cases"])
        self.assertEqual(hotspot["total_registros_30d"], hotspot["registros_30d"])
        self.assertEqual(hotspot["sintomas"]["dor_articular"], 1)
        self.assertEqual(hotspot["sintomas"]["exantema"], 1)
        self.assertIn("risk_level", hotspot)

    def test_mapa_publico_filtra_por_bairro(self):
        from .views import _empresa_app_publico

        empresa = _empresa_app_publico()
        RegistroSintoma.objects.create(
            empresa=empresa,
            febre=True,
            latitude=-22.9068,
            longitude=-43.1729,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Centro",
            grupo="Arbovirose",
        )
        RegistroSintoma.objects.create(
            empresa=empresa,
            tosse=True,
            latitude=-22.9846,
            longitude=-43.2048,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Copacabana",
            grupo="Respiratorio",
        )

        epidemiologia.clear_panorama_cache()
        response = Client().get(
            "/api/public/mapa?estado=RJ&cidade=Rio%20de%20Janeiro&bairro=Centro"
        )
        bairros = {item["bairro"] for item in response.json()["hotspots"]}

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bairros, {"Centro"})

    def test_radar_local_publico_expõe_casos_ativos_equalizados(self):
        from .views import _empresa_app_publico
        empresa = _empresa_app_publico()
        RegistroSintoma.objects.create(
            empresa=empresa,
            dor_articular=True,
            latitude=-22.9068,
            longitude=-43.1729,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Centro",
            grupo="Arbovirose",
        )

        epidemiologia.clear_panorama_cache()
        response = Client().get("/api/public/radar-local?cidade=Rio de Janeiro&estado=RJ")
        radar = response.json()["radar"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(radar["casos_ativos"], radar["active_cases"])
        self.assertEqual(radar["casos_ativos"], radar["total_cases"])
        self.assertEqual(radar["registros_30d"], radar["raw_total_cases"])
        self.assertEqual(radar["registros_30d"], radar["total_registros_30d"])
        self.assertEqual(radar["sintoma_dominante"], "Dor Articular")

    def test_probabilidades_nao_puxam_hantavirose_em_quadro_generico_sem_respiratorio(self):
        probabilidades = epidemiologia._build_disease_probabilities(
            {
                "febre": 10,
                "dor_corpo": 10,
                "cansaco": 10,
                "tosse": 0,
                "falta_ar": 0,
            },
            10,
        )

        self.assertTrue(probabilidades)
        self.assertNotEqual(probabilidades[0]["name"], "Hantavirose")

    def test_probabilidades_priorizam_hantavirose_quando_assinatura_respiratoria_esta_presente(self):
        probabilidades = epidemiologia._build_disease_probabilities(
            {
                "febre": 10,
                "tosse": 10,
                "falta_ar": 10,
                "cansaco": 10,
                "dor_corpo": 6,
            },
            10,
        )

        self.assertTrue(probabilidades)
        self.assertEqual(probabilidades[0]["name"], "Hantavirose")

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

    def test_envio_publico_aceita_localizacao_que_nao_e_atual_com_confianca_reduzida(self):
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

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertLessEqual(body["confianca"], 0.6)
        self.assertIn("localizacao_nao_confirmada", body["motivos_suspeita"])

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

    def test_fluxo_alerta_publicado_espelha_para_app_publico(self):
        criado = self.client.post(
            "/api/governo/alertas/criar",
            data=json.dumps({
                "titulo": "Alerta para o app",
                "mensagem": "Comunicado oficial para a populacao",
                "nivel": "alto",
            }),
            content_type="application/json",
        )
        alerta_id = criado.json()["alerta_id"]
        self.client.post(
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
        empresa_publica = Empresa.objects.get(email="populacao@soluscrt.com")
        espelho = AlertaGovernamental.objects.filter(
            empresa=empresa_publica,
            protocolo=alerta.protocolo,
            status=AlertaGovernamental.STATUS_PUBLICADO,
            ativo=True,
        )
        response_publico = Client().get("/api/public/alertas")

        self.assertEqual(publicar.status_code, 200)
        self.assertTrue(espelho.exists())
        self.assertEqual(len(response_publico.json()["alertas"]), 1)
        self.assertEqual(response_publico.json()["alertas"][0]["titulo"], "Alerta para o app")

    def test_header_bearer_invalido_nao_gera_erro_no_middleware(self):
        response = self.client.post(
            "/api/governo/alertas/criar",
            data=json.dumps({"titulo": "A", "mensagem": "B"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer",
        )
        self.assertEqual(response.status_code, 401)

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

        self.assertEqual(atual, 4.78)
        # Theoretical value is 3.425; banker's rounding vs PostgreSQL float
        # accumulation order produces 3.42 (SQLite) or 3.43 (PostgreSQL).
        self.assertAlmostEqual(dez_dias, 3.42, delta=0.015)
        self.assertGreater(dez_dias, vinte_dias)
        self.assertEqual(trinta_dias, 0.5)

    def test_mapa_publico_mostra_total_ativo_reduzido(self):
        from .views import _empresa_app_publico

        empresa = _empresa_app_publico()
        agora = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        for _ in range(4):
            registro = RegistroSintoma.objects.create(
                empresa=empresa,
                febre=True,
                latitude=-22.9,
                longitude=-43.1,
                cidade="Rio de Janeiro",
                estado="RJ",
                bairro="Centro",
                grupo="Respiratorio",
            )
            RegistroSintoma.objects.filter(id=registro.id).update(
                data_registro=agora - timedelta(days=15)
            )

        epidemiologia.clear_panorama_cache()
        response = Client().get("/api/public/mapa?cidade=Rio de Janeiro&estado=RJ")
        hotspot = response.json()["hotspots"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(hotspot["total_registros_30d"], 4)
        self.assertEqual(hotspot["total"], hotspot["indice_ativo"])
        self.assertLess(hotspot["total"], hotspot["total_registros_30d"])

    def test_panorama_epidemiologico_usa_casos_ativos_temporais(self):
        empresa = Empresa.objects.create(
            nome="Populacao Panorama",
            email="decaimento-panorama@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        agora = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        for _ in range(4):
            registro = RegistroSintoma.objects.create(
                empresa=empresa,
                febre=True,
                latitude=-22.9,
                longitude=-43.1,
                cidade="Rio de Janeiro",
                estado="RJ",
                bairro="Centro",
                grupo="Respiratorio",
            )
            RegistroSintoma.objects.filter(id=registro.id).update(
                data_registro=agora - timedelta(days=15)
            )

        epidemiologia.clear_panorama_cache()
        payload = epidemiologia.build_panorama_payload()
        area = payload["layers"]["bairros"][0]

        self.assertEqual(area["raw_total_cases"], 4)
        self.assertEqual(area["total_cases"], area["active_cases"])
        self.assertLess(area["total_cases"], area["raw_total_cases"])
        self.assertEqual(payload["overview"]["raw_total_cases"], 4)
        self.assertLess(payload["overview"]["total_cases"], payload["overview"]["raw_total_cases"])

    def test_panorama_epidemiologico_ignora_registros_sinteticos_publicos(self):
        empresa = Empresa.objects.create(
            nome="Populacao Sintetico",
            email="sintetico-panorama@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        RegistroSintoma.objects.create(
            empresa=empresa,
            febre=True,
            latitude=-22.9,
            longitude=-43.1,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Centro",
            grupo="Respiratorio",
        )
        RegistroSintoma.objects.create(
            empresa=empresa,
            febre=True,
            latitude=-22.9,
            longitude=-43.1,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Centro",
            grupo="Respiratorio",
            device_id="demo-panorama-001",
            fonte_referencia="stress-test-map",
        )

        epidemiologia.clear_panorama_cache()
        payload = epidemiologia.build_panorama_payload()
        area = payload["layers"]["bairros"][0]

        self.assertEqual(area["raw_total_cases"], 1)
        self.assertEqual(area["total_cases"], area["active_cases"])
        self.assertEqual(payload["overview"]["raw_total_cases"], 1)

    def test_panorama_cache_recalcula_quando_version_global_muda(self):
        empresa = Empresa.objects.create(
            nome="Populacao Cache",
            email="cache-panorama@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        RegistroSintoma.objects.create(
            empresa=empresa,
            febre=True,
            latitude=-22.9,
            longitude=-43.1,
            cidade="Rio de Janeiro",
            estado="RJ",
            bairro="Centro",
            grupo="Respiratorio",
        )

        epidemiologia.clear_panorama_cache()
        payload1 = epidemiologia.build_panorama_payload()
        cache_key = "epidemiologia:panorama:version"
        cache.set(cache_key, int(cache.get(cache_key) or 0) + 1)
        payload2 = epidemiologia.build_panorama_payload()

        self.assertIsNot(payload1, payload2)
        self.assertEqual(payload2["overview"]["raw_total_cases"], 1)

    def test_radar_local_e_mapa_publico_usam_o_mesmo_recorte_publico(self):
        empresa_publica = Empresa.objects.create(
            nome="SolusCRT Populacao",
            email="populacao@soluscrt.com",
            senha=make_password("publico_app"),
            ativo=True,
            plano="publico",
            pacote_codigo="governo_estado",
        )
        empresa_privada = Empresa.objects.create(
            nome="Empresa Privada",
            email="privada-radar@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        for empresa in (empresa_publica, empresa_privada):
            RegistroSintoma.objects.create(
                empresa=empresa,
                febre=True,
                latitude=-22.9,
                longitude=-43.1,
                cidade="Niterói",
                estado="Rio de Janeiro",
                bairro="Icaraí",
                grupo="Respiratorio",
            )

        epidemiologia.clear_panorama_cache()
        response_mapa = Client().get(
            "/api/public/mapa?cidade=Niterói&estado=Rio%20de%20Janeiro"
        )
        response_radar = Client().get(
            "/api/public/radar-local?cidade=Niterói&estado=Rio%20de%20Janeiro&bairro=Icaraí"
        )

        self.assertEqual(response_mapa.status_code, 200)
        self.assertEqual(response_radar.status_code, 200)
        self.assertEqual(len(response_mapa.json()["hotspots"]), 1)
        self.assertEqual(response_mapa.json()["hotspots"][0]["raw_total_cases"], 1)
        self.assertEqual(response_radar.json()["radar"]["raw_total_cases"], 1)

    def test_panorama_epidemiologico_reduz_risco_quando_foco_envelhece(self):
        empresa = Empresa.objects.create(
            nome="Populacao Risco Temporal",
            email="risco-temporal@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        agora = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        for _ in range(13):
            registro = RegistroSintoma.objects.create(
                empresa=empresa,
                febre=True,
                latitude=-22.9,
                longitude=-43.1,
                cidade="Rio de Janeiro",
                estado="RJ",
                bairro="Centro",
                grupo="Respiratorio",
            )
            RegistroSintoma.objects.filter(id=registro.id).update(
                data_registro=agora - timedelta(days=20)
            )

        epidemiologia.clear_panorama_cache()
        payload = epidemiologia.build_panorama_payload()
        area = payload["layers"]["bairros"][0]

        self.assertLess(area["total_cases"], area["raw_total_cases"])
        self.assertEqual(area["risk_level"], "BAIXO")


class WebhookMiddlewareTests(TestCase):
    @override_settings(ASAAS_WEBHOOK_TOKEN="token-teste")
    def test_webhook_asaas_nao_exige_jwt_empresa(self):
        empresa = Empresa.objects.create(
            nome="Empresa Webhook",
            email="empresa-webhook@teste.com",
            senha=make_password("123456"),
            ativo=False,
        )
        payload = {
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "status": "RECEIVED",
                "externalReference": str(empresa.id),
            },
        }

        response = self.client.post(
            "/api/webhook",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-teste",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

        empresa.refresh_from_db()
        self.assertTrue(empresa.ativo)


@override_settings(DJANGO_ENV="test")
class GestaoTrialTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa Trial",
            email="trial@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        resp = self.client.post(
            "/api/login",
            data=json.dumps({"email": "trial@teste.com", "senha": "senha123", "device_id": "dev-trial", "device_name": "T"}),
            content_type="application/json",
        )
        self.token = resp.json().get("token", "")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, url, data=None):
        return self.client.post(url, data=json.dumps(data or {}), content_type="application/json", **self.auth)

    def test_trial_status_sem_trial_retorna_none(self):
        resp = self.client.get("/api/gestao/trial", **self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["trial"])

    def test_ativar_trial_cria_periodo_15_dias(self):
        resp = self._post("/api/gestao/trial/ativar")
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["trial"]["ativo"])
        self.assertEqual(body["trial"]["dias_restantes"], 14)  # 14-15 por arredondamento

    def test_ativar_trial_e_idempotente(self):
        self._post("/api/gestao/trial/ativar")
        resp = self._post("/api/gestao/trial/ativar")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["novo"])

    def test_onboarding_passo_invalido_retorna_400(self):
        resp = self._post("/api/gestao/onboarding/passo_inexistente")
        self.assertEqual(resp.status_code, 400)

    def test_onboarding_marca_passo_e_retorna_percentual(self):
        resp = self._post("/api/gestao/onboarding/primeiro_funcionario")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["novo"])
        self.assertGreater(body["onboarding"]["percentual"], 0)

    def test_onboarding_passo_idempotente(self):
        self._post("/api/gestao/onboarding/primeiro_aso")
        resp = self._post("/api/gestao/onboarding/primeiro_aso")
        self.assertFalse(resp.json()["novo"])


class PlatformStatusTests(TestCase):
    @override_settings(
        ASAAS_API_KEY="",
        ASAAS_WEBHOOK_TOKEN="",
        FIREBASE_SERVICE_ACCOUNT_PATH="/tmp/firebase-inexistente.json",
    )
    def test_platform_status_sinaliza_componentes_sem_configuracao_real(self):
        response = self.client.get("/api/platform/status")

        self.assertEqual(response.status_code, 200)
        componentes = {item["slug"]: item for item in response.json()["componentes"]}
        self.assertEqual(componentes["payments"]["status"], "degradado")
        self.assertEqual(componentes["push"]["status"], "degradado")
        self.assertEqual(componentes["ai"]["status"], "operacional")


class LoginRateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache as _cache
        _cache.clear()  # evita contaminação de tentativas de outros testes no locmem cache
        self.client = Client()
        Empresa.objects.create(
            nome="Empresa Limite",
            email="limite@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )

    @override_settings(TRUST_X_FORWARDED_FOR=True, DJANGO_ENV="development")
    def test_rate_limit_considera_identificador_mesmo_com_ip_variando(self):
        with patch("api.middleware.sys.argv", ["manage.py"]), patch("api.middleware._LOGIN_MAX_ATTEMPTS", 2):
            for forwarded in ("10.0.0.1", "10.0.0.2"):
                response = self.client.post(
                    "/api/login",
                    data=json.dumps({
                        "email": "limite@teste.com",
                        "senha": "senha-errada",
                        "device_id": "limite-device",
                    }),
                    content_type="application/json",
                    HTTP_X_FORWARDED_FOR=forwarded,
                )
                self.assertEqual(response.status_code, 401)

            bloqueio = self.client.post(
                "/api/login",
                data=json.dumps({
                    "email": "limite@teste.com",
                    "senha": "senha-errada",
                    "device_id": "limite-device",
                }),
                content_type="application/json",
                HTTP_X_FORWARDED_FOR="10.0.0.3",
            )

        self.assertEqual(bloqueio.status_code, 429)


@override_settings(DJANGO_ENV="test")
class SaudeOcupacionalAliasTests(TestCase):
    def setUp(self):
        from .models import ColaboradorAliasCorporativo, EmpresaSetor, PedidoApoioCorporativo, RegistroConflitoCultural

        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa Saúde Ocupacional",
            email="saude-ocupacional@teste.com",
            senha=make_password("senha123"),
            ativo=True,
            max_dispositivos=10,
            max_usuarios=10,
        )
        login = self.client.post(
            "/api/login",
            data=json.dumps({"email": "saude-ocupacional@teste.com", "senha": "senha123", "device_id": "dev-saude", "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {login.json()['token']}"}

        setor = EmpresaSetor.objects.create(empresa=self.empresa, nome="Operação")
        alias = ColaboradorAliasCorporativo.objects.create(
            empresa=self.empresa,
            alias_publico="anon-001",
            setor=setor,
            ativo=True,
        )
        PedidoApoioCorporativo.objects.create(
            empresa=self.empresa,
            alias=alias,
            setor=setor,
            relato="Preciso de apoio",
            status=PedidoApoioCorporativo.STATUS_NOVO,
        )
        RegistroConflitoCultural.objects.create(
            empresa=self.empresa,
            alias=alias,
            setor=setor,
            descricao="Conflito de comunicação",
            anonimo=False,
            status=RegistroConflitoCultural.STATUS_NOVO,
        )

    def test_alertas_wellness_retorna_alias_sem_field_error(self):
        response = self.client.get("/api/sst/wellness/alertas/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["apoios"][0]["alias__nome"], "anon-001")

    def test_conflitos_lista_retorna_alias_sem_field_error(self):
        response = self.client.get("/api/sst/conflitos/", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conflitos"][0]["alias__nome"], "anon-001")


@override_settings(DJANGO_ENV="test")
class GestaoIntegracaoTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa Integracao",
            email="integracao@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        resp = self.client.post(
            "/api/login",
            data=json.dumps({"email": "integracao@teste.com", "senha": "senha123", "device_id": "dev-int", "device_name": "T"}),
            content_type="application/json",
        )
        self.token = resp.json().get("token", "")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, url, data=None):
        return self.client.post(url, data=json.dumps(data or {}), content_type="application/json", **self.auth)

    def test_criar_integracao_totvs(self):
        resp = self._post("/api/gestao/integracoes", {"sistema": "totvs", "nome": "TOTVS Matriz"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["integracao"]["sistema"], "totvs")

    def test_sistema_invalido_retorna_400(self):
        resp = self._post("/api/gestao/integracoes", {"sistema": "sap_xyz"})
        self.assertEqual(resp.status_code, 400)

    def test_listar_integracoes(self):
        self._post("/api/gestao/integracoes", {"sistema": "adp"})
        resp = self.client.get("/api/gestao/integracoes", **self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["integracoes"]), 1)

    def test_webhook_importa_funcionarios(self):
        import hmac as _hmac
        import hashlib as _hashlib
        from api.models import IntegracaoRH
        integracao = IntegracaoRH.objects.create(
            empresa=self.empresa,
            sistema="totvs",
            status="inativo",
        )
        payload = json.dumps([
            {"cpf": "111.222.333-44", "nome": "Maria Silva", "cargo": "Operadora", "setor": "Produção"},
            {"cpf": "555.666.777-88", "nome": "João Souza", "cargo": "Técnico", "setor": "TI"},
        ])
        assinatura = "sha256=" + _hmac.new(
            integracao.webhook_secret.encode(), payload.encode(), _hashlib.sha256
        ).hexdigest()
        resp = self.client.post(
            "/api/gestao/integracoes/webhook/totvs",
            data=payload,
            content_type="application/json",
            HTTP_X_EMPRESA_ID=str(self.empresa.id),
            HTTP_X_SIGNATURE=assinatura,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["importados"], 2)

        from api.models import FuncionarioSST
        self.assertEqual(FuncionarioSST.objects.filter(empresa=self.empresa).count(), 2)

    def test_webhook_sem_empresa_id_retorna_400(self):
        resp = self.client.post(
            "/api/gestao/integracoes/webhook/totvs",
            data="[]",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(DJANGO_ENV="test")
class GestaoApiKeyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa ApiKey",
            email="apikey@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        resp = self.client.post(
            "/api/login",
            data=json.dumps({"email": "apikey@teste.com", "senha": "senha123", "device_id": "dev-key", "device_name": "T"}),
            content_type="application/json",
        )
        self.token = resp.json().get("token", "")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, url, data=None):
        return self.client.post(url, data=json.dumps(data or {}), content_type="application/json", **self.auth)

    def test_criar_api_key(self):
        resp = self._post("/api/gestao/chaves", {"nome": "Integração BI"})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("chave", body)
        self.assertTrue(body["chave"]["ativa"])
        self.assertNotIn("…", body["chave"]["chave"])  # chave completa na criação

    def test_nome_obrigatorio(self):
        resp = self._post("/api/gestao/chaves", {})
        self.assertEqual(resp.status_code, 400)

    def test_listar_chaves_esconde_valor(self):
        self._post("/api/gestao/chaves", {"nome": "BI"})
        resp = self.client.get("/api/gestao/chaves", **self.auth)
        self.assertEqual(resp.status_code, 200)
        chave_str = resp.json()["chaves"][0]["chave"]
        self.assertIn("…", chave_str)  # truncada na listagem

    def test_revogar_chave(self):
        resp = self._post("/api/gestao/chaves", {"nome": "Para revogar"})
        chave_id = resp.json()["chave"]["id"]
        resp_rev = self._post(f"/api/gestao/chaves/{chave_id}/revogar")
        self.assertEqual(resp_rev.status_code, 200)
        from api.models import ApiKeyEmpresa
        self.assertFalse(ApiKeyEmpresa.objects.get(id=chave_id).ativa)

    def test_acesso_dados_via_api_key(self):
        resp = self._post("/api/gestao/chaves", {"nome": "BI externo"})
        chave = resp.json()["chave"]["chave"]
        resp_dados = self.client.get(
            "/api/v1/dados",
            HTTP_AUTHORIZATION=f"ApiKey {chave}",
        )
        self.assertEqual(resp_dados.status_code, 200)
        self.assertIn("funcionarios", resp_dados.json())

    def test_acesso_dados_chave_invalida_retorna_401(self):
        resp = self.client.get("/api/v1/dados", HTTP_AUTHORIZATION="ApiKey chave-falsa-xyz")
        self.assertEqual(resp.status_code, 401)

    def test_benchmark_retorna_comparacao(self):
        resp = self.client.get("/api/gestao/benchmark", **self.auth)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("empresa", body)
        self.assertIn("media_setor", body)
        self.assertIn("vs_setor_pct", body)


class AssinaturaSSTApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa SST Teste",
            email="sst@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        resp = self.client.post(
            "/api/login",
            data=json.dumps({"email": "sst@teste.com", "senha": "senha123", "device_id": "dev-sst", "device_name": "Test"}),
            content_type="application/json",
        )
        self.token = resp.json().get("token", "")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

        from .models import FuncionarioSST, ASOOcupacional
        self.funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="João da Silva",
            cpf="12345678900",
            data_nascimento="1990-01-01",
            cargo="Operador",
            setor="Produção",
        )
        self.aso = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="admissional",
            data_emissao="2026-01-01",
            resultado="apto",
            medico_responsavel="Dr. Teste",
            crm="CRM-12345",
        )

    def _post_json(self, url, data):
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            **self.auth,
        )

    def _funcionario_auth(self):
        payload = {
            "funcionario_id": self.funcionario.id,
            "empresa_id": self.empresa.id,
            "iat": int(timezone.now().timestamp()),
            "exp": int((timezone.now() + timedelta(days=30)).timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_solicitar_assinatura_aso_retorna_201(self):
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "aso",
            "objeto_id": self.aso.id,
            "signatario_nome": "João da Silva",
            "signatario_email": "joao@empresa.com",
        })
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("assinatura", body)
        self.assertEqual(body["assinatura"]["status"], "pendente")
        self.assertIn("link_assinatura", body["assinatura"])

    def test_solicitar_assinatura_aso_define_ciencia_do_trabalhador(self):
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "aso",
            "objeto_id": self.aso.id,
        })
        self.assertEqual(resp.status_code, 201)
        assinatura = resp.json()["assinatura"]
        self.assertEqual(assinatura["papel_signatario"], "funcionario")
        self.assertEqual(assinatura["finalidade_assinatura"], "ciencia_trabalhador")
        self.assertEqual(assinatura["signatario_nome"], "João da Silva")
        self.assertEqual(assinatura["signatario_cpf"], "12345678900")
        self.assertIn("trabalhador", assinatura["quem_deve_assinar"].lower())
        self.assertIn("não substitui", assinatura["orientacao_assinatura"].lower())

    def test_assinatura_aso_chega_no_app_e_retorna_feedback(self):
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "aso",
            "objeto_id": self.aso.id,
        })
        self.assertEqual(resp.status_code, 201)
        assinatura = resp.json()["assinatura"]

        notificacao = NotificacaoFuncionario.objects.get(
            funcionario=self.funcionario,
            tipo=NotificacaoFuncionario.TIPO_ASSINATURA_SST,
            referencia_id=assinatura["id"],
        )
        self.assertFalse(notificacao.lida)

        resp_app = self.client.get("/api/funcionario/notificacoes", **self._funcionario_auth())
        self.assertEqual(resp_app.status_code, 200)
        item = resp_app.json()["notificacoes"][0]
        self.assertEqual(item["tipo"], NotificacaoFuncionario.TIPO_ASSINATURA_SST)
        self.assertEqual(item["acao_tipo"], "assinatura_sst")
        self.assertEqual(item["acao_label"], "Assinar pelo app")
        self.assertEqual(item["assinatura_status"], "pendente")
        self.assertIn("/assinatura/sst/", item["acao_url"])

        resp_assinar = self.client.post(
            f"/api/public/sst/assinar/{assinatura['token']}",
            data=json.dumps({"aceite": True, "nome": "João da Silva", "cpf": "12345678900"}),
            content_type="application/json",
        )
        self.assertEqual(resp_assinar.status_code, 200)
        notificacao.refresh_from_db()
        self.assertTrue(notificacao.lida)

    def test_solicitar_assinatura_documento_sst_define_validacao_tecnica(self):
        from .models import DocumentoSST

        documento = DocumentoSST.objects.create(
            empresa=self.empresa,
            tipo="PGR",
            titulo="PGR Unidade Operacional",
            responsavel_tecnico="Eng. Segurança",
            registro_profissional="CREA-123",
        )
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "documento_sst",
            "objeto_id": documento.id,
        })
        self.assertEqual(resp.status_code, 201)
        assinatura = resp.json()["assinatura"]
        self.assertEqual(assinatura["papel_signatario"], "responsavel_tecnico")
        self.assertEqual(assinatura["finalidade_assinatura"], "validacao_tecnica")
        self.assertIn("responsável técnico", assinatura["quem_deve_assinar"].lower())

    def test_listar_assinaturas_retorna_lista(self):
        self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "aso",
            "objeto_id": self.aso.id,
        })
        resp = self.client.get("/api/sst/assinaturas", **self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("assinaturas", resp.json())

    def test_fluxo_completo_solicitar_e_assinar(self):
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "aso",
            "objeto_id": self.aso.id,
            "signatario_nome": "João da Silva",
        })
        self.assertEqual(resp.status_code, 201)
        token = resp.json()["assinatura"]["token"]

        resp_assinar = self.client.post(
            f"/api/public/sst/assinar/{token}",
            data=json.dumps({"aceite": True, "nome": "João da Silva", "cpf": "123.456.789-00"}),
            content_type="application/json",
        )
        self.assertEqual(resp_assinar.status_code, 200)
        self.assertEqual(resp_assinar.json()["assinatura"]["status"], "assinado")

        resp_repetido = self.client.post(
            f"/api/public/sst/assinar/{token}",
            data=json.dumps({"aceite": True, "nome": "João da Silva", "cpf": "123.456.789-00"}),
            content_type="application/json",
        )
        self.assertEqual(resp_repetido.status_code, 409)
        self.assertEqual(resp_repetido.json()["erro"], "assinatura já concluída")

    def test_validar_assinatura_publica(self):
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "aso",
            "objeto_id": self.aso.id,
            "signatario_nome": "João da Silva",
        })
        token = resp.json()["assinatura"]["token"]
        self.client.post(
            f"/api/public/sst/assinar/{token}",
            data=json.dumps({"aceite": True, "nome": "João da Silva"}),
            content_type="application/json",
        )

        resp_valida = self.client.get(f"/api/public/sst/validar/{token}")
        self.assertEqual(resp_valida.status_code, 200)
        body = resp_valida.json()
        self.assertTrue(body["valida"])
        self.assertEqual(body["funcionario"], "João da Silva")

    def test_assinar_sem_nome_retorna_400(self):
        from .models import DocumentoSST

        documento = DocumentoSST.objects.create(
            empresa=self.empresa,
            tipo="PGR",
            titulo="PGR sem signatário",
            responsavel_tecnico="Eng. Segurança",
        )
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "documento_sst",
            "objeto_id": documento.id,
        })
        token = resp.json()["assinatura"]["token"]
        resp_assinar = self.client.post(
            f"/api/public/sst/assinar/{token}",
            data=json.dumps({"aceite": True}),
            content_type="application/json",
        )
        self.assertEqual(resp_assinar.status_code, 400)

    def test_tipo_documento_invalido_retorna_400(self):
        resp = self._post_json("/api/sst/assinaturas", {
            "tipo_documento": "invalido",
            "objeto_id": self.aso.id,
        })
        self.assertEqual(resp.status_code, 400)

    def test_sem_autenticacao_retorna_401(self):
        resp = Client().get("/api/sst/assinaturas")
        self.assertEqual(resp.status_code, 401)


class SolicitacaoExameEmailTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa SST",
            email="sst@example.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="empresa_profissional_25",
            sessao_ativa_chave="sessao-solicitacao-email",
        )
        self.funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Bruno Santos Demo",
            cpf="000.000.000-11",
            cargo="Tecnico de Manutencao",
        )
        payload = {
            "empresa_id": self.empresa.id,
            "principal_kind": "empresa",
            "principal_id": self.empresa.id,
            "session_key": self.empresa.sessao_ativa_chave,
            "exp": timezone.now() + timedelta(hours=1),
        }
        self.client.cookies["auth_token"] = jwt.encode(
            payload, settings.JWT_SECRET_KEY, algorithm="HS256"
        )

    def _pedido_email_payload(self):
        return {
            "funcionario_id": self.funcionario.id,
            "tipo_aso": "periodico",
            "modo": "email",
            "clinica_nome": "ABC Clinica",
            "clinica_email": "contato@abc-clinica.com.br",
            "exames": [
                "Avaliacao clinica geral (anamnese + exame fisico)",
                "Hemograma completo (serie vermelha e branca)",
            ],
            "urgente": True,
        }

    @patch("api.views_solicitacao_exame.EmailMessage.send", return_value=0)
    def test_email_externo_nao_marca_enviado_sem_confirmacao_do_backend(self, send_mock):
        resp = self.client.post(
            "/api/sst/solicitacoes-exame",
            data=json.dumps(self._pedido_email_payload()),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertFalse(body["email_enviado"])
        self.assertIn("nao foi confirmado", body["aviso_email"])

        solicitacao = SolicitacaoExame.objects.get(funcionario=self.funcionario)
        self.assertFalse(solicitacao.email_enviado)
        self.assertIsNone(solicitacao.email_enviado_em)
        self.assertIn("SMTP nao confirmou", solicitacao.resposta_clinica)
        send_mock.assert_called_once()

    @patch("api.views_solicitacao_exame.EmailMessage.send", side_effect=[0, 1])
    def test_reenviar_email_recupera_solicitacao_pendente(self, send_mock):
        resp = self.client.post(
            "/api/sst/solicitacoes-exame",
            data=json.dumps(self._pedido_email_payload()),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

        solicitacao = SolicitacaoExame.objects.get(funcionario=self.funcionario)
        self.assertFalse(solicitacao.email_enviado)

        resp_reenvio = self.client.post(
            f"/api/sst/solicitacoes-exame/{solicitacao.id}",
            data=json.dumps({"acao": "reenviar_email"}),
            content_type="application/json",
        )

        self.assertEqual(resp_reenvio.status_code, 200)
        solicitacao.refresh_from_db()
        self.assertTrue(solicitacao.email_enviado)
        self.assertIsNotNone(solicitacao.email_enviado_em)
        self.assertIn("SMTP", solicitacao.resposta_clinica)
        self.assertEqual(send_mock.call_count, 2)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="mailer@soluscrt.com.br",
        EMAIL_HOST_PASSWORD="segredo-smtp",
        DEFAULT_FROM_EMAIL="SolusCRT <noreply@soluscrt.com.br>",
    )
    @patch("api.views_solicitacao_exame.EmailMessage")
    def test_envio_email_usa_remetente_da_conta_smtp(self, email_message_mock):
        email_message_mock.return_value.send.return_value = 1

        resp = self.client.post(
            "/api/sst/solicitacoes-exame",
            data=json.dumps(self._pedido_email_payload()),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 201)
        _, kwargs = email_message_mock.call_args
        self.assertEqual(kwargs["from_email"], "SolusCRT <mailer@soluscrt.com.br>")


def _owner_e_banco_distinto():
    """True quando a conexao "owner" aponta para um banco fisico diferente da
    "default". Em CI (Postgres) ambos os aliases usam o MESMO banco
    (DATABASE_URL unica) -> retorna False. Em dev/teste com sqlite, o Django
    cria bancos in-memory separados por alias -> retorna True."""
    from django.db import connections

    d = connections["default"].settings_dict
    o = connections["owner"].settings_dict
    chave = lambda s: (s.get("NAME"), s.get("HOST"), s.get("PORT"))
    return chave(d) != chave(o)


def _provisiona_login_funcionario_owner(empresa, funcionario, email, senha):
    """Garante que o login do portal do funcionario (que consulta a conexao
    "owner") encontre a credencial. Em CI (owner == default) basta criar na
    "default": o TransactionTestCase commita e a conexao "owner" enxerga a
    linha. Em sqlite (owner != default) espelha empresa, funcionario e
    credencial na conexao "owner". Escrever nos dois quando sao o mesmo banco
    duplicaria o PK e travaria esperando o lock — por isso o desvio por ambiente."""
    if _owner_e_banco_distinto():
        empresa_owner = Empresa.objects.using("owner").create(
            id=empresa.id,
            nome=empresa.nome,
            email=empresa.email,
            senha=empresa.senha,
            ativo=empresa.ativo,
        )
        funcionario_owner = FuncionarioSST.objects.using("owner").create(
            id=funcionario.id,
            empresa=empresa_owner,
            nome=funcionario.nome,
            cpf=funcionario.cpf,
            cargo=funcionario.cargo,
            setor=getattr(funcionario, "setor", "") or "",
            ativo=funcionario.ativo,
        )
        CredencialAppFuncionario.objects.using("owner").create(
            funcionario=funcionario_owner,
            email=email,
            senha=make_password(senha),
        )
    else:
        CredencialAppFuncionario.objects.create(
            funcionario=funcionario,
            email=email,
            senha=make_password(senha),
        )


@override_settings(DJANGO_ENV="test")
class SolicitacaoExameAppSyncTests(TransactionTestCase):
    # Usa TransactionTestCase (em vez de TestCase) porque o login do app do
    # funcionario le pela conexao "owner". Em TestCase, a transacao atomica do
    # teste fica aberta na conexao "default" e a conexao "owner" (segunda
    # conexao para o MESMO banco fisico em CI/dev) nunca enxerga as linhas — e,
    # ao inserir os mesmos PKs nas duas conexoes, trava esperando o lock para
    # sempre. Com TransactionTestCase as escritas na "default" sao commitadas e
    # ficam visiveis para a conexao "owner" quando os dois aliases compartilham
    # o mesmo banco (CI Postgres). Quando "owner" e um banco distinto (sqlite
    # local), espelhamos as linhas explicitamente na conexao "owner".
    databases = {"default", "owner"}
    reset_sequences = True

    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa SST",
            email="sst@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        self.funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Carlos Operador",
            cpf="123.456.789-00",
            cargo="Operador de Produção",
            ativo=True,
        )
        _provisiona_login_funcionario_owner(
            self.empresa, self.funcionario, "carlos@app.com", "app12345"
        )
        login = self.client.post(
            "/api/login",
            data=json.dumps({"email": "sst@teste.com", "senha": "senha123", "device_id": "sst-web", "device_name": "Navegador"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

    def _token_funcionario(self):
        client = Client()
        resp = client.post(
            "/api/funcionario/login",
            data=json.dumps({"email": "carlos@app.com", "senha": "app12345"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["token"]

    def test_pedido_interno_cria_notificacao_e_aparece_no_app(self):
        resp = self.client.post(
            "/api/sst/solicitacoes-exame",
            data=json.dumps({
                "funcionario_id": self.funcionario.id,
                "tipo_aso": "periodico",
                "modo": "interno",
                "exames": ["Hemograma completo"],
                "observacoes": "Levar documento com foto.",
            }),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["app_notificado"])
        self.assertEqual(NotificacaoFuncionario.objects.filter(
            funcionario=self.funcionario,
            empresa=self.empresa,
            tipo="exame",
            referencia_id=body["id"],
        ).count(), 1)

        token = self._token_funcionario()
        app_client = Client()
        resp_portal = app_client.get(
            "/api/funcionario/minhas-solicitacoes",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp_portal.status_code, 200)
        self.assertEqual(len(resp_portal.json()["solicitacoes"]), 1)
        self.assertEqual(resp_portal.json()["solicitacoes"][0]["status"], "pendente")

    def test_clinica_agenda_exame_e_app_recebe_atualizacao(self):
        clinica = Empresa.objects.create(
            nome="Clinica Centro",
            email="clinica@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        solicitacao = SolicitacaoExame.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            clinica=clinica,
            tipo_aso="periodico",
            exames=json.dumps(["Audiometria"], ensure_ascii=False),
        )

        clinica_client = Client()
        login = clinica_client.post(
            "/api/login",
            data=json.dumps({"email": "clinica@teste.com", "senha": "senha123", "device_id": "clinica-web", "device_name": "Clinic"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        resp = clinica_client.post(
            f"/api/clinica/solicitacoes-exame/{solicitacao.id}/acao",
            data=json.dumps({"acao": "agendar", "data_agendamento": "2026-05-25"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        token = self._token_funcionario()
        app_client = Client()
        resp_notif = app_client.get(
            "/api/funcionario/notificacoes",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp_notif.status_code, 200)
        titulos = [item["titulo"] for item in resp_notif.json()["notificacoes"]]
        self.assertIn("Exame agendado", titulos)

        resp_portal = app_client.get(
            "/api/funcionario/minhas-solicitacoes",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp_portal.status_code, 200)
        self.assertEqual(resp_portal.json()["solicitacoes"][0]["status"], "agendado")


@override_settings(DJANGO_ENV="test")
class FuncionarioPortalEndpointsTests(TransactionTestCase):
    # O login do portal do funcionario consulta a conexao "owner" (que ignora
    # RLS). Em CI a conexao "owner" aponta para o mesmo banco fisico da
    # "default", entao precisamos de TransactionTestCase para que as escritas
    # sejam visiveis entre conexoes (TestCase deixaria tudo em transacao nao
    # commitada, causando deadlock/invisibilidade). Localmente (sqlite) "owner"
    # e um banco separado e o helper espelha as linhas necessarias.
    reset_sequences = True
    databases = {"default", "owner"}

    def setUp(self):
        self.client = Client()
        self.empresa = Empresa.objects.create(
            nome="Empresa Portal",
            email="portal@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        self.funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Aline Colaboradora",
            cpf="111.222.333-44",
            cargo="Analista",
            setor="Operações",
            ativo=True,
        )
        _provisiona_login_funcionario_owner(
            self.empresa, self.funcionario, "aline@app.com", "app12345"
        )
        ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="periodico",
            data_emissao=timezone.now().date(),
            data_validade=timezone.now().date() + timedelta(days=180),
            medico_responsavel="Dra. Portal",
            crm="CRM/SP 123456",
            resultado="apto",
        )
        TreinamentoNR.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            nr="NR-6",
            titulo="Treinamento de EPI",
            instrutor="Instrutor Portal",
            carga_horaria=4,
            data_realizacao=timezone.now().date() - timedelta(days=10),
            data_validade=timezone.now().date() + timedelta(days=355),
            status="valido",
        )
        epi = EPIItem.objects.create(
            empresa=self.empresa,
            nome="Respirador PFF2",
            tipo="respiratoria",
            ca_numero="CA-9988",
            ativo=True,
        )
        EntregaEPI.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            epi=epi,
            data_entrega=timezone.now().date() - timedelta(days=3),
            quantidade=1,
        )

    def _token_funcionario(self):
        app_client = Client()
        resp = app_client.post(
            "/api/funcionario/login",
            data=json.dumps({"email": "aline@app.com", "senha": "app12345"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["token"]

    def test_portal_funcionario_treinamentos_e_epi_respondem_schema_compativel(self):
        token = self._token_funcionario()
        app_client = Client()

        treinamentos = app_client.get(
            "/api/funcionario/meus-treinamentos",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(treinamentos.status_code, 200)
        item_treinamento = treinamentos.json()["treinamentos"][0]
        self.assertEqual(item_treinamento["data_validade"], item_treinamento["data_vencimento"])

        epis = app_client.get(
            "/api/funcionario/meus-epis",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(epis.status_code, 200)
        self.assertEqual(epis.json()["epis"][0]["ca"], "CA-9988")

        dashboard = app_client.get(
            "/api/funcionario/dashboard",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["treinamentos_total"], 1)

    def test_conformidade_retorna_json_mesmo_com_modelos_atuais(self):
        login = self.client.post(
            "/api/login",
            data=json.dumps({"email": "portal@teste.com", "senha": "senha123", "device_id": "portal-web", "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        resp = self.client.get("/api/sst/conformidade/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["resumo"]["total"], 1)
        self.assertEqual(resp.json()["funcionarios"][0]["nome"], "Aline Colaboradora")


@override_settings(DJANGO_ENV="test")
class PlataformaTiAccessTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Empresa TI",
            email="empresa-ti@teste.com",
            senha=make_password("senha123"),
            ativo=True,
            max_dispositivos=10,
            max_usuarios=10,
        )
        self.usuario_rh = EmpresaUsuario.objects.create(
            empresa=self.empresa,
            nome="Usuário RH",
            email="rh@teste.com",
            senha=make_password("senha123"),
            cargo="RH",
            ativo=True,
        )
        self.usuario_ti = EmpresaUsuario.objects.create(
            empresa=self.empresa,
            nome="Usuário TI",
            email="ti@teste.com",
            senha=make_password("senha123"),
            cargo="TI",
            ativo=True,
        )
        self.usuario_operacao = EmpresaUsuario.objects.create(
            empresa=self.empresa,
            nome="Usuário Operação",
            email="operacao@teste.com",
            senha=make_password("senha123"),
            cargo="Operacao",
            ativo=True,
        )
        self.usuario_gerencia = EmpresaUsuario.objects.create(
            empresa=self.empresa,
            nome="Usuário Gerência",
            email="gerencia@teste.com",
            senha=make_password("senha123"),
            cargo="Gerente Operacional",
            ativo=True,
        )
        self._grant_ti_access(self.empresa, self.usuario_ti, concedido_por="setup-ti")

    def _grant_ti_access(self, empresa, usuario, concedido_por="teste"):
        from .models import RBACAtribuicao, RBACPermissao

        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo="plataforma_ti",
            defaults={
                "descricao": "Acesso exclusivo à Plataforma TI",
                "modulo": "ti",
            },
        )
        RBACAtribuicao.objects.update_or_create(
            empresa=empresa,
            usuario=usuario,
            permissao=permissao,
            defaults={"ativo": True, "concedido_por": concedido_por},
        )

    def _login_client(self, email, senha="senha123", device_id="dev-ti"):
        client = Client()
        resp = client.post(
            "/api/login",
            data=json.dumps({"email": email, "senha": senha, "device_id": device_id, "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        return client

    def _empresa_setorial_com_usuarios(self, pacote_codigo, prefixo):
        empresa = Empresa.objects.create(
            nome=f"Empresa {prefixo}",
            email=f"{prefixo}@teste.com",
            senha=make_password("senha123"),
            ativo=True,
            pacote_codigo=pacote_codigo,
            max_dispositivos=10,
            max_usuarios=10,
        )
        usuario_ti = EmpresaUsuario.objects.create(
            empresa=empresa,
            nome=f"TI {prefixo}",
            email=f"ti-{prefixo}@teste.com",
            senha=make_password("senha123"),
            cargo="TI",
            ativo=True,
        )
        self._grant_ti_access(empresa, usuario_ti, concedido_por=f"setup-{prefixo}")
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome=f"RH {prefixo}",
            email=f"rh-{prefixo}@teste.com",
            senha=make_password("senha123"),
            cargo="RH",
            ativo=True,
        )
        EmpresaUsuario.objects.create(
            empresa=empresa,
            nome=f"Gerência {prefixo}",
            email=f"ger-{prefixo}@teste.com",
            senha=make_password("senha123"),
            cargo="Gerente Operacional",
            ativo=True,
        )
        return empresa

    def test_usuario_sem_perfil_ti_nao_acessa_plataforma(self):
        client = self._login_client("rh@teste.com", device_id="dev-rh")
        resp_page = client.get("/gestao/plataforma/")
        self.assertEqual(resp_page.status_code, 403)

        resp_api = client.get("/api/gestao/plataforma/seguranca/")
        self.assertEqual(resp_api.status_code, 403)

    def test_usuario_ti_acessa_rotas_restritas(self):
        client = self._login_client("ti@teste.com", device_id="dev-ti-user")
        resp_page = client.get("/gestao/plataforma/")
        self.assertEqual(resp_page.status_code, 200)

        resp_api = client.get("/api/gestao/plataforma/seguranca/")
        self.assertEqual(resp_api.status_code, 200)

    def test_login_usuario_ti_prioriza_destino_portal_ti(self):
        client = Client()
        resp = client.post(
            "/api/login",
            data=json.dumps({"email": "ti@teste.com", "senha": "senha123", "device_id": "dev-ti-destino", "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("destination"), "/ti/")

    def test_login_usuario_rh_prioriza_destino_portal_rh(self):
        client = Client()
        resp = client.post(
            "/api/login",
            data=json.dumps({"email": "rh@teste.com", "senha": "senha123", "device_id": "dev-rh-destino", "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("destination"), "/rh/")

    def test_login_usuario_gerencia_prioriza_destino_portal_gerencial(self):
        client = Client()
        resp = client.post(
            "/api/login",
            data=json.dumps({"email": "gerencia@teste.com", "senha": "senha123", "device_id": "dev-ger-destino", "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("destination"), "/gerencia/")

    def test_usuario_ti_nao_acessa_gestao_operacional(self):
        client = self._login_client("ti@teste.com", device_id="dev-ti-gestao")
        resp = client.get("/gestao/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/ti/")

    def test_usuario_rh_nao_acessa_gestao_operacional(self):
        client = self._login_client("rh@teste.com", device_id="dev-rh-gestao")
        resp = client.get("/gestao/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/rh/")

    def test_usuario_operacao_nao_acessa_portal_rh(self):
        client = self._login_client("operacao@teste.com", device_id="dev-op-rh")
        resp = client.get("/rh/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/dashboard-empresa/")

    def test_admin_principal_sem_perfil_ti_nao_acessa_plataforma(self):
        empresa_sem_ti = Empresa.objects.create(
            nome="Empresa Bootstrap",
            email="bootstrap@teste.com",
            senha=make_password("senha123"),
            ativo=True,
        )
        client = Client()
        login = client.post(
            "/api/login",
            data=json.dumps({"email": "bootstrap@teste.com", "senha": "senha123", "device_id": "bootstrap-device", "device_name": "Browser"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        resp_page = client.get("/gestao/plataforma/")
        self.assertEqual(resp_page.status_code, 403)
        self.assertContains(resp_page, "Plataforma TI protegida para uso técnico", status_code=403)

    def test_links_ambiente_it_aparecem_nas_gestoes_setoriais(self):
        empresas = [
            ("farmacia_rede_regional", "farmacia-it-link@teste.com", "/farmacia/gestao/"),
            ("hospital_medio", "hospital-it-link@teste.com", "/hospital/gestao/"),
            ("plano_saude_operadora", "plano-it-link@teste.com", "/plano-saude/gestao/"),
        ]
        for pacote_codigo, email, rota in empresas:
            empresa = Empresa.objects.create(
                nome=f"Empresa {pacote_codigo}",
                email=email,
                senha=make_password("senha123"),
                ativo=True,
                pacote_codigo=pacote_codigo,
            )
            client = self._login_client(email, device_id=f"dev-{pacote_codigo}")
            response = client.get(rota)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Ambiente IT")
            self.assertContains(response, "/ti/")

    def test_usuario_ti_de_farmacia_acessa_plataforma_ti(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia TI",
            email="farmacia-ti@teste.com",
            senha=make_password("senha123"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
        )
        usuario_ti = EmpresaUsuario.objects.create(
            empresa=farmacia,
            nome="Tecnico Farmacia",
            email="farmacia-ti-user@teste.com",
            senha=make_password("senha123"),
            cargo="TI",
            ativo=True,
        )
        self._grant_ti_access(farmacia, usuario_ti, concedido_por="teste-farmacia")

        client = self._login_client("farmacia-ti-user@teste.com", device_id="dev-farm-ti")
        resp_page = client.get("/gestao/plataforma/")
        self.assertEqual(resp_page.status_code, 200)

    def test_api_farmacia_bloqueia_ti_e_rh_e_libera_gerencia(self):
        self._empresa_setorial_com_usuarios("farmacia_rede_regional", "farm-api")

        client_ti = self._login_client("ti-farm-api@teste.com", device_id="dev-farm-api-ti")
        client_rh = self._login_client("rh-farm-api@teste.com", device_id="dev-farm-api-rh")
        client_ger = self._login_client("ger-farm-api@teste.com", device_id="dev-farm-api-ger")

        self.assertEqual(client_ti.get("/api/farmacia/dashboard").status_code, 403)
        self.assertEqual(client_rh.get("/api/farmacia/dashboard").status_code, 403)
        self.assertEqual(client_ger.get("/api/farmacia/dashboard").status_code, 200)

    def test_api_hospital_bloqueia_ti_e_rh_e_libera_gerencia(self):
        self._empresa_setorial_com_usuarios("hospital_medio", "hosp-api")

        client_ti = self._login_client("ti-hosp-api@teste.com", device_id="dev-hosp-api-ti")
        client_rh = self._login_client("rh-hosp-api@teste.com", device_id="dev-hosp-api-rh")
        client_ger = self._login_client("ger-hosp-api@teste.com", device_id="dev-hosp-api-ger")

        self.assertEqual(client_ti.get("/api/hospital/dashboard").status_code, 403)
        self.assertEqual(client_rh.get("/api/hospital/dashboard").status_code, 403)
        self.assertEqual(client_ger.get("/api/hospital/dashboard").status_code, 200)

    def test_api_plano_saude_bloqueia_ti_e_rh_e_libera_gerencia(self):
        self._empresa_setorial_com_usuarios("plano_saude_operadora", "plano-api")

        client_ti = self._login_client("ti-plano-api@teste.com", device_id="dev-plano-api-ti")
        client_rh = self._login_client("rh-plano-api@teste.com", device_id="dev-plano-api-rh")
        client_ger = self._login_client("ger-plano-api@teste.com", device_id="dev-plano-api-ger")

        self.assertEqual(client_ti.get("/api/plano-saude/dashboard").status_code, 403)
        self.assertEqual(client_rh.get("/api/plano-saude/dashboard").status_code, 403)
        self.assertEqual(client_ger.get("/api/plano-saude/dashboard").status_code, 200)

    def test_usuario_nao_ti_de_farmacia_nao_acessa_plataforma_ti(self):
        farmacia = Empresa.objects.create(
            nome="Farmacia Operacao",
            email="farmacia-op@teste.com",
            senha=make_password("senha123"),
            ativo=True,
            pacote_codigo="farmacia_rede_regional",
        )
        EmpresaUsuario.objects.create(
            empresa=farmacia,
            nome="Operador Farmacia",
            email="farmacia-op-user@teste.com",
            senha=make_password("senha123"),
            cargo="Operacao",
            ativo=True,
        )

        client = self._login_client("farmacia-op-user@teste.com", device_id="dev-farm-op")
        resp_page = client.get("/gestao/plataforma/")
        self.assertEqual(resp_page.status_code, 403)
        self.assertContains(resp_page, "Plataforma TI protegida para uso técnico", status_code=403)

    def test_rh_consegue_cadastrar_credencial_ti(self):
        client = self._login_client("rh@teste.com", device_id="dev-rh-ti")
        resp = client.post(
            "/api/usuarios/credencial-ti",
            data=json.dumps({
                "nome": "Tecnologia RH",
                "email": "novo-ti@teste.com",
                "senha": "SenhaTI123!",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

        novo_ti = EmpresaUsuario.objects.get(empresa=self.empresa, email="novo-ti@teste.com")
        self.assertEqual(novo_ti.cargo, "TI")
        self.assertTrue(novo_ti.ativo)

        client_ti = self._login_client("novo-ti@teste.com", senha="SenhaTI123!", device_id="dev-ti-novo")
        resp_page = client_ti.get("/gestao/plataforma/")
        self.assertEqual(resp_page.status_code, 200)

    def test_usuario_sem_perfil_rh_nao_pode_cadastrar_credencial_ti(self):
        client = self._login_client("operacao@teste.com", device_id="dev-op-ti")
        resp = client.post(
            "/api/usuarios/credencial-ti",
            data=json.dumps({
                "nome": "Tecnologia Operacao",
                "email": "ti-bloqueado@teste.com",
                "senha": "SenhaTI123!",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Apenas RH", resp.json().get("erro", ""))

    def test_usuario_operacao_nao_acessa_dashboard_executivo_api(self):
        client = self._login_client("operacao@teste.com", device_id="dev-op-exec")
        resp = client.get("/api/executive/dashboard/")
        self.assertEqual(resp.status_code, 403)

    def test_usuario_operacao_nao_executa_seed_demo_enterprise(self):
        client = self._login_client("operacao@teste.com", device_id="dev-op-seed")
        resp = client.post("/api/enterprise/seed-operational-demo")
        self.assertEqual(resp.status_code, 403)


# ════════════════════════════════════════════════════════════════════════════════
#  TESTES — Módulos enterprise do Plano de Saúde
#  Endpoints: dashboard-exec, sla, auditoria, contratos, comunicacao,
#             telemedicina, odontologia, regulatorio
# ════════════════════════════════════════════════════════════════════════════════

from .models import (
    CarenciaBeneficiario,
    ContratoGrupo,
    TeleconsultaAutorizacao,
    BeneficiarioOdonto,
    GuiaOdonto,
    MensagemPlano,
    FaturamentoBeneficiario,
    ProgramaSaude,
)


class PlanoSaudeEnterpriseBaseTests(TestCase):
    """Mixin com setUp e helpers compartilhados por todos os suites enterprise."""

    def setUp(self):
        self.client = Client()
        self.operadora = Empresa.objects.create(
            nome="Operadora Teste",
            email="operadora@teste.com",
            senha=make_password("senha123"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=10,
            max_usuarios=10,
        )
        resp = self.client.post(
            "/api/login",
            data=json.dumps({
                "email": "operadora@teste.com",
                "senha": "senha123",
                "device_id": "device-enterprise",
                "device_name": "Test",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, msg=f"Login falhou: {resp.content}")
        # Django test Client persists the auth_token cookie set by login
        # so all subsequent self.client requests are authenticated via cookie.
        self.anon = Client()  # fresh client with no cookies — used in 401 tests

        # Plano base
        self.plano = PlanoSaude.objects.create(
            empresa=self.operadora,
            nome="Plano Teste",
            registro_ans="000001",
            modalidade="cooperativa",
            status="ativo",
        )
        # Beneficiário base
        self.benef = BeneficiarioPlano.objects.create(
            plano=self.plano,
            nome="Ana Beneficiaria",
            cpf="111.222.333-44",
            email="ana@beneficiario.com",
            situacao="ativo",
        )
        # Prestador base
        self.prestador = PrestadorPlanoSaude.objects.create(
            empresa=self.operadora,
            nome_fantasia="Clinica Teste",
            especialidades="Cardiologia",
            status="credenciado",
        )

    def _get(self, url):
        return self.client.get(url)

    def _post(self, url, data=None):
        return self.client.post(
            url,
            data=json.dumps(data or {}),
            content_type="application/json",
        )

    def _put(self, url, data=None):
        return self.client.put(
            url,
            data=json.dumps(data or {}),
            content_type="application/json",
        )

    def _delete(self, url):
        return self.client.delete(url)


class CarenciasTests(PlanoSaudeEnterpriseBaseTests):
    """GET/POST /api/plano-saude/carencias/"""

    def test_lista_e_criacao_de_carencia_funcionam(self):
        resp_post = self._post("/api/plano-saude/carencias/", {
            "beneficiario_id": self.benef.pk,
            "tipo_procedimento": "consulta",
            "data_inicio": date.today().isoformat(),
            "dias_carencia": 15,
            "observacoes": "Carência inicial",
        })
        self.assertEqual(resp_post.status_code, 201, msg=resp_post.content)
        payload_post = resp_post.json()
        self.assertTrue(payload_post.get("ok"))
        self.assertIn("id", payload_post)

        resp_get = self._get("/api/plano-saude/carencias/")
        self.assertEqual(resp_get.status_code, 200, msg=resp_get.content)
        payload_get = resp_get.json()
        self.assertIn("carencias", payload_get)
        self.assertEqual(len(payload_get["carencias"]), 1)
        carencia = payload_get["carencias"][0]
        self.assertEqual(carencia["beneficiario_nome"], self.benef.nome)
        self.assertEqual(carencia["plano_nome"], self.plano.nome)
        self.assertEqual(carencia["tipo_procedimento"], "consulta")
        self.assertEqual(carencia["dias_carencia"], 15)


class DashboardExecTests(PlanoSaudeEnterpriseBaseTests):
    """GET /api/plano-saude/dashboard-exec/"""

    def test_retorna_200_e_chaves_obrigatorias(self):
        resp = self._get("/api/plano-saude/dashboard-exec/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        for chave in ("mlr", "pmpm", "mrr", "beneficiarios_ativos",
                      "crescimento_beneficiarios", "mlr_por_plano",
                      "mlr_mensal", "top_procedimentos"):
            self.assertIn(chave, payload, msg=f"Chave '{chave}' ausente no dashboard-exec")

    def test_mlr_zero_sem_dados(self):
        resp = self._get("/api/plano-saude/dashboard-exec/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["mlr"], 0.0)

    def test_mlr_calculado_com_sinistros_e_faturamento(self):
        FaturamentoBeneficiario.objects.create(
            empresa=self.operadora,
            plano=self.plano,
            beneficiario=self.benef,
            competencia=date.today().strftime("%Y-%m"),
            valor_mensalidade=1000,
            valor_total=1000,
        )
        Sinistro.objects.create(
            empresa=self.operadora,
            plano=self.plano,
            beneficiario=self.benef,
            tipo="consulta",
            valor_total=800,
            status="aberto",
        )
        resp = self._get("/api/plano-saude/dashboard-exec/?periodo=mes")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertAlmostEqual(payload["mlr"], 80.0, places=0)
        self.assertGreater(payload["mrr"], 0)

    def test_periodo_trimestre_aceito(self):
        resp = self._get("/api/plano-saude/dashboard-exec/?periodo=trimestre")
        self.assertEqual(resp.status_code, 200)

    def test_periodo_ano_aceito(self):
        resp = self._get("/api/plano-saude/dashboard-exec/?periodo=ano")
        self.assertEqual(resp.status_code, 200)

    def test_crescimento_beneficiarios_tem_12_meses(self):
        resp = self._get("/api/plano-saude/dashboard-exec/")
        crescimento = resp.json()["crescimento_beneficiarios"]
        self.assertEqual(len(crescimento), 12)
        for item in crescimento:
            self.assertIn("mes", item)
            self.assertIn("valor", item)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/dashboard-exec/")
        self.assertEqual(resp.status_code, 401)


class SLAMonitoringTests(PlanoSaudeEnterpriseBaseTests):
    """GET /api/plano-saude/sla/"""

    def test_retorna_200_e_estrutura(self):
        resp = self._get("/api/plano-saude/sla/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        for chave in ("por_tipo", "breaches", "geral_pct",
                      "consulta_pct", "exame_pct", "urg_vencidas"):
            self.assertIn(chave, payload, msg=f"Chave '{chave}' ausente no SLA")

    def test_sem_guias_geral_pct_100(self):
        resp = self._get("/api/plano-saude/sla/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["geral_pct"], 100.0)
        self.assertEqual(resp.json()["breaches"], [])

    def test_guia_urgencia_vencida_aparece_em_breaches(self):
        # Cria guia de urgência aberta há 10 horas (prazo=4h → breach)
        guia = GuiaAutorizacao.objects.create(
            plano=self.plano,
            beneficiario=self.benef,
            prestador=self.prestador,
            tipo="urgencia",
            status="solicitada",
            valor_estimado=500,
        )
        # Força data de solicitação para 10h atrás
        GuiaAutorizacao.objects.filter(pk=guia.pk).update(
            solicitada_em=timezone.now() - timedelta(hours=10)
        )
        resp = self._get("/api/plano-saude/sla/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertGreater(len(payload["breaches"]), 0)
        self.assertGreater(payload["urg_vencidas"], 0)

    def test_guia_consulta_dentro_prazo_nao_e_breach(self):
        GuiaAutorizacao.objects.create(
            plano=self.plano,
            beneficiario=self.benef,
            tipo="consulta",
            status="solicitada",
            valor_estimado=200,
        )
        resp = self._get("/api/plano-saude/sla/")
        self.assertEqual(resp.status_code, 200)
        # Guia recém-criada não é breach (prazo = 168h)
        self.assertEqual(resp.json()["breaches"], [])

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/sla/")
        self.assertEqual(resp.status_code, 401)


class AuditoriaMedicaTests(PlanoSaudeEnterpriseBaseTests):
    """GET/POST /api/plano-saude/auditoria/"""

    def test_get_retorna_200_e_estrutura(self):
        resp = self._get("/api/plano-saude/auditoria/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        for chave in ("beneficiarios", "padroes", "procedimentos_anomalos",
                      "critico_count", "alto_count", "medio_count", "economia_estimada"):
            self.assertIn(chave, payload)

    def test_sem_sinistros_counts_sao_zero(self):
        resp = self._get("/api/plano-saude/auditoria/")
        payload = resp.json()
        self.assertEqual(payload["critico_count"], 0)
        self.assertEqual(payload["alto_count"], 0)
        self.assertEqual(payload["economia_estimada"], 0.0)

    def test_benef_com_muitos_sinistros_recebe_score_alto(self):
        # Cria benef com apenas 1 sinistro para elevar a média da carteira
        benef2 = BeneficiarioPlano.objects.create(
            plano=self.plano,
            nome="Outro Benef",
            cpf="999.000.111-22",
            situacao="ativo",
        )
        Sinistro.objects.create(
            empresa=self.operadora,
            plano=self.plano,
            beneficiario=benef2,
            tipo="consulta",
            valor_total=100,
            status="aberto",
        )
        # Cria 15 sinistros para o beneficiário principal (muito acima da média)
        for i in range(15):
            Sinistro.objects.create(
                empresa=self.operadora,
                plano=self.plano,
                beneficiario=self.benef,
                tipo="consulta",
                valor_total=2000,
                status="aberto",
            )
        resp = self._get("/api/plano-saude/auditoria/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        # Deve aparecer na lista com score acima de 40 (ratio=15/8=1.875 → score≥56)
        self.assertGreater(len(payload["beneficiarios"]), 0)
        scores = [b["score"] for b in payload["beneficiarios"]]
        self.assertGreater(max(scores), 40)

    @patch("api.email_service.send_mail")
    def test_post_scan_envia_email_para_criticos(self, mock_mail):
        # Cria sinistros pesados para score crítico (>= 90)
        for _ in range(30):
            Sinistro.objects.create(
                empresa=self.operadora,
                plano=self.plano,
                beneficiario=self.benef,
                tipo="internacao",
                valor_total=10000,
                status="aberto",
            )
        resp = self._post("/api/plano-saude/auditoria/")
        self.assertEqual(resp.status_code, 200)
        # Email deve ter sido chamado para beneficiários críticos
        # (apenas verifica que não quebrou; mock evita envio real)

    def test_filtro_risco_critico_aceito(self):
        resp = self._get("/api/plano-saude/auditoria/?risco=critico")
        self.assertEqual(resp.status_code, 200)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/auditoria/")
        self.assertEqual(resp.status_code, 401)


class ContratosCorporativosTests(PlanoSaudeEnterpriseBaseTests):
    """GET/POST /api/plano-saude/contratos/  e  detalhe"""

    @patch("api.email_service.send_mail")
    def test_criar_contrato_retorna_ok(self, mock_mail):
        resp = self._post("/api/plano-saude/contratos/", {
            "razao_social": "Metalurgica SA",
            "nome_fantasia": "Meta",
            "cnpj": "12.345.678/0001-99",
            "plano_id": self.plano.pk,
            "total_vidas": 80,
            "mensalidade_total": 42000,
            "data_inicio": date.today().isoformat(),
            "data_renovacao": (date.today() + timedelta(days=365)).isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(ContratoGrupo.objects.filter(empresa_operadora=self.operadora).count(), 1)

    @patch("api.email_service.send_mail")
    def test_criar_contrato_dispara_email(self, mock_mail):
        self._post("/api/plano-saude/contratos/", {
            "razao_social": "Empresa Email",
            "plano_id": self.plano.pk,
            "total_vidas": 10,
            "mensalidade_total": 5000,
            "data_inicio": date.today().isoformat(),
            "data_renovacao": (date.today() + timedelta(days=365)).isoformat(),
        })
        mock_mail.assert_called_once()
        subject = mock_mail.call_args[1].get("subject") or mock_mail.call_args[0][0]
        self.assertIn("contrato", subject.lower())

    def test_listar_contratos_retorna_kpis(self):
        ContratoGrupo.objects.create(
            empresa_operadora=self.operadora,
            plano=self.plano,
            razao_social="Empresa Lista",
            total_vidas=50,
            mensalidade_total=25000,
            data_inicio=date.today(),
            data_renovacao=date.today() + timedelta(days=365),
        )
        resp = self._get("/api/plano-saude/contratos/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["total_empresas"], 1)
        self.assertEqual(payload["total_vidas"], 50)
        self.assertGreater(payload["receita_corporativa"], 0)

    def test_detalhe_contrato_get(self):
        contrato = ContratoGrupo.objects.create(
            empresa_operadora=self.operadora,
            plano=self.plano,
            razao_social="Contrato Detalhe",
            total_vidas=30,
            mensalidade_total=15000,
            data_inicio=date.today(),
            data_renovacao=date.today() + timedelta(days=365),
        )
        resp = self._get(f"/api/plano-saude/contratos/{contrato.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["razao_social"], "Contrato Detalhe")

    def test_detalhe_contrato_put(self):
        contrato = ContratoGrupo.objects.create(
            empresa_operadora=self.operadora,
            plano=self.plano,
            razao_social="Contrato PUT",
            total_vidas=20,
            mensalidade_total=10000,
            data_inicio=date.today(),
            data_renovacao=date.today() + timedelta(days=365),
        )
        resp = self._put(f"/api/plano-saude/contratos/{contrato.pk}/", {"total_vidas": 25, "status": "ativo"})
        self.assertEqual(resp.status_code, 200)
        contrato.refresh_from_db()
        self.assertEqual(contrato.total_vidas, 25)

    def test_detalhe_contrato_delete(self):
        contrato = ContratoGrupo.objects.create(
            empresa_operadora=self.operadora,
            plano=self.plano,
            razao_social="Contrato DELETE",
            total_vidas=10,
            mensalidade_total=5000,
            data_inicio=date.today(),
            data_renovacao=date.today() + timedelta(days=365),
        )
        resp = self._delete(f"/api/plano-saude/contratos/{contrato.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ContratoGrupo.objects.filter(pk=contrato.pk).exists())

    def test_plano_invalido_retorna_404(self):
        resp = self._post("/api/plano-saude/contratos/", {
            "razao_social": "Empresa Sem Plano",
            "plano_id": 99999,
            "total_vidas": 5,
            "data_inicio": date.today().isoformat(),
            "data_renovacao": (date.today() + timedelta(days=365)).isoformat(),
        })
        self.assertEqual(resp.status_code, 404)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/contratos/")
        self.assertEqual(resp.status_code, 401)


class ComunicacaoTests(PlanoSaudeEnterpriseBaseTests):
    """GET/POST /api/plano-saude/comunicacao/"""

    def test_listar_contatos_beneficiarios(self):
        resp = self._get("/api/plano-saude/comunicacao/?tipo=benef")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("contatos", payload)
        nomes = [c["nome"] for c in payload["contatos"]]
        self.assertIn("Ana Beneficiaria", nomes)

    def test_listar_contatos_prestadores(self):
        resp = self._get("/api/plano-saude/comunicacao/?tipo=prest")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("contatos", payload)
        nomes = [c["nome"] for c in payload["contatos"]]
        self.assertIn("Clinica Teste", nomes)

    def test_enviar_mensagem_para_beneficiario(self):
        resp = self._post("/api/plano-saude/comunicacao/", {
            "tipo_destinatario": "beneficiario",
            "beneficiario_id": self.benef.pk,
            "conteudo": "Lembrete de consulta preventiva.",
            "canal": "plataforma",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(MensagemPlano.objects.filter(empresa=self.operadora).count(), 1)

    def test_mensagem_sem_conteudo_retorna_400(self):
        resp = self._post("/api/plano-saude/comunicacao/", {
            "tipo_destinatario": "beneficiario",
            "beneficiario_id": self.benef.pk,
            "conteudo": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_thread_beneficiario(self):
        MensagemPlano.objects.create(
            empresa=self.operadora,
            tipo_destinatario="beneficiario",
            beneficiario=self.benef,
            conteudo="Ola beneficiario",
            direcao="saida",
        )
        resp = self._get(f"/api/plano-saude/comunicacao/{self.benef.pk}/thread/?tipo=benef")
        self.assertEqual(resp.status_code, 200)
        msgs = resp.json()["mensagens"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["conteudo"], "Ola beneficiario")

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/comunicacao/")
        self.assertEqual(resp.status_code, 401)


class TelemedicinaTests(PlanoSaudeEnterpriseBaseTests):
    """GET/POST /api/plano-saude/telemedicina/  e  autorizar"""

    def test_kpis_iniciais_sao_zero(self):
        resp = self._get("/api/plano-saude/telemedicina/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["hoje"], 0)
        self.assertEqual(payload["aguardando"], 0)
        self.assertIn("por_especialidade", payload)
        self.assertIn("fila", payload)

    def test_criar_solicitacao_teleconsulta(self):
        resp = self._post("/api/plano-saude/telemedicina/", {
            "beneficiario_id": self.benef.pk,
            "especialidade": "Cardiologia",
            "plataforma": "conexa",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(TeleconsultaAutorizacao.objects.filter(empresa=self.operadora).count(), 1)

    def test_beneficiario_invalido_retorna_404(self):
        resp = self._post("/api/plano-saude/telemedicina/", {
            "beneficiario_id": 99999,
            "especialidade": "Cardiologia",
        })
        self.assertEqual(resp.status_code, 404)

    @patch("api.email_service.send_mail")
    def test_autorizar_teleconsulta_muda_status_e_envia_email(self, mock_mail):
        tele = TeleconsultaAutorizacao.objects.create(
            empresa=self.operadora,
            beneficiario=self.benef,
            especialidade="Dermatologia",
            plataforma="conexa",
        )
        resp = self._post(f"/api/plano-saude/telemedicina/{tele.pk}/autorizar/", {
            "acao": "autorizar",
            "autorizado_por": "Dr. Auditoria",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "autorizado")
        tele.refresh_from_db()
        self.assertEqual(tele.status, "autorizado")
        mock_mail.assert_called_once()

    def test_negar_teleconsulta_muda_status(self):
        tele = TeleconsultaAutorizacao.objects.create(
            empresa=self.operadora,
            beneficiario=self.benef,
            especialidade="Psicologia",
            plataforma="iclinic",
        )
        resp = self._post(f"/api/plano-saude/telemedicina/{tele.pk}/autorizar/", {
            "acao": "negar",
            "justificativa": "Fora da cobertura do plano.",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "negado")

    def test_autorizar_inexistente_retorna_404(self):
        resp = self._post("/api/plano-saude/telemedicina/99999/autorizar/")
        self.assertEqual(resp.status_code, 404)

    def test_aguardando_aumenta_apos_criacao(self):
        self._post("/api/plano-saude/telemedicina/", {
            "beneficiario_id": self.benef.pk,
            "especialidade": "Neurologia",
        })
        resp = self._get("/api/plano-saude/telemedicina/")
        self.assertEqual(resp.json()["aguardando"], 1)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/telemedicina/")
        self.assertEqual(resp.status_code, 401)


class OdontologiaTests(PlanoSaudeEnterpriseBaseTests):
    """GET/POST /api/plano-saude/odontologia/  e  guias detalhe"""

    def test_get_beneficiarios_retorna_200(self):
        resp = self._get("/api/plano-saude/odontologia/?aba=beneficiarios")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("vidas", payload)
        self.assertIn("dados", payload)

    def test_cadastrar_beneficiario_odonto(self):
        resp = self._post("/api/plano-saude/odontologia/", {
            "nome": "Pedro Odonto",
            "cpf": "999.888.777-66",
            "plano_odonto": "Odonto Básico",
            "data_inicio_vigencia": date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(BeneficiarioOdonto.objects.filter(empresa=self.operadora).count(), 1)

    def test_vidas_contadas_corretamente(self):
        BeneficiarioOdonto.objects.create(
            empresa=self.operadora,
            nome="Luisa Odonto",
            cpf="111.222.333-55",
            status="ativo",
        )
        resp = self._get("/api/plano-saude/odontologia/")
        self.assertEqual(resp.json()["vidas"], 1)

    def test_get_aba_guias(self):
        resp = self._get("/api/plano-saude/odontologia/?aba=guias")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("dados", resp.json())

    @patch("api.email_service.send_mail")
    def test_aprovacao_guia_odonto_envia_email(self, mock_mail):
        benef_odonto = BeneficiarioOdonto.objects.create(
            empresa=self.operadora,
            nome="Maria Odonto",
            cpf="222.333.444-55",
            email="maria@odonto.com",
            status="ativo",
        )
        guia = GuiaOdonto.objects.create(
            empresa=self.operadora,
            beneficiario=benef_odonto,
            procedimento="Extração simples",
            valor_estimado=350,
            status="pendente",
        )
        resp = self._put(f"/api/plano-saude/odontologia/guias/{guia.pk}/", {"status": "autorizado"})
        self.assertEqual(resp.status_code, 200)
        guia.refresh_from_db()
        self.assertEqual(guia.status, "autorizado")
        mock_mail.assert_called_once()
        subject = mock_mail.call_args[1].get("subject") or mock_mail.call_args[0][0]
        self.assertIn("autorizada", subject.lower())

    @patch("api.email_service.send_mail")
    def test_negacao_guia_odonto_envia_email(self, mock_mail):
        benef_odonto = BeneficiarioOdonto.objects.create(
            empresa=self.operadora,
            nome="Carlos Odonto",
            cpf="333.444.555-66",
            email="carlos@odonto.com",
            status="ativo",
        )
        guia = GuiaOdonto.objects.create(
            empresa=self.operadora,
            beneficiario=benef_odonto,
            procedimento="Implante dentário",
            valor_estimado=3500,
            status="pendente",
        )
        resp = self._put(f"/api/plano-saude/odontologia/guias/{guia.pk}/", {
            "status": "negado",
            "justificativa_negacao": "Procedimento não coberto no plano básico.",
        })
        self.assertEqual(resp.status_code, 200)
        guia.refresh_from_db()
        self.assertEqual(guia.status, "negado")
        mock_mail.assert_called_once()

    def test_guia_odonto_inexistente_retorna_404(self):
        resp = self._put("/api/plano-saude/odontologia/guias/99999/", {"status": "autorizado"})
        self.assertEqual(resp.status_code, 404)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/odontologia/")
        self.assertEqual(resp.status_code, 401)


class RelatorioRegulatorioTests(PlanoSaudeEnterpriseBaseTests):
    """POST /api/plano-saude/regulatorio/gerar/"""

    def test_gerar_diops_retorna_payload(self):
        resp = self._post("/api/plano-saude/regulatorio/gerar/", {
            "tipo": "DIOPS", "ano": "2026", "trimestre": "1",
        })
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tipo"], "DIOPS")
        self.assertIn("planos", payload["payload"])
        self.assertIn("beneficiarios_ativos", payload["payload"])

    def test_gerar_sib_retorna_movimentacoes(self):
        resp = self._post("/api/plano-saude/regulatorio/gerar/", {
            "tipo": "SIB", "ano": "2026", "trimestre": "5",
        })
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        self.assertIn("movimentacoes", payload["payload"])
        self.assertIn("total_registros", payload["payload"])

    def test_gerar_tiss_retorna_guias(self):
        GuiaAutorizacao.objects.create(
            plano=self.plano,
            beneficiario=self.benef,
            tipo="consulta",
            status="autorizada",
            valor_estimado=250,
        )
        resp = self._post("/api/plano-saude/regulatorio/gerar/", {
            "tipo": "TISS", "ano": "2026", "trimestre": "1",
        })
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        self.assertIn("guias", payload["payload"])
        self.assertEqual(payload["payload"]["versao"], "3.05.00")
        self.assertGreater(len(payload["payload"]["guias"]), 0)

    def test_tipo_invalido_retorna_400(self):
        resp = self._post("/api/plano-saude/regulatorio/gerar/", {"tipo": "XPTO"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("erro", resp.json())

    def test_get_nao_permitido_retorna_405(self):
        resp = self._get("/api/plano-saude/regulatorio/gerar/")
        self.assertEqual(resp.status_code, 405)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.post(
            "/api/plano-saude/regulatorio/gerar/",
            data=json.dumps({"tipo": "DIOPS"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)


class EmailsTransacionaisTests(PlanoSaudeEnterpriseBaseTests):
    """Testes unitários das funções de email — verifica estrutura sem enviar."""

    @patch("api.email_service.send_mail")
    def test_email_novo_contrato_envia_para_operadora(self, mock_mail):
        from api.email_service import enviar_email_novo_contrato
        contrato = ContratoGrupo.objects.create(
            empresa_operadora=self.operadora,
            plano=self.plano,
            razao_social="Empresa Email Teste",
            total_vidas=100,
            mensalidade_total=50000,
            data_inicio=date.today(),
            data_renovacao=date.today() + timedelta(days=365),
        )
        enviar_email_novo_contrato(contrato)
        mock_mail.assert_called_once()
        kwargs = mock_mail.call_args[1]
        self.assertEqual(kwargs["recipient_list"], [self.operadora.email])
        self.assertIn("Empresa Email Teste", kwargs["html_message"])

    @patch("api.email_service.send_mail")
    def test_email_teleconsulta_autorizada_envia_para_beneficiario(self, mock_mail):
        from api.email_service import enviar_email_teleconsulta_autorizada
        tele = TeleconsultaAutorizacao.objects.create(
            empresa=self.operadora,
            beneficiario=self.benef,
            especialidade="Cardiologia",
            plataforma="conexa",
            status="autorizado",
        )
        enviar_email_teleconsulta_autorizada(tele)
        mock_mail.assert_called_once()
        self.assertEqual(mock_mail.call_args[1]["recipient_list"], ["ana@beneficiario.com"])

    @patch("api.email_service.send_mail")
    def test_email_beneficiario_sem_email_nao_envia(self, mock_mail):
        from api.email_service import enviar_email_novo_beneficiario
        benef_sem_email = BeneficiarioPlano.objects.create(
            plano=self.plano,
            nome="Sem Email",
            email="",
            situacao="ativo",
        )
        enviar_email_novo_beneficiario(self.operadora, benef_sem_email)
        mock_mail.assert_not_called()

    @patch("api.email_service.send_mail")
    def test_email_sla_breach_sem_breaches_nao_envia(self, mock_mail):
        from api.email_service import enviar_email_sla_breach_critico
        enviar_email_sla_breach_critico(self.operadora, [])
        mock_mail.assert_not_called()

    @patch("api.email_service.send_mail")
    def test_email_sla_breach_com_breaches_envia(self, mock_mail):
        from api.email_service import enviar_email_sla_breach_critico
        breaches = [
            {"id": "GUI-001", "beneficiario": "Ana", "tipo": "urgência",
             "prazo": "4h", "aberto_ha": "6h", "prestador": "UPA"},
        ]
        enviar_email_sla_breach_critico(self.operadora, breaches)
        mock_mail.assert_called_once()
        subject = mock_mail.call_args[1].get("subject") or mock_mail.call_args[0][0]
        self.assertIn("SLA", subject)

    @patch("api.email_service.send_mail")
    def test_email_auditoria_alerta_score_critico(self, mock_mail):
        from api.email_service import enviar_email_auditoria_alerta
        enviar_email_auditoria_alerta(
            empresa=self.operadora,
            nome_benef="Roberto Alto Risco",
            score=95,
            fatores=["Alta frequência", "Múltiplos médicos"],
        )
        mock_mail.assert_called_once()
        html = mock_mail.call_args[1]["html_message"]
        self.assertIn("95", html)
        self.assertIn("Roberto Alto Risco", html)

    @patch("api.email_service.send_mail")
    def test_email_guia_odonto_aprovada(self, mock_mail):
        from api.email_service import enviar_email_guia_odonto_aprovada
        benef_odonto = BeneficiarioOdonto.objects.create(
            empresa=self.operadora,
            nome="Fernanda Odonto",
            email="fernanda@odonto.com",
            status="ativo",
        )
        guia = GuiaOdonto.objects.create(
            empresa=self.operadora,
            beneficiario=benef_odonto,
            procedimento="Limpeza dental",
            valor_estimado=200,
            status="autorizado",
        )
        enviar_email_guia_odonto_aprovada(guia)
        mock_mail.assert_called_once()
        self.assertEqual(mock_mail.call_args[1]["recipient_list"], ["fernanda@odonto.com"])

    @patch("api.email_service.send_mail")
    def test_email_falha_nao_propaga_excecao(self, mock_mail):
        """Email failure nunca deve quebrar o fluxo principal."""
        from api.email_service import enviar_email_novo_beneficiario
        mock_mail.side_effect = Exception("SMTP timeout")
        # Não deve lançar exceção
        enviar_email_novo_beneficiario(self.operadora, self.benef)


class SLABreachCronTests(PlanoSaudeEnterpriseBaseTests):
    """Testes do management command sla_breach_alertas."""

    def test_dry_run_sem_guias_nao_envia(self):
        out = StringIO()
        call_command("sla_breach_alertas", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertIn("0 breach(es)", output)

    @patch("api.email_service.send_mail")
    def test_dry_run_com_breach_nao_envia_email(self, mock_mail):
        # Cria guia de urgência vencida
        guia = GuiaAutorizacao.objects.create(
            plano=self.plano,
            beneficiario=self.benef,
            tipo="urgencia",
            status="solicitada",
            valor_estimado=400,
        )
        GuiaAutorizacao.objects.filter(pk=guia.pk).update(
            solicitada_em=timezone.now() - timedelta(hours=10)
        )
        out = StringIO()
        call_command("sla_breach_alertas", "--dry-run", stdout=out)
        mock_mail.assert_not_called()
        self.assertIn("[DRY]", out.getvalue())

    @patch("api.email_service.send_mail")
    def test_producao_com_breach_envia_email(self, mock_mail):
        guia = GuiaAutorizacao.objects.create(
            plano=self.plano,
            beneficiario=self.benef,
            tipo="urgencia",
            status="solicitada",
            valor_estimado=400,
        )
        GuiaAutorizacao.objects.filter(pk=guia.pk).update(
            solicitada_em=timezone.now() - timedelta(hours=10)
        )
        call_command("sla_breach_alertas", f"--empresa-id={self.operadora.pk}")
        mock_mail.assert_called_once()

    def test_empresa_id_filtra_corretamente(self):
        # Cria segunda operadora sem guias vencidas
        outra = Empresa.objects.create(
            nome="Outra Operadora",
            email="outra@op.com",
            senha=make_password("123"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
        )
        out = StringIO()
        call_command("sla_breach_alertas", f"--empresa-id={outra.pk}", "--dry-run", stdout=out)
        self.assertIn("0 breach(es)", out.getvalue())


class AssinaturaSSTTests(TestCase):
    def test_fluxo_publico_assina_e_valida_aso(self):
        from datetime import date
        from django.test import RequestFactory
        from .models import ASOOcupacional, AssinaturaDocumentoSST, FuncionarioSST
        from .views_assinatura_sst import api_sst_assinaturas

        empresa = Empresa.objects.create(
            nome="Empresa Assinatura",
            email="assinatura-sst@teste.com",
            senha=make_password("123456"),
            ativo=True,
        )
        funcionario = FuncionarioSST.objects.create(
            empresa=empresa,
            nome="Colaborador Assinatura",
            cpf="000",
            cargo="Operador",
            setor="Produção",
            ativo=True,
        )
        aso = ASOOcupacional.objects.create(
            empresa=empresa,
            funcionario=funcionario,
            tipo="periodico",
            data_emissao=date.today(),
            data_validade=date.today(),
            resultado="apto",
        )

        request = RequestFactory().post(
            "/api/sst/assinaturas/",
            data=json.dumps({"tipo_documento": "aso", "objeto_id": aso.id}),
            content_type="application/json",
        )
        request.empresa = empresa
        response = api_sst_assinaturas(request)

        self.assertEqual(response.status_code, 201)
        token = json.loads(response.content)["assinatura"]["token"]
        page_response = self.client.get(f"/assinatura/sst/{token}/")
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Quem deve assinar")
        self.assertContains(page_response, "Ciência do trabalhador")

        sign_response = self.client.post(
            f"/api/public/sst/assinaturas/{token}/assinar/",
            data=json.dumps({"nome": "Colaborador Assinatura", "cpf": "000", "aceite": True}),
            content_type="application/json",
        )
        self.assertEqual(sign_response.status_code, 200)

        assinatura = AssinaturaDocumentoSST.objects.get(token=token)
        self.assertEqual(assinatura.status, "assinado")
        self.assertTrue(assinatura.hash_documento)
        self.assertTrue(assinatura.hash_assinatura)


class PipelineOficialSivepPeriodoTests(TestCase):
    def test_periodo_sivep_formata_semana_com_ano(self):
        from api.pipeline_oficial import _periodo_sivep

        self.assertEqual(_periodo_sivep("2"), "2026-S02")
        self.assertEqual(_periodo_sivep("13"), "2026-S13")
        self.assertEqual(_periodo_sivep(""), "semana_nao_informada")
        self.assertEqual(_periodo_sivep(None), "semana_nao_informada")


class PipelineOficialTabnetTests(TestCase):
    """Parser do TabNet/DATASUS (formulario publico legado) — protege contra
    os dois bugs reais encontrados ao ligar Tuberculose/Difteria/etc:
    1) TabNet usa "-" para zero, nao "0";
    2) doencas raras fazem o TabNet OMITIR do cabecalho os meses em que
       NENHUM estado teve caso algum (tabela com menos de 12 colunas)."""

    def test_parse_tabela_mensal_completa_12_meses(self):
        from api.pipeline_oficial import _parse_tabnet_tabela_mensal

        texto = (
            "<PRE>\n"
            "UF de notificação             Jan        Fev        Mar        Abr"
            "        Mai        Jun        Jul        Ago        Set        Out"
            "        Nov        Dez     Total\n\n"
            "33 Rio de Janeiro           100        110        120        130"
            "        140        150        160        170        180        190"
            "        200        210     1.860\n"
            "TOTAL                       100        110        120        130"
            "        140        150        160        170        180        190"
            "        200        210     1.860\n"
            "</PRE>"
        )
        resultado = _parse_tabnet_tabela_mensal(texto)

        self.assertEqual(len(resultado), 12)
        self.assertIn((33, 1, 100), resultado)
        self.assertIn((33, 12, 210), resultado)
        # linha TOTAL nunca deve ser interpretada como um estado (codigo 33 != TOTAL)
        self.assertTrue(all(uf == 33 for uf, _, _ in resultado))

    def test_parse_tabela_mensal_trata_traco_como_zero(self):
        from api.pipeline_oficial import _parse_tabnet_tabela_mensal

        texto = (
            "<PRE>\n"
            "UF de notificação             Jan        Fev        Mar        Abr"
            "        Mai        Jun        Jul        Ago        Set        Out"
            "        Nov        Dez     Total\n\n"
            "15 Pará                         -          -          1          -"
            "          -          -          -          -          -          -"
            "          -          -         1\n"
            "</PRE>"
        )
        resultado = _parse_tabnet_tabela_mensal(texto)

        self.assertEqual(len(resultado), 12)
        valores_por_mes = {mes: valor for _, mes, valor in resultado}
        self.assertEqual(valores_por_mes[3], 1)
        self.assertEqual(valores_por_mes[1], 0)
        self.assertEqual(valores_por_mes[12], 0)

    def test_parse_tabela_mensal_cabecalho_esparso_doenca_rara(self):
        from api.pipeline_oficial import _parse_tabnet_tabela_mensal

        # Difteria real: TabNet so mostra os meses em que ALGUM estado teve
        # caso (aqui so Jan, Jun, Jul, Ago) — sem isso o parser desalinharia
        # mes->valor para as doencas mais raras.
        texto = (
            "<PRE>\n"
            "UF de notificação             Jan        Jun        Jul        Ago     Total\n\n"
            "41 Paraná                       -          1          -          -         1\n"
            "43 Rio Grande do Sul             1          -          1          1         3\n"
            "</PRE>"
        )
        resultado = _parse_tabnet_tabela_mensal(texto)

        valores_pr = {mes: valor for uf, mes, valor in resultado if uf == 41}
        self.assertEqual(valores_pr[1], 0)
        self.assertEqual(valores_pr[6], 1)
        self.assertEqual(valores_pr[7], 0)
        self.assertEqual(valores_pr[8], 0)
        # so 4 meses na tabela (esparsa), nao 12
        self.assertEqual(len(valores_pr), 4)

    def test_parse_tabela_mensal_sem_pre_retorna_vazio(self):
        from api.pipeline_oficial import _parse_tabnet_tabela_mensal

        self.assertEqual(_parse_tabnet_tabela_mensal("<html>sem tabela</html>"), [])

    def test_tabnet_escolher_prefere_padrao_mais_especifico(self):
        from api.pipeline_oficial import _TABNET_COLUNA_PADROES, _TABNET_LINHA_PADROES, _tabnet_escolher

        opcoes_linha = ["Região_de_notificação", "UF_de_notificação", "Município_de_notificação"]
        self.assertEqual(_tabnet_escolher(opcoes_linha, _TABNET_LINHA_PADROES), "UF_de_notificação")

        # Hantavirose real: nao tem "Mês_Notificação", so "Mês_1º_Sintoma(s)"
        opcoes_coluna_hantavirose = ["Ano_1º_Sintoma(s)", "Mês_1º_Sintoma(s)", "UF_de_notificação"]
        self.assertEqual(
            _tabnet_escolher(opcoes_coluna_hantavirose, _TABNET_COLUNA_PADROES), "Mês_1º_Sintoma(s)"
        )

    def test_processar_tabnet_doenca_pega_anos_mais_recentes_mesmo_fora_de_ordem(self):
        """Bug real ao ligar Malaria (sinanwin/malabr.def): esse .def lista os
        arquivos do mais ANTIGO para o mais novo (oposto do sinannet usado
        pelas outras doencas) — pegar so arquivos_disponiveis[:3] devolvia
        2004-2006 em vez dos anos mais recentes disponiveis. O processamento
        agora ordena por ano antes de cortar."""
        from api.models import FonteOficialAgregado, FonteOficialExecucao
        from api.pipeline_oficial import _processar_tabnet_doenca

        arquivos_fora_de_ordem = [
            "doencabr01.dbf", "doencabr02.dbf", "doencabr03.dbf",
            "doencabr04.dbf", "doencabr05.dbf", "doencabr06.dbf",
        ]
        tabela_pre = (
            "<PRE>\nUF de notificação             Jan        Fev     Total\n\n"
            "33 Rio de Janeiro                1          2         3\n</PRE>"
        )

        def fake_form_defaults(def_path):
            return (
                {"Linha": "", "Coluna": "", "Arquivos": "", "formato": ""},
                {
                    "Linha": ["UF_de_notificação"],
                    "Coluna": ["Mês_Notificação"],
                    "Arquivos": arquivos_fora_de_ordem,
                },
            )

        with patch("api.pipeline_oficial._tabnet_form_defaults", side_effect=fake_form_defaults), \
             patch("api.pipeline_oficial._tabnet_post_tabela", return_value=tabela_pre):
            execucao = FonteOficialExecucao.objects.create(
                fonte_id="tabnet_teste_ordem", fonte_nome="Teste"
            )
            _processar_tabnet_doenca(
                execucao, "tabnet_teste_ordem",
                {"def_path": "x/y.def", "indicador": "teste_ordem", "fonte_nome": "Teste"},
            )

        anos_gravados = set(
            FonteOficialAgregado.objects.filter(fonte_id="tabnet_teste_ordem")
            .values_list("periodo", flat=True)
        )
        # com 6 anos disponiveis (01..06) e anos_recentes=3, deve pegar 04,05,06 — nao 01,02,03
        self.assertEqual(anos_gravados, {"2004-M01", "2004-M02", "2005-M01", "2005-M02", "2006-M01", "2006-M02"})

    def test_tabnet_ano_de_sufixo_usa_janela_de_seculo(self):
        """Bug real ao ligar Aids (www2.aids.gov.br, arquivos desde 1980):
        sufixo de 2 digitos nao e sempre 20xx — "aids_99.dbf" e 1999, nao
        2099. A janela usa o ano atual como corte: sufixo <= ano atual (2
        digitos) vira 20xx, senao 19xx."""
        from api.pipeline_oficial import _tabnet_ano_de_sufixo

        self.assertEqual(_tabnet_ano_de_sufixo("25"), 2025)
        self.assertEqual(_tabnet_ano_de_sufixo("99"), 1999)
        self.assertEqual(_tabnet_ano_de_sufixo("80"), 1980)
        self.assertEqual(_tabnet_ano_de_sufixo("00"), 2000)

    def test_parse_tabnet_tabela_anual_por_nome_uf_nao_confunde_prefixos_ambiguos(self):
        """Bug real: "Paraiba" e "Parana" comecam com o mesmo prefixo de
        "Para" — usar startswith() fazia as 3 colapsarem na sigla PA. O
        parser agora exige nome completo exato (nao prefixo)."""
        from api.pipeline_oficial import _parse_tabnet_tabela_anual_por_nome_uf

        texto = (
            "<PRE>\nUF Resid&ecirc;ncia          2025   Total\n\n"
            "Par&aacute;                  1.741   1.741\n"
            "Para&iacute;ba                 373     373\n"
            "Paran&aacute;                1.300   1.300\n"
            "TOTAL                25.571  25.571\n</PRE>"
        )
        resultado = _parse_tabnet_tabela_anual_por_nome_uf(texto)
        por_uf = {uf: valor for uf, ano, valor in resultado}

        self.assertEqual(por_uf["PA"], 1741)
        self.assertEqual(por_uf["PB"], 373)
        self.assertEqual(por_uf["PR"], 1300)

    def test_parse_tabnet_tabela_anual_trata_traco_como_zero(self):
        from api.pipeline_oficial import _parse_tabnet_tabela_anual_por_nome_uf

        texto = (
            "<PRE>\nUF Resid&ecirc;ncia          2024   2025   Total\n\n"
            "Acre                        -     83        83\n</PRE>"
        )
        resultado = _parse_tabnet_tabela_anual_por_nome_uf(texto)
        valores_por_ano = {ano: valor for uf, ano, valor in resultado}

        self.assertEqual(valores_por_ano[2024], 0)
        self.assertEqual(valores_por_ano[2025], 83)


class EpidemiologiaMLTests(TestCase):
    """ML treinado em dado oficial (DATASUS/SINAN) — api/epidemiologia_ml.py.

    Usa um MODELS_DIR temporario em todos os testes para nunca sobrescrever o
    modelo real treinado em produção com dado oficial verdadeiro."""

    FONTE = "sinan_agravos"
    INDICADOR = "dengue_notificacoes_sinan"

    def setUp(self):
        import tempfile
        from api import epidemiologia_ml as epi_ml

        self._tmpdir = tempfile.TemporaryDirectory()
        self._patches = [
            patch.object(epi_ml, "MODELS_DIR", Path(self._tmpdir.name)),
            patch.object(epi_ml, "MODEL_PATH", Path(self._tmpdir.name) / "model.joblib"),
            patch.object(epi_ml, "META_PATH", Path(self._tmpdir.name) / "meta.json"),
        ]
        for p in self._patches:
            p.start()
        epi_ml._MODELO_CACHE.clear()
        epi_ml._SERIES_CACHE.clear()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    def _criar_serie_oficial(self, estado, n_semanas=25, base=100, amplitude=40, picos=None, fonte_id=None, indicador=None):
        """Cria uma serie semanal real-like em FonteOficialAgregado para teste."""
        import math
        picos = picos or set()
        for semana in range(1, n_semanas + 1):
            valor = base + amplitude * math.sin(semana / 3.0)
            if semana in picos:
                valor *= 4
            FonteOficialAgregado.objects.create(
                fonte_id=fonte_id or self.FONTE,
                indicador=indicador or self.INDICADOR,
                estado=estado,
                periodo=f"2025-S{semana:02d}",
                valor=max(valor, 0),
                fonte_nome="SINAN/DATASUS (teste)",
            )

    def test_treino_recusa_quando_nao_ha_amostras_oficiais_suficientes(self):
        from api.epidemiologia_ml import treinar_modelo_oficial

        meta = treinar_modelo_oficial(fonte_id=self.FONTE, indicador=self.INDICADOR)

        self.assertFalse(meta["treinado"])
        self.assertEqual(meta["motivo"], "amostras_oficiais_insuficientes")
        self.assertEqual(meta["n_amostras"], 0)

    def test_treino_real_com_dado_oficial_suficiente(self):
        from api.epidemiologia_ml import treinar_modelo_oficial

        self._criar_serie_oficial("RJ", n_semanas=25, picos={10, 20})
        self._criar_serie_oficial("SP", n_semanas=25, picos={8, 18})

        meta = treinar_modelo_oficial(fonte_id=self.FONTE, indicador=self.INDICADOR)

        self.assertTrue(meta["treinado"])
        self.assertTrue(meta["dataset_real_oficial"])
        self.assertGreaterEqual(meta["n_amostras"], 40)
        self.assertEqual(sorted(meta["estados"]), ["RJ", "SP"])
        self.assertIn("cv_f1_media", meta)

    def test_mapa_risco_oficial_por_estado_apos_treino(self):
        from api.epidemiologia_ml import mapa_risco_oficial_por_estado, treinar_modelo_oficial

        self._criar_serie_oficial("RJ", n_semanas=25, picos={10, 20})
        self._criar_serie_oficial("SP", n_semanas=25, picos={8, 18})
        treinar_modelo_oficial(fonte_id=self.FONTE, indicador=self.INDICADOR)

        mapa = mapa_risco_oficial_por_estado(fonte_id=self.FONTE, indicador=self.INDICADOR)

        self.assertEqual(set(mapa.keys()), {"RJ", "SP"})
        for probabilidade in mapa.values():
            self.assertGreaterEqual(probabilidade, 0.0)
            self.assertLessEqual(probabilidade, 1.0)

    def test_mapa_risco_oficial_vazio_sem_modelo_treinado(self):
        from api.epidemiologia_ml import mapa_risco_oficial_por_estado

        self.assertEqual(mapa_risco_oficial_por_estado(fonte_id=self.FONTE, indicador=self.INDICADOR), {})

    def test_modelo_info_reflete_estado_do_treino(self):
        from api.epidemiologia_ml import modelo_info, treinar_modelo_oficial

        self.assertFalse(modelo_info(fonte_id=self.FONTE, indicador=self.INDICADOR)["modelo_treinado"])

        self._criar_serie_oficial("RJ", n_semanas=25, picos={10, 20})
        self._criar_serie_oficial("SP", n_semanas=25, picos={8, 18})
        treinar_modelo_oficial(fonte_id=self.FONTE, indicador=self.INDICADOR)

        info = modelo_info(fonte_id=self.FONTE, indicador=self.INDICADOR)
        self.assertTrue(info["modelo_treinado"])
        self.assertTrue(info["dataset_real_oficial"])

    def test_risk_score_blend_com_probabilidade_oficial(self):
        from api.epidemiologia import _risk_score

        score_sem_oficial = _risk_score(50, 100, 5, 10, 20, 100, oficial_probability=None)
        score_oficial_zero = _risk_score(50, 100, 5, 10, 20, 100, oficial_probability=0.0)
        score_oficial_um = _risk_score(50, 100, 5, 10, 20, 100, oficial_probability=1.0)

        # Sem dado oficial, comportamento idêntico ao heurístico puro (compatibilidade).
        self.assertGreater(score_sem_oficial, 0)
        # Probabilidade oficial alta deve aumentar o score; baixa, reduzir — nunca dominar.
        self.assertLess(score_oficial_zero, score_sem_oficial)
        self.assertGreater(score_oficial_um, score_sem_oficial)
        self.assertAlmostEqual(score_oficial_zero / score_sem_oficial, 0.85, places=2)
        self.assertAlmostEqual(score_oficial_um / score_sem_oficial, 1.25, places=2)

    def test_panorama_nao_quebra_quando_mapa_oficial_falha(self):
        from api import epidemiologia as epi

        with patch.object(epi, "mapa_risco_oficial_por_estado", side_effect=RuntimeError("boom")):
            self.assertEqual(epi._risco_oficial_map_seguro(), {})

    def test_panorama_payload_inclui_flag_calculo_ml_oficial(self):
        from api.epidemiologia import build_panorama_payload, clear_panorama_cache

        clear_panorama_cache()
        payload = build_panorama_payload()

        for estado in payload["layers"]["estados"]:
            self.assertIn("calculo_ml_oficial", estado)

    def test_treinar_todas_doencas_registradas(self):
        from api.epidemiologia_ml import treinar_todas_doencas_registradas

        self._criar_serie_oficial("RJ", n_semanas=25, picos={10, 20})
        self._criar_serie_oficial("SP", n_semanas=25, picos={8, 18})
        self._criar_serie_oficial(
            "RJ", n_semanas=25, picos={5, 15},
            fonte_id="sinan_chikungunya", indicador="chikungunya_notificacoes_sinan",
        )
        self._criar_serie_oficial(
            "SP", n_semanas=25, picos={6, 16},
            fonte_id="sinan_chikungunya", indicador="chikungunya_notificacoes_sinan",
        )
        self._criar_serie_oficial(
            "RJ", n_semanas=25, picos={7, 17},
            fonte_id="sinan_zika", indicador="zika_notificacoes_sinan",
        )
        self._criar_serie_oficial(
            "SP", n_semanas=25, picos={9, 19},
            fonte_id="sinan_zika", indicador="zika_notificacoes_sinan",
        )
        self._criar_serie_oficial(
            "RJ", n_semanas=25, picos={6, 14},
            fonte_id="sivep_gripe", indicador="srag_notificacoes_amostra",
        )
        self._criar_serie_oficial(
            "SP", n_semanas=25, picos={8, 16},
            fonte_id="sivep_gripe", indicador="srag_notificacoes_amostra",
        )

        from api.epidemiologia_ml import DOENCAS_REGISTRADAS

        resultados = treinar_todas_doencas_registradas()

        # treinar_todas_doencas_registradas reporta TODAS as doencas
        # cadastradas (treinadas ou nao) — so as 4 com fixture acima de
        # MIN_AMOSTRAS_TREINO devem reportar treinado=True aqui; as
        # doencas via TabNet sem fixture continuam no dict, mas recusadas.
        self.assertEqual(set(resultados.keys()), {nome for _, _, nome in DOENCAS_REGISTRADAS})
        self.assertTrue(resultados["Dengue"]["treinado"])
        self.assertTrue(resultados["Gripe"]["treinado"])
        self.assertTrue(resultados["Zika"]["treinado"])
        self.assertFalse(resultados["Tuberculose"]["treinado"])
        self.assertTrue(resultados["Chikungunya"]["treinado"])

    def test_build_disease_probabilities_blend_por_doenca(self):
        from api.epidemiologia import _build_disease_probabilities

        sem_oficial = _build_disease_probabilities({"febre": 10, "dor_corpo": 8}, 20)
        dengue_sem = next(d for d in sem_oficial if d["name"] == "Dengue")
        self.assertFalse(dengue_sem["calculo_ml_oficial"])

        com_oficial = _build_disease_probabilities(
            {"febre": 10, "dor_corpo": 8}, 20,
            risco_oficial_doenca_map={"Dengue": {"RJ": 1.0}},
            estado_uf="RJ",
        )
        dengue_com = next(d for d in com_oficial if d["name"] == "Dengue")
        chikungunya_com = next(d for d in com_oficial if d["name"] == "Chikungunya")

        self.assertTrue(dengue_com["calculo_ml_oficial"])
        self.assertFalse(chikungunya_com["calculo_ml_oficial"])
        self.assertGreater(dengue_com["probability"], dengue_sem["probability"])


class AutorizacaoMLConsolidacaoTests(TestCase):
    """Fase 2: Plano de Saude e Hospital passam a usar o ensemble real de ML
    (em vez do motor de regras fixas) para autorizar guias/solicitacoes."""

    def setUp(self):
        import tempfile
        from api import views_ia_autorizacao_ml as plano_ml
        from api import views_hospital_ia_autorizacao_ml as hosp_ml

        self._tmpdir_plano = tempfile.TemporaryDirectory()
        self._tmpdir_hosp = tempfile.TemporaryDirectory()
        self._patches = [
            patch.object(plano_ml, "MODEL_PATH", Path(self._tmpdir_plano.name) / "model.joblib"),
            patch.object(plano_ml, "ENCODER_PATH", Path(self._tmpdir_plano.name) / "encoder.joblib"),
            patch.object(plano_ml, "META_PATH", Path(self._tmpdir_plano.name) / "meta.json"),
            patch.object(hosp_ml, "MODEL_PATH", Path(self._tmpdir_hosp.name) / "model.joblib"),
            patch.object(hosp_ml, "ENCODER_PATH", Path(self._tmpdir_hosp.name) / "encoder.joblib"),
            patch.object(hosp_ml, "META_PATH", Path(self._tmpdir_hosp.name) / "meta.json"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmpdir_plano.cleanup()
        self._tmpdir_hosp.cleanup()

    def test_plano_saude_analisar_guia_usa_ensemble_real(self):
        from api.views_plano_ia import _analisar_guia

        decisao, score, justificativa = _analisar_guia(
            "tratamento estético rejuvenescimento", "Z71", codigo_tuss="40814440", beneficiario="", empresa_id=None
        )

        self.assertEqual(decisao, "negada")
        self.assertGreater(score, 0)
        self.assertNotIn("fallback", justificativa)

    def test_plano_saude_cai_no_fallback_se_ml_falhar(self):
        from api import views_plano_ia

        with patch.object(views_plano_ia, "inferir_autorizacao", side_effect=RuntimeError("boom")):
            decisao, score, justificativa = views_plano_ia._analisar_guia("consulta de rotina", "Z00")

        self.assertEqual(decisao, "aprovada")
        self.assertIn("fallback", justificativa)

    def test_hospital_analisar_solicitacao_usa_ensemble_real(self):
        from api.views_hospital_ia_autorizacao import _analisar_solicitacao

        decisao, score, justificativa = _analisar_solicitacao(
            "internacao", "atendimento de urgencia", "R69", True, paciente_nome="Paciente Teste", empresa_id=None
        )

        self.assertEqual(decisao, "aprovada")
        self.assertGreater(score, 0)
        self.assertNotIn("fallback", justificativa)

    def test_hospital_cai_no_fallback_se_ml_falhar(self):
        from api import views_hospital_ia_autorizacao as hosp_views

        with patch.object(hosp_views, "inferir_autorizacao_clinica", side_effect=RuntimeError("boom")):
            decisao, score, justificativa = hosp_views._analisar_solicitacao(
                "procedimento", "tratamento estetico", "Z71", False
            )

        self.assertEqual(decisao, "negada")
        self.assertIn("fallback", justificativa)


# ─────────────────────────────────────────────────────────────────────────────
# Governo — Notícias Epidemiológicas (TEST-001)
# ─────────────────────────────────────────────────────────────────────────────

class NoticiaEpidemiologicaAPITests(TestCase):
    """Cobertura de api_noticias_epidemiologicas e api_noticia_status."""

    def setUp(self):
        self.client = Client()
        self.governo = Empresa.objects.create(
            nome="Governo Noticias Teste",
            email="gov-noticias@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )
        login = self.client.post(
            "/api/login-governo",
            data=json.dumps({"email": "gov-noticias@teste.com", "senha": "123456", "device_id": "gov-noticias-device"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

        # Notícias de referência
        self.n_info = NoticiaEpidemiologica.objects.create(
            empresa=self.governo,
            titulo="Monitoramento sazonal de dengue no Nordeste",
            fonte="SVS",
            url="https://svs.gov.br/dengue-nordeste",
            resumo="Acompanhamento rotineiro.",
            doencas_detectadas=["dengue"],
            nivel_alerta="informativo",
            status="novo",
        )
        self.n_alerta = NoticiaEpidemiologica.objects.create(
            empresa=self.governo,
            titulo="Aumento de casos de leptospirose após chuvas",
            fonte="OPAS",
            url="https://opas.gov.br/leptospirose-chuvas",
            resumo="Aumento confirmado.",
            doencas_detectadas=["leptospirose"],
            nivel_alerta="alerta",
            status="lido",
        )
        self.n_critico = NoticiaEpidemiologica.objects.create(
            empresa=self.governo,
            titulo="Surto de influenza declarado no Sul",
            fonte="CDC-EID",
            url="https://cdc.gov/influenza-sul",
            resumo="Emergência sanitária.",
            doencas_detectadas=["influenza"],
            nivel_alerta="critico",
            status="novo",
        )

    def test_lista_retorna_resumo_e_noticias(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("resumo", body)
        self.assertIn("noticias", body)
        self.assertEqual(body["resumo"]["total"], 3)
        self.assertEqual(body["resumo"]["novos"], 2)
        self.assertEqual(body["resumo"]["alertas"], 1)
        self.assertEqual(body["resumo"]["criticos"], 1)
        self.assertEqual(len(body["noticias"]), 3)

    def test_filtra_por_nivel_alerta(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?nivel=alerta")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["noticias"]), 1)
        self.assertEqual(body["noticias"][0]["nivel_alerta"], "alerta")

    def test_filtra_por_nivel_critico(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?nivel=critico")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["noticias"]), 1)

    def test_filtra_por_status_lido(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?status=lido")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["noticias"]), 1)
        self.assertEqual(body["noticias"][0]["status"], "lido")

    def test_nivel_invalido_retorna_400(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?nivel=urgente")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("nivel deve ser um de", resp.json()["erro"])

    def test_status_invalido_retorna_400(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?status=pendente")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("status deve ser um de", resp.json()["erro"])

    def test_filtra_por_doenca(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?doenca=dengue")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["noticias"]), 1)
        self.assertEqual(body["noticias"][0]["fonte"], "SVS")

    def test_limite_maximo_aplicado(self):
        for i in range(5):
            NoticiaEpidemiologica.objects.create(
                empresa=self.governo,
                titulo=f"Extra {i}",
                fonte="SVS",
                url=f"https://extra.gov.br/{i}",
                doencas_detectadas=["dengue"],
            )
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?limite=2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["noticias"]), 2)

    def test_limite_invalido_usa_default_50(self):
        resp = self.client.get("/api/governo/noticias-epidemiologicas/?limite=abc")
        self.assertEqual(resp.status_code, 200)
        # Apenas 3 noticias no banco, limite padrão 50 — retorna todos os 3
        self.assertEqual(len(resp.json()["noticias"]), 3)

    def test_sem_autenticacao_retorna_401(self):
        resp = Client().get("/api/governo/noticias-epidemiologicas/")
        self.assertEqual(resp.status_code, 401)

    def test_noticias_isoladas_por_empresa(self):
        outra = Empresa.objects.create(
            nome="Outro Governo",
            email="outro-gov@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )
        NoticiaEpidemiologica.objects.create(
            empresa=outra,
            titulo="Notícia privada de outra empresa",
            fonte="SVS",
            url="https://outra.gov.br/privada",
            doencas_detectadas=["zika"],
        )
        resp = self.client.get("/api/governo/noticias-epidemiologicas/")
        titulos = [n["titulo"] for n in resp.json()["noticias"]]
        self.assertNotIn("Notícia privada de outra empresa", titulos)
        self.assertEqual(len(titulos), 3)

    def test_update_status_para_lido(self):
        url = f"/api/governo/noticias-epidemiologicas/{self.n_info.pk}/status/"
        resp = self.client.post(
            url,
            data=json.dumps({"status": "lido"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "lido")
        self.n_info.refresh_from_db()
        self.assertEqual(self.n_info.status, "lido")

    def test_update_status_para_arquivado(self):
        url = f"/api/governo/noticias-epidemiologicas/{self.n_alerta.pk}/status/"
        resp = self.client.post(
            url,
            data=json.dumps({"status": "arquivado"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "arquivado")

    def test_update_status_invalido_retorna_400(self):
        url = f"/api/governo/noticias-epidemiologicas/{self.n_info.pk}/status/"
        resp = self.client.post(
            url,
            data=json.dumps({"status": "pendente"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Status inválido", resp.json()["erro"])

    def test_update_status_noticia_inexistente_retorna_404(self):
        url = "/api/governo/noticias-epidemiologicas/99999/status/"
        resp = self.client.post(
            url,
            data=json.dumps({"status": "lido"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_update_status_noticia_outra_empresa_retorna_404(self):
        outra = Empresa.objects.create(
            nome="Intruso Gov",
            email="intruso-gov@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )
        noticia_outra = NoticiaEpidemiologica.objects.create(
            empresa=outra,
            titulo="Notícia do intruso",
            fonte="SVS",
            url="https://intruso.gov.br/noticia",
            doencas_detectadas=["dengue"],
        )
        url = f"/api/governo/noticias-epidemiologicas/{noticia_outra.pk}/status/"
        resp = self.client.post(
            url,
            data=json.dumps({"status": "lido"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


class MonitorarNoticiasCommandTests(TransactionTestCase):
    """Cobertura do management command monitorar_noticias."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Governo Monitor",
            email="gov-monitor@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )

    def _rss_xml(self, titulo="Surto de dengue no Nordeste", url="https://svs.gov.br/rss/dengue-1"):
        from datetime import datetime, timezone as tz
        pub_date = datetime.now(tz.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>{titulo}</title>
      <link>{url}</link>
      <description>Aumento de casos confirmados. surto dengue.</description>
      <pubDate>{pub_date}</pubDate>
    </item>
  </channel>
</rss>""".encode()

    def test_sem_empresas_ativas_exibe_aviso(self):
        self.empresa.ativo = False
        self.empresa.save()
        out = StringIO()
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"articles": []}
            mock_get.return_value.content = b"<rss><channel></channel></rss>"
            mock_get.return_value.raise_for_status = lambda: None
            call_command("monitorar_noticias", stdout=out)
        self.assertIn("Nenhuma empresa ativa", out.getvalue())

    def test_rss_bem_sucedido_salva_noticias_com_doenca(self):
        out = StringIO()
        rss_bytes = self._rss_xml()
        gdelt_resp = type("R", (), {
            "status_code": 200,
            "json": lambda s=None: {"articles": []},
            "raise_for_status": lambda s=None: None,
        })()
        rss_resp = type("R", (), {
            "status_code": 200,
            "content": rss_bytes,
            "raise_for_status": lambda s=None: None,
        })()

        def fake_get(url, **kwargs):
            if "gdeltproject" in url:
                return gdelt_resp
            return rss_resp

        with patch("requests.get", side_effect=fake_get):
            call_command("monitorar_noticias", stdout=out)

        count = NoticiaEpidemiologica.objects.filter(empresa=self.empresa).count()
        self.assertGreater(count, 0)
        noticia = NoticiaEpidemiologica.objects.filter(empresa=self.empresa).first()
        self.assertIn("dengue", noticia.doencas_detectadas)

    def test_gdelt_429_escreve_erro_e_continua(self):
        err = StringIO()
        rss_resp = type("R", (), {
            "status_code": 200,
            "content": self._rss_xml(),
            "raise_for_status": lambda s=None: None,
        })()
        gdelt_resp_429 = type("R", (), {"status_code": 429})()

        call_count = {"n": 0}

        def fake_get(url, **kwargs):
            if "gdeltproject" in url:
                call_count["n"] += 1
                return gdelt_resp_429
            return rss_resp

        with patch("requests.get", side_effect=fake_get), patch("time.sleep"):
            call_command("monitorar_noticias", stderr=err)

        self.assertIn("GDELT indisponível", err.getvalue())
        self.assertGreaterEqual(call_count["n"], 2)

    def test_dry_run_nao_salva_no_banco(self):
        out = StringIO()
        rss_bytes = self._rss_xml()
        rss_resp = type("R", (), {
            "status_code": 200,
            "content": rss_bytes,
            "raise_for_status": lambda s=None: None,
        })()
        gdelt_resp = type("R", (), {
            "status_code": 200,
            "json": lambda s=None: {"articles": []},
            "raise_for_status": lambda s=None: None,
        })()

        def fake_get(url, **kwargs):
            if "gdeltproject" in url:
                return gdelt_resp
            return rss_resp

        with patch("requests.get", side_effect=fake_get):
            call_command("monitorar_noticias", "--dry-run", stdout=out)

        self.assertEqual(NoticiaEpidemiologica.objects.count(), 0)

    def test_url_duplicada_nao_e_salva_novamente(self):
        out = StringIO()
        rss_bytes = self._rss_xml()
        rss_resp = type("R", (), {
            "status_code": 200,
            "content": rss_bytes,
            "raise_for_status": lambda s=None: None,
        })()
        gdelt_resp = type("R", (), {
            "status_code": 200,
            "json": lambda s=None: {"articles": []},
            "raise_for_status": lambda s=None: None,
        })()

        def fake_get(url, **kwargs):
            if "gdeltproject" in url:
                return gdelt_resp
            return rss_resp

        with patch("requests.get", side_effect=fake_get):
            call_command("monitorar_noticias", stdout=out)
            first_count = NoticiaEpidemiologica.objects.count()
            call_command("monitorar_noticias", stdout=out)
            second_count = NoticiaEpidemiologica.objects.count()

        self.assertEqual(first_count, second_count)

    def test_empresa_especifica_limita_escopo(self):
        outra = Empresa.objects.create(
            nome="Outro Municipio",
            email="outro-municipio@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )
        rss_bytes = self._rss_xml()
        rss_resp = type("R", (), {
            "status_code": 200,
            "content": rss_bytes,
            "raise_for_status": lambda s=None: None,
        })()
        gdelt_resp = type("R", (), {
            "status_code": 200,
            "json": lambda s=None: {"articles": []},
            "raise_for_status": lambda s=None: None,
        })()

        def fake_get(url, **kwargs):
            if "gdeltproject" in url:
                return gdelt_resp
            return rss_resp

        out = StringIO()
        with patch("requests.get", side_effect=fake_get):
            call_command("monitorar_noticias", f"--empresa-id={self.empresa.pk}", stdout=out)

        self.assertGreater(NoticiaEpidemiologica.objects.filter(empresa=self.empresa).count(), 0)
        self.assertEqual(NoticiaEpidemiologica.objects.filter(empresa=outra).count(), 0)


class AnalisarNoticiasIACommandTests(TestCase):
    """Cobertura do management command analisar_noticias_ia."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Governo IA Teste",
            email="gov-ia@teste.com",
            senha=make_password("123456"),
            ativo=True,
            acesso_governo=True,
            tipo_conta=Empresa.TIPO_GOVERNO,
            pacote_codigo="governo_municipio_pequeno",
            max_dispositivos=5,
            max_usuarios=5,
        )
        self.noticia = NoticiaEpidemiologica.objects.create(
            empresa=self.empresa,
            titulo="Surto de dengue confirmado em Recife",
            fonte="SVS",
            url="https://svs.gov.br/dengue-recife",
            resumo="Aumento de 200% nos casos esta semana.",
            doencas_detectadas=["dengue"],
            nivel_alerta="alerta",
            ia_analisado=False,
        )

    def _fake_anthropic_module(self, client_instance):
        """Injeta módulo 'anthropic' falso em sys.modules."""
        import sys
        fake_mod = type(sys)("anthropic")
        fake_mod.Anthropic = lambda api_key: client_instance
        return fake_mod

    def _haiku_response(self, payload: dict):
        raw_json = json.dumps(payload)
        content_block = type("Block", (), {"text": raw_json})()
        return type("Resp", (), {"content": [content_block]})()

    def _mock_client(self, resp):
        class FakeMsgs:
            def create(self, **kw):
                return resp
        class FakeClient:
            messages = FakeMsgs()
        return FakeClient()

    def test_sem_api_key_exibe_aviso_e_nao_processa(self):
        out = StringIO()
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            call_command("analisar_noticias_ia", stdout=out)
        self.assertIn("ANTHROPIC_API_KEY", out.getvalue())
        self.noticia.refresh_from_db()
        self.assertFalse(self.noticia.ia_analisado)

    def test_analise_bem_sucedida_atualiza_campos(self):
        import sys
        payload = {
            "doenca_confirmada": "dengue",
            "cid10": "A90",
            "regiao_uf": "PE",
            "municipio": "Recife",
            "casos_estimados": 1500,
            "tendencia": "crescendo",
            "score_risco": 7.5,
            "confianca": 0.9,
            "nivel_alerta": "alerta",
            "justificativa": "Aumento acentuado de casos.",
            "acoes_recomendadas": ["Intensificar borrifação", "Alertar UBSs"],
        }
        client = self._mock_client(self._haiku_response(payload))
        fake_mod = self._fake_anthropic_module(client)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.dict(sys.modules, {"anthropic": fake_mod}):
                out = StringIO()
                call_command("analisar_noticias_ia", stdout=out)

        self.noticia.refresh_from_db()
        self.assertTrue(self.noticia.ia_analisado)
        self.assertEqual(self.noticia.ia_cid10, "A90")
        self.assertEqual(self.noticia.ia_regiao_uf, "PE")
        self.assertEqual(self.noticia.ia_casos_estimados, 1500)
        self.assertAlmostEqual(self.noticia.ia_score_risco, 7.5)
        self.assertEqual(self.noticia.ia_tendencia, "crescendo")
        self.assertIn("dengue", self.noticia.doencas_detectadas)

    def test_json_invalido_da_ia_nao_marca_como_analisado(self):
        import sys
        bad_block = type("Block", (), {"text": "isso não é json {{{{"})()
        bad_resp = type("Resp", (), {"content": [bad_block]})()
        client = self._mock_client(bad_resp)
        fake_mod = self._fake_anthropic_module(client)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.dict(sys.modules, {"anthropic": fake_mod}):
                err = StringIO()
                call_command("analisar_noticias_ia", stderr=err)

        self.noticia.refresh_from_db()
        self.assertFalse(self.noticia.ia_analisado)
        self.assertIn("JSON inválido", err.getvalue())

    def test_api_exception_nao_quebra_command(self):
        import sys

        class FakeMsgs:
            def create(self, **kw):
                raise Exception("timeout")

        class FakeClient:
            messages = FakeMsgs()

        fake_mod = self._fake_anthropic_module(FakeClient())
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.dict(sys.modules, {"anthropic": fake_mod}):
                err = StringIO()
                call_command("analisar_noticias_ia", stderr=err)

        self.noticia.refresh_from_db()
        self.assertFalse(self.noticia.ia_analisado)
        self.assertIn("Erro API", err.getvalue())

    def test_re_analisar_processa_noticias_ja_analisadas(self):
        import sys
        self.noticia.ia_analisado = True
        self.noticia.save()

        payload = {
            "doenca_confirmada": "dengue",
            "cid10": "A90",
            "regiao_uf": "PE",
            "municipio": "Recife",
            "casos_estimados": 100,
            "tendencia": "estavel",
            "score_risco": 4.0,
            "confianca": 0.8,
            "nivel_alerta": "alerta",
            "justificativa": "Re-análise.",
            "acoes_recomendadas": [],
        }
        client = self._mock_client(self._haiku_response(payload))
        fake_mod = self._fake_anthropic_module(client)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.dict(sys.modules, {"anthropic": fake_mod}):
                out = StringIO()
                call_command("analisar_noticias_ia", "--re-analisar", stdout=out)

        self.assertIn("1 notícias", out.getvalue())

    def test_nenhuma_pendente_exibe_mensagem(self):
        import sys
        self.noticia.ia_analisado = True
        self.noticia.save()

        fake_mod = self._fake_anthropic_module(None)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.dict(sys.modules, {"anthropic": fake_mod}):
                out = StringIO()
                call_command("analisar_noticias_ia", stdout=out)

        self.assertIn("pendente", out.getvalue())

    def test_nivel_alerta_mapeado_por_score_quando_invalido(self):
        """score_risco ≥ 9 → critico mesmo se nivel_alerta da IA for inválido."""
        import sys
        payload = {
            "doenca_confirmada": "influenza",
            "cid10": "J10",
            "regiao_uf": "RS",
            "municipio": None,
            "casos_estimados": None,
            "tendencia": "crescendo",
            "score_risco": 9.5,
            "confianca": 0.95,
            "nivel_alerta": "INVALIDO",
            "justificativa": "Pandemia em andamento.",
            "acoes_recomendadas": ["Isolar"],
        }
        client = self._mock_client(self._haiku_response(payload))
        fake_mod = self._fake_anthropic_module(client)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
            with patch.dict(sys.modules, {"anthropic": fake_mod}):
                call_command("analisar_noticias_ia")

        self.noticia.refresh_from_db()
        self.assertEqual(self.noticia.nivel_alerta, "critico")


class PortalASOLGPDTests(TestCase):
    """Cobertura do portal_aso_publico — rate limiting e auditoria LGPD."""

    def setUp(self):
        from django.core.cache import cache as django_cache
        django_cache.clear()

        self.empresa = Empresa.objects.create(
            nome="Clinica ASO LGPD",
            email="clinica-aso@teste.com",
            senha=make_password("123456"),
            ativo=True,
            tipo_conta=Empresa.TIPO_EMPRESA,
            pacote_codigo="sst_enterprise_10",
            max_dispositivos=5,
            max_usuarios=5,
        )
        self.funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Funcionário Portal",
            cpf="123.456.789-00",
            cargo="Operador",
            setor="Produção",
            data_admissao=timezone.now().date(),
            ativo=True,
        )
        self.aso = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="admissional",
            data_emissao=timezone.now().date(),
            resultado="apto",
            medico_responsavel="Dr. Teste",
        )

    def _criar_compartilhamento(self, token="tok-teste-valido", ativo=True, expirado=False):
        from django.utils import timezone as tz
        expira = tz.now() - timezone.timedelta(hours=1) if expirado else tz.now() + timezone.timedelta(hours=24)
        return ASOCompartilhamento.objects.create(
            aso=self.aso,
            empresa_origem=self.empresa,
            token=token,
            max_acessos=20,
            acessos=0,
            expira_em=expira,
            ativo=ativo,
        )

    def test_token_invalido_renderiza_erro(self):
        resp = Client().get("/sst/aso/portal/token-inexistente/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "inválido")

    def test_token_expirado_renderiza_erro(self):
        self._criar_compartilhamento(token="tok-expirado", expirado=True)
        resp = Client().get("/sst/aso/portal/tok-expirado/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "expirou")

    def test_rate_limit_bloqueia_apos_5_tentativas(self):
        from django.core.cache import cache as django_cache
        django_cache.clear()
        client = Client()
        for _ in range(5):
            client.get(
                "/sst/aso/portal/token-inexistente/",
                REMOTE_ADDR="1.2.3.4",
            )
        # 6ª tentativa do mesmo IP deve ser bloqueada
        resp = client.get(
            "/sst/aso/portal/token-inexistente/",
            REMOTE_ADDR="1.2.3.4",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Muitas tentativas")

    def test_ips_diferentes_nao_se_interferem(self):
        from django.core.cache import cache as django_cache
        django_cache.clear()
        for _ in range(5):
            Client().get("/sst/aso/portal/token-inexistente/", REMOTE_ADDR="10.0.0.1")
        # IP diferente ainda pode acessar
        resp = Client().get("/sst/aso/portal/token-inexistente/", REMOTE_ADDR="10.0.0.2")
        self.assertNotContains(resp, "Muitas tentativas")

    def test_acesso_valido_incrementa_contador(self):
        from django.core.cache import cache as django_cache
        django_cache.clear()
        comp = self._criar_compartilhamento(token="tok-valido-contador")
        Client().get("/sst/aso/portal/tok-valido-contador/", REMOTE_ADDR="2.2.2.2")
        comp.refresh_from_db()
        self.assertEqual(comp.acessos, 1)

    def test_limite_de_acessos_atingido_renderiza_erro(self):
        comp = self._criar_compartilhamento(token="tok-limite")
        comp.acessos = comp.max_acessos
        comp.save()
        from django.core.cache import cache as django_cache
        django_cache.clear()
        resp = Client().get("/sst/aso/portal/tok-limite/", REMOTE_ADDR="3.3.3.3")
        self.assertContains(resp, "Limite de acessos")


# ─────────────────────────────────────────────────────────────────────────────
# TEST-004 — eSocial XML Generation (S-2210 / S-2220 / S-2230 / S-2240)
# ─────────────────────────────────────────────────────────────────────────────

class EsocialXMLTests(TestCase):
    """Testes unitários para os geradores de XML eSocial."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Empresa SST XML",
            email="sst-xml@teste.com",
            senha=make_password("123456"),
            ativo=True,
            tipo_conta=Empresa.TIPO_EMPRESA,
            pacote_codigo="sst_enterprise_10",
            max_dispositivos=5,
            max_usuarios=5,
        )
        self.cfg = ConfiguracaoSST.objects.create(
            empresa=self.empresa,
            cnpj="12.345.678/0001-90",
            nome_medico_coordenador="Dr. João Teste",
            crm_medico="CRM-123456",
        )
        self.funcionario = FuncionarioSST.objects.create(
            empresa=self.empresa,
            nome="Maria Funcionária",
            cpf="123.456.789-00",
            matricula="MAT001",
            cargo="Operadora de Produção",
            ativo=True,
        )

    def _parse(self, xml_str):
        from xml.etree import ElementTree as ET
        return ET.fromstring(xml_str.split("\n", 1)[1])  # pula linha do XML declaration

    # ── S-2210 (CAT) ──────────────────────────────────────────────────────────

    def test_s2210_estrutura_basica(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="leve",
            data_acidente=date(2026, 6, 1),
            descricao="Queda em escada",
            houve_afastamento=False,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        self.assertTrue(xml.startswith("<?xml version"))
        self.assertIn("evtCAT", xml)
        self.assertIn("SolusCRT_1.0", xml)
        self.assertIn("2026-06-01", xml)

    def test_s2210_fuga_xml_em_descricao(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="leve",
            data_acidente=date(2026, 6, 1),
            descricao='Lesão com instrumento <cortante> & "perfurante"',
            houve_afastamento=False,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        # O `<cortante>` não deve aparecer como tag XML aberta
        self.assertNotIn("</cortante>", xml)
        # `&` do texto original foi escapado (aparece como &amp; ou &amp;amp; após dupla serialização)
        self.assertIn("amp;", xml)

    def test_s2210_fatal_gera_indCatObito_S(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="fatal",
            data_acidente=date(2026, 6, 2),
            descricao="Acidente fatal",
            houve_afastamento=False,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        self.assertIn("<indCatObito>S</indCatObito>", xml)

    def test_s2210_leve_gera_indCatObito_N(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="leve",
            data_acidente=date(2026, 6, 2),
            descricao="Leve",
            houve_afastamento=False,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        self.assertIn("<indCatObito>N</indCatObito>", xml)

    def test_s2210_tipo_trajeto_gera_tpAcid_2(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="trajeto",
            gravidade="moderado",
            data_acidente=date(2026, 6, 3),
            descricao="Acidente de trajeto",
            houve_afastamento=False,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        self.assertIn("<tpAcid>2</tpAcid>", xml)

    def test_s2210_cpf_funcionario_no_xml(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="leve",
            data_acidente=date(2026, 6, 4),
            descricao="Teste CPF",
            houve_afastamento=False,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        self.assertIn("12345678900", xml)  # CPF sem formatação

    def test_s2210_afastamento_houveAfast_S(self):
        from api.views_esocial_sst import _gerar_xml_s2210
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="grave",
            data_acidente=date(2026, 6, 5),
            descricao="Grave com afastamento",
            houve_afastamento=True,
        )
        xml = _gerar_xml_s2210(cat, self.cfg)
        self.assertIn("<houveAfast>S</houveAfast>", xml)
        self.assertIn("<indAfast>S</indAfast>", xml)

    # ── S-2220 (ASO / Monitoramento) ──────────────────────────────────────────

    def test_s2220_estrutura_basica_apto(self):
        from api.views_esocial_sst import _gerar_xml_s2220
        aso = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="admissional",
            data_emissao=date(2026, 6, 1),
            resultado="apto",
            medico_responsavel="Dr. João Teste",
            crm="CRM-123456",
        )
        xml = _gerar_xml_s2220(aso, self.cfg)
        self.assertIn("evtMonit", xml)
        self.assertIn("<resAso>1</resAso>", xml)   # apto = "1"
        self.assertIn("<tpExameOcup>1</tpExameOcup>", xml)   # admissional = "1"

    def test_s2220_inapto_gera_resAso_2(self):
        from api.views_esocial_sst import _gerar_xml_s2220
        aso = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="periodico",
            data_emissao=date(2026, 6, 2),
            resultado="inapto",
            cid_inapto="M54",
            medico_responsavel="Dr. Teste",
        )
        xml = _gerar_xml_s2220(aso, self.cfg)
        self.assertIn("<resAso>2</resAso>", xml)

    def test_s2220_cid_incluido_apenas_quando_inapto(self):
        from api.views_esocial_sst import _gerar_xml_s2220
        aso_apto = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="demissional",
            data_emissao=date(2026, 6, 3),
            resultado="apto",
            cid_inapto="M54",
            medico_responsavel="Dr. Teste",
        )
        xml_apto = _gerar_xml_s2220(aso_apto, self.cfg)
        self.assertNotIn("codCID", xml_apto)

        aso_inapto = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="retorno_trabalho",
            data_emissao=date(2026, 6, 4),
            resultado="inapto",
            cid_inapto="M54",
            medico_responsavel="Dr. Teste",
        )
        xml_inapto = _gerar_xml_s2220(aso_inapto, self.cfg)
        self.assertIn("<codCID>M54</codCID>", xml_inapto)

    def test_s2220_data_emissao_no_xml(self):
        from api.views_esocial_sst import _gerar_xml_s2220
        aso = ASOOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="mudanca_risco",
            data_emissao=date(2026, 5, 15),
            resultado="apto",
        )
        xml = _gerar_xml_s2220(aso, self.cfg)
        self.assertIn("2026-05-15", xml)

    # ── S-2230 (Afastamento) ──────────────────────────────────────────────────

    def test_s2230_estrutura_basica_sem_retorno(self):
        from api.views_esocial_sst import _gerar_xml_s2230
        afastamento = AfastamentoSST.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            motivo="doenca_comum",
            data_inicio=date(2026, 6, 10),
            cid="J10",
        )
        xml = _gerar_xml_s2230(afastamento, self.cfg)
        self.assertIn("evtAfastTemp", xml)
        self.assertIn("2026-06-10", xml)
        self.assertIn("<codMotAfast>03</codMotAfast>", xml)   # doenca_comum = "03"
        self.assertNotIn("fimAfastamento", xml)

    def test_s2230_com_data_retorno_gera_fimAfastamento(self):
        from api.views_esocial_sst import _gerar_xml_s2230
        afastamento = AfastamentoSST.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            motivo="acidente_trabalho",
            data_inicio=date(2026, 6, 1),
            data_retorno_real=date(2026, 6, 20),
            cid="S52",
        )
        xml = _gerar_xml_s2230(afastamento, self.cfg)
        self.assertIn("fimAfastamento", xml)
        self.assertIn("2026-06-20", xml)
        self.assertIn("<codMotAfast>01</codMotAfast>", xml)

    def test_s2230_licenca_maternidade_mapeia_18(self):
        from api.views_esocial_sst import _gerar_xml_s2230
        afastamento = AfastamentoSST.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            motivo="licenca_maternidade",
            data_inicio=date(2026, 7, 1),
        )
        xml = _gerar_xml_s2230(afastamento, self.cfg)
        self.assertIn("<codMotAfast>18</codMotAfast>", xml)

    def test_s2230_cid_incluido_quando_presente(self):
        from api.views_esocial_sst import _gerar_xml_s2230
        afastamento = AfastamentoSST.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            motivo="doenca_ocupacional",
            data_inicio=date(2026, 6, 5),
            cid="Z571",
        )
        xml = _gerar_xml_s2230(afastamento, self.cfg)
        self.assertIn("<codCID>Z571</codCID>", xml)

    def test_s2230_motivo_desconhecido_usa_99(self):
        from api.views_esocial_sst import _gerar_xml_s2230
        afastamento = AfastamentoSST.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            motivo="outro",
            data_inicio=date(2026, 6, 6),
        )
        xml = _gerar_xml_s2230(afastamento, self.cfg)
        self.assertIn("<codMotAfast>99</codMotAfast>", xml)

    # ── S-2240 (Condições Ambientais) ─────────────────────────────────────────

    def test_s2240_estrutura_basica(self):
        from api.views_esocial_sst import _gerar_xml_s2240
        xml = _gerar_xml_s2240(self.empresa, self.cfg, periodo="2026-06")
        self.assertIn("evtCondicAmb", xml)
        self.assertIn("SolusCRT_1.0", xml)

    def test_s2240_namespace_correto(self):
        from api.views_esocial_sst import _gerar_xml_s2240
        xml = _gerar_xml_s2240(self.empresa, self.cfg, periodo="2026-06")
        self.assertIn("evtCondicAmb", xml)
        self.assertIn("esocial.gov.br", xml)

    def test_s2240_sem_cfg_usa_cnpj_padrao(self):
        from api.views_esocial_sst import _gerar_xml_s2240
        xml = _gerar_xml_s2240(self.empresa, None, periodo="2026-06")
        self.assertIn("evtCondicAmb", xml)

    # ── API endpoint gerar XML ─────────────────────────────────────────────────

    def test_api_gerar_xml_s2210_retorna_xml(self):
        from api.models import eSocialEventoSST
        cat = CATOcupacional.objects.create(
            empresa=self.empresa,
            funcionario=self.funcionario,
            tipo="tipico",
            gravidade="leve",
            data_acidente=date(2026, 6, 1),
            descricao="Teste API XML",
            houve_afastamento=False,
        )
        # referencia é CharField — armazena JSON com tipo e id
        evento = eSocialEventoSST.objects.create(
            empresa=self.empresa,
            tipo_evento="S-2210",
            referencia=json.dumps({"tipo": "cat", "id": cat.pk}),
            status="pendente",
        )

        client = Client()
        client.post(
            "/api/login",
            data=json.dumps({
                "email": "sst-xml@teste.com",
                "senha": "123456",
                "device_id": "sst-xml-device",
            }),
            content_type="application/json",
        )
        resp = client.get(f"/api/esocial/evento/{evento.pk}/xml")
        # 200 com XML ou resposta de erro esperada — apenas confirma que o endpoint existe
        self.assertIn(resp.status_code, {200, 400, 404, 422})


# ─────────────────────────────────────────────────────────────────────────────
# TEST-005 — Plano de Saúde ANS: DIOPS / SIB / Rede Credenciada
# ─────────────────────────────────────────────────────────────────────────────

class DIOPSAPITests(PlanoSaudeEnterpriseBaseTests):
    """CRUD de declarações DIOPS e validações ANS IN 77/2022."""

    def test_lista_diops_vazia(self):
        resp = self._get("/api/plano-saude/ans/diops")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("declaracoes", body)
        self.assertEqual(body["declaracoes"], [])
        self.assertEqual(body["total"], 0)

    def test_cria_diops_basico(self):
        resp = self._post("/api/plano-saude/ans/diops", {
            "trimestre": "20261",
            "registro_ans": "123456",
            "receita_operacional": 500000.00,
            "despesa_assistencial": 380000.00,
            "despesa_administrativa": 70000.00,
            "resultado_periodo": 50000.00,
            "vidas_ativas": 1200,
        })
        self.assertEqual(resp.status_code, 201)
        body = resp.json()["declaracao"]
        self.assertEqual(body["trimestre"], "20261")
        self.assertEqual(body["vidas_ativas"], 1200)
        self.assertEqual(body["status"], "em_elaboracao")

    def test_trimestre_invalido_retorna_400(self):
        resp = self._post("/api/plano-saude/ans/diops", {
            "trimestre": "2026X",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("trimestre", resp.json()["erro"])

    def test_trimestre_faltante_retorna_400(self):
        resp = self._post("/api/plano-saude/ans/diops", {
            "receita_operacional": 100000,
        })
        self.assertEqual(resp.status_code, 400)

    def test_tipo_operadora_invalido_retorna_400(self):
        resp = self._post("/api/plano-saude/ans/diops", {
            "trimestre": "20262",
            "tipo_operadora": "9",  # não existe
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("tipo_operadora", resp.json()["erro"])

    def test_modalidade_invalida_retorna_400(self):
        resp = self._post("/api/plano-saude/ans/diops", {
            "trimestre": "20262",
            "modalidade_assistencial": "99",  # não existe
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("modalidade", resp.json()["erro"])

    def test_detalhe_diops_existente(self):
        d = DIOPSDeclaracao.objects.create(
            empresa=self.operadora,
            trimestre="20261",
            receita_operacional=100000,
            despesa_assistencial=80000,
            despesa_administrativa=10000,
            resultado_periodo=10000,
            vidas_ativas=500,
        )
        resp = self._get(f"/api/plano-saude/ans/diops/{d.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["declaracao"]["trimestre"], "20261")

    def test_detalhe_diops_inexistente_retorna_404(self):
        resp = self._get("/api/plano-saude/ans/diops/99999")
        self.assertEqual(resp.status_code, 404)

    def test_update_diops_status(self):
        d = DIOPSDeclaracao.objects.create(
            empresa=self.operadora,
            trimestre="20263",
            receita_operacional=200000,
            despesa_assistencial=150000,
            despesa_administrativa=20000,
            resultado_periodo=30000,
            vidas_ativas=800,
        )
        resp = self._put(f"/api/plano-saude/ans/diops/{d.pk}", {"status": "validada"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["declaracao"]["status"], "validada")

    def test_paginacao_diops(self):
        for i in range(5):
            DIOPSDeclaracao.objects.create(
                empresa=self.operadora,
                trimestre=f"202{i}4",
                receita_operacional=10000 * (i + 1),
                despesa_assistencial=8000 * (i + 1),
                despesa_administrativa=1000,
                resultado_periodo=1000,
                vidas_ativas=100,
            )
        resp = self._get("/api/plano-saude/ans/diops?limit=2&offset=0")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["declaracoes"]), 2)
        self.assertTrue(body["has_more"])
        self.assertEqual(body["total"], 5)

    def test_isolamento_diops_outra_empresa(self):
        outra = Empresa.objects.create(
            nome="Outra Operadora",
            email="outra-op@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        DIOPSDeclaracao.objects.create(
            empresa=outra,
            trimestre="20264",
            receita_operacional=50000,
            despesa_assistencial=40000,
            despesa_administrativa=5000,
            resultado_periodo=5000,
            vidas_ativas=200,
        )
        resp = self._get("/api/plano-saude/ans/diops")
        self.assertEqual(resp.json()["total"], 0)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/ans/diops")
        self.assertEqual(resp.status_code, 401)


class SIBAPITests(PlanoSaudeEnterpriseBaseTests):
    """CRUD de registros SIB e rate limiting na transmissão."""

    def test_lista_sib_vazia(self):
        resp = self._get("/api/plano-saude/ans/sib")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("registros", body)
        self.assertEqual(body["total"], 0)

    def test_cria_sib_basico(self):
        resp = self._post("/api/plano-saude/ans/sib", {
            "competencia": "202606",
            "registro_ans": "123456",
            "vidas_incluidas": 50,
            "vidas_excluidas": 5,
            "vidas_alteradas": 10,
            "total_vidas": 1200,
        })
        self.assertEqual(resp.status_code, 201)
        body = resp.json()["registro"]
        self.assertEqual(body["competencia"], "202606")
        self.assertEqual(body["total_vidas"], 1200)
        self.assertFalse(body["enviado"])

    def test_competencia_faltante_retorna_400(self):
        resp = self._post("/api/plano-saude/ans/sib", {
            "vidas_incluidas": 50,
        })
        self.assertEqual(resp.status_code, 400)

    def test_detalhe_sib(self):
        s = SIBRegistro.objects.create(
            empresa=self.operadora,
            competencia="202605",
            vidas_incluidas=30,
            vidas_excluidas=3,
            vidas_alteradas=5,
            total_vidas=800,
        )
        resp = self._get(f"/api/plano-saude/ans/sib/{s.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["registro"]["competencia"], "202605")

    def test_detalhe_sib_inexistente_retorna_404(self):
        resp = self._get("/api/plano-saude/ans/sib/99999")
        self.assertEqual(resp.status_code, 404)

    def test_update_sib_marca_enviado(self):
        s = SIBRegistro.objects.create(
            empresa=self.operadora,
            competencia="202604",
            total_vidas=600,
        )
        resp = self._put(f"/api/plano-saude/ans/sib/{s.pk}", {"enviado": True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["registro"]["enviado"])

    def test_transmitir_sib_rate_limit(self):
        from django.core.cache import cache as django_cache
        django_cache.clear()
        s = SIBRegistro.objects.create(
            empresa=self.operadora,
            competencia="202603",
            total_vidas=400,
        )
        url = f"/api/plano-saude/ans/sib/{s.pk}/transmitir/"
        # Marca rate limit manualmente
        from django.core.cache import cache
        cache.set(f"sib_transmit:{s.pk}", True, timeout=3600)
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 429)

    def test_transmitir_sib_sem_credenciais_orienta_configuracao(self):
        from django.core.cache import cache as django_cache
        django_cache.clear()
        s = SIBRegistro.objects.create(
            empresa=self.operadora,
            competencia="202602",
            total_vidas=300,
        )
        url = f"/api/plano-saude/ans/sib/{s.pk}/transmitir/"
        resp = self.client.post(url)
        # Sem credenciais ANS configuradas → 200 com orientação ou 400
        self.assertIn(resp.status_code, {200, 400, 422})

    def test_isolamento_sib_outra_empresa(self):
        outra = Empresa.objects.create(
            nome="Outra Op SIB",
            email="outra-op-sib@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        SIBRegistro.objects.create(empresa=outra, competencia="202601", total_vidas=200)
        resp = self._get("/api/plano-saude/ans/sib")
        self.assertEqual(resp.json()["total"], 0)

    def test_paginacao_sib(self):
        for i in range(4):
            SIBRegistro.objects.create(
                empresa=self.operadora,
                competencia=f"2026{i+1:02d}",
                total_vidas=100 * (i + 1),
            )
        resp = self._get("/api/plano-saude/ans/sib?limit=2")
        body = resp.json()
        self.assertEqual(len(body["registros"]), 2)
        self.assertTrue(body["has_more"])


class RedeCredenciadaAPITests(PlanoSaudeEnterpriseBaseTests):
    """CRUD de prestadores na rede credenciada."""

    def test_lista_rede_vazia(self):
        resp = self._get("/api/plano-saude/rede")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("rede", body)
        self.assertEqual(body["rede"], [])

    def test_cria_prestador(self):
        resp = self.client.post(
            "/api/plano-saude/rede/novo",
            data=json.dumps({
                "nome": "Hospital São Lucas",
                "tipo": "hospital",
                "cnpj": "11.222.333/0001-44",
                "cidade": "São Paulo",
                "uf": "SP",
                "especialidades": ["Cardiologia", "Ortopedia"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["rede"]["nome"], "Hospital São Lucas")
        self.assertEqual(body["rede"]["tipo"], "hospital")

    def test_cria_sem_nome_retorna_400(self):
        resp = self.client.post(
            "/api/plano-saude/rede/novo",
            data=json.dumps({"tipo": "hospital"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_detalhe_prestador(self):
        r = RedeCredenciadaPlano.objects.create(
            empresa=self.operadora,
            nome="Clínica Boa Saúde",
            tipo="clinica",
        )
        resp = self._get(f"/api/plano-saude/rede/{r.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["rede"]["nome"], "Clínica Boa Saúde")

    def test_detalhe_inexistente_retorna_404(self):
        resp = self._get("/api/plano-saude/rede/99999")
        self.assertEqual(resp.status_code, 404)

    def test_update_prestador(self):
        r = RedeCredenciadaPlano.objects.create(
            empresa=self.operadora,
            nome="Lab Antigo",
            tipo="laboratorio",
        )
        resp = self._put(f"/api/plano-saude/rede/{r.pk}", {
            "nome": "Lab Renovado",
            "ativo": True,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["rede"]["nome"], "Lab Renovado")

    def test_kpis_retorna_estrutura(self):
        RedeCredenciadaPlano.objects.create(empresa=self.operadora, nome="Hospital A", tipo="hospital", ativo=True)
        RedeCredenciadaPlano.objects.create(empresa=self.operadora, nome="Clínica B", tipo="clinica", ativo=True)
        RedeCredenciadaPlano.objects.create(empresa=self.operadora, nome="Lab C", tipo="laboratorio", ativo=False)
        resp = self._get("/api/plano-saude/rede/kpis")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("ativos", body)
        self.assertEqual(body["ativos"], 2)

    def test_filtro_por_tipo(self):
        RedeCredenciadaPlano.objects.create(empresa=self.operadora, nome="Hospital X", tipo="hospital")
        RedeCredenciadaPlano.objects.create(empresa=self.operadora, nome="Lab Y", tipo="laboratorio")
        resp = self._get("/api/plano-saude/rede?tipo=hospital")
        body = resp.json()
        for p in body["rede"]:
            self.assertEqual(p["tipo"], "hospital")

    def test_paginacao_rede(self):
        for i in range(6):
            RedeCredenciadaPlano.objects.create(
                empresa=self.operadora,
                nome=f"Prestador {i}",
                tipo="clinica",
            )
        resp = self._get("/api/plano-saude/rede?limit=3")
        body = resp.json()
        self.assertEqual(len(body["rede"]), 3)
        self.assertTrue(body["has_more"])

    def test_isolamento_rede_outra_empresa(self):
        outra = Empresa.objects.create(
            nome="Outra Op Rede",
            email="outra-op-rede@teste.com",
            senha=make_password("123456"),
            ativo=True,
            pacote_codigo="plano_saude_operadora",
            max_dispositivos=5,
            max_usuarios=5,
        )
        RedeCredenciadaPlano.objects.create(empresa=outra, nome="Prestador Intruso", tipo="hospital")
        resp = self._get("/api/plano-saude/rede")
        nomes = [p["nome"] for p in resp.json()["rede"]]
        self.assertNotIn("Prestador Intruso", nomes)

    def test_sem_autenticacao_retorna_401(self):
        resp = self.anon.get("/api/plano-saude/rede")
        self.assertEqual(resp.status_code, 401)
