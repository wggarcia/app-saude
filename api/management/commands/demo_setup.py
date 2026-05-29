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
        self.out("     └─ 6 funcionários SST + Luiz Oliveira (app)")
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
    def _criar_dados_sst(self, empresa):
        from api.models import (FuncionarioSST, CredencialAppFuncionario,
                                 ASOOcupacional, TreinamentoNR, EntregaEPI,
                                 EPIItem, AfastamentoSST, NotificacaoFuncionario,
                                 CheckinBemEstar)

        funcionarios = [
            dict(nome="Luiz Oliveira", cpf="111.222.333-44", matricula="L-0042",
                 cargo="Técnico de Segurança do Trabalho", setor="Produção",
                 sexo="M", data_nascimento=datetime.date(1990, 3, 15),
                 data_admissao=datetime.date(2022, 1, 10)),
            dict(nome="Ana Paula Ferreira", cpf="222.333.444-55", matricula="L-0015",
                 cargo="Enfermeira Ocupacional", setor="Saúde",
                 sexo="F", data_nascimento=datetime.date(1988, 7, 22),
                 data_admissao=datetime.date(2021, 3, 5)),
            dict(nome="Carlos Alberto Lima", cpf="333.444.555-66", matricula="L-0023",
                 cargo="Operador de Produção", setor="Produção",
                 sexo="M", data_nascimento=datetime.date(1993, 11, 8),
                 data_admissao=datetime.date(2023, 6, 1)),
            dict(nome="Fernanda Costa Silva", cpf="444.555.666-77", matricula="L-0031",
                 cargo="Supervisora de Linha", setor="Produção",
                 sexo="F", data_nascimento=datetime.date(1985, 4, 17),
                 data_admissao=datetime.date(2019, 8, 15)),
            dict(nome="Diego Rocha Santos", cpf="555.666.777-88", matricula="L-0038",
                 cargo="Eletricista Industrial", setor="Manutenção",
                 sexo="M", data_nascimento=datetime.date(1991, 9, 3),
                 data_admissao=datetime.date(2020, 2, 20)),
            dict(nome="Beatriz Mendes Alves", cpf="666.777.888-99", matricula="L-0044",
                 cargo="Auxiliar Administrativo", setor="Administrativo",
                 sexo="F", data_nascimento=datetime.date(1997, 1, 28),
                 data_admissao=datetime.date(2024, 1, 8)),
        ]

        func_objs = []
        for fd in funcionarios:
            f = FuncionarioSST.objects.create(empresa=empresa, ativo=True, **fd)
            func_objs.append(f)

        luiz = func_objs[0]

        # Credencial app para Luiz
        CredencialAppFuncionario.objects.create(
            funcionario=luiz,
            email="luiz@app.local",
            senha=make_password("Luiz@2026"),
            ativo=True,
        )

        # ASOs
        asos_data = [
            (luiz, "Periódico", "Apto", datetime.date(2026, 3, 29), datetime.date(2027, 3, 29)),
            (func_objs[1], "Admissional", "Apto", datetime.date(2021, 3, 4), datetime.date(2026, 3, 4)),
            (func_objs[2], "Periódico", "Apto", datetime.date(2025, 12, 10), datetime.date(2026, 12, 10)),
            (func_objs[3], "Periódico", "Apto com restrição", datetime.date(2025, 8, 15), datetime.date(2026, 8, 15)),
            (func_objs[4], "Periódico", "Apto", datetime.date(2026, 2, 18), datetime.date(2027, 2, 18)),
        ]
        for func, tipo, resultado, emissao, validade in asos_data:
            try:
                ASOOcupacional.objects.create(
                    empresa=empresa, funcionario=func,
                    tipo_aso=tipo, resultado=resultado,
                    data_emissao=emissao, data_validade=validade,
                    medico_responsavel="Dr. Roberto Carvalho CRM/SP 12345",
                )
            except Exception:
                pass

        # Treinamentos NR
        try:
            TreinamentoNR.objects.create(
                empresa=empresa, funcionario=luiz,
                nr="NR-10", nome="Segurança em Eletricidade",
                carga_horaria=8,
                data_realizacao=datetime.date(2025, 5, 23),
                data_vencimento=datetime.date(2026, 5, 23),
                instrutor="SolusCRT Treinamentos", valido=False,
            )
            TreinamentoNR.objects.create(
                empresa=empresa, funcionario=luiz,
                nr="NR-35", nome="Trabalho em Altura",
                carga_horaria=8,
                data_realizacao=datetime.date(2025, 12, 14),
                data_vencimento=datetime.date(2026, 12, 14),
                instrutor="SolusCRT Treinamentos", valido=True,
            )
            TreinamentoNR.objects.create(
                empresa=empresa, funcionario=luiz,
                nr="NR-06", nome="Utilização de EPIs",
                carga_horaria=4,
                data_realizacao=datetime.date(2025, 6, 10),
                data_vencimento=datetime.date(2027, 6, 10),
                instrutor="SolusCRT Treinamentos", valido=True,
            )
        except Exception:
            pass

        # EPIs / Entregas
        try:
            epis = [
                ("Óculos de Proteção", "CA-15943"),
                ("Bota de Segurança", "CA-26694"),
                ("Capacete de Segurança", "CA-31469"),
            ]
            for nome_epi, ca in epis:
                item = EPIItem.objects.create(
                    empresa=empresa, nome=nome_epi,
                    ca=ca, ativo=True,
                )
                EntregaEPI.objects.create(
                    empresa=empresa, funcionario=luiz, item=item,
                    data_entrega=datetime.date(2026, 5, 18),
                    confirmado=False,
                )
        except Exception:
            pass

        # Afastamento
        try:
            AfastamentoSST.objects.create(
                empresa=empresa, funcionario=luiz,
                tipo="Doença Comum", cid="J06.9",
                data_inicio=datetime.date(2026, 4, 13),
                data_retorno_prevista=datetime.date(2026, 4, 28),
                data_retorno_real=datetime.date(2026, 4, 27),
                observacoes="Afastamento por síndrome gripal. Retorno antecipado em 1 dia.",
                encerrado=True,
            )
        except Exception:
            pass

        # Notificações
        try:
            notifs = [
                ("EPI aguardando confirmação",
                 "3 equipamentos aguardam sua confirmação de recebimento. Acesse a aba EPIs.",
                 "epi", False),
                ("ASO periódico válido ✅",
                 "Seu ASO periódico está válido até 2027-03-29.",
                 "aso", False),
                ("Treinamento vencido ⚠️",
                 "NR-10 Segurança em Eletricidade venceu há 5 dias. Agende renovação com o RH.",
                 "treinamento", False),
            ]
            for titulo, corpo, categoria, lida in notifs:
                NotificacaoFuncionario.objects.create(
                    funcionario=luiz, titulo=titulo, corpo=corpo,
                    categoria=categoria, lida=lida,
                )
        except Exception:
            pass

        # Bem-estar checkin
        try:
            with transaction.atomic():
                CheckinBemEstar.objects.create(
                    empresa=empresa,
                    funcionario=luiz,
                    humor="bom",
                    saude_fisica=3, saude_mental=3,
                    nivel_estresse=3, satisfacao_trabalho=3,
                )
        except Exception:
            pass

        self.out(f"     ✓ {len(func_objs)} funcionários + dados demo SST criados", self.style.SUCCESS)

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
        self.out("└─────────────────────────────────────────────────────────┘")
