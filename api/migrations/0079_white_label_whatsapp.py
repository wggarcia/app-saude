from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0078_add_cipa_biometria_psicossocial"),
    ]

    operations = [
        # ── ConfiguracaoMarca (white label) ─────────────────────────────────
        migrations.CreateModel(
            name="ConfiguracaoMarca",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configuracao_marca",
                        to="api.empresa",
                    ),
                ),
                ("logo_url", models.URLField(blank=True, default="")),
                ("cor_primaria", models.CharField(default="#00c9a7", max_length=7)),
                ("cor_secundaria", models.CharField(default="#1f6ff2", max_length=7)),
                ("nome_marca", models.CharField(blank=True, default="", max_length=80)),
                ("mostrar_powered_by", models.BooleanField(default=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuração de Marca",
                "verbose_name_plural": "Configurações de Marca",
            },
        ),
        # ── IntegracaoWhatsApp ───────────────────────────────────────────────
        migrations.CreateModel(
            name="IntegracaoWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="integracao_whatsapp",
                        to="api.empresa",
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        choices=[("z-api", "Z-API"), ("evolution", "Evolution API")],
                        default="z-api",
                        max_length=20,
                    ),
                ),
                ("instance_id", models.CharField(blank=True, default="", max_length=120)),
                ("token", models.CharField(blank=True, default="", max_length=255)),
                ("numero_remetente", models.CharField(blank=True, default="", max_length=20)),
                ("ativo", models.BooleanField(default=False)),
                ("notif_aso", models.BooleanField(default=True)),
                ("notif_treinamento", models.BooleanField(default=True)),
                ("notif_epi", models.BooleanField(default=True)),
                ("notif_cat", models.BooleanField(default=True)),
                ("notif_psicossocial", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Integração WhatsApp",
                "verbose_name_plural": "Integrações WhatsApp",
            },
        ),
        # ── LogWhatsApp ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="LogWhatsApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs_whatsapp",
                        to="api.empresa",
                    ),
                ),
                ("numero_destino", models.CharField(max_length=20)),
                ("mensagem", models.TextField()),
                ("evento", models.CharField(default="manual", max_length=60)),
                (
                    "status",
                    models.CharField(
                        choices=[("ok", "Enviado"), ("erro", "Erro")],
                        default="ok",
                        max_length=10,
                    ),
                ),
                ("resposta_api", models.JSONField(blank=True, default=dict)),
                ("enviado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Log WhatsApp",
                "verbose_name_plural": "Logs WhatsApp",
                "ordering": ["-enviado_em"],
            },
        ),
    ]
