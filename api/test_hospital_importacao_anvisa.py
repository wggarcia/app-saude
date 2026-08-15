"""
Testes do motor de importação genérico do Hospital + validação ANVISA.
"""
import io
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.utils import timezone

from .models import (
    Empresa, CatalogoOPME, FornecedorHospital, ImportacaoDados,
    RegistroAnvisaProdutoSaude, EmpresaAfeAnvisa,
)


def _client_for(empresa):
    client = Client()
    payload = {
        "empresa_id": empresa.id, "principal_kind": "empresa",
        "principal_id": empresa.id, "session_key": empresa.sessao_ativa_chave,
        "exp": timezone.now() + timedelta(hours=1),
    }
    client.cookies["auth_token"] = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
    return client


def _empresa(nome, email, pacote="hospital_rede"):
    return Empresa.objects.create(
        nome=nome, email=email, senha=make_password("123456"), ativo=True,
        pacote_codigo=pacote, sessao_ativa_chave=f"sessao-{email}")


def _csv_upload(conteudo, nome="dados.csv"):
    f = io.BytesIO(conteudo.encode("utf-8"))
    f.name = nome
    return f


class ImportacaoDadosTests(TestCase):

    def test_fluxo_completo_catalogo_csv(self):
        """Upload → prévia → processar cria itens no catálogo (idempotente)."""
        emp = _empresa("Hosp", "imp-catalogo@ex.com")
        c = _client_for(emp)
        csv_txt = ("Descrição;Fabricante;Preço máximo (R$);Código ANVISA\n"
                   "Placa Titânio 2.4mm;Neoortho;4.300,00;80277351199\n"
                   "Parafuso Cortical;Ortosintese;320,00;80277352200\n")
        up = c.post("/api/hospital/importacao/upload",
                    {"destino": "catalogo_opme", "arquivo": _csv_upload(csv_txt)})
        self.assertEqual(up.status_code, 201)
        imp_id = up.json()["id"]
        self.assertEqual(up.json()["total_linhas"], 2)
        # mapeamento automático deve ter reconhecido "Descrição" e "Fabricante"
        self.assertIn("descricao", up.json()["mapeamento_sugerido"])

        prev = c.post(f"/api/hospital/importacao/{imp_id}/previa",
                      data={"mapeamento": up.json()["mapeamento_sugerido"]},
                      content_type="application/json")
        self.assertEqual(prev.status_code, 200)
        self.assertEqual(prev.json()["obrigatorios_sem_coluna"], [])
        self.assertEqual(prev.json()["previa_erro"], 0)

        proc = c.post(f"/api/hospital/importacao/{imp_id}/processar",
                      data={}, content_type="application/json")
        self.assertEqual(proc.status_code, 200)
        self.assertEqual(proc.json()["linhas_ok"], 2)
        self.assertEqual(CatalogoOPME.objects.filter(empresa=emp).count(), 2)
        placa = CatalogoOPME.objects.get(empresa=emp, descricao="Placa Titânio 2.4mm")
        self.assertEqual(float(placa.preco_maximo), 4300.00)   # 4.300,00 → 4300.00
        self.assertEqual(placa.codigo_anvisa, "80277351199")

        # reprocessar o MESMO arquivo não duplica (upsert pela descrição)
        up2 = c.post("/api/hospital/importacao/upload",
                     {"destino": "catalogo_opme", "arquivo": _csv_upload(csv_txt)})
        c.post(f"/api/hospital/importacao/{up2.json()['id']}/processar",
               data={}, content_type="application/json")
        self.assertEqual(CatalogoOPME.objects.filter(empresa=emp).count(), 2)

    def test_obrigatorio_sem_mapeamento_bloqueia(self):
        """Sem mapear a descrição (obrigatória), processar é bloqueado."""
        emp = _empresa("Hosp", "imp-obrig@ex.com")
        c = _client_for(emp)
        up = c.post("/api/hospital/importacao/upload",
                    {"destino": "catalogo_opme",
                     "arquivo": _csv_upload("Fabricante;Preço\nAcme;100\n")})
        imp_id = up.json()["id"]
        proc = c.post(f"/api/hospital/importacao/{imp_id}/processar",
                      data={}, content_type="application/json")
        self.assertEqual(proc.status_code, 400)
        self.assertIn("Descrição", proc.json()["erro"])

    def test_linha_invalida_e_pulada_e_reportada(self):
        """Linha com preço não-numérico é pulada e listada nos erros."""
        emp = _empresa("Hosp", "imp-invalida@ex.com")
        c = _client_for(emp)
        csv_txt = ("Descrição;Preço máximo (R$)\n"
                   "Item Bom;500\n"
                   "Item Ruim;abc\n")
        up = c.post("/api/hospital/importacao/upload",
                    {"destino": "catalogo_opme", "arquivo": _csv_upload(csv_txt)})
        imp_id = up.json()["id"]
        c.post(f"/api/hospital/importacao/{imp_id}/previa",
               data={"mapeamento": up.json()["mapeamento_sugerido"]},
               content_type="application/json")
        proc = c.post(f"/api/hospital/importacao/{imp_id}/processar",
                      data={}, content_type="application/json")
        d = proc.json()
        self.assertEqual(d["linhas_ok"], 1)
        self.assertEqual(d["linhas_erro"], 1)
        self.assertEqual(d["erros"][0]["linha"], 2)
        self.assertEqual(CatalogoOPME.objects.filter(empresa=emp).count(), 1)

    def test_isolamento_tenant_no_historico(self):
        """Importação de uma empresa não aparece no histórico de outra (LGPD)."""
        emp_a = _empresa("A", "imp-a@ex.com")
        emp_b = _empresa("B", "imp-b@ex.com")
        ca = _client_for(emp_a)
        ca.post("/api/hospital/importacao/upload",
                {"destino": "catalogo_opme", "arquivo": _csv_upload("Descrição\nX\n")})
        cb = _client_for(emp_b)
        hist_b = cb.get("/api/hospital/importacao/historico").json()
        self.assertEqual(len(hist_b["importacoes"]), 0)

    def test_modelo_csv_download(self):
        """Baixar planilha modelo devolve o cabeçalho dos campos do alvo."""
        emp = _empresa("Hosp", "imp-modelo@ex.com")
        c = _client_for(emp)
        r = c.get("/api/hospital/importacao/modelo/fornecedor_hospital")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Razão social", r.content.decode("utf-8"))

    def test_import_fornecedor_verifica_afe(self):
        """Importar fornecedor cruza CNPJ com a base AFE e marca a situação."""
        emp = _empresa("Hosp", "imp-forn-afe@ex.com")
        c = _client_for(emp)
        EmpresaAfeAnvisa.objects.create(
            cnpj="11222333000181", razao_social="Distribuidora X", numero_afe="1.02.030-4", ativo=True)
        csv_txt = "Razão social;CNPJ\nDistribuidora X;11.222.333/0001-81\n"
        up = c.post("/api/hospital/importacao/upload",
                    {"destino": "fornecedor_hospital", "arquivo": _csv_upload(csv_txt)})
        imp_id = up.json()["id"]
        c.post(f"/api/hospital/importacao/{imp_id}/processar",
               data={}, content_type="application/json")
        forn = FornecedorHospital.objects.get(empresa=emp, cnpj="11222333000181")
        self.assertEqual(forn.razao_social, "Distribuidora X")
        # AFE ainda não verificada na importação em lote; verifica sob demanda
        c.post("/api/hospital/opme/fornecedores/verificar-afe",
               data={}, content_type="application/json")
        forn.refresh_from_db()
        self.assertEqual(forn.afe_situacao, "ativa")


