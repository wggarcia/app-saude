"""seed_oncologia_demo — popula a oncologia do tenant de demonstração.

Em produção o módulo tem os 5 protocolos-semente e zero de todo o resto: abrir a
tela na frente da operadora mostra tabelas vazias. Este comando cria uma coorte
pequena e coerente que exercita a cadeia inteira do módulo:

  guia (uma vigente, uma em análise dentro do prazo, uma negada fora do prazo)
    → ciclo dosado (um apto, um inapto por neutropenia, um com carboplatina/AUC)
      → reserva de cadeira na central de infusão
        → preparo na farmácia com dupla checagem e lote
          → administração à beira do leito (uma com extravasamento e conduta)
            → avaliação de resposta RECIST (basal → parcial → progressão)

É idempotente e reversível: todos os pacientes levam o prefixo [DEMO-ONCO];
rodar de novo (ou com --clear) apaga o lote anterior antes de recriar. Exige
--apply para escrever e um alvo explícito de conta de demonstração.

Uso:
  python manage.py seed_oncologia_demo                     # preview
  python manage.py seed_oncologia_demo --apply             # aplica
  python manage.py seed_oncologia_demo --apply --clear     # só limpa
"""
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

TAG = "[DEMO-ONCO]"
EMAIL_PADRAO = "demo.hospital@soluscrt.com"


def _dias(n):
    return date.today() - timedelta(days=n)


def _aware(d, hora):
    return timezone.make_aware(
        datetime.combine(d, hora), timezone.get_current_timezone())


