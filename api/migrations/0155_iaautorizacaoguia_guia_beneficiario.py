from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0154_atendimentoubs_assinatura'),
    ]

    operations = [
        migrations.AddField(
            model_name='iaautorizacaoguia',
            name='guia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ia_autorizacoes',
                to='api.guiaautorizacao',
            ),
        ),
        migrations.AddField(
            model_name='iaautorizacaoguia',
            name='beneficiario_plano',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ia_autorizacoes',
                to='api.beneficiarioplano',
            ),
        ),
    ]
