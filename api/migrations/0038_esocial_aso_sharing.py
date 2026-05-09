from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0037_farmacia_avancado"),
    ]

    operations = [
        # xml_gerado no evento eSocial
        migrations.AddField(
            model_name="esocialeventosst",
            name="xml_gerado",
            field=models.TextField(blank=True, default=""),
        ),
        # S-2230 no choices de tipo_evento
        migrations.AlterField(
            model_name="esocialeventosst",
            name="tipo_evento",
            field=models.CharField(
                choices=[
                    ("S-2210", "S-2210 — Comunicação de Acidente do Trabalho"),
                    ("S-2220", "S-2220 — Monitoramento da Saúde do Trabalhador"),
                    ("S-2230", "S-2230 — Afastamento Temporário"),
                    ("S-2240", "S-2240 — Condições Ambientais do Trabalho"),
                ],
                max_length=10,
            ),
        ),
        # ASOCompartilhamento
        migrations.CreateModel(
            name="ASOCompartilhamento",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=64, unique=True)),
                ("empresa_destino_cnpj", models.CharField(blank=True, default="", max_length=18)),
                ("empresa_destino_nome", models.CharField(blank=True, default="", max_length=200)),
                ("email_destino", models.EmailField(blank=True, default="")),
                ("acessos", models.PositiveIntegerField(default=0)),
                ("max_acessos", models.PositiveIntegerField(default=20)),
                ("expira_em", models.DateTimeField()),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("aso", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="compartilhamentos", to="api.asoocupacional")),
                ("empresa_origem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="asos_compartilhados", to="api.empresa")),
            ],
            options={"ordering": ["-criado_em"]},
        ),
    ]
