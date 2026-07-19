from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0151_atendimentoubs_pressao'),
    ]

    operations = [
        migrations.AddField(
            model_name='agendamentoubs',
            name='data_solicitacao',
            field=models.DateField(blank=True, null=True),
        ),
    ]
