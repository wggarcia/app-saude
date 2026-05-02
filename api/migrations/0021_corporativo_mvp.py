import uuid

from django.db import migrations, models

import api.models


def preencher_codigos_acesso(apps, schema_editor):
    Empresa = apps.get_model("api", "Empresa")
    usados = set(Empresa.objects.exclude(codigo_acesso_corporativo__isnull=True).exclude(codigo_acesso_corporativo="").values_list("codigo_acesso_corporativo", flat=True))

    for empresa in Empresa.objects.all():
        if empresa.codigo_acesso_corporativo:
            continue
        codigo = uuid.uuid4().hex
        while codigo in usados:
            codigo = uuid.uuid4().hex
        empresa.codigo_acesso_corporativo = codigo
        empresa.save(update_fields=["codigo_acesso_corporativo"])
        usados.add(codigo)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0020_aceitelegalpublico"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="codigo_acesso_corporativo",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(preencher_codigos_acesso, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="empresa",
            name="codigo_acesso_corporativo",
            field=models.CharField(default=api.models._codigo_acesso, max_length=32, unique=True),
        ),
        migrations.CreateModel(
            name="EmpresaTurno",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=80)),
                ("janela", models.CharField(blank=True, default="", max_length=80)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="turnos_corporativos", to="api.empresa")),
            ],
            options={
                "ordering": ["nome"],
                "unique_together": {("empresa", "nome")},
            },
        ),
        migrations.CreateModel(
            name="EmpresaUnidade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("codigo", models.CharField(blank=True, default="", max_length=40)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="unidades_corporativas", to="api.empresa")),
            ],
            options={
                "ordering": ["nome"],
                "unique_together": {("empresa", "nome")},
            },
        ),
        migrations.CreateModel(
            name="ColaboradorAliasCorporativo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alias_publico", models.CharField(default=api.models._codigo_acesso, max_length=80)),
                ("ativo", models.BooleanField(default=True)),
                ("permite_contato", models.BooleanField(default=False)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="aliases_corporativos", to="api.empresa")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="aliases", to="api.empresaunidade")),
                ("turno", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="aliases", to="api.empresaturno")),
            ],
            options={
                "ordering": ["-atualizado_em"],
                "unique_together": {("empresa", "alias_publico")},
            },
        ),
        migrations.CreateModel(
            name="EmpresaSetor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="setores_corporativos", to="api.empresa")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="setores", to="api.empresaunidade")),
            ],
            options={
                "ordering": ["nome"],
                "unique_together": {("empresa", "unidade", "nome")},
            },
        ),
        migrations.AddField(
            model_name="colaboradoraliascorporativo",
            name="setor",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="aliases", to="api.empresasetor"),
        ),
        migrations.CreateModel(
            name="PedidoApoioCorporativo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("deseja_contato", models.BooleanField(default=False)),
                ("canal_preferido", models.CharField(blank=True, default="", max_length=80)),
                ("relato", models.CharField(blank=True, default="", max_length=280)),
                ("status", models.CharField(choices=[("novo", "Novo"), ("em_analise", "Em analise"), ("encaminhado", "Encaminhado"), ("concluido", "Concluido")], default="novo", max_length=20)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("alias", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="pedidos_apoio", to="api.colaboradoraliascorporativo")),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="pedidos_apoio_corporativos", to="api.empresa")),
                ("setor", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="pedidos_apoio", to="api.empresasetor")),
                ("turno", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="pedidos_apoio", to="api.empresaturno")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="pedidos_apoio", to="api.empresaunidade")),
            ],
            options={"ordering": ["-criado_em"]},
        ),
        migrations.CreateModel(
            name="CheckinSemanalCorporativo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("semana_referencia", models.DateField()),
                ("carga_emocional", models.PositiveSmallIntegerField(default=3)),
                ("seguranca_psicologica", models.PositiveSmallIntegerField(default=3)),
                ("apoio_percebido", models.PositiveSmallIntegerField(default=3)),
                ("pressao_trabalho", models.PositiveSmallIntegerField(default=3)),
                ("bem_estar_geral", models.PositiveSmallIntegerField(default=3)),
                ("risco_burnout", models.PositiveSmallIntegerField(default=1)),
                ("observacao", models.CharField(blank=True, default="", max_length=280)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("alias", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="checkins_semanais", to="api.colaboradoraliascorporativo")),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="checkins_semanais_corporativos", to="api.empresa")),
                ("setor", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checkins_semanais", to="api.empresasetor")),
                ("turno", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checkins_semanais", to="api.empresaturno")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checkins_semanais", to="api.empresaunidade")),
            ],
            options={
                "ordering": ["-semana_referencia", "-criado_em"],
                "unique_together": {("empresa", "alias", "semana_referencia")},
            },
        ),
        migrations.AddIndex(
            model_name="checkinsemanalcorporativo",
            index=models.Index(fields=["empresa", "semana_referencia"], name="api_checkin_empresa_105b17_idx"),
        ),
        migrations.AddIndex(
            model_name="checkinsemanalcorporativo",
            index=models.Index(fields=["empresa", "unidade", "semana_referencia"], name="api_checkin_empresa_960334_idx"),
        ),
        migrations.AddIndex(
            model_name="checkinsemanalcorporativo",
            index=models.Index(fields=["empresa", "setor", "semana_referencia"], name="api_checkin_empresa_c6aacb_idx"),
        ),
        migrations.CreateModel(
            name="CheckinDiarioCorporativo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_referencia", models.DateField()),
                ("humor", models.PositiveSmallIntegerField(default=3)),
                ("energia", models.PositiveSmallIntegerField(default=3)),
                ("estresse", models.PositiveSmallIntegerField(default=3)),
                ("sono", models.PositiveSmallIntegerField(default=3)),
                ("dor_fisica", models.PositiveSmallIntegerField(default=1)),
                ("fadiga", models.PositiveSmallIntegerField(default=1)),
                ("ansiedade", models.PositiveSmallIntegerField(default=1)),
                ("tristeza", models.PositiveSmallIntegerField(default=1)),
                ("irritabilidade", models.PositiveSmallIntegerField(default=1)),
                ("sintomas_respiratorios", models.BooleanField(default=False)),
                ("dor_corporal", models.BooleanField(default=False)),
                ("dor_cabeca", models.BooleanField(default=False)),
                ("febre", models.BooleanField(default=False)),
                ("apoio_solicitado", models.BooleanField(default=False)),
                ("observacao", models.CharField(blank=True, default="", max_length=280)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("alias", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="checkins_diarios", to="api.colaboradoraliascorporativo")),
                ("empresa", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="checkins_diarios_corporativos", to="api.empresa")),
                ("setor", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checkins_diarios", to="api.empresasetor")),
                ("turno", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checkins_diarios", to="api.empresaturno")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checkins_diarios", to="api.empresaunidade")),
            ],
            options={
                "ordering": ["-data_referencia", "-criado_em"],
                "unique_together": {("empresa", "alias", "data_referencia")},
            },
        ),
        migrations.AddIndex(
            model_name="checkindiariocorporativo",
            index=models.Index(fields=["empresa", "data_referencia"], name="api_checkin_empresa_41fdde_idx"),
        ),
        migrations.AddIndex(
            model_name="checkindiariocorporativo",
            index=models.Index(fields=["empresa", "unidade", "data_referencia"], name="api_checkin_empresa_4a61e0_idx"),
        ),
        migrations.AddIndex(
            model_name="checkindiariocorporativo",
            index=models.Index(fields=["empresa", "setor", "data_referencia"], name="api_checkin_empresa_0b62ab_idx"),
        ),
    ]
