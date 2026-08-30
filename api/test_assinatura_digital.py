"""
Testes da assinatura digital de documentos clínicos (assinatura_digital.py):
assina em CAdES-BES real quando há certificado, verifica integridade E
autenticidade criptográfica, e detecta adulteração.
"""
import base64
import datetime

from django.test import TestCase


def _gerar_cred(senha="senha123"):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12, BestAvailableEncryption

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Dr Teste")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2035, 1, 1))
            .sign(key, hashes.SHA256()))
    pfx = pkcs12.serialize_key_and_certificates(
        b"c", key, cert, None, BestAvailableEncryption(senha.encode()))

    class _Cred:
        rnds_certificado_pfx_b64 = base64.b64encode(pfx).decode()
        def get_rnds_certificado_senha(self):
            return senha
    return _Cred()


class AssinaturaDigitalTests(TestCase):
    CONTEUDO = "PRONTUARIO:1|EVOLUCAO:5|TEXTO:paciente estavel"

    def test_assina_cades_quando_ha_certificado(self):
        from api.assinatura_digital import assinar_conteudo
        ok, assin, h, metodo, erro = assinar_conteudo(self.CONTEUDO, _gerar_cred(), "CRM/SP 1")
        self.assertTrue(ok)
        self.assertIn("ICP-Brasil", metodo)  # CAdES-BES ou RSA-SHA256, nunca rótulo falso
        self.assertTrue(assin)

    def test_verificacao_original_integra(self):
        # Caminho padrão (CAdES quando a lib suporta): integridade garantida;
        # autenticidade plena fica para validador ICP-Brasil externo (autentico None).
        from api.assinatura_digital import assinar_conteudo, verificar_assinatura
        cred = _gerar_cred()
        ok, assin, h, metodo, erro = assinar_conteudo(self.CONTEUDO, cred, "CRM/SP 1")
        v = verificar_assinatura(self.CONTEUDO, assin, h, cred)
        self.assertTrue(v["integro"])
        self.assertIsNot(v["autentico"], False)

    def test_adulteracao_detectada(self):
        from api.assinatura_digital import assinar_conteudo, verificar_assinatura
        cred = _gerar_cred()
        ok, assin, h, metodo, erro = assinar_conteudo(self.CONTEUDO, cred, "CRM/SP 1")
        v = verificar_assinatura(self.CONTEUDO + " ADULTERADO", assin, h, cred)
        self.assertFalse(v["integro"])         # tamper sempre detectado

    def test_rsa_autenticidade_criptografica(self):
        # Força o caminho RSA-raw (sem CAdES) — aí a autenticidade é verificada
        # criptograficamente contra a chave pública do certificado.
        import api.assinatura_digital as ad
        orig = ad._PKCS7_OK
        ad._PKCS7_OK = False
        try:
            cred = _gerar_cred()
            ok, assin, h, metodo, erro = ad.assinar_conteudo(self.CONTEUDO, cred, "CRM/SP 1")
            self.assertEqual(metodo, "ICP-Brasil-RSA-SHA256")
            v_ok = ad.verificar_assinatura(self.CONTEUDO, assin, h, cred)
            self.assertTrue(v_ok["integro"] and v_ok["autentico"])
            # outra chave não autentica
            v_bad = ad.verificar_assinatura(self.CONTEUDO, assin, h, _gerar_cred())
            self.assertTrue(v_bad["integro"])
            self.assertFalse(v_bad["autentico"])
        finally:
            ad._PKCS7_OK = orig

    def test_fallback_sha256_sem_certificado(self):
        from api.assinatura_digital import assinar_conteudo, verificar_assinatura
        ok, assin, h, metodo, erro = assinar_conteudo(self.CONTEUDO, None, "CRM/SP 1")
        self.assertTrue(ok)
        self.assertEqual(metodo, "SHA256")
        v = verificar_assinatura(self.CONTEUDO, assin, h, None)
        self.assertTrue(v["integro"])
        self.assertIsNone(v["autentico"])      # SHA-256 não tem autenticidade de chave
