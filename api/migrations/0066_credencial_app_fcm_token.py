from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0065_reuniao_sst'),
    ]

    operations = [
        migrations.AddField(
            model_name='credencialappfuncionario',
            name='fcm_token',
            field=models.TextField(blank=True, default=''),
        ),
    ]
