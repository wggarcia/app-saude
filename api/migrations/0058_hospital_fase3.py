from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0057_hospital_fase2"),
    ]

    operations = [
        # ── FaturaHospitalar ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="FaturaHospitalar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="faturas_hosp", to="api.empresa")),
                ("paciente", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="fatura", to="api.pacienteinternado")),
                ("numero_guia", models.CharField(blank=True, default="", max_length=50)),
                ("convenio", models.CharField(choices=[("sus","SUS"),("convenio","Convênio / Plano de Saúde"),("particular","Particular")], default="particular", max_length=20)),
                ("nome_convenio", models.CharField(blank=True, default="", max_length=200)),
                ("numero_carteirinha", models.CharField(blank=True, default="", max_length=50)),
                ("status", models.CharField(choices=[("rascunho","Rascunho"),("fechada","Fechada / Aguardando envio"),("enviada","Enviada ao Convênio"),("paga","Paga"),("glosada","Glosada (parcial ou total)"),("cancelada","Cancelada")], default="rascunho", max_length=20)),
                ("valor_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("valor_glosa", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("valor_pago", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("observacoes", models.TextField(blank=True, default="")),
                ("data_envio", models.DateTimeField(blank=True, null=True)),
                ("data_pagamento", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-criado_em"],
                "indexes": [
                    models.Index(fields=["empresa", "status"], name="fatura_hosp_emp_status_idx"),
                ],
            },
        ),

        # ── ItemFaturamento ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="ItemFaturamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens_faturamento_hosp", to="api.empresa")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens_faturamento", to="api.pacienteinternado")),
                ("fatura", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="itens", to="api.faturahospitalar")),
                ("tipo", models.CharField(choices=[("diaria","Diária / Acomodação"),("procedimento","Procedimento"),("exame","Exame / Diagnóstico"),("medicamento","Medicamento"),("material","Material / OPME"),("honorario","Honorário Médico"),("taxa","Taxa / Pacote"),("outro","Outro")], default="procedimento", max_length=20)),
                ("codigo_tuss", models.CharField(blank=True, default="", max_length=20)),
                ("codigo_cbhpm", models.CharField(blank=True, default="", max_length=20)),
                ("descricao", models.CharField(max_length=300)),
                ("quantidade", models.DecimalField(decimal_places=2, default=1, max_digits=8)),
                ("valor_unitario", models.DecimalField(decimal_places=2, max_digits=10)),
                ("valor_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("data_competencia", models.DateField(auto_now_add=True)),
                ("observacao", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-criado_em"],
                "indexes": [
                    models.Index(fields=["empresa", "paciente"], name="itemfat_emp_pac_idx"),
                ],
            },
        ),
    ]
