from django.db import migrations, models
import api.models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0137_diagnostico_confirmado_gov'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReuniaoGoverno',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=140)),
                ('descricao', models.TextField(blank=True, default='')),
                ('data_hora', models.DateTimeField()),
                ('duracao_minutos', models.PositiveSmallIntegerField(default=60)),
                ('sala_jitsi', models.CharField(default=api.models._codigo_acesso, max_length=80, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('agendada', 'Agendada'), ('em_andamento', 'Em andamento'),
                        ('encerrada', 'Encerrada'), ('cancelada', 'Cancelada'),
                    ],
                    default='agendada', max_length=20,
                )),
                ('participantes_nomes', models.TextField(blank=True, default='', help_text='Um por linha: Nome — Cargo')),
                ('pauta', models.TextField(blank=True, default='', help_text='Itens de pauta, um por linha')),
                ('notas', models.TextField(blank=True, default='', help_text='Notas coletadas durante a reunião')),
                ('ata', models.TextField(blank=True, default='')),
                ('ata_gerada_em', models.DateTimeField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reunioes_gov',
                    to='api.empresa',
                )),
            ],
            options={
                'ordering': ['-data_hora'],
            },
        ),
        migrations.AddIndex(
            model_name='reuniaogoverno',
            index=models.Index(fields=['empresa', 'status', 'data_hora'], name='api_reugov_emp_status_idx'),
        ),
    ]
