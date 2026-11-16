"""
ACS: exportação LEDI APS 8.7 (views_governo_acs) e ingestão do PEC
(views_governo_acs_ingestao + integracoes/coletor_pec).
"""
import importlib.util
import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree.ElementTree import fromstring

from django.contrib.auth.hashers import make_password
from django.test import Client, RequestFactory, TestCase, override_settings

from . import views_governo_acs as acs_views
from .models import AgenteComunidadeSaude, ApiKeyEmpresa, Empresa, VisitaDomiciliar

CNS_ACS = "700000000000001"


def _empresa(email, pacote="governo_municipio_pequeno"):
    return Empresa.objects.create(
        nome=f"Municipio {email}", email=email, senha=make_password("x"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote,
        sessao_ativa_chave=f"sessao-{email}",
    )


def _acs(empresa, **kw):
    dados = dict(nome="Ana ACS", cns=CNS_ACS, cnes_usf="1234567", ine_equipe="0000012345",
                 microarea="03", municipio_ibge="3550308")
    dados.update(kw)
    return AgenteComunidadeSaude.objects.create(empresa=empresa, **dados)


def _visita(empresa, acs, **kw):
    dados = dict(paciente_nome="Fulano", cns_paciente="898001234567890", data_visita=date(2026, 11, 10),
                 turno="T", motivo="visita_rotineira", desfecho="visita_realizada")
    dados.update(kw)
    return VisitaDomiciliar.objects.create(empresa=empresa, acs=acs, **dados)


class ExportacaoLediTests(TestCase):
    def setUp(self):
        self.empresa = _empresa("ledi@t.com")
        self.acs = _acs(self.empresa)

    def _pacotes(self, visitas):
        return acs_views.montar_fichas_visita_ledi(visitas, self.empresa)

    def test_codigos_desfecho_turno_e_motivo_seguem_dicionario_ledi(self):
        vs = [
            _visita(self.empresa, self.acs, desfecho="recusou", turno="M"),
            _visita(self.empresa, self.acs, desfecho="ausente", turno="N", motivo="pre_natal"),
            _visita(self.empresa, self.acs, motivo="puericultura", gestante=True),
        ]
        pacotes, pend = self._pacotes(vs)
        self.assertEqual(pend, [])
        filhos = pacotes[0]["ficha"]["visitasDomiciliares"]
        self.assertEqual([f["desfecho"] for f in filhos], [2, 3, 1])
        self.assertEqual([f["turno"] for f in filhos], [1, 3, 2])
        self.assertEqual(filhos[1]["motivosVisita"], [5])
        self.assertEqual(filhos[2]["motivosVisita"], [8, 5])  # gestante soma o motivo 5

    def test_header_envelope_e_versao(self):
        pacotes, _ = self._pacotes([_visita(self.empresa, self.acs)])
        env, ficha = pacotes[0]["envelope"], pacotes[0]["ficha"]
        self.assertEqual(env["tipoDadoSerializado"], 8)
        self.assertEqual(env["versao"], {"major": 8, "minor": 7, "revision": 0})
        self.assertEqual(env["uuidDadoSerializado"], ficha["uuidFicha"])
        self.assertEqual(env["cnesDadoSerializado"], "1234567")
        self.assertEqual(env["codIbge"], "3550308")
        self.assertEqual(env["ineDadoSerializado"], "0000012345")
        self.assertTrue(env["remetente"]["contraChave"].startswith("SoloCRT - "))
        self.assertEqual(ficha["tpCdsOrigem"], 3)
        h = ficha["headerTransport"]
        self.assertEqual((h["profissionalCNS"], h["cboCodigo_2002"], h["cnes"]), (CNS_ACS, "515105", "1234567"))

    def test_data_atendimento_em_epoch_ms(self):
        pacotes, _ = self._pacotes([_visita(self.empresa, self.acs, data_visita=date(2026, 11, 10))])
        # 10/11/2026 00:00 em America/Sao_Paulo (UTC-3)
        self.assertEqual(pacotes[0]["ficha"]["headerTransport"]["dataAtendimento"], 1794279600000)

    def test_quebra_em_fichas_de_ate_99_visitas(self):
        vs = [_visita(self.empresa, self.acs) for _ in range(150)]
        pacotes, _ = self._pacotes(vs)
        self.assertEqual([len(p["ficha"]["visitasDomiciliares"]) for p in pacotes], [99, 51])

    def test_um_header_por_profissional_e_dia(self):
        outro = _acs(self.empresa, nome="Bia", cns="700000000000002")
        vs = [_visita(self.empresa, self.acs), _visita(self.empresa, outro),
              _visita(self.empresa, self.acs, data_visita=date(2026, 11, 11))]
        pacotes, _ = self._pacotes(vs)
        self.assertEqual(len(pacotes), 3)

    def test_visita_sem_cns_do_acs_fica_de_fora_com_pendencia(self):
        sem_cns = _acs(self.empresa, nome="Sem CNS", cns="")
        pacotes, pend = self._pacotes([_visita(self.empresa, sem_cns)])
        self.assertEqual(pacotes, [])
        self.assertEqual(pend[0]["faltando"], ["CNS do ACS"])

    def test_zip_tem_um_esus_por_ficha_com_xml_dos_campos_oficiais(self):
        vs = [_visita(self.empresa, self.acs) for _ in range(100)]
        pacotes, _ = self._pacotes(vs)
        with zipfile.ZipFile(io.BytesIO(acs_views.empacotar_zip_esus(pacotes))) as zf:
            nomes = sorted(zf.namelist())
            self.assertEqual(nomes, sorted(f"{p['envelope']['uuidDadoSerializado']}.esus" for p in pacotes))
            raiz = fromstring(zf.read(nomes[0]))
        self.assertEqual(raiz.tag, "DadoTransporte")
        self.assertEqual(raiz.findtext("tipoDadoSerializado"), "8")
        ficha = raiz.find("dadoSerializado/FichaVisitaDomiciliarMaster")
        self.assertIsNotNone(ficha.find("headerTransport/profissionalCNS"))
        self.assertTrue(len(ficha.findall("visitasDomiciliares")) in (1, 99))

    def test_endpoint_exporta_zip_e_ignora_visitas_vindas_do_pec(self):
        _visita(self.empresa, self.acs)
        _visita(self.empresa, self.acs, origem="pec", uuid_origem="pec:1", transmitido_esus=False)
        r = RequestFactory().get("/")
        r.empresa, r.principal = self.empresa, None
        resp = acs_views.api_visitas_exportar_cds(r)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            raiz = fromstring(zf.read(zf.namelist()[0]))
        self.assertEqual(len(raiz.findall("dadoSerializado/FichaVisitaDomiciliarMaster/visitasDomiciliares")), 1)


@override_settings(RATE_LIMIT_PUBLICO_ENABLED=False)
class IngestaoPecTests(TestCase):
    URL = "/api/governo/acs/ingestao/visitas"

    def setUp(self):
        self.client = Client()
        self.muni_a = _empresa("pec-a@t.com")
        self.muni_b = _empresa("pec-b@t.com")
        _, self.chave_a = ApiKeyEmpresa.criar_para(self.muni_a, "coletor PEC")
        _, self.chave_b = ApiKeyEmpresa.criar_para(self.muni_b, "coletor PEC")

    def _post(self, visitas, chave=None, **extra):
        headers = {"HTTP_AUTHORIZATION": f"ApiKey {chave}"} if chave else {}
        return self.client.post(self.URL, data=json.dumps({"visitas": visitas}),
                                content_type="application/json", **headers, **extra)

    def _item(self, **kw):
        item = {"uuid_origem": "pec:1234567:1", "acs_cns": CNS_ACS, "acs_nome": "Ana",
                "cnes": "1234567", "data_visita": "2026-11-10", "turno": 2, "desfecho": 1,
                "motivos": [29], "cns_paciente": "898001234567890"}
        item.update(kw)
        return item

    def test_sem_chave_ou_chave_errada_recebe_401(self):
        self.assertEqual(self._post([self._item()]).status_code, 401)
        self.assertEqual(self._post([self._item()], chave="errada").status_code, 401)
        self.assertEqual(VisitaDomiciliar.objects.count(), 0)

    def test_chave_revogada_recebe_401(self):
        ApiKeyEmpresa.objects.filter(empresa=self.muni_a).update(ativa=False)
        self.assertEqual(self._post([self._item()], chave=self.chave_a).status_code, 401)

    def test_cria_visita_pec_ja_marcada_como_transmitida(self):
        resp = self._post([self._item(motivos=[5, 29])], chave=self.chave_a)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["criadas"], 1)
        v = VisitaDomiciliar.objects.get()
        self.assertEqual((v.origem, v.transmitido_esus, v.turno, v.motivo, v.gestante),
                         ("pec", True, "T", "pre_natal", True))
        self.assertEqual(v.empresa_id, self.muni_a.id)

    def test_reenvio_do_mesmo_uuid_atualiza_sem_duplicar(self):
        self._post([self._item()], chave=self.chave_a)
        resp = self._post([self._item(desfecho=3)], chave=self.chave_a)
        self.assertEqual((resp.json()["criadas"], resp.json()["atualizadas"]), (0, 1))
        self.assertEqual(VisitaDomiciliar.objects.count(), 1)
        self.assertEqual(VisitaDomiciliar.objects.get().desfecho, "ausente")

    def test_acs_e_reconhecido_pelo_cns(self):
        acs = _acs(self.muni_a)
        self._post([self._item(), self._item(uuid_origem="pec:1234567:2")], chave=self.chave_a)
        self.assertEqual(AgenteComunidadeSaude.objects.filter(empresa=self.muni_a).count(), 1)
        self.assertEqual(set(VisitaDomiciliar.objects.values_list("acs_id", flat=True)), {acs.id})

    def test_acs_desconhecido_e_criado_dentro_da_propria_empresa(self):
        self._post([self._item(acs_cns="700000000000009")], chave=self.chave_a)
        acs = AgenteComunidadeSaude.objects.get(cns="700000000000009")
        self.assertEqual(acs.empresa_id, self.muni_a.id)

    def test_chave_de_b_nunca_escreve_em_a(self):
        acs_a = _acs(self.muni_a)
        self._post([self._item()], chave=self.chave_a)
        self._post([self._item()], chave=self.chave_b)
        self.assertEqual(VisitaDomiciliar.objects.filter(empresa=self.muni_a).count(), 1)
        v_b = VisitaDomiciliar.objects.get(empresa=self.muni_b)
        self.assertNotEqual(v_b.acs_id, acs_a.id)
        self.assertEqual(v_b.acs.empresa_id, self.muni_b.id)

    def test_lote_acima_do_limite_recebe_413(self):
        itens = [self._item(uuid_origem=f"pec:x:{i}") for i in range(501)]
        self.assertEqual(self._post(itens, chave=self.chave_a).status_code, 413)

    def test_itens_invalidos_sao_rejeitados_com_motivo_e_os_validos_entram(self):
        futuro = (date.today() + timedelta(days=10)).isoformat()
        itens = [
            self._item(),
            self._item(uuid_origem="pec:2", acs_cns="123"),
            self._item(uuid_origem="pec:3", data_visita=futuro),
            self._item(uuid_origem="pec:4", turno=9),
            self._item(uuid_origem="tem espaço"),
            self._item(uuid_origem="pec:5", motivos=["29"]),
        ]
        body = self._post(itens, chave=self.chave_a).json()
        self.assertEqual(body["criadas"], 1)
        self.assertEqual(sorted(r["indice"] for r in body["rejeitadas"]), [1, 2, 3, 4, 5])
        self.assertTrue(all(r["motivo"] for r in body["rejeitadas"]))

    def test_segmento_que_nao_e_governo_recebe_403(self):
        farmacia = _empresa("farm@t.com", pacote="farmacia_local")
        _, chave = ApiKeyEmpresa.criar_para(farmacia, "x")
        self.assertEqual(self._post([self._item()], chave=chave).status_code, 403)

    def test_json_invalido_recebe_400(self):
        resp = self.client.post(self.URL, data="{nao json", content_type="application/json",
                                HTTP_AUTHORIZATION=f"ApiKey {self.chave_a}")
        self.assertEqual(resp.status_code, 400)


