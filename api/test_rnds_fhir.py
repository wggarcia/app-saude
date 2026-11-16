"""
Testes do cliente único da RNDS (api/services/rnds_fhir.py) e dos cinco módulos
que passam por ele. Sem rede: requests.get (token) e requests.request (EHR)
são substituídos por mocks.
"""
import base64
import datetime
import json
import os
from unittest.mock import MagicMock, patch

from django.contrib.auth.hashers import make_password
from django.test import RequestFactory, SimpleTestCase, TestCase

from .services import rnds_fhir

AUTH_HMG = "https://ehr-auth-hmg.saude.gov.br/api/token"
AUTH_PROD = "https://ehr-auth.saude.gov.br/api/token"
EHR_HMG = "https://ehr-services.hmg.saude.gov.br/api/fhir/r4"
CNS = "700000000000005"
SENHA = "senha123"


def _gerar_pfx_b64():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Prefeitura Teste")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2035, 1, 1))
            .sign(key, hashes.SHA256()))
    pfx = pkcs12.serialize_key_and_certificates(
        b"c", key, cert, None, BestAvailableEncryption(SENHA.encode()))
    return base64.b64encode(pfx).decode()


PFX_B64 = _gerar_pfx_b64()


class _CredFalsa:
    def __init__(self, **kw):
        self.empresa_id = kw.get("empresa_id", 1)
        self.rnds_certificado_pfx_b64 = kw.get("pfx", PFX_B64)
        self.rnds_ambiente = kw.get("ambiente", "homologacao")
        self.rnds_uf = kw.get("uf", "")
        self.sus_uf = kw.get("sus_uf", "")
        self.rnds_cns_profissional = kw.get("cns", CNS)
        self._senha = kw.get("senha", SENHA)

    def get_rnds_certificado_senha(self):
        return self._senha


