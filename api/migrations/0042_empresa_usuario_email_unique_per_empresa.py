from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0041_gtm_featurestore_financial_compliance_rbac"),
    ]

    operations = [
        migrations.AlterField(
            model_name="empresausuario",
            name="email",
            field=models.EmailField(max_length=254),
        ),
        migrations.AlterUniqueTogether(
            name="empresausuario",
            unique_together={("empresa", "email")},
        ),
    ]
