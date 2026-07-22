import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0159_farmacia_baixa_estoque_delivery_lote'),
    ]

    operations = [
        migrations.CreateModel(
            name='InconsistenciaCadastral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[
                    ('nis_duplicado', 'NIS Duplicado'),
                    ('pbf_renda_acima_limite', 'PBF — Renda acima do limite CadÚnico'),
                    ('integrantes_implausivel', 'Número de integrantes implausível'),
                    ('bpc_sem_marcador', 'BPC sem marcador no CadÚnico'),
                    ('familias_sem_cadunico', 'Família CRAS sem vínculo CadÚnico'),
                    ('creas_sem_vulnerabilidade', 'CREAS sem vulnerabilidade registrada'),
                    ('outro', 'Outro'),
                ], max_length=40)),
                ('severidade', models.CharField(choices=[
                    ('alta', 'Alta'), ('media', 'Média'), ('baixa', 'Baixa')
                ], default='media', max_length=10)),
                ('descricao', models.TextField()),
                ('dados_extras', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[
                    ('pendente', 'Pendente'), ('resolvida', 'Resolvida'), ('descartada', 'Descartada')
                ], default='pendente', max_length=15)),
                ('resolvida_por', models.CharField(blank=True, default='', max_length=160)),
                ('resolvida_em', models.DateTimeField(blank=True, null=True)),
                ('observacao', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assistencia_inconsistencias',
                    to='api.empresa',
                )),
            ],
            options={
                'verbose_name': 'Inconsistência Cadastral',
                'verbose_name_plural': 'Inconsistências Cadastrais',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='inconsistenciacadastral',
            index=models.Index(fields=['empresa', 'status'], name='api_inconsistencia_empresa_status_idx'),
        ),
        migrations.AddIndex(
            model_name='inconsistenciacadastral',
            index=models.Index(fields=['empresa', 'severidade', 'status'], name='api_inconsistencia_empresa_sev_status_idx'),
        ),
        migrations.CreateModel(
            name='ProntuarioSocialPAIF',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tecnico_responsavel', models.CharField(max_length=160)),
                ('data_abertura', models.DateField()),
                ('data_encerramento', models.DateField(blank=True, null=True)),
                ('modalidade', models.CharField(choices=[
                    ('recepcao_acolhida', 'Recepção/Acolhida'),
                    ('acompanhamento_paif', 'Acompanhamento PAIF'),
                    ('atividade_coletiva', 'Atividade Coletiva'),
                    ('encaminhamento', 'Encaminhamento'),
                    ('visita_domiciliar', 'Visita Domiciliar'),
                ], default='acompanhamento_paif', max_length=30)),
                ('situacoes_vulnerabilidade', models.JSONField(
                    blank=True, default=list,
                    help_text='Lista de códigos de SITUACAO_VULNERABILIDADE_CHOICES',
                )),
                ('objetivos', models.TextField(blank=True, default='')),
                ('evolucao', models.TextField(blank=True, default='')),
                ('encaminhamentos', models.TextField(blank=True, default='')),
                ('plano_acao_familiar', models.TextField(blank=True, default='')),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assistencia_prontuarios_paif',
                    to='api.empresa',
                )),
                ('familia', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='prontuarios_paif',
                    to='api.familiacras',
                )),
                ('unidade_cras', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='prontuarios_paif',
                    to='api.unidadecras',
                )),
            ],
            options={
                'verbose_name': 'Prontuário Social PAIF',
                'verbose_name_plural': 'Prontuários Sociais PAIF',
                'ordering': ['-data_abertura'],
            },
        ),
        migrations.AddIndex(
            model_name='prontuariosocialpaif',
            index=models.Index(fields=['empresa', 'ativo'], name='api_prontuariopaif_empresa_ativo_idx'),
        ),
        migrations.AddIndex(
            model_name='prontuariosocialpaif',
            index=models.Index(fields=['empresa', 'data_abertura'], name='api_prontuariopaif_empresa_dt_idx'),
        ),
    ]
