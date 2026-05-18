from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0053_assinatura_sst_auditavel"),
    ]

    operations = [
        # ── LoteMedicamento: campos de bloqueio (recall) ──────────────────────
        migrations.AddField(
            model_name="lotemedicamento",
            name="bloqueado",
            field=models.BooleanField(default=False, help_text="Lote bloqueado para dispensação (recall, suspeita de desvio)"),
        ),
        migrations.AddField(
            model_name="lotemedicamento",
            name="motivo_bloqueio",
            field=models.TextField(blank=True, default=""),
        ),

        # ── MedicamentoFarmacia: Portaria 344 ─────────────────────────────────
        migrations.AddField(
            model_name="medicamentofarmacia",
            name="lista_portaria_344",
            field=models.CharField(
                blank=True,
                choices=[
                    ("",   "Não controlado"),
                    ("A1", "Lista A1 — Entorpecentes"),
                    ("A2", "Lista A2 — Entorpecentes especiais"),
                    ("A3", "Lista A3 — Psicotrópicos"),
                    ("B1", "Lista B1 — Psicotrópicos"),
                    ("B2", "Lista B2 — Psicotrópicos anorexígenos"),
                    ("C1", "Lista C1 — Outras substâncias sujeitas a controle"),
                    ("C2", "Lista C2 — Retinoides"),
                    ("C3", "Lista C3 — Imunossupressores"),
                    ("C4", "Lista C4 — Antirretrovirais"),
                    ("C5", "Lista C5 — Anabolizantes"),
                    ("D1", "Lista D1 — Precursoras"),
                ],
                default="",
                max_length=4,
                help_text="Lista ANVISA Portaria 344",
            ),
        ),
        migrations.AddField(
            model_name="medicamentofarmacia",
            name="requer_notificacao_anvisa",
            field=models.BooleanField(default=False, help_text="Notificação ANVISA obrigatória na dispensação"),
        ),

        # ── LivroRegistroControlado ───────────────────────────────────────────
        migrations.CreateModel(
            name="LivroRegistroControlado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="livro_registro_controlados", to="api.empresa")),
                ("medicamento", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registros_controlados", to="api.medicamentofarmacia")),
                ("lote", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registros_controlados", to="api.lotemedicamento")),
                ("dispensacao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registros_controlados", to="api.dispensacao")),
                ("tipo", models.CharField(choices=[("dispensacao", "Dispensação"), ("entrada", "Entrada em Estoque"), ("descarte", "Descarte / Inutilização"), ("transferencia", "Transferência")], max_length=20)),
                ("data_operacao", models.DateTimeField(auto_now_add=True)),
                ("quantidade", models.DecimalField(decimal_places=3, max_digits=12)),
                ("saldo_apos", models.DecimalField(decimal_places=3, max_digits=12)),
                ("paciente_nome", models.CharField(blank=True, default="", max_length=200)),
                ("paciente_cpf", models.CharField(blank=True, default="", max_length=14)),
                ("prescricao_numero", models.CharField(blank=True, default="", max_length=50)),
                ("medico_crm", models.CharField(blank=True, default="", max_length=30)),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("observacao", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-data_operacao"],
                "indexes": [
                    models.Index(fields=["empresa", "medicamento"], name="livro_ctrl_emp_med_idx"),
                    models.Index(fields=["empresa", "data_operacao"], name="livro_ctrl_emp_dt_idx"),
                ],
            },
        ),

        # ── FarmaciaAuditLog ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="FarmaciaAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="farmacia_audit_logs", to="api.empresa")),
                ("acao", models.CharField(choices=[("criar", "Criar"), ("editar", "Editar"), ("excluir", "Excluir"), ("dispensar", "Dispensar"), ("bloquear_lote", "Bloquear Lote"), ("desbloquear_lote", "Desbloquear Lote"), ("ajuste_estoque", "Ajuste de Estoque"), ("descarte", "Descarte"), ("notificacao_anvisa", "Notificação ANVISA")], max_length=30)),
                ("modelo", models.CharField(max_length=100)),
                ("objeto_id", models.PositiveIntegerField(blank=True, null=True)),
                ("descricao", models.TextField()),
                ("dados_antes", models.JSONField(blank=True, null=True)),
                ("dados_depois", models.JSONField(blank=True, null=True)),
                ("usuario", models.CharField(blank=True, default="", max_length=200)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-criado_em"],
                "indexes": [
                    models.Index(fields=["empresa", "acao"], name="farm_audit_emp_acao_idx"),
                    models.Index(fields=["empresa", "criado_em"], name="farm_audit_emp_dt_idx"),
                ],
            },
        ),
    ]
