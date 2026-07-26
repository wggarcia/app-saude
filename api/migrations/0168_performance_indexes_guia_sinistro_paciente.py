from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0167_diops_sib_protocolo_ans'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='guiaautorizacao',
            index=models.Index(fields=['plano', 'status'], name='api_guiaaut_plano_status_idx'),
        ),
        migrations.AddIndex(
            model_name='guiaautorizacao',
            index=models.Index(fields=['plano', 'fila_status'], name='api_guiaaut_plano_filastat_idx'),
        ),
        migrations.AddIndex(
            model_name='guiaautorizacao',
            index=models.Index(fields=['plano', 'prazo_sla_em'], name='api_guiaaut_plano_slaprazo_idx'),
        ),
        migrations.AddIndex(
            model_name='sinistro',
            index=models.Index(fields=['empresa', 'status'], name='api_sinist_empresa_status_idx'),
        ),
        migrations.AddIndex(
            model_name='sinistro',
            index=models.Index(fields=['empresa', 'data_abertura'], name='api_sinist_empresa_abert_idx'),
        ),
        migrations.AddIndex(
            model_name='pacienteinternado',
            index=models.Index(fields=['empresa', 'status'], name='api_pacint_empresa_status_idx'),
        ),
        migrations.AddIndex(
            model_name='pacienteinternado',
            index=models.Index(fields=['empresa', 'data_internacao'], name='api_pacint_empresa_intern_idx'),
        ),
    ]
