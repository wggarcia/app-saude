from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0044_hospital_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaosst",
            name="certificado_pfx_b64",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="configuracaosst",
            name="certificado_senha",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="configuracaosst",
            name="certificado_validade",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="configuracaosst",
            name="certificado_nome",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="configuracaosst",
            name="esocial_ambiente",
            field=models.CharField(
                choices=[("homologacao", "Homologação"), ("producao", "Produção")],
                default="homologacao",
                max_length=20,
            ),
        ),
    ]
