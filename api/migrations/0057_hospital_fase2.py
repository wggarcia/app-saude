from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0056_hospital_fase1"),
    ]

    operations = [
        # ── PedidoExame ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="PedidoExame",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pedidos_exame_hosp", to="api.empresa")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pedidos_exame", to="api.pacienteinternado")),
                ("prescricao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pedidos_exame", to="api.prescricaohospitalar")),
                ("tipo", models.CharField(choices=[("laboratorial","Laboratorial"),("imagem","Imagem (Rx/TC/RM/US)"),("ecg","ECG / Eletrocardiograma"),("endoscopia","Endoscopia"),("outro","Outro")], max_length=20)),
                ("exames", models.JSONField(default=list)),
                ("prioridade", models.CharField(choices=[("rotina","Rotina"),("urgente","Urgente"),("emergencia","Emergência")], default="rotina", max_length=20)),
                ("status", models.CharField(choices=[("solicitado","Solicitado"),("coletado","Coletado / Em análise"),("concluido","Concluído"),("cancelado","Cancelado")], default="solicitado", max_length=20)),
                ("solicitante", models.CharField(blank=True, default="", max_length=200)),
                ("solicitante_crm", models.CharField(blank=True, default="", max_length=30)),
                ("observacoes_clinicas", models.TextField(blank=True, default="")),
                ("jejum_horas", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("material", models.CharField(blank=True, default="", max_length=100)),
                ("data_solicitacao", models.DateTimeField(auto_now_add=True)),
                ("data_coleta", models.DateTimeField(blank=True, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-data_solicitacao"],
                "indexes": [
                    models.Index(fields=["empresa", "status"], name="pedexame_emp_status_idx"),
                    models.Index(fields=["paciente", "status"], name="pedexame_pac_status_idx"),
                ],
            },
        ),

        # ── ResultadoExame ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="ResultadoExame",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pedido", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resultados", to="api.pedidoexame")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resultados_exame", to="api.pacienteinternado")),
                ("data_resultado", models.DateTimeField(auto_now_add=True)),
                ("resultados_json", models.JSONField(default=list)),
                ("laudo", models.TextField(blank=True, default="")),
                ("interpretacao", models.CharField(choices=[("normal","Normal / Dentro do esperado"),("alterado","Alterado"),("critico","Crítico — requer ação imediata"),("pendente","Pendente de laudo")], default="pendente", max_length=20)),
                ("responsavel_laudo", models.CharField(blank=True, default="", max_length=200)),
                ("crm_responsavel", models.CharField(blank=True, default="", max_length=30)),
                ("url_imagem", models.URLField(blank=True, default="")),
                ("visualizado_por", models.CharField(blank=True, default="", max_length=200)),
                ("visualizado_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-data_resultado"]},
        ),

        # ── AdministracaoMedicamento ──────────────────────────────────────────
        migrations.CreateModel(
            name="AdministracaoMedicamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prescricao", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="administracoes", to="api.prescricaohospitalar")),
                ("paciente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="administracoes", to="api.pacienteinternado")),
                ("nome_medicamento", models.CharField(max_length=200)),
                ("dose", models.CharField(blank=True, default="", max_length=100)),
                ("via", models.CharField(blank=True, default="", max_length=50)),
                ("horario_prescrito", models.TimeField()),
                ("horario_administrado", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("administrado","Administrado"),("recusado","Recusado pelo paciente"),("omitido","Omitido"),("suspenso","Suspenso")], default="administrado", max_length=20)),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("coren", models.CharField(blank=True, default="", max_length=30)),
                ("observacao", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-criado_em"],
                "indexes": [models.Index(fields=["prescricao", "status"], name="adminmed_presc_status_idx")],
            },
        ),
    ]
