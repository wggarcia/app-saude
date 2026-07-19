from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0150_contratogrupo_proposta_renovacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='atendimentoubs',
            name='situacao_pressao',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='atendimentoubs',
            name='ultima_pa_sistolica',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
