import uuid
from django.db import migrations, models


def _backfill_token_acesso(apps, schema_editor):
    FuncionarioSST = apps.get_model('api', 'FuncionarioSST')
    for func in FuncionarioSST.objects.filter(token_acesso__isnull=True):
        func.token_acesso = uuid.uuid4()
        func.save(update_fields=['token_acesso'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0147_empresa_endereco'),
    ]

    operations = [
        # 1 — adiciona coluna nullable (sem unique ainda)
        migrations.AddField(
            model_name='funcionariosst',
            name='token_acesso',
            field=models.UUIDField(null=True, blank=True),
        ),
        # 2 — preenche cada linha com um UUID distinto
        migrations.RunPython(_backfill_token_acesso, migrations.RunPython.noop),
        # 3 — aplica NOT NULL + UNIQUE agora que todos os valores são únicos
        migrations.AlterField(
            model_name='funcionariosst',
            name='token_acesso',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
