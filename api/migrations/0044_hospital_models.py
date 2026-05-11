import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0043_farmacia_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeitoHospitalar",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(max_length=20)),
                ("ala", models.CharField(blank=True, default="", max_length=100)),
                ("tipo", models.CharField(
                    choices=[
                        ("uti", "UTI"),
                        ("enfermaria", "Enfermaria"),
                        ("particular", "Particular"),
                        ("emergencia", "Emergência"),
                        ("semi_intensivo", "Semi-Intensivo"),
                    ],
                    default="enfermaria",
                    max_length=20,
                )),
                ("status", models.CharField(
                    choices=[
                        ("livre", "Livre"),
                        ("ocupado", "Ocupado"),
                        ("manutencao", "Manutenção"),
                        ("bloqueado", "Bloqueado"),
                    ],
                    default="livre",
                    max_length=20,
                )),
                ("paciente_nome", models.CharField(blank=True, max_length=200, null=True)),
                ("paciente_id", models.UUIDField(blank=True, null=True)),
                ("data_internacao", models.DateField(blank=True, null=True)),
                ("previsao_alta", models.DateField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leitos_hospitalar",
                        to="api.empresa",
                    ),
                ),
            ],
            options={
                "ordering": ["ala", "numero"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="leitohospitalar",
            unique_together={("empresa", "numero")},
        ),
        migrations.CreateModel(
            name="TriagemManchester",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_hora", models.DateTimeField()),
                ("paciente_nome", models.CharField(max_length=200)),
                ("paciente_cpf", models.CharField(blank=True, max_length=14, null=True)),
                ("queixa_principal", models.TextField()),
                ("nivel", models.CharField(
                    choices=[
                        ("vermelho", "Vermelho — Emergência"),
                        ("laranja", "Laranja — Muito Urgente"),
                        ("amarelo", "Amarelo — Urgente"),
                        ("verde", "Verde — Pouco Urgente"),
                        ("azul", "Azul — Não Urgente"),
                    ],
                    max_length=20,
                )),
                ("tempo_espera_minutos", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(
                    choices=[
                        ("aguardando", "Aguardando"),
                        ("em_atendimento", "Em Atendimento"),
                        ("atendido", "Atendido"),
                        ("transferido", "Transferido"),
                        ("evadiu", "Evadiu"),
                    ],
                    default="aguardando",
                    max_length=20,
                )),
                ("medico_responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("observacao", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="triagens_manchester",
                        to="api.empresa",
                    ),
                ),
            ],
            options={
                "ordering": ["-data_hora"],
            },
        ),
        migrations.CreateModel(
            name="PacienteInternado",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200)),
                ("cpf", models.CharField(blank=True, default="", max_length=14)),
                ("data_nascimento", models.DateField(blank=True, null=True)),
                ("data_internacao", models.DateField()),
                ("diagnostico_cid", models.CharField(blank=True, default="", max_length=20)),
                ("medico_responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("convenio", models.CharField(blank=True, default="", max_length=200)),
                ("status", models.CharField(
                    choices=[
                        ("internado", "Internado"),
                        ("alta", "Alta"),
                        ("transferido", "Transferido"),
                        ("obito", "Óbito"),
                    ],
                    default="internado",
                    max_length=20,
                )),
                ("prescricao_atual", models.JSONField(default=dict)),
                ("evolucao", models.JSONField(default=list)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pacientes_internados",
                        to="api.empresa",
                    ),
                ),
                (
                    "leito",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pacientes_internados",
                        to="api.leitohospitalar",
                    ),
                ),
            ],
            options={
                "ordering": ["-data_internacao", "nome"],
            },
        ),
        migrations.CreateModel(
            name="PrescricaoHospitalar",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.DateField()),
                ("medicamentos", models.JSONField(default=list)),
                ("validade_horas", models.PositiveSmallIntegerField(default=24)),
                ("medico_crm", models.CharField(blank=True, default="", max_length=30)),
                ("medico_nome", models.CharField(blank=True, default="", max_length=200)),
                ("status", models.CharField(
                    choices=[
                        ("ativa", "Ativa"),
                        ("encerrada", "Encerrada"),
                        ("cancelada", "Cancelada"),
                    ],
                    default="ativa",
                    max_length=20,
                )),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="prescricoes_hospitalares",
                        to="api.empresa",
                    ),
                ),
                (
                    "paciente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="prescricoes_hospitalares",
                        to="api.pacienteinternado",
                    ),
                ),
            ],
            options={
                "ordering": ["-data", "-criado_em"],
            },
        ),
    ]
