"""
Testes dos módulos clínicos hospitalares REDE-exclusivos construídos na
auditoria de jun/2026: CCIH, Hemoterapia, Obstétrico, Oncologia e OPME.

Cobre, para cada módulo: gate de feature na página (bloqueado no tier base
hospital_medio, liberado no tier hospital_rede) e um roundtrip básico de
criação via API no tier liberado.
"""
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, CatalogoOPME, AutorizacaoOPME, ImplantavelRegistro, ProtocoloOncologico,
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

    # ── RN 424/ANS, TNU, ANVISA, fraude (pedido Unimed) ─────────────────────

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
