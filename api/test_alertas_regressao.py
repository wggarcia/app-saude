"""
Testes de regressão dos bugs encontrados na varredura dinâmica de
api/views_alertas.py (jun/2026). Cada bug listado abaixo fazia a função de
alerta correspondente lançar uma exceção real, sempre, para toda empresa —
silenciosamente engolida pelo `except Exception: pass` da função, então o
alerta nunca aparecia no painel e nenhum erro era visto em lugar nenhum.

  - _alertas_sst: ASOOcupacional.objects.filter(valido=True) — campo
    "valido" não existe no modelo (campo real de resultado é "resultado").
  - _alertas_sst: AfastamentoSST usava "data_retorno" — campo real é
    "data_retorno_real".
  - _alertas_hospital: LeitoHospital usava "atualizado_em__date__lt" —
    o modelo não tem nenhum campo de timestamp.
  - _alertas_hospital: InternacaoHospital.objects.filter(status="ativo")
    — o choice real é "ativa" (feminino), nunca "ativo".
  - _alertas_hospital: "hoje - internacao.data_entrada" subtraindo date de
    datetime (TypeError) — corrigido para comparar com .date().
  - _alertas_hospital: EvolucaoClinica usava "criado_em" — campo real é
    "registrado_em".
"""
from datetime import date, timedelta

from django.contrib.auth.hashers import make_password
from django.test import TestCase

from .models import (
    Empresa, FuncionarioSST, ASOOcupacional, AfastamentoSST,
    DepartamentoHospital, LeitoHospital, InternacaoHospital, PacienteHospital,
    EvolucaoClinica,
)
from .views_alertas import _alertas_sst, _alertas_hospital


def _empresa(email, pacote_codigo="empresa_profissional_25"):
    return Empresa.objects.create(
        nome="Empresa Alertas Regressao",
        email=email,
        senha=make_password("123456"),
        ativo=True,
        tipo_conta=Empresa.TIPO_EMPRESA,
        pacote_codigo=pacote_codigo,
        sessao_ativa_chave=f"sessao-{email}",
    )


class AlertaSSTSemExcecaoTests(TestCase):
    def test_aso_inapto_nao_conta_como_valido_e_nao_lanca_excecao(self):
        empresa = _empresa("alerta-aso-inapto@example.com")
        hoje = date.today()
        f = FuncionarioSST.objects.create(
            empresa=empresa, nome="Func", cpf="11122233344", cargo="Op",
            data_admissao=hoje, ativo=True,
        )
        ASOOcupacional.objects.create(
            empresa=empresa, funcionario=f, tipo="periodico",
            data_emissao=hoje, data_validade=hoje + timedelta(days=200),
            resultado="inapto",
        )
        alertas = _alertas_sst(empresa, hoje)
        titulos = [a["titulo"] for a in alertas]
        self.assertIn("1 funcionário(s) sem ASO válido", titulos)

    def test_afastamento_ativo_aparece_sem_excecao(self):
        empresa = _empresa("alerta-afastamento@example.com")
        hoje = date.today()
        f = FuncionarioSST.objects.create(
            empresa=empresa, nome="Func", cpf="11122233355", cargo="Op",
            data_admissao=hoje, ativo=True,
        )
        AfastamentoSST.objects.create(
            empresa=empresa, funcionario=f, motivo="doenca_comum",
            data_inicio=hoje - timedelta(days=5),
        )
        alertas = _alertas_sst(empresa, hoje)
        titulos = [a["titulo"] for a in alertas]
        self.assertIn("1 funcionário(s) afastado(s)", titulos)


class AlertaHospitalSemExcecaoTests(TestCase):
    def test_leito_em_manutencao_aparece_sem_excecao(self):
        empresa = _empresa("alerta-leito@example.com")
        hoje = date.today()
        dep = DepartamentoHospital.objects.create(empresa=empresa, nome="UTI")
        LeitoHospital.objects.create(empresa=empresa, departamento=dep, numero="101", status="manutencao")

        alertas = _alertas_hospital(empresa, hoje)
        titulos = [a["titulo"] for a in alertas]
        self.assertIn("1 leito(s) em manutenção", titulos)

    def test_internacao_ativa_longa_sem_evolucao_aparece_sem_excecao(self):
        empresa = _empresa("alerta-internacao@example.com")
        hoje = date.today()
        dep = DepartamentoHospital.objects.create(empresa=empresa, nome="Clinica")
        leito = LeitoHospital.objects.create(empresa=empresa, departamento=dep, numero="201", status="ocupado")
        paciente = PacienteHospital.objects.create(empresa=empresa, nome="Paciente X", sexo="M")
        internacao = InternacaoHospital.objects.create(
            empresa=empresa, paciente=paciente, leito=leito,
            diagnostico="Investigação", status="ativa",
        )
        internacao.data_entrada = timezone_now_minus_days(40)
        internacao.save(update_fields=["data_entrada"])

        alertas = _alertas_hospital(empresa, hoje)
        titulos = [a["titulo"] for a in alertas]
        self.assertIn("1 paciente(s) sem evolução clínica há 48h", titulos)
        self.assertIn("1 internação(ões) com mais de 30 dias", titulos)

    def test_internacao_com_evolucao_recente_nao_gera_alerta_de_evolucao(self):
        empresa = _empresa("alerta-internacao-evoluiu@example.com")
        hoje = date.today()
        dep = DepartamentoHospital.objects.create(empresa=empresa, nome="Clinica")
        leito = LeitoHospital.objects.create(empresa=empresa, departamento=dep, numero="202", status="ocupado")
        paciente = PacienteHospital.objects.create(empresa=empresa, nome="Paciente Y", sexo="F")
        internacao = InternacaoHospital.objects.create(
            empresa=empresa, paciente=paciente, leito=leito,
            diagnostico="Investigação", status="ativa",
        )
        EvolucaoClinica.objects.create(internacao=internacao, descricao="Estável", responsavel="Dr. X")

        alertas = _alertas_hospital(empresa, hoje)
        titulos = [a["titulo"] for a in alertas]
        self.assertNotIn("1 paciente(s) sem evolução clínica há 48h", titulos)


def timezone_now_minus_days(days):
    from django.utils import timezone
    return timezone.now() - timedelta(days=days)
