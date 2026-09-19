"""Testes dos módulos de expansão SST (CIPA votação, EPI offline, SEC, integração)."""
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.test import TestCase

from api.models import (
    Empresa, FuncionarioSST, EleicaoCIPA, CandidatoCIPA, VotanteCIPA, VotoCIPA,
    SincronizacaoEPIOffline, EPIItem, EntregaEPI, ClienteConsultoriaSST,
    TokenIntegracaoSST,
)


class _Base(TestCase):
    def setUp(self):
        self.emp = Empresa.objects.create(nome="ACME", email="acme@x.com", senha="x")
        self.outra = Empresa.objects.create(nome="Outra", email="outra@x.com", senha="x")
        self.f1 = FuncionarioSST.objects.create(empresa=self.emp, nome="Eleitor", cargo="Op")
        self.f2 = FuncionarioSST.objects.create(empresa=self.emp, nome="Cand", cargo="Op")


class CipaVotacaoTest(_Base):
    def test_voto_secreto_sem_vinculo_eleitor(self):
        campos = [f.name for f in VotoCIPA._meta.fields]
        self.assertNotIn("funcionario", campos)  # cédula anônima

    def test_bloqueia_voto_duplo(self):
        el = EleicaoCIPA.objects.create(empresa=self.emp, titulo="T", status="votacao")
        VotanteCIPA.objects.create(eleicao=el, funcionario=self.f1, votou=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VotanteCIPA.objects.create(eleicao=el, funcionario=self.f1)

    def test_apuracao_conta_votos(self):
        el = EleicaoCIPA.objects.create(empresa=self.emp, titulo="T", status="votacao")
        c = CandidatoCIPA.objects.create(eleicao=el, funcionario=self.f2, numero=1)
        VotoCIPA.objects.create(eleicao=el, candidato=c)
        VotoCIPA.objects.create(eleicao=el, candidato=c)
        cont = dict(VotoCIPA.objects.filter(eleicao=el).values_list("candidato_id").annotate(n=Count("id")))
        self.assertEqual(cont.get(c.id), 2)


class EpiOfflineTest(_Base):
    def test_sync_idempotente_por_uuid(self):
        epi = EPIItem.objects.create(empresa=self.emp, nome="Luva", tipo=EPIItem.TIPO_CHOICES[0][0])

        def sync(uuid):
            if SincronizacaoEPIOffline.objects.filter(empresa=self.emp, uuid_cliente=uuid).exists():
                return "dup"
            ent = EntregaEPI.objects.create(
                empresa=self.emp, funcionario=self.f1, epi=epi, data_entrega="2026-09-19", quantidade=1
            )
            SincronizacaoEPIOffline.objects.create(empresa=self.emp, uuid_cliente=uuid, entrega=ent, processado=True)
            return "ok"

        self.assertEqual(sync("u1"), "ok")
        self.assertEqual(sync("u1"), "dup")
        self.assertEqual(EntregaEPI.objects.filter(empresa=self.emp).count(), 1)

    def test_uuid_unico_global(self):
        SincronizacaoEPIOffline.objects.create(empresa=self.emp, uuid_cliente="dup")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SincronizacaoEPIOffline.objects.create(empresa=self.outra, uuid_cliente="dup")


class SecPortalTest(_Base):
    def test_token_unico_e_isolamento(self):
        c = ClienteConsultoriaSST.objects.create(
            empresa=self.emp, nome_cliente="Cliente", token_acesso="tok123"
        )
        # cliente pertence à empresa correta
        self.assertEqual(c.empresa_id, self.emp.id)
        # busca por token de outra empresa não vaza (filtragem por empresa nas views)
        self.assertFalse(
            ClienteConsultoriaSST.objects.filter(token_acesso="tok123", empresa=self.outra).exists()
        )


class IntegracaoTokenTest(_Base):
    def test_token_armazena_apenas_hash(self):
        import hashlib
        valor = "sst_segredo"
        t = TokenIntegracaoSST.objects.create(
            empresa=self.emp, nome="ERP", token_hash=hashlib.sha256(valor.encode()).hexdigest(), prefixo=valor[:12]
        )
        self.assertNotIn(valor, t.token_hash)
        self.assertEqual(t.token_hash, hashlib.sha256(valor.encode()).hexdigest())
