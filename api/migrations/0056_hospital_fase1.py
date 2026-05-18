from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0055_farmacia_fase2"),
    ]

    operations = [
        # ── PacienteInternado: campos clínicos + isolamento ──────────────────
        migrations.AddField(model_name="pacienteinternado", name="diagnostico_descricao",
            field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="pacienteinternado", name="medico_crm",
            field=models.CharField(blank=True, default="", max_length=30)),
        migrations.AddField(model_name="pacienteinternado", name="numero_prontuario",
            field=models.CharField(blank=True, default="", max_length=50)),
        migrations.AddField(model_name="pacienteinternado", name="tipo_sanguineo",
            field=models.CharField(blank=True, default="", max_length=5)),
        migrations.AddField(model_name="pacienteinternado", name="alergias",
            field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="pacienteinternado", name="peso_kg",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
        migrations.AddField(model_name="pacienteinternado", name="altura_cm",
            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="pacienteinternado", name="tipo_isolamento",
            field=models.CharField(
                choices=[("nenhum","Sem isolamento"),("contato","Precaução de contato"),
                         ("gotículas","Precaução por gotículas"),("aerossol","Precaução por aerossol"),
                         ("protetor","Isolamento protetor")],
                default="nenhum", max_length=20)),
        migrations.AddField(model_name="pacienteinternado", name="motivo_isolamento",
            field=models.TextField(blank=True, default="")),

        # ── EvolucaoClinicaInternado ─────────────────────────────────────────
        migrations.CreateModel(
            name="EvolucaoClinicaInternado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="evolucoes_estruturadas", to="api.pacienteinternado")),
                ("tipo", models.CharField(choices=[
                    ("medica","Evolução Médica"),("enfermagem","Evolução de Enfermagem"),
                    ("fisio","Fisioterapia"),("nutricao","Nutrição"),("psicologia","Psicologia"),
                    ("social","Serviço Social"),("farmacia","Farmácia Clínica"),("outro","Outro"),
                ], default="medica", max_length=20)),
                ("descricao", models.TextField()),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("crm_coren", models.CharField(blank=True, default="", max_length=30)),
                ("sinais_vitais", models.JSONField(default=dict)),
                ("registrado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-registrado_em"]},
        ),

        # ── MonitoramentoUTI ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="MonitoramentoUTI",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="monitoramentos_uti", to="api.pacienteinternado")),
                ("registrado_em", models.DateTimeField(auto_now_add=True)),
                ("pressao_arterial", models.CharField(blank=True, default="", max_length=20)),
                ("pressao_arterial_media", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("frequencia_cardiaca", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("frequencia_respiratoria", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("temperatura", models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ("saturacao_o2", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("diurese_ml", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("glasgow_ocular", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("glasgow_verbal", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("glasgow_motor", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sofa_respiratorio", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sofa_coagulacao", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sofa_hepatico", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sofa_cardiovascular", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sofa_neurologico", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sofa_renal", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("ventilacao_mecanica", models.BooleanField(default=False)),
                ("modo_ventilatorio", models.CharField(blank=True, default="", max_length=50)),
                ("fio2_pct", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("peep", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("volume_corrente_ml", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("drogas_vasoativas", models.BooleanField(default=False)),
                ("droga_vasoativa_desc", models.CharField(blank=True, default="", max_length=200)),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("observacoes", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["-registrado_em"],
                "indexes": [models.Index(fields=["paciente", "registrado_em"], name="mon_uti_pac_dt_idx")],
            },
        ),

        # ── SumarioAlta ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="SumarioAlta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paciente", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name="sumario_alta", to="api.pacienteinternado")),
                ("tipo_alta", models.CharField(choices=[
                    ("alta_medica","Alta Médica"),("alta_voluntaria","Alta a Pedido"),
                    ("transferencia","Transferência"),("obito","Óbito"),("evasao","Evasão"),
                ], default="alta_medica", max_length=20)),
                ("data_alta", models.DateTimeField()),
                ("medico_responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("medico_crm", models.CharField(blank=True, default="", max_length=30)),
                ("diagnostico_final", models.TextField(blank=True, default="")),
                ("cid_principal", models.CharField(blank=True, default="", max_length=20)),
                ("cid_secundarios", models.JSONField(default=list)),
                ("resumo_internacao", models.TextField(blank=True, default="")),
                ("procedimentos_realizados", models.TextField(blank=True, default="")),
                ("medicamentos_alta", models.JSONField(default=list)),
                ("orientacoes_paciente", models.TextField(blank=True, default="")),
                ("retorno_previsao", models.DateField(blank=True, null=True)),
                ("restricoes_atividade", models.TextField(blank=True, default="")),
                ("encaminhamentos", models.TextField(blank=True, default="")),
                ("condicao_alta", models.CharField(choices=[
                    ("curado","Curado"),("melhorado","Melhorado"),("inalterado","Inalterado"),
                    ("piorado","Piorado"),("obito","Óbito"),
                ], default="melhorado", max_length=20)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-data_alta"]},
        ),

        # ── CentroCirurgico ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="CentroCirurgico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="cirurgias", to="api.empresa")),
                ("paciente", models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="cirurgias", to="api.pacienteinternado")),
                ("data_hora_prevista", models.DateTimeField()),
                ("data_hora_inicio", models.DateTimeField(blank=True, null=True)),
                ("data_hora_fim", models.DateTimeField(blank=True, null=True)),
                ("sala", models.CharField(blank=True, default="", max_length=50)),
                ("procedimento", models.CharField(max_length=300)),
                ("codigo_tuss", models.CharField(blank=True, default="", max_length=20)),
                ("porte", models.CharField(choices=[
                    ("pequeno","Pequeno Porte"),("medio","Médio Porte"),
                    ("grande","Grande Porte"),("especial","Especial"),
                ], default="medio", max_length=20)),
                ("cirurgiao_principal", models.CharField(blank=True, default="", max_length=200)),
                ("cirurgiao_crm", models.CharField(blank=True, default="", max_length=30)),
                ("anestesiologista", models.CharField(blank=True, default="", max_length=200)),
                ("tipo_anestesia", models.CharField(blank=True, default="", max_length=50)),
                ("equipe", models.JSONField(default=list)),
                ("status", models.CharField(choices=[
                    ("agendado","Agendado"),("em_andamento","Em Andamento"),
                    ("concluido","Concluído"),("cancelado","Cancelado"),("suspenso","Suspenso"),
                ], default="agendado", max_length=20)),
                ("cid_indicacao", models.CharField(blank=True, default="", max_length=20)),
                ("relatorio_cirurgico", models.TextField(blank=True, default="")),
                ("intercorrencias", models.TextField(blank=True, default="")),
                ("sangramento_ml", models.PositiveIntegerField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["data_hora_prevista"],
                "indexes": [
                    models.Index(fields=["empresa", "status"], name="cc_emp_status_idx"),
                    models.Index(fields=["empresa", "data_hora_prevista"], name="cc_emp_dt_idx"),
                ],
            },
        ),
    ]