def _carregar_coletor():
    caminho = Path(__file__).resolve().parent.parent / "integracoes" / "coletor_pec" / "coletor_pec.py"
    spec = importlib.util.spec_from_file_location("coletor_pec", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ColetorPecMapeamentoTests(TestCase):
    def setUp(self):
        self.c = _carregar_coletor()

    def _schema_completo(self):
        return {
            "tb_fat_visita_domiciliar": {"co_seq_fat_visita_domiciliar", "co_dim_profissional", "co_dim_tempo",
                                         "co_dim_unidade_saude", "co_dim_turno", "ds_filtro_motivo_visita",
                                         "nu_cns", "coluna_nova_desconhecida"},
            "tb_dim_profissional": {"co_seq_dim_profissional", "nu_cns", "no_profissional"},
            "tb_dim_tempo": {"co_seq_dim_tempo", "dt_registro"},
            "tb_dim_unidade_saude": {"co_seq_dim_unidade_saude", "nu_cnes"},
        }

    def test_mapeia_colunas_existentes_e_ignora_as_ausentes(self):
        mapa, faltando = self.c.mapear_colunas(self._schema_completo())
        self.assertEqual(faltando, [])
        self.assertEqual(mapa["pk"], ("tb_fat_visita_domiciliar", "co_seq_fat_visita_domiciliar"))
        self.assertEqual(mapa["motivos"][1], "ds_filtro_motivo_visita")
        self.assertNotIn("peso", mapa)
        self.assertNotIn("equipe_ine", mapa)
        sql = self.c.montar_sql(mapa)
        self.assertIn('JOIN "tb_dim_tempo"', sql)
        self.assertNotIn("tb_dim_equipe", sql)

    def test_aponta_o_que_falta_sem_quebrar(self):
        schema = self._schema_completo()
        del schema["tb_dim_tempo"]
        schema["tb_dim_profissional"] = {"co_seq_dim_profissional"}
        _, faltando = self.c.mapear_colunas(schema)
        self.assertIn("prof_cns", faltando)
        self.assertTrue(any("data da visita" in f for f in faltando))

    def test_linha_vira_item_valido_para_a_api(self):
        item = self.c.linha_para_item({"pk": 42, "acs_cns": CNS_ACS, "data_visita": date(2026, 11, 10),
                                       "cnes": "1234567", "turno": 2, "motivos": "|5|29|", "peso": None})
        self.assertEqual(item["uuid_origem"], "pec:1234567:42")
        self.assertEqual(item["motivos"], [5, 29])
        self.assertEqual(item["turno"], 2)
        from .views_governo_acs_ingestao import validar_item
        validar_item(item)

    def test_linha_sem_cns_valido_e_descartada(self):
        self.assertIsNone(self.c.linha_para_item({"pk": 1, "acs_cns": "123", "data_visita": date(2026, 1, 1)}))