class AnvisaConsultaTests(TestCase):

    def test_consulta_registro_valido(self):
        """Registro existente e válido devolve dados para autopreenchimento."""
        emp = _empresa("Hosp", "anvisa-ok@ex.com")
        c = _client_for(emp)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80277351199", nome_produto="Placa Mandibular",
            detentor="Neoortho", situacao="Válido",
            data_vencimento=date.today() + timedelta(days=365))
        r = c.get("/api/hospital/opme/anvisa/consulta?registro=80277351199")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["encontrado"])
        self.assertTrue(d["valido"])
        self.assertFalse(d["vencido"])
        self.assertEqual(d["nome_produto"], "Placa Mandibular")

    def test_consulta_registro_inexistente(self):
        """Registro que não está na base devolve encontrado=False."""
        emp = _empresa("Hosp", "anvisa-nao@ex.com")
        c = _client_for(emp)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80000000001", situacao="Válido")
        r = c.get("/api/hospital/opme/anvisa/consulta?registro=99999999999")
        self.assertFalse(r.json()["encontrado"])

    def test_consulta_base_vazia_sinaliza_indisponivel(self):
        """Sem base sincronizada, avisa em vez de fingir 'não encontrado'."""
        emp = _empresa("Hosp", "anvisa-vazia@ex.com")
        c = _client_for(emp)
        r = c.get("/api/hospital/opme/anvisa/consulta?registro=80277351199")
        d = r.json()
        self.assertFalse(d["encontrado"])
        self.assertTrue(d["base_indisponivel"])

    def test_consulta_registro_vencido(self):
        """Registro válido mas com data passada é marcado como vencido."""
        emp = _empresa("Hosp", "anvisa-venc@ex.com")
        c = _client_for(emp)
        RegistroAnvisaProdutoSaude.objects.create(
            numero_registro="80277351199", situacao="Válido",
            data_vencimento=date(2020, 1, 1))
        r = c.get("/api/hospital/opme/anvisa/consulta?registro=80277351199")
        self.assertTrue(r.json()["vencido"])
