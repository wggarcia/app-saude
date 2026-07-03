from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0130_add_surto_epidemiologico_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="email_verificado",
            field=models.BooleanField(default=False),
        ),
    ]
