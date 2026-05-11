"""
Migration 0043 — Farmácia: MedicamentoFarmacia, EstoqueMovimento, Dispensacao,
FornecedorFarmaciaGestao, PedidoFarmacia.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0042_empresa_usuario_email_unique_per_empresa"),
    ]

    operations = [
        # ── MedicamentoFarmacia ──────────────────────────────────────────────
        migrations.CreateModel(
            name="MedicamentoFarmacia",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="medicamentos_farmacia",
                        to="api.empresa",
                    ),
                ),
                ("nome", models.CharField(max_length=200)),
                ("principio_ativo", models.CharField(blank=True, default="", max_length=200)),
                (
                    "forma_farmaceutica",
                    models.CharField(
                        choices=[
                            ("comprimido", "Comprimido"),
                            ("capsula", "Cápsula"),
                            ("solucao", "Solução"),
                            ("suspensao", "Suspensão"),
                            ("injetavel", "Injetável"),
                            ("creme", "Creme"),
                            ("pomada", "Pomada"),
                            ("gel", "Gel"),
                            ("gotas", "Gotas"),
                            ("inalador", "Inalador"),
                            ("supositorio", "Supositório"),
                            ("outro", "Outro"),
                        ],
                        default="comprimido",
                        max_length=20,
                    ),
                ),
                ("concentracao", models.CharField(blank=True, default="", max_length=100)),
                ("registro_anvisa", models.CharField(blank=True, default="", max_length=50)),
                ("codigo_barras", models.CharField(blank=True, default="", max_length=50)),
                ("fabricante", models.CharField(blank=True, default="", max_length=200)),
                (
                    "classe_terapeutica",
                    models.CharField(
                        choices=[
                            ("analgesico", "Analgésico"),
                            ("antibiotico", "Antibiótico"),
                            ("anti_inflamatorio", "Anti-inflamatório"),
                            ("antihipertensivo", "Anti-hipertensivo"),
                            ("antidiabetes", "Antidiabetes"),
                            ("cardiovascular", "Cardiovascular"),
                            ("neurologico", "Neurológico"),
                            ("psiquiatrico", "Psiquiátrico"),
                            ("oncologico", "Oncológico"),
                            ("vitamina", "Vitamina / Suplemento"),
                            ("outro", "Outro"),
                        ],
                        default="outro",
                        max_length=30,
                    ),
                ),
                ("quantidade_atual", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("quantidade_minima", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("quantidade_maxima", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("preco_custo", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("preco_venda", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("controlado", models.BooleanField(default=False)),
                ("refrigerado", models.BooleanField(default=False)),
                ("validade_media_dias", models.PositiveIntegerField(default=365)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["nome"],
            },
        ),
        migrations.AddIndex(
            model_name="medicamentofarmacia",
            index=models.Index(fields=["empresa", "ativo"], name="med_farm_emp_ativo_idx"),
        ),

        # ── EstoqueMovimento ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="EstoqueMovimento",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="estoque_movimentos",
                        to="api.empresa",
                    ),
                ),
                (
                    "medicamento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="movimentos_estoque",
                        to="api.medicamentofarmacia",
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("entrada", "Entrada"),
                            ("saida", "Saída"),
                            ("ajuste", "Ajuste"),
                            ("descarte", "Descarte"),
                            ("transferencia", "Transferência"),
                        ],
                        max_length=20,
                    ),
                ),
                ("quantidade", models.DecimalField(decimal_places=3, max_digits=12)),
                ("motivo", models.TextField(blank=True, default="")),
                ("lote", models.CharField(blank=True, default="", max_length=100)),
                ("data_validade", models.DateField(blank=True, null=True)),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("observacao", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-criado_em"],
            },
        ),
        migrations.AddIndex(
            model_name="estoquemovimento",
            index=models.Index(fields=["empresa", "medicamento"], name="estmov_emp_med_idx"),
        ),

        # ── Dispensacao ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Dispensacao",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dispensacoes_farmacia",
                        to="api.empresa",
                    ),
                ),
                ("data", models.DateTimeField(auto_now_add=True)),
                ("paciente_nome", models.CharField(max_length=200)),
                ("paciente_cpf", models.CharField(blank=True, default="", max_length=14)),
                ("prescricao_numero", models.CharField(blank=True, default="", max_length=50)),
                ("medico_crm", models.CharField(blank=True, default="", max_length=30)),
                ("medicamentos", models.JSONField(default=list)),
                ("valor_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("convenio", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pendente", "Pendente"),
                            ("dispensada", "Dispensada"),
                            ("devolvida", "Devolvida"),
                            ("parcial", "Parcialmente Dispensada"),
                        ],
                        default="pendente",
                        max_length=20,
                    ),
                ),
                ("observacoes", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-criado_em"],
            },
        ),
        migrations.AddIndex(
            model_name="dispensacao",
            index=models.Index(fields=["empresa", "status"], name="disp_farm_emp_status_idx"),
        ),

        # ── FornecedorFarmaciaGestao ─────────────────────────────────────────
        migrations.CreateModel(
            name="FornecedorFarmaciaGestao",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fornecedores_farmacia_gestao",
                        to="api.empresa",
                    ),
                ),
                ("nome", models.CharField(max_length=200)),
                ("cnpj", models.CharField(blank=True, default="", max_length=18)),
                ("contato", models.CharField(blank=True, default="", max_length=200)),
                ("email", models.EmailField(blank=True, default="")),
                ("telefone", models.CharField(blank=True, default="", max_length=20)),
                ("prazo_entrega_dias", models.PositiveSmallIntegerField(default=7)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["nome"],
            },
        ),

        # ── PedidoFarmacia ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="PedidoFarmacia",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pedidos_farmacia_gestao",
                        to="api.empresa",
                    ),
                ),
                (
                    "fornecedor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pedidos_farmacia",
                        to="api.fornecedorfarmaciagestao",
                    ),
                ),
                ("data_pedido", models.DateField(auto_now_add=True)),
                ("data_entrega_prevista", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("rascunho", "Rascunho"),
                            ("enviado", "Enviado"),
                            ("confirmado", "Confirmado"),
                            ("recebido", "Recebido"),
                            ("cancelado", "Cancelado"),
                        ],
                        default="rascunho",
                        max_length=20,
                    ),
                ),
                ("itens", models.JSONField(default=list)),
                ("valor_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("observacao", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-criado_em"],
            },
        ),
    ]
