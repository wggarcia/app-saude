from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """MPI leve do segmento Hospital (Fase 0 + Fase 1 da convergência de
    identidade de paciente) — cria o hub IdentidadePaciente e liga
    PacienteInternado (Moderna) e ProntuarioHospitalar (EMR) a ele.

    Puramente aditivo: colunas novas, todas nullable, nenhuma constraint
    NOT NULL/UNIQUE. Dados existentes continuam válidos sem backfill —
    o backfill roda na migração seguinte (0156)."""

    dependencies = [
        ('api', '0154_atendimentoubs_assinatura'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdentidadePaciente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=200)),
                ('cpf', models.CharField(
                    blank=True, default='',
                    help_text='Somente dígitos — normalizado via cpf_digitos()',
                    max_length=11,
                )),
                ('cns', models.CharField(blank=True, default='', max_length=18, verbose_name='CNS')),
                ('data_nascimento', models.DateField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='identidades_paciente', to='api.empresa',
                )),
            ],
            options={
                'verbose_name': 'Identidade de Paciente (MPI)',
                'verbose_name_plural': 'Identidades de Paciente (MPI)',
                'ordering': ['nome'],
                'indexes': [
                    models.Index(fields=['empresa', 'cpf'], name='idx_identpac_empresa_cpf'),
                    models.Index(fields=['empresa', 'nome'], name='idx_identpac_empresa_nome'),
                ],
            },
        ),
        migrations.AddField(
            model_name='pacienteinternado',
            name='identidade',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='perfis_internacao', to='api.identidadepaciente',
                help_text='Vínculo com a identidade única do paciente (MPI) — populado por sync, não exposto na UI',
            ),
        ),
        migrations.AddField(
            model_name='prontuariohospitalar',
            name='identidade',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='prontuarios', to='api.identidadepaciente',
                help_text='Vínculo com a identidade única do paciente (MPI) — populado por sync, não exposto na UI',
            ),
        ),
    ]
