"""
Portal do prestador (self-service) + recurso de glosa com IA de mérito.
"""
import json
from datetime import timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, GuiaTISS, LoteTISSRecebido, PortalPrestadorToken,
    PrestadorPlanoSaude, RecursoGlosa,
)
from .views_hospital_tiss import gerar_xml_tiss_3_05
from .views_plano_portal_prestador import _ia_merito_recurso
from .views_plano_tiss_recepcao import importar_lote_tiss, processar_lote


def _empresa(email):
    return Empresa.objects.create(
        nome="Operadora Portal", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_operadora",
        sessao_ativa_chave=f"sessao-{email}",
    )


def _client_for(empresa):
    c = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    c.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return c


def _xml_lote_duplicidade(empresa):
    """Gera um XML TISS com 2 procedimentos iguais → o 2º será glosado por duplicidade."""
    guia = GuiaTISS.objects.create(
        empresa=empresa, tipo="sp_sadt", numero_guia="G-P1",
        operadora_codigo="123456", operadora_nome="SoloCRT",
        beneficiario_nome="Paciente Portal", beneficiario_carteirinha="00011122233",
        cid10="A90",
        procedimentos=[
            {"tabela": "22", "codigo": "40304361", "descricao": "Exame", "quantidade": 1, "valor_unitario": 100.0},
            {"tabela": "22", "codigo": "40304361", "descricao": "Exame dup", "quantidade": 1, "valor_unitario": 100.0},
        ],
    )
    return gerar_xml_tiss_3_05(guia, empresa)


class PortalPrestadorTests(TestCase):
    def setUp(self):
        self.op = _empresa("portal@example.com")
        self.prest = PrestadorPlanoSaude.objects.create(
            empresa=self.op, nome_fantasia="Clínica Portal", codigo_rede="CP1",
            status=PrestadorPlanoSaude.STATUS_CREDENCIADO,
        )
        self.pt = PortalPrestadorToken.objects.create(prestador=self.prest, token="tok-teste-123", ativo=True)
        self.base = f"/portal-prestador/{self.pt.token}/api"

    def test_ia_merito_heuristica(self):
        alto, _ = _ia_merito_recurso("1403", "Foram dois atendimentos em horários distintos, com laudo anexo.")
        baixo, _ = _ia_merito_recurso("1401", "não concordo")
        self.assertGreater(alto, baixo)
        self.assertGreaterEqual(alto, 65)

    def test_token_gerar_owner(self):
        c = _client_for(self.op)
        r = c.post(f"/api/plano-saude/prestador/{self.prest.id}/portal-token/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("portal-prestador/", r.json()["url"])

    def test_enviar_lote_forca_prestador_do_token(self):
        # o XML foi gerado pela operadora (codigo do prestador vazio); o portal deve
        # AINDA assim vincular ao prestador do token (isolamento).
        xml = _xml_lote_duplicidade(self.op)
        c = Client()
        r = c.post(f"{self.base}/enviar-lote/", data=xml, content_type="application/xml")
        self.assertEqual(r.status_code, 200)
        lote_id = r.json()["lote"]["id"]
        lote = LoteTISSRecebido.objects.get(id=lote_id)
        self.assertEqual(lote.prestador_id, self.prest.id)
        self.assertEqual(lote.status, "processado")
        # duplicidade → 100 glosado
        self.assertEqual(lote.valor_glosado, Decimal("100.00"))

    def test_dados_lista_lotes_e_recursos(self):
        xml = _xml_lote_duplicidade(self.op)
        Client().post(f"{self.base}/enviar-lote/", data=xml, content_type="application/xml")
        r = Client().get(f"{self.base}/dados/")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["lotes"]), 1)
        self.assertEqual(d["prestador"]["nome"], "Clínica Portal")

    def test_abrir_recurso_e_responder_deferido(self):
        # cria um lote processado com item glosado
        lote = processar_lote(importar_lote_tiss(_xml_lote_duplicidade(self.op), self.op))
        lote.prestador = self.prest; lote.save(update_fields=["prestador"])
        item_glosado = lote.itens.filter(glosado=True).first()
        self.assertIsNotNone(item_glosado)
        # prestador abre recurso
        c = Client()
        r = c.post(f"{self.base}/recurso/", data=json.dumps({
            "lote_id": lote.id, "item_id": item_glosado.id,
            "justificativa": "Atendimentos em horários distintos, com prontuário anexo comprovando.",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        rec_id = r.json()["recurso"]["id"]
        self.assertGreaterEqual(r.json()["recurso"]["ia_merito_score"], 60)
        # operadora defere total → glosa do lote zera
        oc = _client_for(self.op)
        r2 = oc.post(f"/api/plano-saude/recursos/{rec_id}/responder/",
                     data=json.dumps({"decisao": "deferido", "resposta": "Procedente."}),
                     content_type="application/json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["recurso"]["status"], "deferido")
        lote.refresh_from_db()
        self.assertEqual(lote.valor_glosado, Decimal("0.00"))
        self.assertEqual(lote.valor_liberado, lote.valor_apresentado)

    def test_recurso_sem_valor_glosado_erro(self):
        # lote sem glosa (procedimento único válido)
        guia = GuiaTISS.objects.create(
            empresa=self.op, tipo="sp_sadt", numero_guia="G-OK",
            operadora_codigo="1", operadora_nome="X", beneficiario_nome="Y",
            beneficiario_carteirinha="1", cid10="A90",
            procedimentos=[{"tabela": "22", "codigo": "40304361", "descricao": "E", "quantidade": 1, "valor_unitario": 50.0}],
        )
        lote = processar_lote(importar_lote_tiss(gerar_xml_tiss_3_05(guia, self.op), self.op))
        lote.prestador = self.prest; lote.save(update_fields=["prestador"])
        r = Client().post(f"{self.base}/recurso/", data=json.dumps({
            "lote_id": lote.id, "justificativa": "quero contestar mesmo sem glosa"}),
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_token_invalido(self):
        r = Client().get("/portal-prestador/token-que-nao-existe/api/dados/")
        self.assertEqual(r.status_code, 403)
