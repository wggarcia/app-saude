"""
Testes da página Multi-Unidade do SST (Turnos / Benchmarking / Multi-Estado),
construída na auditoria de jun/2026.

A página em si é gateada por sst.multi_unidade (tier Enterprise+), mas as
abas internas usam features mais altas (sst.turnos = Corporativo,
sst.benchmarking = Nacional) — por isso o roundtrip completo só passa no
tier Nacional, e os tiers intermediários devem ver a página mas tomar 403
nas abas que não pagaram.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa


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
        tipo_conta=Empresa.TIPO_EMPRESA,
        pacote_codigo=pacote_codigo,
        sessao_ativa_chave=f"sessao-{email}",
    )


class SSTMultiUnidadeTests(TestCase):
    def test_pagina_bloqueada_no_tier_base(self):
        empresa = _empresa("SST Starter", "sst-starter@example.com", "empresa_starter_5")
        client = _client_for(empresa)
        self.assertEqual(client.get("/sst/multi-unidade/").status_code, 403)

    def test_pagina_liberada_no_tier_enterprise_mas_turnos_bloqueado(self):
        empresa = _empresa("SST Enterprise", "sst-enterprise@example.com", "empresa_enterprise_100")
        client = _client_for(empresa)

        self.assertEqual(client.get("/sst/multi-unidade/").status_code, 200)

        r = client.get("/api/sst/turnos/")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json().get("upgrade_necessario"))

        r = client.get("/api/sst/benchmarking/")
        self.assertEqual(r.status_code, 403)

    def test_tier_nacional_libera_turnos_e_benchmarking(self):
        empresa = _empresa("SST Nacional", "sst-nacional@example.com", "empresa_nacional_500")
        client = _client_for(empresa)

        self.assertEqual(client.get("/sst/multi-unidade/").status_code, 200)

        r = client.post(
            "/api/sst/turnos/",
            data={"nome": "Turno Manhã", "janela": "06:00-14:00"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

        r = client.get("/api/sst/turnos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["turnos"]), 1)

        r = client.get("/api/sst/benchmarking/")
        self.assertEqual(r.status_code, 200)
