from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0100_perfil_granular_empresa_usuario"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="cortesia_ativa",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="empresa",
            name="cortesia_plano_original",
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name="empresa",
            name="cortesia_ciclo_original",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="empresa",
            name="cortesia_expira_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
