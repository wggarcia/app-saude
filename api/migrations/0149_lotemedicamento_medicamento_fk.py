import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0148_funcionariosst_token_acesso'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotemedicamento',
            name='medicamento',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='lotes',
                to='api.medicamentofarmacia',
            ),
        ),
    ]
