from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0054_farmacia_fase1"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransferenciaFarmaciaMed",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rede", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transferencias_farmacia", to="api.rede")),
                ("empresa_solicitante", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transf_farm_solicitadas", to="api.empresa")),
                ("empresa_fornecedora", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transf_farm_fornecidas", to="api.empresa")),
                ("medicamento", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transferencias_rede", to="api.medicamentofarmacia")),
                ("lote", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transferencias_rede", to="api.lotemedicamento")),
                ("quantidade_solicitada", models.DecimalField(decimal_places=3, max_digits=12)),
                ("quantidade_aprovada", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True)),
                ("status", models.CharField(choices=[("pendente", "Pendente"), ("aprovada", "Aprovada"), ("enviada", "Enviada"), ("recebida", "Recebida"), ("cancelada", "Cancelada"), ("rejeitada", "Rejeitada")], default="pendente", max_length=20)),
                ("urgente", models.BooleanField(default=False)),
                ("motivo", models.TextField(blank=True, default="")),
                ("observacoes", models.TextField(blank=True, default="")),
                ("solicitado_por", models.CharField(blank=True, default="", max_length=150)),
                ("aprovado_por", models.CharField(blank=True, default="", max_length=150)),
                ("solicitado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-solicitado_em"],
                "indexes": [
                    models.Index(fields=["rede", "status"], name="transf_farm_rede_status_idx"),
                    models.Index(fields=["empresa_solicitante", "status"], name="transf_farm_sol_status_idx"),
                ],
            },
        ),
    ]