def _resp(status=200, corpo=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = corpo if corpo is not None else {}
    r.text = json.dumps(corpo or {})
    r.content = r.text.encode()
    r.headers = headers or {}
    return r


def _token_ok():
    return _resp(200, {"access_token": "tok-123"})


class ClienteRndsTests(SimpleTestCase):
    def setUp(self):
        rnds_fhir._TOKEN_CACHE.clear()

    @patch("api.services.rnds_fhir.requests.get")
    def test_token_homologacao_usa_servidor_auth_com_certificado(self, mget):
        caminhos = {}

        def _capturar(url, cert, timeout):
            caminhos["cert"] = cert
            self.assertTrue(all(os.path.exists(p) for p in cert))
            return _token_ok()

        mget.side_effect = _capturar
        self.assertEqual(rnds_fhir.obter_token(_CredFalsa()), "tok-123")
        self.assertEqual(mget.call_args.args[0], AUTH_HMG)
        self.assertEqual(len(caminhos["cert"]), 2)
        self.assertFalse(any(os.path.exists(p) for p in caminhos["cert"]))

    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_token_producao_usa_servidor_auth_nacional(self, mget):
        rnds_fhir.obter_token(_CredFalsa(ambiente="producao", uf="SP"))
        self.assertEqual(mget.call_args.args[0], AUTH_PROD)

    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_token_reaproveitado_do_cache(self, mget):
        cred = _CredFalsa()
        rnds_fhir.obter_token(cred)
        rnds_fhir.obter_token(cred)
        self.assertEqual(mget.call_count, 1)

    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_token_renovado_um_minuto_antes_de_vencer(self, mget):
        cred = _CredFalsa()
        with patch("api.services.rnds_fhir.time.monotonic", return_value=1000.0):
            rnds_fhir.obter_token(cred)
        with patch("api.services.rnds_fhir.time.monotonic", return_value=1000.0 + 28 * 60):
            rnds_fhir.obter_token(cred)
        self.assertEqual(mget.call_count, 1)
        with patch("api.services.rnds_fhir.time.monotonic", return_value=1000.0 + 29 * 60 + 1):
            rnds_fhir.obter_token(cred)
        self.assertEqual(mget.call_count, 2)

    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_certificado_trocado_nao_reusa_token_antigo(self, mget):
        rnds_fhir.obter_token(_CredFalsa())
        rnds_fhir.obter_token(_CredFalsa(pfx=_gerar_pfx_b64()))
        self.assertEqual(mget.call_count, 2)

    def test_host_ehr_homologacao(self):
        self.assertEqual(rnds_fhir.url_ehr(_CredFalsa()), EHR_HMG)

    def test_host_ehr_producao_por_uf(self):
        self.assertEqual(rnds_fhir.url_ehr(_CredFalsa(ambiente="producao", uf="MG")),
                         "https://mg-ehr-services.saude.gov.br/api/fhir/r4")

    def test_host_ehr_producao_usa_sus_uf_se_rnds_uf_vazio(self):
        self.assertEqual(rnds_fhir.url_ehr(_CredFalsa(ambiente="producao", sus_uf="go")),
                         "https://go-ehr-services.saude.gov.br/api/fhir/r4")

    @patch("api.services.rnds_fhir.requests.request")
    @patch("api.services.rnds_fhir.requests.get")
    def test_producao_sem_uf_da_erro_claro_sem_chamar_rede(self, mget, mreq):
        r = rnds_fhir.enviar_bundle(_CredFalsa(ambiente="producao"), {"resourceType": "Bundle"})
        self.assertFalse(r.ok)
        self.assertIn("UF", r.erro)
        mget.assert_not_called()
        mreq.assert_not_called()

    @patch("api.services.rnds_fhir.requests.request",
           return_value=_resp(201, {}, {"Location": f"{EHR_HMG}/Bundle/abc-1"}))
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_envio_leva_os_dois_cabecalhos_com_cns(self, mget, mreq):
        r = rnds_fhir.enviar_bundle(_CredFalsa(), {"resourceType": "Bundle"})
        self.assertTrue(r.ok)
        self.assertEqual(r.protocolo, "abc-1")
        metodo, url = mreq.call_args.args
        self.assertEqual((metodo, url), ("POST", f"{EHR_HMG}/Bundle"))
        cab = mreq.call_args.kwargs["headers"]
        self.assertEqual(cab["X-Authorization-Server"], "Bearer tok-123")
        self.assertEqual(cab["Authorization"], CNS)
        self.assertNotIn("cert", mreq.call_args.kwargs)

    @patch("api.services.rnds_fhir.requests.request")
    @patch("api.services.rnds_fhir.requests.get")
    def test_sem_cns_da_erro_claro(self, mget, mreq):
        r = rnds_fhir.enviar_bundle(_CredFalsa(cns=""), {})
        self.assertFalse(r.ok)
        self.assertIn("CNS", r.erro)
        mreq.assert_not_called()

    @patch("api.services.rnds_fhir.requests.request",
           side_effect=[_resp(401), _resp(200, {"id": "ok-2"})])
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_401_renova_token_e_repete_uma_vez(self, mget, mreq):
        r = rnds_fhir.enviar_bundle(_CredFalsa(), {})
        self.assertTrue(r.ok)
        self.assertEqual(r.protocolo, "ok-2")
        self.assertEqual(mget.call_count, 2)
        self.assertEqual(mreq.call_count, 2)

    @patch("api.services.rnds_fhir.requests.get")
    def test_senha_errada_vira_mensagem_em_portugues(self, mget):
        r = rnds_fhir.testar_conexao(_CredFalsa(senha="errada"))
        self.assertFalse(r.ok)
        self.assertIn("senha incorreta", r.erro)
        mget.assert_not_called()

    @patch("api.services.rnds_fhir.requests.get", return_value=_resp(403, {"erro": "x"}))
    def test_certificado_recusado_explica_ao_gestor(self, mget):
        r = rnds_fhir.testar_conexao(_CredFalsa())
        self.assertFalse(r.ok)
        self.assertEqual(r.status_http, 403)
        self.assertIn("recusou o certificado", r.erro)

    @patch("api.services.rnds_fhir.requests.request", return_value=_resp(200, {"resourceType": "Bundle"}))
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_consulta_paciente_por_cpf(self, mget, mreq):
        r = rnds_fhir.consultar_paciente(_CredFalsa(), "11144477735", "cpf")
        self.assertTrue(r.ok)
        metodo, url = mreq.call_args.args
        self.assertEqual((metodo, url), ("GET", f"{EHR_HMG}/Patient"))
        self.assertEqual(mreq.call_args.kwargs["params"],
                         {"identifier": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf|11144477735"})


# ── Os cinco módulos chamadores passam pelo cliente único ─────────────────────

def _empresa(email, pacote):
    from .models import Empresa
    return Empresa.objects.create(
        nome=f"Teste {email}", email=email, senha=make_password("x"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _cred(empresa, **extra):
    from .models import CredenciaisIntegracoes
    cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
    cred.rnds_certificado_pfx_b64 = PFX_B64
    cred.set_rnds_certificado_senha(SENHA)
    cred.rnds_cns_profissional = CNS
    cred.rnds_cpf_gestor = "11144477735"
    cred.rnds_cnes = "1234567"
    cred.rnds_ambiente = "homologacao"
    cred.rnds_ativo = True
    for k, v in extra.items():
        setattr(cred, k, v)
    cred.save()
    return cred


class ChamadoresUsamClienteUnicoTests(TestCase):
    def setUp(self):
        rnds_fhir._TOKEN_CACHE.clear()
        self.rf = RequestFactory()

    def _req(self, empresa, body=None):
        r = self.rf.post("/", data=json.dumps(body or {}), content_type="application/json")
        r.empresa = empresa
        r.principal = None
        return r

    def _assert_fluxo_oficial(self, mget, mreq):
        self.assertEqual(mget.call_args.args[0], AUTH_HMG)
        self.assertEqual(mreq.call_args.args, ("POST", f"{EHR_HMG}/Bundle"))
        self.assertEqual(mreq.call_args.kwargs["headers"]["Authorization"], CNS)

    @patch("api.services.rnds_fhir.requests.request", return_value=_resp(201, {"id": "p1"}))
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_esus_envia_fichas_pelo_cliente(self, mget, mreq):
        from .models import AtendimentoUBS
        from .views_governo_esus import api_esus_enviar_fichas
        emp = _empresa("esus@t.com", "governo_municipio_pequeno")
        _cred(emp)
        at = AtendimentoUBS.objects.create(
            empresa=emp, paciente_nome="Ana", cns="898000000000001", profissional="Dra X",
            data_atendimento=datetime.date(2026, 11, 1))
        resp = api_esus_enviar_fichas(self._req(emp))
        self.assertEqual(resp.status_code, 200, resp.content)
        self._assert_fluxo_oficial(mget, mreq)
        at.refresh_from_db()
        self.assertTrue(at.enviado_esus)

    @patch("api.views_governo_sipni._gerar_bundle_immunization", return_value={"resourceType": "Bundle"})
    @patch("api.views_governo_sipni._coletar_registros", return_value=[object()])
    @patch("api.services.rnds_fhir.requests.request", return_value=_resp(201, {"id": "p2"}))
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_sipni_transmite_pelo_cliente(self, mget, mreq, _col, _bundle):
        from .views_governo_sipni import api_sipni_transmitir
        emp = _empresa("sipni@t.com", "governo_municipio_pequeno")
        _cred(emp)
        resp = api_sipni_transmitir(self._req(emp, {"competencia": "202611"}))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(json.loads(resp.content)["protocolo"], "p2")
        self._assert_fluxo_oficial(mget, mreq)

    @patch("api.services.rnds_fhir.requests.request", return_value=_resp(201, {"id": "p3"}))
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_ceaf_horus_pelo_cliente(self, mget, mreq):
        from .models import DispensacaoCEAF, MedicamentoCEAF, SolicitacaoCEAF
        from .views_governo_ceaf import api_ceaf_horus_enviar
        emp = _empresa("ceaf@t.com", "governo_municipio_pequeno")
        _cred(emp)
        med = MedicamentoCEAF.objects.create(codigo_rename="T-RNDS-1", principio_ativo="Adalimumabe",
                                             componente="1A")
        sol = SolicitacaoCEAF.objects.create(
            empresa=emp, medicamento=med, paciente_nome="Bia", cpf_paciente="11144477735",
            cid10_principal="M05", medico_solicitante="Dr Y", numero_lme="LME-1")
        disp = DispensacaoCEAF.objects.create(empresa=emp, solicitacao=sol,
                                              data_dispensacao=datetime.date(2026, 11, 2))
        resp = api_ceaf_horus_enviar(self._req(emp), disp.id)
        self.assertEqual(resp.status_code, 200, resp.content)
        self._assert_fluxo_oficial(mget, mreq)
        disp.refresh_from_db()
        self.assertEqual((disp.horus_enviado, disp.horus_protocolo), (True, "p3"))

    @patch("api.services.rnds_fhir.requests.request", return_value=_resp(201, {"id": "p4"}))
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_hospital_reprocessa_pelo_cliente(self, mget, mreq):
        from .models import TransmissaoRNDSHospital
        from .views_hospital_rnds import api_hospital_rnds_reprocessar
        emp = _empresa("hosp@t.com", "hospital_rede")
        _cred(emp)
        tx = TransmissaoRNDSHospital.objects.create(
            empresa=emp, tipo="ips_br", bundle_fhir={"resourceType": "Bundle"}, status="erro")
        resp = api_hospital_rnds_reprocessar(self._req(emp), tx.id)
        self.assertEqual(resp.status_code, 200, resp.content)
        self._assert_fluxo_oficial(mget, mreq)
        tx.refresh_from_db()
        self.assertEqual((tx.status, tx.protocolo_rnds), ("transmitido", "p4"))

    @patch("api.services.rnds_fhir.requests.request")
    @patch("api.services.rnds_fhir.requests.get", return_value=_token_ok())
    def test_testar_credencial_so_gera_token(self, mget, mreq):
        from .views_credenciais import api_credenciais_rnds_testar
        emp = _empresa("cred@t.com", "hospital_rede")
        _cred(emp)
        resp = api_credenciais_rnds_testar(self._req(emp))
        corpo = json.loads(resp.content)
        self.assertTrue(corpo["ok"], corpo)
        self.assertEqual(mget.call_args.args[0], AUTH_HMG)
        mreq.assert_not_called()

    def test_configurado_exige_cns_e_uf_em_producao(self):
        emp = _empresa("cfg@t.com", "hospital_rede")
        cred = _cred(emp)
        self.assertTrue(cred.rnds_configurado())
        cred.rnds_cns_profissional = ""
        self.assertIn("CNS do profissional", cred.rnds_pendencias())
        cred.rnds_cns_profissional = CNS
        cred.rnds_ambiente = "producao"
        self.assertFalse(cred.rnds_configurado())
        cred.rnds_uf = "SP"
        self.assertTrue(cred.rnds_configurado())

    def test_salvar_aceita_cns_e_uf_e_rejeita_invalidos(self):
        from .views_credenciais import api_credenciais_rnds_salvar
        emp = _empresa("salvar@t.com", "hospital_rede")
        base = {"cpf_gestor": "11144477735", "cnes": "1234567", "ambiente": "producao"}
        r = api_credenciais_rnds_salvar(self._req(emp, {**base, "cns_profissional": "123"}))
        self.assertEqual(r.status_code, 400)
        r = api_credenciais_rnds_salvar(self._req(emp, {**base, "uf": "XX"}))
        self.assertEqual(r.status_code, 400)
        r = api_credenciais_rnds_salvar(self._req(emp, {**base, "cns_profissional": CNS, "uf": "mg"}))
        self.assertEqual(r.status_code, 200, r.content)
        status = json.loads(r.content)["status"]
        self.assertEqual((status["cns_profissional"], status["uf"]), (CNS, "MG"))
