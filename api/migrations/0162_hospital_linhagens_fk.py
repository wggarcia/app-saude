import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0161_asoocupacional_agendamento_origem'),
    ]

    operations = [
        # Liga InternacaoHospital ao ProntuarioHospitalar (PEP) pelo CPF do paciente.
        migrations.AddField(
            model_name='internacaohospital',
            name='prontuario_pep',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='api.prontuariohospitalar',
                help_text='PEP vinculado na criação da internação por CPF/MPI — não exposto na UI',
            ),
        ),
        # Liga PacienteInternado à InternacaoHospital que o criou/sincronizou.
        migrations.AddField(
            model_name='pacienteinternado',
            name='internacao_sync',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='api.internacaohospital',
                help_text='InternacaoHospital correspondente — populado ao criar internação, não exposto na UI',
            ),
        ),
    ]
