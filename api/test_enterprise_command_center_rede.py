"""
Gap encontrado após remover o setor standalone "rede" (ver
api/test_rede_embutida_em_farmacia_hospital.py): o Enterprise Command Center
(/api/enterprise/command-center) só mostrava o card de Rede (estrutura/
governança + transferências entre unidades) para esse setor que nunca foi
vendido — Farmácia e Hospital no plano de rede nunca recebiam esse card,
mesmo já fazendo parte de uma Rede de verdade via UnidadeRede.

Corrigido em api/services/enterprise_dashboard.py::_cards_por_setor: Farmácia/
Hospital com a feature "*.multi_unidade" (plano de rede) agora recebem os
cards de rede (_rede_cards) em conjunto com os cards do próprio setor. Contas
sem essa feature (ex: farmacia_local) continuam sem o card — não fazem parte
de uma rede e o plano nem permite.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, Rede, UnidadeRede


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
        nome="Command Center Teste", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo=pacote_codigo,
        sessao_ativa_chave="", max_dispositivos=10, max_usuarios=10,
    )


class CommandCenterRedeEmbutidaTests(TestCase):
    def test_farmacia_rede_com_unidade_mostra_card_de_rede(self):
        empresa = _empresa("farmacia-cc-rede@example.com", "farmacia_rede_regional")
        rede = Rede.objects.create(nome="Rede Teste", tipo=Rede.TIPO_FARMACIA)
        UnidadeRede.objects.create(empresa=empresa, rede=rede, tipo=UnidadeRede.TIPO_FARMACIA)

        client = _client_for(empresa)
        r = client.get("/api/enterprise/command-center")
        self.assertEqual(r.status_code, 200)
        codigos = [c["codigo"] for c in r.json()["modulos"]]
        self.assertIn("rede_unidades", codigos)
        self.assertIn("transferencias_estoque", codigos)

    def test_hospital_rede_com_unidade_mostra_card_de_rede(self):
        empresa = _empresa("hospital-cc-rede@example.com", "hospital_rede")
        rede = Rede.objects.create(nome="Rede Hospitalar Teste", tipo=Rede.TIPO_HOSPITAL)
        UnidadeRede.objects.create(empresa=empresa, rede=rede, tipo=UnidadeRede.TIPO_HOSPITAL)

        client = _client_for(empresa)
        r = client.get("/api/enterprise/command-center")
        self.assertEqual(r.status_code, 200)
        codigos = [c["codigo"] for c in r.json()["modulos"]]
        self.assertIn("rede_unidades", codigos)
        self.assertIn("transferencias_estoque", codigos)

    def test_farmacia_local_nao_mostra_card_de_rede(self):
        empresa = _empresa("farmacia-cc-local@example.com", "farmacia_local")
        client = _client_for(empresa)
        r = client.get("/api/enterprise/command-center")
        self.assertEqual(r.status_code, 200)
        codigos = [c["codigo"] for c in r.json()["modulos"]]
        self.assertNotIn("rede_unidades", codigos)
