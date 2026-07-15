from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0136_teleconsulta_sala_jitsi'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiagnosticoConfirmadoGov',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cid10', models.CharField(max_length=10)),
                ('estado', models.CharField(blank=True, default='', max_length=100)),
                ('cidade', models.CharField(blank=True, default='', max_length=100)),
                ('data_registro', models.DateField()),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='diagnosticos_confirmados_gov',
                    to='api.empresa',
                )),
            ],
            options={},
        ),
        migrations.AddIndex(
            model_name='diagnosticoconfirmadogov',
            index=models.Index(fields=['empresa', 'cid10'], name='api_diagcon_emp_cid_idx'),
        ),
        migrations.AddIndex(
            model_name='diagnosticoconfirmadogov',
            index=models.Index(fields=['empresa', 'data_registro'], name='api_diagcon_emp_data_idx'),
        ),
        migrations.AddIndex(
            model_name='diagnosticoconfirmadogov',
            index=models.Index(fields=['empresa', 'estado', 'cidade'], name='api_diagcon_emp_geo_idx'),
        ),
    ]
