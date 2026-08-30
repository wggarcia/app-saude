"""
Testes da trilha de auditoria clínica imutável (AuditoriaClinica) — requisito SBIS.
Cobre: hash-chain, imutabilidade (instância e queryset), detecção de adulteração
e o registro automático de acesso ao prontuário (leitura e escrita).
"""
from django.test import TestCase
from django.db import connection

from api.models import Empresa, AuditoriaClinica


class AuditoriaClinicaImutabilidadeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.emp = Empresa.objects.create(nome="Hosp Teste", email="hosp.audit@test.local", senha="x")

    def _cria(self, **kw):
        base = dict(empresa=self.emp, acao="visualizar", recurso="prontuario", recurso_id="1")
        base.update(kw)
        return AuditoriaClinica.objects.create(**base)

    def test_hash_chain_encadeia(self):
        r1 = self._cria(acao="criar")
        r2 = self._cria()
        r3 = self._cria(acao="criar", recurso="evolucao", recurso_id="9")
        self.assertEqual(r1.hash_anterior, "0" * 64)
        self.assertEqual(r2.hash_anterior, r1.hash_registro)
        self.assertEqual(r3.hash_anterior, r2.hash_registro)
        v = AuditoriaClinica.verificar_cadeia(self.emp)
        self.assertTrue(v["integra"])
        self.assertEqual(v["registros_verificados"], 3)

    def test_update_instancia_bloqueado(self):
        r = self._cria()
        r.acao = "alterar"
        with self.assertRaises(ValueError):
            r.save()

    def test_delete_instancia_bloqueado(self):
        r = self._cria()
        with self.assertRaises(ValueError):
            r.delete()

    def test_delete_e_update_em_massa_bloqueados(self):
        self._cria()
        with self.assertRaises(ValueError):
            AuditoriaClinica.objects.filter(empresa=self.emp).delete()
        with self.assertRaises(ValueError):
            AuditoriaClinica.objects.filter(empresa=self.emp).update(acao="x")

    def test_adulteracao_detectada(self):
        self._cria(acao="criar")
        alvo = self._cria()
        self._cria(acao="criar", recurso="evolucao", recurso_id="9")
        # adultera direto no banco, contornando o ORM
        with connection.cursor() as c:
            c.execute("UPDATE api_auditoriaclinica SET acao=%s WHERE id=%s", ["forjado", alvo.pk])
        v = AuditoriaClinica.verificar_cadeia(self.emp)
        self.assertFalse(v["integra"])
        self.assertEqual(v["quebra_em_id"], alvo.pk)

    def test_isolamento_por_empresa(self):
        outra = Empresa.objects.create(nome="Outro", email="outro.audit@test.local", senha="x")
        self._cria()
        AuditoriaClinica.objects.create(empresa=outra, acao="criar", recurso="prontuario", recurso_id="1")
        # cadeia de cada empresa é independente e íntegra
        self.assertTrue(AuditoriaClinica.verificar_cadeia(self.emp)["integra"])
        self.assertTrue(AuditoriaClinica.verificar_cadeia(outra)["integra"])
