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
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction


DEMO_SENHA_ADMIN = "Demo@SST2026"   # SST
DEMO_SENHA_FARM  = "Demo@Farm2026"
DEMO_SENHA_HOSP  = "Demo@Hosp2026"
DEMO_SENHA_GOV   = "Demo@Gov2026"
DEMO_SENHA_PLANO = "Demo@Plano2026"

HOJE = datetime.date.today()


class Command(BaseCommand):
    help = "Reseta o banco local ou monta 5 ambientes de demonstração para homologacao."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Reseta o banco local e cria os 5 demos do zero (uso local).",
        )
        parser.add_argument(
            "--upsert",
            action="store_true",
            help="Cria as contas demo se nao existirem; ignora se ja existirem (uso em homologacao).",
        )
        parser.add_argument(
            "--refresh-dados",
            action="store_true",
            help="Recria APENAS os dados demo (funcionarios, EPIs, etc.) nas contas existentes. "
                 "Nao deleta nem recria as contas. Uso em homologacao.",
        )

    def out(self, msg, style=None):
        if style:
            self.stdout.write(style(msg))
        else:
            self.stdout.write(msg)

    def handle(self, *args, **options):
        apply         = options["apply"]
        upsert        = options["upsert"]
        refresh_dados = options["refresh_dados"]

        # Em produção apenas --upsert é permitido: ele provisiona, de forma
        # idempotente, as contas de demonstração exigidas pela revisão da
        # App Store / Play Store (Guideline 2.1) — sem apagar nem recriar
        # dados existentes. Operações destrutivas (--apply) e de mutação de
        # dados (--refresh-dados) permanecem bloqueadas em produção.
        if getattr(settings, "IS_PRODUCTION", False) and not upsert:
            raise CommandError(
                "Em producao apenas 'demo_setup --upsert' e permitido "
                "(provisiona contas de demonstracao de forma idempotente). "
                "Use staging/homologacao para --apply ou --refresh-dados."
            )

        if refresh_dados:
            self.out(f"\n{'='*60}")
            self.out("  demo_setup --refresh-dados  (homologacao — atualiza dados)")
            self.out(f"{'='*60}\n")
            self._refresh_dados_demos()
            return

        if upsert:
            self.out(f"\n{'='*60}")
            self.out("  demo_setup --upsert  (homologacao — idempotente)")
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

        # Garante as credenciais de login do APP do trabalhador mesmo quando a
        # empresa SST já existe (o bloco de dados acima é pulado nesse caso, e
        # as credenciais luiz@app.local / carlos@app.local vivem dentro dele).
        # Sem isso, os avaliadores da App Store recebem 404 "E-mail não
        # encontrado" (causa da rejeição Apple Guideline 2.1).
        self._garantir_credenciais_app()

        # Popular dados ocupacionais dos trabalhadores demo (ASO, EPIs,
        # treinamentos, notificações) para que as telas do app não fiquem
        # vazias na revisão da App Store (Guideline 2.3.3 — screenshots).
        self._garantir_dados_app_demo()

        self._recria_dono_saas()

        self.out(f"\n  {criados} conta(s) demo criada(s). ✅\n", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # CREDENCIAIS DO APP DO TRABALHADOR — idempotente, seguro em produção
    # ─────────────────────────────────────────────────────────────────────────
    def _garantir_credenciais_app(self):
        """Garante que luiz@app.local e carlos@app.local existam e tenham a
        senha conhecida, vinculados a funcionários da empresa demo SST.

        Idempotente: cria o que faltar e reseta a senha das credenciais para o
        valor publicado (necessário para a revisão da App Store / Play Store).
        """
        from api.models import Empresa, FuncionarioSST, CredencialAppFuncionario

        empresa = Empresa.objects.filter(email="demo.sst@soluscrt.com").first()
        if not empresa:
            self.out("  ⚠ empresa demo SST inexistente — não há onde criar credenciais app", self.style.WARNING)
            return

        # (cpf, nome, cargo, setor, email_app, senha_app)
        trabalhadores = [
            ("111.222.333-44", "Luiz Oliveira",      "Técnico de Segurança do Trabalho", "Produção",
             "luiz@app.local",   "Luiz@2026"),
            ("333.444.555-66", "Carlos Alberto Lima", "Operador de Produção",            "Produção",
             "carlos@app.local", "Carlos@2026"),
        ]

        for cpf, nome, cargo, setor, email_app, senha_app in trabalhadores:
            # Cada trabalhador roda em seu próprio savepoint: uma falha aqui
            # NÃO pode abortar a transação inteira do upsert (senão nenhuma
            # credencial é persistida e os avaliadores recebem 404).
            try:
                with transaction.atomic():
                    self._upsert_credencial_app(
                        FuncionarioSST, CredencialAppFuncionario,
                        empresa, cpf, nome, cargo, setor, email_app, senha_app,
                    )
            except Exception as exc:  # noqa: BLE001
                self.out(
                    f"  ⚠ credencial {email_app} falhou: {exc}",
                    self.style.WARNING,
                )

    def _upsert_credencial_app(
        self, FuncionarioSST, CredencialAppFuncionario,
        empresa, cpf, nome, cargo, setor, email_app, senha_app,
    ):
        """Garante 1 FuncionarioSST + 1 CredencialAppFuncionario de forma
        idempotente, tratando explicitamente todos os conflitos do vínculo
        OneToOne (funcionario↔credencial) para nunca levantar IntegrityError."""
        func = FuncionarioSST.objects.filter(empresa=empresa, cpf=cpf).first()
        if not func:
            func = FuncionarioSST.objects.filter(empresa=empresa, nome=nome).first()
        if not func:
            func = FuncionarioSST.objects.create(
                empresa=empresa, ativo=True, nome=nome, cpf=cpf,
                cargo=cargo, setor=setor,
            )
        elif not func.ativo:
            func.ativo = True
            func.save(update_fields=["ativo"])

        cred_por_email = CredencialAppFuncionario.objects.filter(email=email_app).first()
        cred_do_func = CredencialAppFuncionario.objects.filter(funcionario=func).first()

        if cred_por_email and cred_do_func and cred_por_email.pk != cred_do_func.pk:
            # O e-mail-alvo pertence a OUTRO funcionário e este func já tem uma
            # credencial diferente. Remove a credencial atual do func e
            # reaponta a credencial do e-mail para ele (OneToOne fica consistente).
            cred_do_func.delete()
            cred = cred_por_email
            cred.funcionario = func
        elif cred_por_email:
            # Existe credencial com o e-mail-alvo (pode já ser deste func).
            cred = cred_por_email
            cred.funcionario = func
        elif cred_do_func:
            # Func tem credencial com OUTRO e-mail — atualiza o e-mail dele.
            cred = cred_do_func
            cred.email = email_app
        else:
            cred = CredencialAppFuncionario(funcionario=func, email=email_app)

        cred.senha = make_password(senha_app)
        cred.ativo = True
        cred.save()
        self.out(f"  ✅ {email_app} garantido", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS OCUPACIONAIS DO APP — idempotente, seguro em produção
    # ─────────────────────────────────────────────────────────────────────────
    def _garantir_dados_app_demo(self):
        """Garante que os trabalhadores demo do app (Luiz e Carlos) tenham
        dados ocupacionais visíveis — ASO, exames, treinamentos NR, EPIs e
        notificações — para que as telas do app NÃO apareçam vazias na revisão
        da App Store (Guideline 2.3.3 — screenshots "app em uso").

        Por que aqui (e não no _criar_dados_sst)? Em produção a empresa demo
        SST já existe, então o bloco rico de _criar_dados_sst é PULADO pelo
        --upsert; os trabalhadores são criados só por _garantir_credenciais_app
        (sem dado ocupacional). Este método preenche esse vão.

        Idempotente: cada bloco só cria o que falta (exists/get_or_create),
        nunca deleta nada e roda em savepoints para nunca abortar o deploy.
        """
        from api.models import (
            Empresa, FuncionarioSST,
            ASOOcupacional, ExameOcupacional, TreinamentoNR,
            EPIItem, EntregaEPI, NotificacaoFuncionario,
        )

        empresa = Empresa.objects.filter(email="demo.sst@soluscrt.com").first()
        if not empresa:
            self.out("  ⚠ empresa demo SST inexistente — sem dados ocupacionais a criar", self.style.WARNING)
            return

        def _func(cpf, nome):
            f = FuncionarioSST.objects.filter(empresa=empresa, cpf=cpf).first()
            if not f:
                f = FuncionarioSST.objects.filter(empresa=empresa, nome=nome).first()
            return f

        luiz = _func("111.222.333-44", "Luiz Oliveira")
        carlos = _func("333.444.555-66", "Carlos Alberto Lima")

        # Catálogo de EPI compartilhado (get_or_create por empresa + nº do CA).
        # (CA: nome, tipo, validade_ca, fornecedor, descrição)
        catalogo = {
            "22347": ("Protetor Auditivo de Inserção Espuma 3M 1100", "auditiva",
                      datetime.date(2027, 8, 31), "3M Brasil", "Espuma de PU, NRRsf 27 dB, descartável"),
            "15943": ("Óculos de Proteção Ampla Visão Incolor", "visual",
                      datetime.date(2027, 9, 30), "Uvex do Brasil", "Policarbonato, antirrisco, antiembaçante"),
            "31469": ("Capacete de Segurança ABS Aba Total Classe A", "cabeca",
                      datetime.date(2028, 9, 30), "Planat Proteções", "ABS, aba completa, classe A, suspensão 8 pontos"),
            "26694": ("Bota de Borracha PVC Bicolor Cano 28 cm", "pes",
                      datetime.date(2028, 8, 31), "Bracol Safety", "PVC bicolor, cano 28 cm, bico de aço, antiderrapante"),
            "25261": ("Cinto de Segurança Tipo Paraquedista 5 Pontos", "altura",
                      datetime.date(2027, 11, 30), "Pioner Equipamentos", "Trava dupla, 5 pontos, ABNT NBR 14626"),
            "13071": ("Óculos de Segurança Lente Incolor Steelflex", "visual",
                      datetime.date(2028, 1, 31), "Steelflex Safety", "Haste ajustável, impacto médio"),
            "13026": ("Luva de Raspa de Couro Cano Curto", "maos",
                      datetime.date(2028, 2, 28), "Capivaseg EPIs", "Raspa bovino, proteção contra cortes e calor moderado"),
            "11697": ("Sapato de Segurança Couro c/ Bico de Aço", "pes",
                      datetime.date(2027, 5, 31), "Marluvas Calçados", "Couro bovino, bico aço, solado antiderrapante"),
        }

        def _epi(ca):
            nome, tipo, val_ca, forn, desc = catalogo[ca]
            obj, _ = EPIItem.objects.get_or_create(
                empresa=empresa, ca_numero=ca,
                defaults=dict(nome=nome, tipo=tipo, validade_ca=val_ca,
                              fornecedor=forn, descricao=desc, ativo=True),
            )
            return obj

        plano = []
        if luiz:
            plano.append(dict(
                func=luiz,
                aso=("periodico", "apto", datetime.date(2026, 3, 29), datetime.date(2027, 3, 29),
                     "Audiometria, Hemograma, Glicemia, Acuidade Visual"),
                exames=[
                    ("audiometria",     "Normal — limiar auditivo dentro dos padrões"),
                    ("acuidade_visual", "20/20 binocular — dentro do padrão"),
                    ("laboratorial",    "Hemograma: normal / Glicemia: 92 mg/dL"),
                ],
                treinos=[
                    ("NR-35", "Trabalho em Altura", 8,
                     datetime.date(2025, 12, 14), datetime.date(2026, 12, 14), "valido"),
                    ("NR-6", "Utilização e Conservação de EPIs", 4,
                     datetime.date(2025, 6, 10), datetime.date(2027, 6, 10), "valido"),
                    ("NR-5", "CIPA — Comissão Interna de Prevenção de Acidentes", 8,
                     datetime.date(2024, 11, 8), datetime.date(2026, 11, 8), "valido"),
                    ("NR-10", "Segurança em Instalações e Serviços em Eletricidade", 40,
                     datetime.date(2025, 5, 23), datetime.date(2026, 5, 23), "vencido"),
                ],
                epis=["22347", "15943", "31469", "26694", "25261"],
                notifs=[
                    ("treinamento", "NR-10 vencido ⚠️",
                     "Seu treinamento NR-10 (Eletricidade) venceu em 23/05/2026. Procure o SESMT para reciclagem."),
                    ("aso", "ASO válido ✅",
                     "Seu ASO periódico está válido até 29/03/2027."),
                ],
            ))
        if carlos:
            plano.append(dict(
                func=carlos,
                aso=("periodico", "apto", datetime.date(2025, 12, 10), datetime.date(2026, 12, 10),
                     "Audiometria, Espirometria, Hemograma"),
                exames=[],
                treinos=[
                    ("NR-12", "Segurança no Trabalho em Máquinas e Equipamentos", 8,
                     datetime.date(2026, 2, 10), datetime.date(2027, 2, 10), "valido"),
                    ("NR-6", "Utilização e Conservação de EPIs", 4,
                     datetime.date(2025, 8, 14), datetime.date(2027, 8, 14), "valido"),
                ],
                epis=["22347", "13071", "13026", "11697"],
                notifs=[
                    ("exame", "Novo pedido de exame 🔬",
                     "ASO periódico agendado para 10/06/2026. Compareça em jejum de 8h."),
                ],
            ))

        if not plano:
            self.out("  ⚠ trabalhadores demo (Luiz/Carlos) inexistentes — nada a popular", self.style.WARNING)
            return

        for spec in plano:
            func = spec["func"]

            # ASO + exames vinculados
            try:
                with transaction.atomic():
                    aso_obj = ASOOcupacional.objects.filter(funcionario=func).order_by("-data_emissao").first()
                    if not aso_obj:
                        tipo, resultado, emissao, validade, riscos = spec["aso"]
                        aso_obj = ASOOcupacional.objects.create(
                            empresa=empresa, funcionario=func, tipo=tipo, resultado=resultado,
                            data_emissao=emissao, data_validade=validade,
                            medico_responsavel="Dra. Patricia Nunes Costa", crm="CRM/SP 34872",
                            riscos_ocupacionais=riscos,
                        )
                    for tipo_ex, resultado_ex in spec["exames"]:
                        if not ExameOcupacional.objects.filter(funcionario=func, tipo_exame=tipo_ex).exists():
                            ExameOcupacional.objects.create(
                                empresa=empresa, funcionario=func, aso=aso_obj,
                                tipo_exame=tipo_ex, status="realizado", resultado=resultado_ex,
                                data_realizacao=aso_obj.data_emissao, data_validade=aso_obj.data_validade,
                            )
            except Exception as exc:  # noqa: BLE001
                self.out(f"  ⚠ ASO/exames {func.nome} falhou: {exc}", self.style.WARNING)

            # Treinamentos NR
            try:
                with transaction.atomic():
                    for nr, titulo, horas, realiz, validade, status_t in spec["treinos"]:
                        if not TreinamentoNR.objects.filter(funcionario=func, nr=nr).exists():
                            TreinamentoNR.objects.create(
                                empresa=empresa, funcionario=func, nr=nr, titulo=titulo,
                                carga_horaria=horas, data_realizacao=realiz, data_validade=validade,
                                status=status_t, instrutor="SolusCRT Treinamentos Ltda",
                            )
            except Exception as exc:  # noqa: BLE001
                self.out(f"  ⚠ treinamentos {func.nome} falhou: {exc}", self.style.WARNING)

            # EPIs entregues
            try:
                with transaction.atomic():
                    for ca in spec["epis"]:
                        epi_item = _epi(ca)
                        if not EntregaEPI.objects.filter(funcionario=func, epi=epi_item).exists():
                            EntregaEPI.objects.create(
                                empresa=empresa, funcionario=func, epi=epi_item,
                                data_entrega=datetime.date(2026, 3, 1), quantidade=1,
                            )
            except Exception as exc:  # noqa: BLE001
                self.out(f"  ⚠ EPIs {func.nome} falhou: {exc}", self.style.WARNING)

            # Notificações in-app
            try:
                with transaction.atomic():
                    for tipo_n, titulo_n, msg_n in spec["notifs"]:
                        if not NotificacaoFuncionario.objects.filter(funcionario=func, titulo=titulo_n).exists():
                            NotificacaoFuncionario.objects.create(
                                empresa=empresa, funcionario=func,
                                tipo=tipo_n, titulo=titulo_n, mensagem=msg_n,
                            )
            except Exception as exc:  # noqa: BLE001
                self.out(f"  ⚠ notificações {func.nome} falhou: {exc}", self.style.WARNING)

            self.out(f"  ✅ dados ocupacionais garantidos p/ {func.nome}", self.style.SUCCESS)

    # ─────────────────────────────────────────────────────────────────────────
    # REFRESH DADOS — recria dados sem deletar contas
    # ─────────────────────────────────────────────────────────────────────────
    def _refresh_dados_demos(self):
        """
        Para cada conta demo existente:
          1. Deleta todos os dados demo relacionados (via cascade, por segmento)
             Mantém Empresa + EmpresaUsuario intactos.
          2. Recria todos os dados com a versão mais recente.

        Seguro em produção — não toca em e-mails, senhas ou planos.
        """
        from api.models import (
            Empresa,
            # SST
            FuncionarioSST, EPIItem, RiscoOcupacional,
            DocumentoSST, SolicitacaoExame, ComissaoCIPA,
            ClinicaCredenciada, VinculoClinicaEmpresa,
            PostoTrabalho, ConfiguracaoSST,
            # Farmácia
            FornecedorFarmacia, ItemFarmacia, PacienteFarmacia,
            InventarioFarmacia, PedidoCompraFarmacia,
            # Hospital
            DepartamentoHospital, PacienteHospital,
            # Governo
            ProgramaSaudeGov, IndicadorSaudeGov, UnidadeSaude,
            AlertaGovernamental, SerieEpidemiologica, RegistroSintoma,
            # Plano
            PlanoSaude, PrestadorPlanoSaude,
        )
        try:
            from api.models import OrcamentoSaudeGov, PlanoAcaoGov, AtoNormativoGov
        except ImportError:
            OrcamentoSaudeGov = PlanoAcaoGov = AtoNormativoGov = None

        def _limpar_sst(empresa):
            FuncionarioSST.objects.filter(empresa=empresa).delete()
            EPIItem.objects.filter(empresa=empresa).delete()
            RiscoOcupacional.objects.filter(empresa=empresa).delete()
            DocumentoSST.objects.filter(empresa=empresa).delete()
            SolicitacaoExame.objects.filter(empresa=empresa).delete()
            ComissaoCIPA.objects.filter(empresa=empresa).delete()
            PostoTrabalho.objects.filter(empresa=empresa).delete()
            VinculoClinicaEmpresa.objects.filter(empresa_contratante=empresa).delete()
            ClinicaCredenciada.objects.filter(
                cnpj__in=["11.222.333/0001-44", "03.773.700/0001-55", "44.555.666/0001-77"]
            ).delete()
            try:
                ConfiguracaoSST.objects.filter(empresa=empresa).delete()
            except Exception:
                pass

        def _limpar_farmacia(empresa):
            # cascade: ItemFarmacia → LoteMedicamento, MovimentoEstoque,
            #          ReceitaMedica, DispensacaoMedicamento, ItemPedidoCompra
            #          InventarioFarmacia → ItemInventario
            InventarioFarmacia.objects.filter(empresa=empresa).delete()
            PedidoCompraFarmacia.objects.filter(empresa=empresa).delete()
            ItemFarmacia.objects.filter(empresa=empresa).delete()
            PacienteFarmacia.objects.filter(empresa=empresa).delete()
            FornecedorFarmacia.objects.filter(empresa=empresa).delete()
            try:
                from api.models import DescarteItemFarmacia
                DescarteItemFarmacia.objects.filter(empresa=empresa).delete()
            except Exception:
                pass

        def _limpar_hospital(empresa):
            # cascade: DepartamentoHospital → LeitoHospital → InternacaoHospital
            #          PacienteHospital → TriagemHospital, InternacaoHospital
            PacienteHospital.objects.filter(empresa=empresa).delete()
            DepartamentoHospital.objects.filter(empresa=empresa).delete()

        def _limpar_governo(empresa):
            if OrcamentoSaudeGov:
                OrcamentoSaudeGov.objects.filter(empresa=empresa).delete()
            if PlanoAcaoGov:
                PlanoAcaoGov.objects.filter(empresa=empresa).delete()
            if AtoNormativoGov:
                AtoNormativoGov.objects.filter(empresa=empresa).delete()
            IndicadorSaudeGov.objects.filter(empresa=empresa).delete()
            ProgramaSaudeGov.objects.filter(empresa=empresa).delete()
            AlertaGovernamental.objects.filter(empresa=empresa).delete()
            RegistroSintoma.objects.filter(empresa=empresa).delete()
            UnidadeSaude.objects.filter(empresa=empresa).delete()
            try:
                from api.models import TeleconsultaGoverno
                TeleconsultaGoverno.objects.filter(empresa=empresa).delete()
            except Exception:
                pass
            try:
                SerieEpidemiologica.objects.filter(empresa=empresa).delete()
            except Exception:
                pass

        def _limpar_plano(empresa):
            # cascade: PlanoSaude → BeneficiarioPlano → GuiaAutorizacao, Sinistro, Reembolso
            PlanoSaude.objects.filter(empresa=empresa).delete()
            PrestadorPlanoSaude.objects.filter(empresa=empresa).delete()
            try:
                from api.models import CarenciaBeneficiario, CoparticipacaoRegra, FaturamentoBeneficiario, RedeCredenciadaPlano
                RedeCredenciadaPlano.objects.filter(empresa=empresa).delete()
                FaturamentoBeneficiario.objects.filter(empresa=empresa).delete()
            except Exception:
                pass

        demos_mapa = {
            "demo.sst@soluscrt.com":      (_limpar_sst,      self._criar_dados_sst),
            "demo.farmacia@soluscrt.com":  (_limpar_farmacia, self._criar_dados_farmacia),
            "demo.hospital@soluscrt.com":  (_limpar_hospital, self._criar_dados_hospital),
            "demo.governo@soluscrt.com":   (_limpar_governo,  self._criar_dados_governo),
            "demo.plano@soluscrt.com":     (_limpar_plano,    self._criar_dados_plano),
        }

        for email, (limpar_fn, dados_fn) in demos_mapa.items():
            empresa = Empresa.objects.filter(email=email).first()
            if not empresa:
                self.out(f"  ⚠  {email} não encontrada — pulando", self.style.WARNING)
                continue

            self.out(f"\n  🔄 Limpando dados de {email}...", self.style.WARNING)
            try:
                limpar_fn(empresa)
            except Exception as exc:
                self.out(f"  ⚠ Limpeza parcial para {email}: {exc}", self.style.WARNING)

            self.out(f"  📥 Recriando dados para {email}...")
            try:
                with transaction.atomic():
                    dados_fn(empresa)
                self.out(f"  ✅ {email} — dados atualizados", self.style.SUCCESS)
            except Exception as exc:
                self.out(f"  ⚠ {email} falhou (parcial): {exc}", self.style.WARNING)

        self._recria_dono_saas()
        self.out(f"\n  ✅ Refresh concluído!\n", self.style.SUCCESS)

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
    def _criar_dados_farmacia(self, empresa):  # noqa: C901
        from api.models import (
            ItemFarmacia, LoteMedicamento, FornecedorFarmacia,
            PacienteFarmacia, ReceitaMedica, DispensacaoMedicamento,
            MovimentoEstoque, PedidoCompraFarmacia, ItemPedidoCompra,
            InventarioFarmacia, ItemInventario, DescarteItemFarmacia,
        )

        # ── 1. Fornecedores ─────────────────────────────────────────────────
        fornecedores_data = [
            ("Distribuidora MedFarma Ltda",        "12.345.678/0001-90", "contato@medfarma.com.br",       "(11) 3344-5566"),
            ("EMS Distribuidora de Medicamentos",  "33.066.064/0001-17", "vendas@ems.com.br",             "(11) 4133-2000"),
            ("Cimed Industrial Ltda",              "07.601.774/0001-84", "distribuicao@cimed.com.br",     "(35) 3215-5100"),
            ("Profarma Distribuidora",             "04.394.387/0001-14", "comercial@profarma.com.br",     "(21) 3503-2200"),
            ("Precision Rx Distribuidora",         "55.123.456/0001-33", "pedidos@precisionrx.com.br",    "(11) 5098-7700"),
        ]
        forn_objs = []
        for nome_f, cnpj_f, email_f, tel_f in fornecedores_data:
            try:
                f = FornecedorFarmacia.objects.create(
                    empresa=empresa, nome=nome_f, cnpj=cnpj_f,
                    contato=email_f, email=email_f, telefone=tel_f, ativo=True,
                )
                forn_objs.append(f)
            except Exception:
                forn_objs.append(None)

        forn1 = forn_objs[0]
        forn2 = forn_objs[1] if len(forn_objs) > 1 else forn1
        forn3 = forn_objs[2] if len(forn_objs) > 2 else forn1

        # ── 2. Medicamentos / Itens (40 itens) ──────────────────────────────
        # (nome, codigo, categoria, unidade, estoque_atual, estoque_minimo, fornecedor)
        itens_data = [
            # Analgésicos/Antitérmicos
            ("Paracetamol 750mg",               "7891058010283", "medicamento", "comprimido",  200, 50, forn1),
            ("Dipirona Sódica 500mg",            "7896714800042", "medicamento", "comprimido",  180, 40, forn1),
            ("Ibuprofeno 600mg",                 "7896714800037", "medicamento", "comprimido",  150, 30, forn2),
            ("Nimesulida 100mg",                 "7891058023801", "medicamento", "comprimido",  100, 25, forn2),
            ("Cetoprofeno 100mg",                "7898166710123", "medicamento", "cápsula",      80, 20, forn2),
            # Antibióticos
            ("Amoxicilina 500mg",                "7896714800038", "medicamento", "cápsula",     120, 30, forn1),
            ("Azitromicina 500mg",               "7891058045611", "medicamento", "comprimido",   90, 20, forn1),
            ("Ciprofloxacino 500mg",             "7891217100192", "medicamento", "comprimido",   75, 15, forn3),
            ("Amoxicilina + Clavulanato 875mg",  "7896658240130", "medicamento", "comprimido",   60, 15, forn3),
            # Cardiovasculares
            ("Atorvastatina 20mg",               "7896714800039", "medicamento", "comprimido",  160, 40, forn2),
            ("Losartana Potássica 50mg",          "7896714800043", "medicamento", "comprimido",  190, 45, forn2),
            ("Anlodipino 5mg",                   "7891058054490", "medicamento", "comprimido",  140, 35, forn1),
            ("Enalapril 10mg",                   "7891058010177", "medicamento", "comprimido",  130, 30, forn1),
            ("Carvedilol 25mg",                  "7896714800051", "medicamento", "comprimido",   85, 20, forn2),
            ("AAS 100mg (Aspirina)",             "7891058010145", "medicamento", "comprimido",  220, 50, forn1),
            # Antidiabéticos
            ("Metformina 850mg",                 "7896714800040", "medicamento", "comprimido",  175, 40, forn2),
            ("Glibenclamida 5mg",                "7891058016827", "medicamento", "comprimido",   95, 20, forn2),
            ("Sitagliptina 100mg",               "7896714800062", "medicamento", "comprimido",   50, 12, forn3),
            # Antiulcerosos/GI
            ("Omeprazol 20mg",                   "7896714800041", "medicamento", "cápsula",     200, 50, forn1),
            ("Pantoprazol 40mg",                 "7896714800059", "medicamento", "comprimido",  155, 35, forn1),
            ("Ranitidina 150mg",                 "7891058017275", "medicamento", "comprimido",   80, 20, forn2),
            ("Domperidona 10mg",                 "7891058025966", "medicamento", "comprimido",   90, 20, forn2),
            # Respiratórios
            ("Salbutamol 100mcg Spray",          "7896660680090", "medicamento", "frasco",       35, 10, forn3),
            ("Budesonida 200mcg Spray",          "7896660680101", "medicamento", "frasco",       28, 8,  forn3),
            ("Loratadina 10mg",                  "7891058011426", "medicamento", "comprimido",  160, 35, forn1),
            ("Desloratadina 5mg",                "7896714800073", "medicamento", "comprimido",  110, 25, forn2),
            # Psicotrópicos
            ("Fluoxetina 20mg",                  "7896714800084", "medicamento", "cápsula",      60, 15, forn3),
            ("Sertralina 50mg",                  "7896714800091", "medicamento", "comprimido",   55, 12, forn3),
            ("Clonazepam 2mg",                   "7896714800108", "medicamento", "comprimido",   40, 10, forn3),
            ("Alprazolam 0,5mg",                 "7896714800115", "medicamento", "comprimido",   30, 8,  forn3),
            # Vitaminas/Suplementos
            ("Vitamina D3 2000 UI",              "7896714800122", "medicamento", "cápsula",     180, 40, forn1),
            ("Vitamina C 1g Efervescente",       "7891058030069", "medicamento", "comprimido",  250, 50, forn1),
            ("Sulfato Ferroso 40mg",             "7891058010252", "medicamento", "comprimido",  120, 30, forn2),
            ("Ácido Fólico 5mg",                 "7891058010269", "medicamento", "comprimido",   90, 20, forn2),
            # Materiais / Insumos
            ("Luva Procedimento M (cx 100)",     "7890001000001", "material",    "caixa",        25, 5,  forn1),
            ("Seringa 5ml c/ Agulha (cx 100)",   "7890001000002", "material",    "caixa",        30, 8,  forn1),
            ("Curativo Adesivo (cx 100)",         "7890001000003", "material",    "caixa",        40, 10, forn2),
            ("Álcool 70% 1L",                    "7890001000004", "insumo",      "litro",        50, 15, forn2),
            ("Soro Fisiológico 0,9% 500ml",      "7890001000005", "insumo",      "frasco",       60, 20, forn1),
        ]

        item_objs = []
        for nome_i, cod_i, cat_i, unid_i, est_i, esmin_i, forn_i in itens_data:
            try:
                it = ItemFarmacia.objects.create(
                    empresa=empresa, fornecedor=forn_i,
                    nome=nome_i, codigo=cod_i, categoria=cat_i,
                    unidade_medida=unid_i,
                    estoque_atual=est_i, estoque_minimo=esmin_i, ativo=True,
                )
                item_objs.append(it)
            except Exception:
                item_objs.append(None)

        # ── 3. Lotes ─────────────────────────────────────────────────────────
        import random as _rnd
        _rnd.seed(99)
        for idx, it in enumerate(item_objs):
            if not it:
                continue
            # Lote principal — validade normal
            try:
                LoteMedicamento.objects.create(
                    empresa=empresa, item=it,
                    numero_lote=f"L{idx+1:03d}2025A",
                    quantidade_inicial=it.estoque_atual,
                    quantidade_atual=it.estoque_atual,
                    data_fabricacao=datetime.date(2024, _rnd.randint(1, 12), 1),
                    data_validade=datetime.date(2027, _rnd.randint(1, 12), 30),
                )
            except Exception:
                pass
            # Lote secundário — vencendo / vencido (para alertas)
            if idx % 5 == 0:
                try:
                    LoteMedicamento.objects.create(
                        empresa=empresa, item=it,
                        numero_lote=f"L{idx+1:03d}2023B",
                        quantidade_inicial=20,
                        quantidade_atual=20,
                        data_fabricacao=datetime.date(2022, 6, 1),
                        data_validade=datetime.date(2026, 4, 30),  # vencido
                    )
                except Exception:
                    pass

        # ── 4. Pacientes ──────────────────────────────────────────────────────
        pacientes_farm = [
            ("Ana Lima Ferreira",       "111.222.333-01", datetime.date(1958, 3, 15), "F", "(11)99111-1111", "HAS; DM2", "Losartana 50mg; Metformina 850mg"),
            ("João Carlos Souza",       "222.333.444-02", datetime.date(1945, 7, 20), "M", "(11)99222-2222", "Cardiopatia isquêmica", "AAS 100mg; Atorvastatina 20mg; Enalapril"),
            ("Maria Aparecida Costa",   "333.444.555-03", datetime.date(1962, 11, 8), "F", "(11)99333-3333", "Hipotireoidismo; HAS", "Losartana; Vitamina D3"),
            ("Pedro Henrique Alves",    "444.555.666-04", datetime.date(1978, 4, 2),  "M", "(11)99444-4444", "", "Omeprazol 20mg"),
            ("Fernanda Silva Santos",   "555.666.777-05", datetime.date(1990, 9, 22), "F", "(11)99555-5555", "Depressão; ansiedade", "Fluoxetina 20mg; Clonazepam"),
            ("Carlos Eduardo Lima",     "666.777.888-06", datetime.date(1985, 6, 14), "M", "(11)99666-6666", "Rinite alérgica", "Loratadina 10mg"),
            ("Beatriz Nunes Torres",    "777.888.999-07", datetime.date(1970, 1, 30), "F", "(11)99777-7777", "DM2; Obesidade", "Metformina; Sitagliptina"),
            ("Roberto Melo Barros",     "888.999.000-08", datetime.date(1952, 8, 5),  "M", "(11)99888-8888", "DPOC; HAS; Dislipidemia", "Salbutamol; Budesonida; Losartana"),
            ("Juliana Pires Moura",     "999.000.111-09", datetime.date(1995, 12, 18),"F", "(11)99999-9999", "Asma leve persistente", "Salbutamol; Fluticasona"),
            ("Antônio José Ribeiro",    "000.111.222-10", datetime.date(1940, 5, 10), "M", "(11)90000-0000", "IC; FA; DM2", "Carvedilol; AAS; Metformina; Furosemida"),
        ]
        pac_objs = []
        for nome_p, cpf_p, nasc_p, sexo_p, tel_p, cond_p, med_p in pacientes_farm:
            try:
                p = PacienteFarmacia.objects.create(
                    empresa=empresa, nome=nome_p, cpf=cpf_p,
                    data_nascimento=nasc_p, sexo=sexo_p, telefone=tel_p,
                    condicoes_cronicas=cond_p,
                    medicamentos_uso_continuo=med_p, ativo=True,
                )
                pac_objs.append(p)
            except Exception:
                pac_objs.append(None)

        # ── 5. Receitas e Dispensações ────────────────────────────────────────
        receitas_data = [
            # (paciente_idx, item_idx, tipo, numero, medico, crm, data_em, posologia, status, qtd)
            (0, 10, "simples", "REC-2026-001", "Dr. Marcos Cardoso",  "CRM/SP 12345", datetime.date(2026, 3, 1), "1 cp ao dia", "dispensada", 2),
            (0, 15, "simples", "REC-2026-002", "Dr. Marcos Cardoso",  "CRM/SP 12345", datetime.date(2026, 3, 1), "1 cp 2x ao dia jejum", "dispensada", 2),
            (1, 9,  "simples", "REC-2026-003", "Dra. Ana Cardio",     "CRM/SP 22345", datetime.date(2026, 2, 15), "1 cp ao dia à noite", "dispensada", 3),
            (1, 14, "simples", "REC-2026-004", "Dra. Ana Cardio",     "CRM/SP 22345", datetime.date(2026, 2, 15), "1 cp ao dia", "pendente",   2),
            (4, 26, "especial_amarela","REC-2026-005","Dra. Vera Psiq","CRM/SP 33456", datetime.date(2026, 4, 10), "1 cp ao dia pela manhã", "dispensada", 1),
            (4, 28, "especial_amarela","REC-2026-006","Dra. Vera Psiq","CRM/SP 33456", datetime.date(2026, 4, 10), "1/2 cp à noite", "pendente",   1),
            (6, 15, "simples", "REC-2026-007", "Dr. João Endo",       "CRM/SP 44567", datetime.date(2026, 3, 20), "1 cp 2x ao dia", "dispensada", 2),
            (6, 17, "simples", "REC-2026-008", "Dr. João Endo",       "CRM/SP 44567", datetime.date(2026, 3, 20), "1 cp ao dia", "dispensada",  1),
            (7, 22, "simples", "REC-2026-009", "Dr. Paulo Pneumo",    "CRM/SP 55678", datetime.date(2026, 4, 5),  "2 jatos 4x ao dia", "dispensada", 2),
            (2, 0,  "simples", "REC-2026-010", "Dra. Carla Clínica",  "CRM/SP 66789", datetime.date(2026, 5, 2),  "1 cp de 6h em 6h por 5 dias", "pendente", 1),
            (5, 24, "simples", "REC-2026-011", "Dr. Fernando Alergo", "CRM/SP 77890", datetime.date(2026, 5, 10), "1 cp ao dia à noite", "pendente", 2),
        ]
        for pac_idx, item_idx, tipo_r, num_r, med_r, crm_r, data_em_r, pos_r, status_r, qtd_r in receitas_data:
            pac_obj = pac_objs[pac_idx] if pac_idx < len(pac_objs) else None
            item_obj = item_objs[item_idx] if item_idx < len(item_objs) else None
            if not item_obj:
                continue
            try:
                rec = ReceitaMedica.objects.create(
                    empresa=empresa,
                    paciente=pac_obj,
                    paciente_nome=pac_obj.nome if pac_obj else "",
                    paciente_cpf=pac_obj.cpf if pac_obj else "",
                    tipo=tipo_r, numero_receita=num_r,
                    medico_nome=med_r, medico_crm=crm_r,
                    data_emissao=data_em_r,
                    data_validade=datetime.date(data_em_r.year, data_em_r.month, data_em_r.day)
                    + datetime.timedelta(days=30),
                    item=item_obj,
                    quantidade=qtd_r, posologia=pos_r,
                    status=status_r,
                )
                if status_r == "dispensada":
                    disp = DispensacaoMedicamento.objects.create(
                        empresa=empresa, item=item_obj,
                        paciente_nome=pac_obj.nome if pac_obj else "Paciente",
                        paciente_cpf=pac_obj.cpf if pac_obj else "",
                        quantidade=qtd_r,
                        responsavel="Farm. Responsável Demo",
                    )
                    rec.dispensacao = disp
                    rec.save(update_fields=["dispensacao"])
            except Exception:
                pass

        # ── 6. Movimentos de Estoque ──────────────────────────────────────────
        movs_data = [
            # (item_idx, tipo, qtd, motivo, responsavel)
            (0,  "entrada",  100, "Recebimento NF 12345 — MedFarma",   "Farm. Juliana Demo"),
            (1,  "entrada",   80, "Recebimento NF 12346 — MedFarma",   "Farm. Juliana Demo"),
            (5,  "entrada",   60, "Recebimento NF 12347 — MedFarma",   "Farm. Juliana Demo"),
            (9,  "entrada",   70, "Recebimento NF 12348 — EMS",        "Farm. Juliana Demo"),
            (0,  "saida",     10, "Dispensação REC-2026-010",          "Farm. Juliana Demo"),
            (9,  "saida",      5, "Dispensação REC-2026-003",          "Farm. Juliana Demo"),
            (15, "saida",     30, "Dispensação dispensações mensais",  "Farm. Juliana Demo"),
            (34, "ajuste",    -5, "Ajuste inventário — diferença contada", "Farm. Juliana Demo"),
            (5,  "vencimento",-20,"Descarte lote L0062023B — vencido", "Farm. Juliana Demo"),
        ]
        for item_idx, tipo_mv, qtd_mv, motivo_mv, resp_mv in movs_data:
            item_obj = item_objs[item_idx] if item_idx < len(item_objs) else None
            if not item_obj:
                continue
            try:
                ant = item_obj.estoque_atual
                post = ant + qtd_mv
                MovimentoEstoque.objects.create(
                    empresa=empresa, item=item_obj, tipo=tipo_mv,
                    quantidade=qtd_mv, estoque_anterior=ant, estoque_posterior=post,
                    motivo=motivo_mv, responsavel=resp_mv,
                )
            except Exception:
                pass

        # ── 7. Pedidos de Compra ──────────────────────────────────────────────
        try:
            ped1 = PedidoCompraFarmacia.objects.create(
                empresa=empresa, fornecedor=forn1, status="recebido",
                observacoes="Pedido mensal rotina — NF recebida e conferida.",
            )
            for it, qtd in [(item_objs[0], 100), (item_objs[1], 80), (item_objs[5], 60)]:
                if it:
                    ItemPedidoCompra.objects.create(pedido=ped1, item=it, quantidade_solicitada=qtd, quantidade_recebida=qtd)
        except Exception:
            pass
        try:
            ped2 = PedidoCompraFarmacia.objects.create(
                empresa=empresa, fornecedor=forn2, status="aprovado",
                observacoes="Pedido quinzenal cardiovasculares.",
            )
            for it, qtd in [(item_objs[9], 70), (item_objs[10], 80), (item_objs[13], 50)]:
                if it:
                    ItemPedidoCompra.objects.create(pedido=ped2, item=it, quantidade_solicitada=qtd, quantidade_recebida=0)
        except Exception:
            pass
        try:
            ped3 = PedidoCompraFarmacia.objects.create(
                empresa=empresa, fornecedor=forn3, status="enviado",
                observacoes="Reposição urgente psicotrópicos — estoque crítico.",
            )
            for it, qtd in [(item_objs[26], 40), (item_objs[27], 35), (item_objs[28], 30)]:
                if it:
                    ItemPedidoCompra.objects.create(pedido=ped3, item=it, quantidade_solicitada=qtd, quantidade_recebida=0)
        except Exception:
            pass

        # ── 8. Inventário ─────────────────────────────────────────────────────
        try:
            from django.utils import timezone as _tz
            inv = InventarioFarmacia.objects.create(
                empresa=empresa,
                descricao="Inventário Mensal — Maio 2026",
                status="concluido",
                responsavel="Farm. Juliana Demo",
                concluido_em=_tz.now(),
                observacoes="Diferença de -5 unidades em Álcool 70% corrigida.",
            )
            for it in item_objs[:15]:
                if not it:
                    continue
                try:
                    delta = _rnd.randint(-2, 0)
                    ItemInventario.objects.create(
                        inventario=inv, item=it,
                        estoque_sistema=it.estoque_atual,
                        estoque_contado=it.estoque_atual + delta,
                        diferenca=delta, ajustado=(delta != 0),
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # ── 9. Descarte ───────────────────────────────────────────────────────
        if item_objs[5]:
            try:
                DescarteItemFarmacia.objects.create(
                    empresa=empresa, item=item_objs[5],
                    motivo="vencimento", quantidade=20,
                    responsavel="Farm. Juliana Demo",
                    observacoes="Lote L0062023B vencido em 30/04/2026. ABNT NBR 10.004.",
                )
            except Exception:
                pass

        self.out(
            f"     ✓ Farmácia: {len([x for x in item_objs if x])} itens | "
            f"{len([x for x in pac_objs if x])} pacientes | "
            f"3 pedidos de compra | inventário concluído",
            self.style.SUCCESS,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Hospital
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_hospital(self, empresa):
        from api.models import (
            LeitoHospital, DepartamentoHospital, PacienteHospital,
            TriagemHospital, InternacaoHospital,
        )
        try:
            from api.models import PrescricaoMedica, EvolucaoClinica
        except ImportError:
            PrescricaoMedica = EvolucaoClinica = None

        # ── 1. Departamentos ─────────────────────────────────────────────────
        dept_cfg = [
            # (nome, tipo, capacidade, responsavel)
            ("UTI Adulto",                "UTI",        10, "Dr. Renato Souza — CRM/SP 11001"),
            ("Clínica Médica",            "clinica",    20, "Dra. Cristina Alves — CRM/SP 11002"),
            ("Cirurgia Geral",            "cirurgia",   15, "Dr. Fábio Menezes — CRM/SP 11003"),
            ("Pediatria",                 "pediatria",  12, "Dra. Luciana Ferreira — CRM/SP 11004"),
            ("Maternidade / Obstetrícia", "maternidade",10, "Dra. Patrícia Costa — CRM/SP 11005"),
            ("Pronto-Socorro",            "outro",      16, "Dr. Alexandre Lima — CRM/SP 11006"),
            ("Oncologia",                 "outro",       8, "Dra. Márcia Rocha — CRM/SP 11007"),
            ("Neurologia / Neurocirug.",  "outro",       6, "Dr. Eduardo Pinto — CRM/SP 11008"),
        ]
        dept_objs = []
        for nome_d, tipo_d, cap_d, resp_d in dept_cfg:
            try:
                d = DepartamentoHospital.objects.create(
                    empresa=empresa, nome=nome_d, tipo=tipo_d,
                    capacidade_leitos=cap_d, responsavel=resp_d, ativo=True,
                )
                dept_objs.append(d)
            except Exception:
                dept_objs.append(None)

        # ── 2. Leitos (totalizando ~50) ──────────────────────────────────────
        # Cada depto recebe leitos com status variados
        leito_status_ciclo = ["ocupado","ocupado","ocupado","disponivel","manutencao","reservado","ocupado","disponivel"]
        leito_tipo_map = {
            "UTI":        ("uti",       10),
            "clinica":    ("adulto",    20),
            "cirurgia":   ("adulto",    15),
            "pediatria":  ("pediatrico",12),
            "maternidade":("adulto",    10),
            "outro":      ("adulto",    16),
        }
        leito_objs_por_dept = {}   # dept_idx → [leito_obj, ...]
        leito_num_global = 1
        for di, dept in enumerate(dept_objs):
            if not dept:
                leito_objs_por_dept[di] = []
                continue
            tipo_l, qtd_l = leito_tipo_map.get(dept.tipo, ("adulto", 6))
            # Reduza a qtd para o demo (max 8 por depto)
            qtd_l = min(qtd_l, 8)
            leitos_dept = []
            for i in range(qtd_l):
                sigla = dept.nome[:3].upper().replace(" ", "")
                num_l = f"{sigla}{leito_num_global:03d}"
                st_l  = leito_status_ciclo[(leito_num_global + i) % len(leito_status_ciclo)]
                try:
                    lo = LeitoHospital.objects.create(
                        empresa=empresa, departamento=dept,
                        numero=num_l, tipo=tipo_l, status=st_l,
                    )
                    leitos_dept.append(lo)
                except Exception:
                    leitos_dept.append(None)
                leito_num_global += 1
            leito_objs_por_dept[di] = leitos_dept

        # ── 3. Pacientes (15) ────────────────────────────────────────────────
        pacientes_hosp = [
            # (nome, cpf, nasc, sexo, telefone, tipo_sang, alergias, endereco)
            ("José Antônio da Silva",     "101.202.303-10", datetime.date(1958,  3, 10), "M", "(11)99100-1001", "O+",  "Penicilina", "Rua das Flores, 10 — Centro"),
            ("Maria Aparecida Santos",    "202.303.404-20", datetime.date(1945,  7, 22), "F", "(11)99200-2002", "A+",  "",           "Av. Brasil, 200 — Jardim"),
            ("Pedro Henrique Costa",      "303.404.505-30", datetime.date(1982, 11,  5), "M", "(11)99300-3003", "B+",  "Dipirona",   "Rua 7 de Setembro, 30"),
            ("Fernanda Lima Torres",      "404.505.606-40", datetime.date(1990,  6, 18), "F", "(11)99400-4004", "AB-", "",           "Rua XV de Novembro, 45"),
            ("Carlos Eduardo Mendes",     "505.606.707-50", datetime.date(1970,  2, 28), "M", "(11)99500-5005", "A-",  "Látex",      "Av. Paulista, 1000"),
            ("Ana Paula Rodrigues",       "606.707.808-60", datetime.date(1995,  9,  3), "F", "(11)99600-6006", "O-",  "",           "Rua Augusta, 500"),
            ("Roberto Carlos Barros",     "707.808.909-70", datetime.date(1952,  4, 15), "M", "(11)99700-7007", "B-",  "AAS",        "Rua Consolação, 77"),
            ("Juliana Pires Moura",       "808.909.010-80", datetime.date(2001,  1, 30), "F", "(11)99800-8008", "O+",  "",           "Av. Santo Amaro, 300"),
            ("Marcos Vinícius Pinto",     "909.010.111-90", datetime.date(1969, 12,  5), "M", "(11)99900-9009", "A+",  "",           "Rua Vergueiro, 600"),
            ("Beatriz Alves Cunha",       "010.111.212-01", datetime.date(1988,  8, 22), "F", "(11)90100-0010", "AB+", "Contraste",  "Rua Bela Vista, 88"),
            ("Diego Rocha Ferreira",      "111.212.313-11", datetime.date(1978,  5, 10), "M", "(11)90200-0011", "O+",  "",           "Av. Rebouças, 120"),
            ("Cristiane Torres Melo",     "212.313.414-12", datetime.date(1965, 11, 19), "F", "(11)90300-0012", "A+",  "Sulfas",     "Rua da Consolação, 300"),
            ("Alexandre Oliveira Neto",   "313.414.515-13", datetime.date(2005,  3,  7), "M", "(11)90400-0013", "B+",  "",           "Rua Boa Vista, 15"),
            ("Patrícia Costa Souza",      "414.515.616-14", datetime.date(1983,  7, 14), "F", "(11)90500-0014", "O-",  "",           "Av. Indianópolis, 45"),
            ("Antônio José Ribeiro",      "515.616.717-15", datetime.date(1940,  5, 20), "M", "(11)90600-0015", "A-",  "Penicilina", "Rua Funchal, 800"),
        ]
        pac_objs = []
        for nome_p, cpf_p, nasc_p, sexo_p, tel_p, tsang_p, alergia_p, end_p in pacientes_hosp:
            try:
                p = PacienteHospital.objects.create(
                    empresa=empresa, nome=nome_p, cpf=cpf_p,
                    data_nascimento=nasc_p, sexo=sexo_p, telefone=tel_p,
                    tipo_sanguineo=tsang_p, alergias=alergia_p, endereco=end_p,
                )
                pac_objs.append(p)
            except Exception:
                pac_objs.append(None)

        # ── 4. Triagens ───────────────────────────────────────────────────────
        triagens_data = [
            # (pac_idx, prioridade, queixa, pa, temp, sat, fc, responsavel)
            (0, "vermelho", "Dor torácica intensa irradiando para MSE, sudorese, náuseas — suspeita de IAM", "180/110", 37.2, 92, 110, "Enf. Ana Lima"),
            (1, "laranja",  "Dispneia progressiva, edema MMII, crepitações à ausculta bilateral",           "160/100", 36.8,  95,  98, "Enf. Carlos Melo"),
            (2, "amarelo",  "Dor abdominal em FID, Blumberg positivo, suspeita de apendicite aguda",        "120/80",  38.1,  98,  88, "Enf. Ana Lima"),
            (3, "verde",    "Febre há 3 dias, tosse produtiva, mialgia — síndrome gripal",                  "110/70",  38.5,  97,  92, "Enf. Beatriz Torres"),
            (4, "amarelo",  "Crise hipertensiva — PA 200/120, cefaleia intensa, sem déficit focal",         "200/120", 36.5,  97, 105, "Enf. Carlos Melo"),
            (5, "azul",     "Consulta de rotina — retirada de pontos após procedimento ambulatorial",       "120/75",  36.2,  99,  72, "Enf. Ana Lima"),
            (6, "laranja",  "Rebaixamento de consciência, Glasgow 10, HGT 42 mg/dL — hipoglicemia grave",   "90/60",   36.0,  94, 115, "Enf. Beatriz Torres"),
            (7, "verde",    "Náuseas, vômitos repetidos, desidratação leve — gastroenterite aguda",         "105/65",  37.8,  98,  90, "Enf. Carlos Melo"),
        ]
        triagem_objs = []
        for pac_idx, prior, queixa, pa, temp, sat, fc, resp in triagens_data:
            pac = pac_objs[pac_idx] if pac_idx < len(pac_objs) else None
            if not pac:
                triagem_objs.append(None)
                continue
            try:
                t = TriagemHospital.objects.create(
                    empresa=empresa, paciente=pac, prioridade=prior,
                    queixa_principal=queixa, pressao_arterial=pa,
                    temperatura=temp, saturacao=sat, frequencia_cardiaca=fc,
                    responsavel=resp,
                )
                triagem_objs.append(t)
            except Exception:
                triagem_objs.append(None)

        # ── 5. Internações com prescrições e evoluções ────────────────────────
        # Pega leitos ocupados dos deptos 0 (UTI) e 1 (Clínica Médica)
        leitos_uti    = [l for l in leito_objs_por_dept.get(0, []) if l and l.status == "ocupado"]
        leitos_clinica= [l for l in leito_objs_por_dept.get(1, []) if l and l.status == "ocupado"]
        leitos_cirur  = [l for l in leito_objs_por_dept.get(2, []) if l and l.status == "ocupado"]

        internacoes_data = [
            # (pac_idx, leito_lista_idx, leito_lista, diag, medico, status)
            (0,  0, leitos_uti,     "IAM com supra de ST anterior — submetido a angioplastia primária", "Dr. Renato Souza — CRM/SP 11001",    "ativa"),
            (1,  1, leitos_uti,     "Insuficiência Cardíaca Descompensada — fração de ejeção 25%",      "Dr. Renato Souza — CRM/SP 11001",    "ativa"),
            (2,  0, leitos_clinica, "Pneumonia Bacteriana — lobar direita — CID J18.1",                 "Dra. Cristina Alves — CRM/SP 11002", "ativa"),
            (4,  1, leitos_clinica, "Crise Hipertensiva — controle PA e investigação órgão-alvo",       "Dra. Cristina Alves — CRM/SP 11002", "ativa"),
            (6,  0, leitos_cirur,   "Apendicite Aguda — pós-apendicectomia videolaparoscópica",         "Dr. Fábio Menezes — CRM/SP 11003",   "alta"),
            (9,  1, leitos_cirur,   "Colecistite Aguda Calculosa — colecistectomia laparoscópica",      "Dr. Fábio Menezes — CRM/SP 11003",   "ativa"),
            (14, 2, leitos_uti,     "AVC Isquêmico extenso hemisfério esquerdo — CID I63.3",            "Dr. Eduardo Pinto — CRM/SP 11008",   "ativa"),
        ]
        intern_objs = []
        for pac_idx, leito_idx, leito_lista, diag, med, status_i in internacoes_data:
            pac   = pac_objs[pac_idx] if pac_idx < len(pac_objs) else None
            leito = leito_lista[leito_idx] if leito_idx < len(leito_lista) else None
            if not pac:
                intern_objs.append(None)
                continue
            try:
                inn = InternacaoHospital.objects.create(
                    empresa=empresa, paciente=pac, leito=leito,
                    diagnostico=diag, medico_responsavel=med, status=status_i,
                )
                intern_objs.append(inn)
            except Exception:
                intern_objs.append(None)

        # Prescrições para internações ativas
        prescricoes_data = [
            # (intern_idx, medicamento, dose, via, freq, duracao, status, medico)
            (0, "AAS 100mg",              "100mg",    "oral",       "1x ao dia",    30, "ativa", "Dr. Renato Souza"),
            (0, "Clopidogrel 75mg",       "75mg",     "oral",       "1x ao dia",    30, "ativa", "Dr. Renato Souza"),
            (0, "Heparina Sódica 5000 UI","5000 UI",  "ev",         "6/6h",          7, "ativa", "Dr. Renato Souza"),
            (0, "Nitroglicerina",         "5 mcg/min","ev",         "contínuo SN",   2, "ativa", "Dr. Renato Souza"),
            (1, "Furosemida 40mg",        "40mg",     "ev",         "12/12h",        5, "ativa", "Dr. Renato Souza"),
            (1, "Espironolactona 25mg",   "25mg",     "oral",       "1x ao dia",    30, "ativa", "Dr. Renato Souza"),
            (1, "Carvedilol 12,5mg",      "12,5mg",   "oral",       "12/12h",       30, "ativa", "Dr. Renato Souza"),
            (2, "Amoxicilina+Clavulanato","875/125mg","oral",       "12/12h",        7, "ativa", "Dra. Cristina Alves"),
            (2, "Azitromicina 500mg",     "500mg",    "oral",       "1x ao dia",     5, "ativa", "Dra. Cristina Alves"),
            (2, "Paracetamol 750mg",      "750mg",    "oral",       "6/6h SN",       7, "ativa", "Dra. Cristina Alves"),
            (3, "Captopril 25mg",         "25mg",     "sublingual", "SN crise HAS",  0, "ativa", "Dra. Cristina Alves"),
            (3, "Losartana 100mg",        "100mg",    "oral",       "1x ao dia",    30, "ativa", "Dra. Cristina Alves"),
            (5, "Dipirona 500mg",         "500mg",    "oral",       "6/6h SN",       5, "concluida","Dr. Fábio Menezes"),
            (5, "Metronidazol 500mg",     "500mg",    "ev",         "8/8h",          5, "concluida","Dr. Fábio Menezes"),
            (6, "Alteplase",              "0,9mg/kg", "ev",         "dose única",    1, "concluida","Dr. Eduardo Pinto"),
            (6, "AAS 100mg",              "100mg",    "oral",       "1x ao dia",    90, "ativa", "Dr. Eduardo Pinto"),
            (6, "Atorvastatina 80mg",     "80mg",     "oral",       "1x ao dia",    90, "ativa", "Dr. Eduardo Pinto"),
        ]
        if PrescricaoMedica:
            for intern_idx, med_nome, dose, via, freq, dur, st_p, med_resp in prescricoes_data:
                inn = intern_objs[intern_idx] if intern_idx < len(intern_objs) else None
                if not inn:
                    continue
                try:
                    PrescricaoMedica.objects.create(
                        internacao=inn, medicamento=med_nome, dose=dose,
                        via=via, frequencia=freq,
                        duracao_dias=dur if dur > 0 else None,
                        status=st_p, medico=med_resp,
                    )
                except Exception:
                    pass

        # Evoluções clínicas
        evolucoes_data = [
            (0, "Paciente estável pós-angioplastia. Dor torácica revertida. ECG sem supra. Monitorização contínua.", "Dr. Renato Souza"),
            (0, "Enzimas cardíacas em queda. Mantém anticoagulação. Aguarda ecocardiograma.", "Dr. Renato Souza"),
            (1, "Melhora de dispneia após diurético IV. Redução de edema. Pressão controlada.", "Dr. Renato Souza"),
            (2, "Febre cedeu. Saturação 97% RA. Iniciou antibioticoterapia oral.", "Dra. Cristina Alves"),
            (3, "PA 140/90 após ajuste de medicação. Sem cefaleia. Aguarda avaliação cardiológica.", "Dra. Cristina Alves"),
            (4, "Alta hospitalar em boas condições gerais. Retorno ambulatorial em 7 dias.", "Dr. Fábio Menezes"),
            (6, "Sem novas crises convulsivas. Fisioterapia motora iniciada. NIHSS 8.", "Dr. Eduardo Pinto"),
        ]
        if EvolucaoClinica:
            for intern_idx, desc, resp in evolucoes_data:
                inn = intern_objs[intern_idx] if intern_idx < len(intern_objs) else None
                if not inn:
                    continue
                try:
                    EvolucaoClinica.objects.create(
                        internacao=inn, descricao=desc, responsavel=resp,
                    )
                except Exception:
                    pass

        n_pac   = len([p for p in pac_objs if p])
        n_intern = len([i for i in intern_objs if i])
        self.out(
            f"     ✓ Hospital: 8 departs | ~50 leitos | {n_pac} pacientes | "
            f"{n_intern} internações | triagens | prescrições | evoluções",
            self.style.SUCCESS,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Governo
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_governo(self, empresa):
        from api.models import (
            IndicadorSaudeGov, ProgramaSaudeGov,
            UnidadeSaude, AlertaGovernamental, RegistroSintoma,
        )
        try:
            from api.models import OrcamentoSaudeGov, PlanoAcaoGov, AtoNormativoGov
        except ImportError:
            OrcamentoSaudeGov = PlanoAcaoGov = AtoNormativoGov = None
        try:
            from api.models import SerieEpidemiologica
        except ImportError:
            SerieEpidemiologica = None

        import uuid as _uuid

        # ── 1. Programas de saúde (8) ────────────────────────────────────────
        programas_cfg = [
            # (nome, descricao, status, pop_alvo, orc_prev, orc_exec, responsavel, inicio, fim)
            ("Dengue Zero 2026",
             "Combate ao Aedes aegypti — mutirões de vistoria, eliminação de criadouros e vacinação.",
             "ativo", "Toda a população municipal", 2_800_000, 1_950_000,
             "Coord. Vigilância Epidemiológica",
             datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)),
            ("Saúde da Família — Expansão 2026",
             "Implantação de 12 novas equipes eSF em regiões de alta vulnerabilidade social.",
             "ativo", "Populações sem cobertura eSF", 4_500_000, 2_100_000,
             "Dep. Atenção Básica",
             datetime.date(2026, 3, 1), datetime.date(2027, 2, 28)),
            ("Vacinação em Dia",
             "Campanha de atualização do calendário vacinal adulto e infantil — todas as UBSs.",
             "ativo", "Crianças 0–5 anos e adultos 60+", 1_200_000, 980_000,
             "Coord. Imunizações",
             datetime.date(2026, 2, 1), datetime.date(2026, 11, 30)),
            ("Saúde Mental na APS",
             "Implantação do matriciamento CAPS–eSF em todos os municípios. Redução de internações psiquiátricas.",
             "ativo", "Adultos com transtornos mentais comuns", 3_100_000, 890_000,
             "Dep. Saúde Mental",
             datetime.date(2026, 1, 15), datetime.date(2026, 12, 31)),
            ("Controle da Hipertensão Arterial",
             "Rastreamento e tratamento de HAS — aferição gratuita nas UBSs e farmácias populares.",
             "ativo", "Adultos acima de 18 anos", 1_800_000, 1_200_000,
             "Coord. DCNT",
             datetime.date(2025, 7, 1), datetime.date(2026, 6, 30)),
            ("Redução da Mortalidade Infantil",
             "Fortalecimento da atenção pré-natal e puericultura nos primeiros 1000 dias.",
             "planejamento", "Gestantes e crianças < 1 ano", 900_000, 0,
             "Dep. Saúde da Mulher e Criança",
             datetime.date(2026, 7, 1), datetime.date(2028, 6, 30)),
            ("Programa Oncologia Rede",
             "Rastreamento de câncer de mama e colo do útero — mamografias e preventivos.",
             "ativo", "Mulheres 25–64 anos", 2_200_000, 1_100_000,
             "Coord. Oncologia",
             datetime.date(2025, 9, 1), datetime.date(2026, 8, 31)),
            ("Saúde do Trabalhador — CEREST",
             "Vigilância em saúde do trabalhador — fiscalização, PCMSO, CIPA e notificações SINAN.",
             "concluido", "Trabalhadores formais e informais", 600_000, 580_000,
             "CEREST Regional",
             datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)),
        ]
        prog_objs = []
        for nome_pg, desc_pg, st_pg, pop_pg, orc_prev, orc_exec, resp_pg, dt_ini, dt_fim in programas_cfg:
            try:
                pg = ProgramaSaudeGov.objects.create(
                    empresa=empresa, nome=nome_pg, descricao=desc_pg,
                    status=st_pg, populacao_alvo=pop_pg,
                    orcamento_previsto=orc_prev, orcamento_executado=orc_exec,
                    responsavel=resp_pg, data_inicio=dt_ini, data_fim_prevista=dt_fim,
                )
                prog_objs.append(pg)
            except Exception:
                prog_objs.append(None)

        # ── 2. Indicadores (12) ──────────────────────────────────────────────
        # tipo: quantitativo | percentual | indice
        indicadores_cfg = [
            # (nome, tipo_ind, meta, valor_atual, unidade, periodo, prog_idx)
            ("Cobertura Vacinal Poliomielite",        "percentual", 95.0,  87.3,  "%",         "2026",   2),
            ("Cobertura Vacinal COVID-19 (dose 3)",   "percentual", 90.0,  73.8,  "%",         "2026",   2),
            ("Taxa de Incidência de Dengue",          "quantitativo",2.0,   5.4,  "/100k hab", "2026",   0),
            ("Internações por Dengue",                "quantitativo",50.0, 189.0, "internações","2026",  0),
            ("Cobertura de eSF",                      "percentual", 80.0,  64.2,  "%",         "2026",   1),
            ("Consultas APS por Habitante/Ano",       "quantitativo",4.0,   3.1,  "cons/hab",  "2026",   1),
            ("Taxa de Mortalidade Infantil",          "quantitativo",8.0,  11.2,  "/1000 NV",  "2025",   5),
            ("Prevalência de HAS controlada",         "percentual", 60.0,  47.5,  "%",         "2026",   4),
            ("Rastreamento Ca Mama (mamografia)",     "percentual", 70.0,  52.4,  "%",         "2025",   6),
            ("Casos Notificados Saúde Mental (CAPS)", "quantitativo",1200.0,980.0,"casos/mês", "2026",   3),
            ("Acidente de Trabalho Grave Notificado", "quantitativo",50.0,  72.0, "casos",     "2025",   7),
            ("Índice de Satisfação UBS (pesquisa)",   "indice",     4.0,   3.6,  "0–5",       "2026",   1),
        ]
        for nome_i, tipo_i, meta_i, val_i, unid_i, period_i, prog_idx in indicadores_cfg:
            prog = prog_objs[prog_idx] if prog_idx < len(prog_objs) else None
            try:
                IndicadorSaudeGov.objects.create(
                    empresa=empresa, programa=prog,
                    nome=nome_i, tipo=tipo_i, meta=meta_i,
                    valor_atual=val_i, unidade=unid_i,
                    periodo_referencia=period_i,
                )
            except Exception:
                pass

        # ── 3. Unidades de saúde (12) ────────────────────────────────────────
        unidades_cfg = [
            # (cnes, nome, tipo, status, municipio, uf, bairro, tel, pop_ref, leitos_sus, leitos_uti, diretor)
            ("2079798", "UBS Jardim São Paulo",     "ubs",         "ativa", "São Paulo","SP","Jardim São Paulo","(11)3392-1100", 18000, 0, 0, "Dra. Fernanda Castro"),
            ("2079802", "UBS Vila Madalena",        "ubs",         "ativa", "São Paulo","SP","Vila Madalena",   "(11)3819-2200", 15000, 0, 0, "Dr. Paulo Mendes"),
            ("2079815", "UBS Capão Redondo",        "ubs",         "ativa", "São Paulo","SP","Capão Redondo",   "(11)5843-3300", 22000, 0, 0, "Dra. Renata Lima"),
            ("2079830", "UBS Ermelino Matarazzo",   "ubs",         "ativa", "São Paulo","SP","Ermelino Mat.",   "(11)2272-4400", 20000, 0, 0, "Dr. Cláudio Nunes"),
            ("2079844", "UPA 24h Lapa",             "upa",         "ativa", "São Paulo","SP","Lapa",            "(11)3675-5500", 60000, 0, 0, "Dr. André Cardoso"),
            ("2079858", "UPA 24h Santo André",      "upa",         "ativa", "Santo André","SP","Centro",        "(11)4433-6600", 80000, 0, 0, "Dra. Sônia Araújo"),
            ("2079871", "CAPS II Pinheiros",        "caps_ii",     "ativa", "São Paulo","SP","Pinheiros",       "(11)3814-7700", 12000, 0, 0, "Psic. Vera Melo"),
            ("2079885", "CAPS AD Zona Sul",         "caps_ad",     "ativa", "São Paulo","SP","Zona Sul",        "(11)5011-8800",  8000, 0, 0, "Dr. Ricardo Torres"),
            ("2079899", "Hospital Municipal Saúde", "hospital",    "ativa", "São Paulo","SP","Santana",         "(11)2976-9900",120000,240,20, "Dr. Marcelo Bastos"),
            ("2079903", "Policlínica Centro",       "policlinica", "ativa", "São Paulo","SP","Centro",          "(11)3151-0010", 45000, 0, 0, "Dra. Elisa Freitas"),
            ("2079917", "CEREST Regional SP",       "cerest",      "ativa", "São Paulo","SP","Bela Vista",      "(11)3241-1111",200000, 0, 0, "Enf. Marcos Souza"),
            ("2079931", "Lab Público Central",      "laboratorio", "ativa", "São Paulo","SP","Ipiranga",        "(11)6950-2222", 90000, 0, 0, "Farm. Ana Torres"),
        ]
        unidade_objs = []
        for cnes_u, nome_u, tipo_u, st_u, mun_u, uf_u, bairro_u, tel_u, pop_u, lei_sus, lei_uti, dir_u in unidades_cfg:
            try:
                import random as _rnd_gov
                lat_base = {"São Paulo": -23.5505, "Santo André": -23.6639}
                lon_base = {"São Paulo": -46.6333, "Santo André": -46.5310}
                u = UnidadeSaude.objects.create(
                    empresa=empresa, cnes=cnes_u, nome=nome_u,
                    tipo=tipo_u, status=st_u, municipio=mun_u, uf=uf_u,
                    bairro=bairro_u, telefone=tel_u,
                    populacao_referenciada=pop_u,
                    leitos_sus=lei_sus, leitos_uti=lei_uti,
                    diretor=dir_u,
                    latitude=lat_base.get(mun_u, -23.55),
                    longitude=lon_base.get(mun_u, -46.63),
                )
                unidade_objs.append(u)
            except Exception:
                unidade_objs.append(None)

        # ── 4. Alertas epidemiológicos (5) ────────────────────────────────────
        alertas_cfg = [
            ("Surto de Dengue — Zona Norte SP",
             "Aumento de 65% nos casos confirmados de dengue na Zona Norte na última quinzena. Casos de dengue hemorrágica notificados. Intensificar eliminação de criadouros.",
             "alto", "SP", "São Paulo", "Zona Norte"),
            ("Surto de Influenza A (H3N2) — Grande SP",
             "Laboratório Central confirma circulação de H3N2. Vacinação anti-influenza disponível nas UBSs. Grupos de risco devem se vacinar.",
             "moderado", "SP", "São Paulo", "Zona Leste"),
            ("Alerta Calor Extremo — Risco de Desidratação",
             "Temperaturas acima de 38°C previstas para os próximos 7 dias. Idosos e crianças em risco. Hidratação frequente recomendada.",
             "moderado", "SP", "São Paulo", ""),
            ("Monkeypox — Caso Confirmado Zona Sul",
             "Confirmado caso de mpox na Zona Sul. Investigação epidemiológica em andamento. Comunicantes rastreados. Sem risco de surto no momento.",
             "baixo", "SP", "São Paulo", "Zona Sul"),
            ("Coqueluche — Surto em Creche Municipal",
             "Cluster de coqueluche confirmado em creche. 8 crianças menores de 1 ano afetadas. Bloqueio vacinal em andamento.",
             "alto", "SP", "São Paulo", "Pirituba"),
        ]
        for titulo_a, msg_a, nivel_a, estado_a, cidade_a, bairro_a in alertas_cfg:
            try:
                AlertaGovernamental.objects.create(
                    empresa=empresa, titulo=titulo_a, mensagem=msg_a,
                    nivel=nivel_a, estado=estado_a, cidade=cidade_a,
                    bairro=bairro_a, ativo=True, status="publicado",
                )
            except Exception:
                pass

        # ── 5. Orçamento (2 anos) ─────────────────────────────────────────────
        if OrcamentoSaudeGov:
            for ano_o, prev_o, exec_o, fonte_o in [
                (2025, 185_000_000, 181_200_000, "Fundo Municipal de Saúde — SUS + Tesouro Municipal"),
                (2026, 198_000_000,  95_400_000, "Fundo Municipal de Saúde — SUS + Tesouro Municipal"),
            ]:
                try:
                    OrcamentoSaudeGov.objects.get_or_create(
                        empresa=empresa, ano=ano_o,
                        defaults=dict(
                            total_previsto=prev_o, total_executado=exec_o,
                            fonte_recurso=fonte_o,
                        )
                    )
                except Exception:
                    pass

        # ── 6. Planos de ação (6) ─────────────────────────────────────────────
        if PlanoAcaoGov:
            planos_acao_cfg = [
                # (titulo, desc, responsavel, prioridade, status, prog_idx, progresso, prazo)
                ("Mutirão de vistoria contra dengue — 3000 imóveis",
                 "Agentes de endemias percorrerão 3000 imóveis por semana nas zonas vermelhas.",
                 "Coord. Vigilância Epidemiológica", "alta", "em_andamento", 0, 65,
                 datetime.date(2026, 7, 31)),
                ("Implantação 6 novas equipes eSF — Capão Redondo",
                 "Contratação e implantação de 6 equipes completas com médico, enfermeiro e ACS.",
                 "Dep. Atenção Básica", "alta", "em_andamento", 1, 40,
                 datetime.date(2026, 9, 30)),
                ("Campanha vacinação polio — meta 95%",
                 "Intensificação da vacinação nas UBSs e pontos de vacinação volante.",
                 "Coord. Imunizações", "alta", "em_andamento", 2, 72,
                 datetime.date(2026, 6, 30)),
                ("Capacitar 80 profissionais APS em saúde mental",
                 "Matriciamento CAPS–eSF: 80 profissionais capacitados para manejo de TMC.",
                 "Dep. Saúde Mental", "media", "em_andamento", 3, 55,
                 datetime.date(2026, 8, 31)),
                ("Implantar 500 pontos de aferição de PA gratuita",
                 "Parcerias com farmácias e supermercados para aferição gratuita de pressão arterial.",
                 "Coord. DCNT", "media", "pendente", 4, 10,
                 datetime.date(2026, 10, 31)),
                ("Relatório final CEREST 2025 — publicação",
                 "Elaboração e publicação do relatório anual de saúde do trabalhador.",
                 "CEREST Regional", "baixa", "concluido", 7, 100,
                 datetime.date(2026, 3, 31)),
            ]
            for titulo_pa, desc_pa, resp_pa, prio_pa, st_pa, prog_idx_pa, prog_pct, prazo_pa in planos_acao_cfg:
                prog_pa = prog_objs[prog_idx_pa] if prog_idx_pa < len(prog_objs) else None
                try:
                    PlanoAcaoGov.objects.create(
                        empresa=empresa, programa=prog_pa,
                        titulo=titulo_pa, descricao=desc_pa,
                        responsavel=resp_pa, prioridade=prio_pa,
                        status=st_pa, progresso=prog_pct, prazo=prazo_pa,
                    )
                except Exception:
                    pass

        # ── 7. Atos normativos (3) ────────────────────────────────────────────
        if AtoNormativoGov:
            atos_cfg = [
                ("portaria", "001/2026", "Portaria que define critérios de rastreamento da Dengue no Município",
                 "Estabelece fluxos de vigilância epidemiológica e notificação de dengue.",
                 datetime.date(2026, 1, 10), "vigente", "Secretaria Municipal de Saúde", prog_objs[0] if prog_objs else None),
                ("resolucao", "012/2025", "Resolução que regulamenta o matriciamento CAPS–eSF",
                 "Define protocolos de apoio matricial em saúde mental na Atenção Básica.",
                 datetime.date(2025, 6, 15), "vigente", "Conselho Municipal de Saúde", prog_objs[3] if len(prog_objs) > 3 else None),
                ("nota_tecnica", "007/2026", "Nota Técnica sobre manejo clínico da dengue grave",
                 "Orientações técnicas para unidades hospitalares no manejo de dengue com sinais de alarme.",
                 datetime.date(2026, 3, 1), "vigente", "Dep. Vigilância em Saúde", prog_objs[0] if prog_objs else None),
            ]
            for tipo_at, num_at, tit_at, em_at, dt_pub, st_at, org_at, prog_at in atos_cfg:
                try:
                    AtoNormativoGov.objects.create(
                        empresa=empresa, tipo=tipo_at, numero=num_at,
                        titulo=tit_at, ementa=em_at, data_publicacao=dt_pub,
                        data_vigencia=dt_pub, status=st_at,
                        orgao_emissor=org_at, programa=prog_at,
                    )
                except Exception:
                    pass

        # ── 8. Registros de sintomas (60 pontos) ─────────────────────────────
        import random as _rnd_s
        _rnd_s.seed(42)
        clusters = [
            dict(doenca="dengue",   febre=True, dor_cabeca=True, dor_corpo=True,
                 cidade="São Paulo", estado="SP", bairro="Zona Norte",
                 lat=-23.51, lon=-46.64, origem="cidadao"),
            dict(doenca="influenza",febre=True, tosse=True, falta_ar=False,
                 cidade="São Paulo", estado="SP", bairro="Zona Leste",
                 lat=-23.57, lon=-46.52, origem="cidadao"),
            dict(doenca="dengue",   febre=True, dor_cabeca=True, dor_corpo=True,
                 cidade="São Paulo", estado="SP", bairro="Pirituba",
                 lat=-23.50, lon=-46.73, origem="unidade_saude"),
            dict(doenca="influenza",febre=True, tosse=True, falta_ar=True,
                 cidade="Santo André", estado="SP", bairro="Centro",
                 lat=-23.66, lon=-46.53, origem="cidadao"),
        ]
        for i in range(60):
            cl = clusters[i % len(clusters)].copy()
            try:
                RegistroSintoma.objects.create(
                    empresa=empresa,
                    id_anonimo=_uuid.uuid4(),
                    doenca=cl["doenca"],
                    febre=cl.get("febre", False),
                    tosse=cl.get("tosse", False),
                    falta_ar=cl.get("falta_ar", False),
                    dor_cabeca=cl.get("dor_cabeca", False),
                    dor_corpo=cl.get("dor_corpo", False),
                    cidade=cl["cidade"],
                    estado=cl["estado"],
                    bairro=cl["bairro"],
                    latitude=cl["lat"] + _rnd_s.uniform(-0.04, 0.04),
                    longitude=cl["lon"] + _rnd_s.uniform(-0.04, 0.04),
                    origem_dado=cl["origem"],
                )
            except Exception:
                pass

        n_prog  = len([p for p in prog_objs if p])
        n_unid  = len([u for u in unidade_objs if u])
        self.out(
            f"     ✓ Governo: {n_prog} programas | 12 indicadores | {n_unid} unidades | "
            f"5 alertas | planos de ação | orçamento | atos normativos | 60 registros sintomas",
            self.style.SUCCESS,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DADOS DEMO — Plano de Saúde
    # ─────────────────────────────────────────────────────────────────────────
    def _criar_dados_plano(self, empresa):
        from api.models import (
            PlanoSaude, BeneficiarioPlano, PrestadorPlanoSaude,
            GuiaAutorizacao, Sinistro, Reembolso,
        )
        try:
            from api.models import CarenciaBeneficiario, CoparticipacaoRegra, FaturamentoBeneficiario, RedeCredenciadaPlano
        except ImportError:
            CarenciaBeneficiario = CoparticipacaoRegra = FaturamentoBeneficiario = RedeCredenciadaPlano = None

        from django.utils import timezone as _tz_plano

        # ── 1. Planos (6) ─────────────────────────────────────────────────────
        planos_cfg = [
            # (nome, registro_ans, cnpj, modalidade, abrangencia, status)
            ("Básico Ambulatorial",          "434561", "12.345.678/0001-01", "cooperativa",  "municipal", "ativo"),
            ("Essencial Ambulatorial+Exames","434562", "12.345.678/0001-01", "cooperativa",  "estadual",  "ativo"),
            ("Clínico Hospitalar Enfermaria","434563", "12.345.678/0001-01", "cooperativa",  "estadual",  "ativo"),
            ("Premium Hospitalar Apartamento","434564","12.345.678/0001-01", "cooperativa",  "nacional",  "ativo"),
            ("Master Odonto + Hospital",     "434565", "12.345.678/0001-01", "cooperativa",  "nacional",  "ativo"),
            ("Empresarial Coletivo",         "434566", "12.345.678/0001-01", "autogestao",   "nacional",  "ativo"),
        ]
        plano_objs = []
        for nome_pl, ans_pl, cnpj_pl, mod_pl, abr_pl, st_pl in planos_cfg:
            try:
                pl = PlanoSaude.objects.create(
                    empresa=empresa, nome=nome_pl, registro_ans=ans_pl,
                    cnpj=cnpj_pl, modalidade=mod_pl, abrangencia=abr_pl,
                    status=st_pl,
                    telefone="(11)4000-1234",
                    email="operadora@demo.com.br",
                )
                plano_objs.append(pl)
            except Exception:
                plano_objs.append(None)

        if not any(plano_objs):
            self.out(f"     ⚠ Plano: nenhum plano criado", self.style.WARNING)
            return

        # ── 2. Regras de Coparticipação ───────────────────────────────────────
        if CoparticipacaoRegra:
            copars = [
                ("consulta",   20.0,   0,    None),
                ("exame",      15.0,   0,    200),
                ("internacao",  0.0,   0,    None),
                ("cirurgia",    0.0,   0,    None),
                ("terapia",    30.0,   0,    300),
                ("urgencia",    0.0,   0,    None),
            ]
            for pl in plano_objs:
                if not pl:
                    continue
                for tipo_c, pct_c, fixo_c, teto_c in copars:
                    try:
                        CoparticipacaoRegra.objects.get_or_create(
                            plano=pl, tipo_atendimento=tipo_c,
                            defaults=dict(percentual=pct_c, valor_fixo=fixo_c, teto_mensal=teto_c, ativo=True),
                        )
                    except Exception:
                        pass

        # ── 3. Prestadores (15) ───────────────────────────────────────────────
        prestadores_cfg = [
            # (cod_rede, nome_fantasia, razao_social, cnpj, tipo, cnes, especialidades, cidade, estado, tel, sla, score)
            ("PREST001","Hospital São Camilo",           "Hosp. São Camilo S/A",      "01.111.222/0001-01","hospital",          "2079000","Clínica Geral; Cirurgia; UTI; Cardiologia","São Paulo","SP","(11)3888-1111",48,92),
            ("PREST002","Hospital e Maternidade Santa Cruz","Santa Cruz S/A",         "02.222.333/0001-02","hospital",          "2079100","Obstetrícia; Neonatologia; Cirurgia",       "São Paulo","SP","(11)3889-2222",48,90),
            ("PREST003","Hospital Albert Einstein",      "Hosp. Israelita A.E. S/A",  "03.333.444/0001-03","hospital",          "2079200","Alta Complexidade; Oncologia; Transplante",  "São Paulo","SP","(11)2151-3333",24,98),
            ("PREST004","Clínica São Lucas",             "Clínica São Lucas Ltda",    "04.444.555/0001-04","clinica",           "2079300","Cardiologia; Ortopedia; Dermatologia",       "São Paulo","SP","(11)3033-4444",72,88),
            ("PREST005","Clínica Médica Saúde Total",    "Saúde Total Ltda",          "05.555.666/0001-05","clinica",           "2079400","Clínica Geral; Ginecologia; Pediatria",      "São Paulo","SP","(11)4033-5555",72,85),
            ("PREST006","Clínica Odonto Premium",        "Odonto Premium Ltda",       "06.666.777/0001-06","clinica",           "2079500","Odontologia Geral; Ortodontia; Implantes",   "São Paulo","SP","(11)3120-6666",72,87),
            ("PREST007","Laboratório Central de Análises","Lab Central S/A",          "07.777.888/0001-07","laboratorio",       "2079600","Hematologia; Bioquímica; Imunologia; PCR",   "São Paulo","SP","(11)3254-7777",24,95),
            ("PREST008","Labo Diagnose",                 "Labo Diagnose Ltda",        "08.888.999/0001-08","laboratorio",       "2079700","Análises Clínicas; Microbiologia; Citologia","São Paulo","SP","(11)3222-8888",24,91),
            ("PREST009","Clínica de Imagem Avançada",    "Imagem Avançada S/A",       "09.999.000/0001-09","imagem",            "2079800","Tomografia; Ressonância; Mamografia; ECO",   "São Paulo","SP","(11)3100-9999",48,93),
            ("PREST010","Eco-Cardio Centro",             "Ecocardiologia Centro Ltda","10.000.111/0001-10","imagem",            "2079810","Ecocardiograma; Holter; MAPA; Ergometria",   "São Paulo","SP","(11)3010-0010",48,90),
            ("PREST011","UPA Lapa Credenciada",          "UPA Lapa S/A",              "11.111.222/0001-11","pronto_atendimento","2079820","Urgência e Emergência 24h",                   "São Paulo","SP","(11)3675-0011",  4,82),
            ("PREST012","PA Guarulhos 24h",              "PA Guarulhos S/A",          "12.222.333/0001-12","pronto_atendimento","2079830","Pronto Atendimento 24h",                     "Guarulhos","SP","(11)2443-0012",  4,80),
            ("PREST013","Home Care BemViver",            "BemViver Saúde Ltda",       "13.333.444/0001-13","homecare",          "2079840","Home Care; Enfermagem; Fisioterapia Domiciliar","São Paulo","SP","(11)4100-0013",72,89),
            ("PREST014","Clínica Fisio & Reab",          "Fisio Reab Ltda",           "14.444.555/0001-14","clinica",           "2079850","Fisioterapia; Fonoaudiologia; Psicologia",   "São Paulo","SP","(11)3922-0014",72,86),
            ("PREST015","Oncovida Clínica Oncológica",   "Oncovida Ltda",             "15.555.666/0001-15","clinica",           "2079860","Oncologia; Hematologia; Quimioterapia",      "São Paulo","SP","(11)3044-0015",24,94),
        ]
        prest_objs = []
        for cod_r, nom_f, raz_s, cnpj_pr, tipo_pr, cnes_pr, espec_pr, cid_pr, est_pr, tel_pr, sla_pr, score_pr in prestadores_cfg:
            try:
                pr = PrestadorPlanoSaude.objects.create(
                    empresa=empresa, codigo_rede=cod_r,
                    nome_fantasia=nom_f, razao_social=raz_s, cnpj=cnpj_pr,
                    tipo=tipo_pr, registro_cnes=cnes_pr, especialidades=espec_pr,
                    cidade=cid_pr, estado=est_pr, telefone=tel_pr,
                    sla_autorizacao_horas=sla_pr, score_qualidade=score_pr,
                    portal_ativo=True, status="credenciado",
                )
                prest_objs.append(pr)
            except Exception:
                prest_objs.append(None)

        # ── 4. Beneficiários (25) ─────────────────────────────────────────────
        benef_cfg = [
            # (nome, cpf, nasc, sexo, tel, carteirinha, dt_inicio, plano_idx, tipo_pl, acomod, situacao)
            ("Carlos Eduardo Mendes",   "100.200.300-01", datetime.date(1975,  5, 12), "M","(11)9100-0001","0001-00001-0",datetime.date(2020, 1,1),3,"Premium","apartamento","ativo"),
            ("Patrícia Souza Lima",     "200.300.400-02", datetime.date(1983,  9, 28), "F","(11)9200-0002","0001-00002-0",datetime.date(2021, 3,1),2,"Clínico Hosp.","enfermaria","ativo"),
            ("Roberto Alves Teixeira",  "300.400.500-03", datetime.date(1990,  2, 14), "M","(11)9300-0003","0001-00003-0",datetime.date(2022, 6,1),1,"Essencial","enfermaria","ativo"),
            ("Juliana Moreira Costa",   "400.500.600-04", datetime.date(1995, 12,  3), "F","(11)9400-0004","0001-00004-0",datetime.date(2023, 1,1),0,"Básico","enfermaria","ativo"),
            ("Marcos Vinícius Pinto",   "500.600.700-05", datetime.date(1969,  7, 19), "M","(11)9500-0005","0001-00005-0",datetime.date(2019, 7,1),4,"Master","apartamento","ativo"),
            ("Ana Beatriz Rodrigues",   "600.700.800-06", datetime.date(1988, 11, 11), "F","(11)9600-0006","0001-00006-0",datetime.date(2021, 4,1),2,"Clínico Hosp.","enfermaria","ativo"),
            ("Fernando Lima Torres",    "700.800.900-07", datetime.date(1972,  8, 25), "M","(11)9700-0007","0001-00007-0",datetime.date(2020, 8,1),3,"Premium","apartamento","ativo"),
            ("Cristiane Melo Santos",   "800.900.010-08", datetime.date(1965,  3, 30), "F","(11)9800-0008","0001-00008-0",datetime.date(2018,12,1),4,"Master","apartamento","ativo"),
            ("Diego Rocha Ferreira",    "900.010.120-09", datetime.date(1980,  6,  5), "M","(11)9900-0009","0001-00009-0",datetime.date(2022, 2,1),5,"Empresarial","apartamento","ativo"),
            ("Beatriz Nunes Torres",    "010.120.230-10", datetime.date(1970,  1, 20), "F","(11)9010-0010","0001-00010-0",datetime.date(2020,10,1),2,"Clínico Hosp.","enfermaria","ativo"),
            ("Alexandre Oliveira Neto", "120.230.340-11", datetime.date(1992,  4, 17), "M","(11)9120-0011","0001-00011-0",datetime.date(2023, 5,1),0,"Básico","enfermaria","ativo"),
            ("Patrícia Costa Souza",    "230.340.450-12", datetime.date(1978, 10,  8), "F","(11)9230-0012","0001-00012-0",datetime.date(2021, 9,1),1,"Essencial","enfermaria","ativo"),
            ("Antônio José Ribeiro",    "340.450.560-13", datetime.date(1960,  5, 22), "M","(11)9340-0013","0001-00013-0",datetime.date(2017, 1,1),4,"Master","apartamento","ativo"),
            ("Mariana Lima Barros",     "450.560.670-14", datetime.date(1997,  7, 14), "F","(11)9450-0014","0001-00014-0",datetime.date(2024, 1,1),0,"Básico","enfermaria","ativo"),
            ("José Antônio da Silva",   "560.670.780-15", datetime.date(1955,  3, 10), "M","(11)9560-0015","0001-00015-0",datetime.date(2016, 6,1),3,"Premium","apartamento","ativo"),
            ("Maria Aparecida Santos",  "670.780.890-16", datetime.date(1945,  7, 22), "F","(11)9670-0016","0001-00016-0",datetime.date(2015, 1,1),4,"Master","apartamento","ativo"),
            ("Pedro Henrique Costa",    "780.890.900-17", datetime.date(1982, 11,  5), "M","(11)9780-0017","0001-00017-0",datetime.date(2022, 7,1),2,"Clínico Hosp.","enfermaria","ativo"),
            ("Fernanda Lima Souza",     "890.900.010-18", datetime.date(2000,  2, 28), "F","(11)9890-0018","0001-00018-0",datetime.date(2023, 3,1),1,"Essencial","enfermaria","ativo"),
            ("Luiz Carlos Pereira",     "901.010.120-19", datetime.date(1986,  9,  3), "M","(11)9901-0019","0001-00019-0",datetime.date(2021,11,1),5,"Empresarial","apartamento","ativo"),
            ("Sandra Regina Alves",     "012.120.230-20", datetime.date(1974,  4, 16), "F","(11)9012-0020","0001-00020-0",datetime.date(2020, 5,1),2,"Clínico Hosp.","enfermaria","ativo"),
            ("Bruno Henrique Moura",    "123.230.340-21", datetime.date(1993,  8, 21), "M","(11)9123-0021","0001-00021-0",datetime.date(2023, 8,1),0,"Básico","enfermaria","ativo"),
            ("Vanessa Aparecida Rocha", "234.340.450-22", datetime.date(1987, 12, 12), "F","(11)9234-0022","0001-00022-0",datetime.date(2022, 4,1),1,"Essencial","enfermaria","suspenso"),
            ("Rafael Souza Barbosa",    "345.450.560-23", datetime.date(1975,  6,  7), "M","(11)9345-0023","0001-00023-0",datetime.date(2019, 2,1),3,"Premium","apartamento","ativo"),
            ("Camila Torres Mendes",    "456.560.670-24", datetime.date(1998,  1, 25), "F","(11)9456-0024","0001-00024-0",datetime.date(2024, 6,1),5,"Empresarial","apartamento","ativo"),
            ("Eduardo Lima Pinto",      "567.670.780-25", datetime.date(1968, 10, 30), "M","(11)9567-0025","0001-00025-0",datetime.date(2018, 8,1),4,"Master","apartamento","cancelado"),
        ]
        benef_objs = []
        for (nome_b, cpf_b, nasc_b, sexo_b, tel_b, cart_b, dt_ini_b,
             pl_idx, tipo_pl_b, acom_b, sit_b) in benef_cfg:
            plano_b = plano_objs[pl_idx] if pl_idx < len(plano_objs) else None
            if not plano_b:
                benef_objs.append(None)
                continue
            try:
                b = BeneficiarioPlano.objects.create(
                    plano=plano_b, nome=nome_b, cpf=cpf_b,
                    data_nascimento=nasc_b, sexo=sexo_b, telefone=tel_b,
                    numero_carteirinha=cart_b, data_inicio_vigencia=dt_ini_b,
                    plano_tipo=tipo_pl_b, acomodacao=acom_b, situacao=sit_b,
                )
                benef_objs.append(b)
            except Exception:
                benef_objs.append(None)

        # ── 5. Carências ──────────────────────────────────────────────────────
        if CarenciaBeneficiario:
            novatos = [b for b in benef_objs if b and b.data_inicio_vigencia and b.data_inicio_vigencia.year >= 2023]
            for b in novatos[:6]:
                for tipo_car, dias_car in [("consulta",30),("exame",60),("internacao",180),("parto",300)]:
                    try:
                        CarenciaBeneficiario.objects.get_or_create(
                            beneficiario=b, tipo_procedimento=tipo_car,
                            defaults=dict(empresa=empresa, data_inicio=b.data_inicio_vigencia, dias_carencia=dias_car),
                        )
                    except Exception:
                        pass

        # ── 6. Guias de autorização (12) ──────────────────────────────────────
        guias_cfg = [
            # (benef_idx, prest_idx, tipo, num, cod_proc, desc, cid, medico, crm, qtd, valor_est, status, prioridade, fila)
            (0,  0,"internacao","G2026-001","03.01.01.017","Angioplastia Transluminal Coronariana","I21.0","Dr. Roberto Cardoso","CRM/SP 20001",1, 18000,"autorizada","eletiva","autorizada"),
            (1,  0,"internacao","G2026-002","03.01.01.018","Internação Clínica — ICC Descompensada","I50.0","Dra. Ana Paula Melo","CRM/SP 20002",5,  4500,"autorizada","eletiva","autorizada"),
            (2,  3,"exame",    "G2026-003","02.04.03.188","Tomografia Computadorizada de Tórax",   "J18.1","Dr. Paulo Ferreira","CRM/SP 20003",1,  1200,"autorizada","eletiva","autorizada"),
            (4,  6,"exame",    "G2026-004","02.02.03.099","Ressonância Magnética de Coluna Lombar","M54.5","Dra. Carla Lima",   "CRM/SP 20004",1,  2800,"em_analise","eletiva","auditoria_clinica"),
            (5,  2,"internacao","G2026-005","03.02.02.022","Histerectomia por Via Laparoscópica",   "N80.0","Dr. Marco Oliveira","CRM/SP 20005",1,  9500,"autorizada","eletiva","autorizada"),
            (6,  3,"consulta", "G2026-006","01.01.01.006","Consulta Cardiologista — pós-IAM",      "I21.9","Dr. Roberto Cardoso","CRM/SP 20001",3,   450,"autorizada","eletiva","autorizada"),
            (7,  8,"exame",    "G2026-007","02.11.07.014","Densitometria Óssea",                   "M81.0","Dra. Beatriz Couto","CRM/SP 20006",1,   380,"solicitada","eletiva","triagem"),
            (9,  0,"procedimento","G2026-008","04.01.01.025","Colecistectomia Videolaparoscópica",  "K80.1","Dr. Fábio Menezes","CRM/SP 11003",1, 12000,"autorizada","urgente","autorizada"),
            (10, 3,"consulta", "G2026-009","01.01.01.007","Consulta Ortopedista — dor crônica",    "M17.1","Dr. Edu Santos",   "CRM/SP 20007",2,   300,"negada","eletiva","negada"),
            (12, 2,"medicamento","G2026-010","06.05.99.001","Trastuzumabe 440mg — Ca Mama HER2+",  "C50.9","Dra. Márcia Rocha","CRM/SP 11007",6, 28000,"em_analise","alta_complexidade","auditoria_medica"),
            (14, 0,"internacao","G2026-011","03.01.06.010","Reabilitação AVC — Unidade Internada",  "I63.3","Dr. Eduardo Pinto","CRM/SP 11008",14, 7000,"autorizada","urgente","autorizada"),
            (3,  6,"exame",    "G2026-012","02.02.01.014","Eletrocardiograma + Holter 24h",        "R00.0","Dra. Ana Cardio",  "CRM/SP 20008",1,   220,"solicitada","eletiva","triagem"),
        ]
        guia_objs = []
        for (bi, pi, tipo_g, num_g, cod_g, desc_g, cid_g, med_g, crm_g,
             qtd_g, val_g, st_g, prior_g, fila_g) in guias_cfg:
            benef = benef_objs[bi] if bi < len(benef_objs) else None
            prest = prest_objs[pi] if pi < len(prest_objs) else None
            if not benef:
                guia_objs.append(None)
                continue
            plano_g = benef.plano
            num_aut  = f"AUT{num_g[2:]}" if st_g == "autorizada" else ""
            val_auth = datetime.date(2026, 12, 31) if st_g == "autorizada" else None
            try:
                g = GuiaAutorizacao.objects.create(
                    plano=plano_g, beneficiario=benef, prestador=prest, unidade=None,
                    tipo=tipo_g, numero_guia=num_g, codigo_procedimento=cod_g,
                    descricao_procedimento=desc_g, cid=cid_g,
                    medico_solicitante=med_g, crm_medico=crm_g,
                    quantidade=qtd_g, valor_estimado=val_g,
                    status=st_g, prioridade_clinica=prior_g, fila_status=fila_g,
                    numero_autorizacao=num_aut, validade_autorizacao=val_auth,
                    auditor_responsavel="Dr. Luís Auditor — CRM/SP 99001" if st_g in ("autorizada","negada") else "",
                )
                guia_objs.append(g)
            except Exception:
                guia_objs.append(None)

        # ── 7. Sinistros (10) ─────────────────────────────────────────────────
        sinistros_cfg = [
            # (benef_idx, guia_idx, tipo, num_sin, cid, desc, prestador_str, medico, dt_atend, val_tot, val_pago, status)
            (0, 0, "internacao","SIN-2026-001","I21.0","Angioplastia Coronariana — IAM com supra ST","Hospital São Camilo","Dr. Roberto Cardoso",datetime.date(2026,1,15), 18500, 18500,"pago"),
            (1, 1, "internacao","SIN-2026-002","I50.0","Internação ICC — 5 dias UTI cardiológica",   "Hospital São Camilo","Dra. Ana Paula Melo", datetime.date(2026,2,8),  5200,  5200,"pago"),
            (2, 2, "exame",    "SIN-2026-003","J18.1","Tomografia Computadorizada de Tórax",         "Clínica Imagem Av.","Dr. Paulo Ferreira",  datetime.date(2026,3,2),  1300,  1300,"pago"),
            (5, 4, "procedimento","SIN-2026-004","N80.0","Histerectomia Laparoscópica + 2d internação","Hospital São Camilo","Dr. Marco Oliveira",datetime.date(2026,2,20),10200, 10200,"pago"),
            (6, 5, "consulta", "SIN-2026-005","I21.9","Consulta cardiológica — 3 sessões",           "Clínica São Lucas","Dr. Roberto Cardoso",  datetime.date(2026,3,10),  450,   450,"pago"),
            (9, 7, "procedimento","SIN-2026-006","K80.1","Colecistectomia laparoscópica",             "Hospital São Camilo","Dr. Fábio Menezes",  datetime.date(2026,4,5), 12800, 12800,"pago"),
            (14,10,"internacao","SIN-2026-007","I63.3","Reabilitação AVC — 14 dias internado",       "Hospital São Camilo","Dr. Eduardo Pinto",  datetime.date(2026,4,20), 9800,  9800,"aprovado"),
            (4, None,"consulta","SIN-2026-008","K74.6","Consulta gastroenterologista — hepatite C",  "Clínica Médica S.T.","Dr. João Gastro",    datetime.date(2026,5,3),   280,     0,"em_analise"),
            (12,None,"medicamento","SIN-2026-009","C50.9","Quimioterapia — Trastuzumabe ciclo 1/6",  "Oncovida","Dra. Márcia Rocha",              datetime.date(2026,5,10),28000,     0,"em_analise"),
            (7, None,"urgencia","SIN-2026-010","J45.9","Atendimento de urgência — crise asmática",   "UPA Lapa","Dr. André Cardoso",              datetime.date(2026,5,15),  820,   820,"pago"),
        ]
        sinistro_objs = []
        for (bi, gi, tipo_s, num_s, cid_s, desc_s, prest_s, med_s, dt_s,
             val_tot_s, val_pag_s, st_s) in sinistros_cfg:
            benef = benef_objs[bi] if bi < len(benef_objs) else None
            guia  = guia_objs[gi] if gi is not None and gi < len(guia_objs) else None
            if not benef:
                sinistro_objs.append(None)
                continue
            try:
                s = Sinistro.objects.create(
                    empresa=empresa, plano=benef.plano, beneficiario=benef,
                    guia=guia, numero_sinistro=num_s, tipo=tipo_s, status=st_s,
                    cid=cid_s, descricao_procedimento=desc_s,
                    prestador=prest_s, medico=med_s, data_atendimento=dt_s,
                    valor_total=val_tot_s, valor_pago=val_pag_s,
                )
                sinistro_objs.append(s)
            except Exception:
                sinistro_objs.append(None)

        # ── 8. Reembolsos (5) ─────────────────────────────────────────────────
        reembolsos_cfg = [
            # (benef_idx, sin_idx, tipo_desp, num_reemb, val_sol, val_apr, val_pago, status, dt_pag, desc)
            (3, None,"consulta","REM-2026-001", 350, 280,  280,"pago",  datetime.date(2026,3,20),"Consulta oftalmologista — não credenciado"),
            (6, None,"exame",  "REM-2026-002", 420, 420,  420,"pago",  datetime.date(2026,4,10),"Audiometria — serviço não credenciado"),
            (11,None,"terapia","REM-2026-003", 800, 600,    0,"aprovado",None,                   "Psicoterapia — 8 sessões — profissional não credenciado"),
            (15,None,"consulta","REM-2026-004", 250,   0,   0,"negado", None,                    "Consulta em cirurgia plástica estética — não coberta"),
            (18,None,"exame",  "REM-2026-005",1800,1800, 1800,"pago",  datetime.date(2026,5,8),"Ressonância fora da rede em outro estado"),
        ]
        for (bi, si, tipo_d, num_r, val_sol, val_apr, val_pag, st_r, dt_pag, desc_r) in reembolsos_cfg:
            benef = benef_objs[bi] if bi < len(benef_objs) else None
            sin   = sinistro_objs[si] if si is not None and si < len(sinistro_objs) else None
            if not benef:
                continue
            try:
                Reembolso.objects.create(
                    empresa=empresa, plano=benef.plano, beneficiario=benef, sinistro=sin,
                    numero_reembolso=num_r, tipo_despesa=tipo_d, status=st_r,
                    valor_solicitado=val_sol, valor_aprovado=val_apr, valor_pago=val_pag,
                    data_pagamento=dt_pag, descricao=desc_r,
                    banco="Banco do Brasil", agencia="0001-9", conta="12345-6",
                )
            except Exception:
                pass

        # ── 9. Faturas de beneficiários (amostra — meses recentes) ────────────
        if FaturamentoBeneficiario:
            competencias_fat = ["2026-03","2026-04","2026-05"]
            mensalidades_map = {0:689.00, 1:489.00, 2:389.50, 3:189.90, 4:989.00, 5:550.00}
            for bi, benef in enumerate(benef_objs[:10]):
                if not benef or benef.situacao != "ativo":
                    continue
                mens = mensalidades_map.get(bi % 6, 389.00)
                for comp in competencias_fat:
                    ano_c, mes_c = int(comp[:4]), int(comp[5:])
                    vencto = datetime.date(ano_c, mes_c, 10)
                    st_fat = "pago" if comp < "2026-05" else "pendente"
                    try:
                        FaturamentoBeneficiario.objects.create(
                            empresa=empresa, beneficiario=benef, plano=benef.plano,
                            competencia=comp, valor_mensalidade=mens,
                            valor_coparticipacao=0, valor_total=mens,
                            status=st_fat, vencimento=vencto,
                            pago_em=vencto if st_fat == "pago" else None,
                        )
                    except Exception:
                        pass

        n_pl  = len([p for p in plano_objs if p])
        n_bn  = len([b for b in benef_objs if b])
        n_pr  = len([p for p in prest_objs if p])
        n_gu  = len([g for g in guia_objs if g])
        n_si  = len([s for s in sinistro_objs if s])
        self.out(
            f"     ✓ Plano: {n_pl} planos | {n_bn} beneficiários | {n_pr} prestadores | "
            f"{n_gu} guias | {n_si} sinistros | 5 reembolsos | faturas",
            self.style.SUCCESS,
        )

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
        self.out("┌──────────────────────────────────────────────────────────────┐")
        self.out("│  AMBIENTE           EMAIL                       SENHA        │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  SST (empresa)      demo.sst@soluscrt.com       Demo@SST2026 │")
        self.out("│  Farmácia           demo.farmacia@soluscrt.com  Demo@Farm2026│")
        self.out("│  Hospital           demo.hospital@soluscrt.com  Demo@Hosp2026│")
        self.out("│  Governo            demo.governo@soluscrt.com   Demo@Gov2026 │")
        self.out("│  Plano de Saúde     demo.plano@soluscrt.com     Demo@Plano26 │")
        self.out("│  DonoSaaS           owner@soluscrt.com          Owner@...    │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  APP TRABALHADOR (SST)                                       │")
        self.out("│  Luiz Oliveira      luiz@app.local              Luiz@2026    │")
        self.out("│  Carlos Lima        carlos@app.local            Carlos@2026  │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  DEMO SST                                                    │")
        self.out("│  12 funcionários   35 EPIs c/ CAs válidos                   │")
        self.out("│  7 riscos PGR      6 pedidos de exame   CIPA ativa          │")
        self.out("│  3 clínicas        Docs: PGR, PCMSO, LTCAT, PPP, Insalub.  │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  DEMO FARMÁCIA                                               │")
        self.out("│  40 itens/medicamentos   5 fornecedores   10 pacientes       │")
        self.out("│  11 receitas   3 pedidos de compra   inventário   descartes  │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  DEMO HOSPITAL                                               │")
        self.out("│  8 departamentos   ~50 leitos   15 pacientes                 │")
        self.out("│  8 triagens   7 internações   prescrições   evoluções        │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  DEMO GOVERNO                                                │")
        self.out("│  8 programas   12 indicadores   12 unidades de saúde        │")
        self.out("│  5 alertas   6 planos de ação   orçamento   60 sintomas     │")
        self.out("├──────────────────────────────────────────────────────────────┤")
        self.out("│  DEMO PLANO DE SAÚDE                                         │")
        self.out("│  6 planos   25 beneficiários   15 prestadores               │")
        self.out("│  12 guias   10 sinistros   5 reembolsos   faturas            │")
        self.out("└──────────────────────────────────────────────────────────────┘")
