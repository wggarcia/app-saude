"""
Adiciona campos eSocial corretos à CAT e ASO:
- CATOcupacional: tp_cat, cod_parte_corpo, lateralidade, cod_agente_causador,
                  testemunha_nome, testemunha_telefone
- ASOOcupacional: cid_inapto, riscos_ocupacionais
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0047_gestao_crescimento'),
    ]

    operations = [
        # ── CATOcupacional ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='catocupacional',
            name='tp_cat',
            field=models.CharField(
                choices=[('1', 'Inicial'), ('2', 'Reabertura'), ('3', 'Comunicação de Óbito')],
                default='1', max_length=1, verbose_name='Tipo de CAT',
            ),
        ),
        migrations.AddField(
            model_name='catocupacional',
            name='cod_parte_corpo',
            field=models.CharField(
                choices=[
                    ('010', 'Cabeça / Crânio'), ('020', 'Ouvido(s)'), ('030', 'Olho(s) / Face'),
                    ('040', 'Pescoço'), ('050', 'Tronco / Tórax'), ('060', 'Coluna Vertebral'),
                    ('070', 'Abdome'), ('080', 'Membro Superior Direito'), ('081', 'Membro Superior Esquerdo'),
                    ('082', 'Ambos os Membros Superiores'), ('090', 'Membro Inferior Direito'),
                    ('091', 'Membro Inferior Esquerdo'), ('092', 'Ambos os Membros Inferiores'),
                    ('730', 'Múltiplas Partes do Corpo'), ('800', 'Sistema Nervoso'),
                    ('900', 'Órgãos Internos'), ('999', 'Outras Partes'),
                ],
                default='730', max_length=3, verbose_name='Código parte atingida (eSocial)',
            ),
        ),
        migrations.AddField(
            model_name='catocupacional',
            name='lateralidade',
            field=models.CharField(
                choices=[('1', 'Esquerdo'), ('2', 'Direito'), ('3', 'Ambos'), ('9', 'Não Aplicável')],
                default='9', max_length=1, verbose_name='Lateralidade',
            ),
        ),
        migrations.AddField(
            model_name='catocupacional',
            name='cod_agente_causador',
            field=models.CharField(
                choices=[
                    ('0001', 'Animais e insetos'), ('0002', 'Choque elétrico'),
                    ('0003', 'Esforço excessivo / movimento repetitivo'), ('0004', 'Explosão / implosão'),
                    ('0005', 'Incêndio'), ('0006', 'Queda'),
                    ('0007', 'Substâncias químicas / gases / fumaças'), ('0008', 'Temperatura extrema'),
                    ('0009', 'Máquinas e equipamentos'), ('0010', 'Material cortante / perfurante'),
                    ('0011', 'Impacto por objeto / equipamento'), ('0012', 'Acidente de trânsito'),
                    ('0099', 'Outros agentes'),
                ],
                default='0099', max_length=4, verbose_name='Agente causador (eSocial)',
            ),
        ),
        migrations.AddField(
            model_name='catocupacional',
            name='testemunha_nome',
            field=models.CharField(blank=True, default='', max_length=180, verbose_name='Nome da testemunha'),
        ),
        migrations.AddField(
            model_name='catocupacional',
            name='testemunha_telefone',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Telefone da testemunha'),
        ),

        # ── ASOOcupacional ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='asoocupacional',
            name='cid_inapto',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='CID (quando inapto/restrito)'),
        ),
        migrations.AddField(
            model_name='asoocupacional',
            name='riscos_ocupacionais',
            field=models.TextField(blank=True, default='', verbose_name='Riscos ocupacionais do cargo (NR-7)'),
        ),
    ]
