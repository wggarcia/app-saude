"""
Regressão da varredura dinâmica do Plano de Saúde (jun/2026): 112 rotas
de api/plano-saude percorridas com test client e dados reais de todos
os submódulos. 1 bug real encontrado:

  - api_diops_criar não validava o formato do campo "trimestre" (o
    próprio erro de validação dizia "obrigatório (AAAAQ)", mas nada
    impedia salvar qualquer string). api_diops_gerar_xml então chamava
    gerar_diops_3_0 -> _trimestre_para_periodo, que fazia
    int(trimestre[4]) sem tratamento — qualquer valor fora do formato
    AAAAQ (ex: "2026-Q2") derrubava a geração do XML real da DIOPS com
    500 em vez de um erro claro.

Corrigido com validação por regex na criação (raiz do problema) e uma
guarda defensiva na geração do XML (para registros já salvos com
formato inválido antes da correção).
"""
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
import jwt
from datetime import timedelta
from django.conf import settings
from django.utils import timezone

from .models import Empresa, DIOPSDeclaracao


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
        "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa_plano(email):
    return Empresa.objects.create(
        nome="Plano DIOPS", email=email, senha=make_password("123456"), ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA, pacote_codigo="plano_saude_enterprise",
        sessao_ativa_chave=f"sessao-{email}",
    )


class DiopsTrimestreValidacaoTests(TestCase):
    def test_criar_diops_com_trimestre_invalido_e_rejeitado(self):
        empresa = _empresa_plano("diops-criar-invalido@example.com")
        client = _client_for(empresa)
        r = client.post(
            "/api/plano-saude/ans/diops",
            data={"trimestre": "2026-Q2"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_criar_diops_com_trimestre_valido_funciona(self):
        empresa = _empresa_plano("diops-criar-valido@example.com")
        client = _client_for(empresa)
        r = client.post(
            "/api/plano-saude/ans/diops",
            data={"trimestre": "20262"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)

    def test_gerar_xml_de_registro_legado_com_trimestre_invalido_nao_quebra(self):
        empresa = _empresa_plano("diops-xml-legado@example.com")
        d = DIOPSDeclaracao.objects.create(empresa=empresa, trimestre="2026-Q2")
        client = _client_for(empresa)
        r = client.get(f"/api/plano-saude/ans/diops/{d.id}/xml")
        self.assertEqual(r.status_code, 422)
