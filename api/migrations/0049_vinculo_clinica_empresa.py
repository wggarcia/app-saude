"""
Cria VinculoClinicaEmpresa e ASOEnviadoClinica —
sistema de envio direto de ASOs entre clínica e empresa no SolusCRT.
"""
import api.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0048_cat_aso_campos_esocial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VinculoClinicaEmpresa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('empresa_cnpj', models.CharField(blank=True, default='', max_length=18, verbose_name='CNPJ da empresa')),
                ('empresa_nome', models.CharField(blank=True, default='', max_length=200, verbose_name='Nome da empresa')),
                ('empresa_email_convite', models.EmailField(blank=True, default='', max_length=254, verbose_name='E-mail para convite')),
                ('token_convite', models.CharField(default=api.models._codigo_acesso, max_length=64, unique=True)),
                ('status', models.CharField(choices=[('pendente', 'Aguardando aceitação'), ('ativo', 'Ativo'), ('suspenso', 'Suspenso'), ('recusado', 'Recusado')], default='pendente', max_length=20)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('aceito_em', models.DateTimeField(blank=True, null=True)),
                ('observacoes', models.TextField(blank=True, default='')),
                ('clinica', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vinculos_como_clinica', to='api.empresa', verbose_name='Clínica / prestadora')),
                ('empresa_contratante', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vinculos_como_empresa', to='api.empresa', verbose_name='Empresa contratante (conta SolusCRT)')),
            ],
            options={
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddConstraint(
            model_name='vinculoclinicaempresa',
            constraint=models.UniqueConstraint(fields=['clinica', 'empresa_contratante'], name='unique_vinculo_clinica_empresa'),
        ),
        migrations.AddIndex(
            model_name='vinculoclinicaempresa',
            index=models.Index(fields=['clinica', 'status'], name='api_vinculo_clinica_status_idx'),
        ),
        migrations.AddIndex(
            model_name='vinculoclinicaempresa',
            index=models.Index(fields=['empresa_contratante', 'status'], name='api_vinculo_empresa_status_idx'),
        ),
        migrations.AddIndex(
            model_name='vinculoclinicaempresa',
            index=models.Index(fields=['token_convite'], name='api_vinculo_token_idx'),
        ),
        migrations.CreateModel(
            name='ASOEnviadoClinica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('enviado', 'Enviado'), ('visualizado', 'Visualizado'), ('importado', 'Importado ao prontuário'), ('rejeitado', 'Rejeitado pela empresa')], default='enviado', max_length=20)),
                ('enviado_em', models.DateTimeField(auto_now_add=True)),
                ('visualizado_em', models.DateTimeField(blank=True, null=True)),
                ('importado_em', models.DateTimeField(blank=True, null=True)),
                ('observacao_empresa', models.TextField(blank=True, default='')),
                ('aso', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='envios_clinica', to='api.asoocupacional')),
                ('vinculo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asos_enviados', to='api.vinculoclinicaempresa')),
            ],
            options={
                'ordering': ['-enviado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='asoenviadoclinica',
            index=models.Index(fields=['vinculo', 'status'], name='api_aso_enviado_vinculo_idx'),
        ),
    ]
