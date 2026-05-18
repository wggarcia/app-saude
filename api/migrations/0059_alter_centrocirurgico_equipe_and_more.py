from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0058_hospital_fase3"),
    ]

    operations = [
        migrations.AlterField(
            model_name="centrocirurgico",
            name="equipe",
            field=models.JSONField(default=list, help_text="[{nome, funcao}]"),
        ),
        migrations.AlterField(
            model_name="centrocirurgico",
            name="sala",
            field=models.CharField(blank=True, default="", help_text="Ex: Sala 1, CC-A", max_length=50),
        ),
        migrations.AlterField(
            model_name="centrocirurgico",
            name="tipo_anestesia",
            field=models.CharField(blank=True, default="", help_text="Geral, Raqui, Peridural, Local", max_length=50),
        ),
        migrations.AlterField(
            model_name="evolucaoclinicainternado",
            name="sinais_vitais",
            field=models.JSONField(default=dict, help_text='{"pa":"120/80","temp":36.5,"spo2":98,"fc":72,"fr":16}'),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="fio2_pct",
            field=models.PositiveSmallIntegerField(blank=True, help_text="FiO2 em %", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="glasgow_motor",
            field=models.PositiveSmallIntegerField(blank=True, help_text="1-6", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="glasgow_ocular",
            field=models.PositiveSmallIntegerField(blank=True, help_text="1-4", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="glasgow_verbal",
            field=models.PositiveSmallIntegerField(blank=True, help_text="1-5", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="modo_ventilatorio",
            field=models.CharField(blank=True, default="", help_text="Ex: VCV, PCV, SIMV, PSV", max_length=50),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="peep",
            field=models.PositiveSmallIntegerField(blank=True, help_text="PEEP em cmH2O", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="pressao_arterial_media",
            field=models.PositiveSmallIntegerField(blank=True, help_text="PAM em mmHg", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="sofa_cardiovascular",
            field=models.PositiveSmallIntegerField(blank=True, help_text="0-4", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="sofa_coagulacao",
            field=models.PositiveSmallIntegerField(blank=True, help_text="0-4", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="sofa_hepatico",
            field=models.PositiveSmallIntegerField(blank=True, help_text="0-4", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="sofa_neurologico",
            field=models.PositiveSmallIntegerField(blank=True, help_text="0-4", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="sofa_renal",
            field=models.PositiveSmallIntegerField(blank=True, help_text="0-4", null=True),
        ),
        migrations.AlterField(
            model_name="monitoramentouti",
            name="sofa_respiratorio",
            field=models.PositiveSmallIntegerField(blank=True, help_text="0-4", null=True),
        ),
        migrations.AlterField(
            model_name="pedidoexame",
            name="exames",
            field=models.JSONField(default=list, help_text="[{nome, codigo_tuss, instrucoes}]"),
        ),
        migrations.AlterField(
            model_name="pedidoexame",
            name="material",
            field=models.CharField(blank=True, default="", help_text="Ex: sangue venoso, urina 24h", max_length=100),
        ),
        migrations.AlterField(
            model_name="pedidoexame",
            name="observacoes_clinicas",
            field=models.TextField(blank=True, default="", help_text="Hipótese diagnóstica / contexto clínico"),
        ),
        migrations.AlterField(
            model_name="resultadoexame",
            name="resultados_json",
            field=models.JSONField(default=list, help_text="[{exame, valor, unidade, referencia, status}]"),
        ),
        migrations.AlterField(
            model_name="resultadoexame",
            name="url_imagem",
            field=models.URLField(blank=True, default="", help_text="Link do DICOM / PDF do laudo"),
        ),
        migrations.AlterField(
            model_name="sumarioalta",
            name="cid_secundarios",
            field=models.JSONField(default=list, help_text='["J18.9", "E11"]'),
        ),
        migrations.AlterField(
            model_name="sumarioalta",
            name="medicamentos_alta",
            field=models.JSONField(default=list, help_text="[{nome, dose, via, frequencia, duracao}]"),
        ),
    ]
