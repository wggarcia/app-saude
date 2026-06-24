"""
Achado ao revisar o setor "Rede de Saúde" com o usuário: não existe (nem nunca
existiu de fato) um 6º segmento vendável "Rede" fora de Farmácia e Hospital —
os planos reais sempre foram "Rede Farmacêutica Regional/Nacional"
(farmacia_rede_regional/nacional, setor "farmacia") e "Rede/Grupo Hospitalar"
(hospital_rede/hospital_grupo, setor "hospital"). O pacote standalone
"rede_regional"/"rede_nacional" (setor "rede") nunca foi um produto real e foi
removido de api/planos.py — junto com todo o despacho que tratava "rede" como
setor próprio (destino_conta, dashboard_url_por_setor, setor_label,
dashboard_empresa_corporativo, TODOS_SETORES, _destino_correto).

A funcionalidade de Rede (multi-unidade, benchmarking, KPIs consolidados,
transferências, sala de situação) continua existindo — mas só como módulo
interno ("Rede de Gestão", código `farmacia.rede` / `hospital.rede`) dentro de
uma conta de Farmácia ou Hospital que está no plano de rede. Estes testes
confirmam que esse caminho embutido funciona ponta a ponta.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa
from .planos import PACOTES_SAAS, normalizar_codigo_pacote


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa(email, pacote_codigo):
    return Empresa.objects.create(
        nome="Rede Embutida Teste", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote_codigo,
        sessao_ativa_chave="", max_dispositivos=10, max_usuarios=10,
    )


class SegmentoRedeStandaloneNaoExisteTests(TestCase):
    def test_pacotes_saas_nao_tem_setor_rede(self):
        setores = {p["setor"] for p in PACOTES_SAAS.values()}
        self.assertNotIn("rede", setores)

    def test_codigo_legado_rede_resolve_para_farmacia_rede(self):
        self.assertEqual(normalizar_codigo_pacote("rede"), "farmacia_rede_regional")


class RedeEmbutidaFarmaciaTests(TestCase):
    def test_login_de_farmacia_rede_vai_para_dashboard_farmacia(self):
        empresa = _empresa("farmacia-rede@example.com", "farmacia_rede_regional")
        client = _client_for(empresa)
        r = client.get("/dashboard-empresa/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/dashboard-farmacia/")

    def test_farmacia_rede_acessa_pagina_rede_gestao(self):
        empresa = _empresa("farmacia-rede-2@example.com", "farmacia_rede_regional")
        client = _client_for(empresa)
        r = client.get("/rede/gestao/")
        self.assertEqual(r.status_code, 200)


class RedeEmbutidaHospitalTests(TestCase):
    def test_login_de_hospital_rede_vai_para_dashboard_hospital(self):
        empresa = _empresa("hospital-rede@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.get("/dashboard-empresa/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/dashboard-hospital/")

    def test_hospital_rede_acessa_pagina_rede_gestao(self):
        empresa = _empresa("hospital-rede-2@example.com", "hospital_rede")
        client = _client_for(empresa)
        r = client.get("/rede/gestao/")
        self.assertEqual(r.status_code, 200)
