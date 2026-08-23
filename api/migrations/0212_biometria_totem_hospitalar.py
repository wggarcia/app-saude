from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0211_agendamentopaciente_mensagempacienteportal'),
    ]

    operations = [
        migrations.CreateModel(
            name='BiometriaTotemPaciente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identidade', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='biometria_totem', to='api.identidadepaciente')),
                ('embedding_json', models.JSONField(help_text='Vetor ArcFace 512D normalizado')),
                ('assinatura_base64', models.TextField(blank=True, default='', help_text='Assinatura digital PNG em base64')),
                ('consentimento_lgpd', models.BooleanField(default=False)),
                ('consentimento_em', models.DateTimeField(blank=True, null=True)),
                ('ativo', models.BooleanField(default=True)),
                ('coletado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Biometria Totem Paciente', 'verbose_name_plural': 'Biometrias Totem Paciente'},
        ),
        migrations.CreateModel(
            name='TotemCheckinLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='totem_checkins', to='api.empresa')),
                ('identidade', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='checkins_totem', to='api.identidadepaciente')),
                ('id_temporario', models.CharField(blank=True, default='', max_length=30)),
                ('score_similaridade', models.FloatField(default=0.0)),
                ('tipo_entrada', models.CharField(choices=[('eletivo', 'Eletivo — consulta agendada'), ('emergencia', 'Emergência — PS'), ('novo_cadastro', 'Novo cadastro'), ('nao_reconhecido', 'Não reconhecido')], default='eletivo', max_length=20)),
                ('guia_gerada', models.BooleanField(default=False)),
                ('guia_numero', models.CharField(blank=True, default='', max_length=50)),
                ('plano_elegivel', models.BooleanField(blank=True, null=True)),
                ('checkin_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name': 'Log de Check-in no Totem', 'verbose_name_plural': 'Logs de Check-in no Totem', 'ordering': ['-checkin_em'], 'indexes': [models.Index(fields=['empresa', 'checkin_em'], name='api_totem_checkin_emp_idx')]},
        ),
        migrations.CreateModel(
            name='TriagemManchesterPS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='triagens_manchester_ps', to='api.empresa')),
                ('checkin', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='triagem', to='api.totemcheckinlog')),
                ('identidade', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='triagens', to='api.identidadepaciente')),
                ('id_temporario', models.CharField(blank=True, default='', max_length=30)),
                ('nome_paciente', models.CharField(max_length=200)),
                ('queixa_principal', models.TextField()),
                ('dor_intensa', models.BooleanField(default=False)),
                ('alteracao_consciencia', models.BooleanField(default=False)),
                ('dificuldade_respirar', models.BooleanField(default=False)),
                ('sangramento_ativo', models.BooleanField(default=False)),
                ('febre_alta', models.BooleanField(default=False)),
                ('convulsao', models.BooleanField(default=False)),
                ('dor_toracica', models.BooleanField(default=False)),
                ('trauma', models.BooleanField(default=False)),
                ('gestante', models.BooleanField(default=False)),
                ('crianca_menor_2', models.BooleanField(default=False)),
                ('pa_sistolica', models.IntegerField(blank=True, null=True)),
                ('pa_diastolica', models.IntegerField(blank=True, null=True)),
                ('freq_cardiaca', models.IntegerField(blank=True, null=True)),
                ('freq_respiratoria', models.IntegerField(blank=True, null=True)),
                ('saturacao_o2', models.IntegerField(blank=True, null=True)),
                ('temperatura', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('cor_classificacao', models.CharField(choices=[('vermelho', '🔴 Vermelho — Emergência imediata'), ('laranja', '🟠 Laranja — Muito urgente (≤ 10 min)'), ('amarelo', '🟡 Amarelo — Urgente (≤ 30 min)'), ('verde', '🟢 Verde — Pouco urgente (≤ 120 min)'), ('azul', '🔵 Azul — Não urgente')], max_length=10)),
                ('justificativa_ia', models.TextField(blank=True, default='')),
                ('enfermeiro', models.CharField(blank=True, default='', max_length=150)),
                ('triado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name': 'Triagem de Manchester (PS)', 'verbose_name_plural': 'Triagens de Manchester (PS)', 'ordering': ['-triado_em'], 'indexes': [models.Index(fields=['empresa', 'cor_classificacao'], name='api_triagem_manchester_cor_idx'), models.Index(fields=['empresa', 'triado_em'], name='api_triagem_manchester_dt_idx')]},
        ),
    ]
