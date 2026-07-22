from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0160_assistencia_social_segmento"),
    ]

    operations = [
        migrations.AddField(
            model_name="asoocupacional",
            name="agendamento_origem",
            field=models.OneToOneField(
                blank=True,
                help_text="Agendamento SST que gerou este ASO automaticamente",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="aso_gerado",
                to="api.agendamentosst",
                verbose_name="Agendamento SST de origem",
            ),
        ),
    ]
