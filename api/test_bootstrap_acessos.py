import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from .models import DonoSaaS, Empresa


class BootstrapAcessosTests(TestCase):
    def test_bootstrap_acessos_cria_contas_setoriais_para_staging(self):
        env = {
            "SOLUSCRT_BOOTSTRAP_EMPRESA_EMAIL": "empresa-staging@example.com",
            "SOLUSCRT_BOOTSTRAP_EMPRESA_PASSWORD": "senha-empresa",
            "SOLUSCRT_BOOTSTRAP_FARMACIA_EMAIL": "farmacia-staging@example.com",
            "SOLUSCRT_BOOTSTRAP_FARMACIA_PASSWORD": "senha-farmacia",
            "SOLUSCRT_BOOTSTRAP_HOSPITAL_EMAIL": "hospital-staging@example.com",
            "SOLUSCRT_BOOTSTRAP_HOSPITAL_PASSWORD": "senha-hospital",
            "SOLUSCRT_BOOTSTRAP_GOVERNO_EMAIL": "governo-staging@example.com",
            "SOLUSCRT_BOOTSTRAP_GOVERNO_PASSWORD": "senha-governo",
            "SOLUSCRT_BOOTSTRAP_OWNER_EMAIL": "owner-staging@example.com",
            "SOLUSCRT_BOOTSTRAP_OWNER_PASSWORD": "senha-owner",
        }
        buffer = StringIO()

        with patch.dict(os.environ, env, clear=False):
            call_command("bootstrap_acessos", stdout=buffer)

        empresa = Empresa.objects.get(email="empresa-staging@example.com")
        farmacia = Empresa.objects.get(email="farmacia-staging@example.com")
        hospital = Empresa.objects.get(email="hospital-staging@example.com")
        governo = Empresa.objects.get(email="governo-staging@example.com")
        owner = DonoSaaS.objects.get(email="owner-staging@example.com")

        self.assertEqual(empresa.pacote_codigo, "empresa_starter_5")
        self.assertEqual(farmacia.pacote_codigo, "farmacia_rede_regional")
        self.assertEqual(hospital.pacote_codigo, "hospital_medio")
        self.assertEqual(governo.pacote_codigo, "governo_estado")
        self.assertEqual(farmacia.tipo_conta, Empresa.TIPO_EMPRESA)
        self.assertEqual(hospital.tipo_conta, Empresa.TIPO_EMPRESA)
        self.assertFalse(farmacia.acesso_governo)
        self.assertFalse(hospital.acesso_governo)
        self.assertTrue(governo.acesso_governo)
        self.assertTrue(owner.ativo)
        self.assertIn("farmacia-staging@example.com", buffer.getvalue())
        self.assertIn("hospital-staging@example.com", buffer.getvalue())
