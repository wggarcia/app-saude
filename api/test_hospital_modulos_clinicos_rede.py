"""
Testes dos módulos clínicos hospitalares REDE-exclusivos construídos na
auditoria de jun/2026: CCIH, Hemoterapia, Obstétrico, Oncologia e OPME.

Cobre, para cada módulo: gate de feature na página (bloqueado no tier base
hospital_medio, liberado no tier hospital_rede) e um roundtrip básico de
criação via API no tier liberado.
"""
import warnings
from datetime import date, datetime, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, CatalogoOPME, AutorizacaoOPME, ImplantavelRegistro, ProtocoloOncologico,
    IndicacaoClinicaOPME, ReacaoTransfusional, TransfusaoPaciente,
)


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id,
        "principal_kind": "empresa",
        "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave,
        "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _client_usuario(empresa, usuario):
    """Client autenticado como um EmpresaUsuario nominal (não a conta corporativa),
    para testar segregação de visão gerência × usuário clínico comum."""
    client = Client()
    payload = {
        "empresa_id": empresa.id,
        "principal_kind": "usuario_empresa",
        "principal_id": usuario.id,
        "session_key": empresa.sessao_ativa_chave,
        "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa(nome, email, pacote_codigo):
    return Empresa.objects.create(
        nome=nome,
        email=email,
        senha=make_password("123456"),
        ativo=True,
        pacote_codigo=pacote_codigo,
        sessao_ativa_chave=f"sessao-{email}",
    )


class CCIHTests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("Hospital Base", "ccih-base@example.com", "hospital_medio")
        client = _client_for(empresa)
        self.assertEqual(client.get("/hospital/ccih/").status_code, 403)

    def test_pagina_liberada_no_tier_rede_e_cria_infeccao_e_isolamento(self):
        empresa = _empresa("Hospital Rede", "ccih-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/ccih/").status_code, 200)

        r = client.post(
            "/api/hospital/ccih/infeccoes/",
            data={"paciente_nome": "Paciente CCIH", "topografia": "itu"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        infeccao_id = r.json()["id"]

        r = client.get("/api/hospital/ccih/infeccoes/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)

        r = client.post(
            "/api/hospital/ccih/isolamentos/",
            data={
                "infeccao_id": infeccao_id,
                "paciente_nome": "Paciente CCIH",
                "leito": "101A",
                "tipo": "contato",
                "motivo": "MRSA",
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.get("/api/hospital/ccih/kpis/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["isolamentos_ativos"], 1)


class HemoterapiaTests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("Hospital Base", "hemo-base@example.com", "hospital_medio")
        client = _client_for(empresa)
        self.assertEqual(client.get("/hospital/hemoterapia/").status_code, 403)

    def test_pagina_liberada_e_cria_bolsa(self):
        empresa = _empresa("Hospital Rede", "hemo-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/hemoterapia/").status_code, 200)

        r = client.post(
            "/api/hospital/hemoterapia/bolsas/",
            data={
                "codigo_bolsa": "BS-0001",
                "tipo": "ch",
                "tipo_abo": "O",
                "fator_rh": "+",
                "volume_ml": 280,
                "validade": (date.today() + timedelta(days=30)).isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.get("/api/hospital/hemoterapia/bolsas/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)

        r = client.get("/api/hospital/hemoterapia/kpis/")
        self.assertEqual(r.status_code, 200)

    def test_horario_da_reacao_nao_desloca_com_use_tz(self):
        """Regressão: a hora da transfusão/reação é dado clínico (RDC 34/2014).

        O formulário manda `datetime-local` sem fuso. Antes, o valor ingênuo
        era gravado como se fosse UTC e voltava 3h deslocado em produção
        (Brasil em UTC-3), além de emitir RuntimeWarning do Django.
        """
        empresa = _empresa("Hospital TZ", "hemo-tz@example.com", "hospital_rede")
        client = _client_for(empresa)

        r = client.post(
            "/api/hospital/hemoterapia/bolsas/",
            data={
                "codigo_bolsa": "BS-TZ-01",
                "tipo": "ch",
                "tipo_abo": "A",
                "fator_rh": "+",
                "volume_ml": 300,
                "validade": (date.today() + timedelta(days=20)).isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        bolsa_id = r.json()["id"]

        # Exatamente o que o <input type="datetime-local"> envia: sem fuso.
        quando = "2026-03-12T14:30"

        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")

            r = client.post(
                "/api/hospital/hemoterapia/transfusoes/",
                data={
                    "bolsa_id": bolsa_id,
                    "paciente_nome": "Paciente TZ",
                    "data_inicio": quando,
                    "volume_ml": 300,
                },
                content_type="application/json",
            )
            self.assertEqual(r.status_code, 201)
            transfusao_id = r.json()["id"]

            r = client.post(
                "/api/hospital/hemoterapia/reacoes/",
                data={
                    "transfusao_id": transfusao_id,
                    "paciente_nome": "Paciente TZ",
                    "tipo_reacao": "febre",
                    "gravidade": "leve",
                    "data_reacao": quando,
                    "descricao": "Pico febril 38,4 °C durante a infusão.",
                },
                content_type="application/json",
            )
            self.assertEqual(r.status_code, 201)
            reacao_id = r.json()["id"]

            # O KPI mensal filtra por data_reacao — não pode comparar date com
            # DateTimeField e disparar o aviso.
            self.assertEqual(client.get("/api/hospital/hemoterapia/kpis/").status_code, 200)

        ingenuos = [str(w.message) for w in capturados
                    if "naive datetime" in str(w.message)]
        self.assertEqual(ingenuos, [], f"datetime ingênuo gravado: {ingenuos}")

        reacao = ReacaoTransfusional.objects.get(id=reacao_id)
        transfusao = TransfusaoPaciente.objects.get(id=transfusao_id)

        self.assertIsNotNone(reacao.data_reacao.tzinfo)
        self.assertIsNotNone(transfusao.data_inicio.tzinfo)

        local_reacao = timezone.localtime(reacao.data_reacao)
        self.assertEqual((local_reacao.hour, local_reacao.minute), (14, 30))
        self.assertEqual(local_reacao.date(), date(2026, 3, 12))

        local_transfusao = timezone.localtime(transfusao.data_inicio)
        self.assertEqual((local_transfusao.hour, local_transfusao.minute), (14, 30))

        # E a API devolve o mesmo horário que o cliente mandou.
        r = client.get("/api/hospital/hemoterapia/reacoes/")
        self.assertEqual(r.status_code, 200)
        devolvido = r.json()["reacoes"][0]["data_reacao"]
        self.assertEqual(timezone.localtime(
            datetime.fromisoformat(devolvido)).strftime("%Y-%m-%d %H:%M"),
            "2026-03-12 14:30")

    def test_data_da_reacao_omitida_usa_agora_com_fuso(self):
        """Sem data_reacao no payload, o default também precisa vir com fuso."""
        empresa = _empresa("Hospital TZ2", "hemo-tz2@example.com", "hospital_rede")
        client = _client_for(empresa)

        r = client.post(
            "/api/hospital/hemoterapia/reacoes/",
            data={
                "paciente_nome": "Paciente Sem Data",
                "tipo_reacao": "alergica_leve",
                "gravidade": "leve",
                "descricao": "Urticária localizada.",
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        reacao = ReacaoTransfusional.objects.get(id=r.json()["id"])
        self.assertIsNotNone(reacao.data_reacao.tzinfo)
        self.assertLess(abs((timezone.now() - reacao.data_reacao).total_seconds()), 120)


class ObstetricoTests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("Hospital Base", "obst-base@example.com", "hospital_medio")
        client = _client_for(empresa)
        self.assertEqual(client.get("/hospital/obstetrico/").status_code, 403)

    def test_pagina_liberada_e_cria_partograma_e_parto(self):
        empresa = _empresa("Hospital Rede", "obst-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/obstetrico/").status_code, 200)

        r = client.post(
            "/api/hospital/obstetrico/partogramas/",
            data={
                "paciente_nome": "Gestante Teste",
                "data_internacao": timezone.now().isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.post(
            "/api/hospital/obstetrico/partos/",
            data={
                "mae_nome": "Gestante Teste",
                "tipo_parto": "normal",
                "data_parto": timezone.now().isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.get("/api/hospital/obstetrico/partogramas/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)


class OncologiaTests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("Hospital Base", "onco-base@example.com", "hospital_medio")
        client = _client_for(empresa)
        self.assertEqual(client.get("/hospital/oncologia/").status_code, 403)

    def _protocolo(self, empresa, drogas=None, ciclos=12, intervalo=14):
        return ProtocoloOncologico.objects.create(
            empresa=empresa, codigo="FOLFOX-6-TESTE", nome="FOLFOX-6",
            ciclos_total=ciclos, intervalo_dias=intervalo,
            drogas=drogas or [{"droga": "Oxaliplatina", "dose": 85, "unidade": "mg/m²", "dia": 1}],
        )

    def test_pagina_liberada_e_cria_ciclo_e_apac(self):
        empresa = _empresa("Hospital Rede", "onco-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/oncologia/").status_code, 200)

        protocolo = self._protocolo(empresa)

        r = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={
                "protocolo_id": protocolo.id,
                "paciente_nome": "Paciente Onco",
                "cid10_principal": "C18",
                "data_inicio": date.today().isoformat(),
                "peso_kg": 70, "altura_cm": 170,
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        # SC DuBois de 70kg/170cm ≈ 1.81 m²
        self.assertAlmostEqual(body["sc_m2"], 1.81, places=1)
        # dose calculada = 85 mg/m² × SC
        self.assertTrue(body["doses_calculadas"])
        self.assertIsNotNone(body["doses_calculadas"][0]["dose_calculada"])

        r = client.post(
            "/api/hospital/oncologia/apacs/",
            data={"paciente_nome": "Paciente Onco", "cid10_principal": "C18"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["numero_apac"])  # número gerado

        r = client.get("/api/hospital/oncologia/ciclos/")
        self.assertEqual(r.status_code, 200)

    # ══ Resposta ao tratamento — RECIST 1.1 ═══════════════════════════════════
    def _aval(self, client, **extra):
        payload = {"paciente_nome": "Paciente Onco",
                   "data_avaliacao": date.today().isoformat(), "metodo": "tc"}
        payload.update(extra)
        return client.post("/api/hospital/oncologia/respostas/",
                           data=payload, content_type="application/json")

    def test_recist_regua_pura(self):
        """A régua, isolada, antes de qualquer HTTP."""
        from api.views_hospital_oncologia import _classificar_recist
        # redução de 40% vs basal → resposta parcial
        r, vb, vn = _classificar_recist(60, 100, 100)
        self.assertEqual(r, "rp"); self.assertEqual(vb, -40.0)
        # estável: caiu só 10%
        self.assertEqual(_classificar_recist(90, 100, 100)[0], "de")
        # progressão medida contra o NADIR, não contra a basal:
        # basal 100, nadir 40, atual 60 → ainda 40% abaixo da basal, mas +50%
        # sobre o nadir e +20 mm → progressão
        r2, vb2, vn2 = _classificar_recist(60, 100, 40)
        self.assertEqual(r2, "dp"); self.assertEqual(vb2, -40.0); self.assertEqual(vn2, 50.0)
        # aumento percentual grande mas absoluto < 5 mm não é progressão
        self.assertEqual(_classificar_recist(12, 100, 10)[0], "rp")
        # lesão nova é progressão mesmo com tumor menor
        self.assertEqual(_classificar_recist(10, 100, 100, lesoes_novas=True)[0], "dp")
        # desaparecimento total é resposta completa
        self.assertEqual(
            _classificar_recist(0, 100, 100, desaparecimento_total=True)[0], "rc")
        # sem basal não dá para julgar
        self.assertEqual(_classificar_recist(50, None, None)[0], "ne")

    def test_resposta_exige_basal_antes(self):
        empresa = _empresa("Hospital Rede", "onco-rc1@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._aval(client, soma_lesoes_mm=80)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "sem_basal")

    def test_basal_depois_resposta_parcial(self):
        empresa = _empresa("Hospital Rede", "onco-rc2@example.com", "hospital_rede")
        client = _client_for(empresa)
        b = self._aval(client, basal=True, soma_lesoes_mm=100)
        self.assertEqual(b.status_code, 201, b.content)
        self.assertEqual(b.json()["avaliacao"]["resposta"], "ne")
        r = self._aval(client, soma_lesoes_mm=60)
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()["avaliacao"]
        self.assertEqual(d["resposta"], "rp")
        self.assertEqual(d["variacao_vs_basal_pct"], -40.0)
        self.assertTrue(d["resposta_automatica"])

    def test_progressao_contra_nadir(self):
        """Tumor encolheu muito e voltou a crescer: é progressão mesmo abaixo da basal."""
        empresa = _empresa("Hospital Rede", "onco-rc3@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._aval(client, basal=True, soma_lesoes_mm=100)
        self._aval(client, soma_lesoes_mm=40)   # nadir
        r = self._aval(client, soma_lesoes_mm=60)
        d = r.json()["avaliacao"]
        self.assertEqual(d["resposta"], "dp")
        self.assertEqual(d["variacao_vs_nadir_pct"], 50.0)

    def test_lesao_nova_e_progressao(self):
        empresa = _empresa("Hospital Rede", "onco-rc4@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._aval(client, basal=True, soma_lesoes_mm=100)
        r = self._aval(client, soma_lesoes_mm=10, lesoes_novas=True)
        self.assertEqual(r.json()["avaliacao"]["resposta"], "dp")

    def test_override_sem_justificativa_recusado(self):
        empresa = _empresa("Hospital Rede", "onco-rc5@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._aval(client, basal=True, soma_lesoes_mm=100)
        r = self._aval(client, soma_lesoes_mm=60, resposta="de")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "override_sem_justificativa")
        self.assertEqual(r.json()["resposta_calculada"], "rp")

    def test_override_com_justificativa_fica_marcado(self):
        empresa = _empresa("Hospital Rede", "onco-rc6@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._aval(client, basal=True, soma_lesoes_mm=100)
        r = self._aval(client, soma_lesoes_mm=60, resposta="de",
                       justificativa="Lesão medida inclui componente cístico.")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()["avaliacao"]
        self.assertEqual(d["resposta"], "de")
        self.assertFalse(d["resposta_automatica"])

    def test_metodo_invalido_recusado(self):
        empresa = _empresa("Hospital Rede", "onco-rc7@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._aval(client, basal=True, soma_lesoes_mm=100, metodo="bola-de-cristal")
        self.assertEqual(r.status_code, 400)

    def test_avaliacao_nao_vaza_entre_empresas(self):
        e1 = _empresa("Hospital Rede", "onco-rc8@example.com", "hospital_rede")
        e2 = _empresa("Hospital Rede", "onco-rc9@example.com", "hospital_rede")
        c1, c2 = _client_for(e1), _client_for(e2)
        self._aval(c1, basal=True, soma_lesoes_mm=100)
        self.assertEqual(c2.get("/api/hospital/oncologia/respostas/").json()["total"], 0)
        # e a basal de e1 não serve de base para e2
        r = self._aval(c2, soma_lesoes_mm=60)
        self.assertEqual(r.status_code, 400)

    def test_jornada_inclui_o_desfecho(self):
        """'Da guia ao desfecho': a avaliação de resposta entra na linha do tempo."""
        empresa = _empresa("Hospital Rede", "onco-rc10@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._aval(client, basal=True, soma_lesoes_mm=100)
        self._aval(client, soma_lesoes_mm=60)
        r = client.get("/api/hospital/oncologia/jornada/?nome=Paciente Onco")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertIn("resposta", [e["tipo"] for e in d["timeline"]])
        self.assertEqual(d["resumo"]["resposta"], 2)
        self.assertEqual(d["desfecho_atual"], "Resposta parcial")

    # ══ Relógio regulatório da autorização (ANS RN 623/2024 — 5 dias úteis) ═══
    def _guia(self, client, **extra):
        payload = {
            "numero_guia": "G-1", "paciente_nome": "Paciente Onco",
            "data_emissao": date.today().isoformat(),
            "data_validade": (date.today() + timedelta(days=90)).isoformat(),
            "ciclos_autorizados": 6,
        }
        payload.update(extra)
        return client.post("/api/hospital/oncologia/guias/",
                           data=payload, content_type="application/json")

    def test_dias_uteis_ignora_fim_de_semana(self):
        from api.views_hospital_oncologia import _dias_uteis_entre
        # sexta 2026-01-02 → segunda 2026-01-05 = 1 dia útil
        self.assertEqual(_dias_uteis_entre(date(2026, 1, 2), date(2026, 1, 5)), 1)
        # segunda → sexta da mesma semana = 4 dias úteis
        self.assertEqual(_dias_uteis_entre(date(2026, 1, 5), date(2026, 1, 9)), 4)
        self.assertEqual(_dias_uteis_entre(date(2026, 1, 5), date(2026, 1, 5)), 0)

    def test_prazo_estourado_aparece_no_alerta(self):
        empresa = _empresa("Hospital Rede", "onco-pz1@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._guia(client, status="em_analise",
                       data_solicitacao=(date.today() - timedelta(days=20)).isoformat())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["guia"]["prazo_resposta"]["estourado"])
        a = client.get("/api/hospital/oncologia/guias/alertas/").json()
        self.assertEqual(a["total_prazo_resposta_estourado"], 1)

    def test_prazo_dentro_nao_alerta(self):
        empresa = _empresa("Hospital Rede", "onco-pz2@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._guia(client, numero_guia="G-2", status="em_analise",
                   data_solicitacao=date.today().isoformat())
        a = client.get("/api/hospital/oncologia/guias/alertas/").json()
        self.assertEqual(a["total_prazo_resposta_estourado"], 0)

    def test_guia_respondida_para_o_relogio(self):
        """Depois de respondida, o relógio mede o que levou e não alerta mais."""
        empresa = _empresa("Hospital Rede", "onco-pz3@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._guia(client, numero_guia="G-3",
                       data_solicitacao=(date.today() - timedelta(days=30)).isoformat(),
                       data_resposta=(date.today() - timedelta(days=28)).isoformat())
        p = r.json()["guia"]["prazo_resposta"]
        self.assertTrue(p["respondida"])
        a = client.get("/api/hospital/oncologia/guias/alertas/").json()
        self.assertEqual(a["total_prazo_resposta_estourado"], 0)

    def test_negativa_exige_motivo_valido(self):
        empresa = _empresa("Hospital Rede", "onco-pz4@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._guia(client, numero_guia="G-4", status="negada",
                       motivo_negativa="inventado")
        self.assertEqual(r.status_code, 400)
        self.assertIn("validos", r.json())

    def test_negativa_com_motivo_estruturado(self):
        empresa = _empresa("Hospital Rede", "onco-pz5@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._guia(client, numero_guia="G-5", status="negada",
                       motivo_negativa="dut",
                       motivo_negativa_detalhe="Não cumpre a DUT do rol vigente.")
        self.assertEqual(r.status_code, 201, r.content)
        g = r.json()["guia"]
        self.assertEqual(g["motivo_negativa"], "dut")
        self.assertIn("Diretriz de Utilização", g["motivo_negativa_display"])

    def test_guia_em_analise_nao_vira_vigente_sozinha(self):
        """Regressão: autorização pendente não pode ser tratada como concedida."""
        empresa = _empresa("Hospital Rede", "onco-pz6@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._guia(client, numero_guia="G-6", status="em_analise",
                       data_solicitacao=date.today().isoformat())
        self.assertEqual(r.json()["guia"]["status"], "em_analise")

    def test_kpi_conta_autorizacoes_estouradas(self):
        empresa = _empresa("Hospital Rede", "onco-pz7@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._guia(client, numero_guia="G-7", status="em_analise",
                   data_solicitacao=(date.today() - timedelta(days=20)).isoformat())
        k = client.get("/api/hospital/oncologia/kpis/").json()
        self.assertEqual(k["autorizacoes_prazo_estourado"], 1)
        self.assertEqual(k["autorizacoes_aguardando_resposta"], 1)

    # ══ Pré-medicação e suporte ═══════════════════════════════════════════════
    def test_protocolos_semeados_tem_pre_medicacao(self):
        """Nenhum esquema real existe só com antineoplásico."""
        empresa = _empresa("Hospital Rede", "onco-sup1@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.get("/api/hospital/oncologia/protocolos/")
        self.assertEqual(r.status_code, 200)
        por_codigo = {p["codigo"]: p for p in r.json()["protocolos"]}
        for cod in ("FOLFOX-6", "FOLFIRI", "AC-T", "BEP", "CHOP"):
            self.assertTrue(por_codigo[cod]["drogas_suporte"],
                            f"{cod} sem pré-medicação")
        # BEP carrega cisplatina: exige função renal melhor que o padrão
        self.assertEqual(por_codigo["BEP"]["criterios_aptidao"]["clearance_min"], 60)
        self.assertFalse(por_codigo["BEP"]["criterios_sao_padrao"])
        # FOLFOX usa o padrão seguro
        self.assertTrue(por_codigo["FOLFOX-6"]["criterios_sao_padrao"])

    def test_bep_hidratacao_na_pre_medicacao(self):
        """Cisplatina sem hiper-hidratação é nefrotoxicidade programada."""
        empresa = _empresa("Hospital Rede", "onco-sup2@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.get("/api/hospital/oncologia/protocolos/")
        bep = [p for p in r.json()["protocolos"] if p["codigo"] == "BEP"][0]
        nomes = " ".join(d["droga"] for d in bep["drogas_suporte"]).lower()
        self.assertIn("fisiológico", nomes)

    def test_ciclo_devolve_pre_medicacao_do_protocolo(self):
        empresa = _empresa("Hospital Rede", "onco-sup3@example.com", "hospital_rede")
        client = _client_for(empresa)
        from api.models import ProtocoloOncologico
        p = ProtocoloOncologico.objects.create(
            empresa=empresa, codigo="X1", nome="X1", ciclos_total=4, intervalo_dias=21,
            drogas=[{"droga": "Oxaliplatina", "dose": 85, "unidade": "mg/m²", "dia": 1}],
            drogas_suporte=[{"droga": "Ondansetrona", "dose": 8, "unidade": "mg",
                             "via": "EV", "momento": "30 min antes"}])
        r = self._criar_ciclo(client, p, neutrofilos=3000, plaquetas=250000)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["pre_medicacao"][0]["droga"], "Ondansetrona")

    def test_protocolo_proprio_aceita_suporte_e_criterios(self):
        empresa = _empresa("Hospital Rede", "onco-sup4@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post("/api/hospital/oncologia/protocolos/", data={
            "codigo": "MEU-1", "nome": "Protocolo da Casa",
            "drogas": [{"droga": "Cisplatina", "dose": 75, "unidade": "mg/m²", "dia": 1}],
            "drogas_suporte": [{"droga": "Ondansetrona", "dose": 8, "unidade": "mg",
                                "via": "EV", "momento": "30 min antes"}],
            "criterios_aptidao": {"neutrofilos_min": 2000},
        }, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        from api.models import ProtocoloOncologico
        p = ProtocoloOncologico.objects.get(id=r.json()["id"])
        self.assertEqual(p.criterios_aptidao["neutrofilos_min"], 2000)
        self.assertTrue(p.drogas_suporte)

    # ══ Segurança clínica do ciclo ════════════════════════════════════════════
    def _criar_ciclo(self, client, protocolo, **extra):
        payload = {
            "protocolo_id": protocolo.id,
            "paciente_nome": "Paciente Onco",
            "cid10_principal": "C18",
            "data_inicio": date.today().isoformat(),
            "peso_kg": 70, "altura_cm": 170,
        }
        payload.update(extra)
        return client.post("/api/hospital/oncologia/ciclos/",
                           data=payload, content_type="application/json")

    def test_aptidao_inapto_quando_neutropenico(self):
        """Neutrófilo abaixo do limiar: o ciclo é REGISTRADO (o médico nunca é
        bloqueado), mas sai marcado como inapto e com o motivo gravado."""
        empresa = _empresa("Hospital Rede", "onco-apt1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo, neutrofilos=300, plaquetas=200000)
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual(d["aptidao"]["status"], "inapto")
        self.assertTrue(any("Neutrófilos" in b for b in d["aptidao"]["bloqueios"]))
        self.assertTrue(any("INAPTO" in a for a in d["alertas"]))
        from api.models import CicloQuimioterapia
        self.assertEqual(
            CicloQuimioterapia.objects.get(id=d["id"]).aptidao_status, "inapto")

    def test_aptidao_inapto_quando_plaquetopenico(self):
        empresa = _empresa("Hospital Rede", "onco-apt2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo, neutrofilos=2000, plaquetas=40000)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["aptidao"]["status"], "inapto")

    def test_aptidao_apta_com_hemograma_normal(self):
        empresa = _empresa("Hospital Rede", "onco-apt3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo, neutrofilos=3000, plaquetas=250000)
        self.assertEqual(r.json()["aptidao"]["status"], "apto")

    def test_aptidao_ressalva_no_limite(self):
        """Logo acima do limiar acende ressalva, não bloqueio."""
        empresa = _empresa("Hospital Rede", "onco-apt4@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo, neutrofilos=1600, plaquetas=250000)
        self.assertEqual(r.json()["aptidao"]["status"], "apto_ressalva")

    def test_aptidao_nao_avaliada_sem_hemograma(self):
        """Sem exame não finge veredito — mesma honestidade da adequação clínica."""
        empresa = _empresa("Hospital Rede", "onco-apt5@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo)
        self.assertEqual(r.json()["aptidao"]["status"], "nao_avaliado")

    def test_protocolo_pode_apertar_limiar(self):
        """Protocolo com critério próprio prevalece sobre o padrão."""
        empresa = _empresa("Hospital Rede", "onco-apt6@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        protocolo.criterios_aptidao = {"neutrofilos_min": 3000}
        protocolo.save(update_fields=["criterios_aptidao"])
        r = self._criar_ciclo(client, protocolo, neutrofilos=2000, plaquetas=250000)
        self.assertEqual(r.json()["aptidao"]["status"], "inapto")

    def test_liberacao_medica_fica_registrada(self):
        empresa = _empresa("Hospital Rede", "onco-apt7@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(
            client, protocolo, neutrofilos=300, plaquetas=200000,
            aptidao_liberada_por="Dra. Oncologista",
            aptidao_justificativa="Tumor de crescimento rápido; risco de atraso supera o risco hematológico.")
        self.assertEqual(r.status_code, 201)
        from api.models import CicloQuimioterapia
        c = CicloQuimioterapia.objects.get(id=r.json()["id"])
        self.assertEqual(c.aptidao_liberada_por, "Dra. Oncologista")
        self.assertIn("crescimento rápido", c.aptidao_justificativa)

    # ══ Carboplatina por AUC (Calvert) ════════════════════════════════════════
    def test_carboplatina_dose_por_calvert(self):
        """Carboplatina não é dosada por superfície corporal: AUC × (TFG + 25)."""
        empresa = _empresa("Hospital Rede", "onco-auc1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa, drogas=[
            {"droga": "Carboplatina", "dose": 5, "unidade": "AUC", "dia": 1}])
        r = self._criar_ciclo(client, protocolo, clearance_creatinina=80,
                              neutrofilos=3000, plaquetas=250000)
        self.assertEqual(r.status_code, 201, r.content)
        item = r.json()["doses_calculadas"][0]
        # 5 × (80 + 25) = 525 mg
        self.assertAlmostEqual(item["dose_calculada"], 525.0, places=1)
        self.assertEqual(item["unidade_calculada"], "mg")
        self.assertIn("Calvert", item["formula"])

    def test_carboplatina_teto_de_tfg(self):
        """Clearance acima do teto fisiológico não pode inflar a dose."""
        empresa = _empresa("Hospital Rede", "onco-auc2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa, drogas=[
            {"droga": "Carboplatina", "dose": 6, "unidade": "AUC", "dia": 1}])
        r = self._criar_ciclo(client, protocolo, clearance_creatinina=300,
                              neutrofilos=3000, plaquetas=250000)
        item = r.json()["doses_calculadas"][0]
        # TFG limitada a 125 → 6 × 150 = 900 mg
        self.assertAlmostEqual(item["dose_calculada"], 900.0, places=1)
        self.assertTrue(item["cap_aplicado"])

    def test_carboplatina_sem_clearance_nao_inventa_dose(self):
        empresa = _empresa("Hospital Rede", "onco-auc3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa, drogas=[
            {"droga": "Carboplatina", "dose": 5, "unidade": "AUC", "dia": 1}])
        r = self._criar_ciclo(client, protocolo, neutrofilos=3000, plaquetas=250000)
        item = r.json()["doses_calculadas"][0]
        self.assertIsNone(item["dose_calculada"])
        self.assertIn("Calvert", item["erro"])

    # ══ Ajuste por função renal/hepática ══════════════════════════════════════
    def test_cisplatina_alerta_com_clearance_baixo(self):
        empresa = _empresa("Hospital Rede", "onco-org1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa, drogas=[
            {"droga": "Cisplatina", "dose": 75, "unidade": "mg/m²", "dia": 1}])
        r = self._criar_ciclo(client, protocolo, clearance_creatinina=55,
                              neutrofilos=3000, plaquetas=250000)
        self.assertTrue(any("Cisplatina" in a and "clearance" in a
                            for a in r.json()["alertas"]), r.json()["alertas"])

    def test_paclitaxel_alerta_com_bilirrubina_alta(self):
        empresa = _empresa("Hospital Rede", "onco-org2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa, drogas=[
            {"droga": "Paclitaxel", "dose": 175, "unidade": "mg/m²", "dia": 1}])
        r = self._criar_ciclo(client, protocolo, bilirrubina_mg_dl=3.0,
                              neutrofilos=3000, plaquetas=250000)
        self.assertTrue(any("Paclitaxel" in a for a in r.json()["alertas"]))

    # ══ Elementos obrigatórios antes da 1ª dose (ASCO/ONS) ════════════════════
    def test_primeira_dose_cobra_elementos_obrigatorios(self):
        empresa = _empresa("Hospital Rede", "onco-1a1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo, numero_ciclo=1,
                              neutrofilos=3000, plaquetas=250000)
        faltando = r.json()["elementos_faltando_1a_dose"]
        self.assertIn("confirmação patológica do diagnóstico", faltando)
        self.assertIn("estadiamento no início do tratamento", faltando)

    def test_primeira_dose_completa_nao_cobra_nada(self):
        empresa = _empresa("Hospital Rede", "onco-1a2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(
            client, protocolo, numero_ciclo=1, neutrofilos=3000, plaquetas=250000,
            confirmacao_patologica=True, estadiamento="IIIB",
            intencao_tratamento="curativo")
        self.assertEqual(r.json()["elementos_faltando_1a_dose"], [])

    def test_ciclo_seguinte_nao_cobra_elementos_da_primeira_dose(self):
        empresa = _empresa("Hospital Rede", "onco-1a3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = self._criar_ciclo(client, protocolo, numero_ciclo=3,
                              neutrofilos=3000, plaquetas=250000)
        self.assertEqual(r.json()["elementos_faltando_1a_dose"], [])

    def test_ciclo_sem_peso_altura_rejeitado(self):
        """Regressão: peso/altura obrigatórios — sem eles não há base de dose."""
        empresa = _empresa("Hospital Rede", "onco-sc@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        r = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={"protocolo_id": protocolo.id, "paciente_nome": "P",
                  "cid10_principal": "C18", "data_inicio": date.today().isoformat()},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_vincristina_cap_2mg(self):
        """Regressão de segurança: Vincristina nunca ultrapassa 2 mg mesmo com SC alta."""
        empresa = _empresa("Hospital Rede", "onco-vcr@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(
            empresa, drogas=[{"droga": "Vincristina", "dose": 1.4, "unidade": "mg/m²", "dia": 1}])
        # paciente grande → SC ~2.2 → 1.4×2.2 = 3.08 mg, deve ser capado em 2.0
        r = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={"protocolo_id": protocolo.id, "paciente_nome": "P Grande",
                  "cid10_principal": "C83", "data_inicio": date.today().isoformat(),
                  "peso_kg": 120, "altura_cm": 190},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        dose = r.json()["doses_calculadas"][0]
        self.assertEqual(dose["dose_calculada"], 2.0)
        self.assertTrue(dose["cap_aplicado"])

    def test_grau_ctcae_fora_de_faixa_rejeitado(self):
        """Regressão: grau CTCAE fora de 1..5 não pode poluir o KPI."""
        empresa = _empresa("Hospital Rede", "onco-tox@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={"protocolo_id": protocolo.id, "paciente_nome": "P",
                  "cid10_principal": "C18", "data_inicio": date.today().isoformat(),
                  "peso_kg": 70, "altura_cm": 170},
            content_type="application/json",
        ).json()["id"]
        r = client.post(
            f"/api/hospital/oncologia/ciclos/{ciclo_id}/toxicidade/",
            data={"categoria": "Neutropenia", "grau": 9},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_ciclo_transicao_invalida_bloqueada(self):
        """Regressão: status arbitrário via PUT é rejeitado (agendado→concluido salta em_curso)."""
        empresa = _empresa("Hospital Rede", "onco-fsm@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={"protocolo_id": protocolo.id, "paciente_nome": "P",
                  "cid10_principal": "C18", "data_inicio": date.today().isoformat(),
                  "peso_kg": 70, "altura_cm": 170},
            content_type="application/json",
        ).json()["id"]
        # agendado → concluido (pula em_curso) deve dar 409
        r = client.put(
            f"/api/hospital/oncologia/ciclos/{ciclo_id}/",
            data={"status": "concluido"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 409)

    # ── Cadeia fechada: agenda → preparo → administração ───────────────────
    def _ciclo_pronto(self, client, protocolo, **extra):
        """Ciclo apto, com doses calculadas — ponto de partida da cadeia."""
        base = {"neutrofilos": 2500, "plaquetas": 220000}
        base.update(extra)
        return self._criar_ciclo(client, protocolo, **base).json()["id"]

    def _preparar_ate_conferido(self, client, ciclo_id):
        """Leva um preparo até 'conferido' — o estado que libera a veia."""
        pid = client.post("/api/hospital/oncologia/preparos/",
                          data={"ciclo_id": ciclo_id},
                          content_type="application/json").json()["preparos"][0]["id"]
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "em_preparo", "preparado_por": "Farm. Ana"},
                   content_type="application/json")
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "pronto", "dose_preparada": 150,
                         "lote": "L123", "diluente": "SF 0,9%"},
                   content_type="application/json")
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "conferido", "conferido_por": "Farm. Bruno"},
                   content_type="application/json")
        return pid

    def test_agenda_infusao_bloqueia_cadeira_ocupada(self):
        """Duas infusões na mesma cadeira no mesmo horário é erro operacional:
        tem de aparecer na hora de agendar, não no dia."""
        empresa = _empresa("Hospital Rede", "onco-ag1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        c1 = self._ciclo_pronto(client, protocolo)
        c2 = self._ciclo_pronto(client, protocolo)
        hoje = date.today().isoformat()
        r1 = client.post("/api/hospital/oncologia/agenda-infusao/",
                         data={"ciclo_id": c1, "data": hoje, "hora_inicio": "08:00",
                               "duracao_min": 180, "cadeira": "P1"},
                         content_type="application/json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r1.json()["agendamento"]["hora_fim_prevista"], "11:00")
        # 10:00 cai dentro de 08:00–11:00
        r2 = client.post("/api/hospital/oncologia/agenda-infusao/",
                         data={"ciclo_id": c2, "data": hoje, "hora_inicio": "10:00",
                               "duracao_min": 120, "cadeira": "P1"},
                         content_type="application/json")
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.json()["codigo"], "cadeira_ocupada")
        # Mesma hora em OUTRA cadeira é legítimo.
        r3 = client.post("/api/hospital/oncologia/agenda-infusao/",
                         data={"ciclo_id": c2, "data": hoje, "hora_inicio": "10:00",
                               "duracao_min": 120, "cadeira": "P2"},
                         content_type="application/json")
        self.assertEqual(r3.status_code, 201)

    def test_agenda_cancelada_libera_a_cadeira(self):
        """Cancelar devolve o horário para a central — senão a agenda entope
        com reservas mortas."""
        empresa = _empresa("Hospital Rede", "onco-ag2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        c1 = self._ciclo_pronto(client, protocolo)
        c2 = self._ciclo_pronto(client, protocolo)
        hoje = date.today().isoformat()
        ag = client.post("/api/hospital/oncologia/agenda-infusao/",
                         data={"ciclo_id": c1, "data": hoje, "hora_inicio": "08:00",
                               "cadeira": "P1"},
                         content_type="application/json").json()["id"]
        client.delete(f"/api/hospital/oncologia/agenda-infusao/{ag}/")
        r = client.post("/api/hospital/oncologia/agenda-infusao/",
                        data={"ciclo_id": c2, "data": hoje, "hora_inicio": "08:00",
                              "cadeira": "P1"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)

    def test_preparo_nasce_das_doses_calculadas_do_ciclo(self):
        """A farmácia recebe a prescrição que o médico assinou, não redigita."""
        empresa = _empresa("Hospital Rede", "onco-prep1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post("/api/hospital/oncologia/preparos/",
                        data={"ciclo_id": ciclo_id}, content_type="application/json")
        self.assertEqual(r.status_code, 201)
        preparos = r.json()["preparos"]
        self.assertEqual([p["droga"] for p in preparos], ["Oxaliplatina"])
        # 85 mg/m² × SC(70kg,170cm) — veio calculado, não digitado
        self.assertIsNotNone(preparos[0]["dose_prescrita"])
        self.assertEqual(preparos[0]["status"], "pendente")

    def test_preparo_bloqueado_para_ciclo_inapto_sem_liberacao(self):
        """A farmácia não manipula droga para paciente que o hemograma reprovou
        e que ninguém liberou."""
        empresa = _empresa("Hospital Rede", "onco-prep2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(client, protocolo,
                                     neutrofilos=300, plaquetas=200000).json()["id"]
        r = client.post("/api/hospital/oncologia/preparos/",
                        data={"ciclo_id": ciclo_id}, content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "ciclo_nao_liberado")

    def test_preparo_inapto_liberado_por_medico_passa(self):
        """Liberação médica registrada destrava — o médico nunca é bloqueado,
        só precisa assumir a decisão."""
        empresa = _empresa("Hospital Rede", "onco-prep3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(
            client, protocolo, neutrofilos=300, plaquetas=200000,
            aptidao_liberada_por="Dra. Marina",
            aptidao_justificativa="Paciente em cuidado paliativo, risco assumido",
        ).json()["id"]
        r = client.post("/api/hospital/oncologia/preparos/",
                        data={"ciclo_id": ciclo_id}, content_type="application/json")
        self.assertEqual(r.status_code, 201)

    def test_conferencia_exige_segundo_profissional(self):
        """Dupla checagem de verdade: conferir o próprio preparo não é conferência."""
        empresa = _empresa("Hospital Rede", "onco-prep4@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = client.post("/api/hospital/oncologia/preparos/",
                          data={"ciclo_id": ciclo_id},
                          content_type="application/json").json()["preparos"][0]["id"]
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "em_preparo", "preparado_por": "Farm. Ana"},
                   content_type="application/json")
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "pronto", "dose_preparada": 150},
                   content_type="application/json")
        r = client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                       data={"status": "conferido", "conferido_por": "farm. ANA"},
                       content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "dupla_checagem_mesma_pessoa")

    def test_preparo_nao_fica_pronto_sem_dose_preparada(self):
        """Dose efetivamente manipulada é o que será administrado: não pode
        ficar em branco."""
        empresa = _empresa("Hospital Rede", "onco-prep5@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = client.post("/api/hospital/oncologia/preparos/",
                          data={"ciclo_id": ciclo_id},
                          content_type="application/json").json()["preparos"][0]["id"]
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "em_preparo", "preparado_por": "Farm. Ana"},
                   content_type="application/json")
        r = client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                       data={"status": "pronto"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "sem_dose_preparada")

    def test_lote_vencido_nao_e_liberado(self):
        empresa = _empresa("Hospital Rede", "onco-prep6@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = client.post("/api/hospital/oncologia/preparos/",
                          data={"ciclo_id": ciclo_id},
                          content_type="application/json").json()["preparos"][0]["id"]
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "em_preparo", "preparado_por": "Farm. Ana"},
                   content_type="application/json")
        client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                   data={"status": "pronto", "dose_preparada": 150, "lote": "L9",
                         "validade_lote": (date.today() - timedelta(days=1)).isoformat()},
                   content_type="application/json")
        r = client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                       data={"status": "conferido", "conferido_por": "Farm. Bruno"},
                       content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "lote_vencido")

    def test_descarte_exige_motivo(self):
        empresa = _empresa("Hospital Rede", "onco-prep7@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = client.post("/api/hospital/oncologia/preparos/",
                          data={"ciclo_id": ciclo_id},
                          content_type="application/json").json()["preparos"][0]["id"]
        r = client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                       data={"status": "descartado"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "descarte_sem_motivo")
        r = client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                       data={"status": "descartado",
                             "motivo_descarte": "Frasco violado no transporte"},
                       content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_preparo_nao_volta_atras(self):
        """Frasco manipulado não desmanipula: a FSM da farmácia é de mão única."""
        empresa = _empresa("Hospital Rede", "onco-prep8@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.put(f"/api/hospital/oncologia/preparos/{pid}/",
                       data={"status": "em_preparo"}, content_type="application/json")
        self.assertEqual(r.status_code, 409)

    def test_administracao_exige_preparo_conferido(self):
        """O elo que fecha a cadeia: só entra na veia o que a farmácia conferiu."""
        empresa = _empresa("Hospital Rede", "onco-adm1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = client.post("/api/hospital/oncologia/preparos/",
                          data={"ciclo_id": ciclo_id},
                          content_type="application/json").json()["preparos"][0]["id"]
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "preparo_nao_conferido")

    def test_administracao_completa_e_dispensa_o_preparo(self):
        empresa = _empresa("Hospital Rede", "onco-adm2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego", "via": "porto"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        adm = r.json()["administracao"]
        self.assertEqual(adm["droga"], "Oxaliplatina")
        # Dose administrada herda a dose preparada quando não é informada.
        self.assertEqual(adm["dose_administrada"], 150.0)
        # O preparo é consumido pela administração.
        d = client.get(f"/api/hospital/oncologia/preparos?ciclo_id={ciclo_id}").json()
        self.assertEqual(d["preparos"][0]["status"], "dispensado")
        self.assertTrue(d["preparos"][0]["administrado"])
        # E não pode ser administrado duas vezes.
        r2 = client.post("/api/hospital/oncologia/administracoes/",
                         data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                               "checado_por": "Enf. Diego"},
                         content_type="application/json")
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.json()["codigo"], "preparo_ja_administrado")

    def test_administracao_exige_dois_profissionais_distintos(self):
        empresa = _empresa("Hospital Rede", "onco-adm3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "enf. carla"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "dupla_checagem_mesma_pessoa")
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "dupla_checagem_incompleta")

    def test_extravasamento_exige_conduta(self):
        """Intercorrência sem conduta é o caso que some do prontuário e
        reaparece como processo."""
        empresa = _empresa("Hospital Rede", "onco-adm4@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "intercorrencia": "extravasamento"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "intercorrencia_sem_conduta")
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "intercorrencia": "extravasamento",
                              "intercorrencia_conduta": "Infusão interrompida, "
                                                        "compressa fria, dexrazoxano"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        d = client.get("/api/hospital/oncologia/administracoes").json()
        self.assertEqual(d["com_intercorrencia"], 1)

    def test_horario_de_infusao_e_gravado_com_fuso(self):
        """Regressão: datetime ingênuo com USE_TZ ativo desloca o horário real
        da infusão. O que a enfermagem digita é o que tem de voltar."""
        empresa = _empresa("Hospital Rede", "onco-tz@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.post(
            "/api/hospital/oncologia/administracoes/",
            data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                  "checado_por": "Enf. Diego",
                  "inicio": f"{date.today().isoformat()}T14:30"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        from .models import AdministracaoQuimioterapia
        a = AdministracaoQuimioterapia.objects.get(id=r.json()["id"])
        self.assertIsNotNone(a.inicio.tzinfo)
        local = timezone.localtime(a.inicio)
        self.assertEqual((local.hour, local.minute), (14, 30))

    def test_kpis_enxergam_a_cadeia(self):
        """Fila da farmácia e intercorrência do mês são o painel do dia da
        central — se não sobem para o KPI, ninguém olha."""
        empresa = _empresa("Hospital Rede", "onco-kpi-cad@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        client.post("/api/hospital/oncologia/preparos/",
                    data={"ciclo_id": ciclo_id}, content_type="application/json")
        k = client.get("/api/hospital/oncologia/kpis").json()
        self.assertEqual(k["fila_farmacia"], 1)
        self.assertEqual(k["intercorrencias_mes"], 0)

        ciclo2 = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo2)
        client.post("/api/hospital/oncologia/administracoes/",
                    data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                          "checado_por": "Enf. Diego",
                          "intercorrencia": "extravasamento",
                          "intercorrencia_conduta": "Infusão interrompida"},
                    content_type="application/json")
        client.post("/api/hospital/oncologia/agenda-infusao/",
                    data={"ciclo_id": ciclo_id, "data": date.today().isoformat(),
                          "hora_inicio": "08:00", "cadeira": "P1"},
                    content_type="application/json")
        k = client.get("/api/hospital/oncologia/kpis").json()
        self.assertEqual(k["intercorrencias_mes"], 1)
        self.assertEqual(k["extravasamentos_mes"], 1)
        self.assertEqual(k["infusoes_agendadas_hoje"], 1)

    def test_jornada_mostra_o_que_entrou_na_veia(self):
        """A linha do tempo do paciente tem de registrar a administração, com
        quem administrou e quem checou — é a prova do que foi feito."""
        empresa = _empresa("Hospital Rede", "onco-jor-cad@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(
            client, protocolo, paciente_nome="Jorge Cadeia",
            cpf_paciente="52998224725", neutrofilos=2500, plaquetas=220000,
        ).json()["id"]
        pid = self._preparar_ate_conferido(client, ciclo_id)
        client.post("/api/hospital/oncologia/administracoes/",
                    data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                          "checado_por": "Enf. Diego"},
                    content_type="application/json")
        d = client.get("/api/hospital/oncologia/jornada?cpf=52998224725").json()
        self.assertEqual(d["resumo"]["administracao"], 1)
        ev = [e for e in d["timeline"] if e["tipo"] == "administracao"]
        self.assertEqual(len(ev), 1)
        self.assertIn("Oxaliplatina", ev[0]["titulo"])
        self.assertEqual(ev[0]["detalhe"]["checado_por"], "Enf. Diego")

    def test_seed_demo_popula_e_reverte_a_cadeia(self):
        """O seed de demonstração roda sozinho e desfaz o que criou. Sem isto,
        só se descobre que ele quebra apontando para a conta demo de produção."""
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from .models import (CicloQuimioterapia, GuiaOncologica,
                             AdministracaoQuimioterapia,
                             AvaliacaoRespostaOncologica, PrescricaoQuimioOral,
                             SeguimentoOncologico)

        empresa = _empresa("Hospital Demo", "demo.hospital@exemplo-demo.com",
                           "hospital_rede")
        client = _client_for(empresa)
        self._protocolo(empresa)
        ProtocoloOncologico.objects.create(
            empresa=empresa, codigo="CARBO-TESTE", nome="Carbo/Taxol",
            ciclos_total=6, intervalo_dias=21,
            drogas=[{"droga": "Carboplatina", "dose": 5, "unidade": "AUC", "dia": 1}])

        out = StringIO()
        call_command("seed_oncologia_demo", "--apply",
                     "--empresa-id", str(empresa.id), stdout=out)
        self.assertEqual(
            CicloQuimioterapia.objects.filter(
                empresa=empresa, paciente_nome__startswith="[DEMO-ONCO]").count(), 3)
        self.assertEqual(GuiaOncologica.objects.filter(empresa=empresa).count(), 3)
        self.assertEqual(
            AdministracaoQuimioterapia.objects.filter(empresa=empresa).count(), 2)
        self.assertEqual(
            AvaliacaoRespostaOncologica.objects.filter(empresa=empresa).count(), 3)
        # O motivo da negativa precisa estar na lista de escolhas do modelo:
        # um valor fora dela faz get_..._display() devolver o código cru e o
        # usuário lê "doc_insuficiente" no lugar da frase.
        negada = GuiaOncologica.objects.get(empresa=empresa, status="negada")
        self.assertIn(negada.motivo_negativa,
                      dict(GuiaOncologica.MOTIVO_NEGATIVA))
        self.assertNotEqual(negada.get_motivo_negativa_display(),
                            negada.motivo_negativa)
        segs = SeguimentoOncologico.objects.filter(empresa=empresa)
        self.assertEqual(segs.count(), 2)
        # Um dos dois tem de cair como perdido de seguimento — é o caso que o
        # seed existe para mostrar.
        d = client.get("/api/hospital/oncologia/seguimentos").json()
        self.assertEqual(d["fora_do_radar"], 1)
        # O SQLite dos testes NÃO valida tamanho de varchar — o PostgreSQL de
        # produção valida. Sem checar aqui, um valor longo no seed só estoura
        # no servidor (foi o que aconteceu com o código SIGTAP da APAC).
        from django.core.exceptions import ValidationError
        for modelo in (CicloQuimioterapia, GuiaOncologica, PrescricaoQuimioOral,
                       SeguimentoOncologico):
            for obj in modelo.objects.filter(empresa=empresa):
                for campo in obj._meta.fields:
                    limite = getattr(campo, "max_length", None)
                    valor = getattr(obj, campo.name, None)
                    if limite and isinstance(valor, str) and len(valor) > limite:
                        self.fail(
                            f"{modelo.__name__}.{campo.name} tem {len(valor)} "
                            f"caracteres e o limite é {limite}: {valor!r}")
        from .models import APACOncologia as _Apac
        for apac in _Apac.objects.filter(empresa=empresa):
            self.assertLessEqual(len(apac.procedimento_principal), 10)

        oral = PrescricaoQuimioOral.objects.get(empresa=empresa)
        self.assertEqual(oral.dispensacoes.count(), 2)
        self.assertEqual(float(oral.dispensacoes.order_by("-data").first().adesao_pct), 50.0)

        # Rodar de novo não duplica (é idempotente).
        call_command("seed_oncologia_demo", "--apply",
                     "--empresa-id", str(empresa.id), stdout=out)
        self.assertEqual(
            CicloQuimioterapia.objects.filter(empresa=empresa).count(), 3)

        call_command("seed_oncologia_demo", "--apply", "--clear",
                     "--empresa-id", str(empresa.id), stdout=out)
        self.assertEqual(CicloQuimioterapia.objects.filter(empresa=empresa).count(), 0)
        self.assertEqual(
            AdministracaoQuimioterapia.objects.filter(empresa=empresa).count(), 0)
        self.assertEqual(PrescricaoQuimioOral.objects.filter(empresa=empresa).count(), 0)
        self.assertEqual(SeguimentoOncologico.objects.filter(empresa=empresa).count(), 0)

        # Trava de segurança: conta sem "demo" no e-mail é recusada.
        real = _empresa("Hospital Real", "contas@hospital-real.com", "hospital_rede")
        self._protocolo(real)
        with self.assertRaises(CommandError):
            call_command("seed_oncologia_demo", "--apply",
                         "--empresa-id", str(real.id), stdout=out)

    # ── Quimioterapia oral: adesão por contagem de comprimidos ─────────────
    def _prescricao_oral(self, client, **extra):
        payload = {
            "paciente_nome": "Paciente Oral", "droga": "Capecitabina",
            "dose_por_tomada": 1500, "unidades_por_dia": 2,
            "dias_uso": 14, "dias_pausa": 7,
            "data_inicio": (date.today() - timedelta(days=21)).isoformat(),
            "posologia": "2 comprimidos 12/12h após refeição",
        }
        payload.update(extra)
        return client.post("/api/hospital/oncologia/quimio-oral/",
                           data=payload, content_type="application/json")

    def test_primeira_dispensacao_nao_mede_adesao(self):
        """Não há intervalo anterior para contar: entregar não é medir."""
        empresa = _empresa("Hospital Rede", "onco-or1@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(client).json()["id"]
        r = client.post(f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/",
                        data={"data": (date.today() - timedelta(days=21)).isoformat(),
                              "unidades_dispensadas": 28},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.json()["adesao_intervalo"]["adesao_pct"])

    def test_adesao_respeita_esquema_de_pausa(self):
        """Capecitabina 14+7 não é tomar todo dia: contar dias corridos faria
        todo paciente parecer não-aderente (21 dias × 2 = 42 esperados em vez de 28)."""
        empresa = _empresa("Hospital Rede", "onco-or2@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(client).json()["id"]
        url = f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/"
        client.post(url, data={"data": (date.today() - timedelta(days=21)).isoformat(),
                               "unidades_dispensadas": 28},
                    content_type="application/json")
        r = client.post(url, data={"data": date.today().isoformat(),
                                   "unidades_dispensadas": 28,
                                   "unidades_devolvidas": 0},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        ad = r.json()["adesao_intervalo"]
        self.assertEqual(ad["unidades_esperadas"], 28)   # 14 dias de uso × 2
        self.assertEqual(ad["adesao_pct"], 100.0)
        self.assertFalse(ad["baixa"])

    def test_adesao_baixa_dispara_alerta(self):
        """Metade dos comprimidos voltou: é não-adesão, não falha do tratamento."""
        empresa = _empresa("Hospital Rede", "onco-or3@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(client).json()["id"]
        url = f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/"
        client.post(url, data={"data": (date.today() - timedelta(days=21)).isoformat(),
                               "unidades_dispensadas": 28},
                    content_type="application/json")
        r = client.post(url, data={"data": date.today().isoformat(),
                                   "unidades_dispensadas": 28,
                                   "unidades_devolvidas": 14},
                        content_type="application/json")
        self.assertEqual(r.json()["adesao_intervalo"]["adesao_pct"], 50.0)
        self.assertTrue(r.json()["adesao_intervalo"]["baixa"])
        self.assertIn("Adesão abaixo", r.json()["alerta"])
        d = client.get("/api/hospital/oncologia/quimio-oral").json()
        self.assertEqual(d["adesao_baixa"], 1)
        self.assertEqual(d["prescricoes"][0]["adesao_media_pct"], 50.0)

    def test_uso_continuo_conta_dias_corridos(self):
        """Hormonioterapia é uso contínuo: sem pausa, o esperado é dia a dia."""
        empresa = _empresa("Hospital Rede", "onco-or4@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(
            client, droga="Tamoxifeno", dias_uso=30, dias_pausa=0,
            unidades_por_dia=1,
            data_inicio=(date.today() - timedelta(days=30)).isoformat(),
        ).json()["id"]
        url = f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/"
        client.post(url, data={"data": (date.today() - timedelta(days=30)).isoformat(),
                               "unidades_dispensadas": 30},
                    content_type="application/json")
        r = client.post(url, data={"data": date.today().isoformat(),
                                   "unidades_dispensadas": 30,
                                   "unidades_devolvidas": 0},
                        content_type="application/json")
        self.assertEqual(r.json()["adesao_intervalo"]["unidades_esperadas"], 30)

    def test_devolucao_maior_que_entrega_e_recusada(self):
        """Devolver mais do que levou é erro de contagem, não adesão perfeita."""
        empresa = _empresa("Hospital Rede", "onco-or5@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(client).json()["id"]
        url = f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/"
        client.post(url, data={"data": (date.today() - timedelta(days=21)).isoformat(),
                               "unidades_dispensadas": 28},
                    content_type="application/json")
        r = client.post(url, data={"data": date.today().isoformat(),
                                   "unidades_dispensadas": 28,
                                   "unidades_devolvidas": 40},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "devolucao_maior_que_entrega")

    def test_retirada_atrasada_aparece_na_lista(self):
        """O paciente que não voltou buscar a caixa é o que some do radar."""
        empresa = _empresa("Hospital Rede", "onco-or6@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(client).json()["id"]
        client.post(f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/",
                    data={"data": (date.today() - timedelta(days=30)).isoformat(),
                          "unidades_dispensadas": 28,
                          "proxima_retirada": (date.today() - timedelta(days=9)).isoformat()},
                    content_type="application/json")
        d = client.get("/api/hospital/oncologia/quimio-oral").json()
        self.assertEqual(d["atrasados_retirada"], 1)
        self.assertEqual(d["prescricoes"][0]["retirada"]["dias_atraso"], 9)

    def test_prescricao_suspensa_nao_dispensa(self):
        empresa = _empresa("Hospital Rede", "onco-or7@example.com", "hospital_rede")
        client = _client_for(empresa)
        pid = self._prescricao_oral(client).json()["id"]
        r = client.put(f"/api/hospital/oncologia/quimio-oral/{pid}/",
                       data={"status": "suspensa"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = client.post(f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/",
                        data={"unidades_dispensadas": 28},
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "prescricao_inativa")

    def test_quimio_oral_isolada_por_empresa(self):
        a = _empresa("Hospital A", "onco-or-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-or-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        pid = self._prescricao_oral(ca).json()["id"]
        self.assertEqual(cb.get("/api/hospital/oncologia/quimio-oral").json()["total"], 0)
        r = cb.post(f"/api/hospital/oncologia/quimio-oral/{pid}/dispensacoes/",
                    data={"unidades_dispensadas": 28}, content_type="application/json")
        self.assertEqual(r.status_code, 404)
        r = cb.put(f"/api/hospital/oncologia/quimio-oral/{pid}/",
                   data={"status": "cancelada"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_jornada_por_nome_para_paciente_sem_identidade_no_mpi(self):
        """Regressão REAL: o teste anterior passava por engano.

        Criar o paciente pela API resolve a identidade no MPI, e a jornada
        então usa o ramo da identidade — o fallback por nome nunca roda. Quem
        cai no fallback é o registro criado direto no banco (importação, seed,
        carga legada), e aí a divergência de nome de campo entre os modelos
        derruba a tela com 500. A radioterapia usa `paciente`, o RHC usa
        `nome_paciente` e o resto usa `paciente_nome`.
        """
        from .models import CicloQuimioterapia, SeguimentoOncologico
        empresa = _empresa("Hospital Rede", "onco-jor-mpi@example.com",
                           "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        # Direto no ORM, SEM identidade e SEM CPF — como numa carga legada.
        CicloQuimioterapia.objects.create(
            empresa=empresa, protocolo=protocolo,
            paciente_nome="Carga Legada Souza", cid10_principal="C18",
            numero_ciclo=1, data_inicio=date.today())
        SeguimentoOncologico.objects.create(
            empresa=empresa, paciente_nome="Carga Legada Souza",
            data_fim_tratamento=date.today() - timedelta(days=30))

        r = client.get("/api/hospital/oncologia/jornada?nome=Carga%20Legada%20Souza")
        self.assertEqual(r.status_code, 200, r.content[:400])
        d = r.json()
        self.assertEqual(d["resumo"]["quimioterapia"], 1)
        self.assertEqual(d["resumo"]["seguimento"], 1)

    def test_jornada_por_nome_sem_cpf_nao_quebra(self):
        """Regressão: o fallback por nome usava `nome_paciente`, campo que só o
        RHC tem — buscar um paciente sem CPF derrubava a jornada com 500."""
        empresa = _empresa("Hospital Rede", "onco-jor-nome@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        # Sem CPF: o paciente não entra no MPI, então o filtro cai no nome.
        self._criar_ciclo(client, protocolo, paciente_nome="Sem Documento Silva",
                          neutrofilos=2500, plaquetas=220000)
        self._prescricao_oral(client, paciente_nome="Sem Documento Silva")
        r = client.get("/api/hospital/oncologia/jornada?nome=Sem%20Documento%20Silva")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["resumo"]["quimioterapia"], 1)
        self.assertEqual(d["resumo"]["quimio_oral"], 1)
        ev = [e for e in d["timeline"] if e["tipo"] == "quimio_oral"]
        self.assertIn("Capecitabina", ev[0]["titulo"])

    # ── Seguimento e sobrevida ─────────────────────────────────────────────
    def _seguimento(self, client, **extra):
        payload = {
            "paciente_nome": "Paciente Seguimento",
            "data_diagnostico": (date.today() - timedelta(days=730)).isoformat(),
            "data_fim_tratamento": (date.today() - timedelta(days=365)).isoformat(),
            "cid10_principal": "C50", "periodicidade_meses": 3,
        }
        payload.update(extra)
        return client.post("/api/hospital/oncologia/seguimentos/",
                           data=payload, content_type="application/json")

    def test_sobrevida_censurada_enquanto_paciente_vivo(self):
        """Paciente vivo sem recidiva é CENSURADO: conta o tempo observado, mas
        não conta como desfecho. Tratar censura como evento faz a sobrevida
        parecer pior do que é."""
        empresa = _empresa("Hospital Rede", "onco-sg1@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._seguimento(client)
        self.assertEqual(r.status_code, 201)
        s = r.json()["seguimento"]["sobrevida"]
        self.assertTrue(s["censurado"])
        self.assertEqual(s["sobrevida_global_evento"], "censurado")
        self.assertEqual(s["sobrevida_livre_doenca_evento"], "censurado")
        # Diagnóstico há 24 meses; o último contato nasce no fim do tratamento (12m atrás).
        self.assertEqual(s["sobrevida_global_meses"], 12)
        self.assertEqual(s["sobrevida_livre_doenca_meses"], 0)

    def test_recidiva_exige_tipo_e_data_coerente(self):
        empresa = _empresa("Hospital Rede", "onco-sg2@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(client).json()["id"]
        url = f"/api/hospital/oncologia/seguimentos/{sid}/"
        # Sem tipo
        r = client.put(url, data={"recidiva": True,
                                  "data_recidiva": (date.today() - timedelta(days=100)).isoformat()},
                       content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "recidiva_sem_tipo")
        # Antes do fim do tratamento
        r = client.put(url, data={"recidiva": True, "tipo_recidiva": "local",
                                  "data_recidiva": (date.today() - timedelta(days=400)).isoformat()},
                       content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "recidiva_antes_do_fim")
        # Válida: fecha a sobrevida livre de doença como EVENTO, não censura
        r = client.put(url, data={"recidiva": True, "tipo_recidiva": "distante",
                                  "data_recidiva": (date.today() - timedelta(days=90)).isoformat()},
                       content_type="application/json")
        self.assertEqual(r.status_code, 200)
        s = r.json()["seguimento"]["sobrevida"]
        self.assertEqual(s["sobrevida_livre_doenca_evento"], "recidiva")
        self.assertEqual(s["sobrevida_livre_doenca_meses"], 9)

    def test_obito_fecha_a_sobrevida_e_vira_ultimo_contato(self):
        """Sem isso a sobrevida segue contando tempo de um paciente já falecido."""
        empresa = _empresa("Hospital Rede", "onco-sg3@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(client).json()["id"]
        url = f"/api/hospital/oncologia/seguimentos/{sid}/"
        r = client.put(url, data={"status_vital": "obito"},
                       content_type="application/json")
        self.assertEqual(r.status_code, 400)   # exige data
        d_obito = (date.today() - timedelta(days=60)).isoformat()
        r = client.put(url, data={"status_vital": "obito", "data_obito": d_obito,
                                  "causa_obito": "neoplasia"},
                       content_type="application/json")
        self.assertEqual(r.status_code, 200)
        seg = r.json()["seguimento"]
        self.assertFalse(seg["sobrevida"]["censurado"])
        self.assertEqual(seg["sobrevida"]["sobrevida_global_evento"], "obito")
        self.assertEqual(seg["data_ultimo_contato"], d_obito)
        self.assertEqual(seg["situacao"]["situacao"], "obito")

    def test_obito_antes_do_fim_do_tratamento_e_recusado(self):
        empresa = _empresa("Hospital Rede", "onco-sg4@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(client).json()["id"]
        r = client.put(f"/api/hospital/oncologia/seguimentos/{sid}/",
                       data={"status_vital": "obito",
                             "data_obito": (date.today() - timedelta(days=500)).isoformat()},
                       content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "obito_antes_do_fim")

    def test_paciente_sem_contato_sai_do_radar(self):
        """O paciente que para de vir e ninguém percebe — é o que some em
        agenda de papel."""
        empresa = _empresa("Hospital Rede", "onco-sg5@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._seguimento(
            client,
            data_diagnostico=(date.today() - timedelta(days=1000)).isoformat(),
            data_fim_tratamento=(date.today() - timedelta(days=800)).isoformat(),
            data_ultimo_contato=(date.today() - timedelta(days=700)).isoformat())
        self.assertEqual(r.status_code, 201)
        d = client.get("/api/hospital/oncologia/seguimentos").json()
        self.assertEqual(d["fora_do_radar"], 1)
        sit = d["seguimentos"][0]["situacao"]
        self.assertTrue(sit["fora_do_radar"])
        self.assertEqual(sit["situacao"], "perdido")
        self.assertGreaterEqual(sit["meses_sem_contato"], 12)

    def test_comparecer_tira_do_radar_e_reagenda(self):
        empresa = _empresa("Hospital Rede", "onco-sg6@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(
            client,
            data_diagnostico=(date.today() - timedelta(days=1000)).isoformat(),
            data_fim_tratamento=(date.today() - timedelta(days=800)).isoformat(),
            data_ultimo_contato=(date.today() - timedelta(days=700)).isoformat(),
        ).json()["id"]
        d = client.get("/api/hospital/oncologia/seguimentos").json()
        self.assertEqual(d["fora_do_radar"], 1)
        r = client.post(f"/api/hospital/oncologia/seguimentos/{sid}/consultas/",
                        data={"data_prevista": date.today().isoformat(),
                              "compareceu": True, "exames": "TC de tórax",
                              "profissional": "Dra. Helena"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        seg = r.json()["seguimento"]
        self.assertEqual(seg["data_ultimo_contato"], date.today().isoformat())
        self.assertFalse(seg["situacao"]["fora_do_radar"])
        # Reagendou pelo intervalo do plano (3 meses).
        self.assertGreater(seg["proxima_avaliacao"], date.today().isoformat())
        d = client.get("/api/hospital/oncologia/seguimentos").json()
        self.assertEqual(d["fora_do_radar"], 0)

    def test_falta_nao_pode_ter_data_de_realizacao(self):
        empresa = _empresa("Hospital Rede", "onco-sg7@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(client).json()["id"]
        r = client.post(f"/api/hospital/oncologia/seguimentos/{sid}/consultas/",
                        data={"data_prevista": (date.today()-timedelta(days=10)).isoformat(),
                              "compareceu": False,
                              "data_realizada": date.today().isoformat()},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "falta_com_data_realizada")

    def test_falta_conta_como_consulta_perdida(self):
        empresa = _empresa("Hospital Rede", "onco-sg8@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(client).json()["id"]
        client.post(f"/api/hospital/oncologia/seguimentos/{sid}/consultas/",
                    data={"data_prevista": (date.today()-timedelta(days=30)).isoformat(),
                          "compareceu": False},
                    content_type="application/json")
        d = client.get("/api/hospital/oncologia/seguimentos").json()
        self.assertEqual(d["seguimentos"][0]["consultas_perdidas"], 1)

    def test_suspeita_de_recidiva_avisa_sem_fechar_desfecho(self):
        """Suspeita não é diagnóstico: entra como alerta, não entra na sobrevida."""
        empresa = _empresa("Hospital Rede", "onco-sg9@example.com", "hospital_rede")
        client = _client_for(empresa)
        sid = self._seguimento(client).json()["id"]
        r = client.post(f"/api/hospital/oncologia/seguimentos/{sid}/consultas/",
                        data={"data_prevista": date.today().isoformat(),
                              "compareceu": True, "suspeita_recidiva": True,
                              "achados": "Nódulo novo em TC"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("Suspeita de recidiva", r.json()["alerta"])
        self.assertFalse(r.json()["seguimento"]["recidiva"])
        self.assertEqual(
            r.json()["seguimento"]["sobrevida"]["sobrevida_livre_doenca_evento"],
            "censurado")

    def test_diagnostico_depois_do_fim_do_tratamento_e_recusado(self):
        empresa = _empresa("Hospital Rede", "onco-sg10@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._seguimento(
            client, data_diagnostico=date.today().isoformat(),
            data_fim_tratamento=(date.today() - timedelta(days=100)).isoformat())
        self.assertEqual(r.status_code, 400)

    def test_jornada_termina_no_desfecho_de_longo_prazo(self):
        """A linha do tempo tem de chegar até o seguimento: sem isso ela para no
        último ciclo e o desfecho do paciente fica fora da história."""
        empresa = _empresa("Hospital Rede", "onco-sg-jor@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        self._criar_ciclo(client, protocolo, paciente_nome="Final Oliveira",
                          cpf_paciente="52998224725",
                          neutrofilos=2500, plaquetas=220000)
        sid = self._seguimento(client, paciente_nome="Final Oliveira",
                               cpf_paciente="52998224725").json()["id"]
        client.put(f"/api/hospital/oncologia/seguimentos/{sid}/",
                   data={"recidiva": True, "tipo_recidiva": "local",
                         "data_recidiva": (date.today()-timedelta(days=30)).isoformat()},
                   content_type="application/json")
        d = client.get("/api/hospital/oncologia/jornada?cpf=52998224725").json()
        self.assertEqual(d["resumo"]["seguimento"], 1)
        ev = [e for e in d["timeline"] if e["tipo"] == "seguimento"]
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]["detalhe"]["recidiva"])
        self.assertEqual(
            ev[0]["detalhe"]["sobrevida"]["sobrevida_livre_doenca_evento"], "recidiva")

    def test_seguimento_isolado_por_empresa(self):
        a = _empresa("Hospital A", "onco-sg-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-sg-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        sid = self._seguimento(ca).json()["id"]
        self.assertEqual(cb.get("/api/hospital/oncologia/seguimentos").json()["total"], 0)
        r = cb.put(f"/api/hospital/oncologia/seguimentos/{sid}/",
                   data={"status_vital": "perdido"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)
        r = cb.post(f"/api/hospital/oncologia/seguimentos/{sid}/consultas/",
                    data={"data_prevista": date.today().isoformat()},
                    content_type="application/json")
        self.assertEqual(r.status_code, 404)

    # ── Assinatura digital ICP-Brasil ──────────────────────────────────────
    def _certificado_teste(self, dias_validade=365, valido_de_dias=-1):
        """Gera um PKCS#12 autoassinado em arquivo temporário.

        Não é um certificado ICP-Brasil — é o que permite exercitar TODO o
        caminho de assinatura (carregar, assinar, extrair dados do titular)
        sem depender de comprar o certificado real.
        """
        import datetime as _dt
        import tempfile
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs12

        chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nome = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "HELENA DUARTE:52998224725"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        ])
        emissor = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "AC TESTE SOLOCRT"),
        ])
        agora = _dt.datetime.now(_dt.timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(nome).issuer_name(emissor)
                .public_key(chave.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(agora + _dt.timedelta(days=valido_de_dias))
                .not_valid_after(agora + _dt.timedelta(days=dias_validade))
                .sign(chave, hashes.SHA256()))
        senha = b"senha-de-teste"
        p12 = pkcs12.serialize_key_and_certificates(
            b"teste", chave, cert, None,
            serialization.BestAvailableEncryption(senha))
        arq = tempfile.NamedTemporaryFile(suffix=".pfx", delete=False)
        arq.write(p12)
        arq.close()
        self.addCleanup(lambda: __import__("os").unlink(arq.name))
        return arq.name, senha.decode()

    def test_status_diz_que_assinatura_nao_esta_configurada(self):
        """O sistema precisa admitir que não assina — em vez de ficar calado —
        e deixar claro de quem é o certificado."""
        empresa = _empresa("Hospital Rede", "onco-icp1@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = client.get("/api/hospital/oncologia/assinatura/status").json()
        self.assertFalse(d["disponivel"])
        self.assertEqual(d["provedor"], "nao_configurado")
        self.assertEqual(d["assinantes_ativos"], 0)
        self.assertTrue(d["pendencias"])
        self.assertIn("NÃO ASSINADAS", d["mensagem"])
        self.assertIn("médico", d["titularidade"])

    def test_sem_certificado_nada_e_marcado_como_assinado(self):
        """A regra inegociável: fingir que assinou seria uma mentira com valor
        jurídico. Sem certificado, a tentativa vira FALHA registrada."""
        empresa = _empresa("Hospital Rede", "onco-icp2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 503)
        d = r.json()
        self.assertEqual(d["codigo"], "assinatura_nao_configurada")
        self.assertFalse(d["assinada"])
        self.assertTrue(d["pendencias"])
        from .models import AssinaturaDocumento
        a = AssinaturaDocumento.objects.get(empresa=empresa, objeto_id=ciclo_id)
        self.assertEqual(a.status, "falha")
        self.assertEqual(
            AssinaturaDocumento.objects.filter(status="assinada").count(), 0)
        # E a consulta continua dizendo que não está assinada.
        g = client.get(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/").json()
        self.assertFalse(g["assinada"])

    def test_conteudo_canonico_e_deterministico(self):
        """Se a serialização variar, o mesmo documento gera resumos diferentes
        e toda assinatura 'quebra' sozinha na verificação seguinte."""
        from .services.assinatura_icp import (conteudo_canonico_prescricao,
                                              resumo_sha256)
        empresa = _empresa("Hospital Rede", "onco-icp3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        from django.utils import timezone as _tz
        from .models import CicloQuimioterapia
        c = CicloQuimioterapia.objects.get(id=ciclo_id)
        # Para um MESMO instante de emissão o conteúdo é byte a byte igual —
        # é essa a propriedade que a verificação reproduz depois.
        instante = _tz.now()
        a = resumo_sha256(conteudo_canonico_prescricao(c, emitido_em=instante))
        c.refresh_from_db()
        b = resumo_sha256(conteudo_canonico_prescricao(c, emitido_em=instante))
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)
        # E instantes diferentes dão resumos diferentes: a hora de emissão
        # integra o documento (art. 2º, "d"), não é enfeite.
        outro = resumo_sha256(conteudo_canonico_prescricao(
            c, emitido_em=instante + timedelta(minutes=1)))
        self.assertNotEqual(a, outro)

    def test_assina_de_verdade_quando_ha_certificado(self):
        """Prova que o caminho inteiro funciona com o certificado DO MÉDICO."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-icp4@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        st = client.get("/api/hospital/oncologia/assinatura/status"
                        "?cpf=52998224725").json()
        self.assertTrue(st["disponivel"])
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725",
                              "signatario_registro": "CRM-MS 12345"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:400])
        d = r.json()
        self.assertTrue(d["assinada"])
        a = d["assinatura"]
        self.assertEqual(a["status"], "assinada")
        # Em certificado ICP-Brasil de pessoa física o CPF vem anexado ao CN.
        self.assertEqual(a["certificado"]["titular"], "HELENA DUARTE")
        self.assertEqual(a["certificado"]["cpf_cnpj"], "52998224725")
        self.assertEqual(a["certificado"]["emissor"], "AC TESTE SOLOCRT")
        # Sem Autoridade de Carimbo do Tempo, a data não tem fé pública.
        self.assertFalse(a["data_com_fe_publica"])
        from .models import AssinaturaDocumento
        self.assertTrue(AssinaturaDocumento.objects.get(id=a["id"]).assinatura_b64)

    def test_alterar_a_dose_depois_invalida_a_assinatura(self):
        """O coração da coisa: a assinatura só vale enquanto o documento for
        byte a byte o mesmo. Mudou a dose, a garantia acaba."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-icp5@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:300])

        # Alguém mexe na prescrição depois de assinada.
        from .models import CicloQuimioterapia
        c = CicloQuimioterapia.objects.get(id=ciclo_id)
        doses = c.doses_calculadas
        doses[0]["dose_calculada"] = float(doses[0]["dose_calculada"] or 0) + 50
        c.doses_calculadas = doses
        c.save(update_fields=["doses_calculadas"])

        d = client.get(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/").json()
        self.assertFalse(d["assinada"])
        self.assertEqual(d["assinatura"]["status"], "invalidada")
        self.assertFalse(d["assinatura"]["conferencia"]["integro"])
        self.assertNotEqual(d["assinatura"]["conferencia"]["hash_atual"],
                            d["assinatura"]["conferencia"]["hash_assinado"])
        self.assertIn("alterada após a assinatura",
                      d["assinatura"]["conferencia"]["mensagem"])

    def test_nao_assina_duas_vezes_o_mesmo_documento_integro(self):
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-icp6@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        corpo = {"signatario_nome": "Dra. Helena Duarte",
                 "signatario_cpf": "52998224725"}
        client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                    data=corpo, content_type="application/json")
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data=corpo, content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "ja_assinada")

    def test_certificado_vencido_nao_assina(self):
        """A ICP-Brasil não reconhece assinatura feita com certificado vencido."""
        caminho, senha = self._certificado_teste(dias_validade=-1,
                                                 valido_de_dias=-400)
        empresa = _empresa("Hospital Rede", "onco-icp7@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["codigo"], "certificado_vencido")
        from .models import AssinaturaDocumento
        self.assertEqual(
            AssinaturaDocumento.objects.filter(status="assinada").count(), 0)

    def test_certificado_inexistente_reporta_o_que_falta(self):
        """Arquivo que não existe: a configuração nasce pendente e diz o motivo."""
        empresa = _empresa("Hospital Rede", "onco-icp8@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._cert(client, provedor="a1_local",
                       a1_caminho="/caminho/que/nao/existe.pfx", a1_senha="x")
        self.assertEqual(r.status_code, 201)
        c = r.json()["certificado"]
        self.assertEqual(c["status"], "pendente")
        self.assertFalse(c["pronto_para_assinar"])
        self.assertTrue(any("não encontrado" in p for p in c["pendencias"]))

        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 503)

    def test_ciclo_sem_doses_nao_tem_o_que_assinar(self):
        empresa = _empresa("Hospital Rede", "onco-icp9@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(
            empresa, drogas=[{"droga": "X", "dose": 1, "unidade": "mg", "dia": 1}])
        from .models import CicloQuimioterapia
        ciclo = CicloQuimioterapia.objects.create(
            empresa=empresa, protocolo=protocolo, paciente_nome="Sem Dose",
            cid10_principal="C18", numero_ciclo=1, data_inicio=date.today(),
            doses_calculadas=[])
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo.id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "sem_doses")

    def test_assinatura_registra_quem_assinou_e_o_certificado_usado(self):
        """Signatário (o profissional) e titular do certificado são coisas
        distintas e as duas ficam registradas: é o que permite auditar se
        alguém assinou com o certificado de outra pessoa."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-icp10@example.com",
                           "hospital_rede")
        client = _client_for(empresa)
        # Configuração em nome do Dr. Paulo, mas o ARQUIVO é da Dra. Helena.
        self._cert(client, profissional_nome="Dr. Paulo Vieira",
                   profissional_cpf="11144477735",
                   profissional_registro="CRM-MS 98765",
                   provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                    data={"signatario_nome": "Dr. Paulo Vieira",
                          "signatario_cpf": "11144477735",
                          "signatario_registro": "CRM-MS 98765"},
                    content_type="application/json")
        d = client.get(
            f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/").json()
        a = d["assinatura"]
        self.assertEqual(a["signatario_nome"], "Dr. Paulo Vieira")
        self.assertEqual(a["signatario_registro"], "CRM-MS 98765")
        # O certificado é de OUTRA pessoa — fica evidente na auditoria.
        self.assertEqual(a["certificado"]["titular"], "HELENA DUARTE")
        self.assertTrue(a["conferencia"]["integro"])

    def _cert(self, client, **extra):
        payload = {"profissional_nome": "Dra. Helena Duarte",
                   "profissional_cpf": "52998224725",
                   "profissional_registro": "CRM-MS 12345",
                   "provedor": "vidaas"}
        payload.update(extra)
        return client.post("/api/hospital/oncologia/certificados/",
                           data=payload, content_type="application/json")

    def test_certificado_e_por_profissional_nao_por_instalacao(self):
        """O certificado é do MÉDICO, não da empresa que vende o software nem
        do hospital. Dois médicos no mesmo hospital = duas configurações."""
        empresa = _empresa("Hospital Rede", "onco-cert1@example.com", "hospital_rede")
        client = _client_for(empresa)
        r1 = self._cert(client)
        self.assertEqual(r1.status_code, 201)
        r2 = self._cert(client, profissional_nome="Dr. Paulo Vieira",
                        profissional_cpf="11144477735",
                        profissional_registro="CRM-MS 98765")
        self.assertEqual(r2.status_code, 201)
        d = client.get("/api/hospital/oncologia/certificados").json()
        self.assertEqual(d["total"], 2)
        self.assertIn("médico", d["titularidade"])
        self.assertIn("Não é da empresa", d["titularidade"])

    def test_mesmo_profissional_nao_duplica_na_empresa(self):
        """Duas configurações para o mesmo CPF deixariam a auditoria sem saber
        qual delas assinou."""
        empresa = _empresa("Hospital Rede", "onco-cert2@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client)
        r = self._cert(client)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "profissional_duplicado")

    def test_segredos_nunca_voltam_na_resposta(self):
        """Token e senha saem do sistema só para o provedor — nunca para a tela."""
        empresa = _empresa("Hospital Rede", "onco-cert3@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._cert(client, provedor="api_hospital",
                       api_url="https://assinatura.hospital.exemplo/v1/assinar",
                       api_token="token-secreto-do-hospital")
        self.assertEqual(r.status_code, 201)
        corpo = r.content.decode()
        self.assertNotIn("token-secreto-do-hospital", corpo)
        self.assertTrue(r.json()["certificado"]["tem_api_token"])
        listagem = client.get("/api/hospital/oncologia/certificados").content.decode()
        self.assertNotIn("token-secreto-do-hospital", listagem)

    def test_segredo_fica_cifrado_em_repouso(self):
        """O token é dado sensível: no banco não pode estar em texto claro."""
        from django.db import connection
        from .models import CertificadoAssinante
        empresa = _empresa("Hospital Rede", "onco-cert4@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="api_hospital",
                   api_url="https://assinatura.hospital.exemplo/v1/assinar",
                   api_token="token-secreto-do-hospital")
        c = CertificadoAssinante.objects.get(empresa=empresa)
        # Pela ORM volta decifrado...
        self.assertEqual(c.api_token, "token-secreto-do-hospital")
        # ...mas o valor cru no banco não contém o segredo.
        with connection.cursor() as cur:
            cur.execute("SELECT api_token FROM api_certificadoassinante WHERE id=%s",
                        [c.id])
            cru = cur.fetchone()[0]
        self.assertNotIn("token-secreto-do-hospital", cru or "")

    def test_api_do_hospital_exige_https(self):
        """Resumo de documento clínico e token não trafegam em texto claro."""
        empresa = _empresa("Hospital Rede", "onco-cert5@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._cert(client, provedor="api_hospital",
                       api_url="http://assinatura.hospital.exemplo/v1/assinar",
                       api_token="x")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "api_url_insegura")

    def test_configuracao_incompleta_nao_fica_ativa(self):
        """Nuvem sem credencial de aplicação não assina — e o sistema não pode
        deixar o hospital achar que está pronto."""
        empresa = _empresa("Hospital Rede", "onco-cert6@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._cert(client)          # vidaas sem cliente_id/segredo
        self.assertEqual(r.status_code, 201)
        c = r.json()["certificado"]
        self.assertEqual(c["status"], "pendente")
        self.assertFalse(c["pronto_para_assinar"])
        self.assertTrue(c["pendencias"])
        r = client.put(f"/api/hospital/oncologia/certificados/{c['id']}/",
                       data={"status": "ativo"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "configuracao_incompleta")

    def test_status_de_assinatura_responde_pelo_profissional(self):
        """'Dá para assinar?' só faz sentido perguntando de QUEM."""
        empresa = _empresa("Hospital Rede", "onco-cert7@example.com", "hospital_rede")
        client = _client_for(empresa)
        caminho, senha = self._certificado_teste()
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        # Médico configurado
        d = client.get("/api/hospital/oncologia/assinatura/status"
                       "?cpf=52998224725").json()
        self.assertTrue(d["disponivel"])
        self.assertEqual(d["profissional"], "Dra. Helena Duarte")
        # Outro médico do MESMO hospital segue sem certificado
        d = client.get("/api/hospital/oncologia/assinatura/status"
                       "?medico=Dr.%20Desconhecido").json()
        self.assertFalse(d["disponivel"])
        self.assertEqual(d["assinantes_ativos"], 1)

    def test_assina_com_o_certificado_do_profissional_do_ciclo(self):
        empresa = _empresa("Hospital Rede", "onco-cert8@example.com", "hospital_rede")
        client = _client_for(empresa)
        caminho, senha = self._certificado_teste()
        rc = self._cert(client, provedor="a1_local",
                        a1_caminho=caminho, a1_senha=senha)
        cert_id = rc.json()["id"]
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo,
                                      medico_oncologista="Dra. Helena Duarte")
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:400])
        a = r.json()["assinatura"]
        self.assertTrue(r.json()["assinada"])
        # Fica registrado QUAL configuração assinou.
        self.assertEqual(a["certificado_config_id"], cert_id)

    def test_medico_sem_certificado_nao_assina_mesmo_com_outro_configurado(self):
        """Ter um médico configurado não habilita o hospital inteiro."""
        empresa = _empresa("Hospital Rede", "onco-cert9@example.com", "hospital_rede")
        client = _client_for(empresa)
        caminho, senha = self._certificado_teste()
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dr. Sem Certificado"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 503)
        from .models import AssinaturaDocumento
        self.assertEqual(
            AssinaturaDocumento.objects.filter(status="assinada").count(), 0)

    def test_certificados_isolados_por_empresa(self):
        """Hospital A não enxerga nem altera o certificado do hospital B."""
        a = _empresa("Hospital A", "onco-cert-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-cert-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        cid = self._cert(ca).json()["id"]
        self.assertEqual(
            cb.get("/api/hospital/oncologia/certificados").json()["total"], 0)
        r = cb.put(f"/api/hospital/oncologia/certificados/{cid}/",
                   data={"profissional_nome": "Invasor"},
                   content_type="application/json")
        self.assertEqual(r.status_code, 404)
        r = cb.delete(f"/api/hospital/oncologia/certificados/{cid}/")
        self.assertEqual(r.status_code, 404)

    def test_desativar_preserva_a_auditoria(self):
        """Apagar a configuração deixaria assinaturas antigas órfãs: desativa."""
        from .models import CertificadoAssinante
        empresa = _empresa("Hospital Rede", "onco-cert10@example.com",
                           "hospital_rede")
        client = _client_for(empresa)
        cid = self._cert(client).json()["id"]
        r = client.delete(f"/api/hospital/oncologia/certificados/{cid}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            CertificadoAssinante.objects.get(id=cid).status, "inativo")

    # ── Interação medicamentosa (subconjunto curado) ───────────────────────
    def test_capecitabina_com_varfarina_e_alerta_grave(self):
        """O caso que motivou tudo: alerta de caixa-preta. Prescrever
        capecitabina para quem usa varfarina sem avisar é omissão séria."""
        empresa = _empresa("Hospital Rede", "onco-int1@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post("/api/hospital/oncologia/interacoes/",
                        data={"medicamentos": ["Capecitabina", "Varfarina"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["graves"], 1)
        i = d["interacoes"][0]
        self.assertEqual(i["gravidade"], "grave")
        self.assertIn("RNI", i["mecanismo"])
        self.assertIn("heparina", i["conduta"].lower())
        self.assertIn("caixa-preta", i["fonte"].lower())

    def test_reconhece_nome_comercial_e_sinonimo(self):
        """Quem prescreve escreve 'Xeloda' e 'Marevan'. Se o sistema só casa o
        nome genérico, o alerta de caixa-preta simplesmente não dispara."""
        empresa = _empresa("Hospital Rede", "onco-int2@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post("/api/hospital/oncologia/interacoes/",
                        data={"medicamentos": ["Xeloda 500mg", "Marevan"]},
                        content_type="application/json")
        self.assertEqual(r.json()["graves"], 1)

    def test_interacao_por_classe_e_nao_so_por_molecula(self):
        """Metotrexato + ibuprofeno tem de alertar: o que importa clinicamente
        é a classe (anti-inflamatório), não a molécula exata."""
        empresa = _empresa("Hospital Rede", "onco-int3@example.com", "hospital_rede")
        client = _client_for(empresa)
        for aine in ("Ibuprofeno", "Naproxeno", "Diclofenaco"):
            r = client.post("/api/hospital/oncologia/interacoes/",
                            data={"medicamentos": ["Metotrexato", aine]},
                            content_type="application/json")
            self.assertEqual(r.json()["graves"], 1, f"falhou para {aine}")

    def test_tamoxifeno_com_fluoxetina_alerta_perda_de_eficacia(self):
        """A interação que não causa toxicidade — reduz a EFICÁCIA. É a que
        passa despercebida porque o paciente não piora na hora."""
        empresa = _empresa("Hospital Rede", "onco-int4@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post("/api/hospital/oncologia/interacoes/",
                        data={"medicamentos": ["Tamoxifeno", "Fluoxetina"]},
                        content_type="application/json")
        d = r.json()
        self.assertEqual(d["graves"], 1)
        self.assertIn("endoxifeno", d["interacoes"][0]["mecanismo"])

    def test_resposta_sempre_diz_que_e_subconjunto(self):
        """'Nenhuma interação encontrada' NÃO pode ser lido como 'seguro'."""
        empresa = _empresa("Hospital Rede", "onco-int5@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post("/api/hospital/oncologia/interacoes/",
                        data={"medicamentos": ["Soro fisiológico", "Dipirona"]},
                        content_type="application/json")
        d = r.json()
        self.assertEqual(d["total"], 0)
        self.assertIn("não substitui", d["escopo"])
        self.assertIn("Ausência de alerta não significa", d["escopo"])

    def test_ciclo_alerta_interacao_na_criacao(self):
        """O alerta tem de aparecer sozinho, não só se alguém for consultar."""
        empresa = _empresa("Hospital Rede", "onco-int6@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(
            empresa,
            drogas=[{"droga": "Metotrexato", "dose": 50, "unidade": "mg/m²", "dia": 1}])
        protocolo.drogas_suporte = [
            {"droga": "Ibuprofeno", "dose": 400, "unidade": "mg",
             "via": "VO", "momento": "se dor"}]
        protocolo.save(update_fields=["drogas_suporte"])
        r = self._criar_ciclo(client, protocolo, neutrofilos=2500,
                              plaquetas=220000)
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertGreaterEqual(d["interacoes"]["graves"], 1)
        self.assertTrue(any("Interação GRAVE" in a for a in d["alertas"]))

    def test_oral_checa_contra_o_ciclo_em_andamento(self):
        """A capecitabina oral precisa ser checada contra o que o paciente já
        recebe — inclusive medicamento de fora da oncologia."""
        empresa = _empresa("Hospital Rede", "onco-int7@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post(
            "/api/hospital/oncologia/quimio-oral/",
            data={"paciente_nome": "Paciente Anticoagulado",
                  "droga": "Capecitabina", "unidades_por_dia": 2,
                  "dias_uso": 14, "dias_pausa": 7,
                  "data_inicio": date.today().isoformat(),
                  "medicamentos_em_uso": ["Varfarina 5mg"]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertGreaterEqual(d["interacoes"]["graves"], 1)
        self.assertTrue(any("Interação GRAVE" in a for a in d["alertas"]))

    def test_falha_na_checagem_nao_derruba_a_criacao_do_ciclo(self):
        """O médico nunca é bloqueado por uma falha da checagem."""
        from unittest.mock import patch
        empresa = _empresa("Hospital Rede", "onco-int8@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        with patch("api.services.interacoes_onco.checar",
                   side_effect=RuntimeError("base fora do ar")):
            r = self._criar_ciclo(client, protocolo, neutrofilos=2500,
                                  plaquetas=220000)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["interacoes"].get("falha"))

    def test_base_curada_e_semeada_e_idempotente(self):
        from .models import InteracaoMedicamentosa
        from .services.interacoes_onco import seed_interacoes, BASE_CURADA
        empresa = _empresa("Hospital Rede", "onco-int9@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = client.get("/api/hospital/oncologia/interacoes").json()
        self.assertEqual(d["total"], len(BASE_CURADA))
        self.assertGreater(d["graves"], 10)
        seed_interacoes(empresa)      # de novo não duplica
        self.assertEqual(
            InteracaoMedicamentosa.objects.filter(empresa=empresa).count(),
            len(BASE_CURADA))

    def test_toda_interacao_tem_mecanismo_conduta_e_fonte(self):
        """Alerta sem conduta é só um susto: a equipe não sabe o que fazer."""
        from .services.interacoes_onco import BASE_CURADA
        for a, b, gravidade, mecanismo, conduta, fonte in BASE_CURADA:
            self.assertTrue(mecanismo.strip(), f"{a}+{b} sem mecanismo")
            self.assertTrue(conduta.strip(), f"{a}+{b} sem conduta")
            self.assertTrue(fonte.strip(), f"{a}+{b} sem fonte")
            self.assertIn(gravidade, ("grave", "moderada", "leve"))

    def test_interacoes_isoladas_por_empresa(self):
        a = _empresa("Hospital A", "onco-int-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-int-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        ca.get("/api/hospital/oncologia/interacoes")     # semeia só o A
        from .models import InteracaoMedicamentosa
        self.assertEqual(
            InteracaoMedicamentosa.objects.filter(empresa=b).count(), 0)
        # O B semeia a sua própria base, sem ver a do A.
        db = cb.get("/api/hospital/oncologia/interacoes").json()
        self.assertTrue(db["total"] > 0)
        self.assertEqual(
            InteracaoMedicamentosa.objects.filter(empresa=a).count(),
            InteracaoMedicamentosa.objects.filter(empresa=b).count())

    # ── Código de barras na pulseira (os "cinco certos") ───────────────────
    def _pulseira(self, client, nome, cpf=""):
        return client.post("/api/hospital/oncologia/pulseiras/",
                           data={"paciente_nome": nome, "cpf_paciente": cpf,
                                 "emitida_por": "Recepção"},
                           content_type="application/json")

    def test_pulseira_trocada_bloqueia_a_administracao(self):
        """O ERRO QUE ISTO EXISTE PARA PEGAR: paciente trocado. A dupla
        checagem por nome não pega quando os dois profissionais leem a mesma
        tela errada — a leitura do código pega."""
        empresa = _empresa("Hospital Rede", "onco-cb1@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(client, protocolo,
                                     paciente_nome="Maria Souza",
                                     neutrofilos=2500, plaquetas=220000
                                     ).json()["id"]
        pid = self._preparar_ate_conferido(client, ciclo_id)
        etiqueta = client.get(
            f"/api/hospital/oncologia/preparos/{pid}/etiqueta").json()
        # Pulseira de OUTRO paciente.
        outra = self._pulseira(client, "João Pereira").json()["pulseira"]

        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid,
                              "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "codigo_paciente": outra["codigo"],
                              "codigo_preparo": etiqueta["codigo"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        d = r.json()
        self.assertEqual(d["codigo"], "paciente_divergente")
        self.assertIn("NÃO administrar", d["erro"])
        self.assertIn("João Pereira", d["erro"])
        self.assertIn("Maria Souza", d["erro"])
        from .models import AdministracaoQuimioterapia
        self.assertEqual(AdministracaoQuimioterapia.objects.count(), 0)

    def test_pulseira_certa_libera_e_registra_a_conferencia(self):
        empresa = _empresa("Hospital Rede", "onco-cb2@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(client, protocolo,
                                     paciente_nome="Maria Souza",
                                     neutrofilos=2500, plaquetas=220000
                                     ).json()["id"]
        pid = self._preparar_ate_conferido(client, ciclo_id)
        etiqueta = client.get(
            f"/api/hospital/oncologia/preparos/{pid}/etiqueta").json()
        pulseira = self._pulseira(client, "Maria Souza").json()["pulseira"]

        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid,
                              "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "codigo_paciente": pulseira["codigo"],
                              "codigo_preparo": etiqueta["codigo"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertTrue(r.json()["administracao"]["conferido_por_codigo"])
        d = client.get("/api/hospital/oncologia/administracoes").json()
        self.assertEqual(d["conferidas_por_codigo"], 1)
        self.assertEqual(d["adesao_codigo_pct"], 100.0)

    def test_frasco_de_outro_preparo_e_recusado(self):
        """Ler o frasco errado do mesmo paciente também é erro de medicação."""
        empresa = _empresa("Hospital Rede", "onco-cb3@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        pulseira = self._pulseira(client, "Paciente Onco").json()["pulseira"]
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid,
                              "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "codigo_paciente": pulseira["codigo"],
                              "codigo_preparo": "PRE-XXXXXXXX"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "preparo_divergente")

    def test_ler_so_o_frasco_nao_basta(self):
        """Conferir só o frasco não identifica QUEM vai receber."""
        empresa = _empresa("Hospital Rede", "onco-cb4@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        etiqueta = client.get(
            f"/api/hospital/oncologia/preparos/{pid}/etiqueta").json()
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid,
                              "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "codigo_preparo": etiqueta["codigo"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "falta_codigo_paciente")

    def test_pulseira_desativada_nao_confere(self):
        """Reemitir a pulseira desativa a anterior: duas ativas tornariam a
        conferência ambígua."""
        empresa = _empresa("Hospital Rede", "onco-cb5@example.com", "hospital_rede")
        client = _client_for(empresa)
        antiga = self._pulseira(client, "Maria Souza",
                                cpf="52998224725").json()["pulseira"]
        nova = self._pulseira(client, "Maria Souza",
                              cpf="52998224725").json()["pulseira"]
        self.assertNotEqual(antiga["codigo"], nova["codigo"])
        d = client.get("/api/hospital/oncologia/pulseiras").json()
        self.assertEqual(d["total"], 1)

        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(client, protocolo,
                                     paciente_nome="Maria Souza",
                                     cpf_paciente="52998224725",
                                     neutrofilos=2500, plaquetas=220000
                                     ).json()["id"]
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego",
                              "codigo_paciente": antiga["codigo"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "pulseira_desconhecida")

    def test_conferencia_previa_antes_de_abrir_o_formulario(self):
        """A enfermagem descobre a divergência com o frasco ainda na mão."""
        empresa = _empresa("Hospital Rede", "onco-cb6@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(client, protocolo,
                                     paciente_nome="Maria Souza",
                                     neutrofilos=2500, plaquetas=220000
                                     ).json()["id"]
        pid = self._preparar_ate_conferido(client, ciclo_id)
        etiqueta = client.get(
            f"/api/hospital/oncologia/preparos/{pid}/etiqueta").json()
        certa = self._pulseira(client, "Maria Souza").json()["pulseira"]
        errada = self._pulseira(client, "João Pereira").json()["pulseira"]

        r = client.post("/api/hospital/oncologia/conferir-codigos/",
                        data={"codigo_preparo": etiqueta["codigo"],
                              "codigo_paciente": certa["codigo"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["confere"])
        self.assertEqual(r.json()["paciente_nome"], "Maria Souza")

        r = client.post("/api/hospital/oncologia/conferir-codigos/",
                        data={"codigo_preparo": etiqueta["codigo"],
                              "codigo_paciente": errada["codigo"]},
                        content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()["confere"])

    def test_codigo_evita_caracteres_ambiguos(self):
        """Quando o leitor falha alguém digita à mão: confundir 0 com O vira
        paciente errado."""
        empresa = _empresa("Hospital Rede", "onco-cb7@example.com", "hospital_rede")
        client = _client_for(empresa)
        for i in range(12):
            c = self._pulseira(client, f"Paciente {i}").json()["pulseira"]["codigo"]
            corpo = c.split("-", 1)[1]
            for proibido in ("0", "O", "1", "I", "L"):
                self.assertNotIn(proibido, corpo,
                                 f"código ambíguo gerado: {c}")

    def test_administracao_sem_codigo_continua_possivel(self):
        """Hospital que ainda não tem leitor não pode ficar impedido de
        administrar — a leitura soma, não substitui o fluxo."""
        empresa = _empresa("Hospital Rede", "onco-cb8@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        pid = self._preparar_ate_conferido(client, ciclo_id)
        r = client.post("/api/hospital/oncologia/administracoes/",
                        data={"preparo_id": pid, "administrado_por": "Enf. Carla",
                              "checado_por": "Enf. Diego"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.json()["administracao"]["conferido_por_codigo"])
        d = client.get("/api/hospital/oncologia/administracoes").json()
        self.assertEqual(d["adesao_codigo_pct"], 0.0)

    def test_pulseiras_isoladas_por_empresa(self):
        a = _empresa("Hospital A", "onco-cb-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-cb-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        pulseira_a = self._pulseira(ca, "Maria Souza").json()["pulseira"]
        self.assertEqual(cb.get("/api/hospital/oncologia/pulseiras").json()["total"], 0)
        # A pulseira do hospital A não confere no hospital B.
        ciclo_b = self._ciclo_pronto(cb, self._protocolo(b))
        pid_b = self._preparar_ate_conferido(cb, ciclo_b)
        r = cb.post("/api/hospital/oncologia/administracoes/",
                    data={"preparo_id": pid_b, "administrado_por": "X",
                          "checado_por": "Y",
                          "codigo_paciente": pulseira_a["codigo"]},
                    content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["codigo"], "pulseira_desconhecida")

    # ── Conformidade CFM 2.299/2021 (deveres do ESTABELECIMENTO) ───────────
    def test_hora_de_emissao_nao_quebra_a_verificacao(self):
        """REGRESSÃO CRÍTICA: o art. 2º exige data E HORA no documento. Se a
        verificação recalculasse o conteúdo com a hora atual, NENHUMA
        assinatura conferiria — toda prescrição assinada viraria 'adulterada'
        no segundo seguinte."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-cf1@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:300])
        # Confere várias vezes: tem de continuar íntegro sempre.
        for _ in range(3):
            d = client.get(
                f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/").json()
            self.assertTrue(d["assinada"], d)
            self.assertTrue(d["assinatura"]["conferencia"]["integro"])
        from .models import AssinaturaDocumento
        a = AssinaturaDocumento.objects.get(objeto_id=ciclo_id, status="assinada")
        self.assertIsNotNone(a.documento_emitido_em)

    def test_documento_carrega_crm_rqe_e_estabelecimento(self):
        """Art. 2º: nome, CRM e endereço do médico, RQE, e identificação do
        paciente. Assinar sem isso deixa o documento incompleto."""
        from .models import ResponsabilidadeTecnica, CertificadoAssinante
        from .services.assinatura_icp import conteudo_canonico_prescricao
        empresa = _empresa("Hospital Rede", "onco-cf2@example.com", "hospital_rede")
        client = _client_for(empresa)
        ResponsabilidadeTecnica.objects.create(
            empresa=empresa, crm_pessoa_juridica="CRM-MS PJ 555",
            uf_conselho="MS", diretor_tecnico_nome="Dr. Diretor",
            diretor_tecnico_crm="CRM-MS 111", endereco="Rua do Hospital, 100",
            cnes="1234567")
        self._cert(client, profissional_rqe="RQE 4321",
                   profissional_endereco="Av. Central, 50 - sala 3")
        cfg = CertificadoAssinante.objects.get(empresa=empresa)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._criar_ciclo(client, protocolo, cpf_paciente="52998224725",
                                     neutrofilos=2500, plaquetas=220000).json()["id"]
        from .models import CicloQuimioterapia
        ciclo = CicloQuimioterapia.objects.get(id=ciclo_id)
        conteudo = conteudo_canonico_prescricao(ciclo, cfg=cfg)
        for esperado in ("CRM-MS 12345", "RQE 4321", "Av. Central, 50",
                         "CRM-MS PJ 555", "Dr. Diretor", "Rua do Hospital, 100",
                         "emitido_em"):
            self.assertIn(esperado, conteudo, f"faltou {esperado} no documento")

    def test_avisa_o_que_falta_do_art2_sem_impedir_a_assinatura(self):
        """O médico não é bloqueado — mas precisa saber que o documento sai
        incompleto."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-cf3@example.com", "hospital_rede")
        client = _client_for(empresa)
        # Sem CRM, sem endereço, e o paciente sem CPF.
        self._cert(client, profissional_registro="", provedor="a1_local",
                   a1_caminho=caminho, a1_senha=senha)
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201)
        faltando = r.json()["elementos_faltando_art2"]
        self.assertIn("CRM do médico", faltando)
        self.assertIn("número do documento legal do paciente", faltando)
        self.assertIn("incompleto", r.json()["alerta"])

    def test_painel_diz_o_que_falta_e_de_quem_e_o_dever(self):
        """O dever do art. 5º é do ESTABELECIMENTO, não de quem fornece o
        software — e o painel precisa deixar isso explícito."""
        empresa = _empresa("Hospital Rede", "onco-cf4@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = client.get("/api/hospital/oncologia/conformidade").json()
        self.assertFalse(d["conforme"])
        self.assertTrue(any("CRM" in p for p in d["pendencias"]))
        self.assertTrue(any("Diretor Técnico" in p for p in d["pendencias"]))
        self.assertIn("ESTABELECIMENTO DE SAÚDE", d["de_quem_e_o_dever"])
        self.assertIn("não presta nem intermedeia", d["de_quem_e_o_dever"])
        self.assertTrue(d["base_normativa"])

    def test_preencher_responsabilidade_tecnica_zera_as_pendencias(self):
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "onco-cf5@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho,
                   a1_senha=senha, profissional_endereco="Av. Central, 50")
        r = client.put("/api/hospital/oncologia/conformidade/",
                       data={"crm_pessoa_juridica": "CRM-MS PJ 555",
                             "uf_conselho": "MS",
                             "diretor_tecnico_nome": "Dr. Diretor",
                             "diretor_tecnico_crm": "CRM-MS 111",
                             "endereco": "Rua do Hospital, 100",
                             "cnes": "1234567",
                             "ciente_informado_em": date.today().isoformat()},
                       content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["conforme"], d["pendencias"])
        self.assertEqual(d["assinantes_prontos"], 1)

    def test_validacao_do_prescritor_admite_que_nao_esta_configurada(self):
        """O web service do CFM é tarifado. Sem credencial, dizer isso é melhor
        que devolver um 'médico regular' que ninguém verificou."""
        empresa = _empresa("Hospital Rede", "onco-cf6@example.com", "hospital_rede")
        client = _client_for(empresa)
        v = client.get("/api/hospital/oncologia/conformidade").json()["validacao_prescritor"]
        self.assertFalse(v["disponivel"])
        self.assertIn("conferida manualmente", v["mensagem"])
        self.assertTrue(any("tarifado" in p for p in v["pendencias"]))

    def test_conformidade_isolada_por_empresa(self):
        a = _empresa("Hospital A", "onco-cf-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-cf-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        ca.put("/api/hospital/oncologia/conformidade/",
               data={"crm_pessoa_juridica": "CRM-MS PJ 555",
                     "diretor_tecnico_nome": "Dr. A"},
               content_type="application/json")
        d = cb.get("/api/hospital/oncologia/conformidade").json()
        self.assertEqual(d["estabelecimento"]["crm_pessoa_juridica"], "")
        self.assertEqual(d["estabelecimento"]["diretor_tecnico_nome"], "")

    # ── Prescrição de internação assinada (fora da oncologia) ──────────────
    def _internacao_com_prescricao(self, empresa, medico="Dra. Helena Duarte"):
        from .models import (PacienteHospital, InternacaoHospital,
                             PrescricaoMedica)
        pac = PacienteHospital.objects.create(
            empresa=empresa, nome="Paciente Internado", cpf="52998224725")
        inte = InternacaoHospital.objects.create(
            empresa=empresa, paciente=pac, diagnostico="Pneumonia",
            medico_responsavel=medico)
        for med, dose in (("Ceftriaxona", "1g"), ("Dipirona", "1g")):
            # PrescricaoMedica não tem empresa: o tenant vem pela internação.
            PrescricaoMedica.objects.create(
                internacao=inte, medicamento=med,
                dose=dose, via="ev", frequencia="12/12h", status="ativa",
                medico=medico)
        return inte

    def test_prescricao_de_internacao_assina_com_certificado_do_medico(self):
        """A Resolução CFM 2.299/2021 lista 'Prescrição' no art. 1º — não é
        privilégio da oncologia. E o certificado é do MÉDICO (art. 4º)."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "presc-a1@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        inte = self._internacao_com_prescricao(empresa)
        r = client.post(
            f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/",
            data={"signatario_nome": "Dra. Helena Duarte",
                  "signatario_cpf": "52998224725"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:400])
        d = r.json()
        self.assertTrue(d["assinada"])
        self.assertEqual(d["itens_assinados"], 2)
        self.assertTrue(d["conforme_cfm"])
        self.assertEqual(d["formato"], "ICP-Brasil-CAdES-BES")

    def test_acrescentar_item_depois_invalida_a_assinatura(self):
        """Assina-se o CONJUNTO: se bastasse assinar item a item, alguém
        acrescentaria uma linha depois sem invalidar nada."""
        from .models import PrescricaoMedica
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "presc-a2@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        inte = self._internacao_com_prescricao(empresa)
        client.post(f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/",
                    data={"signatario_nome": "Dra. Helena Duarte",
                          "signatario_cpf": "52998224725"},
                    content_type="application/json")
        # Alguém acrescenta um medicamento depois.
        PrescricaoMedica.objects.create(
            internacao=inte, medicamento="Morfina",
            dose="10mg", via="ev", status="ativa")
        d = client.get(
            f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/").json()
        self.assertFalse(d["assinada"])
        self.assertEqual(d["assinatura"]["status"], "invalidada")
        self.assertIn("alterada após a assinatura",
                      d["assinatura"]["conferencia"]["mensagem"])

    def test_assinatura_de_prescricao_e_estavel_no_tempo(self):
        """Mesma regressão da oncologia: a hora de emissão não pode fazer a
        verificação falhar sozinha."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "presc-a3@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        inte = self._internacao_com_prescricao(empresa)
        client.post(f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/",
                    data={"signatario_nome": "Dra. Helena Duarte",
                          "signatario_cpf": "52998224725"},
                    content_type="application/json")
        for _ in range(3):
            d = client.get(
                f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/").json()
            self.assertTrue(d["assinada"])
            self.assertTrue(d["assinatura"]["conferencia"]["integro"])

    def test_sem_certificado_nenhum_nao_assina(self):
        empresa = _empresa("Hospital Rede", "presc-a4@example.com", "hospital_rede")
        client = _client_for(empresa)
        inte = self._internacao_com_prescricao(empresa)
        r = client.post(
            f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/",
            data={"signatario_nome": "Dra. Helena Duarte"},
            content_type="application/json")
        self.assertEqual(r.status_code, 503)
        from .models import AssinaturaDocumento
        self.assertEqual(
            AssinaturaDocumento.objects.filter(status="assinada").count(), 0)

    def test_prescricao_vazia_nao_assina(self):
        from .models import PacienteHospital, InternacaoHospital
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Rede", "presc-a5@example.com", "hospital_rede")
        client = _client_for(empresa)
        self._cert(client, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        pac = PacienteHospital.objects.create(empresa=empresa, nome="Sem Itens")
        inte = InternacaoHospital.objects.create(
            empresa=empresa, paciente=pac, diagnostico="X")
        r = client.post(
            f"/api/hospital/internacoes/{inte.id}/prescricao/assinatura/",
            data={"signatario_nome": "Dra. Helena Duarte"},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "prescricao_vazia")

    def test_prescricao_isolada_por_empresa(self):
        a = _empresa("Hospital A", "presc-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "presc-b@example.com", "hospital_rede")
        cb = _client_for(b)
        inte_a = self._internacao_com_prescricao(a)
        r = cb.get(f"/api/hospital/internacoes/{inte_a.id}/prescricao/assinatura/")
        self.assertEqual(r.status_code, 404)
        r = cb.post(f"/api/hospital/internacoes/{inte_a.id}/prescricao/assinatura/",
                    data={"signatario_nome": "X"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_motor_antigo_de_assinatura_continua_intacto(self):
        """Regressão: eu sobrescrevi este módulo por engano uma vez. O fluxo de
        assinatura de evolução clínica, que já existia, tem de seguir de pé."""
        from api.views_hospital_assinatura import (
            api_assinatura_pendentes, api_assinatura_assinar,
            api_assinatura_assinar_lote, hospital_assinatura_page)
        from api.assinatura_digital import assinar_conteudo, verificar_assinatura
        for fn in (api_assinatura_pendentes, api_assinatura_assinar,
                   api_assinatura_assinar_lote, hospital_assinatura_page,
                   assinar_conteudo, verificar_assinatura):
            self.assertTrue(callable(fn))
        # E o motor segue produzindo assinatura verificável sem certificado.
        ok, ass, h, metodo, erro = assinar_conteudo("conteudo", None, "CRM/MS 1")
        self.assertTrue(ok)
        self.assertEqual(metodo, "SHA256")
        v = verificar_assinatura("conteudo", ass, h)
        self.assertTrue(v["integro"])
        self.assertFalse(verificar_assinatura("outro", ass, h)["integro"])

    # ── Roteiro de implantação (hospital que acabou de contratar) ──────────
    def _roteiro(self, client):
        return client.get("/api/hospital/assinatura/implantacao").json()

    def test_hospital_novo_ve_o_caminho_desde_o_primeiro_acesso(self):
        """Quem acaba de contratar precisa chegar e já ver o que fazer, na
        ordem — não descobrir na frente do paciente que não assina."""
        empresa = _empresa("Hospital Novo", "impl-1@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = self._roteiro(client)
        self.assertFalse(d["pronto_para_assinar"])
        self.assertEqual(d["concluidos"], 0)
        self.assertEqual(d["proximo_passo"], "responsabilidade_tecnica")
        ids = [p["id"] for p in d["passos"]]
        self.assertEqual(ids[:4], ["responsabilidade_tecnica",
                                   "cadastrar_medicos",
                                   "certificado_medico",
                                   "primeira_assinatura"])
        # Todo passo explica COMO fazer e cita a base normativa.
        for p in d["passos"]:
            self.assertTrue(p["como_fazer"], f"{p['id']} sem como_fazer")
            self.assertTrue(p["base"], f"{p['id']} sem base normativa")
            self.assertIn(p["de_quem"], ("hospital", "médico"))

    def test_passo_so_libera_depois_do_anterior(self):
        """Mostrar tudo aberto de uma vez faz o hospital começar pelo fim."""
        empresa = _empresa("Hospital Novo", "impl-2@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = self._roteiro(client)
        por_id = {p["id"]: p for p in d["passos"]}
        self.assertTrue(por_id["responsabilidade_tecnica"]["liberado"])
        self.assertFalse(por_id["cadastrar_medicos"]["liberado"])
        self.assertFalse(por_id["certificado_medico"]["liberado"])
        # Opcional nunca fica travado — o hospital decide se precisa.
        self.assertTrue(por_id["sncr"]["liberado"])
        self.assertFalse(por_id["sncr"]["obrigatorio"])

    def test_roteiro_avanca_conforme_o_hospital_preenche(self):
        """O status é CALCULADO do estado real: checklist que o usuário marca
        à mão vira ficção."""
        caminho, senha = self._certificado_teste()
        empresa = _empresa("Hospital Novo", "impl-3@example.com", "hospital_rede")
        client = _client_for(empresa)

        # 1) responsabilidade técnica
        client.put("/api/hospital/oncologia/conformidade/",
                   data={"crm_pessoa_juridica": "CRM-MS PJ 555",
                         "diretor_tecnico_nome": "Dr. Diretor",
                         "diretor_tecnico_crm": "CRM-MS 111",
                         "endereco": "Rua do Hospital, 100",
                         "ciente_informado_em": date.today().isoformat()},
                   content_type="application/json")
        d = self._roteiro(client)
        self.assertEqual(d["concluidos"], 1)
        self.assertEqual(d["proximo_passo"], "cadastrar_medicos")

        # 2) médico cadastrado com os dados do art. 2º e 3) certificado pronto
        self._cert(client, provedor="a1_local", a1_caminho=caminho,
                   a1_senha=senha, profissional_endereco="Av. Central, 50")
        d = self._roteiro(client)
        self.assertEqual(d["concluidos"], 3)
        self.assertEqual(d["proximo_passo"], "primeira_assinatura")
        self.assertEqual(d["assinantes_prontos"], 1)

        # 4) assina de verdade — aí a implantação fecha
        protocolo = self._protocolo(empresa)
        ciclo_id = self._ciclo_pronto(client, protocolo)
        r = client.post(f"/api/hospital/oncologia/ciclos/{ciclo_id}/assinatura/",
                        data={"signatario_nome": "Dra. Helena Duarte",
                              "signatario_cpf": "52998224725"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content[:300])
        d = self._roteiro(client)
        self.assertTrue(d["pronto_para_assinar"])
        self.assertIsNone(d["proximo_passo"])
        self.assertEqual(d["percentual"], 100)

    def test_medico_sem_endereco_trava_o_passo_do_art2(self):
        """Cadastrar o médico não basta: sem CRM e endereço o documento sai
        incompleto, e o roteiro não pode dar por feito."""
        empresa = _empresa("Hospital Novo", "impl-4@example.com", "hospital_rede")
        client = _client_for(empresa)
        client.put("/api/hospital/oncologia/conformidade/",
                   data={"crm_pessoa_juridica": "CRM-MS PJ 555",
                         "diretor_tecnico_nome": "Dr. D", "diretor_tecnico_crm": "C1",
                         "endereco": "", "ciente_informado_em": date.today().isoformat()},
                   content_type="application/json")
        self._cert(client)  # sem endereço do médico nem do estabelecimento
        d = self._roteiro(client)
        por_id = {p["id"]: p for p in d["passos"]}
        self.assertFalse(por_id["cadastrar_medicos"]["concluido"])
        self.assertTrue(por_id["cadastrar_medicos"]["pendencias"])

    def test_roteiro_diz_de_quem_e_cada_passo(self):
        """A confusão sobre quem cumpre o quê custou caro — tem de estar na
        tela, não num documento à parte."""
        empresa = _empresa("Hospital Novo", "impl-5@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = self._roteiro(client)
        quem = d["quem_faz_o_que"]
        self.assertIn("CRM", quem["hospital"])
        self.assertIn("certificado", quem["medico"])
        self.assertIn("ão presta nem intermedeia", quem["fornecedor_do_software"])
        por_id = {p["id"]: p for p in d["passos"]}
        self.assertEqual(por_id["certificado_medico"]["de_quem"], "médico")
        self.assertEqual(por_id["responsabilidade_tecnica"]["de_quem"], "hospital")

    def test_roteiro_isolado_por_empresa(self):
        caminho, senha = self._certificado_teste()
        a = _empresa("Hospital A", "impl-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "impl-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        ca.put("/api/hospital/oncologia/conformidade/",
               data={"crm_pessoa_juridica": "X", "diretor_tecnico_nome": "D",
                     "diretor_tecnico_crm": "C", "endereco": "E",
                     "ciente_informado_em": date.today().isoformat()},
               content_type="application/json")
        self._cert(ca, provedor="a1_local", a1_caminho=caminho, a1_senha=senha)
        self.assertGreater(self._roteiro(ca)["concluidos"], 0)
        self.assertEqual(self._roteiro(cb)["concluidos"], 0)

    def test_assinatura_isolada_por_empresa(self):
        a = _empresa("Hospital A", "onco-icp-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-icp-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        ciclo_a = self._ciclo_pronto(ca, self._protocolo(a))
        r = cb.get(f"/api/hospital/oncologia/ciclos/{ciclo_a}/assinatura/")
        self.assertEqual(r.status_code, 404)
        r = cb.post(f"/api/hospital/oncologia/ciclos/{ciclo_a}/assinatura/",
                    data={"signatario_nome": "X"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_cadeia_isolada_por_empresa(self):
        """Hospital A não enxerga nem administra preparo do hospital B."""
        a = _empresa("Hospital A", "onco-iso-a@example.com", "hospital_rede")
        b = _empresa("Hospital B", "onco-iso-b@example.com", "hospital_rede")
        ca, cb = _client_for(a), _client_for(b)
        ciclo_a = self._ciclo_pronto(ca, self._protocolo(a))
        pid_a = self._preparar_ate_conferido(ca, ciclo_a)
        r = cb.put(f"/api/hospital/oncologia/preparos/{pid_a}/",
                   data={"status": "dispensado"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)
        r = cb.post("/api/hospital/oncologia/administracoes/",
                    data={"preparo_id": pid_a, "administrado_por": "X",
                          "checado_por": "Y"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(cb.get("/api/hospital/oncologia/preparos").json()["total"], 0)

    def test_detalhe_ciclo_traz_pre_medicacao_do_protocolo(self):
        """A tela do ciclo precisa da pré-medicação junto: antiemético é prescrição,
        não observação. Sem isto o detalhe mostra o quimioterápico e esconde o resto."""
        empresa = _empresa("Hospital Rede", "onco-premed@example.com", "hospital_rede")
        client = _client_for(empresa)
        protocolo = self._protocolo(empresa)
        protocolo.drogas_suporte = [
            {"droga": "Ondansetrona", "dose": 8, "unidade": "mg",
             "via": "IV", "momento": "30 min antes"}
        ]
        protocolo.save(update_fields=["drogas_suporte"])
        ciclo_id = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={"protocolo_id": protocolo.id, "paciente_nome": "P",
                  "cid10_principal": "C18", "data_inicio": date.today().isoformat(),
                  "peso_kg": 70, "altura_cm": 170},
            content_type="application/json",
        ).json()["id"]
        d = client.get(f"/api/hospital/oncologia/ciclos/{ciclo_id}/").json()
        self.assertEqual(
            [m["droga"] for m in d["protocolo"]["drogas_suporte"]], ["Ondansetrona"])

    def test_cadastro_protocolo_proprio(self):
        """Hospital pode cadastrar protocolo próprio (POST) além dos seeds."""
        empresa = _empresa("Hospital Rede", "onco-proto@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post(
            "/api/hospital/oncologia/protocolos/",
            data={"codigo": "MEU-PROTO", "nome": "Protocolo Custom",
                  "indicacao_cid": "C50", "ciclos_total": 6, "intervalo_dias": 21,
                  "drogas": [{"droga": "Paclitaxel", "dose": 175, "unidade": "mg/m²", "dia": 1}]},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        # duplicar código → 400
        r2 = client.post(
            "/api/hospital/oncologia/protocolos/",
            data={"codigo": "MEU-PROTO", "nome": "Outro"},
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 400)

    def test_apac_calcula_competencia_final(self):
        """APAC vale 3 competências — a final é competência+2 meses."""
        empresa = _empresa("Hospital Rede", "onco-apac@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post(
            "/api/hospital/oncologia/apacs/",
            data={"paciente_nome": "P", "cid10_principal": "C50", "competencia": "202611"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        apac_id = r.json()["id"]
        det = client.get(f"/api/hospital/oncologia/apacs/{apac_id}/").json()
        # 202611 + 2 meses = 202701
        self.assertEqual(det["competencia_final"], "202701")


class OPMETests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("Hospital Base", "opme-base@example.com", "hospital_medio")
        client = _client_for(empresa)
        self.assertEqual(client.get("/hospital/opme/").status_code, 403)

    def _catalogo(self, client, descricao="Prótese de Quadril", tipo="protese"):
        r = client.post(
            "/api/hospital/opme/catalogo/",
            data={"descricao": descricao, "tipo": tipo},
            content_type="application/json",
        )
        return r

    def test_pagina_liberada_e_cria_item_catalogo_e_autorizacao(self):
        empresa = _empresa("Hospital Rede", "opme-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/opme/").status_code, 200)

        # tipo no singular (choices reais do model)
        r = self._catalogo(client)
        self.assertEqual(r.status_code, 201)
        item_id = r.json()["id"]

        r = client.post(
            "/api/hospital/opme/autorizacoes/",
            data={
                "paciente_nome": "Paciente OPME",
                "medico_solicitante": "Dr. Teste",
                "itens": [{"opme_id": item_id, "quantidade": 1}],
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.get("/api/hospital/opme/kpis/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["catalogo_itens_ativos"], 1)

    def test_tipo_invalido_rejeitado(self):
        """Regressão: 'proteses' (plural) não é choice válida — deve dar 400."""
        empresa = _empresa("Hospital Rede", "opme-tipo@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = self._catalogo(client, tipo="proteses")
        self.assertEqual(r.status_code, 400)

    def test_autorizacao_sem_item_valido_rejeitada(self):
        """Regressão: opme_id inexistente não pode gerar autorização vazia (era 201)."""
        empresa = _empresa("Hospital Rede", "opme-vazia@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post(
            "/api/hospital/opme/autorizacoes/",
            data={
                "paciente_nome": "Paciente X",
                "medico_solicitante": "Dr. Y",
                "itens": [{"opme_id": 999999, "quantidade": 1}],
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(AutorizacaoOPME.objects.filter(empresa=empresa).count(), 0)

    def test_implantavel_exige_serie_e_lote(self):
        """Regressão ANVISA RDC 27/2008: série e lote são obrigatórios."""
        empresa = _empresa("Hospital Rede", "opme-impl@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = self._catalogo(client).json()["id"]

        # sem série/lote → 400
        r = client.post(
            "/api/hospital/opme/implantaveis/",
            data={"opme_id": item_id, "paciente_nome": "P", "data_implante": "2026-08-12"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

        # com série/lote → 201
        r = client.post(
            "/api/hospital/opme/implantaveis/",
            data={"opme_id": item_id, "paciente_nome": "P", "data_implante": "2026-08-12",
                  "numero_serie": "SN-123", "lote_fabricante": "LOTE-9"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

    def test_implantavel_nao_vincula_autorizacao_de_outra_empresa(self):
        """Regressão LGPD: autorizacao_id de OUTRO tenant deve ser rejeitado."""
        empresa_a = _empresa("Hospital A", "opme-a@example.com", "hospital_rede")
        empresa_b = _empresa("Hospital B", "opme-b@example.com", "hospital_rede")
        client_a = _client_for(empresa_a)
        client_b = _client_for(empresa_b)

        # B cria catálogo + autorização
        item_b = self._catalogo(client_b).json()["id"]
        aut_b = client_b.post(
            "/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "Paciente B", "medico_solicitante": "Dr B",
                  "itens": [{"opme_id": item_b, "quantidade": 1}]},
            content_type="application/json",
        ).json()["id"]

        # A tenta pendurar seu implante na autorização de B
        item_a = self._catalogo(client_a).json()["id"]
        r = client_a.post(
            "/api/hospital/opme/implantaveis/",
            data={"opme_id": item_a, "paciente_nome": "Paciente A",
                  "data_implante": "2026-08-12", "numero_serie": "SN-A", "lote_fabricante": "L-A",
                  "autorizacao_id": aut_b},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)
        # nenhum implante de A pendurado na autorização de B
        self.assertEqual(
            ImplantavelRegistro.objects.filter(autorizacao_id=aut_b).count(), 0)

    def test_estado_negada_nao_pode_ser_aprovada(self):
        """Regressão: máquina de estados bloqueia negada→aprovada."""
        empresa = _empresa("Hospital Rede", "opme-fsm@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = self._catalogo(client).json()["id"]
        aut_id = client.post(
            "/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json",
        ).json()["id"]

        # nega (com motivo)
        r = client.post(
            f"/api/hospital/opme/autorizacoes/{aut_id}/acao/",
            data={"acao": "negar", "observacao": "fora do padrão"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        # tenta aprovar a já negada → 409
        r = client.post(
            f"/api/hospital/opme/autorizacoes/{aut_id}/acao/",
            data={"acao": "aprovar"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 409)

    def test_triagem_sinaliza_acima_do_teto(self):
        """GAP-2: item com preço acima do teto é sinalizado fora do padrão."""
        empresa = _empresa("Hospital Rede", "opme-teto@example.com", "hospital_rede")
        client = _client_for(empresa)
        # cria item com teto R$ 1000
        item_id = client.post(
            "/api/hospital/opme/catalogo/",
            data={"descricao": "Stent X", "tipo": "material", "preco_maximo": 1000},
            content_type="application/json",
        ).json()["id"]
        r = client.post(
            "/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "Único stent disponível compatível com o calibre do vaso do paciente.",
                  "itens": [{"opme_id": item_id, "quantidade": 1, "preco_solicitado": 2500}]},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertTrue(body["alertas_triagem"], "deveria alertar preço acima do teto")
        self.assertIn("acima do teto", " ".join(body["alertas_triagem"]))
        # IA deu uma recomendação
        self.assertIn(body["ia"]["decisao"], ("aprovada", "negada", "revisao"))

    def test_triagem_material_nao_homologado(self):
        """GAP-2: material não homologado é sinalizado."""
        empresa = _empresa("Hospital Rede", "opme-homol@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post(
            "/api/hospital/opme/catalogo/",
            data={"descricao": "Material experimental", "tipo": "material", "homologado": False},
            content_type="application/json",
        ).json()["id"]
        r = client.post(
            "/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "Material experimental necessário — ausência de alternativa homologada no mercado.",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("homologado", " ".join(r.json()["alertas_triagem"]).lower())

    def test_procedimento_padroniza_e_triagem_fora_da_lista(self):
        """GAP-1: material fora da lista padronizada do procedimento é sinalizado."""
        empresa = _empresa("Hospital Rede", "opme-proc@example.com", "hospital_rede")
        client = _client_for(empresa)
        permitido = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese padrão", "tipo": "protese"},
            content_type="application/json").json()["id"]
        outro = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese alternativa", "tipo": "protese"},
            content_type="application/json").json()["id"]
        # procedimento TUSS só permite a prótese padrão
        client.post("/api/hospital/opme/procedimentos/",
            data={"codigo_tuss": "30729068", "descricao": "Artroplastia de quadril",
                  "itens": [{"opme_id": permitido, "quantidade_maxima": 1, "preferencial": True}]},
            content_type="application/json")
        # solicita a prótese que NÃO está na lista, para esse TUSS
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr", "procedimento_tuss": "30729068",
                  "justificativa": "Prótese alternativa indicada por incompatibilidade anatômica com a padrão.",
                  "itens": [{"opme_id": outro, "quantidade": 1}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("padronizada", " ".join(r.json()["alertas_triagem"]).lower())

    def test_guia_oncologica_vencida_alerta(self):
        """GAP-4: ciclo vinculado a guia vencida gera alerta; KPI conta vencida."""
        empresa = _empresa("Hospital Rede", "onco-guia@example.com", "hospital_rede")
        client = _client_for(empresa)
        proto = ProtocoloOncologico.objects.create(
            empresa=empresa, codigo="P1", nome="P1", ciclos_total=6, intervalo_dias=21,
            drogas=[{"droga": "Cisplatina", "dose": 20, "unidade": "mg/m²", "dia": 1}])
        # guia já vencida
        guia_id = client.post("/api/hospital/oncologia/guias/",
            data={"numero_guia": "G-001", "paciente_nome": "Ana", "cpf_paciente": "52998224725",
                  "data_emissao": "2026-01-01", "data_validade": "2026-02-01", "ciclos_autorizados": 6},
            content_type="application/json").json()["id"]
        # cria ciclo vinculado
        r = client.post("/api/hospital/oncologia/ciclos/",
            data={"protocolo_id": proto.id, "paciente_nome": "Ana", "cpf_paciente": "52998224725",
                  "cid10_principal": "C50", "data_inicio": date.today().isoformat(),
                  "peso_kg": 60, "altura_cm": 165, "guia_id": guia_id},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertIn("VENCIDA", " ".join(r.json()["alertas"]))
        # KPI conta a guia vencida
        kpi = client.get("/api/hospital/oncologia/kpis/").json()
        self.assertGreaterEqual(kpi["guias_vencidas"], 1)
        # endpoint de alertas também
        al = client.get("/api/hospital/oncologia/guias/alertas/").json()
        self.assertGreaterEqual(al["total_vencidas"], 1)

    # ── RN 424/ANS, código de operadora, ANVISA, fraude ─────────────────────

    def test_justificativa_obrigatoria_quando_fora_padrao(self):
        """RN 424/ANS: sem justificativa, pedido com item fora do padrão é bloqueado (400)."""
        empresa = _empresa("Hospital Rede", "opme-rn424-just@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Material X", "tipo": "material", "homologado": False},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("RN 424", r.json()["erro"])
        # com justificativa, passa
        r2 = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "Sem alternativa homologada disponível.",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json")
        self.assertEqual(r2.status_code, 201)

    def test_marcas_alternativas_rn424_oferecidas_no_pedido(self):
        """RN 424/ANS: item fora do padrão retorna marcas alternativas do mesmo
        grupo de equivalência clínica (base para a Junta Médica)."""
        empresa = _empresa("Hospital Rede", "opme-rn424-marcas@example.com", "hospital_rede")
        client = _client_for(empresa)
        grupo = "PROTESE-QUADRIL-X"
        principal = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese Marca A", "tipo": "protese", "fabricante": "A",
                  "grupo_equivalencia": grupo, "homologado": False},
            content_type="application/json").json()["id"]
        for marca in ("B", "C", "D"):
            client.post("/api/hospital/opme/catalogo/",
                data={"descricao": f"Prótese Marca {marca}", "tipo": "protese",
                      "fabricante": marca, "grupo_equivalencia": grupo, "homologado": True},
                content_type="application/json")
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "Indicação técnica do cirurgião.",
                  "itens": [{"opme_id": principal, "quantidade": 1}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        alternativas = r.json()["marcas_alternativas"][str(principal)]
        self.assertEqual(len(alternativas), 3, "RN 424 pede ao menos 3 marcas, quando existirem")
        fabricantes = {a["fabricante"] for a in alternativas}
        self.assertEqual(fabricantes, {"B", "C", "D"})

    def test_abrir_e_resolver_junta_medica(self):
        """RN 424/ANS: abre Junta Médica para divergência técnica e resolve."""
        empresa = _empresa("Hospital Rede", "opme-junta@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item Y", "tipo": "material"},
            content_type="application/json").json()["id"]
        aut_id = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut_id}/juntas",
            data={"motivo_divergencia": "Operadora diverge da marca indicada pelo médico."},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        junta_id = r.json()["id"]
        self.assertEqual(r.json()["status"], "aberta")
        # sem motivo é rejeitado
        r_sem_motivo = client.post(f"/api/hospital/opme/autorizacoes/{aut_id}/juntas",
            data={"motivo_divergencia": ""}, content_type="application/json")
        self.assertEqual(r_sem_motivo.status_code, 400)
        # resolve
        r_resolve = client.put(f"/api/hospital/opme/juntas/{junta_id}",
            data={"status": "resolvida_medico", "parecer": "Mantida indicação do assistente."},
            content_type="application/json")
        self.assertEqual(r_resolve.status_code, 200)
        # transição inválida depois de resolvida
        r_invalida = client.put(f"/api/hospital/opme/juntas/{junta_id}",
            data={"status": "em_analise"}, content_type="application/json")
        self.assertEqual(r_invalida.status_code, 409)

    def test_codigo_operadora_tnu_persiste(self):
        """TNU/código próprio da operadora: campo é salvo e retornado no catálogo."""
        empresa = _empresa("Hospital Rede", "opme-tnu@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item TNU", "tipo": "material", "codigo_operadora": "TNU-00123"},
            content_type="application/json").json()["id"]
        item = client.get(f"/api/hospital/opme/catalogo/{item_id}").json()
        self.assertEqual(item["codigo_operadora"], "TNU-00123")
        listagem = client.get("/api/hospital/opme/catalogo?ativo=all").json()["itens"]
        achado = next(i for i in listagem if i["id"] == item_id)
        self.assertEqual(achado["codigo_operadora"], "TNU-00123")

    def test_anvisa_formato_invalido_rejeitado(self):
        """Checagem de formato do registro ANVISA (não é webservice ao vivo —
        validação de dígitos, mas rejeita valores claramente inválidos)."""
        empresa = _empresa("Hospital Rede", "opme-anvisa-fmt@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item Z", "tipo": "material", "codigo_anvisa": "123"},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r_ok = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item Z", "tipo": "material", "codigo_anvisa": "80146170123"},
            content_type="application/json")
        self.assertEqual(r_ok.status_code, 201)

    def test_catalogo_registro_anvisa_vencido_conta_no_kpi(self):
        """Registro ANVISA vencido aparece no KPI de monitoramento."""
        empresa = _empresa("Hospital Rede", "opme-anvisa-venc@example.com", "hospital_rede")
        client = _client_for(empresa)
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item Vencido", "tipo": "material",
                  "data_validade_registro_anvisa": "2020-01-01"},
            content_type="application/json")
        kpi = client.get("/api/hospital/opme/kpis").json()
        self.assertGreaterEqual(kpi["catalogo_registros_anvisa_vencidos"], 1)

    def test_substituicao_grava_economia_comprovada(self):
        """Trocar pelo equivalente mais barato grava economia auditável (× quantidade)."""
        empresa = _empresa("Hospital Rede", "opme-economia@example.com", "hospital_rede")
        client = _client_for(empresa)
        caro = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese Cara", "tipo": "protese", "fabricante": "A",
                  "grupo_equivalencia": "GRP-1", "preco_maximo": 20000},
            content_type="application/json").json()["id"]
        barato = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese Equivalente", "tipo": "protese", "fabricante": "B",
                  "grupo_equivalencia": "GRP-1", "preco_maximo": 12000},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": barato, "quantidade": 2, "preco_solicitado": 12000,
                             "substituido_de_id": caro, "preco_substituido": 20000}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        eco = client.get("/api/hospital/opme/economia").json()
        self.assertEqual(eco["economia_realizada"], 16000.0)  # (20000-12000) × 2
        self.assertEqual(eco["substituicoes_aceitas"], 1)

    def test_substituicao_sem_ganho_nao_infla_kpi(self):
        """Troca por item igual/mais caro não pode virar 'economia'."""
        empresa = _empresa("Hospital Rede", "opme-eco-zero@example.com", "hospital_rede")
        client = _client_for(empresa)
        a = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item A", "tipo": "protese", "grupo_equivalencia": "G",
                  "preco_maximo": 5000}, content_type="application/json").json()["id"]
        b = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item B", "tipo": "protese", "grupo_equivalencia": "G",
                  "preco_maximo": 9000}, content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": b, "quantidade": 1, "preco_solicitado": 9000,
                             "substituido_de_id": a, "preco_substituido": 5000}]},
            content_type="application/json")
        eco = client.get("/api/hospital/opme/economia").json()
        self.assertEqual(eco["economia_realizada"], 0.0)
        self.assertEqual(eco["substituicoes_aceitas"], 0)

    def test_economia_potencial_lista_itens_em_risco(self):
        """Pedido pendente fora do padrão com equivalente barato entra em 'em risco'."""
        empresa = _empresa("Hospital Rede", "opme-risco@example.com", "hospital_rede")
        client = _client_for(empresa)
        caro = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cara não homologada", "tipo": "protese", "fabricante": "X",
                  "grupo_equivalencia": "GR", "preco_maximo": 30000, "homologado": False},
            content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Equivalente barata", "tipo": "protese", "fabricante": "Y",
                  "grupo_equivalencia": "GR", "preco_maximo": 10000},
            content_type="application/json")
        client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "Paciente Risco", "medico_solicitante": "Dr",
                  "justificativa": "Indicação técnica.",
                  "itens": [{"opme_id": caro, "quantidade": 1, "preco_solicitado": 30000}]},
            content_type="application/json")
        eco = client.get("/api/hospital/opme/economia").json()
        self.assertEqual(eco["economia_potencial_aberta"], 20000.0)
        self.assertEqual(len(eco["itens_em_risco"]), 1)
        self.assertEqual(eco["itens_em_risco"][0]["economia_possivel"], 20000.0)

    def test_endpoint_alternativas_calcula_economia(self):
        """Endpoint de alternativas devolve economia de cada marca equivalente."""
        empresa = _empresa("Hospital Rede", "opme-alt@example.com", "hospital_rede")
        client = _client_for(empresa)
        base = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Base", "tipo": "protese", "grupo_equivalencia": "GG",
                  "preco_maximo": 10000}, content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Alt barata", "tipo": "protese", "grupo_equivalencia": "GG",
                  "preco_maximo": 6000}, content_type="application/json")
        r = client.get(f"/api/hospital/opme/catalogo/{base}/alternativas?preco=10000")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["item"]["preco_referencia"], 10000.0)
        self.assertEqual(d["alternativas"][0]["economia"], 4000.0)

    def test_ia_area_treina_e_status(self):
        """IA por área: treina o modelo OPME da empresa (bootstrap) e expõe status."""
        from api.models import ModeloIAArea
        empresa = _empresa("Hospital Rede", "opme-iaarea@example.com", "hospital_rede")
        client = _client_for(empresa)
        # status antes de treinar
        r0 = client.get("/api/hospital/opme/ia/modelo").json()
        self.assertFalse(r0["treinado"])
        # treina
        r1 = client.post("/api/hospital/opme/ia/modelo", data={}, content_type="application/json")
        self.assertEqual(r1.status_code, 200)
        d = r1.json()
        self.assertTrue(d["treinado"])
        self.assertIn("aprovada", d["classes"])
        self.assertIn("negada", d["classes"])
        self.assertTrue(d["dataset_sintetico"])  # sem decisões reais → bootstrap
        # registro persistido, isolado por empresa
        self.assertEqual(ModeloIAArea.objects.filter(empresa=empresa, area="opme").count(), 1)

    def test_ia_area_isolada_por_empresa(self):
        """O modelo de uma empresa não vaza para outra (LGPD)."""
        from api.services.ia_areas import treinar_area, inferir
        emp_a = _empresa("A", "iaa-a@example.com", "hospital_rede")
        emp_b = _empresa("B", "iaa-b@example.com", "hospital_rede")
        treinar_area("opme", emp_a.id)
        # inferência de B treina o próprio modelo de B (não usa o de A)
        r = inferir("opme", emp_b.id, {"tem_fora_padrao": 0, "nao_homologado": 0,
                                       "acima_teto": 0, "tem_alerta_fraude": 0,
                                       "tem_procedimento_tuss": 1, "tem_justificativa": 1,
                                       "n_itens": 1, "qtd_alertas": 0})
        self.assertIn(r["decisao"], ["aprovada", "negada", "parcial", "revisao"])
        from api.models import ModeloIAArea
        self.assertTrue(ModeloIAArea.objects.filter(empresa=emp_b, area="opme").exists())

    def test_ia_area_aprende_padrao_conforme(self):
        """Caso 100% conforme tende a 'aprovada'; caso fora do padrão + fraude tende
        a 'negada' — o modelo capta o padrão do bootstrap."""
        from api.services.ia_areas import treinar_area, inferir
        emp = _empresa("Hospital Rede", "iaa-padrao@example.com", "hospital_rede")
        treinar_area("opme", emp.id)
        conforme = inferir("opme", emp.id, {"tem_fora_padrao": 0, "nao_homologado": 0,
            "acima_teto": 0, "tem_alerta_fraude": 0, "tem_procedimento_tuss": 1,
            "tem_justificativa": 1, "n_itens": 1, "qtd_alertas": 0})
        ruim = inferir("opme", emp.id, {"tem_fora_padrao": 1, "nao_homologado": 1,
            "acima_teto": 1, "tem_alerta_fraude": 1, "tem_procedimento_tuss": 0,
            "tem_justificativa": 0, "n_itens": 2, "qtd_alertas": 3})
        self.assertEqual(conforme["decisao"], "aprovada")
        self.assertEqual(ruim["decisao"], "negada")

    def test_anvisa_busca_por_registro_e_por_nome(self):
        """Buscar na ANVISA por número de registro e por nome (base dentro do sistema)."""
        from api.models import RegistroAnvisaProdutoSaude
        empresa = _empresa("Hospital Rede", "opme-anvisabusca@example.com", "hospital_rede")
        client = _client_for(empresa)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80044680371", nome_produto="PROTESE FEMURAL DE QUADRIL",
            detentor="ZIMMER", situacao="Válido")
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="10132590627", nome_produto="KIT INSTRUMENTAL QUADRIL",
            detentor="J&J", situacao="Inválido")
        # por registro
        r1 = client.get("/api/hospital/opme/anvisa/buscar?tipo=produto&q=80044680371").json()
        self.assertEqual(len(r1["resultados"]), 1)
        self.assertTrue(r1["resultados"][0]["valido"])
        # por nome (retorna os 2, válido primeiro)
        r2 = client.get("/api/hospital/opme/anvisa/buscar?tipo=produto&q=quadril").json()
        self.assertEqual(len(r2["resultados"]), 2)
        self.assertTrue(r2["resultados"][0]["valido"])  # 'Válido' ordena antes
        # curto demais
        self.assertEqual(client.get("/api/hospital/opme/anvisa/buscar?q=ab").status_code, 400)

    def test_anvisa_busca_fornecedor_afe(self):
        """Buscar fornecedor na base de AFE da ANVISA por CNPJ e por razão social."""
        from api.models import EmpresaAfeAnvisa
        empresa = _empresa("Hospital Rede", "opme-afebusca@example.com", "hospital_rede")
        client = _client_for(empresa)
        EmpresaAfeAnvisa.objects.create(cnpj="11222333000181", razao_social="DISTRIBUIDORA ALFA",
                                        numero_afe="1.02.030-4", ativo=True, uf="MS")
        r = client.get("/api/hospital/opme/anvisa/buscar?tipo=fornecedor&q=alfa").json()
        self.assertEqual(r["tipo"], "fornecedor")
        self.assertEqual(r["resultados"][0]["razao_social"], "DISTRIBUIDORA ALFA")
        self.assertTrue(r["resultados"][0]["ativo"])

    def test_ans_busca_no_espelho_cruza_anvisa(self):
        """Buscar na ANS (TUSS-19) no espelho local já devolve o cruzamento com a
        situação do registro na ANVISA — o diferencial de 'tudo numa tela só'."""
        from api.models import TerminologiaTuss, RegistroAnvisaProdutoSaude
        empresa = _empresa("Hospital Rede", "opme-ansbusca@example.com", "hospital_rede")
        client = _client_for(empresa)
        TerminologiaTuss.objects.create(
            tabela="tuss-19", tabela_nome="OPME", codigo="74317270",
            descricao="STENT CORONARIO H-STENT", fabricante="SCITECH",
            classe_risco="III", registro_anvisa="80174300001", vigente=True)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80174300001", nome_produto="STENT CORONARIO",
            detentor="SCITECH", situacao="Válido", classe_risco="III")
        r = client.get("/api/hospital/opme/ans/buscar?tabela=tuss-19&q=stent").json()
        self.assertEqual(r["fonte"], "espelho")
        self.assertEqual(len(r["resultados"]), 1)
        res = r["resultados"][0]
        self.assertEqual(res["codigo"], "74317270")
        # o cruzamento ANVISA veio junto e diz que o registro é válido
        self.assertIsNotNone(res["anvisa"])
        self.assertTrue(res["anvisa"]["encontrado"])
        self.assertTrue(res["anvisa"]["valido"])
        # curto demais → 400
        self.assertEqual(client.get("/api/hospital/opme/ans/buscar?q=ab").status_code, 400)

    def test_ans_consulta_por_codigo(self):
        """Consulta de um código TUSS específico no espelho + estado da base."""
        from api.models import TerminologiaTuss
        empresa = _empresa("Hospital Rede", "opme-ansconsulta@example.com", "hospital_rede")
        client = _client_for(empresa)
        # base ainda vazia p/ tuss-22 → responde base_indisponivel (sem fingir 404)
        vazio = client.get("/api/hospital/opme/ans/consulta?tabela=tuss-22&codigo=30914175").json()
        self.assertFalse(vazio["encontrado"])
        self.assertTrue(vazio.get("base_indisponivel"))
        TerminologiaTuss.objects.create(
            tabela="tuss-22", tabela_nome="Procedimentos", codigo="30914175",
            descricao="Linfadenectomia pélvica robótica", vigente=True)
        ok = client.get("/api/hospital/opme/ans/consulta?tabela=tuss-22&codigo=30914175").json()
        self.assertTrue(ok["encontrado"])
        self.assertEqual(ok["descricao"], "Linfadenectomia pélvica robótica")
        nao = client.get("/api/hospital/opme/ans/consulta?tabela=tuss-22&codigo=999").json()
        self.assertFalse(nao["encontrado"])

    def test_ans_busca_ao_vivo_grava_no_espelho(self):
        """Quando não há no espelho, cai para a API da ANS ao vivo e GRAVA o que
        achar (o sistema aprende os itens usados). API mockada — sem rede no teste."""
        from unittest.mock import patch
        from api.models import TerminologiaTuss
        empresa = _empresa("Hospital Rede", "opme-ansaovivo@example.com", "hospital_rede")
        client = _client_for(empresa)
        fake = [{
            "tabela": "tuss-19", "codigo": "76611701",
            "descricao": "STENT CASPER - ARTERIA CAROTIDA", "registro_anvisa": "80583400005",
            "fabricante": "MICROVENTION", "classe_risco": "III", "apresentacao": "",
            "modelo": "", "inicio_vigencia": None, "fim_vigencia": None, "vigente": True,
        }]
        with patch("api.services.ans_tuss.buscar_ao_vivo", return_value=fake):
            r = client.get("/api/hospital/opme/ans/buscar?tabela=tuss-19&q=casper").json()
        self.assertEqual(r["fonte"], "ans_ao_vivo")
        self.assertEqual(len(r["resultados"]), 1)
        # persistiu no espelho para a próxima busca ser instantânea
        self.assertTrue(TerminologiaTuss.objects.filter(tabela="tuss-19", codigo="76611701").exists())

    def test_ans_busca_exige_login(self):
        """LGPD/RBAC: sem sessão de hospital não responde."""
        from django.test import Client
        r = Client().get("/api/hospital/opme/ans/buscar?tabela=tuss-19&q=stent")
        self.assertIn(r.status_code, (401, 403))

    def test_esteira_registra_solicitacao_e_avanca(self):
        """Esteira: pedido nasce em 'auditoria', a trilha tem a solicitação, e
        avançar move para a próxima etapa registrando quem/quando."""
        from api.models import AutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-esteira@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item Esteira", "tipo": "material"},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr. Fulano",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        e = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(e["etapa_atual"], "auditoria")
        etapas_hist = [h["etapa"] for h in e["historico"]]
        self.assertIn("solicitacao", etapas_hist)
        # avança a auditoria → autorização
        e2 = client.post(f"/api/hospital/opme/autorizacoes/{aut}/esteira",
            data={"acao": "avancar", "observacao": "Auditoria aprovada."},
            content_type="application/json").json()
        self.assertEqual(e2["etapa_atual"], "autorizacao")

    def test_esteira_via_rapida_dispensa_auditoria(self):
        """Via Rápida marca análise/auditoria como 'dispensada' na esteira e já
        posiciona o pedido em cotação (pós-autorização)."""
        from api.models import RegistroAnvisaProdutoSaude
        empresa = _empresa("Hospital Rede", "opme-esteira-vr@example.com", "hospital_rede")
        client = _client_for(empresa)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80044680371", situacao="Válido",
            data_vencimento=date.today() + timedelta(days=400))
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Homologada", "tipo": "protese", "homologado": True,
                  "preco_maximo": 9000, "codigo_anvisa": "80044680371"},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": item_id, "quantidade": 1, "preco_solicitado": 8000}]},
            content_type="application/json").json()["id"]
        e = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(e["etapa_atual"], "cotacao")
        sit = {h["etapa"]: h["situacao"] for h in e["historico"]}
        self.assertEqual(sit.get("auditoria"), "dispensada")
        self.assertEqual(sit.get("autorizacao"), "concluida")

    def test_esteira_pendencia_exige_observacao(self):
        """Pôr em pendência sem observação é bloqueado."""
        empresa = _empresa("Hospital Rede", "opme-esteira-pend@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "X", "tipo": "material"},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/esteira",
            data={"acao": "pendenciar", "observacao": ""},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_via_rapida_pre_aprova_pedido_100_conforme(self):
        """Via Rápida: pedido homologado + ANVISA válido + sem alertas é
        pré-aprovado na hora (status aprovada, via_rapida=True), sem fila."""
        from api.models import RegistroAnvisaProdutoSaude, AutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-viarapida@example.com", "hospital_rede")
        client = _client_for(empresa)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80044680371", situacao="Válido",
            data_vencimento=date.today() + timedelta(days=400))
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese Homologada", "tipo": "protese",
                  "homologado": True, "preferencial": True, "preco_maximo": 9000,
                  "codigo_anvisa": "80044680371"},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr. Correto",
                  "itens": [{"opme_id": item_id, "quantidade": 1, "preco_solicitado": 8000}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertTrue(d["via_rapida"], "pedido 100% conforme deveria ir pela Via Rápida")
        self.assertEqual(d["status"], "aprovada")
        aut = AutorizacaoOPME.objects.get(id=d["id"])
        self.assertTrue(aut.via_rapida)
        self.assertEqual(aut.status, "aprovada")
        self.assertTrue(aut.itens.filter(status="aprovado").exists())

    def test_via_rapida_NAO_dispara_com_alerta(self):
        """Pedido fora do padrão (não homologado) NÃO pode ser auto-aprovado —
        vai para auditoria humana."""
        from api.models import AutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-vr-bloq@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Não homologada", "tipo": "protese", "homologado": False},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "necessário",
                  "itens": [{"opme_id": item_id, "quantidade": 1}]},
            content_type="application/json")
        d = r.json()
        self.assertFalse(d["via_rapida"])
        self.assertEqual(d["status"], "solicitada")

    def test_via_rapida_NAO_dispara_sem_base_anvisa(self):
        """Sem base ANVISA sincronizada, não há como confirmar o registro —
        a Via Rápida é conservadora e NÃO auto-aprova."""
        empresa = _empresa("Hospital Rede", "opme-vr-semanvisa@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Homologada s/ base ANVISA", "tipo": "protese",
                  "homologado": True, "preco_maximo": 9000, "codigo_anvisa": "80044680371"},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": item_id, "quantidade": 1, "preco_solicitado": 8000}]},
            content_type="application/json")
        self.assertFalse(r.json()["via_rapida"])

    def test_ia_recomenda_custo_beneficio_mesma_qualidade(self):
        """A IA recomenda o equivalente mais barato de MESMA qualidade (homologado
        + ANVISA válido), não simplesmente o mais barato."""
        from api.models import RegistroAnvisaProdutoSaude, AutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-mcb@example.com", "hospital_rede")
        client = _client_for(empresa)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80044680371", situacao="Válido",
            data_vencimento=date.today() + timedelta(days=400))
        # caro, fora do padrão (não homologado)
        caro = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Premium", "tipo": "protese", "homologado": False,
                  "grupo_equivalencia": "GEQ", "preco_maximo": 20000},
            content_type="application/json").json()["id"]
        # barato mas SEM registro ANVISA válido (não deve ser recomendado)
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Barata sem ANVISA", "tipo": "protese", "homologado": True,
                  "grupo_equivalencia": "GEQ", "preco_maximo": 7000, "codigo_anvisa": "80000000000"},
            content_type="application/json")
        # equivalente de mesma qualidade (homologado + ANVISA válido)
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Equivalente válida", "tipo": "protese", "homologado": True,
                  "grupo_equivalencia": "GEQ", "preco_maximo": 12000, "codigo_anvisa": "80044680371"},
            content_type="application/json")
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "indicação",
                  "itens": [{"opme_id": caro, "quantidade": 1, "preco_solicitado": 20000}]},
            content_type="application/json")
        rec = r.json()["recomendacao"]
        self.assertEqual(rec["para_descricao"], "Equivalente válida")  # não a "barata sem ANVISA"
        self.assertEqual(rec["economia"], 8000.0)

    def test_alternativas_trazem_atributos_clinicos_e_anvisa(self):
        """Comparação clínica: a alternativa vem com material, especificação e a
        situação REAL do registro na ANVISA — não só preço."""
        from api.models import RegistroAnvisaProdutoSaude
        empresa = _empresa("Hospital Rede", "opme-clinico@example.com", "hospital_rede")
        client = _client_for(empresa)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80111222333", situacao="Válido", classe_risco="III",
            data_vencimento=date.today() + timedelta(days=365))
        base = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese Premium", "tipo": "protese", "fabricante": "A",
                  "grupo_equivalencia": "GRPX", "preco_maximo": 20000},
            content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese Equivalente", "tipo": "protese", "fabricante": "B",
                  "grupo_equivalencia": "GRPX", "preco_maximo": 12000,
                  "material": "Titânio revestido", "especificacoes": "Não cimentada, haste reta",
                  "codigo_anvisa": "80111222333"},
            content_type="application/json")
        r = client.get(f"/api/hospital/opme/catalogo/{base}/alternativas?preco=20000")
        alt = r.json()["alternativas"][0]
        self.assertEqual(alt["material"], "Titânio revestido")
        self.assertEqual(alt["especificacoes"], "Não cimentada, haste reta")
        self.assertEqual(alt["economia"], 8000.0)
        self.assertTrue(alt["anvisa"]["encontrado"])
        self.assertTrue(alt["anvisa"]["valido"])
        self.assertEqual(alt["anvisa"]["classe_risco"], "III")

    def test_alternativa_com_anvisa_vencida_e_sinalizada(self):
        """Alternativa mais barata mas com registro ANVISA vencido é sinalizada."""
        from api.models import RegistroAnvisaProdutoSaude
        empresa = _empresa("Hospital Rede", "opme-alt-venc@example.com", "hospital_rede")
        client = _client_for(empresa)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80999888777", situacao="Válido", data_vencimento=date(2020, 1, 1))
        base = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Base", "tipo": "protese", "grupo_equivalencia": "GV",
                  "preco_maximo": 15000}, content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Alt vencida", "tipo": "protese", "grupo_equivalencia": "GV",
                  "preco_maximo": 8000, "codigo_anvisa": "80999888777"},
            content_type="application/json")
        r = client.get(f"/api/hospital/opme/catalogo/{base}/alternativas?preco=15000")
        alt = r.json()["alternativas"][0]
        self.assertTrue(alt["anvisa"]["vencido"])

    def test_listagem_juntas_da_empresa(self):
        """Endpoint de listagem de Juntas Médicas devolve as da empresa, com filtro."""
        empresa = _empresa("Hospital Rede", "opme-lista-junta@example.com", "hospital_rede")
        client = _client_for(empresa)
        item = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item J", "tipo": "material"},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "Pac J", "medico_solicitante": "Dr J",
                  "itens": [{"opme_id": item, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/autorizacoes/{aut}/juntas",
            data={"motivo_divergencia": "Divergência de marca."},
            content_type="application/json")
        d = client.get("/api/hospital/opme/juntas").json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["juntas"][0]["paciente_nome"], "Pac J")
        self.assertEqual(client.get("/api/hospital/opme/juntas?status=aberta").json()["total"], 1)
        self.assertEqual(client.get("/api/hospital/opme/juntas?status=cancelada").json()["total"], 0)

    def test_deteccao_fraude_repeticao_mesmo_item(self):
        """Padrão atípico: mesmo médico pede o mesmo material repetidamente em 30 dias."""
        empresa = _empresa("Hospital Rede", "opme-fraude@example.com", "hospital_rede")
        client = _client_for(empresa)
        item_id = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item Repetido", "tipo": "material"},
            content_type="application/json").json()["id"]
        payload = {"paciente_nome": "Paciente", "medico_solicitante": "Dr. Repetitivo",
                   "itens": [{"opme_id": item_id, "quantidade": 1}]}
        for _ in range(3):
            r = client.post("/api/hospital/opme/autorizacoes/", data=payload,
                             content_type="application/json")
            self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["alertas_fraude"], "3ª solicitação repetida deveria alertar")
        kpi = client.get("/api/hospital/opme/kpis").json()
        self.assertGreaterEqual(kpi["medicos_padrao_atipico_30d"], 1)

    # ── Cotação competitiva (leilão reverso) ─────────────────────────────────
    def _forn(self, client, razao, cnpj=""):
        return client.post("/api/hospital/opme/fornecedores/",
            data={"razao_social": razao, "cnpj": cnpj},
            content_type="application/json").json()["id"]

    def test_lance_registra_autoria_e_prazo_vencido(self):
        """Auditoria da cotação: o lance grava QUEM registrou; cotação aberta com
        prazo passado é sinalizada como vencida."""
        empresa = _empresa("Hospital Rede", "opme-cot-aud@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Placa aud", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        f1 = self._forn(client, "Forn Aud")
        # cotação com prazo no passado
        cot = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "prazo_ate": "2020-01-01"},
            content_type="application/json").json()
        self.assertTrue(cot["prazo_vencido"])   # aberta + prazo passado
        cid = cot["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 4000},
            content_type="application/json")
        det = client.get(f"/api/hospital/opme/cotacoes/{cid}").json()
        self.assertTrue(det["lances"][0]["registrado_por"])   # autoria gravada

    def test_cotacao_menor_lance_valido_vence_e_grava_economia(self):
        """Leilão reverso: menor lance vence e a economia comprovada = teto − vencedor."""
        empresa = _empresa("Hospital Rede", "opme-cot@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Placa de titânio", "tipo": "material", "preco_maximo": 10000},
            content_type="application/json").json()["id"]
        f1 = self._forn(client, "Fornecedor A")
        f2 = self._forn(client, "Fornecedor B")
        # abre cotação (referência = teto do catálogo = 10000)
        cot = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 2},
            content_type="application/json").json()
        self.assertEqual(cot["preco_referencia"], 10000.0)
        cid = cot["id"]
        # dois lances (sem base AFE sincronizada → ambos válidos)
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 9000},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f2, "preco_unitario": 8000},
            content_type="application/json")
        # encerra → menor válido (8000) vence; economia = (10000-8000)*2 = 4000
        r = client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["status"], "encerrada")
        self.assertEqual(d["economia_obtida"], 4000.0)
        vencedor = [l for l in d["lances"] if l["vencedor"]][0]
        self.assertEqual(vencedor["preco_unitario"], 8000.0)

    def test_cotacao_entra_na_torre_de_economia(self):
        """A economia da cotação encerrada soma na Torre de Economia (alavanca)."""
        empresa = _empresa("Hospital Rede", "opme-torre@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Parafuso", "tipo": "material", "preco_maximo": 2000},
            content_type="application/json").json()["id"]
        f1 = self._forn(client, "Distribuidora X")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 1500},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        eco = client.get("/api/hospital/opme/economia").json()
        self.assertEqual(eco["economia_cotacoes"], 500.0)
        self.assertEqual(eco["cotacoes_vencidas"], 1)
        # a Torre lista a alavanca de cotação com o fato correto
        cot_lever = [a for a in eco["torre_economia"] if a["alavanca"] == "Cotação competitiva"][0]
        self.assertEqual(cot_lever["fato"], 500.0)
        self.assertEqual(eco["torre_fato_total"], 500.0)

    def test_cotacao_lance_de_fornecedor_sem_afe_ativa_nao_vence(self):
        """Com base AFE sincronizada, lance de fornecedor sem AFE ativa não disputa."""
        from api.models import EmpresaAfeAnvisa, FornecedorHospital
        empresa = _empresa("Hospital Rede", "opme-afe@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Haste femoral", "tipo": "protese", "preco_maximo": 20000},
            content_type="application/json").json()["id"]
        # dois fornecedores: um com AFE ativa (mais caro), um sem AFE (mais barato)
        f_ativo = self._forn(client, "Forn Regular", cnpj="11222333000181")
        f_irregular = self._forn(client, "Forn Sem AFE", cnpj="99888777000166")
        # base AFE: só o primeiro tem AFE ativa
        EmpresaAfeAnvisa.objects.create(cnpj="11222333000181", razao_social="Forn Regular",
                                        numero_afe="1234", ativo=True)
        EmpresaAfeAnvisa.objects.create(cnpj="99888777000166", razao_social="Forn Sem AFE",
                                        numero_afe="", ativo=False)
        # reverifica AFE dos fornecedores agora que a base existe
        client.post("/api/hospital/opme/fornecedores/verificar-afe",
                    data={}, content_type="application/json")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1},
            content_type="application/json").json()["id"]
        # lance barato do irregular (NÃO deve vencer) e caro do regular
        r_irr = client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f_irregular, "preco_unitario": 12000},
            content_type="application/json").json()
        self.assertFalse(r_irr["valida"])
        self.assertIsNotNone(r_irr["aviso"])
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f_ativo, "preco_unitario": 18000},
            content_type="application/json")
        d = client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json").json()
        vencedor = [l for l in d["lances"] if l["vencedor"]][0]
        # vence o regular (18000), não o irregular mais barato (12000)
        self.assertEqual(vencedor["preco_unitario"], 18000.0)
        self.assertEqual(d["economia_obtida"], 2000.0)

    def test_cotacao_sem_lance_valido_nao_encerra(self):
        """Sem nenhum lance válido, não dá pra cravar vencedor (evita economia falsa)."""
        from api.models import EmpresaAfeAnvisa
        empresa = _empresa("Hospital Rede", "opme-cot-vazia@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cage", "tipo": "protese", "preco_maximo": 15000},
            content_type="application/json").json()["id"]
        f = self._forn(client, "Forn Irregular", cnpj="55444333000122")
        EmpresaAfeAnvisa.objects.create(cnpj="00000000000000", razao_social="Outro",
                                        numero_afe="1", ativo=True)  # base existe, mas sem este CNPJ
        client.post("/api/hospital/opme/fornecedores/verificar-afe",
                    data={}, content_type="application/json")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f, "preco_unitario": 9000},
            content_type="application/json")
        r = client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_cotacao_encerrada_nao_aceita_novo_lance(self):
        """Cotação encerrada é imutável para lances."""
        empresa = _empresa("Hospital Rede", "opme-cot-fecha@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Tela", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        f = self._forn(client, "Forn Z")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f, "preco_unitario": 2500},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        r = client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f, "preco_unitario": 2000},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_cotacao_isolada_por_empresa(self):
        """Cotação de uma empresa não é acessível por outra (LGPD/multi-tenant)."""
        emp_a = _empresa("Hospital A", "opme-cot-a@example.com", "hospital_rede")
        emp_b = _empresa("Hospital B", "opme-cot-b@example.com", "hospital_rede")
        ca, cb = _client_for(emp_a), _client_for(emp_b)
        opme = ca.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item A", "tipo": "material", "preco_maximo": 1000},
            content_type="application/json").json()["id"]
        cid = ca.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1},
            content_type="application/json").json()["id"]
        # empresa B não enxerga a cotação de A
        r = cb.get(f"/api/hospital/opme/cotacoes/{cid}")
        self.assertEqual(r.status_code, 404)

    def test_cotacao_encerrada_grava_preco_negociado_no_item(self):
        """Fecha o ciclo: o preço vencedor da cotação volta para o item do pedido
        vinculado (preco_negociado), sem sobrescrever o preco_solicitado."""
        from api.models import ItemAutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-writeback@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Haste femoral", "tipo": "material", "preco_maximo": 12000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1, "preco_solicitado": 12000}]},
            content_type="application/json").json()
        aut_id = aut["id"]
        f1 = self._forn(client, "Distribuidora Z")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "autorizacao_id": aut_id},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 9500},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        item = ItemAutorizacaoOPME.objects.get(autorizacao_id=aut_id, opme_id=opme)
        # preço negociado gravado; preço solicitado intacto (trilha de auditoria)
        self.assertEqual(float(item.preco_negociado), 9500.0)
        self.assertEqual(float(item.preco_solicitado), 12000.0)

    def test_junta_acatar_alternativa_troca_material_e_gera_economia(self):
        """A junta precisa FECHAR O LAÇO: acatar a alternativa troca o material no
        pedido, grava a economia e libera a autorização."""
        from api.models import ItemAutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-junta-loop@example.com", "hospital_rede")
        client = _client_for(empresa)
        caro = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cara não homologada", "tipo": "protese", "fabricante": "X",
                  "grupo_equivalencia": "GJ", "preco_maximo": 30000, "homologado": False},
            content_type="application/json").json()["id"]
        barata = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Equivalente homologada", "tipo": "protese", "fabricante": "Y",
                  "grupo_equivalencia": "GJ", "preco_maximo": 20000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "justificativa": "Indicação técnica.",
                  "itens": [{"opme_id": caro, "quantidade": 1, "preco_solicitado": 30000}]},
            content_type="application/json").json()["id"]
        item_id = ItemAutorizacaoOPME.objects.get(autorizacao_id=aut).id
        junta = client.post(f"/api/hospital/opme/autorizacoes/{aut}/juntas",
            data={"motivo_divergencia": "Existe equivalente homologada mais barata.",
                  "item_id": item_id},
            content_type="application/json").json()["id"]
        r = client.put(f"/api/hospital/opme/juntas/{junta}",
            data={"status": "resolvida_operadora", "parecer": "Equivalência clínica confirmada.",
                  "opme_escolhido_id": barata},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        # material trocado e economia medida
        self.assertIn("material_trocado", d)
        self.assertEqual(d["material_trocado"]["economia"], 10000.0)
        it = ItemAutorizacaoOPME.objects.get(id=item_id)
        self.assertEqual(it.opme_id, barata)
        self.assertEqual(it.substituido_de_id, caro)
        self.assertEqual(float(it.economia_aplicada), 10000.0)
        # o pedido foi liberado — não ficou esperando cliques
        self.assertEqual(d["autorizacao_status"], "aprovada")
        self.assertEqual(d["autorizacao_etapa"], "cotacao")
        # a etapa 'junta' saiu de "em andamento"
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        concl = [h for h in est["historico"]
                 if h["etapa"] == "junta" and h["situacao"] == "concluida"]
        self.assertTrue(concl, "a etapa junta deve ficar concluída")

    def test_junta_a_favor_do_medico_mantem_material_e_libera(self):
        """Decidiu a favor do médico: material é MANTIDO e o pedido segue."""
        from api.models import ItemAutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-junta-med@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Escolha do médico", "tipo": "protese", "preco_maximo": 15000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        junta = client.post(f"/api/hospital/opme/autorizacoes/{aut}/juntas",
            data={"motivo_divergencia": "Operadora sugere outra marca."},
            content_type="application/json").json()["id"]
        r = client.put(f"/api/hospital/opme/juntas/{junta}",
            data={"status": "resolvida_medico", "parecer": "Mantida a indicação do assistente."},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertNotIn("material_trocado", d)
        self.assertEqual(d["autorizacao_status"], "aprovada")
        it = ItemAutorizacaoOPME.objects.get(autorizacao_id=aut)
        self.assertEqual(it.opme_id, opme)          # material do médico preservado
        self.assertIsNone(it.substituido_de_id)

    def test_junta_troca_sem_ganho_nao_infla_economia(self):
        """Se a alternativa acatada não é mais barata, não inventa economia."""
        from api.models import ItemAutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-junta-zero@example.com", "hospital_rede")
        client = _client_for(empresa)
        a1 = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item A", "tipo": "protese", "grupo_equivalencia": "GZ",
                  "preco_maximo": 10000}, content_type="application/json").json()["id"]
        a2 = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item B", "tipo": "protese", "grupo_equivalencia": "GZ",
                  "preco_maximo": 12000}, content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": a1, "quantidade": 1, "preco_solicitado": 10000}]},
            content_type="application/json").json()["id"]
        item_id = ItemAutorizacaoOPME.objects.get(autorizacao_id=aut).id
        junta = client.post(f"/api/hospital/opme/autorizacoes/{aut}/juntas",
            data={"motivo_divergencia": "Divergência de marca.", "item_id": item_id},
            content_type="application/json").json()["id"]
        client.put(f"/api/hospital/opme/juntas/{junta}",
            data={"status": "resolvida_operadora", "opme_escolhido_id": a2},
            content_type="application/json")
        it = ItemAutorizacaoOPME.objects.get(id=item_id)
        self.assertEqual(it.opme_id, a2)
        self.assertIsNone(it.economia_aplicada)   # troca mais cara não vira "economia"

    def test_parecer_ia_explica_o_rebaixamento(self):
        """A IA não pode parecer contraditória: quando o modelo tendia a aprovar e a
        governança rebaixou, o parecer precisa dizer isso em palavras."""
        from api.views_hospital_opme import _auditoria_ia_completa
        empresa = _empresa("Hospital Rede", "opme-ia-ovr@example.com", "hospital_rede")
        # com ressalva de triagem, a decisão cai para revisão
        dec, score, _just, parecer = _auditoria_ia_completa(
            empresa, "30715016", ["Placa X"], "M43.16", False,
            alertas_triagem=["'Placa X' NÃO consta na lista padronizada."],
            alertas_fraude=[], anvisa_ok=True)
        self.assertEqual(dec, "revisao")
        self.assertLessEqual(score, 0.5)
        self.assertIn("REVISAR", parecer)
        self.assertIn("Ressalvas", parecer)
        # sem ressalva nenhuma o parecer não fala em rebaixamento
        dec2, _s2, _j2, parecer2 = _auditoria_ia_completa(
            empresa, "30715016", ["Placa X"], "M43.16", False,
            alertas_triagem=[], alertas_fraude=[], anvisa_ok=True)
        self.assertNotIn("rebaixada", parecer2)

    def test_seed_previsibilidade_demo_eleva_o_score(self):
        """O seed de demonstração deve popular histórico suficiente para a
        previsibilidade sair de 'dados insuficientes' para um score alto — e ser
        idempotente e reversível."""
        from django.core.management import call_command
        from api.models import (Empresa, CatalogoOPME, OPMEProcedimento,
                                AutorizacaoOPME)
        from django.contrib.auth.hashers import make_password
        # tenant de demonstração com o catálogo/procedimentos que o seed espera
        empresa = Empresa.objects.create(
            nome="Hospital Demo Prev", email="demo.hospital-prev@soluscrt.com",
            senha=make_password("x"), ativo=True, pacote_codigo="hospital_rede")
        for desc, preco in [("Prótese Total de Quadril Não Cimentada — Linha Standard", 8900),
                            ("Sistema de Fixação Pedicular Titânio — 4 parafusos", 15400)]:
            CatalogoOPME.objects.create(empresa=empresa, descricao=desc, tipo="material",
                                        preco_maximo=preco, homologado=True, ativo=True)
        OPMEProcedimento.objects.create(empresa=empresa, codigo_tuss="30729068",
                                        descricao="Artroplastia de Quadril")
        OPMEProcedimento.objects.create(empresa=empresa, codigo_tuss="30715016",
                                        descricao="Artrodese Toracolombar")

        call_command("seed_opme_previsibilidade_demo", "--apply",
                     "--empresa-id", str(empresa.id))
        n1 = AutorizacaoOPME.objects.filter(
            empresa=empresa, paciente_nome__startswith="[DEMO-PREV]").count()
        self.assertEqual(n1, sum([3,3,3,4,4,5,6,7,9,11,13,16]) + sum([4,5,4,5,5,4,5,5,4,5,5,5]))

        # fração via rápida realista (nem 0% nem 100%) — preserva a métrica do painel
        vr = AutorizacaoOPME.objects.filter(
            empresa=empresa, paciente_nome__startswith="[DEMO-PREV]", via_rapida=True).count()
        self.assertTrue(0 < vr < n1, "seed deve ter mistura de via rápida e fila")

        # especialidade foi setada nos procedimentos (dimensão da métrica Unimed)
        self.assertEqual(
            OPMEProcedimento.objects.get(empresa=empresa, codigo_tuss="30729068").especialidade,
            "Ortopedia — Quadril")

        # a previsibilidade agora tem base real (score > 0, meses de histórico ≥ 6)
        client = _client_for(empresa)
        prev = client.get("/api/hospital/opme/previsibilidade/?dim=procedimento&historico=12").json()
        self.assertGreaterEqual(prev["previsibilidade_media"], 40)
        grupo_quadril = [g for g in prev["grupos"] if g["label"] == "30729068"][0]
        self.assertGreaterEqual(grupo_quadril["meses_historico"], 6)
        self.assertEqual(grupo_quadril["tendencia"], "alta")   # série crescente
        # gera alerta de compra antecipada
        self.assertTrue(prev["alertas_compra_antecipada"])

        # idempotência: rodar de novo não duplica
        call_command("seed_opme_previsibilidade_demo", "--apply",
                     "--empresa-id", str(empresa.id))
        n2 = AutorizacaoOPME.objects.filter(
            empresa=empresa, paciente_nome__startswith="[DEMO-PREV]").count()
        self.assertEqual(n1, n2)

        # reversível
        call_command("seed_opme_previsibilidade_demo", "--apply", "--clear",
                     "--empresa-id", str(empresa.id))
        self.assertEqual(0, AutorizacaoOPME.objects.filter(
            empresa=empresa, paciente_nome__startswith="[DEMO-PREV]").count())

    def test_seed_previsibilidade_recusa_tenant_nao_demo(self):
        """Trava de segurança: o seed recusa escrever em conta que não é demo."""
        from django.core.management import call_command, CommandError
        from api.models import Empresa
        from django.contrib.auth.hashers import make_password
        real = Empresa.objects.create(
            nome="Hospital Real", email="contato@hospitalreal.com.br",
            senha=make_password("x"), ativo=True, pacote_codigo="hospital_rede")
        with self.assertRaises(CommandError):
            call_command("seed_opme_previsibilidade_demo", "--apply",
                         "--empresa-id", str(real.id))

    def test_ia_nao_treina_nas_proprias_aprovacoes_via_rapida(self):
        """A IA não pode aprender com as próprias auto-aprovações (retroalimentação):
        o dataset de treino exclui as autorizações via_rapida=True."""
        from api.models import AutorizacaoOPME
        from api.services.ia_areas import _opme_dataset_real
        empresa = _empresa("Hospital Rede", "opme-ia-loop@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ia", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        # decisão HUMANA (aprovada por auditor) — deve entrar no dataset
        aut_h = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/autorizacoes/{aut_h}/acao",
            data={"acao": "aprovar"}, content_type="application/json")
        # simula uma aprovação da Via Rápida (feita pela IA)
        aut_vr = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P2", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        AutorizacaoOPME.objects.filter(id=aut_vr).update(
            status="aprovada", via_rapida=True)

        n = len(_opme_dataset_real(empresa.id))
        # apenas a decisão humana entra; a via_rapida fica de fora
        self.assertEqual(n, 1)

    def test_ranking_nominal_de_medicos_so_para_gerencia(self):
        """LGPD/ética: o ranking nominal de solicitantes fora do padrão não pode
        vazar para um usuário clínico comum. Conta corporativa (gerência) vê."""
        empresa = _empresa("Hospital Rede", "opme-rank-ger@example.com", "hospital_rede")
        client = _client_for(empresa)   # conta corporativa = gerência
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cara", "tipo": "protese", "homologado": False,
                  "preco_maximo": 9000}, content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr. Fulano",
                  "justificativa": "indicado", "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json")
        eco = client.get("/api/hospital/opme/economia").json()
        # gerência (conta corporativa) vê o ranking nominal
        self.assertTrue(any(r.get("medico_solicitante") for r in eco["ranking_fora_padrao"]))

        # usuário clínico comum (não gerência) → ranking vem VAZIO
        from api.models import EmpresaUsuario
        usr = EmpresaUsuario.objects.create(
            empresa=empresa, nome="Enf. Clínico", email="enf-seg@ex.com",
            senha="x", perfil="tecnico_sesmt", ativo=True, is_admin=False)
        c2 = _client_usuario(empresa, usr)
        eco2 = c2.get("/api/hospital/opme/economia")
        # se o usuário nominal conseguir abrir o módulo, o ranking tem que vir vazio;
        # se o RBAC barrar (403), a exposição também não ocorre — ambos são OK.
        if eco2.status_code == 200:
            self.assertEqual(eco2.json()["ranking_fora_padrao"], [])

    def test_medico_ve_apenas_os_proprios_pedidos(self):
        """LGPD: o médico solicitante (perfil 'medico') enxerga apenas os pedidos
        que ele mesmo criou — não a fila dos colegas. Gestão vê tudo."""
        from api.models import EmpresaUsuario
        empresa = _empresa("Hospital Rede", "opme-med-scope@example.com", "hospital_rede")
        ger = _client_for(empresa)  # conta corporativa = gerência
        opme = ger.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        # pedido criado pela conta corporativa (sem médico nominal dono)
        ger.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P Corp", "medico_solicitante": "Dr Corp",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json")

        medA = EmpresaUsuario.objects.create(empresa=empresa, nome="Dr A",
            email="dra@ex.com", senha="x", perfil="medico", ativo=True,
            sessao_ativa_chave=empresa.sessao_ativa_chave)
        medB = EmpresaUsuario.objects.create(empresa=empresa, nome="Dr B",
            email="drb@ex.com", senha="x", perfil="medico", ativo=True,
            sessao_ativa_chave=empresa.sessao_ativa_chave)
        cA = _client_usuario(empresa, medA)
        cB = _client_usuario(empresa, medB)

        # médico A cria o próprio pedido
        rA = cA.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P de A", "medico_solicitante": "Dr A",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json")
        self.assertEqual(rA.status_code, 201)
        aut_a = rA.json()["id"]

        # A vê só o próprio (1), não o da conta corporativa
        lst_a = cA.get("/api/hospital/opme/autorizacoes/").json()
        self.assertEqual(lst_a["total"], 1)
        self.assertEqual(lst_a["autorizacoes"][0]["id"], aut_a)

        # B (médico) não criou nada → vê 0, mesmo existindo 2 pedidos no hospital
        lst_b = cB.get("/api/hospital/opme/autorizacoes/").json()
        self.assertEqual(lst_b["total"], 0)

        # gerência vê todos (2)
        lst_g = ger.get("/api/hospital/opme/autorizacoes/").json()
        self.assertEqual(lst_g["total"], 2)

    def test_medico_nao_acessa_pedido_de_colega(self):
        """LGPD: médico recebe 404 (não 403 — não revela a existência) ao tentar
        alcançar o pedido de um colega pela ação ou pela junta; o dono acessa."""
        from api.models import EmpresaUsuario
        empresa = _empresa("Hospital Rede", "opme-med-cross@example.com", "hospital_rede")
        ger = _client_for(empresa)
        opme = ger.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        medA = EmpresaUsuario.objects.create(empresa=empresa, nome="Dr A",
            email="dra2@ex.com", senha="x", perfil="medico", ativo=True,
            sessao_ativa_chave=empresa.sessao_ativa_chave)
        medB = EmpresaUsuario.objects.create(empresa=empresa, nome="Dr B",
            email="drb2@ex.com", senha="x", perfil="medico", ativo=True,
            sessao_ativa_chave=empresa.sessao_ativa_chave)
        cA = _client_usuario(empresa, medA)
        cB = _client_usuario(empresa, medB)
        aut_a = cA.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P de A", "medico_solicitante": "Dr A",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        # B tenta ver a ação do pedido de A → 404
        self.assertEqual(cB.get(f"/api/hospital/opme/autorizacoes/{aut_a}/acao").status_code, 404)
        # B tenta ver as juntas do pedido de A → 404
        self.assertEqual(cB.get(f"/api/hospital/opme/autorizacoes/{aut_a}/juntas").status_code, 404)
        # o próprio dono (A) acessa normalmente
        self.assertEqual(cA.get(f"/api/hospital/opme/autorizacoes/{aut_a}/acao").status_code, 200)

    def test_auxiliar_administrativo_ve_fila_inteira(self):
        """O auxiliar administrativo (perfil 'auxiliar') precisa da fila inteira
        para analisar, cotar e receber — não é restringido como o médico."""
        from api.models import EmpresaUsuario
        empresa = _empresa("Hospital Rede", "opme-aux@example.com", "hospital_rede")
        ger = _client_for(empresa)
        opme = ger.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        ger.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P1", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json")
        aux = EmpresaUsuario.objects.create(empresa=empresa, nome="Aux",
            email="aux@ex.com", senha="x", perfil="auxiliar", ativo=True,
            sessao_ativa_chave=empresa.sessao_ativa_chave)
        cAux = _client_usuario(empresa, aux)
        lst = cAux.get("/api/hospital/opme/autorizacoes/")
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(lst.json()["total"], 1)

    def _levar_ate_cotacao(self, client, opme):
        """Cria um pedido e o leva (aprovando) até a etapa 'cotacao'."""
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1, "preco_solicitado": 5000}]},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "aprovar"}, content_type="application/json")
        return aut

    def test_cotacao_encerrada_avanca_esteira(self):
        """Evento: encerrar a cotação vinculada conclui a etapa 'cotacao' sozinha."""
        empresa = _empresa("Hospital Rede", "opme-ev-cot@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ev1", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut = self._levar_ate_cotacao(client, opme)
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(est["etapa_atual"], "cotacao")
        f1 = self._forn(client, "Forn ev1")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "autorizacao_id": aut},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 4000},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        est2 = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(est2["etapa_atual"], "dispensacao")

    def test_recebimento_liberado_avanca_esteira(self):
        """Evento: material liberado conclui a etapa 'dispensacao' sozinha."""
        empresa = _empresa("Hospital Rede", "opme-ev-rec@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ev2", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut = self._levar_ate_cotacao(client, opme)
        # avança cotacao->dispensacao via cotação encerrada
        f1 = self._forn(client, "Forn ev2")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "autorizacao_id": aut},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 4000},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        # recebe e libera (validade futura → liberado)
        client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2090-01-01",
                  "lote": "L-ev2"}, content_type="application/json")
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(est["etapa_atual"], "implante")

    def test_recebimento_bloqueado_nao_avanca_esteira(self):
        """Evento negativo: material bloqueado NÃO avança a esteira."""
        empresa = _empresa("Hospital Rede", "opme-ev-blq@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ev3", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut = self._levar_ate_cotacao(client, opme)
        f1 = self._forn(client, "Forn ev3")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "autorizacao_id": aut},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 4000},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        # lote vencido → bloqueado
        client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2000-01-01"},
            content_type="application/json")
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(est["etapa_atual"], "dispensacao")  # não avançou

    def test_implante_avanca_ate_faturamento(self):
        """Evento: registrar o implante conclui 'implante' e 'rastreabilidade',
        parando em 'faturamento' (que segue manual)."""
        empresa = _empresa("Hospital Rede", "opme-ev-imp@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ev4", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut = self._levar_ate_cotacao(client, opme)
        f1 = self._forn(client, "Forn ev4")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "autorizacao_id": aut},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 4000},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2090-01-01"},
            content_type="application/json")
        # registra implante → deve ir de 'implante' a 'faturamento'
        r = client.post("/api/hospital/opme/implantaveis/",
            data={"opme_id": opme, "autorizacao_id": aut, "paciente_nome": "P",
                  "data_implante": "2026-09-11", "numero_serie": "SN-ev4",
                  "lote_fabricante": "L-ev4"}, content_type="application/json")
        self.assertEqual(r.status_code, 201)
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(est["etapa_atual"], "faturamento")

    def test_avanco_por_evento_e_idempotente(self):
        """Um evento fora de ordem não pula etapas nem retrocede."""
        from api.models import AutorizacaoOPME
        from api.views_hospital_opme import _avancar_esteira_por_evento
        empresa = _empresa("Hospital Rede", "opme-ev-idem@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ev5", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut_id = self._levar_ate_cotacao(client, opme)
        aut = AutorizacaoOPME.objects.get(id=aut_id)   # etapa = cotacao
        # evento de dispensação chegando enquanto ainda está em cotacao: não age
        self.assertIsNone(_avancar_esteira_por_evento(aut, "dispensacao", "x"))
        self.assertEqual(aut.etapa, "cotacao")
        # evento correto avança uma única etapa
        self.assertEqual(_avancar_esteira_por_evento(aut, "cotacao", "x"), "dispensacao")
        # repetir o mesmo evento não avança de novo
        self.assertIsNone(_avancar_esteira_por_evento(aut, "cotacao", "x"))
        self.assertEqual(aut.etapa, "dispensacao")

    def test_segregacao_conta_corporativa_nao_trava(self):
        """Sem usuário nominal (login por conta corporativa) NÃO se bloqueia nada —
        não dá para afirmar identidade, e travar no escuro pararia a operação."""
        from api.models import AutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-seg-corp@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item seg", "tipo": "material", "preco_maximo": 2000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        # conta corporativa não grava usuário nominal
        self.assertIsNone(
            AutorizacaoOPME.objects.get(id=aut).solicitado_por_usuario_id)
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "aprovar"}, content_type="application/json")
        self.assertEqual(r.status_code, 200, "sem identidade não pode bloquear")

    def test_segregacao_bloqueia_autoaprovacao(self):
        """Quem solicitou não autoriza o próprio pedido — nem pela tela de decisão,
        nem contornando pela esteira."""
        from api.models import AutorizacaoOPME
        from api.views_hospital_opme import _bloqueio_segregacao
        empresa = _empresa("Hospital Rede", "opme-seg-self@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item self", "tipo": "material", "preco_maximo": 2000},
            content_type="application/json").json()["id"]
        aut_id = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        aut = AutorizacaoOPME.objects.get(id=aut_id)
        # simula pedido criado pelo usuário 42
        aut.solicitado_por_usuario_id = 42
        aut.save(update_fields=["solicitado_por_usuario_id"])

        class _Req:            # request com principal nominal
            pass
        class _Usr:
            __class__ = type("EmpresaUsuario", (), {})
        req = _Req()
        usr = _Usr(); usr.id = 42
        req.principal = usr
        self.assertIsNotNone(_bloqueio_segregacao(req, aut),
                             "mesmo usuário deve ser bloqueado")
        outro = _Usr(); outro.id = 43
        req.principal = outro
        self.assertIsNone(_bloqueio_segregacao(req, aut),
                          "outro auditor pode autorizar")

    def test_serializer_marca_autorizacao_propria(self):
        """A tela precisa saber que o pedido é do próprio usuário para esconder o
        botão de aprovar antes do clique."""
        empresa = _empresa("Hospital Rede", "opme-seg-ser@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item ser seg", "tipo": "material", "preco_maximo": 2000},
            content_type="application/json").json()["id"]
        client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json")
        lista = client.get("/api/hospital/opme/autorizacoes").json()["autorizacoes"]
        self.assertIn("autorizacao_propria", lista[0])
        # conta corporativa: sem identidade, nada é marcado como próprio
        self.assertFalse(lista[0]["autorizacao_propria"])

    def test_aprovar_move_esteira_e_registra_trilha(self):
        """A decisão não pode deixar o pedido travado na auditoria: aprovar avança a
        esteira e grava QUEM decidiu, na trilha."""
        empresa = _empresa("Hospital Rede", "opme-dec-apr@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item dec", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 2}]},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "aprovar"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["novo_status"], "aprovada")
        # a esteira saiu da auditoria — não ficou travada
        self.assertEqual(d["etapa"], "cotacao")
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        self.assertEqual(est["etapa_atual"], "cotacao")
        # a trilha registra a decisão com responsável
        historico = est["historico"]
        aprovacoes = [h for h in historico if "Aprovado" in (h.get("observacao") or "")]
        self.assertTrue(aprovacoes, "a trilha deve registrar quem aprovou")
        self.assertTrue(aprovacoes[0]["responsavel"])

    def test_negar_exige_motivo_e_encerra_com_trilha(self):
        """Negar sem motivo é recusado; com motivo, o motivo entra na trilha."""
        empresa = _empresa("Hospital Rede", "opme-dec-neg@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item neg", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1}]},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "negar"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "negar", "observacao": "Material sem indicação para o CID."},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["novo_status"], "negada")
        est = client.get(f"/api/hospital/opme/autorizacoes/{aut}/esteira").json()
        reprov = [h for h in est["historico"] if h["situacao"] == "reprovada"]
        self.assertTrue(reprov)
        self.assertIn("indicação", reprov[0]["observacao"])

    def test_aprovacao_parcial_pela_api_reduz_quantidade(self):
        """Aprovação parcial (antes inalcançável pela tela) aprova item a item."""
        from api.models import ItemAutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-dec-par@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item parcial", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        criado = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 4}]},
            content_type="application/json").json()
        aut = criado["id"]
        item_id = ItemAutorizacaoOPME.objects.get(autorizacao_id=aut).id
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "parcial",
                  "itens": [{"id": item_id, "quantidade_aprovada": 2,
                             "motivo_negativa": "Reduzido conforme protocolo."}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["novo_status"], "parcial")
        it = ItemAutorizacaoOPME.objects.get(id=item_id)
        self.assertEqual(it.quantidade_aprovada, 2)
        self.assertEqual(it.quantidade, 4)

    def test_parcial_nao_aprova_mais_que_solicitado(self):
        """Regressão: não dá para aprovar quantidade maior que a pedida."""
        from api.models import ItemAutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-dec-par2@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item p2", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 2}]},
            content_type="application/json").json()["id"]
        item_id = ItemAutorizacaoOPME.objects.get(autorizacao_id=aut).id
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut}/acao",
            data={"acao": "parcial",
                  "itens": [{"id": item_id, "quantidade_aprovada": 99}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)
        # rollback: nada foi alterado
        it = ItemAutorizacaoOPME.objects.get(id=item_id)
        self.assertEqual(it.quantidade_aprovada, 0)

    def test_preco_negociado_aparece_no_serializer_da_autorizacao(self):
        """O preço negociado precisa chegar na tela — é o que torna o ciclo visível
        (o que foi pedido × o que foi realmente pago)."""
        empresa = _empresa("Hospital Rede", "opme-ser-neg@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Parafuso ser", "tipo": "material", "preco_maximo": 4000},
            content_type="application/json").json()["id"]
        aut = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme, "quantidade": 1, "preco_solicitado": 4000}]},
            content_type="application/json").json()["id"]
        f1 = self._forn(client, "Forn Ser")
        cid = client.post("/api/hospital/opme/cotacoes/",
            data={"opme_id": opme, "quantidade": 1, "autorizacao_id": aut},
            content_type="application/json").json()["id"]
        client.post(f"/api/hospital/opme/cotacoes/{cid}",
            data={"fornecedor_id": f1, "preco_unitario": 3100},
            content_type="application/json")
        client.post(f"/api/hospital/opme/cotacoes/{cid}/encerrar",
            data={}, content_type="application/json")
        lista = client.get("/api/hospital/opme/autorizacoes").json()["autorizacoes"]
        alvo = [a for a in lista if a["id"] == aut][0]
        self.assertEqual(alvo["itens"][0]["preco_negociado"], 3100.0)
        # a trilha é preservada: o que o médico pediu continua lá
        self.assertEqual(alvo["itens"][0]["preco_solicitado"], 4000.0)

    def test_mediana_usa_preco_negociado_e_nao_infla(self):
        """Integridade da alavanca de sobrepreço: a mediana histórica tem que usar o
        preço REALMENTE pago, não o pedido — senão fica inflada e a alavanca mente."""
        from api.models import ItemAutorizacaoOPME
        from api.views_hospital_opme import _mediana_preco_praticado
        empresa = _empresa("Hospital Rede", "opme-med-neg@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Placa med", "tipo": "material", "preco_maximo": 10000},
            content_type="application/json").json()["id"]
        # 3 pedidos com preço solicitado alto (mínimo de amostra p/ mediana)
        for _ in range(3):
            client.post("/api/hospital/opme/autorizacoes/",
                data={"paciente_nome": "P", "medico_solicitante": "Dr",
                      "itens": [{"opme_id": opme, "quantidade": 1, "preco_solicitado": 9000}]},
                content_type="application/json")
        med_antes, n = _mediana_preco_praticado(empresa, opme)
        self.assertEqual(med_antes, 9000.0)
        self.assertEqual(n, 3)
        # negociação real derruba o preço dos 3 itens para 5000
        ItemAutorizacaoOPME.objects.filter(
            autorizacao__empresa=empresa, opme_id=opme).update(preco_negociado=5000)
        med_depois, _n2 = _mediana_preco_praticado(empresa, opme)
        self.assertEqual(med_depois, 5000.0)

    def test_kpis_expoem_alerta_compra_antecipada(self):
        """O painel principal (KPIs) expõe a contagem de alertas de compra
        antecipada — antes só existia dentro da aba Previsibilidade."""
        empresa = _empresa("Hospital Rede", "opme-kpi-prev@example.com", "hospital_rede")
        client = _client_for(empresa)
        d = client.get("/api/hospital/opme/kpis").json()
        self.assertIn("alertas_compra_antecipada_total", d)
        self.assertIn("alertas_compra_antecipada_top", d)
        self.assertIsInstance(d["alertas_compra_antecipada_top"], list)

    # ── Recebimento e Liberação para Cirurgia ────────────────────────────────
    def _aut_simples(self, client, opme_id):
        return client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "itens": [{"opme_id": opme_id, "quantidade": 1}]},
            content_type="application/json").json()["id"]

    def test_consignacao_entra_como_estoque_sem_paciente(self):
        """Consignação: material do fornecedor entra sem autorização/paciente, como
        estoque, e é validado na entrada (ANVISA/lote)."""
        empresa = _empresa("Hospital Rede", "opme-consig@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Kit consignado", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/recebimentos/",
            data={"consignado": True, "opme_id": opme, "quantidade_recebida": 4,
                  "lote": "L-CONS", "validade": "2090-01-01"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        d = r.json()
        self.assertEqual(d["status"], "consignado")
        self.assertTrue(d["consignado"])
        self.assertIsNone(d["autorizacao_id"])
        self.assertEqual(d["paciente_nome"], "(estoque em consignação)")

    def test_consignacao_lote_vencido_bloqueia(self):
        """A validação de entrada vale também para consignação."""
        empresa = _empresa("Hospital Rede", "opme-consig-v@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Kit venc", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/recebimentos/",
            data={"consignado": True, "opme_id": opme, "validade": "2000-01-01"},
            content_type="application/json").json()
        self.assertEqual(r["status"], "bloqueado")

    def test_consignacao_consumir_vira_faturavel(self):
        """Consumir consignação (implantada) → 'consumido', vinculando a cirurgia."""
        empresa = _empresa("Hospital Rede", "opme-consig-c@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Kit cons2", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        rid = client.post("/api/hospital/opme/recebimentos/",
            data={"consignado": True, "opme_id": opme, "validade": "2090-01-01"},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/recebimentos/{rid}/acao",
            data={"acao": "consumir", "autorizacao_id": aut},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["status"], "consumido")
        self.assertEqual(d["autorizacao_id"], aut)

    def test_consignacao_devolver_nao_fatura(self):
        """Devolver consignação não usada → 'devolvido' (não vira custo)."""
        empresa = _empresa("Hospital Rede", "opme-consig-d@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Kit cons3", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        rid = client.post("/api/hospital/opme/recebimentos/",
            data={"consignado": True, "opme_id": opme, "validade": "2090-01-01"},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/recebimentos/{rid}/acao",
            data={"acao": "devolver"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "devolvido")

    def test_acao_consignacao_recusa_recebimento_normal(self):
        """A ação de consignação não age sobre recebimento comum (de pedido)."""
        empresa = _empresa("Hospital Rede", "opme-consig-n@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Kit normal", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        rid = client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2090-01-01"},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/recebimentos/{rid}/acao",
            data={"acao": "devolver"}, content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_recebimento_valido_libera_para_cirurgia(self):
        """Material sem pendência ANVISA e sem lote vencido → LIBERADO."""
        empresa = _empresa("Hospital Rede", "opme-rec-ok@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cage lombar", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        r = client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "lote": "L1",
                  "numero_serie": "SN1", "validade": "2090-01-01"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["status"], "liberado")

    def test_recebimento_lote_vencido_bloqueia(self):
        """Lote com validade no passado → BLOQUEADO (não libera cirurgia)."""
        empresa = _empresa("Hospital Rede", "opme-rec-venc@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Placa", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        r = client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2000-01-01"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["status"], "bloqueado")
        self.assertIn("vencido", r.json()["motivo_bloqueio"].lower())

    def test_implante_bloqueado_sem_recebimento_liberado(self):
        """Trava progressiva: recebimento BLOQUEADO impede registrar implante (409)."""
        empresa = _empresa("Hospital Rede", "opme-trava@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Haste", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2000-01-01"},
            content_type="application/json")
        r = client.post("/api/hospital/opme/implantaveis/",
            data={"opme_id": opme, "autorizacao_id": aut, "paciente_nome": "P",
                  "data_implante": "2026-09-09", "numero_serie": "SN", "lote_fabricante": "L"},
            content_type="application/json")
        self.assertEqual(r.status_code, 409)

    def test_implante_passa_com_recebimento_liberado_e_consome(self):
        """Com recebimento LIBERADO o implante passa e o recebimento vira consumido."""
        from api.models import RecebimentoOPME
        empresa = _empresa("Hospital Rede", "opme-trava-ok@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Haste 2", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        rec = client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2090-01-01"},
            content_type="application/json").json()
        self.assertEqual(rec["status"], "liberado")
        r = client.post("/api/hospital/opme/implantaveis/",
            data={"opme_id": opme, "autorizacao_id": aut, "paciente_nome": "P",
                  "data_implante": "2026-09-09", "numero_serie": "SN", "lote_fabricante": "L"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(RecebimentoOPME.objects.get(id=rec["id"]).status, "consumido")

    def test_implante_legado_sem_autorizacao_nao_e_travado(self):
        """Regressão: implante SEM autorização vinculada segue funcionando (201)."""
        empresa = _empresa("Hospital Rede", "opme-legado@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item legado", "tipo": "material", "preco_maximo": 1000},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/implantaveis/",
            data={"opme_id": opme, "paciente_nome": "P", "data_implante": "2026-09-09",
                  "numero_serie": "SN", "lote_fabricante": "L"},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)

    def test_liberar_manual_exige_justificativa(self):
        """Liberar recebimento bloqueado exige justificativa; com ela, libera."""
        empresa = _empresa("Hospital Rede", "opme-lib@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item", "tipo": "material", "preco_maximo": 1000},
            content_type="application/json").json()["id"]
        aut = self._aut_simples(client, opme)
        rid = client.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut, "opme_id": opme, "validade": "2000-01-01"},
            content_type="application/json").json()["id"]
        r = client.post(f"/api/hospital/opme/recebimentos/{rid}/liberar",
            data={}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = client.post(f"/api/hospital/opme/recebimentos/{rid}/liberar",
            data={"justificativa": "Conferido manualmente pelo farmacêutico."},
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "liberado")

    def test_recebimento_isolado_por_empresa(self):
        """LGPD: autorização de outra empresa não pode receber material aqui."""
        emp_a = _empresa("Hospital A", "opme-rec-a@example.com", "hospital_rede")
        emp_b = _empresa("Hospital B", "opme-rec-b@example.com", "hospital_rede")
        ca, cb = _client_for(emp_a), _client_for(emp_b)
        opme_b = cb.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item B", "tipo": "material", "preco_maximo": 1000},
            content_type="application/json").json()["id"]
        aut_b = self._aut_simples(cb, opme_b)
        opme_a = ca.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item A", "tipo": "material", "preco_maximo": 1000},
            content_type="application/json").json()["id"]
        r = ca.post("/api/hospital/opme/recebimentos/",
            data={"autorizacao_id": aut_b, "opme_id": opme_a},
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    # ── Previsibilidade de consumo ───────────────────────────────────────────
    def test_previsao_serie_crescente_tendencia_alta(self):
        """Motor de previsão: série que sobe → tendência 'alta' e previsão > média histórica."""
        from api.services.opme_previsao import prever_serie
        d = prever_serie([2, 4, 6, 8, 10, 12], meses_frente=3)
        self.assertEqual(d["tendencia"], "alta")
        self.assertEqual(len(d["previsao"]), 3)
        self.assertGreater(d["previsao"][0], 0)
        self.assertGreaterEqual(d["meses_historico"], 6)

    def test_previsao_serie_estavel_previsibilidade_alta(self):
        """Série constante → previsibilidade máxima (100) e tendência estável."""
        from api.services.opme_previsao import prever_serie
        d = prever_serie([5, 5, 5, 5, 5, 5], meses_frente=2)
        self.assertEqual(d["tendencia"], "estavel")
        self.assertEqual(d["previsibilidade"], 100)
        self.assertEqual(d["previsao"], [5, 5])

    def test_previsao_serie_erratica_previsibilidade_baixa(self):
        """Série muito irregular → previsibilidade baixa (não dá pra planejar)."""
        from api.services.opme_previsao import prever_serie
        estavel = prever_serie([10, 10, 10, 10])["previsibilidade"]
        erratica = prever_serie([0, 30, 1, 25, 2, 28])["previsibilidade"]
        self.assertGreater(estavel, erratica)

    def test_previsao_sem_historico(self):
        """Sem consumo → previsão indisponível, sem quebrar."""
        from api.services.opme_previsao import prever_serie
        d = prever_serie([], meses_frente=3)
        self.assertEqual(d["previsao"], [0, 0, 0])
        self.assertEqual(d["previsibilidade"], 0)

    def test_previsibilidade_endpoint_por_procedimento(self):
        """Endpoint agrega consumo por procedimento em meses distintos e projeta."""
        from api.models import AutorizacaoOPME
        empresa = _empresa("Hospital Rede", "opme-prev@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cage cervical", "tipo": "protese", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        # cria autorizações e "espalha" no tempo (backdate de solicitado_em)
        base = date.today()
        for k, mesatras in enumerate([3, 2, 1, 0]):
            r = client.post("/api/hospital/opme/autorizacoes/",
                data={"paciente_nome": f"P{k}", "medico_solicitante": "Dr. Coluna",
                      "procedimento_tuss": "30715016",
                      "itens": [{"opme_id": opme, "quantidade": k + 1}]},
                content_type="application/json")
            aid = r.json()["id"]
            alvo = base.replace(day=1)
            for _ in range(mesatras):
                alvo = (alvo.replace(day=1) - timedelta(days=1)).replace(day=1)
            AutorizacaoOPME.objects.filter(id=aid).update(
                solicitado_em=timezone.make_aware(
                    __import__("datetime").datetime(alvo.year, alvo.month, 15, 12, 0)))
        r = client.get("/api/hospital/opme/previsibilidade?dim=procedimento&meses=3&historico=12")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["dimensao"], "procedimento")
        self.assertEqual(len(d["rotulos_previsao"]), 3)
        grupo = [g for g in d["grupos"] if g["label"] == "30715016"]
        self.assertTrue(grupo, "procedimento deveria aparecer nos grupos")
        self.assertEqual(len(grupo[0]["historico_mensal"]), 12)
        self.assertGreater(grupo[0]["total_historico"], 0)

    def test_previsibilidade_por_especialidade_usa_procedimento(self):
        """Dimensão especialidade agrega via a especialidade cadastrada no procedimento."""
        empresa = _empresa("Hospital Rede", "opme-prev-esp@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Placa buco", "tipo": "material", "preco_maximo": 3000},
            content_type="application/json").json()["id"]
        # procedimento com especialidade "Buco Maxilo"
        client.post("/api/hospital/opme/procedimentos/",
            data={"codigo_tuss": "40814096", "descricao": "Osteotomia mandibular",
                  "especialidade": "Buco Maxilo",
                  "itens": [{"opme_id": opme, "quantidade_maxima": 4}]},
            content_type="application/json")
        client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "Paciente Buco", "medico_solicitante": "Dr. BM",
                  "procedimento_tuss": "40814096",
                  "itens": [{"opme_id": opme, "quantidade": 2}]},
            content_type="application/json")
        r = client.get("/api/hospital/opme/previsibilidade?dim=especialidade")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        labels = [g["label"] for g in d["grupos"]]
        self.assertIn("Buco Maxilo", labels)

    # ── Controle de sobrepreço ───────────────────────────────────────────────
    def _pedido(self, client, opme_id, preco, extra=None):
        item = {"opme_id": opme_id, "quantidade": 1, "preco_solicitado": preco}
        if extra:
            item.update(extra)
        return client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr. Preço",
                  "justificativa": "ok",
                  "itens": [item]}, content_type="application/json")

    def test_sobrepreco_flag_acima_da_mediana(self):
        """Depois de histórico, um preço bem acima da mediana é sinalizado."""
        empresa = _empresa("Hospital Rede", "opme-sp1@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Parafuso X", "tipo": "material", "preco_maximo": 5000},
            content_type="application/json").json()["id"]
        # histórico: 3 pedidos a ~1000 (mediana = 1000)
        for _ in range(3):
            self._pedido(client, opme, 1000)
        # consulta pontual: preço 2000 deve acusar acima
        r = client.get(f"/api/hospital/opme/sobrepreco?opme_id={opme}&preco=2000")
        d = r.json()
        self.assertEqual(d["mediana"], 1000.0)
        self.assertTrue(d["acima"])
        self.assertEqual(d["excesso_unitario"], 1000.0)
        # e um novo pedido a 2000 registra alerta de triagem de sobrepreço
        r2 = self._pedido(client, opme, 2000)
        self.assertEqual(r2.status_code, 201)
        self.assertTrue(any("acima da mediana" in a for a in r2.json()["alertas_triagem"]))

    def test_sobrepreco_alinhar_mediana_grava_economia_e_entra_na_torre(self):
        """Aceitar alinhar à mediana grava economia real e soma na Torre."""
        empresa = _empresa("Hospital Rede", "opme-sp2@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Haste Y", "tipo": "protese", "preco_maximo": 9000},
            content_type="application/json").json()["id"]
        for _ in range(3):
            self._pedido(client, opme, 3000)   # mediana = 3000
        # pedido a 5000 aceitando alinhar → economia (5000-3000)*1 = 2000
        r = self._pedido(client, opme, 5000, extra={"alinhar_mediana": True})
        self.assertEqual(r.status_code, 201)
        eco = client.get("/api/hospital/opme/economia").json()
        self.assertEqual(eco["economia_sobrepreco"], 2000.0)
        self.assertEqual(eco["alinhamentos_mediana"], 1)
        lever = [a for a in eco["torre_economia"] if a["alavanca"] == "Controle de sobrepreço"][0]
        self.assertEqual(lever["fato"], 2000.0)

    def test_sobrepreco_potencial_no_painel(self):
        """Pedido pendente acima da mediana entra no painel de sobrepreço (potencial)."""
        empresa = _empresa("Hospital Rede", "opme-sp3@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Cage Z", "tipo": "protese", "preco_maximo": 12000},
            content_type="application/json").json()["id"]
        for _ in range(3):
            self._pedido(client, opme, 4000)   # mediana = 4000
        self._pedido(client, opme, 7000)       # acima, sem alinhar → potencial 3000
        pan = client.get("/api/hospital/opme/sobrepreco").json()
        self.assertEqual(pan["total_evitavel"], 3000.0)
        self.assertEqual(len(pan["itens"]), 1)
        self.assertEqual(pan["itens"][0]["excesso_evitavel"], 3000.0)

    def test_sobrepreco_sem_historico_nao_flag(self):
        """Sem amostra mínima de histórico, não afirma sobrepreço."""
        empresa = _empresa("Hospital Rede", "opme-sp4@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Novo item", "tipo": "material", "preco_maximo": 8000},
            content_type="application/json").json()["id"]
        r = client.get(f"/api/hospital/opme/sobrepreco?opme_id={opme}&preco=9999")
        d = r.json()
        self.assertIsNone(d["mediana"])
        self.assertFalse(d["acima"])

    # ── Alavanca padronização por procedimento (lever 5) ─────────────────────
    def test_padronizacao_potencial_material_nao_preferencial(self):
        """Pedido pendente com material não-preferencial mais caro que o preferencial
        do procedimento entra na alavanca de padronização (o médico não é bloqueado)."""
        empresa = _empresa("Hospital Rede", "opme-pad@example.com", "hospital_rede")
        client = _client_for(empresa)
        pref = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Preferencial barato", "tipo": "protese", "preco_maximo": 4000},
            content_type="application/json").json()["id"]
        caro = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Não preferencial caro", "tipo": "protese", "preco_maximo": 7000},
            content_type="application/json").json()["id"]
        # procedimento padroniza o preferencial (barato) e permite o caro também
        client.post("/api/hospital/opme/procedimentos/",
            data={"codigo_tuss": "30715016", "descricao": "Artrodese",
                  "itens": [{"opme_id": pref, "quantidade_maxima": 1, "preferencial": True},
                            {"opme_id": caro, "quantidade_maxima": 1, "preferencial": False}]},
            content_type="application/json")
        # médico pede o caro (com justificativa — nunca é bloqueado)
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr",
                  "procedimento_tuss": "30715016", "justificativa": "preferência técnica",
                  "itens": [{"opme_id": caro, "quantidade": 1, "preco_solicitado": 7000}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)  # passou, não foi bloqueado
        eco = client.get("/api/hospital/opme/economia").json()
        lever = [a for a in eco["torre_economia"] if a["alavanca"] == "Padronização por procedimento"][0]
        self.assertEqual(lever["potencial"], 3000.0)  # 7000 - 4000
        self.assertEqual(eco["padronizacao_potencial"], 3000.0)

    # ── Alavanca anti-compra-emergencial (lever 4) ───────────────────────────
    def test_anti_emergencial_estimativa_no_torre(self):
        """Pedido urgente gera estimativa de sobrecusto evitável, marcada como estimativa."""
        empresa = _empresa("Hospital Rede", "opme-emerg@example.com", "hospital_rede")
        client = _client_for(empresa)
        opme = client.post("/api/hospital/opme/catalogo/",
            data={"descricao": "Item urgente", "tipo": "material", "preco_maximo": 12000},
            content_type="application/json").json()["id"]
        r = client.post("/api/hospital/opme/autorizacoes/",
            data={"paciente_nome": "P", "medico_solicitante": "Dr", "urgente": True,
                  "itens": [{"opme_id": opme, "quantidade": 1, "preco_solicitado": 12000}]},
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        eco = client.get("/api/hospital/opme/economia").json()
        lever = [a for a in eco["torre_economia"] if a["alavanca"] == "Anti-compra-emergencial"][0]
        self.assertTrue(lever.get("estimativa"))
        self.assertEqual(lever["fato"], 0.0)
        # 12000 * (0.20 / 1.20) = 2000
        self.assertEqual(lever["potencial"], 2000.0)
        # estimativa NÃO entra no potencial "duro" da Torre
        self.assertEqual(eco["torre_estimativa_total"], 2000.0)


class CamadaUmAdequacaoClinicaTests(TestCase):
    """CAMADA 1 · Adequação clínica (o ATO). Julga se o procedimento é indicado
    para o CID, sem tocar na governança de material (Camada 2). Nunca bloqueia."""

    TUSS = "30731000"          # artroplastia total de quadril (exemplo)
    CID_OK = "M16.1"           # coxartrose primária → indicação canônica
    CID_RUIM = "M54.5"         # lombalgia → não sustenta prótese de quadril

    def _hospital(self, email):
        return _empresa("Hospital Camada1", email, "hospital_rede")

    def _seed_indicacao(self):
        IndicacaoClinicaOPME.objects.create(
            procedimento_tuss=self.TUSS, procedimento_descricao="Artroplastia de quadril",
            especialidade="Ortopedia — Quadril", cid10_prefixo="M16",
            nivel="indicado", fonte="Diretriz SBOT")

    def _catalogo(self, client):
        return client.post("/api/hospital/opme/catalogo/",
                           data={"descricao": "Prótese de Quadril", "tipo": "protese"},
                           content_type="application/json").json()["id"]

    def _pedir(self, client, item_id, cid, tuss=None, **extra):
        body = {"paciente_nome": "Paciente C1", "medico_solicitante": "Dr. C1",
                "cid10": cid, "procedimento_tuss": tuss if tuss is not None else self.TUSS,
                "itens": [{"opme_id": item_id, "quantidade": 1}]}
        body.update(extra)
        return client.post("/api/hospital/opme/autorizacoes/",
                           data=body, content_type="application/json")

    # ── a lógica de avaliação ────────────────────────────────────────────────
    def test_verde_quando_cid_casa_indicacao(self):
        self._seed_indicacao()
        client = _client_for(self._hospital("c1-verde@example.com"))
        r = self._pedir(client, self._catalogo(client), self.CID_OK)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["adequacao"]["status"], "verde")

    def test_vermelho_quando_cid_nao_sustenta_procedimento(self):
        self._seed_indicacao()
        client = _client_for(self._hospital("c1-vermelho@example.com"))
        r = self._pedir(client, self._catalogo(client), self.CID_RUIM, justificativa="quadro atípico")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["adequacao"]["status"], "vermelho")

    def test_amarelo_quando_indicacao_condicional(self):
        IndicacaoClinicaOPME.objects.create(
            procedimento_tuss=self.TUSS, cid10_prefixo="M16", nivel="condicional",
            criterio="após falha do tratamento conservador", fonte="Diretriz SBOT")
        client = _client_for(self._hospital("c1-amarelo@example.com"))
        r = self._pedir(client, self._catalogo(client), self.CID_OK, justificativa="tratamento prévio falhou")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["adequacao"]["status"], "amarelo")

    def test_nao_avaliado_sem_base(self):
        """Sem base para o procedimento → nao_avaliado (honesto, não finge)."""
        client = _client_for(self._hospital("c1-sembase@example.com"))
        r = self._pedir(client, self._catalogo(client), self.CID_OK)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["adequacao"]["status"], "nao_avaliado")

    # ── interação com a Via Rápida (não penaliza o que não avaliou) ───────────
    def test_via_rapida_nao_penalizada_quando_sem_base(self):
        """Regressão crítica: sem base de indicação, a Camada 1 NÃO deve travar a
        Via Rápida — preserva o comportamento anterior da Camada 2."""
        empresa = self._hospital("c1-vr-sembase@example.com")
        client = _client_for(empresa)
        # material homologado + ANVISA válida → via rápida elegível
        item = client.post("/api/hospital/opme/catalogo/",
                           data={"descricao": "Prótese OK", "tipo": "protese",
                                 "homologado": True, "codigo_anvisa": "80044680371"},
                           content_type="application/json").json()["id"]
        r = self._pedir(client, item, self.CID_OK)
        self.assertEqual(r.status_code, 201, r.content)
        # sem base → nao_avaliado; a via rápida decide pelos critérios de material
        self.assertEqual(r.json()["adequacao"]["status"], "nao_avaliado")

    def test_via_rapida_bloqueada_quando_indicacao_vermelha(self):
        """Indicação frágil (vermelho) NÃO pode auto-aprovar por Via Rápida."""
        IndicacaoClinicaOPME.objects.create(
            procedimento_tuss=self.TUSS, cid10_prefixo="M16", nivel="nao_indicado",
            fonte="Diretriz SBOT")
        empresa = self._hospital("c1-vr-vermelho@example.com")
        client = _client_for(empresa)
        item = client.post("/api/hospital/opme/catalogo/",
                           data={"descricao": "Prótese OK", "tipo": "protese",
                                 "homologado": True, "codigo_anvisa": "80044680371"},
                           content_type="application/json").json()["id"]
        r = self._pedir(client, item, self.CID_OK, justificativa="quadro atípico")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["adequacao"]["status"], "vermelho")
        self.assertFalse(r.json()["via_rapida"])

    # ── confirmação da indicação pelo médico (nunca bloqueia) ────────────────
    def test_medico_confirma_indicacao_verde(self):
        self._seed_indicacao()
        client = _client_for(self._hospital("c1-confirma@example.com"))
        aut_id = self._pedir(client, self._catalogo(client), self.CID_OK).json()["id"]
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut_id}/adequacao/",
                        data={}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["adequacao_confirmada"])

    def test_confirmacao_vermelha_exige_justificativa_mas_nao_bloqueia(self):
        IndicacaoClinicaOPME.objects.create(
            procedimento_tuss=self.TUSS, cid10_prefixo="M16", nivel="nao_indicado",
            fonte="Diretriz SBOT")
        client = _client_for(self._hospital("c1-just@example.com"))
        aut_id = self._pedir(client, self._catalogo(client), self.CID_OK,
                             justificativa="pedido inicial").json()["id"]
        # sem justificativa na confirmação → 400 orientando (não bloqueia o pedido)
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut_id}/adequacao/",
                        data={}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["codigo"], "adequacao_requer_justificativa")
        # com justificativa clínica → confirma (a decisão do procedimento é do médico)
        r = client.post(f"/api/hospital/opme/autorizacoes/{aut_id}/adequacao/",
                        data={"justificativa": "caso excepcional documentado"},
                        content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["adequacao_confirmada"])

    def test_camada2_intacta_material_continua_avaliado(self):
        """Garantia de não-regressão: a Camada 2 (governança de material) segue
        avaliando triagem/alertas normalmente, independente da Camada 1."""
        self._seed_indicacao()
        empresa = self._hospital("c1-camada2@example.com")
        client = _client_for(empresa)
        # material NÃO homologado → a Camada 2 deve exigir justificativa (RN 424)
        item = client.post("/api/hospital/opme/catalogo/",
                           data={"descricao": "Prótese fora", "tipo": "protese",
                                 "homologado": False},
                           content_type="application/json").json()["id"]
        r = self._pedir(client, item, self.CID_OK)  # sem justificativa
        self.assertEqual(r.status_code, 400)  # Camada 2 barra por falta de justificativa
