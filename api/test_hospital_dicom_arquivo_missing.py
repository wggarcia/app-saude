"""
Regressão da varredura dinâmica do Hospital (jun/2026): 186 rotas de
api/hospital e hospital/ percorridas com dados reais via test client.

api_ris_dicom_arquivo abria o arquivo DICOM direto do storage sem tratar
a ausência dele — se o registro existe no banco mas o arquivo não está
mais em disco (migração de storage, limpeza manual, falha de sync),
FileNotFoundError não tratado quebrava a request com 500 em vez de
devolver 404.
"""
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import Empresa, ProntuarioHospitalar, ExameRIS, InstanciaDicom


class DicomArquivoAusenteTests(TestCase):
    def test_arquivo_dicom_ausente_no_storage_e_404_nao_500(self):
        empresa = Empresa.objects.create(
            nome="Hospital DICOM", email="dicom-ausente@example.com",
            senha=make_password("123456"), ativo=True, tipo_conta=Empresa.TIPO_EMPRESA,
            pacote_codigo="hospital_rede", sessao_ativa_chave="sessao-dicom-ausente",
        )
        prontuario = ProntuarioHospitalar.objects.create(empresa=empresa, paciente_nome="Pac")
        exame = ExameRIS.objects.create(
            empresa=empresa, prontuario=prontuario, paciente_nome="Pac",
            regiao_anatomica="Torax", solicitante="Dr. X",
        )
        instancia = InstanciaDicom.objects.create(exame=exame, arquivo="dicom/inexistente.dcm")

        client = Client()
        payload = {
            "empresa_id": empresa.id, "principal_kind": "empresa", "principal_id": empresa.id,
            "session_key": empresa.sessao_ativa_chave, "exp": timezone.now() + timedelta(hours=1),
        }
        client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

        r = client.get(f"/api/hospital/imagem/dicom/{instancia.id}/arquivo/")
        self.assertEqual(r.status_code, 404)
