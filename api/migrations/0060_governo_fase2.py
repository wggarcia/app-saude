"""
Migration 0060 — Governo Fase 2
Cria as tabelas: UnidadeSaude, EquipeSaude, SurtoEpidemiologico,
NotificacaoCompulsoria, RegulacaoLeito, ProducaoAmbulatorial,
MetaPrevine, ContratoGestao, AtendimentoUrgencia
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0059_alter_centrocirurgico_equipe_and_more"),
    ]

    operations = [
        # ── UnidadeSaude ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="UnidadeSaude",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cnes", models.CharField(blank=True, default="", max_length=7)),
                ("nome", models.CharField(max_length=200)),
                ("tipo", models.CharField(max_length=20, choices=[
                    ("ubs","UBS — Unidade Básica de Saúde"),("upa","UPA 24h"),
                    ("caps_i","CAPS I"),("caps_ii","CAPS II"),("caps_iii","CAPS III — 24h"),
                    ("caps_ad","CAPS AD"),("caps_inf","CAPS Infantil"),("hospital","Hospital"),
                    ("amb","Ambulatório Especializado"),("ceo","CEO — Centro Odontológico"),
                    ("policlinica","Policlínica"),("cerest","CEREST"),("laboratorio","Laboratório Público"),
                    ("cco","CCO — Central de Regulação"),("outro","Outro"),
                ])),
                ("status", models.CharField(default="ativa", max_length=20, choices=[
                    ("ativa","Ativa"),("inativa","Inativa"),("obras","Em Obras"),("interditada","Interditada"),
                ])),
                ("municipio", models.CharField(max_length=100)),
                ("uf", models.CharField(max_length=2)),
                ("bairro", models.CharField(blank=True, default="", max_length=100)),
                ("endereco", models.CharField(blank=True, default="", max_length=300)),
                ("telefone", models.CharField(blank=True, default="", max_length=20)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True)),
                ("populacao_referenciada", models.PositiveIntegerField(default=0)),
                ("leitos_sus", models.PositiveSmallIntegerField(default=0)),
                ("leitos_uti", models.PositiveSmallIntegerField(default=0)),
                ("diretor", models.CharField(blank=True, default="", max_length=200)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unidades_saude", to="api.empresa")),
            ],
            options={"ordering": ["municipio", "nome"]},
        ),
        migrations.AddIndex(
            model_name="unidadesaude",
            index=models.Index(fields=["empresa","tipo"], name="api_unid_empresa_tipo_idx"),
        ),
        migrations.AddIndex(
            model_name="unidadesaude",
            index=models.Index(fields=["empresa","municipio"], name="api_unid_empresa_mun_idx"),
        ),

        # ── EquipeSaude ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="EquipeSaude",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200)),
                ("tipo", models.CharField(default="esf", max_length=10, choices=[
                    ("esf","eSF — Saúde da Família"),("esb","eSB — Saúde Bucal"),
                    ("nasf","NASF-AB"),("acs","ACS — Agentes"),("outro","Outro"),
                ])),
                ("ine", models.CharField(blank=True, default="", max_length=10)),
                ("area_codigo", models.CharField(blank=True, default="", max_length=10)),
                ("populacao_cadastrada", models.PositiveIntegerField(default=0)),
                ("ativa", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="equipes_saude", to="api.empresa")),
                ("unidade", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="equipes", to="api.unidadesaude")),
            ],
            options={"ordering": ["unidade", "nome"]},
        ),

        # ── SurtoEpidemiologico ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="SurtoEpidemiologico",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doenca", models.CharField(max_length=100)),
                ("municipio", models.CharField(max_length=100)),
                ("uf", models.CharField(max_length=2)),
                ("bairro", models.CharField(blank=True, default="", max_length=100)),
                ("data_inicio", models.DateField()),
                ("data_encerramento", models.DateField(blank=True, null=True)),
                ("total_casos", models.PositiveIntegerField(default=0)),
                ("total_obitos", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(default="ativo", max_length=20, choices=[
                    ("ativo","Ativo — Investigação em Curso"),("controlado","Controlado"),("encerrado","Encerrado"),
                ])),
                ("nivel_alerta", models.CharField(default="amarelo", max_length=10, choices=[
                    ("verde","Verde"),("amarelo","Amarelo"),("laranja","Laranja"),("vermelho","Vermelho"),
                ])),
                ("acoes_resposta", models.TextField(blank=True, default="")),
                ("responsavel_investigacao", models.CharField(blank=True, default="", max_length=200)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="surtos_epidemiologicos", to="api.empresa")),
            ],
            options={"ordering": ["-data_inicio"]},
        ),

        # ── NotificacaoCompulsoria ──────────────────────────────────────────────
        migrations.CreateModel(
            name="NotificacaoCompulsoria",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doenca", models.CharField(max_length=30, choices=[
                    ("dengue","Dengue"),("zika","Zika Vírus"),("chikungunya","Chikungunya"),
                    ("malaria","Malária"),("febre_amarela","Febre Amarela"),
                    ("leishmaniose_visceral","Leishmaniose Visceral"),("leishmaniose_tegumentar","Leishmaniose Tegumentar"),
                    ("leptospirose","Leptospirose"),("esquistossomose","Esquistossomose"),
                    ("doenca_chagas","Doença de Chagas"),("tuberculose","Tuberculose"),
                    ("hanseniase","Hanseníase"),("hiv_aids","HIV/AIDS"),("sifilis","Sífilis"),
                    ("sifilis_congenita","Sífilis Congênita"),("hepatite_a","Hepatite A"),
                    ("hepatite_b","Hepatite B"),("hepatite_c","Hepatite C"),
                    ("meningite","Meningite"),("sarampo","Sarampo"),("rubeola","Rubéola"),
                    ("coqueluche","Coqueluche"),("difteria","Difteria"),("tetano","Tétano"),
                    ("raiva","Raiva"),("antraz","Antraz/Carbúnculo"),
                    ("influenza_grave","Influenza Grave"),("covid19","COVID-19"),
                    ("mpox","Mpox"),("botulismo","Botulismo"),("colera","Cólera"),
                    ("plague","Peste"),("variola","Varíola"),("ebola","Ebola"),
                    ("intoxicacao","Intoxicação Exógena"),("acidente_trabalho","Acidente de Trabalho Grave"),
                    ("violencia","Violência Interpessoal/Autoprovocada"),("outro","Outro"),
                ])),
                ("data_notificacao", models.DateField()),
                ("data_inicio_sintomas", models.DateField(blank=True, null=True)),
                ("municipio_notificacao", models.CharField(max_length=100)),
                ("uf_notificacao", models.CharField(max_length=2)),
                ("idade_paciente", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sexo", models.CharField(default="I", max_length=1, choices=[("M","Masculino"),("F","Feminino"),("I","Ignorado")])),
                ("zona", models.CharField(default="urbana", max_length=10, choices=[("urbana","Urbana"),("rural","Rural"),("periurbana","Periurbana")])),
                ("status_investigacao", models.CharField(default="aberto", max_length=20, choices=[("aberto","Aberto"),("em_investigacao","Em Investigação"),("encerrado","Encerrado")])),
                ("evolucao", models.CharField(default="ativo", max_length=20, choices=[("ativo","Em Acompanhamento"),("curado","Curado"),("obito","Óbito"),("ignorado","Ignorado/Inconclusivo")])),
                ("observacoes", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notificacoes_compulsorias", to="api.empresa")),
                ("unidade_notificante", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notificacoes", to="api.unidadesaude")),
                ("surto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notificacoes", to="api.surtoepidemiologico")),
            ],
            options={"ordering": ["-data_notificacao"]},
        ),
        migrations.AddIndex(
            model_name="notificacaocompulsoria",
            index=models.Index(fields=["empresa","doenca"], name="api_notif_empresa_doenca_idx"),
        ),
        migrations.AddIndex(
            model_name="notificacaocompulsoria",
            index=models.Index(fields=["empresa","data_notificacao"], name="api_notif_empresa_data_idx"),
        ),
        migrations.AddIndex(
            model_name="notificacaocompulsoria",
            index=models.Index(fields=["empresa","municipio_notificacao"], name="api_notif_empresa_mun_idx"),
        ),

        # ── RegulacaoLeito ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="RegulacaoLeito",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero_solicitacao", models.CharField(max_length=20, unique=True)),
                ("tipo_leito", models.CharField(max_length=20, choices=[
                    ("uti_adulto","UTI Adulto"),("uti_neo","UTI Neonatal"),("uti_ped","UTI Pediátrica"),
                    ("clinico","Clínico"),("cirurgico","Cirúrgico"),("obstetricia","Obstetrícia"),
                    ("psiquiatria","Psiquiatria"),("queimados","Queimados"),("outro","Outro"),
                ])),
                ("prioridade", models.CharField(default="urgencia", max_length=20, choices=[
                    ("emergencia","Emergência"),("urgencia","Urgência"),("eletivo","Eletivo"),
                ])),
                ("status", models.CharField(default="solicitado", max_length=20, choices=[
                    ("solicitado","Solicitado"),("regulado","Regulado — Aguardando Vaga"),
                    ("internado","Internado"),("cancelado","Cancelado"),("obito_espera","Óbito na Fila"),
                ])),
                ("cid_principal", models.CharField(blank=True, default="", max_length=10)),
                ("diagnostico", models.CharField(blank=True, default="", max_length=300)),
                ("idade_paciente", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("municipio_origem", models.CharField(blank=True, default="", max_length=100)),
                ("medico_solicitante", models.CharField(blank=True, default="", max_length=200)),
                ("data_solicitacao", models.DateTimeField(auto_now_add=True)),
                ("data_regulacao", models.DateTimeField(blank=True, null=True)),
                ("data_internacao", models.DateTimeField(blank=True, null=True)),
                ("tempo_espera_horas", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("observacoes", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="regulacoes_leito", to="api.empresa")),
                ("unidade_origem", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="solicitacoes_regulacao", to="api.unidadesaude")),
                ("unidade_destino", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="vagas_regulacao", to="api.unidadesaude")),
            ],
            options={"ordering": ["-data_solicitacao"]},
        ),
        migrations.AddIndex(
            model_name="regulacaoleito",
            index=models.Index(fields=["empresa","status"], name="api_reg_empresa_status_idx"),
        ),
        migrations.AddIndex(
            model_name="regulacaoleito",
            index=models.Index(fields=["empresa","tipo_leito"], name="api_reg_empresa_tipo_idx"),
        ),

        # ── ProducaoAmbulatorial ────────────────────────────────────────────────
        migrations.CreateModel(
            name="ProducaoAmbulatorial",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("competencia", models.CharField(max_length=7)),
                ("consultas_basicas", models.PositiveIntegerField(default=0)),
                ("consultas_especializadas", models.PositiveIntegerField(default=0)),
                ("procedimentos_basicos", models.PositiveIntegerField(default=0)),
                ("procedimentos_especializados", models.PositiveIntegerField(default=0)),
                ("exames_realizados", models.PositiveIntegerField(default=0)),
                ("visitas_domiciliares", models.PositiveIntegerField(default=0)),
                ("acolhimentos", models.PositiveIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="producoes_ambulatoriais", to="api.empresa")),
                ("unidade", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="producoes", to="api.unidadesaude")),
            ],
            options={"ordering": ["-competencia"]},
        ),
        migrations.AddConstraint(
            model_name="producaoambulatorial",
            constraint=models.UniqueConstraint(fields=["empresa","unidade","competencia"], name="api_producao_unique"),
        ),

        # ── MetaPrevine ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="MetaPrevine",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("indicador", models.CharField(max_length=30, choices=[
                    ("prenatal_6","Pré-natal — ≥6 consultas + 1º trim."),
                    ("prenatal_sifilis_hiv","Pré-natal — Sífilis e HIV"),
                    ("gestante_odonto","Gestantes com atendimento odontológico"),
                    ("consumo_alcool","Usuários de álcool/drogas com avaliação"),
                    ("hipertensos","Hipertensos com PA aferida"),
                    ("diabeticos","Diabéticos com HbA1c solicitada"),
                    ("criancas_obesidade","Crianças <5 anos com avaliação nutricional"),
                    ("saude_bucal_ab","Saúde bucal — procedimentos clínicos"),
                    ("visita_puerpera","Puérperas com visita na 1ª semana"),
                ])),
                ("competencia", models.CharField(max_length=7)),
                ("municipio", models.CharField(blank=True, default="", max_length=100)),
                ("denominador", models.PositiveIntegerField(default=0)),
                ("numerador", models.PositiveIntegerField(default=0)),
                ("meta_percentual", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("resultado_percentual", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("atingiu_meta", models.BooleanField(default=False)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metas_previne", to="api.empresa")),
            ],
            options={"ordering": ["-competencia", "indicador"]},
        ),
        migrations.AddConstraint(
            model_name="metaprevine",
            constraint=models.UniqueConstraint(fields=["empresa","indicador","competencia","municipio"], name="api_previne_unique"),
        ),

        # ── ContratoGestao ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="ContratoGestao",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero_contrato", models.CharField(max_length=50)),
                ("fornecedor_nome", models.CharField(max_length=300)),
                ("fornecedor_cnpj", models.CharField(blank=True, default="", max_length=18)),
                ("tipo", models.CharField(max_length=20, choices=[
                    ("hospital","Hospital Contratado"),("clinica","Clínica/AMB"),("laboratorio","Laboratório"),
                    ("imagem","Imagem/Diagnóstico"),("sadt","SADT"),("oss","OSS"),
                    ("convenio_federal","Convênio Federal"),("convenio_estadual","Convênio Estadual"),("outro","Outro"),
                ])),
                ("status", models.CharField(default="vigente", max_length=20, choices=[
                    ("vigente","Vigente"),("vencido","Vencido"),("suspenso","Suspenso"),("rescindido","Rescindido"),
                ])),
                ("objeto", models.TextField()),
                ("valor_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("valor_mensal", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("data_inicio", models.DateField()),
                ("data_fim", models.DateField()),
                ("gestor_contrato", models.CharField(blank=True, default="", max_length=200)),
                ("producao_prevista", models.JSONField(default=dict)),
                ("producao_realizada", models.JSONField(default=dict)),
                ("observacoes", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contratos_gestao", to="api.empresa")),
            ],
            options={"ordering": ["-data_inicio"]},
        ),
        migrations.AddIndex(
            model_name="contratogestao",
            index=models.Index(fields=["empresa","status"], name="api_cgestao_empresa_status_idx"),
        ),
        migrations.AddIndex(
            model_name="contratogestao",
            index=models.Index(fields=["empresa","tipo"], name="api_cgestao_empresa_tipo_idx"),
        ),

        # ── AtendimentoUrgencia ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="AtendimentoUrgencia",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_unidade", models.CharField(max_length=20, choices=[
                    ("samu","SAMU 192"),("upa","UPA 24h"),("pronto_socorro","Pronto-Socorro"),("cco","CCO"),
                ])),
                ("data_atendimento", models.DateField()),
                ("total_atendimentos", models.PositiveIntegerField(default=0)),
                ("vermelho", models.PositiveIntegerField(default=0)),
                ("laranja", models.PositiveIntegerField(default=0)),
                ("amarelo", models.PositiveIntegerField(default=0)),
                ("verde", models.PositiveIntegerField(default=0)),
                ("azul", models.PositiveIntegerField(default=0)),
                ("obitos", models.PositiveIntegerField(default=0)),
                ("tempo_espera_medio_min", models.PositiveSmallIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="atendimentos_urgencia", to="api.empresa")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="atendimentos_urgencia", to="api.unidadesaude")),
            ],
            options={"ordering": ["-data_atendimento"]},
        ),
        migrations.AddConstraint(
            model_name="atendimentourgencia",
            constraint=models.UniqueConstraint(fields=["empresa","unidade","data_atendimento"], name="api_atend_unique"),
        ),
    ]
