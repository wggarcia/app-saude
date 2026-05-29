"""
demo_setup  — reseta o banco local e cria 5 ambientes de demonstração limpos.

Uso:
  python manage.py demo_setup           # preview (não altera nada)
  python manage.py demo_setup --apply   # aplica todas as mudanças

Ambientes criados:
  1. SST          — demo.sst@soluscrt.com        / Demo@SST2026
  2. Farmácia     — demo.farmacia@soluscrt.com   / Demo@Farm2026
  3. Hospital     — demo.hospital@soluscrt.com   / Demo@Hosp2026
  4. Governo      — demo.governo@soluscrt.com    / Demo@Gov2026
  5. Plano Saúde  — demo.plano@soluscrt.com      / Demo@Plano2026

APP do trabalhador (SST):
  Funcionário Luiz Oliveira — luiz@app.local / Luiz@2026
"""

import datetime
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction


DEMO_SENHA_ADMIN = "Demo@SST2026"   # SST
DEMO_SENHA_FARM  = "Demo@Farm2026"
DEMO_SENHA_HOSP  = "Demo@Hosp2026"
DEMO_SENHA_GOV   = "Demo@Gov2026"
DEMO_SENHA_PLANO = "Demo@Plano2026"

HOJE = datetime.date.today()


class Command(BaseCommand):
    help = "Reseta o banco local e cria 5 ambientes de demonstração limpos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Reseta o banco local e cria os 5 demos do zero (uso local).",
        )
        parser.add_argument(
            "--upsert",
            action="store_true",
            help="Cria as contas demo se não existirem; ignora se já existirem (seguro em produção).",
        )

    def out(self, msg, style=None):
        if style:
            self.stdout.write(style(msg))
        else:
            self.stdout.write(msg)

    def handle(self, *args, **options):
        apply  = options["apply"]
        upsert = options["upsert"]

        if upsert:
            self.out(f"\n{'='*60}")
            self.out("  demo_setup --upsert  (produção — idempotente)")
            self.out(f"{'='*60}\n")
            with transaction.atomic():
                self._upsert_demos()
            return

        mode = "APLICANDO" if apply else "PREVIEW (use --apply para executar)"
        self.out(f"\n{'='*60}")
        self.out(f"  demo_setup — {mode}")
        self.out(f"{'='*60}\n")

        if apply:
            with transaction.atomic():
                self._limpar_banco()
                self._criar_demos()
        else:
            self._preview()

    # ─────────────────────────────────────────────────────────────────────────
    # PREVIEW
    # ─────────────────────────────────────────────────────────────────────────
    def _preview(self):
        from api.models import Empresa, EmpresaUsuario, FuncionarioSST, CredencialAppFuncionario
        self.out("O que será DELETADO:")
        self.out(f"  • {Empresa.objects.count()} empresas")
        self.out(f"  • {EmpresaUsuario.objects.count()} usuários admin")
        self.out(f"  • {FuncionarioSST.objects.count()} funcionários SST")
        self.out(f"  • {CredencialAppFuncionario.objects.count()} credenciais app")
        self.out("")
        self.out("O que será CRIADO:")
        self.out("  1. Demo SST            — demo.sst@soluscrt.com / Demo@SST2026")
        self.out("     └─ Usuário admin:     ti@demo-sst.com")
        self.out("     └─ 12 funcionários SST | 35 EPIs c/ CAs válidos | 7 riscos PGR")
        self.out("     └─ 6 pedidos de exame | CIPA ativa | 3 clínicas credenciadas")
        self.out("     └─ Documentos: PGR, PCMSO, LTCAT, PPP, Laudo Insalubridade")
        self.out("     └─ Postos de trabalho + EPCs | Treinamentos NR | Afastamentos")
        self.out("     └─ APP trabalhador: Luiz Oliveira luiz@app.local / Luiz@2026")
        self.out("     └─ APP trabalhador: Carlos Lima   carlos@app.local / Carlos@2026")
        self.out("  2. Demo Farmácia       — demo.farmacia@soluscrt.com / Demo@Farm2026")
        self.out("     └─ Usuário admin:     ti@demo-farmacia.com")
        self.out("  3. Demo Hospital       — demo.hospital@soluscrt.com / Demo@Hosp2026")
        self.out("     └─ Usuário admin:     ti@demo-hospital.com")
        self.out("  4. Demo Governo        — demo.governo@soluscrt.com / Demo@Gov2026")
        self.out("     └─ Usuário admin:     ti@demo-governo.com")
        self.out("  5. Demo Plano de Saúde — demo.plano@soluscrt.com / Demo@Plano2026")
        self.out("     └─ Usuário admin:     ti@demo-plano.com")
        self.out("")
        self.out("Execute com --apply para confirmar.", self.style.WARNING)

    # ─────────────────────────────────────────────────────────────────────────
    # LIMPEZA
    # ─────────────────────────────────────────────────────────────────────────
    def _limpar_banco(self):
        from django.apps import apps
        from django.db import connection

        self.out("► Limpando dados de desenvolvimento...", self.style.WARNING)

        # Desativa FKs temporariamente para truncate seguro
        with connection.cursor() as c:
            c.execute("PRAGMA foreign_keys = OFF;")

        # Modelos a limpar (exclui migrations e auth do Django)
        skip = {"django_migrations", "django_content_type", "auth_permission",
                "auth_group", "auth_group_permissions", "auth_user",
                "auth_user_groups", "auth_user_user_permissions"}

        deleted_total = 0
        for model in apps.get_app_config("api").get_models():
            table = model._meta.db_table
            if table in skip:
                continue
            try:
                cnt = model.objects.count()
                if cnt:
                    model.objects.all().delete()
                    deleted_total += cnt
            except Exception as e:
                self.out(f"  ⚠ Não deletou {model.__name__}: {e}")

        with connection.cursor() as c:
            c.execute("PRAGMA foreign_keys = ON;")

        self.out(f"  ✓ {deleted_total} registros removidos", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # CRIAÇÃO DE DEMOS
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_demos(self):
        self.out("\n► Criando ambientes demo...", self.style.MIGRATE_HEADING)
        e_sst    = self._criar_empresa_sst()
        e_farm   = self._criar_empresa_farmacia()
        e_hosp   = self._criar_empresa_hospital()
        e_gov    = self._criar_empresa_governo()
        e_plano  = self._criar_empresa_plano()

        self._criar_dados_sst(e_sst)
        self._criar_dados_farmacia(e_farm)
        self._criar_dados_hospital(e_hosp)
        self._criar_dados_governo(e_gov)
        self._criar_dados_plano(e_plano)

        self._recria_dono_saas()

        self.out("\n" + "="*60, self.style.SUCCESS)
        self.out("  ✅ Demo setup concluído!", self.style.SUCCESS)
        self.out("="*60 + "\n", self.style.SUCCESS)
        self._imprimir_resumo()

    # ─────────────────────────────────────────────────────────────────────────
    # UPSERT — idempotente, seguro em produção
    # ─────────────────────────────────────────────────────────────────────────
    def _upsert_demos(self):
        """Cria cada conta demo apenas se o e-mail ainda não existir no banco."""
        from api.models import Empresa

        demos = [
            ("demo.sst@soluscrt.com",     self._criar_empresa_sst,     self._criar_dados_sst),
            ("demo.farmacia@soluscrt.com", self._criar_empresa_farmacia, self._criar_dados_farmacia),
            ("demo.hospital@soluscrt.com", self._criar_empresa_hospital, self._criar_dados_hospital),
            ("demo.governo@soluscrt.com",  self._criar_empresa_governo,  self._criar_dados_governo),
            ("demo.plano@soluscrt.com",    self._criar_empresa_plano,    self._criar_dados_plano),
        ]

        criados = 0
        for email, criar_fn, dados_fn in demos:
            if Empresa.objects.filter(email=email).exists():
                self.out(f"  ↷  {email} já existe — ignorando")
            else:
                e = criar_fn()
                try:
                    with transaction.atomic():
                        dados_fn(e)
                except Exception as exc:
                    self.out(f"  ⚠ dados demo para {email} falharam (parcial): {exc}", self.style.WARNING)
                self.out(f"  ✅ {email} criado", self.style.SUCCESS)
                criados += 1

        self._recria_dono_saas()

        self.out(f"\n  {criados} conta(s) demo criada(s). ✅\n", self.style.SUCCESS)

    # ── Empresa SST ──────────────────────────────────────────────────────────
    def _criar_empresa_sst(self):
        from api.models import Empresa, EmpresaUsuario
        from api.planos import pacote_padrao, detalhes_pacote
        pkg = "sst_enterprise_10"
        try:
            det = detalhes_pacote(pkg)
        except Exception:
            pkg = pacote_padrao()
            det = detalhes_pacote(pkg)

        e = Empresa.objects.create(
            nome="SolusCRT Demo SST",
            email="demo.sst@soluscrt.com",
            senha=make_password(DEMO_SENHA_ADMIN),
            tipo_conta=Empresa.TIPO_EMPRESA,
            acesso_governo=False,
            pacote_codigo=pkg,
            plano="anual",
            ativo=True,
            max_dispositivos=det.get("dispositivos", 50),
            max_usuarios=det.get("usuarios", 10),
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="TI Demo SST",
            email="ti@demo-sst.com",
            senha=make_password("Ti@Demo2026"),
            cargo="TI", ativo=True, is_admin=True,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="RH Demo SST",
            email="rh@demo-sst.com",
            senha=make_password("Rh@Demo2026"),
            cargo="RH", ativo=True, is_admin=False,
        )
        self.out(f"  ✓ SST: {e.nome} (id={e.id})", self.style.SUCCESS)
        return e

    # ── Empresa Farmácia ─────────────────────────────────────────────────────
    def _criar_empresa_farmacia(self):
        from api.models import Empresa, EmpresaUsuario
        from api.planos import detalhes_pacote
        pkg = "farmacia_rede_regional"
        try:
            det = detalhes_pacote(pkg)
        except Exception:
            det = {"dispositivos": 20, "usuarios": 5}

        e = Empresa.objects.create(
            nome="SolusCRT Demo Farmácia",
            email="demo.farmacia@soluscrt.com",
            senha=make_password(DEMO_SENHA_FARM),
            tipo_conta=Empresa.TIPO_EMPRESA,
            acesso_governo=False,
            pacote_codigo=pkg,
            plano="anual",
            ativo=True,
            max_dispositivos=det.get("dispositivos", 20),
            max_usuarios=det.get("usuarios", 5),
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="TI Demo Farmácia",
            email="ti@demo-farmacia.com",
            senha=make_password("Ti@Demo2026"),
            cargo="TI", ativo=True, is_admin=True,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Gestor Demo Farmácia",
            email="gestor@demo-farmacia.com",
            senha=make_password("Gest@Demo2026"),
            cargo="Gestor", ativo=True, is_admin=False,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Farmacêutico Demo",
            email="farm@demo-farmacia.com",
            senha=make_password("Farm@Demo2026"),
            cargo="Farmacêutico", ativo=True, is_admin=False,
        )
        self.out(f"  ✓ Farmácia: {e.nome} (id={e.id})", self.style.SUCCESS)
        return e

    # ── Empresa Hospital ─────────────────────────────────────────────────────
    def _criar_empresa_hospital(self):
        from api.models import Empresa, EmpresaUsuario
        from api.planos import detalhes_pacote
        pkg = "hospital_medio"
        try:
            det = detalhes_pacote(pkg)
        except Exception:
            det = {"dispositivos": 100, "usuarios": 20}

        e = Empresa.objects.create(
            nome="SolusCRT Demo Hospital",
            email="demo.hospital@soluscrt.com",
            senha=make_password(DEMO_SENHA_HOSP),
            tipo_conta=Empresa.TIPO_EMPRESA,
            acesso_governo=False,
            pacote_codigo=pkg,
            plano="anual",
            ativo=True,
            max_dispositivos=det.get("dispositivos", 100),
            max_usuarios=det.get("usuarios", 20),
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="TI Demo Hospital",
            email="ti@demo-hospital.com",
            senha=make_password("Ti@Demo2026"),
            cargo="TI", ativo=True, is_admin=True,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Diretora Médica Demo",
            email="diretora@demo-hospital.com",
            senha=make_password("Dir@Demo2026"),
            cargo="Diretora Médica", ativo=True, is_admin=False,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Enfermeira Chefe Demo",
            email="enfermagem@demo-hospital.com",
            senha=make_password("Enf@Demo2026"),
            cargo="Enfermagem", ativo=True, is_admin=False,
        )
        self.out(f"  ✓ Hospital: {e.nome} (id={e.id})", self.style.SUCCESS)
        return e

    # ── Empresa Governo ──────────────────────────────────────────────────────
    def _criar_empresa_governo(self):
        from api.models import Empresa, EmpresaUsuario
        from api.planos import pacote_governo_padrao, detalhes_pacote
        pkg = pacote_governo_padrao()
        try:
            det = detalhes_pacote(pkg)
        except Exception:
            det = {"dispositivos": 200, "usuarios": 50}

        e = Empresa.objects.create(
            nome="SolusCRT Demo Governo",
            email="demo.governo@soluscrt.com",
            senha=make_password(DEMO_SENHA_GOV),
            tipo_conta=Empresa.TIPO_GOVERNO,
            acesso_governo=True,
            pacote_codigo=pkg,
            plano="anual",
            ativo=True,
            max_dispositivos=det.get("dispositivos", 200),
            max_usuarios=det.get("usuarios", 50),
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="TI Demo Governo",
            email="ti@demo-governo.com",
            senha=make_password("Ti@Demo2026"),
            cargo="TI", ativo=True, is_admin=True,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Secretário de Saúde Demo",
            email="secretario@demo-governo.com",
            senha=make_password("Sec@Demo2026"),
            cargo="Secretário de Saúde", ativo=True, is_admin=False,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Epidemiologista Demo",
            email="epidemio@demo-governo.com",
            senha=make_password("Epid@Demo2026"),
            cargo="Epidemiologista", ativo=True, is_admin=False,
        )
        self.out(f"  ✓ Governo: {e.nome} (id={e.id})", self.style.SUCCESS)
        return e

    # ── Empresa Plano de Saúde ───────────────────────────────────────────────
    def _criar_empresa_plano(self):
        from api.models import Empresa, EmpresaUsuario
        from api.planos import detalhes_pacote
        pkg = "plano_saude_operadora"
        try:
            det = detalhes_pacote(pkg)
        except Exception:
            det = {"dispositivos": 50, "usuarios": 15}

        e = Empresa.objects.create(
            nome="SolusCRT Demo Plano de Saúde",
            email="demo.plano@soluscrt.com",
            senha=make_password(DEMO_SENHA_PLANO),
            tipo_conta=Empresa.TIPO_EMPRESA,
            acesso_governo=False,
            pacote_codigo=pkg,
            plano="anual",
            ativo=True,
            max_dispositivos=det.get("dispositivos", 50),
            max_usuarios=det.get("usuarios", 15),
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="TI Demo Plano",
            email="ti@demo-plano.com",
            senha=make_password("Ti@Demo2026"),
            cargo="TI", ativo=True, is_admin=True,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Diretor Comercial Demo",
            email="comercial@demo-plano.com",
            senha=make_password("Com@Demo2026"),
            cargo="Diretor Comercial", ativo=True, is_admin=False,
        )
        EmpresaUsuario.objects.create(
            empresa=e, nome="Analista de Benefícios Demo",
            email="beneficios@demo-plano.com",
            senha=make_password("Ben@Demo2026"),
            cargo="Analista de Benefícios", ativo=True, is_admin=False,
        )
        self.out(f"  ✓ Plano de Saúde: {e.nome} (id={e.id})", self.style.SUCCESS)
        return e

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — SST
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_sst(self, empresa):  # noqa: C901
        from api.models import (
            FuncionarioSST, CredencialAppFuncionario,
            ASOOcupacional, ExameOcupacional,
            TreinamentoNR, EntregaEPI, EPIItem,
            AfastamentoSST, NotificacaoFuncionario, CheckinBemEstar,
            SolicitacaoExame, DocumentoSST,
            RiscoOcupacional, PostoTrabalho, AgenteNocivoPostoTrabalho,
            FuncionarioPostoTrabalho,
            VinculoClinicaEmpresa, ClinicaCredenciada,
            ComissaoCIPA, MembroCIPA, ReuniaoCIPA, ParticipanteReuniaoCIPA,
            ConfiguracaoSST,
        )
        import json as _json

        # ── 1. Configuração SST da empresa ───────────────────────────────────
        try:
            with transaction.atomic():
                ConfiguracaoSST.objects.update_or_create(
                    empresa=empresa,
                    defaults=dict(
                        nome_medico_coordenador="Dra. Patricia Nunes Costa",
                        crm_medico="CRM/SP 34872",
                        especialidade_medico="Medicina do Trabalho",
                        nome_engenheiro="Eng. Marcos Andrade",
                        crea_engenheiro="CREA/SP 987654",
                        nome_tecnico="Luiz Oliveira",
                        registro_tecnico="TRT/SP 54321",
                        cnpj="12.345.678/0001-95",
                        cnae_principal="2512-8/00 — Fabricação de esquadrias de metal",
                        grau_risco="3",
                        numero_funcionarios=12,
                        endereco_completo="Av. Industrial, 1500 — Distrito Industrial — São Paulo/SP — CEP 04000-000",
                        alerta_aso_dias=30,
                        alerta_treinamento_dias=45,
                        email_alertas="sst@demo-sst.com",
                        alertas_ativos=True,
                    ),
                )
        except Exception as ex:
            self.out(f"     ⚠ ConfiguracaoSST parcial: {ex}")

        # ── 2. Funcionários ──────────────────────────────────────────────────
        funcionarios_data = [
            dict(nome="Luiz Oliveira",         cpf="111.222.333-44", matricula="L-0042",
                 cargo="Técnico de Segurança do Trabalho", setor="Produção",
                 sexo="M", data_nascimento=datetime.date(1990, 3, 15),
                 data_admissao=datetime.date(2022, 1, 10)),
            dict(nome="Ana Paula Ferreira",     cpf="222.333.444-55", matricula="L-0015",
                 cargo="Enfermeira Ocupacional", setor="Saúde",
                 sexo="F", data_nascimento=datetime.date(1988, 7, 22),
                 data_admissao=datetime.date(2021, 3, 5)),
            dict(nome="Carlos Alberto Lima",    cpf="333.444.555-66", matricula="L-0023",
                 cargo="Operador de Produção", setor="Produção",
                 sexo="M", data_nascimento=datetime.date(1993, 11, 8),
                 data_admissao=datetime.date(2023, 6, 1)),
            dict(nome="Fernanda Costa Silva",   cpf="444.555.666-77", matricula="L-0031",
                 cargo="Supervisora de Linha", setor="Produção",
                 sexo="F", data_nascimento=datetime.date(1985, 4, 17),
                 data_admissao=datetime.date(2019, 8, 15)),
            dict(nome="Diego Rocha Santos",     cpf="555.666.777-88", matricula="L-0038",
                 cargo="Eletricista Industrial", setor="Manutenção",
                 sexo="M", data_nascimento=datetime.date(1991, 9, 3),
                 data_admissao=datetime.date(2020, 2, 20)),
            dict(nome="Beatriz Mendes Alves",   cpf="666.777.888-99", matricula="L-0044",
                 cargo="Auxiliar Administrativo", setor="Administrativo",
                 sexo="F", data_nascimento=datetime.date(1997, 1, 28),
                 data_admissao=datetime.date(2024, 1, 8)),
            dict(nome="Rodrigo Pereira Cunha",  cpf="777.888.999-00", matricula="L-0051",
                 cargo="Soldador", setor="Produção",
                 sexo="M", data_nascimento=datetime.date(1987, 6, 12),
                 data_admissao=datetime.date(2018, 9, 3)),
            dict(nome="Mariana Sousa Lima",     cpf="888.999.000-11", matricula="L-0056",
                 cargo="Analista de RH", setor="Recursos Humanos",
                 sexo="F", data_nascimento=datetime.date(1994, 3, 21),
                 data_admissao=datetime.date(2022, 7, 11)),
            dict(nome="José Carlos Barros",     cpf="999.000.111-22", matricula="L-0061",
                 cargo="Motorista Operacional", setor="Logística",
                 sexo="M", data_nascimento=datetime.date(1975, 10, 5),
                 data_admissao=datetime.date(2016, 4, 18)),
            dict(nome="Patricia Nunes Costa",   cpf="000.111.222-33", matricula="L-0010",
                 cargo="Médica do Trabalho", setor="Saúde",
                 sexo="F", data_nascimento=datetime.date(1982, 8, 30),
                 data_admissao=datetime.date(2017, 2, 1)),
            dict(nome="Alexandre Silva Melo",   cpf="011.122.233-44", matricula="L-0067",
                 cargo="Operador de Empilhadeira", setor="Almoxarifado",
                 sexo="M", data_nascimento=datetime.date(1989, 12, 17),
                 data_admissao=datetime.date(2021, 11, 22)),
            dict(nome="Cristiane Alves Torres", cpf="122.233.344-55", matricula="L-0072",
                 cargo="Técnica de Enfermagem", setor="Saúde",
                 sexo="F", data_nascimento=datetime.date(1996, 5, 8),
                 data_admissao=datetime.date(2023, 3, 15)),
        ]

        func_objs = []
        for fd in funcionarios_data:
            try:
                f = FuncionarioSST.objects.create(empresa=empresa, ativo=True, **fd)
                func_objs.append(f)
            except Exception:
                pass

        if not func_objs:
            self.out(f"     ⚠ Nenhum funcionário criado", self.style.WARNING)
            return

        luiz     = func_objs[0]
        ana      = func_objs[1]
        carlos   = func_objs[2]
        fernanda = func_objs[3]
        diego    = func_objs[4]
        beatriz  = func_objs[5]
        rodrigo  = func_objs[6] if len(func_objs) > 6 else luiz
        mariana  = func_objs[7] if len(func_objs) > 7 else luiz
        jose     = func_objs[8] if len(func_objs) > 8 else luiz
        patricia = func_objs[9] if len(func_objs) > 9 else luiz
        alex     = func_objs[10] if len(func_objs) > 10 else luiz
        cris     = func_objs[11] if len(func_objs) > 11 else luiz

        # Credenciais APP
        try:
            CredencialAppFuncionario.objects.create(
                funcionario=luiz, email="luiz@app.local",
                senha=make_password("Luiz@2026"), ativo=True,
            )
            CredencialAppFuncionario.objects.create(
                funcionario=carlos, email="carlos@app.local",
                senha=make_password("Carlos@2026"), ativo=True,
            )
        except Exception:
            pass

        # ── 3. ASOs ──────────────────────────────────────────────────────────
        asos_data = [
            (luiz,     "periodico",       "apto",          datetime.date(2026, 3, 29), datetime.date(2027, 3, 29),
             "Audiometria, Hemograma, Glicemia, Acuidade Visual"),
            (ana,      "admissional",      "apto",          datetime.date(2021, 3, 4),  datetime.date(2026, 3, 4),
             "Hemograma, Sorologia Hepatite B, VDRL"),
            (carlos,   "periodico",       "apto",          datetime.date(2025, 12, 10), datetime.date(2026, 12, 10),
             "Audiometria, Espirometria, Hemograma"),
            (fernanda, "periodico",       "apto_restricao", datetime.date(2025, 8, 15), datetime.date(2026, 8, 15),
             "Audiometria, Avaliação Ergonômica, ECG"),
            (diego,    "periodico",       "apto",          datetime.date(2026, 2, 18), datetime.date(2027, 2, 18),
             "Audiometria, Acuidade Visual, Hemograma, Glicemia"),
            (rodrigo,  "periodico",       "apto",          datetime.date(2025, 10, 5), datetime.date(2026, 10, 5),
             "Audiometria, Espirometria, Hemograma, Raio-X Tórax"),
            (jose,     "periodico",       "apto",          datetime.date(2025, 11, 20), datetime.date(2026, 11, 20),
             "Hemograma, ECG, Acuidade Visual, Toxicológico"),
            (beatriz,  "demissional",     "apto",          datetime.date(2026, 4, 30), None,
             "Hemograma, Glicemia, Acuidade Visual"),
            (alex,     "retorno_trabalho", "apto",         datetime.date(2026, 3, 10), datetime.date(2027, 3, 10),
             "Hemograma, Radiografia Lombar"),
            (patricia, "admissional",     "apto",          datetime.date(2017, 2, 1),  datetime.date(2022, 2, 1),
             "Hemograma, Sorologia Hepatite B, VDRL, Toxicológico"),
        ]
        aso_objs = {}
        for func, tipo, resultado, emissao, validade, riscos in asos_data:
            try:
                a = ASOOcupacional.objects.create(
                    empresa=empresa, funcionario=func,
                    tipo=tipo, resultado=resultado,
                    data_emissao=emissao, data_validade=validade,
                    medico_responsavel="Dra. Patricia Nunes Costa",
                    crm="CRM/SP 34872",
                    riscos_ocupacionais=riscos,
                    restricoes="Evitar trabalho em altura > 2 m" if resultado == "apto_restricao" else "",
                )
                aso_objs[func.id] = a
            except Exception:
                pass

        # Exames vinculados ao ASO do Luiz
        try:
            aso_luiz = aso_objs.get(luiz.id)
            if aso_luiz:
                exames_luiz = [
                    ("audiometria",    "realizado", "Normal — limiar auditivo dentro dos padrões",   datetime.date(2026, 3, 29), datetime.date(2027, 3, 29)),
                    ("acuidade_visual","realizado", "20/20 binocular — dentro do padrão",            datetime.date(2026, 3, 29), datetime.date(2027, 3, 29)),
                    ("laboratorial",   "realizado", "Hemograma: normal / Glicemia: 92 mg/dL",        datetime.date(2026, 3, 29), datetime.date(2027, 3, 29)),
                ]
                for tipo_ex, status_ex, resultado_ex, realiz, valid_ex in exames_luiz:
                    ExameOcupacional.objects.create(
                        empresa=empresa, funcionario=luiz, aso=aso_luiz,
                        tipo_exame=tipo_ex, status=status_ex, resultado=resultado_ex,
                        data_realizacao=realiz, data_validade=valid_ex,
                    )
        except Exception:
            pass

        # ── 4. Treinamentos NR ───────────────────────────────────────────────
        treinamentos = [
            # (funcionario, nr, titulo, horas, realizado, validade, status)
            (luiz,   "NR-10", "Segurança em Instalações e Serviços em Eletricidade", 40,
             datetime.date(2025, 5, 23), datetime.date(2026, 5, 23), "vencido"),
            (luiz,   "NR-35", "Trabalho em Altura", 8,
             datetime.date(2025, 12, 14), datetime.date(2026, 12, 14), "valido"),
            (luiz,   "NR-6",  "Utilização e Conservação de EPIs", 4,
             datetime.date(2025, 6, 10), datetime.date(2027, 6, 10), "valido"),
            (luiz,   "NR-5",  "CIPA — Comissão Interna de Prevenção de Acidentes", 8,
             datetime.date(2024, 11, 8), datetime.date(2026, 11, 8), "valido"),
            (diego,  "NR-10", "Segurança em Instalações e Serviços em Eletricidade", 40,
             datetime.date(2026, 1, 15), datetime.date(2027, 1, 15), "valido"),
            (diego,  "NR-35", "Trabalho em Altura", 8,
             datetime.date(2025, 9, 22), datetime.date(2026, 9, 22), "valido"),
            (rodrigo,"NR-6",  "Utilização e Conservação de EPIs", 4,
             datetime.date(2025, 4, 5), datetime.date(2027, 4, 5), "valido"),
            (rodrigo,"NR-12", "Segurança no Trabalho em Máquinas e Equipamentos", 8,
             datetime.date(2025, 2, 18), datetime.date(2026, 2, 18), "vencido"),
            (carlos, "NR-12", "Segurança no Trabalho em Máquinas e Equipamentos", 8,
             datetime.date(2026, 2, 10), datetime.date(2027, 2, 10), "valido"),
            (carlos, "NR-6",  "Utilização e Conservação de EPIs", 4,
             datetime.date(2025, 8, 14), datetime.date(2027, 8, 14), "valido"),
            (alex,   "NR-11", "Transporte, Movimentação, Armazenagem e Manuseio de Materiais", 8,
             datetime.date(2025, 7, 3), datetime.date(2026, 7, 3), "valido"),
            (jose,   "NR-33", "Segurança e Saúde nos Trabalhos em Espaços Confinados", 16,
             datetime.date(2024, 10, 10), datetime.date(2026, 10, 10), "valido"),
            (fernanda,"NR-5", "CIPA — Comissão Interna de Prevenção de Acidentes", 8,
             datetime.date(2024, 11, 8), datetime.date(2026, 11, 8), "valido"),
        ]
        for func, nr, titulo, horas, realiz, valid_t, status_t in treinamentos:
            try:
                TreinamentoNR.objects.create(
                    empresa=empresa, funcionario=func,
                    nr=nr, titulo=titulo,
                    carga_horaria=horas,
                    data_realizacao=realiz, data_validade=valid_t,
                    status=status_t,
                    instrutor="SolusCRT Treinamentos Ltda",
                )
            except Exception:
                pass

        # ── 5. Catálogo EPI completo (35 itens) ─────────────────────────────
        # (nome, tipo, ca_numero, validade_ca, fornecedor, descricao)
        catalogo_epi = [
            # Proteção Auditiva
            ("Protetor Auditivo de Inserção Espuma 3M 1100",   "auditiva",    "22347",
             datetime.date(2027, 8, 31),  "3M Brasil",
             "Espuma de PU, NRRsf 27 dB, descartável, embalagem individual"),
            ("Protetor Auditivo de Inserção Silicone Kalipso", "auditiva",    "15243",
             datetime.date(2028, 3, 15),  "Kalipso Ind. Com.",
             "Silicone reutilizável, NRRsf 23 dB, com cordão"),
            ("Protetor Auditivo Tipo Concha SNR 29 dB",        "auditiva",    "14477",
             datetime.date(2027, 12, 31), "Centurion Safety",
             "Concha binaural, NRRsf 29 dB, ajuste de arco"),
            # Proteção Respiratória
            ("Respirador Descartável PFF2 N95 s/ Válvula",     "respiratoria","38503",
             datetime.date(2028, 6, 30),  "3M Brasil",
             "Filtro PFF2, eficiência ≥ 94%, partículas sólidas e líquidas"),
            ("Respirador Descartável PFF3 c/ Válvula",         "respiratoria","15717",
             datetime.date(2027, 4, 30),  "Moldex do Brasil",
             "Filtro PFF3, eficiência ≥ 99%, válvula de exalação"),
            ("Respirador Semifacial Reutilizável c/ Filtro A2P3","respiratoria","24932",
             datetime.date(2028, 12, 31), "3M Brasil",
             "Meia face, par de filtros A2P3 incluso, silicone premium"),
            ("Respirador Quartos de Face para Névoas Ácidas",  "respiratoria","31854",
             datetime.date(2027, 9, 30),  "MSA do Brasil",
             "Silicone, filtro B2E2P3, para névoas de ácidos e vapores orgânicos"),
            # Proteção Visual
            ("Óculos de Proteção Ampla Visão Incolor",         "visual",      "15943",
             datetime.date(2027, 9, 30),  "Uvex do Brasil",
             "Policarbonato, antirisco, antiembaçante, vedação espuma"),
            ("Óculos de Segurança Lente Incolor Steelflex",    "visual",      "13071",
             datetime.date(2028, 1, 31),  "Steelflex Safety",
             "Haste ajustável, impacto médio, CA ABNT NBR 14380"),
            ("Protetor Facial de Policarbonato 20 cm",         "visual",      "14910",
             datetime.date(2027, 6, 30),  "3M Brasil",
             "Visor 20 cm, suporte catraca, resistente a respingos e partículas"),
            ("Óculos de Solda Oxiacetilênica Escuro #5",       "visual",      "10346",
             datetime.date(2027, 11, 30), "Carbografite",
             "Lentes DIN 5, solda oxiacetilênica e brasagem"),
            # Proteção de Mãos
            ("Luva de Látex Pigmentada Antiderrapante",        "maos",        "11297",
             datetime.date(2026, 10, 31), "Danny Ind. Ltda",
             "Látex natural, palma rugosa, punho longo, tam. M/G/GG"),
            ("Luva de PVC Cano Médio 33 cm",                   "maos",        "12020",
             datetime.date(2027, 3, 31),  "Volk Industrial",
             "PVC, resistente a produtos químicos ácidos e álcalis, cano 33 cm"),
            ("Luva de Raspa de Couro Cano Curto",              "maos",        "13026",
             datetime.date(2028, 2, 28),  "Capivaseg EPIs",
             "Raspa bovino, proteção contra cortes e calor moderado"),
            ("Luva de Nitrila Azul Descartável sem Pó",        "maos",        "26691",
             datetime.date(2027, 8, 31),  "Supermax Healthcare",
             "Nitrila 0,10 mm, sem pó, antialérgica, cx 100 un."),
            ("Luva de Malha de Aço Anticorte Nível 5",         "maos",        "34561",
             datetime.date(2028, 5, 31),  "Steelgrip Brasil",
             "Malha de aço inox, nível 5 de resistência a cortes"),
            ("Luva de Couro Flor para Solda MIG/MAG",         "maos",        "16890",
             datetime.date(2027, 10, 31), "Kalipso Ind. Com.",
             "Couro flor c/ capuz, proteção contra respingos de solda"),
            ("Luva de Borracha Isolante Elétrica Classe 0",    "maos",        "32741",
             datetime.date(2027, 6, 30),  "Honeywell Brasil",
             "Borracha natural, classe 0 (1.000 V CA), inspeção semestral"),
            # Proteção de Pés
            ("Sapato de Segurança Couro c/ Bico de Aço",      "pes",         "11697",
             datetime.date(2027, 5, 31),  "Marluvas Calçados",
             "Couro bovino, bico aço, solado antiderrapante bifásico, CA vigente"),
            ("Bota de Borracha PVC Bicolor Cano 28 cm",       "pes",         "26694",
             datetime.date(2028, 8, 31),  "Bracol Safety",
             "PVC bicolor, cano 28 cm, bico de aço, antiderrapante, NR-10"),
            ("Bota de Segurança Impermeável c/ Bico Composite","pes",         "17254",
             datetime.date(2027, 12, 31), "Marluvas Calçados",
             "Couro hidrofugado, bico composite, solado antifuro aço"),
            ("Sapato Antiestático ESD (NR-10)",                "pes",         "32450",
             datetime.date(2028, 4, 30),  "Protefort Calçados",
             "Solado ESD, resistência 10⁶–10⁸ Ω, certificado NR-10"),
            ("Bota de Borracha para Ambientes Molhados",       "pes",         "41128",
             datetime.date(2028, 2, 28),  "Volk Industrial",
             "Borracha natural, impermeável, antiderrapante, sem bico metálico"),
            # Proteção de Cabeça
            ("Capacete de Segurança ABS Aba Total Classe A",   "cabeca",      "31469",
             datetime.date(2028, 9, 30),  "Planat Proteções",
             "ABS, aba completa, classe A (baixa tensão), suspenção 8 pontos"),
            ("Capacete de Segurança PEAD Classe B c/ Jugular", "cabeca",      "17248",
             datetime.date(2027, 7, 31),  "Vonder Ferramentas",
             "PEAD, jugular 4 pontos, classe B (alta tensão até 20 kV)"),
            ("Touca Balaclava Retardante à Chama Modacrilico", "cabeca",      "38901",
             datetime.date(2028, 3, 31),  "Brascamp Proteções",
             "Viscose/Modacrilico, protege pescoço e face de faíscas e respingos"),
            # Proteção Contra Quedas
            ("Cinto de Segurança Tipo Paraquedista 5 Pontos",  "altura",      "25261",
             datetime.date(2027, 11, 30), "Pioner Equipamentos",
             "Trava dupla, 5 pontos de ancoragem, conforme ABNT NBR 14626"),
            ("Talabarte em Y c/ Absorvedor de Energia 1,80 m", "altura",      "21026",
             datetime.date(2028, 6, 30),  "MSA do Brasil",
             "Duplo, absorvedor, 1,80 m cada perna, gancho triplo-trava"),
            ("Trava-quedas Deslizante para Cabo de Aço 8–16 mm","altura",     "36114",
             datetime.date(2027, 8, 31),  "Pioner Equipamentos",
             "Inercial, cabos 8–16 mm, retração automática em queda"),
            ("Linha de Vida Retrátil 15 m Carcaça Alumínio",   "altura",      "28742",
             datetime.date(2028, 2, 28),  "MSA do Brasil",
             "Cabo de aço inox 5 mm, carcaça alumínio, indicador de choque"),
            # Proteção do Corpo
            ("Avental de Raspa de Couro para Solda",           "corpo",       "30012",
             datetime.date(2027, 9, 30),  "Capivaseg EPIs",
             "Raspa bovino 3 mm, protege tronco/pernas de respingos e faíscas"),
            ("Jaleco de PVC Impermeável Cano Longo c/ Capuz",  "corpo",       "27891",
             datetime.date(2028, 1, 31),  "Volk Industrial",
             "PVC flexível, resistente a ácidos e álcalis, capuz removível"),
            ("Roupa de Proteção Retardante à Chama (FR) 8 cal","corpo",       "39201",
             datetime.date(2028, 11, 30), "Brascamp Proteções",
             "Algodão FR 100%, 8 cal/cm² arc flash, NR-10/NR-16"),
            ("Colete Refletivo Classe II Alta Visibilidade",   "corpo",       "41003",
             datetime.date(2027, 6, 30),  "Plastcor Proteções",
             "Poliéster, 3 faixas retrorrefletivas, visibilidade noturna"),
            # Outro
            ("Detector de Gás Portátil 4 em 1 (O₂/LEL/CO/H₂S)","outro",    "35124",
             datetime.date(2028, 5, 31),  "Honeywell Brasil",
             "O₂, LEL, CO, H₂S; alarme sonoro/visual/vibratório, IP65"),
        ]

        epi_objs = {}
        for nome_e, tipo_e, ca_e, val_ca, forn_e, desc_e in catalogo_epi:
            try:
                epi = EPIItem.objects.create(
                    empresa=empresa, nome=nome_e, tipo=tipo_e,
                    ca_numero=ca_e, validade_ca=val_ca,
                    fornecedor=forn_e, descricao=desc_e, ativo=True,
                )
                epi_objs[nome_e] = epi
            except Exception:
                pass

        # ── 6. Entregas de EPI ───────────────────────────────────────────────
        entregas = [
            # (funcionario, epi_nome, data, qntd, observacoes)
            (luiz,    "Protetor Auditivo de Inserção Espuma 3M 1100",    datetime.date(2026, 3, 1),  5,  "Kit inicial de segurança"),
            (luiz,    "Óculos de Proteção Ampla Visão Incolor",          datetime.date(2026, 3, 1),  1,  ""),
            (luiz,    "Capacete de Segurança ABS Aba Total Classe A",    datetime.date(2026, 3, 1),  1,  ""),
            (luiz,    "Bota de Borracha PVC Bicolor Cano 28 cm",         datetime.date(2026, 3, 1),  1,  ""),
            (luiz,    "Cinto de Segurança Tipo Paraquedista 5 Pontos",   datetime.date(2026, 5, 18), 1,  "Trocado por desgaste"),
            (carlos,  "Protetor Auditivo de Inserção Espuma 3M 1100",    datetime.date(2026, 4, 10), 10, "Reposição mensal"),
            (carlos,  "Óculos de Segurança Lente Incolor Steelflex",     datetime.date(2026, 4, 10), 1,  ""),
            (carlos,  "Luva de Raspa de Couro Cano Curto",               datetime.date(2026, 4, 10), 2,  ""),
            (carlos,  "Sapato de Segurança Couro c/ Bico de Aço",        datetime.date(2026, 4, 10), 1,  ""),
            (diego,   "Luva de Borracha Isolante Elétrica Classe 0",     datetime.date(2026, 2, 20), 1,  "Obrigatório NR-10"),
            (diego,   "Capacete de Segurança PEAD Classe B c/ Jugular",  datetime.date(2026, 2, 20), 1,  "Classe B — eletricista"),
            (diego,   "Sapato Antiestático ESD (NR-10)",                 datetime.date(2026, 2, 20), 1,  "Obrigatório NR-10"),
            (rodrigo, "Luva de Couro Flor para Solda MIG/MAG",          datetime.date(2026, 1, 15), 2,  ""),
            (rodrigo, "Avental de Raspa de Couro para Solda",            datetime.date(2026, 1, 15), 1,  ""),
            (rodrigo, "Óculos de Solda Oxiacetilênica Escuro #5",        datetime.date(2026, 1, 15), 1,  ""),
            (rodrigo, "Roupa de Proteção Retardante à Chama (FR) 8 cal", datetime.date(2026, 1, 15), 1,  ""),
            (jose,    "Colete Refletivo Classe II Alta Visibilidade",    datetime.date(2026, 3, 5),  1,  "Logística — NR-21"),
            (alex,    "Capacete de Segurança ABS Aba Total Classe A",    datetime.date(2026, 4, 22), 1,  ""),
            (alex,    "Bota de Borracha PVC Bicolor Cano 28 cm",         datetime.date(2026, 4, 22), 1,  ""),
            (fernanda,"Óculos de Proteção Ampla Visão Incolor",          datetime.date(2026, 5, 10), 1,  "Supervisão de linha"),
        ]
        for func, epi_nome, dt, qtd, obs in entregas:
            epi_item = epi_objs.get(epi_nome)
            if not epi_item:
                continue
            try:
                EntregaEPI.objects.create(
                    empresa=empresa, funcionario=func, epi=epi_item,
                    data_entrega=dt, quantidade=qtd, observacoes=obs,
                )
            except Exception:
                pass

        # ── 7. Postos de Trabalho + Agentes Nocivos (EPCs) ──────────────────
        postos = [
            ("Operador de Produção — Linha A",    "Produção",
             "Operação de prensas hidráulicas, linha de montagem mecânica",
             "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2025, 6, 1), "2025-06"),
            ("Eletricista Industrial — Manutenção","Manutenção",
             "Manutenção preventiva e corretiva de painéis elétricos",
             "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2025, 6, 1), "2025-06"),
            ("Soldador — Produção",                "Produção",
             "Soldagem MIG/MAG e TIG de estruturas metálicas",
             "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2025, 6, 1), "2025-06"),
            ("Motorista Operacional — Logística",  "Logística",
             "Condução de veículos de carga até 3,5 t, entregas internas",
             "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2025, 6, 1), "2025-06"),
        ]
        posto_objs = []
        for nome_p, setor_p, desc_p, resp_p, reg_p, dt_laudo, vig in postos:
            try:
                p = PostoTrabalho.objects.create(
                    empresa=empresa, nome=nome_p, setor=setor_p, descricao=desc_p,
                    responsavel_tecnico=resp_p, responsavel_registro=reg_p,
                    data_laudo=dt_laudo, vigencia_inicio=vig, ativo=True,
                )
                posto_objs.append(p)
            except Exception:
                posto_objs.append(None)

        # Agentes nocivos (EPCs incluídos na descrição)
        agentes_por_posto = [
            # Posto 0 — Operador de Produção
            [("fisico", "01.01.001", "Ruído contínuo de prensas hidráulicas — 87 dB(A)",
              "Sonômetro calibrado ABNT NBR ISO 9612", "87 dB(A)", "85 dB(A) — NR-15",
              "Enclausuramento acústico da prensa; antepara de absorção sonora instalada", True,
              "Protetor Auditivo de Inserção Espuma 3M 1100 (CA 22347)", "22347", True),
             ("ergonomico", "01.01.002", "Postura inadequada em linha de montagem",
              "Análise ergonômica conforme NR-17", "RULA = 6", "RULA ≤ 3",
              "Mesa regulável em altura; tapete antifadiga instalado", False,
              "Não aplicável — EPC preferencial", "", False)],
            # Posto 1 — Eletricista
            [("fisico", "01.04.001", "Risco de choque elétrico em painéis de média tensão",
              "Mapeamento de risco NR-10", "13,8 kV", "≤ 1.000 V c/ luvas classe 0",
              "Bloqueio / sinalização LOTO; proteção dielétrica nos painéis", True,
              "Luva de Borracha Isolante Elétrica Classe 0 (CA 32741)", "32741", True)],
            # Posto 2 — Soldador
            [("quimico", "02.01.011", "Fumos metálicos de soldagem MIG/MAG",
              "Coleta gravimétrica NIOSH 0500", "2,1 mg/m³", "1,0 mg/m³ — NR-15",
              "Exaustor localizado (LEV) na bancada de solda; ventilação geral diluidora", True,
              "Respirador Semifacial Reutilizável c/ Filtro A2P3 (CA 24932)", "24932", True),
             ("fisico", "01.04.001", "Radiação ultravioleta do arco elétrico",
              "Dosimetria de UV ACGIH TLV", "Exposto", "TLV-ACGIH",
              "Biombo de proteção ao redor da bancada; cortina de solda instalada", True,
              "Óculos de Solda Oxiacetilênica Escuro #5 (CA 10346); Protetor Facial (CA 14910)", "10346", True)],
            # Posto 3 — Motorista
            [("ergonomico", "01.01.002", "Vibração corpo inteiro em veículo de carga",
              "Medição vibração ISO 2631-1", "0,7 m/s²", "0,5 m/s² — Limite NR-9",
              "Assento pneumático anti-vibratório instalado no veículo", True,
              "Não aplicável — EPC preferencial", "", False)],
        ]

        for i, (posto, agentes_lista) in enumerate(zip(posto_objs, agentes_por_posto)):
            if posto is None:
                continue
            for ag in agentes_lista:
                try:
                    AgenteNocivoPostoTrabalho.objects.create(
                        posto=posto,
                        tipo_agente=ag[0], cod_agente=ag[1], dsc_agente=ag[2],
                        tec_medicao=ag[3], intensidade=ag[4], limite_tolerancia=ag[5],
                        epc_descricao=ag[6], epc_eficaz=ag[7],
                        epi_descricao=ag[8], epi_ca=ag[9], epi_eficaz=ag[10],
                    )
                except Exception:
                    pass

        # Vincular funcionários a postos
        vinculos_posto = [
            (carlos,  0, datetime.date(2023, 6, 1)),
            (fernanda,0, datetime.date(2019, 8, 15)),
            (diego,   1, datetime.date(2020, 2, 20)),
            (rodrigo, 2, datetime.date(2018, 9, 3)),
            (jose,    3, datetime.date(2016, 4, 18)),
            (alex,    0, datetime.date(2021, 11, 22)),
        ]
        for func, idx, dt_inicio in vinculos_posto:
            if idx < len(posto_objs) and posto_objs[idx]:
                try:
                    FuncionarioPostoTrabalho.objects.create(
                        funcionario=func, posto=posto_objs[idx], data_inicio=dt_inicio,
                    )
                except Exception:
                    pass

        # ── 8. Riscos PGR ────────────────────────────────────────────────────
        riscos = [
            ("Produção",      "fisico",      "Ruído contínuo — prensas e estamparia",
             "I", 4, 4, "NR-15", "Protetores auditivos (CA 22347), treinamento NR-6",
             "Enclausuramento acústico das prensas; damper de vibração",
             datetime.date(2026, 9, 30), "Eng. Marcos Andrade", "em_controle"),
            ("Manutenção",    "acidente",    "Risco elétrico — painéis de alta tensão",
             "IV", 3, 5, "NR-10", "Luvas isolantes Classe 0 (CA 32741); LOTO; NR-10 renovada",
             "Bloqueio/sinalização LOTO obrigatório; barreiras dielétricas",
             datetime.date(2026, 6, 30), "Eng. Marcos Andrade", "em_controle"),
            ("Produção",      "quimico",     "Fumos metálicos — soldagem MIG/MAG",
             "III", 3, 4, "NR-15", "Respirador A2P3 (CA 24932); exaustor localizado",
             "LEV (exaustão localizada) na bancada; ventilação geral diluidora",
             datetime.date(2026, 12, 31), "Eng. Marcos Andrade", "em_controle"),
            ("Administrativo","ergonomico",  "Postura estática — trabalho em computador",
             "II", 3, 2, "NR-17", "Ginástica laboral; pausas programadas",
             "Cadeiras ergonômicas ajustáveis; monitor na altura dos olhos",
             datetime.date(2026, 8, 31), "Dra. Patricia Nunes", "identificado"),
            ("Saúde",         "biologico",   "Agentes biológicos — material biológico",
             "III", 2, 4, "NR-32", "EPI barreira; vacinação hepatite B obrigatória",
             "Coletores específicos de perfurocortante; EPIs descartáveis",
             datetime.date(2026, 10, 31), "Dra. Patricia Nunes", "controlado"),
            ("Logística",     "acidente",    "Circulação de veículos e pessoas — risco de atropelamento",
             "III", 3, 3, "NR-21", "Colete refletivo Classe II; treinamento de trânsito interno",
             "Faixas demarcatórias de circulação; espelhos convexos nas curvas",
             datetime.date(2026, 7, 31), "Eng. Marcos Andrade", "em_controle"),
            ("Produção",      "acidente",    "Queda de materiais em armazenamento vertical",
             "III", 2, 4, "NR-11", "Capacete (CA 31469); calçado de segurança (CA 11697)",
             "Estrutura porta-pallets inspecionada semestralmente; placas de carga",
             datetime.date(2026, 11, 30), "Eng. Marcos Andrade", "identificado"),
        ]
        for setor_r, tipo_r, agente_r, nivel_r, prob_r, sev_r, nr_ref, mc_exist, mc_prop, prazo_r, resp_r, status_r in riscos:
            try:
                RiscoOcupacional.objects.create(
                    empresa=empresa, setor=setor_r, tipo_risco=tipo_r, agente=agente_r,
                    nivel=nivel_r, probabilidade=prob_r, severidade=sev_r,
                    nr_referencia=nr_ref,
                    medida_controle_existente=mc_exist,
                    medida_controle_proposta=mc_prop,
                    prazo=prazo_r, responsavel=resp_r, status=status_r,
                )
            except Exception:
                pass

        # ── 9. Documentos SST ────────────────────────────────────────────────
        docs_sst = [
            ("PGR", "PGR — Programa de Gerenciamento de Riscos 2025/2026",
             "vigente", "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2025, 6, 1), datetime.date(2027, 6, 1)),
            ("PCMSO", "PCMSO — Programa de Controle Médico de Saúde Ocupacional",
             "vigente", "Dra. Patricia Nunes Costa", "CRM/SP 34872",
             datetime.date(2025, 3, 1), datetime.date(2026, 3, 1)),
            ("LTCAT", "LTCAT — Laudo Técnico das Condições Ambientais",
             "vigente", "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2024, 10, 15), datetime.date(2026, 10, 15)),
            ("laudo_insalubridade", "Laudo de Insalubridade — Produção e Manutenção",
             "vigente", "Eng. Marcos Andrade", "CREA/SP 987654",
             datetime.date(2024, 10, 15), datetime.date(2026, 10, 15)),
            ("PPP", "PPP — Perfil Profissiográfico Previdenciário (modelo)",
             "vigente", "Dra. Patricia Nunes Costa", "CRM/SP 34872",
             datetime.date(2025, 1, 10), datetime.date(2028, 1, 10)),
            ("CIPA", "CIPA — Ata de Posse e Mandato 2025/2026",
             "vigente", "Luiz Oliveira", "TRT/SP 54321",
             datetime.date(2024, 11, 8), datetime.date(2026, 11, 8)),
        ]
        for tipo_d, titulo_d, status_d, resp_d, reg_d, emis_d, valid_d in docs_sst:
            try:
                DocumentoSST.objects.create(
                    empresa=empresa, tipo=tipo_d, titulo=titulo_d, status=status_d,
                    responsavel_tecnico=resp_d, registro_profissional=reg_d,
                    data_emissao=emis_d, data_validade=valid_d,
                )
            except Exception:
                pass

        # ── 10. Afastamentos ─────────────────────────────────────────────────
        try:
            AfastamentoSST.objects.create(
                empresa=empresa, funcionario=luiz,
                motivo="doenca_comum", cid="J06.9",
                data_inicio=datetime.date(2026, 4, 13),
                data_prevista_retorno=datetime.date(2026, 4, 28),
                data_retorno_real=datetime.date(2026, 4, 27),
                status="encerrado",
                observacoes="Síndrome gripal. Retorno antecipado em 1 dia.",
            )
        except Exception:
            pass
        try:
            AfastamentoSST.objects.create(
                empresa=empresa, funcionario=alex,
                motivo="acidente_trabalho", cid="S60.0",
                data_inicio=datetime.date(2026, 2, 20),
                data_prevista_retorno=datetime.date(2026, 3, 10),
                data_retorno_real=datetime.date(2026, 3, 10),
                status="encerrado",
                observacoes="Contusão no punho direito durante movimentação de carga. CAT emitida.",
            )
        except Exception:
            pass

        # ── 11. CIPA ─────────────────────────────────────────────────────────
        try:
            cipa = ComissaoCIPA.objects.create(
                empresa=empresa,
                mandato_inicio=datetime.date(2024, 11, 8),
                mandato_fim=datetime.date(2026, 11, 7),
                numero_membros_eleitos=4,
                numero_membros_indicados=2,
                status="ativa",
                designacao_nr5=False,
            )
            membros_cipa = [
                (luiz,    "presidente",      "eleito"),
                (fernanda,"vice_presidente", "indicado"),
                (carlos,  "secretario",      "eleito"),
                (diego,   "membro_eleito",   "eleito"),
                (ana,     "membro_indicado", "indicado"),
                (rodrigo, "membro_eleito",   "eleito"),
            ]
            for func, cargo_c, tipo_c in membros_cipa:
                try:
                    MembroCIPA.objects.create(
                        comissao=cipa, funcionario=func, cargo=cargo_c, tipo=tipo_c,
                        data_posse=datetime.date(2024, 11, 8), ativo=True,
                    )
                except Exception:
                    pass

            # Reuniões
            import datetime as _dt
            reuniao1 = ReuniaoCIPA.objects.create(
                comissao=cipa, tipo="ordinaria",
                data_reuniao=_dt.datetime(2026, 4, 8, 9, 0),
                local="Sala de Reuniões — Planta Industrial",
                pauta="1. Análise de acidentes do 1º trimestre\n2. Revisão do PPRA\n3. Inspeções programadas",
                ata="Reunião ordinária realizada com quórum. Analisados 2 acidentes do período. "
                    "Aprovado plano de inspeções para o 2º trimestre.",
                status="realizada",
            )
            reuniao2 = ReuniaoCIPA.objects.create(
                comissao=cipa, tipo="ordinaria",
                data_reuniao=_dt.datetime(2026, 5, 13, 9, 0),
                local="Sala de Reuniões — Planta Industrial",
                pauta="1. Relatório de EPIs\n2. Análise de quase-acidentes\n3. Semana SIPAT 2026",
                status="agendada",
            )

            # Participantes reunião 1
            presentes_r1 = [luiz, fernanda, carlos, diego, ana, rodrigo]
            for func in presentes_r1:
                try:
                    ParticipanteReuniaoCIPA.objects.create(
                        reuniao=reuniao1, funcionario=func, presente=True,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # ── 12. Clínicas credenciadas (rede nacional) ────────────────────────
        clinicas_credenciadas = [
            dict(nome="Clínica de Medicina Ocupacional SolusCRT SP",
                 cnpj="11.222.333/0001-44",
                 tipo="clinica_ocupacional",
                 especialidades=["audiometria","espirometria","hemograma","acuidade_visual","ecg","raio_x"],
                 endereco="Av. Paulista, 2200 — Bela Vista",
                 cidade="São Paulo", uf="SP", cep="01310-300",
                 telefone="(11) 3300-1111",
                 email="contato@clinica-sp.soluscrt.com",
                 responsavel_tecnico="Dr. Fernando Leite",
                 crm="CRM/SP 22345",
                 horario_atendimento="Seg–Sex 07h30–18h / Sáb 08h–12h",
                 aceita_agendamento_online=True,
                 tempo_medio_laudo_dias=2,
                 avaliacao_media="4.8", total_avaliacoes=312,
                 lat="-23.5616", lng="-46.6562",
                 status_credenciamento="ativo", ativa=True),
            dict(nome="SESI SP — Saúde do Trabalhador — Unidade Santo André",
                 cnpj="03.773.700/0001-55",
                 tipo="sesi",
                 especialidades=["audiometria","espirometria","hemograma","acuidade_visual","toxicologico"],
                 endereco="Rua Senador Fláquer, 638 — Centro",
                 cidade="Santo André", uf="SP", cep="09010-161",
                 telefone="(11) 4433-2200",
                 email="unidade.sa@sesisp.org.br",
                 responsavel_tecnico="Dr. Renato Carvalho",
                 crm="CRM/SP 15678",
                 horario_atendimento="Seg–Sex 07h–17h",
                 aceita_agendamento_online=True,
                 tempo_medio_laudo_dias=3,
                 avaliacao_media="4.6", total_avaliacoes=528,
                 lat="-23.6616", lng="-46.5232",
                 status_credenciamento="ativo", ativa=True),
            dict(nome="Lab Análises Clínicas Oswaldo Cruz — SP",
                 cnpj="44.555.666/0001-77",
                 tipo="laboratorio",
                 especialidades=["hemograma","bioquimica","toxicologico","urina","pcr","hbsag"],
                 endereco="Rua Dr. Arnaldo, 455 — Cerqueira César",
                 cidade="São Paulo", uf="SP", cep="01246-903",
                 telefone="(11) 3088-8200",
                 email="lab@oswaldocruz.com.br",
                 responsavel_tecnico="Dra. Beatriz Torres",
                 crm="CRM/SP 44123",
                 horario_atendimento="Seg–Sex 06h–18h / Sáb 06h–12h",
                 aceita_agendamento_online=True,
                 tempo_medio_laudo_dias=1,
                 avaliacao_media="4.9", total_avaliacoes=1204,
                 lat="-23.5543", lng="-46.6680",
                 status_credenciamento="ativo", ativa=True),
        ]
        clinica_objs = []
        for cd in clinicas_credenciadas:
            try:
                c = ClinicaCredenciada.objects.create(**cd)
                clinica_objs.append(c)
            except Exception:
                clinica_objs.append(None)

        # ── 13. Vínculos empresa → clínica (a empresa usa 2 clínicas) ────────
        vinculos_clinica = []
        for i, clin_cred in enumerate(clinica_objs[:2]):
            if clin_cred is None:
                continue
            try:
                # Para VinculoClinicaEmpresa, a "clinica" é uma Empresa SST;
                # usamos empresa_contratante=empresa e registramos a clínica credenciada como externa
                v = VinculoClinicaEmpresa.objects.create(
                    clinica=empresa,              # demo: empresa vinculada a si mesma como prestadora (demo)
                    empresa_contratante=empresa,
                    empresa_nome=clin_cred.nome,
                    empresa_email_convite=clin_cred.email,
                    status="ativo",
                    observacoes=f"Clínica credenciada SolusCRT — {clin_cred.cidade}/{clin_cred.uf}",
                )
                vinculos_clinica.append(v)
            except Exception:
                vinculos_clinica.append(None)

        # ── 14. Pedidos de Exame (SolicitacaoExame) ───────────────────────────
        vinculo_ativo = vinculos_clinica[0] if vinculos_clinica else None
        pedidos = [
            # (func, tipo_aso, exames_lista, status, urgente, obs, data_agenda, clinica_nome_ext, email_ext)
            (rodrigo, "admissional",
             ["Audiometria","Espirometria","Hemograma Completo","Raio-X Tórax PA","Acuidade Visual"],
             "pendente", False,
             "Exame admissional — início na função de soldador. Verificar histórico audiométrico.",
             None, "", ""),
            (carlos, "periodico",
             ["Audiometria","Espirometria","Hemograma Completo","Glicemia de Jejum"],
             "agendado", False,
             "ASO periódico anual. Agendado para 10/06/2026 às 08h.",
             datetime.date(2026, 6, 10), "", ""),
            (beatriz, "demissional",
             ["Hemograma Completo","Glicemia","Acuidade Visual","Eletrocardiograma"],
             "realizado", False,
             "Exame demissional — desligamento voluntário em 30/04/2026.",
             datetime.date(2026, 4, 28), "", ""),
            (diego, "periodico",
             ["Audiometria","Acuidade Visual","Hemograma Completo","Glicemia","ECG"],
             "pendente", True,
             "⚠️ URGENTE — Eletricista com ASO vencendo em 15 dias. Prioridade máxima.",
             None, "Clínica São Lucas Ltda", "contato@sao-lucas.com.br"),
            (luiz, "retorno_trabalho",
             ["Hemograma Completo","Glicemia de Jejum","Acuidade Visual"],
             "realizado", False,
             "Retorno ao trabalho após afastamento por síndrome gripal (15 dias).",
             datetime.date(2026, 4, 27), "", ""),
            (jose, "periodico",
             ["Hemograma Completo","ECG","Acuidade Visual","Toxicológico Urina","Glicemia"],
             "agendado", False,
             "ASO periódico motorista — exige toxicológico conforme Res. CONTRAN 784/2020.",
             datetime.date(2026, 6, 3), "", ""),
        ]
        for func, tipo_aso, exames_lista, status_p, urgente_p, obs_p, data_ag, cl_nome, cl_email in pedidos:
            try:
                SolicitacaoExame.objects.create(
                    empresa=empresa,
                    funcionario=func,
                    tipo_aso=tipo_aso,
                    exames=_json.dumps(exames_lista, ensure_ascii=False),
                    status=status_p,
                    urgente=urgente_p,
                    observacoes=obs_p,
                    data_agendamento=data_ag,
                    clinica_nome_externo=cl_nome,
                    clinica_email_externo=cl_email,
                    vinculo=vinculo_ativo if not cl_nome else None,
                )
            except Exception:
                pass

        # ── 15. Notificações APP (Luiz e Carlos) ─────────────────────────────
        notifs_app = [
            (luiz, "EPI aguardando confirmação",
             "5 equipamentos aguardam sua confirmação de recebimento. Toque para confirmar.",
             "epi", False),
            (luiz, "ASO periódico válido ✅",
             "Seu ASO periódico está válido até 29/03/2027. Próximo exame agendado.",
             "aso", False),
            (luiz, "Treinamento NR-10 vencido ⚠️",
             "Segurança em Eletricidade (NR-10) venceu há 8 dias. Agende renovação com o RH.",
             "treinamento", False),
            (luiz, "Reunião CIPA agendada 📅",
             "Reunião ordinária da CIPA em 13/05/2026 às 09h. Sala de Reuniões — Planta.",
             "cipa", False),
            (carlos, "Novo pedido de exame 🔬",
             "ASO periódico agendado para 10/06/2026. Compareça em jejum de 8h.",
             "exame", False),
            (carlos, "EPI recebido — confirme 📦",
             "Você recebeu 10 protetores auditivos + óculos + luvas. Confirme o recebimento.",
             "epi", False),
        ]
        for func, titulo_n, corpo_n, cat_n, lida_n in notifs_app:
            try:
                NotificacaoFuncionario.objects.create(
                    funcionario=func, titulo=titulo_n, corpo=corpo_n,
                    categoria=cat_n, lida=lida_n,
                )
            except Exception:
                pass

        # ── 16. Bem-estar (check-ins) ─────────────────────────────────────────
        checkins = [
            (luiz,    "bom",    4, 3, 2, 4),
            (carlos,  "neutro", 3, 3, 3, 3),
            (ana,     "otimo",  5, 5, 1, 5),
            (fernanda,"ruim",   2, 2, 4, 2),
            (diego,   "bom",    4, 4, 2, 4),
            (rodrigo, "neutro", 3, 2, 3, 3),
        ]
        for func, humor, sf, sm, ne, st in checkins:
            try:
                with transaction.atomic():
                    CheckinBemEstar.objects.create(
                        empresa=empresa, funcionario=func,
                        humor=humor, saude_fisica=sf, saude_mental=sm,
                        nivel_estresse=ne, satisfacao_trabalho=st,
                    )
            except Exception:
                pass

        total_f = len(func_objs)
        self.out(
            f"     ✓ {total_f} funcionários | {len(catalogo_epi)} EPIs | "
            f"{len(riscos)} riscos PGR | {len(pedidos)} pedidos de exame | "
            f"CIPA ativa | 3 clínicas credenciadas",
            self.style.SUCCESS,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Farmácia
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_farmacia(self, empresa):
        from api.models import ItemFarmacia, LoteMedicamento, FornecedorFarmacia

        try:
            medicamentos = [
                ("Paracetamol 750mg", "7896714800036", "comprimido", "Analgésico"),
                ("Ibuprofeno 600mg", "7896714800037", "comprimido", "Anti-inflamatório"),
                ("Amoxicilina 500mg", "7896714800038", "cápsula", "Antibiótico"),
                ("Atorvastatina 20mg", "7896714800039", "comprimido", "Cardiovascular"),
                ("Metformina 850mg", "7896714800040", "comprimido", "Antidiabético"),
                ("Omeprazol 20mg", "7896714800041", "cápsula", "Antiulceroso"),
                ("Dipirona 500mg", "7896714800042", "comprimido", "Analgésico"),
                ("Losartana 50mg", "7896714800043", "comprimido", "Anti-hipertensivo"),
            ]
            for nome, ean, forma, categoria in medicamentos:
                item = ItemFarmacia.objects.create(
                    empresa=empresa,
                    nome=nome,
                    codigo=ean,
                    categoria=categoria,
                    unidade_medida=forma,
                    estoque_atual=50 + len(nome),
                    estoque_minimo=10,
                    ativo=True,
                )
                LoteMedicamento.objects.create(
                    empresa=empresa, item=item,
                    numero_lote=f"LOT{len(nome):04d}",
                    quantidade_inicial=50 + len(nome),
                    quantidade_atual=50 + len(nome),
                    data_fabricacao=datetime.date(2025, 1, 1),
                    data_validade=datetime.date(2027, 6, 30),
                )
        except Exception as ex:
            self.out(f"     ⚠ Farmácia dados parciais: {ex}")

        try:
            FornecedorFarmacia.objects.create(
                empresa=empresa,
                nome="Distribuidora MedFarma Ltda",
                cnpj="12.345.678/0001-90",
                contato="contato@medfarma.com.br",
                ativo=True,
            )
        except Exception:
            pass

        self.out(f"     ✓ Dados demo Farmácia criados", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Hospital
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_hospital(self, empresa):
        from api.models import LeitoHospital, DepartamentoHospital, PacienteHospital

        try:
            depts = [
                ("UTI", "UTI"),
                ("Clínica Médica", "clinica"),
                ("Cirurgia", "cirurgia"),
                ("Pediatria", "pediatria"),
                ("Maternidade", "maternidade"),
            ]
            dept_objs = []
            for nome_dept, sigla in depts:
                d = DepartamentoHospital.objects.create(
                    empresa=empresa, nome=nome_dept, tipo=sigla,
                    capacidade_leitos=20, ativo=True,
                )
                dept_objs.append(d)

            # Leitos
            status_cycle = ["ocupado", "ocupado", "disponivel", "ocupado", "higienizacao"]
            for dept in dept_objs:
                for i in range(1, 6):
                    LeitoHospital.objects.create(
                        empresa=empresa,
                        departamento=dept,
                        numero=f"{dept.tipo[:3].upper()}-{i:02d}",
                        tipo="adulto" if dept.tipo != "pediatria" else "pediatrico",
                        status=status_cycle[i % len(status_cycle)],
                    )
        except Exception as ex:
            self.out(f"     ⚠ Hospital leitos parciais: {ex}")

        try:
            pacientes = [
                ("José da Silva", "123.456.789-00", datetime.date(1958, 3, 10)),
                ("Maria Aparecida Santos", "234.567.890-11", datetime.date(1945, 7, 22)),
                ("Pedro Henrique Costa", "345.678.901-22", datetime.date(1982, 11, 5)),
            ]
            for nome, cpf, nasc in pacientes:
                PacienteHospital.objects.create(
                    empresa=empresa, nome=nome, cpf=cpf,
                    data_nascimento=nasc,
                )
        except Exception as ex:
            self.out(f"     ⚠ Hospital pacientes parciais: {ex}")

        self.out(f"     ✓ Dados demo Hospital criados", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Governo
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_governo(self, empresa):
        from api.models import (IndicadorSaudeGov, ProgramaSaudeGov,
                                 UnidadeSaude, AlertaGovernamental,
                                 SerieEpidemiologica, RegistroSintoma)

        try:
            indicadores = [
                ("Cobertura Vacinal COVID-19", "vacinacao", 78.5, 90.0, "%"),
                ("Taxa de Internação por Dengue", "dengue", 4.2, 2.0, "/100k"),
                ("Consultas APS por habitante", "aps", 3.1, 4.0, "cons/hab"),
                ("Taxa de Mortalidade Infantil", "mortalidade", 11.2, 8.0, "/1000 NV"),
            ]
            for nome, categoria, val_atual, meta, unidade in indicadores:
                IndicadorSaudeGov.objects.create(
                    empresa=empresa,
                    nome=nome, tipo=categoria,
                    valor_atual=val_atual, meta=meta,
                    unidade=unidade,
                    periodo_referencia=str(HOJE.year),
                )
        except Exception as ex:
            self.out(f"     ⚠ Governo indicadores parciais: {ex}")

        try:
            programas = [
                ("Programa Dengue Zero", "epidemiologia", "em_andamento"),
                ("Saúde da Família — Expansão 2026", "atenção_primária", "em_andamento"),
                ("Vacinação em Dia", "vacinacao", "ativo"),
                ("Saúde Mental na APS", "saude_mental", "planejamento"),
            ]
            for nome, categoria, status in programas:
                ProgramaSaudeGov.objects.create(
                    empresa=empresa,
                    nome=nome,
                    status=status,
                    descricao=f"Programa demo: {nome}",
                    populacao_alvo=5000,
                )
        except Exception as ex:
            self.out(f"     ⚠ Governo programas parciais: {ex}")

        try:
            unidades = [
                ("UBS Centro", "ubs", "São Paulo", "SP", "-23.5505", "-46.6333"),
                ("UBS Vila Nova", "ubs", "São Paulo", "SP", "-23.5600", "-46.6400"),
                ("UPA Zona Leste", "upa", "São Paulo", "SP", "-23.5700", "-46.5200"),
                ("Hospital Municipal", "hospital", "São Paulo", "SP", "-23.5475", "-46.6361"),
            ]
            for nome, tipo, cidade, estado, lat, lon in unidades:
                UnidadeSaude.objects.create(
                    empresa=empresa,
                    nome=nome, tipo=tipo,
                    municipio=cidade, uf=estado,
                    latitude=float(lat), longitude=float(lon),
                )
        except Exception as ex:
            self.out(f"     ⚠ Governo unidades parciais: {ex}")

        try:
            # Alertas epidemiológicos
            AlertaGovernamental.objects.create(
                empresa=empresa,
                titulo="Aumento de casos de Dengue — Zona Norte",
                mensagem="Registrado aumento de 40% nos casos confirmados de Dengue na Zona Norte na última semana. Reforce medidas preventivas.",
                nivel="alto",
                estado="SP",
                cidade="São Paulo",
                bairro="Zona Norte",
                ativo=True,
                status="publicado",
            )
            AlertaGovernamental.objects.create(
                empresa=empresa,
                titulo="Surto de Influenza — Zona Leste",
                mensagem="Elevação no índice de síndrome gripal na Zona Leste. Vacinação disponível nas UBSs.",
                nivel="moderado",
                estado="SP",
                cidade="São Paulo",
                bairro="Zona Leste",
                ativo=True,
                status="publicado",
            )
        except Exception as ex:
            self.out(f"     ⚠ Governo alertas parciais: {ex}")

        # Registros de sintomas (simulação população)
        try:
            import random, uuid
            sintomas_base = [
                {"febre": True, "dor_cabeca": True, "dor_corpo": True,
                 "cidade": "São Paulo", "estado": "SP", "bairro": "Zona Norte",
                 "latitude": -23.51, "longitude": -46.64, "doenca": "dengue"},
                {"tosse": True, "falta_ar": True,
                 "cidade": "São Paulo", "estado": "SP", "bairro": "Zona Leste",
                 "latitude": -23.57, "longitude": -46.52, "doenca": "influenza"},
            ]
            random.seed(42)
            for i in range(40):
                base = sintomas_base[i % 2].copy()
                lat_jitter = random.uniform(-0.03, 0.03)
                lon_jitter = random.uniform(-0.03, 0.03)
                RegistroSintoma.objects.create(
                    empresa=empresa,
                    id_anonimo=uuid.uuid4(),
                    doenca=base.pop("doenca"),
                    febre=base.pop("febre", False),
                    tosse=base.pop("tosse", False),
                    falta_ar=base.pop("falta_ar", False),
                    dor_cabeca=base.pop("dor_cabeca", False),
                    dor_corpo=base.pop("dor_corpo", False),
                    cidade=base["cidade"],
                    estado=base["estado"],
                    bairro=base["bairro"],
                    latitude=base["latitude"] + lat_jitter,
                    longitude=base["longitude"] + lon_jitter,
                    origem_dado='cidadao',
                )
        except Exception as ex:
            self.out(f"     ⚠ Governo sintomas pop parciais: {ex}")

        self.out(f"     ✓ Dados demo Governo criados", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Plano de Saúde
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_plano(self, empresa):
        from api.models import (PlanoSaude, BeneficiarioPlano,
                                 RedeCredenciadaPlano, PrestadorPlanoSaude)

        try:
            planos = [
                ("Básico Ambulatorial", "basico", 189.90),
                ("Essencial Ambulatorial + Exames", "essencial", 389.50),
                ("Premium Hospitalar", "premium", 689.00),
                ("Master Odonto + Hospital", "master", 989.00),
            ]
            plano_objs = []
            for nome, codigo, mensalidade in planos:
                p = PlanoSaude.objects.create(
                    empresa=empresa,
                    nome=nome,
                )
                plano_objs.append(p)

            # Beneficiários
            beneficiarios = [
                ("Carlos Eduardo Mendes", "100.200.300-44", datetime.date(1975, 5, 12)),
                ("Patrícia Souza Lima", "200.300.400-55", datetime.date(1983, 9, 28)),
                ("Roberto Alves Teixeira", "300.400.500-66", datetime.date(1990, 2, 14)),
                ("Juliana Moreira Costa", "400.500.600-77", datetime.date(1995, 12, 3)),
                ("Marcos Vinícius Pinto", "500.600.700-88", datetime.date(1969, 7, 19)),
            ]
            for nome, cpf, nasc in beneficiarios:
                BeneficiarioPlano.objects.create(
                    plano=plano_objs[len(nome) % len(plano_objs)],
                    nome=nome, cpf=cpf,
                    data_nascimento=nasc,
                )
        except Exception as ex:
            self.out(f"     ⚠ Plano dados parciais: {ex}")

        try:
            prestadores = [
                ("Clínica São Lucas", "clínica", "São Paulo", "SP"),
                ("Lab Análises Médicas Central", "laboratorio", "São Paulo", "SP"),
                ("Hospital e Maternidade Santa Cruz", "hospital", "São Paulo", "SP"),
                ("Clínica Odonto Premium", "odontologia", "São Paulo", "SP"),
            ]
            for nome, tipo, cidade, estado in prestadores:
                PrestadorPlanoSaude.objects.create(
                    empresa=empresa,
                    nome_fantasia=nome, tipo=tipo,
                    cidade=cidade, estado=estado,
                )
        except Exception as ex:
            self.out(f"     ⚠ Plano prestadores parciais: {ex}")

        self.out(f"     ✓ Dados demo Plano de Saúde criados", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # DONO SAAS
    # ─────────────────────────────────────────────────────────────────────────
    def _recria_dono_saas(self):
        from api.models import DonoSaaS
        dono, created = DonoSaaS.objects.get_or_create(
            email="owner@soluscrt.com",
            defaults={
                "nome": "Operação SolusCRT",
                "senha": make_password("Owner@SolusCRT2026"),
                "ativo": True,
            },
        )
        if not created:
            # Garante que está ativo mesmo se já existia
            if not dono.ativo:
                dono.ativo = True
                dono.save(update_fields=["ativo"])
        self.out(f"  ✓ DonoSaaS {'criado' if created else 'já existe'}", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # RESUMO FINAL
    # ─────────────────────────────────────────────────────────────────────────
    def _imprimir_resumo(self):
        self.out("📋 CREDENCIAIS DOS AMBIENTES DEMO", self.style.MIGRATE_HEADING)
        self.out("")
        self.out("┌─────────────────────────────────────────────────────────┐")
        self.out("│  AMBIENTE           EMAIL                    SENHA      │")
        self.out("├─────────────────────────────────────────────────────────┤")
        self.out("│  SST (empresa)      demo.sst@soluscrt.com   Demo@SST2026│")
        self.out("│  Farmácia           demo.farmacia@soluscrt  Demo@Farm202│")
        self.out("│  Hospital           demo.hospital@soluscrt  Demo@Hosp202│")
        self.out("│  Governo            demo.governo@soluscrt   Demo@Gov2026│")
        self.out("│  Plano de Saúde     demo.plano@soluscrt     Demo@Plano20│")
        self.out("│  DonoSaaS           owner@soluscrt.com      Owner@...   │")
        self.out("├─────────────────────────────────────────────────────────┤")
        self.out("│  APP TRABALHADOR (SST)                                  │")
        self.out("│  Luiz Oliveira      luiz@app.local          Luiz@2026   │")
        self.out("│  Carlos Lima        carlos@app.local        Carlos@2026  │")
        self.out("├─────────────────────────────────────────────────────────┤")
        self.out("│  DEMO SST — dados de demonstração                       │")
        self.out("│  12 funcionários   35 EPIs c/ CAs válidos               │")
        self.out("│  7 riscos PGR      6 pedidos de exame                   │")
        self.out("│  CIPA ativa        3 clínicas credenciadas              │")
        self.out("│  Docs: PGR, PCMSO, LTCAT, PPP, Laudo Insalubridade     │")
        self.out("└─────────────────────────────────────────────────────────┘")
