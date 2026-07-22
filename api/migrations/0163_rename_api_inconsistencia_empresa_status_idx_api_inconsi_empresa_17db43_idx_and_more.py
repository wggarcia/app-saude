from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0162_hospital_linhagens_fk'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='inconsistenciacadastral',
            new_name='api_inconsi_empresa_17db43_idx',
            old_name='api_inconsistencia_empresa_status_idx',
        ),
        migrations.RenameIndex(
            model_name='inconsistenciacadastral',
            new_name='api_inconsi_empresa_d93fc2_idx',
            old_name='api_inconsistencia_empresa_sev_status_idx',
        ),
        migrations.RenameIndex(
            model_name='prontuariosocialpaif',
            new_name='api_prontua_empresa_6e11f6_idx',
            old_name='api_prontuariopaif_empresa_ativo_idx',
        ),
        migrations.RenameIndex(
            model_name='prontuariosocialpaif',
            new_name='api_prontua_empresa_717716_idx',
            old_name='api_prontuariopaif_empresa_dt_idx',
        ),
    ]