class Command(BaseCommand):
    help = "Popula a oncologia (guias, ciclos, infusão, farmácia, RECIST) no tenant demo."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Escreve de verdade (sem isto, só mostra o preview).")
        parser.add_argument("--clear", action="store_true",
                            help="Apenas remove o lote [DEMO-ONCO] e sai.")
        parser.add_argument("--email", default=EMAIL_PADRAO,
                            help=f"E-mail do tenant demo (padrão: {EMAIL_PADRAO}).")
        parser.add_argument("--empresa-id", type=int, default=None,
                            help="Alvo por id (tem prioridade sobre --email).")

    def handle(self, *args, **opts):
        from django.db import connections
        from api.models import (Empresa, ProtocoloOncologico, CicloQuimioterapia,
                                GuiaOncologica, AgendamentoInfusao,
                                PreparoQuimioterapia, AdministracaoQuimioterapia,
                                AvaliacaoRespostaOncologica,
                                PrescricaoQuimioOral, DispensacaoQuimioOral)

        # Mesma lógica de conexão do seed de OPME: owner só quando é papel
        # realmente distinto (produção com RLS); em SQLite usar 2ª conexão trava.
        _d = connections["default"].settings_dict
        if "sqlite" in _d.get("ENGINE", ""):
            DB = "default"
        else:
            _o = connections["owner"].settings_dict if "owner" in connections else _d
            DB = "owner" if _d.get("USER") != _o.get("USER") else "default"

        if opts["empresa_id"]:
            empresa = Empresa.objects.using(DB).filter(id=opts["empresa_id"]).first()
        else:
            empresa = Empresa.objects.using(DB).filter(email=opts["email"]).first()
        if not empresa:
            raise CommandError(
                "Tenant de demonstração não encontrado — verifique --email/--empresa-id.")
        if "demo" not in (empresa.email or "").lower():
            raise CommandError(
                f"'{empresa.email}' não parece uma conta de demonstração. Abortando "
                "para não escrever dados fabricados num tenant real.")

        self.stdout.write(f"Tenant alvo: #{empresa.id} {empresa.email} ({empresa.nome})")

        ciclos_antigos = CicloQuimioterapia.objects.using(DB).filter(
            empresa=empresa, paciente_nome__startswith=TAG)
        guias_antigas = GuiaOncologica.objects.using(DB).filter(
            empresa=empresa, paciente_nome__startswith=TAG)
        respostas_antigas = AvaliacaoRespostaOncologica.objects.using(DB).filter(
            empresa=empresa, paciente_nome__startswith=TAG)
        orais_antigas = PrescricaoQuimioOral.objects.using(DB).filter(
            empresa=empresa, paciente_nome__startswith=TAG)
        n_antigos = ciclos_antigos.count()
        self.stdout.write(
            f"Lote {TAG} existente: {n_antigos} ciclo(s), {guias_antigas.count()} guia(s), "
            f"{respostas_antigas.count()} avaliação(ões).")

        def _limpar():
            # Agendamento/preparo/administração caem em cascata pelo ciclo.
            respostas_antigas.delete()
            orais_antigas.delete()     # dispensações caem em cascata
            ciclos_antigos.delete()
            guias_antigas.delete()

        if opts["clear"]:
            if opts["apply"]:
                _limpar()
                self.stdout.write(self.style.SUCCESS("Lote removido. Fim (--clear)."))
            else:
                self.stdout.write("[preview] removeria o lote acima. Use --apply.")
            return

        protocolos = {p.codigo: p for p in
                      ProtocoloOncologico.objects.using(DB).filter(empresa=empresa)}
        if not protocolos:
            raise CommandError(
                "Nenhum protocolo cadastrado neste tenant. Abra a tela de oncologia "
                "uma vez (ela semeia os protocolos PCDT/INCA) e rode de novo.")

        # Usa os protocolos que existirem, sem assumir códigos fixos.
        codigos = sorted(protocolos)
        proto_a = protocolos[codigos[0]]
        proto_b = protocolos[codigos[1 % len(codigos)]]

        if not opts["apply"]:
            self.stdout.write(
                "[preview] criaria: 3 guias (vigente / em análise / negada fora do "
                "prazo), 3 ciclos (apto, inapto por neutropenia, e um dosado), "
                "2 reservas de cadeira, 3 preparos conferidos, 2 administrações "
                "(uma com extravasamento) e 3 avaliações RECIST. Use --apply.")
            return

        with transaction.atomic(using=DB):
            _limpar()

            # ── Guias: uma de cada situação do relógio da RN 623/2024 ──────────
            GuiaOncologica.objects.using(DB).create(
                empresa=empresa, numero_guia="DEMO-G-1001",
                paciente_nome=f"{TAG} Marina Alves", tipo="quimioterapia",
                operadora="Operadora Demonstração", status="vigente",
                data_emissao=_dias(40), data_validade=date.today() + timedelta(days=150),
                ciclos_autorizados=6, ciclos_utilizados=2,
                data_solicitacao=_dias(45), data_resposta=_dias(42))
            GuiaOncologica.objects.using(DB).create(
                empresa=empresa, numero_guia="DEMO-G-1002",
                paciente_nome=f"{TAG} Carlos Prado", tipo="quimioterapia",
                operadora="Operadora Demonstração", status="em_analise",
                data_emissao=date.today(), data_validade=date.today() + timedelta(days=180),
                ciclos_autorizados=4, data_solicitacao=_dias(2))
            GuiaOncologica.objects.using(DB).create(
                empresa=empresa, numero_guia="DEMO-G-1003",
                paciente_nome=f"{TAG} Rosa Lima", tipo="quimioterapia",
                operadora="Operadora Demonstração", status="negada",
                data_emissao=_dias(20), data_validade=date.today() + timedelta(days=160),
                ciclos_autorizados=6, data_solicitacao=_dias(20),
                data_resposta=_dias(1), motivo_negativa="falta_documentacao",
                motivo_negativa_detalhe="Laudo anatomopatológico não anexado.")

            # ── Ciclos ────────────────────────────────────────────────────────
            c_apto = CicloQuimioterapia.objects.using(DB).create(
                empresa=empresa, protocolo=proto_a,
                paciente_nome=f"{TAG} Marina Alves", cid10_principal="C50",
                numero_ciclo=3, data_inicio=_dias(1), status="em_curso",
                peso_kg=64, altura_cm=162, sc_m2=1.6854,
                neutrofilos=2800, plaquetas=240000,
                creatinina_mg_dl=0.9, bilirrubina_mg_dl=0.6,
                aptidao_status="apto", aptidao_bloqueios=[],
                estadiamento="IIB", intencao_tratamento="curativa",
                confirmacao_patologica=True,
                medico_oncologista="Dra. HelenaDuarte",
                doses_calculadas=[
                    {"droga": d.get("droga"), "dose_referencia": d.get("dose"),
                     "unidade": d.get("unidade"), "dia": d.get("dia"),
                     "dose_calculada": round(float(d.get("dose") or 0) * 1.6854, 1)
                                        if "m²" in str(d.get("unidade") or "") else d.get("dose"),
                     "unidade_calculada": "mg", "cap_aplicado": False}
                    for d in (proto_a.drogas or [])],
            )
            CicloQuimioterapia.objects.using(DB).create(
                empresa=empresa, protocolo=proto_a,
                paciente_nome=f"{TAG} Carlos Prado", cid10_principal="C34",
                numero_ciclo=2, data_inicio=date.today(), status="agendado",
                peso_kg=78, altura_cm=175, sc_m2=1.9333,
                neutrofilos=800, plaquetas=90000,
                creatinina_mg_dl=1.1, bilirrubina_mg_dl=0.8,
                aptidao_status="inapto",
                aptidao_bloqueios=[
                    "Neutrófilos 800/mm³ abaixo do mínimo de 1500/mm³.",
                    "Plaquetas 90000/mm³ abaixo do mínimo de 100000/mm³.",
                ],
                estadiamento="IIIA", intencao_tratamento="curativa",
                confirmacao_patologica=True,
                medico_oncologista="Dr. Paulo Vieira",
            )
            c_dose = CicloQuimioterapia.objects.using(DB).create(
                empresa=empresa, protocolo=proto_b,
                paciente_nome=f"{TAG} Rosa Lima", cid10_principal="C56",
                numero_ciclo=1, data_inicio=_dias(7), status="concluido",
                peso_kg=70, altura_cm=168, sc_m2=1.8007,
                neutrofilos=3100, plaquetas=260000,
                creatinina_mg_dl=0.8, clearance_creatinina=88, bilirrubina_mg_dl=0.5,
                auc_alvo=5, aptidao_status="apto", aptidao_bloqueios=[],
                estadiamento="IIIC", intencao_tratamento="curativa",
                confirmacao_patologica=True,
                medico_oncologista="Dra. Helena Duarte",
                doses_calculadas=[
                    {"droga": "Carboplatina", "dose_referencia": 5, "unidade": "AUC",
                     "dia": 1, "dose_calculada": 565.0, "unidade_calculada": "mg",
                     "cap_aplicado": False, "auc_alvo": 5.0, "tfg_utilizada": 88.0,
                     "formula": "Calvert (AUC × [TFG + 25])"},
                ],
            )

            # ── Central de infusão ────────────────────────────────────────────
            AgendamentoInfusao.objects.using(DB).create(
                empresa=empresa, ciclo=c_apto, data=date.today(),
                hora_inicio=time(8, 0), duracao_min=180, cadeira="P1",
                status="em_curso", agendado_por="Enf. Juliana Reis")
            AgendamentoInfusao.objects.using(DB).create(
                empresa=empresa, ciclo=c_dose, data=date.today(),
                hora_inicio=time(13, 0), duracao_min=240, cadeira="P2",
                status="reservado", agendado_por="Enf. Juliana Reis")

            # ── Farmácia: cadeia completa até a conferência ────────────────────
            def _preparo(ciclo, droga, prescrita, preparada, lote, dias_val):
                return PreparoQuimioterapia.objects.using(DB).create(
                    empresa=empresa, ciclo=ciclo, droga=droga,
                    dose_prescrita=prescrita, dose_preparada=preparada, unidade="mg",
                    lote=lote, validade_lote=date.today() + timedelta(days=dias_val),
                    diluente="SF 0,9% 250 mL", volume_final_ml=250,
                    status="conferido",
                    preparado_por="Farm. André Moraes",
                    conferido_por="Farm. Letícia Campos",
                    preparado_em=_aware(date.today(), time(7, 10)),
                    conferido_em=_aware(date.today(), time(7, 25)))

            drogas_a = (proto_a.drogas or [{"droga": "Quimioterápico", "dose": 100}])
            p1 = _preparo(c_apto, str(drogas_a[0].get("droga") or "Quimioterápico"),
                          140, 140, "LT-4417", 240)
            p2 = _preparo(c_dose, "Carboplatina", 565, 560, "LT-9032", 180)
            # Um preparo ainda na fila: é o que faz o KPI da farmácia sair de zero.
            PreparoQuimioterapia.objects.using(DB).create(
                empresa=empresa, ciclo=c_apto, droga="Ondansetrona",
                dose_prescrita=8, unidade="mg", status="pendente")

            # ── Beira do leito ────────────────────────────────────────────────
            AdministracaoQuimioterapia.objects.using(DB).create(
                empresa=empresa, preparo=p1, ciclo=c_apto, via="porto",
                inicio=_aware(date.today(), time(8, 15)),
                fim=_aware(date.today(), time(10, 45)),
                dose_administrada=140,
                administrado_por="Enf. Juliana Reis", checado_por="Enf. Marcos Tavares",
                intercorrencia="nenhuma")
            AdministracaoQuimioterapia.objects.using(DB).create(
                empresa=empresa, preparo=p2, ciclo=c_dose, via="periferico",
                inicio=_aware(_dias(7), time(13, 20)),
                fim=_aware(_dias(7), time(16, 5)),
                dose_administrada=560,
                administrado_por="Enf. Marcos Tavares", checado_por="Enf. Juliana Reis",
                intercorrencia="extravasamento",
                intercorrencia_conduta="Infusão interrompida, aspiração pelo acesso, "
                                       "compressa fria e elevação do membro. "
                                       "Oncologista avisado; sem necrose em 24h.")
            p1.status = "dispensado"
            p1.save(using=DB, update_fields=["status"])
            p2.status = "dispensado"
            p2.save(using=DB, update_fields=["status"])

            # ── RECIST: basal → resposta parcial → progressão ─────────────────
            AvaliacaoRespostaOncologica.objects.using(DB).create(
                empresa=empresa, paciente_nome=f"{TAG} Marina Alves",
                data_avaliacao=_dias(90), metodo="tc", basal=True,
                soma_lesoes_mm=84, resposta="ne",
                avaliador="Dra. Helena Duarte")
            AvaliacaoRespostaOncologica.objects.using(DB).create(
                empresa=empresa, paciente_nome=f"{TAG} Marina Alves",
                ciclo=c_apto, data_avaliacao=_dias(30), metodo="tc",
                soma_lesoes_mm=52, resposta="rp",
                variacao_vs_basal_pct=-38.1, variacao_vs_nadir_pct=-38.1,
                avaliador="Dra. Helena Duarte")
            # Progressão medida contra o NADIR (52 mm), não contra a basal — é o
            # caso que separa a régua RECIST de uma conta simples: 68 mm ainda
            # está abaixo dos 84 mm iniciais e mesmo assim é doença progressiva.
            AvaliacaoRespostaOncologica.objects.using(DB).create(
                empresa=empresa, paciente_nome=f"{TAG} Marina Alves",
                ciclo=c_apto, data_avaliacao=_dias(3), metodo="tc",
                soma_lesoes_mm=68, resposta="dp",
                variacao_vs_basal_pct=-19.0, variacao_vs_nadir_pct=30.8,
                avaliador="Dra. Helena Duarte")

            # ── Quimioterapia oral: o paciente que some de casa ───────────
            # Adesão de 50% no intervalo — é o caso que faz a tela mostrar que
            # "o tratamento não respondeu" pode ser outra coisa.
            oral = PrescricaoQuimioOral.objects.using(DB).create(
                empresa=empresa, paciente_nome=f"{TAG} AntônioBezerra",
                droga="Capecitabina", dose_por_tomada=1500, unidade="mg",
                unidades_por_dia=2, dias_uso=14, dias_pausa=7,
                posologia="2 comprimidos de 12 em 12 horas, após as refeições",
                data_inicio=_dias(42), status="ativa",
                medico="Dr. Paulo Vieira")
            DispensacaoQuimioOral.objects.using(DB).create(
                empresa=empresa, prescricao=oral, data=_dias(42),
                unidades_dispensadas=28, unidades_devolvidas=0,
                proxima_retirada=_dias(21), dispensado_por="Farm. Letícia Campos")
            DispensacaoQuimioOral.objects.using(DB).create(
                empresa=empresa, prescricao=oral, data=_dias(21),
                unidades_dispensadas=28, unidades_devolvidas=14, adesao_pct=50.0,
                proxima_retirada=_dias(5), dispensado_por="Farm. Letícia Campos",
                observacao="Paciente relata náusea; devolveu metade da caixa.")

        self.stdout.write(self.style.SUCCESS(
            f"OK — lote {TAG} criado: 3 guias, 3 ciclos, 2 reservas de cadeira, "
            f"3 preparos, 2 administrações (1 com extravasamento), 3 avaliações "
            f"RECIST e 1 prescrição oral com adesão de 50% (retirada atrasada). "
            f"Reversível: rode com --apply --clear para remover."))
