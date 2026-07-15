from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0138_reuniao_governo'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='diagnosticoconfirmadogov',
            new_name='api_diagnos_empresa_0593ce_idx',
            old_name='api_diagcon_emp_cid_idx',
        ),
        migrations.RenameIndex(
            model_name='diagnosticoconfirmadogov',
            new_name='api_diagnos_empresa_74524b_idx',
            old_name='api_diagcon_emp_data_idx',
        ),
        migrations.RenameIndex(
            model_name='diagnosticoconfirmadogov',
            new_name='api_diagnos_empresa_fe0e31_idx',
            old_name='api_diagcon_emp_geo_idx',
        ),
        migrations.RenameIndex(
            model_name='reuniaogoverno',
            new_name='api_reuniao_empresa_8cb37a_idx',
            old_name='api_reugov_emp_status_idx',
        ),
    ]
