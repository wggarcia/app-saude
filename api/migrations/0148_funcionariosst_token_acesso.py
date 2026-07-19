import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0147_empresa_endereco'),
    ]

    operations = [
        migrations.AddField(
            model_name='funcionariosst',
            name='token_acesso',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
