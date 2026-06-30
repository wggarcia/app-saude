from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0126_funcionario_comunicado_lido"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="registrosintoma",
            index=models.Index(
                fields=["empresa", "data_registro", "estado", "cidade", "bairro"],
                name="regsintoma_mapa_bairro_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="registrosintoma",
            index=models.Index(
                fields=["empresa", "data_registro", "estado", "cidade"],
                name="regsintoma_mapa_mun_idx",
            ),
        ),
    ]
