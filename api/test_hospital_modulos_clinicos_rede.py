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

from .models import Empresa, CatalogoOPME, ProtocoloOncologico


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
                "tipo": "concentrado_hemacias",
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

    def test_pagina_liberada_e_cria_ciclo_e_apac(self):
        empresa = _empresa("Hospital Rede", "onco-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/oncologia/").status_code, 200)

        protocolo = ProtocoloOncologico.objects.create(
            empresa=empresa, codigo="FOLFOX-6-TESTE", nome="FOLFOX-6"
        )

        r = client.post(
            "/api/hospital/oncologia/ciclos/",
            data={
                "protocolo_id": protocolo.id,
                "paciente_nome": "Paciente Onco",
                "cid10_principal": "C18",
                "data_inicio": date.today().isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.post(
            "/api/hospital/oncologia/apacs/",
            data={"paciente_nome": "Paciente Onco", "cid10_principal": "C18"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.get("/api/hospital/oncologia/ciclos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)


class OPMETests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("Hospital Base", "opme-base@example.com", "hospital_medio")
        client = _client_for(empresa)
        self.assertEqual(client.get("/hospital/opme/").status_code, 403)

    def test_pagina_liberada_e_cria_item_catalogo_e_autorizacao(self):
        empresa = _empresa("Hospital Rede", "opme-rede@example.com", "hospital_rede")
        client = _client_for(empresa)

        self.assertEqual(client.get("/hospital/opme/").status_code, 200)

        r = client.post(
            "/api/hospital/opme/catalogo/",
            data={"descricao": "Prótese de Quadril", "tipo": "proteses"},
            content_type="application/json",
        )
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
