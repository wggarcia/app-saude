from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0135_alter_cpf_encryptedfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='teleconsultagoverno',
            name='sala_jitsi',
            field=models.CharField(blank=True, max_length=80, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='teleconsultagoverno',
            name='token_paciente',
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='teleconsultagoverno',
            name='encerrado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='teleconsultagoverno',
            name='cid10',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        migrations.AddField(
            model_name='teleconsultagoverno',
            name='tcle_aceito_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
