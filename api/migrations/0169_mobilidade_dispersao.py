# Mobilidade aérea agregada (OpenSky) + projeção de dispersão epidemiológica.
#
# Duas tabelas novas, puramente aditivas. Nenhuma FK para Empresa, de propósito:
# são dado público AGREGADO (fluxo de voos entre municípios e projeção sobre
# território), no mesmo padrão de api_fonteoficialagregado. Por isso ficam
# FORA da RLS (0085_rls_policies.py cobre só tabelas com FK direta a Empresa)
# — não há dado de indivíduo para isolar.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0168_performance_indexes_guia_sinistro_paciente'),
    ]

    operations = [
        migrations.CreateModel(
            name='MatrizMobilidade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('origem_ibge', models.CharField(max_length=20)),
                ('destino_ibge', models.CharField(max_length=20)),
                ('origem_nome', models.CharField(blank=True, default='', max_length=120)),
                ('destino_nome', models.CharField(blank=True, default='', max_length=120)),
                ('origem_uf', models.CharField(blank=True, default='', max_length=2)),
                ('destino_uf', models.CharField(blank=True, default='', max_length=2)),
                ('modo', models.CharField(choices=[('aereo', 'Aéreo'), ('rodoviario', 'Rodoviário')], default='aereo', max_length=20)),
                ('periodo', models.CharField(max_length=20)),
                ('viagens', models.PositiveIntegerField(default=0)),
                ('peso', models.FloatField(default=0.0)),
                ('fonte', models.CharField(default='opensky', max_length=80)),
                ('metadados', models.JSONField(blank=True, default=dict)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='ProjecaoDispersao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('doenca', models.CharField(max_length=120)),
                ('municipio_ibge', models.CharField(max_length=20)),
                ('municipio_nome', models.CharField(blank=True, default='', max_length=120)),
                ('uf', models.CharField(blank=True, default='', max_length=2)),
                ('horizonte_dias', models.PositiveSmallIntegerField()),
                ('probabilidade', models.FloatField(default=0.0)),
                ('casos_projetados', models.FloatField(default=0.0)),
                ('origem_provavel_ibge', models.CharField(blank=True, default='', max_length=20)),
                ('origem_provavel_nome', models.CharField(blank=True, default='', max_length=120)),
                ('calculado_em', models.DateTimeField(auto_now=True)),
                ('metadados', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'ordering': ['-probabilidade'],
            },
        ),
        migrations.AddIndex(
            model_name='matrizmobilidade',
            index=models.Index(fields=['origem_ibge', 'modo', 'periodo'], name='api_matmob_orig_modo_per_idx'),
        ),
        migrations.AddIndex(
            model_name='matrizmobilidade',
            index=models.Index(fields=['destino_ibge', 'modo', 'periodo'], name='api_matmob_dest_modo_per_idx'),
        ),
        migrations.AddIndex(
            model_name='matrizmobilidade',
            index=models.Index(fields=['periodo'], name='api_matmob_periodo_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='matrizmobilidade',
            unique_together={('origem_ibge', 'destino_ibge', 'modo', 'periodo')},
        ),
        migrations.AddIndex(
            model_name='projecaodispersao',
            index=models.Index(fields=['doenca', 'horizonte_dias', '-probabilidade'], name='api_projdisp_doe_hor_prob_idx'),
        ),
        migrations.AddIndex(
            model_name='projecaodispersao',
            index=models.Index(fields=['municipio_ibge', 'doenca'], name='api_projdisp_mun_doenca_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='projecaodispersao',
            unique_together={('doenca', 'municipio_ibge', 'horizonte_dias')},
        ),
    ]
