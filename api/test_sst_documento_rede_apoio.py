"""
SST: fecha 2 stubs — atualização de status de DocumentoSST (marcar em revisão)
e a Rede de Apoio psicossocial (CRUD real, antes botão "em breve").
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, DocumentoSST, RedeApoioSST


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa_sst(email):
    return Empresa.objects.create(
        nome="Empresa SST", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="empresa_starter_5",
        sessao_ativa_chave=f"sessao-{email}",
    )


class DocumentoStatusTests(TestCase):
    def test_marcar_em_revisao(self):
        emp = _empresa_sst("doc@example.com")
        doc = DocumentoSST.objects.create(empresa=emp, tipo="PGR", titulo="PGR 2026", status="vigente")
        client = _client_for(emp)
        r = client.patch(f"/api/sst/documentos/{doc.id}", data={"status": "em_revisao"},
                         content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 200, r.content)
        doc.refresh_from_db()
        self.assertEqual(doc.status, "em_revisao")

    def test_status_invalido_rejeitado(self):
        emp = _empresa_sst("doc2@example.com")
        doc = DocumentoSST.objects.create(empresa=emp, tipo="PGR", titulo="X", status="vigente")
        r = _client_for(emp).patch(f"/api/sst/documentos/{doc.id}", data={"status": "xpto"},
                                   content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 400)

    def test_isolamento_tenant(self):
        emp = _empresa_sst("doc-a@example.com")
        outra = _empresa_sst("doc-b@example.com")
        doc_o = DocumentoSST.objects.create(empresa=outra, tipo="PGR", titulo="Alheio", status="vigente")
        r = _client_for(emp).patch(f"/api/sst/documentos/{doc_o.id}", data={"status": "em_revisao"},
                                   content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 404)


class RedeApoioTests(TestCase):
    def test_crud_e_isolamento(self):
        emp = _empresa_sst("apoio@example.com")
        client = _client_for(emp)
        # cria
        r = client.post("/api/sst/rede-apoio", data={
            "nome": "CAPS II", "tipo": "externo", "categoria": "psiquiatrico",
            "telefone": "188", "disponibilidade": "24h"},
            content_type="application/json", secure=True)
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["recurso"]["id"]
        # lista
        d = client.get("/api/sst/rede-apoio", secure=True).json()
        self.assertEqual(len(d["recursos"]), 1)
        self.assertEqual(d["recursos"][0]["categoria_label"], "Psiquiátrico")
        # remove
        rr = client.delete(f"/api/sst/rede-apoio/{rid}", secure=True)
        self.assertEqual(rr.status_code, 200)
        self.assertEqual(RedeApoioSST.objects.filter(empresa=emp).count(), 0)

    def test_isolamento_tenant(self):
        emp = _empresa_sst("apoio-a@example.com")
        outra = _empresa_sst("apoio-b@example.com")
        RedeApoioSST.objects.create(empresa=outra, nome="Alheio", categoria="social")
        d = _client_for(emp).get("/api/sst/rede-apoio", secure=True).json()
        self.assertEqual(len(d["recursos"]), 0)
