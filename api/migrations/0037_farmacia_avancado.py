from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0036_contratos_series_epi"),
    ]

    operations = [
        migrations.CreateModel(
            name="PacienteFarmacia",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200)),
                ("cpf", models.CharField(blank=True, default="", max_length=14)),
                ("data_nascimento", models.DateField(blank=True, null=True)),
                ("sexo", models.CharField(blank=True, default="", max_length=1)),
                ("telefone", models.CharField(blank=True, default="", max_length=20)),
                ("email", models.EmailField(blank=True, default="")),
                ("endereco", models.CharField(blank=True, default="", max_length=300)),
                ("alergias", models.TextField(blank=True, default="")),
                ("condicoes_cronicas", models.TextField(blank=True, default="")),
                ("medicamentos_uso_continuo", models.TextField(blank=True, default="")),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pacientes_farmacia", to="api.empresa")),
            ],
            options={"ordering": ["nome"]},
        ),
        migrations.CreateModel(
            name="ReceitaMedica",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paciente_nome", models.CharField(blank=True, default="", max_length=200)),
                ("paciente_cpf", models.CharField(blank=True, default="", max_length=14)),
                ("tipo", models.CharField(choices=[("simples","Receita Simples"),("especial_branca","Receita Especial Branca (2 vias)"),("especial_amarela","Receita Especial Amarela (Psicotrópico)"),("alto_custo","Medicamento de Alto Custo")], default="simples", max_length=25)),
                ("numero_receita", models.CharField(blank=True, default="", max_length=50)),
                ("medico_nome", models.CharField(blank=True, default="", max_length=200)),
                ("medico_crm", models.CharField(blank=True, default="", max_length=30)),
                ("data_emissao", models.DateField()),
                ("data_validade", models.DateField(blank=True, null=True)),
                ("medicamento_descricao", models.TextField(blank=True, default="")),
                ("quantidade", models.PositiveIntegerField(default=1)),
                ("posologia", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("pendente","Pendente"),("dispensada","Dispensada"),("vencida","Vencida"),("cancelada","Cancelada")], default="pendente", max_length=20)),
                ("observacoes", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("dispensacao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="receitas", to="api.dispensacaomedicamento")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="receitas_farmacia", to="api.empresa")),
                ("item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="receitas", to="api.itemfarmacia")),
                ("paciente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="receitas", to="api.pacientefarmacia")),
            ],
            options={"ordering": ["-criado_em"]},
        ),
        migrations.CreateModel(
            name="InventarioFarmacia",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descricao", models.CharField(blank=True, default="", max_length=200)),
                ("status", models.CharField(choices=[("aberto","Em andamento"),("concluido","Concluído"),("cancelado","Cancelado")], default="aberto", max_length=15)),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("iniciado_em", models.DateTimeField(auto_now_add=True)),
                ("concluido_em", models.DateTimeField(blank=True, null=True)),
                ("observacoes", models.TextField(blank=True, default="")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventarios_farmacia", to="api.empresa")),
            ],
            options={"ordering": ["-iniciado_em"]},
        ),
        migrations.CreateModel(
            name="ItemInventario",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estoque_sistema", models.IntegerField()),
                ("estoque_contado", models.IntegerField(blank=True, null=True)),
                ("diferenca", models.IntegerField(blank=True, null=True)),
                ("ajustado", models.BooleanField(default=False)),
                ("observacao", models.CharField(blank=True, default="", max_length=300)),
                ("inventario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="api.inventariofarmacia")),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="api.itemfarmacia")),
            ],
            options={"ordering": ["item__nome"]},
        ),
        migrations.AlterUniqueTogether(
            name="iteminventario",
            unique_together={("inventario", "item")},
        ),
        migrations.CreateModel(
            name="DescarteItemFarmacia",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("motivo", models.CharField(choices=[("vencimento","Vencimento"),("avaria","Avaria / Dano físico"),("contaminacao","Contaminação"),("recolhimento","Recolhimento ANVISA"),("outro","Outro")], default="vencimento", max_length=20)),
                ("quantidade", models.PositiveIntegerField()),
                ("responsavel", models.CharField(blank=True, default="", max_length=200)),
                ("empresa_descarte", models.CharField(blank=True, default="", max_length=200)),
                ("numero_manifesto", models.CharField(blank=True, default="", max_length=100)),
                ("observacoes", models.TextField(blank=True, default="")),
                ("data_descarte", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="descartes_farmacia", to="api.empresa")),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="descartes", to="api.itemfarmacia")),
                ("lote", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="api.lotemedicamento")),
            ],
            options={"ordering": ["-data_descarte"]},
        ),
    ]
