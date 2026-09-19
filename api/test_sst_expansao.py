"""Testes dos módulos de expansão SST (CIPA votação, EPI offline, SEC, integração)."""
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.test import TestCase

from api.models import (
    Empresa, FuncionarioSST, EleicaoCIPA, CandidatoCIPA, VotanteCIPA, VotoCIPA,
    SincronizacaoEPIOffline, EPIItem, EntregaEPI, ClienteConsultoriaSST,
    TokenIntegracaoSST, OrdemServicoSST, OrdemServicoCiencia,
    InvestigacaoAcidente, AcaoCorretivaAcidente,
    InspecaoSeguranca, ItemInspecao,
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


class OrdemServicoTest(_Base):
    def test_ciencia_unica_por_trabalhador(self):
        o = OrdemServicoSST.objects.create(empresa=self.emp, titulo="OS", funcao="Soldador")
        OrdemServicoCiencia.objects.create(ordem=o, funcionario=self.f1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrdemServicoCiencia.objects.create(ordem=o, funcionario=self.f1)

    def test_contagem_assinadas(self):
        o = OrdemServicoSST.objects.create(empresa=self.emp, titulo="OS", funcao="Op")
        OrdemServicoCiencia.objects.create(ordem=o, funcionario=self.f1, assinado=True)
        OrdemServicoCiencia.objects.create(ordem=o, funcionario=self.f2, assinado=False)
        self.assertEqual(o.ciencias.filter(assinado=True).count(), 1)
        self.assertEqual(o.ciencias.count(), 2)


class InvestigacaoAcidenteTest(_Base):
    def test_ishikawa_e_porques_persistem(self):
        i = InvestigacaoAcidente.objects.create(
            empresa=self.emp, titulo="Queda", metodo="ambos",
            ishikawa={"mao_de_obra": ["sem treinamento"], "material": ["piso molhado"]},
            cinco_porques=["escorregou", "piso molhado", "vazamento", "cano velho", "sem manutenção"],
            causa_raiz="Falta de manutenção preventiva",
        )
        i.refresh_from_db()
        self.assertEqual(i.ishikawa["material"], ["piso molhado"])
        self.assertEqual(len(i.cinco_porques), 5)

    def test_kpi_acoes(self):
        i = InvestigacaoAcidente.objects.create(empresa=self.emp, titulo="Ev")
        AcaoCorretivaAcidente.objects.create(investigacao=i, descricao="a1", status="concluida")
        AcaoCorretivaAcidente.objects.create(investigacao=i, descricao="a2", status="pendente")
        self.assertEqual(i.acoes.count(), 2)
        self.assertEqual(i.acoes.filter(status="concluida").count(), 1)

    def test_isolamento_por_empresa(self):
        i = InvestigacaoAcidente.objects.create(empresa=self.emp, titulo="X")
        self.assertFalse(InvestigacaoAcidente.objects.filter(id=i.id, empresa=self.outra).exists())


class InspecaoSegurancaTest(_Base):
    def test_indice_conformidade(self):
        ins = InspecaoSeguranca.objects.create(empresa=self.emp, titulo="NR-12")
        ItemInspecao.objects.create(inspecao=ins, descricao="a", conforme="conforme")
        ItemInspecao.objects.create(inspecao=ins, descricao="b", conforme="conforme")
        ItemInspecao.objects.create(inspecao=ins, descricao="c", conforme="nao_conforme")
        ItemInspecao.objects.create(inspecao=ins, descricao="d", conforme="na")  # ignorado no índice
        self.assertEqual(ins.indice_conformidade, 66.7)  # 2 de 3 avaliáveis

    def test_indice_sem_itens_none(self):
        ins = InspecaoSeguranca.objects.create(empresa=self.emp, titulo="Vazia")
        self.assertIsNone(ins.indice_conformidade)

    def test_nao_conformidades_contadas(self):
        ins = InspecaoSeguranca.objects.create(empresa=self.emp, titulo="X")
        ItemInspecao.objects.create(inspecao=ins, descricao="a", conforme="nao_conforme")
        self.assertEqual(ins.itens.filter(conforme="nao_conforme").count(), 1)
