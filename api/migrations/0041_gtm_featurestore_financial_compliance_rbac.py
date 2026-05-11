"""
Migration 0041 — GTM Machine, Feature Store, Financial OS, Compliance SOC2, RBAC.
Completa as 5 áreas enterprise ao nível 100%.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0040_outbox_schema_mlops"),
    ]

    operations = [

        # ── GTM Machine ──────────────────────────────────────────────────────

        migrations.CreateModel(
            name="LeadComercial",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("nome_empresa", models.CharField(max_length=200)),
                ("cnpj", models.CharField(blank=True, default="", max_length=18)),
                ("etapa", models.CharField(
                    choices=[
                        ("leads", "Lead Captado"),
                        ("qualificados", "Qualificado (MQL)"),
                        ("demo", "Demo Realizada"),
                        ("proposta", "Proposta Enviada"),
                        ("negociacao", "Em Negociação"),
                        ("fechado", "Fechado (Won)"),
                        ("perdido", "Perdido (Lost)"),
                    ],
                    db_index=True, default="leads", max_length=20,
                )),
                ("segmento", models.CharField(
                    choices=[
                        ("industria", "Indústria"),
                        ("saude", "Saúde"),
                        ("varejo", "Varejo"),
                        ("governo", "Governo"),
                        ("financeiro", "Financeiro"),
                        ("outros", "Outros"),
                    ],
                    default="outros", max_length=20,
                )),
                ("plano_interesse", models.CharField(blank=True, default="", max_length=50)),
                ("valor_estimado", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("owner", models.CharField(blank=True, default="", max_length=100)),
                ("fonte", models.CharField(blank=True, default="", max_length=100)),
                ("data_entrada", models.DateField(auto_now_add=True, db_index=True)),
                ("data_conversao", models.DateField(blank=True, null=True)),
                ("ciclo_dias", models.PositiveIntegerField(blank=True, null=True)),
                ("notas", models.TextField(blank=True, default="")),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-criado_em"]},
        ),
        migrations.AddIndex(
            model_name="leadcomercial",
            index=models.Index(fields=["etapa", "criado_em"], name="lead_etapa_idx"),
        ),

        migrations.CreateModel(
            name="ExpansaoContrato",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="expansoes", to="api.empresa",
                )),
                ("pacote_anterior", models.CharField(max_length=50)),
                ("pacote_novo", models.CharField(max_length=50)),
                ("mrr_anterior", models.DecimalField(decimal_places=2, max_digits=10)),
                ("mrr_novo", models.DecimalField(decimal_places=2, max_digits=10)),
                ("delta_mrr", models.DecimalField(decimal_places=2, max_digits=10)),
                ("motivo", models.CharField(blank=True, default="", max_length=200)),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-criado_em"]},
        ),

        # ── Feature Store Registry ───────────────────────────────────────────

        migrations.CreateModel(
            name="FeatureRegistro",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("entidade", models.CharField(
                    choices=[
                        ("colaborador", "Colaborador"),
                        ("empresa", "Empresa"),
                        ("unidade", "Unidade"),
                    ],
                    db_index=True, max_length=30,
                )),
                ("nome", models.CharField(max_length=100)),
                ("descricao", models.TextField()),
                ("tipo", models.CharField(
                    choices=[
                        ("float", "Float"),
                        ("int", "Integer"),
                        ("bool", "Boolean"),
                        ("str", "String"),
                        ("embedding", "Embedding"),
                    ],
                    default="float", max_length=20,
                )),
                ("fonte", models.CharField(max_length=100)),
                ("frequencia_atualizacao", models.CharField(
                    choices=[
                        ("realtime", "Real-time"),
                        ("diaria", "Diária"),
                        ("semanal", "Semanal"),
                        ("mensal", "Mensal"),
                    ],
                    default="diaria", max_length=20,
                )),
                ("sla_atraso_max_horas", models.PositiveIntegerField(default=25)),
                ("owner", models.CharField(max_length=100)),
                ("tags", models.JSONField(default=list)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["entidade", "nome"]},
        ),
        migrations.AlterUniqueTogether(
            name="featureregistro",
            unique_together={("entidade", "nome")},
        ),

        # ── Financial OS — Real Cost Models ─────────────────────────────────

        migrations.CreateModel(
            name="CentroCusto",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("nome", models.CharField(max_length=100)),
                ("tipo", models.CharField(
                    choices=[
                        ("headcount", "Headcount"),
                        ("infraestrutura", "Infraestrutura"),
                        ("marketing", "Marketing"),
                        ("vendas", "Vendas"),
                        ("outros", "Outros"),
                    ],
                    default="outros", max_length=30,
                )),
                ("responsavel", models.CharField(blank=True, default="", max_length=100)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["tipo", "nome"]},
        ),

        migrations.CreateModel(
            name="LancamentoDespesa",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("centro", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lancamentos", to="api.centrocusto",
                )),
                ("competencia", models.DateField(db_index=True)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=12)),
                ("descricao", models.CharField(blank=True, default="", max_length=200)),
                ("recorrente", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-competencia"]},
        ),
        migrations.AddIndex(
            model_name="lancamentodespesa",
            index=models.Index(fields=["competencia", "centro"], name="despesa_comp_idx"),
        ),

        migrations.CreateModel(
            name="CohortRetencao",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("cohort_mes", models.DateField(db_index=True)),
                ("empresas_adquiridas", models.PositiveIntegerField(default=0)),
                ("mrr_inicial", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("mes_referencia", models.DateField(db_index=True)),
                ("empresas_ativas", models.PositiveIntegerField(default=0)),
                ("mrr_retido", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("mrr_expandido", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("retencao_pct", models.FloatField(default=0.0)),
                ("nrr_pct", models.FloatField(default=0.0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-cohort_mes", "-mes_referencia"]},
        ),
        migrations.AlterUniqueTogether(
            name="cohortretencao",
            unique_together={("cohort_mes", "mes_referencia")},
        ),

        # ── Compliance — SOC2 ────────────────────────────────────────────────

        migrations.CreateModel(
            name="SOC2Controle",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="soc2_controles", to="api.empresa",
                )),
                ("codigo", models.CharField(max_length=20)),
                ("categoria", models.CharField(
                    choices=[
                        ("CC", "Common Criteria"),
                        ("A", "Availability"),
                        ("C", "Confidentiality"),
                        ("PI", "Processing Integrity"),
                        ("P", "Privacy"),
                    ],
                    db_index=True, max_length=5,
                )),
                ("titulo", models.CharField(max_length=200)),
                ("descricao", models.TextField()),
                ("status", models.CharField(
                    choices=[
                        ("nao_iniciado", "Não Iniciado"),
                        ("em_andamento", "Em Andamento"),
                        ("implementado", "Implementado"),
                        ("auditado", "Auditado"),
                    ],
                    db_index=True, default="nao_iniciado", max_length=20,
                )),
                ("responsavel", models.CharField(blank=True, default="", max_length=100)),
                ("data_prevista", models.DateField(blank=True, null=True)),
                ("data_implementacao", models.DateField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["categoria", "codigo"]},
        ),
        migrations.AlterUniqueTogether(
            name="soc2controle",
            unique_together={("empresa", "codigo")},
        ),

        migrations.CreateModel(
            name="EvidenciaControle",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("controle", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="evidencias", to="api.soc2controle",
                )),
                ("tipo", models.CharField(
                    choices=[
                        ("screenshot", "Screenshot"),
                        ("log", "Log de Sistema"),
                        ("documento", "Documento"),
                        ("politica", "Política"),
                        ("procedimento", "Procedimento"),
                        ("relatorio", "Relatório"),
                    ],
                    max_length=20,
                )),
                ("titulo", models.CharField(max_length=200)),
                ("descricao", models.TextField(blank=True, default="")),
                ("arquivo_url", models.URLField(blank=True, default="")),
                ("coletado_por", models.CharField(blank=True, default="", max_length=100)),
                ("data_coleta", models.DateField(auto_now_add=True)),
                ("valido_ate", models.DateField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-criado_em"]},
        ),

        migrations.CreateModel(
            name="TesteControle",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("controle", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="testes", to="api.soc2controle",
                )),
                ("testado_por", models.CharField(max_length=100)),
                ("data_teste", models.DateField(db_index=True)),
                ("resultado", models.CharField(
                    choices=[
                        ("aprovado", "Aprovado"),
                        ("reprovado", "Reprovado"),
                        ("excecao", "Exceção Documentada"),
                    ],
                    max_length=20,
                )),
                ("observacoes", models.TextField(blank=True, default="")),
                ("evidencias_ids", models.JSONField(default=list)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-data_teste"]},
        ),

        # ── RBAC ─────────────────────────────────────────────────────────────

        migrations.CreateModel(
            name="RBACPermissao",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("codigo", models.CharField(max_length=100, unique=True)),
                ("descricao", models.CharField(max_length=200)),
                ("modulo", models.CharField(db_index=True, max_length=50)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["modulo", "codigo"]},
        ),

        migrations.CreateModel(
            name="RBACAtribuicao",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="rbac_atribuicoes", to="api.empresa",
                )),
                ("usuario", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="rbac_atribuicoes", to="api.empresausuario",
                )),
                ("permissao", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="atribuicoes", to="api.rbacpermissao",
                )),
                ("concedido_por", models.CharField(blank=True, default="", max_length=100)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name="rbacatribuicao",
            unique_together={("empresa", "usuario", "permissao")},
        ),
        migrations.AddIndex(
            model_name="rbacatribuicao",
            index=models.Index(fields=["empresa", "usuario", "ativo"], name="rbac_emp_usr_idx"),
        ),
    ]
