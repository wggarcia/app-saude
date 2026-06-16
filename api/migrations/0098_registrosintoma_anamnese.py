from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0097_alter_notificacaofuncionario_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrosintoma",
            name="dias_sintomas",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="inicio_abrupto",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="viagem_area_endemica",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="exposicao_agua_enchente",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="contato_roedores",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="contato_caso_confirmado",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="vacinado_febre_amarela",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="registrosintoma",
            name="tem_comorbidade",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
