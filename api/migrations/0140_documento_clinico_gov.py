from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0139_rename_indexes_diaggov_reuniao'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentoClinicoGov',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[
                        ('receita', 'Receita Médica'),
                        ('atestado', 'Atestado Médico'),
                        ('exame', 'Solicitação de Exame'),
                    ],
                    max_length=20,
                )),
                ('paciente_nome', models.CharField(max_length=200)),
                ('cns', models.CharField(blank=True, max_length=20)),
                ('profissional', models.CharField(blank=True, max_length=200)),
                ('dados', models.JSONField(default=dict)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos_clinicos_gov',
                    to='api.empresa',
                )),
                ('teleconsulta', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='documentos',
                    to='api.teleconsultagoverno',
                )),
            ],
            options={
                'ordering': ['-criado_em'],
            },
        ),
    ]
