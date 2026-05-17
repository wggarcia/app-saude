# Moved to the end of the migration chain because production already applied 0046.

import api.models
import django.db.models.deletion
from django.db import migrations, models


def criar_tabela_assinatura_se_ausente(apps, schema_editor):
    table_name = 'api_assinaturadocumentosst'
    existing_tables = schema_editor.connection.introspection.table_names()
    if table_name in existing_tables:
        return

    Empresa = apps.get_model('api', 'Empresa')
    FuncionarioSST = apps.get_model('api', 'FuncionarioSST')

    class AssinaturaDocumentoSST(models.Model):
        tipo_documento = models.CharField(choices=[('aso', 'ASO'), ('cat', 'CAT'), ('prontuario', 'Prontuário SST'), ('documento_sst', 'Documento SST')], max_length=30)
        objeto_id = models.PositiveIntegerField()
        titulo = models.CharField(max_length=240)
        token = models.CharField(default=api.models._codigo_acesso, max_length=64, unique=True)
        status = models.CharField(choices=[('pendente', 'Pendente'), ('assinado', 'Assinado'), ('cancelado', 'Cancelado')], default='pendente', max_length=20)
        hash_documento = models.CharField(max_length=64)
        hash_assinatura = models.CharField(blank=True, default='', max_length=64)
        signatario_nome = models.CharField(blank=True, default='', max_length=180)
        signatario_email = models.EmailField(blank=True, default='', max_length=254)
        signatario_cpf = models.CharField(blank=True, default='', max_length=20)
        solicitado_por = models.CharField(blank=True, default='', max_length=180)
        ip_solicitacao = models.GenericIPAddressField(blank=True, null=True)
        ip_assinatura = models.GenericIPAddressField(blank=True, null=True)
        user_agent_assinatura = models.CharField(blank=True, default='', max_length=300)
        assinado_em = models.DateTimeField(blank=True, null=True)
        expiracao_em = models.DateTimeField(blank=True, null=True)
        criado_em = models.DateTimeField(auto_now_add=True)
        atualizado_em = models.DateTimeField(auto_now=True)
        empresa = models.ForeignKey(Empresa, on_delete=django.db.models.deletion.CASCADE, related_name='assinaturas_sst')
        funcionario = models.ForeignKey(FuncionarioSST, blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assinaturas_sst')

        class Meta:
            app_label = 'api'
            db_table = table_name
            indexes = [
                models.Index(fields=['empresa', 'status'], name='api_assinat_empresa_2ca5c2_idx'),
                models.Index(fields=['empresa', 'tipo_documento', 'objeto_id'], name='api_assinat_empresa_71725c_idx'),
                models.Index(fields=['token'], name='api_assinat_token_2d276c_idx'),
            ]

    schema_editor.create_model(AssinaturaDocumentoSST)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0052_solicitacao_exame_email'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(criar_tabela_assinatura_se_ausente, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='AssinaturaDocumentoSST',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('tipo_documento', models.CharField(choices=[('aso', 'ASO'), ('cat', 'CAT'), ('prontuario', 'Prontuário SST'), ('documento_sst', 'Documento SST')], max_length=30)),
                        ('objeto_id', models.PositiveIntegerField()),
                        ('titulo', models.CharField(max_length=240)),
                        ('token', models.CharField(default=api.models._codigo_acesso, max_length=64, unique=True)),
                        ('status', models.CharField(choices=[('pendente', 'Pendente'), ('assinado', 'Assinado'), ('cancelado', 'Cancelado')], default='pendente', max_length=20)),
                        ('hash_documento', models.CharField(max_length=64)),
                        ('hash_assinatura', models.CharField(blank=True, default='', max_length=64)),
                        ('signatario_nome', models.CharField(blank=True, default='', max_length=180)),
                        ('signatario_email', models.EmailField(blank=True, default='', max_length=254)),
                        ('signatario_cpf', models.CharField(blank=True, default='', max_length=20)),
                        ('solicitado_por', models.CharField(blank=True, default='', max_length=180)),
                        ('ip_solicitacao', models.GenericIPAddressField(blank=True, null=True)),
                        ('ip_assinatura', models.GenericIPAddressField(blank=True, null=True)),
                        ('user_agent_assinatura', models.CharField(blank=True, default='', max_length=300)),
                        ('assinado_em', models.DateTimeField(blank=True, null=True)),
                        ('expiracao_em', models.DateTimeField(blank=True, null=True)),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assinaturas_sst', to='api.empresa')),
                        ('funcionario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assinaturas_sst', to='api.funcionariosst')),
                    ],
                    options={
                        'ordering': ['-criado_em'],
                        'indexes': [models.Index(fields=['empresa', 'status'], name='api_assinat_empresa_2ca5c2_idx'), models.Index(fields=['empresa', 'tipo_documento', 'objeto_id'], name='api_assinat_empresa_71725c_idx'), models.Index(fields=['token'], name='api_assinat_token_2d276c_idx')],
                    },
                ),
            ],
        ),
    ]
