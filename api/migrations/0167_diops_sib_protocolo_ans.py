from django.db import migrations, models


class Migration(migrations.Migration):
    """Campo protocolo_ans em DIOPSDeclaracao e SIBRegistro — guarda o
    protocolo de retorno da ANS após transmissão real (automática SIPWeb ou
    registro manual do envio feito pela operadora no portal oficial da ANS).

    Puramente aditivo: CharField blank/default vazio, nenhuma constraint.
    Dados existentes continuam válidos (protocolo vazio = ainda não transmitido
    de fato)."""

    dependencies = [
        ('api', '0166_backfill_identidade_paciente_onco_ccih'),
    ]

    operations = [
        migrations.AddField(
            model_name='diopsdeclaracao',
            name='protocolo_ans',
            field=models.CharField(
                blank=True, default='', max_length=60,
                help_text='Protocolo de retorno da ANS — só preenchido após transmissão real (automática SIPWeb ou registro manual do envio pelo portal ANS)',
            ),
        ),
        migrations.AddField(
            model_name='sibregistro',
            name='protocolo_ans',
            field=models.CharField(
                blank=True, default='', max_length=60,
                help_text='Protocolo de retorno da ANS — só preenchido após transmissão real (automática SIPWeb ou registro manual do envio pelo portal ANS)',
            ),
        ),
    ]
