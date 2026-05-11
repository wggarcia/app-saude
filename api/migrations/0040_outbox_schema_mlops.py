from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0039_rede_network_plano_saude"),
    ]

    operations = [
        # OutboxEvento
        migrations.CreateModel(
            name="OutboxEvento",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="outbox_eventos", to="api.empresa")),
                ("tipo_evento", models.CharField(max_length=120)),
                ("agregado_tipo", models.CharField(blank=True, default="", max_length=80)),
                ("agregado_id", models.CharField(blank=True, default="", max_length=80)),
                ("payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("pendente","Pendente"),("processando","Processando"),("entregue","Entregue"),("falha","Falha"),("dlq","Dead Letter Queue")], db_index=True, default="pendente", max_length=20)),
                ("tentativas", models.PositiveSmallIntegerField(default=0)),
                ("max_tentativas", models.PositiveSmallIntegerField(default=3)),
                ("proxima_tentativa", models.DateTimeField(blank=True, null=True)),
                ("erro_ultimo", models.TextField(blank=True, default="")),
                ("processado_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["criado_em"]},
        ),
        migrations.AddIndex(
            model_name="outboxevento",
            index=models.Index(fields=["status", "proxima_tentativa"], name="outbox_status_prox_idx"),
        ),
        migrations.AddIndex(
            model_name="outboxevento",
            index=models.Index(fields=["tipo_evento", "status"], name="outbox_tipo_status_idx"),
        ),

        # SubscricaoEvento
        migrations.CreateModel(
            name="SubscricaoEvento",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscricoes_evento", to="api.empresa")),
                ("tipo_evento_pattern", models.CharField(max_length=200)),
                ("url_destino", models.URLField(max_length=500)),
                ("secret_hmac", models.CharField(blank=True, default="", max_length=128)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-criado_em"]},
        ),

        # SchemaContrato
        migrations.CreateModel(
            name="SchemaContrato",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="schema_contratos", to="api.empresa")),
                ("nome", models.CharField(max_length=200)),
                ("dominio", models.CharField(default="", max_length=80)),
                ("descricao", models.TextField(blank=True, default="")),
                ("owner_equipe", models.CharField(blank=True, default="", max_length=120)),
                ("compatibilidade", models.CharField(choices=[("full","Full"),("backward","Backward"),("forward","Forward"),("none","Nenhuma")], default="backward", max_length=20)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["dominio", "nome"]},
        ),
        migrations.AlterUniqueTogether(
            name="schemacontrato",
            unique_together={("empresa", "nome")},
        ),

        # VersaoSchema
        migrations.CreateModel(
            name="VersaoSchema",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("schema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versoes", to="api.schemacontrato")),
                ("versao", models.PositiveSmallIntegerField()),
                ("schema_json", models.JSONField()),
                ("exemplo_payload", models.JSONField(default=dict)),
                ("changelog", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("rascunho","Rascunho"),("publicado","Publicado"),("deprecado","Deprecado")], default="rascunho", max_length=20)),
                ("publicado_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-versao"]},
        ),
        migrations.AlterUniqueTogether(
            name="versaoschema",
            unique_together={("schema", "versao")},
        ),

        # ModeloML
        migrations.CreateModel(
            name="ModeloML",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("empresa", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="modelos_ml", to="api.empresa")),
                ("nome", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=100)),
                ("tipo", models.CharField(choices=[("classificacao","Classificação"),("regressao","Regressão"),("anomalia","Detecção de Anomalia"),("nlp","NLP / Texto"),("series_temporais","Séries Temporais"),("regras","Motor de Regras")], default="classificacao", max_length=30)),
                ("descricao", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("staging","Staging"),("producao","Produção"),("deprecado","Deprecado"),("pausado","Pausado")], db_index=True, default="staging", max_length=20)),
                ("versao_atual", models.CharField(default="1.0.0", max_length=30)),
                ("owner_equipe", models.CharField(blank=True, default="", max_length=120)),
                ("endpoint_inferencia", models.URLField(blank=True, default="", max_length=500)),
                ("metricas_baseline", models.JSONField(default=dict)),
                ("features_entrada", models.JSONField(default=list)),
                ("feature_alvo", models.CharField(blank=True, default="", max_length=100)),
                ("slo_latencia_ms", models.PositiveIntegerField(default=500)),
                ("slo_precisao_min", models.FloatField(default=0.8)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["nome"]},
        ),
        migrations.AlterUniqueTogether(
            name="modeloml",
            unique_together={("empresa", "slug")},
        ),

        # RunModelo
        migrations.CreateModel(
            name="RunModelo",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modelo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="runs", to="api.modeloml")),
                ("versao", models.CharField(max_length=30)),
                ("input_hash", models.CharField(blank=True, default="", max_length=64)),
                ("predicao", models.JSONField(default=dict)),
                ("confianca", models.FloatField(blank=True, null=True)),
                ("latencia_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("ground_truth", models.JSONField(blank=True, null=True)),
                ("correto", models.BooleanField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-criado_em"]},
        ),
        migrations.AddIndex(
            model_name="runmodelo",
            index=models.Index(fields=["modelo", "criado_em"], name="run_modelo_criado_idx"),
        ),

        # MonitoramentoModelo
        migrations.CreateModel(
            name="MonitoramentoModelo",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modelo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="monitoramentos", to="api.modeloml")),
                ("data_referencia", models.DateField(db_index=True)),
                ("total_predicoes", models.PositiveIntegerField(default=0)),
                ("precisao_periodo", models.FloatField(blank=True, null=True)),
                ("f1_periodo", models.FloatField(blank=True, null=True)),
                ("latencia_p50_ms", models.FloatField(blank=True, null=True)),
                ("latencia_p95_ms", models.FloatField(blank=True, null=True)),
                ("latencia_p99_ms", models.FloatField(blank=True, null=True)),
                ("taxa_erro", models.FloatField(default=0.0)),
                ("drift_score", models.FloatField(blank=True, null=True)),
                ("status_alerta", models.CharField(choices=[("ok","OK"),("atencao","Atenção"),("drift","Drift Detectado"),("degradacao","Degradação de Performance")], db_index=True, default="ok", max_length=20)),
                ("distribuicao_features", models.JSONField(default=dict)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-data_referencia"]},
        ),
        migrations.AlterUniqueTogether(
            name="monitoramentomodelo",
            unique_together={("modelo", "data_referencia")},
        ),
    ]
