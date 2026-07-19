from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0149_lotemedicamento_medicamento_fk'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contratogrupo',
            name='status',
            field=models.CharField(
                choices=[
                    ('ativo', 'Ativo'),
                    ('suspenso', 'Suspenso'),
                    ('encerrado', 'Encerrado'),
                    ('proposta_renovacao', 'Proposta de Renovação'),
                ],
                default='ativo',
                max_length=20,
            ),
        ),
    ]
