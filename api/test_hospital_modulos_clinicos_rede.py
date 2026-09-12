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
