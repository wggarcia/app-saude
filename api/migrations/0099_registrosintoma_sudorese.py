from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0098_registrosintoma_anamnese'),
    ]

    operations = [
        migrations.AddField(
            model_name='registrosintoma',
            name='sudorese',
            field=models.BooleanField(default=False),
        ),
    ]
