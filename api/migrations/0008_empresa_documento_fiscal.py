from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_registrosintoma_confianca_registrosintoma_ip_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="documento_fiscal",
            field=models.CharField(blank=True, default="", max_length=14),
        ),
    ]
