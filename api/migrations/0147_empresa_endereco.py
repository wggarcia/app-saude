import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0146_novos_modulos_licitacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='empresa',
            name='logradouro',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='empresa',
            name='numero',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='empresa',
            name='bairro',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='empresa',
            name='cep',
            field=models.CharField(blank=True, default='', max_length=9),
        ),
        migrations.AddField(
            model_name='empresa',
            name='cidade',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='empresa',
            name='uf',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
    ]
