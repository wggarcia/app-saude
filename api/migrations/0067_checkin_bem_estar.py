from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0066_credencial_app_fcm_token'),
    ]

    operations = [
        migrations.CreateModel(
            name='CheckinBemEstar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('humor', models.CharField(choices=[('otimo', 'Ótimo 😄'), ('bom', 'Bom 🙂'), ('regular', 'Regular 😐'), ('ruim', 'Ruim 😔'), ('pessimo', 'Péssimo 😞')], max_length=10)),
                ('saude_fisica', models.PositiveSmallIntegerField(default=3)),
                ('saude_mental', models.PositiveSmallIntegerField(default=3)),
                ('nivel_estresse', models.PositiveSmallIntegerField(default=3)),
                ('satisfacao_trabalho', models.PositiveSmallIntegerField(default=3)),
                ('mensagem', models.TextField(blank=True)),
                ('precisa_ajuda', models.BooleanField(default=False)),
                ('tipo_ajuda', models.CharField(blank=True, choices=[('saude_fisica', 'Saúde física'), ('saude_mental', 'Saúde mental / ansiedade'), ('vicio', 'Dependência / vício'), ('trabalho', 'Problemas no trabalho'), ('financeiro', 'Dificuldade financeira'), ('familiar', 'Problema familiar'), ('outro', 'Outro')], max_length=20)),
                ('quer_contato', models.BooleanField(default=False)),
                ('contato_resolvido', models.BooleanField(default=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checkins_bem_estar', to='api.empresa')),
                ('funcionario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checkins_bem_estar', to='api.funcionariosst')),
            ],
            options={
                'ordering': ['-criado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='checkinbemestar',
            index=models.Index(fields=['empresa', 'criado_em'], name='api_checkin_empresa_criado_idx'),
        ),
    ]
