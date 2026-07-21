from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0153_suas_assistencia_social'),
    ]

    operations = [
        migrations.AddField(
            model_name='atendimentoubs',
            name='assinado_digitalmente',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='atendimentoubs',
            name='assinado_digitalmente_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='atendimentoubs',
            name='assinatura_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='atendimentoubs',
            name='assinatura_icp',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='atendimentoubs',
            name='assinatura_metodo',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='atendimentoubs',
            name='assinatura_profissional',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]
