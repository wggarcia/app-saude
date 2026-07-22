import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0158_dispositivopushpublico_empresa'),
    ]

    operations = [
        # LoteMedicamento.item passa a ser opcional — lotes de MedicamentoFarmacia
        # (catálogo com rastreabilidade ANVISA própria) são vinculados por
        # `medicamento`, sem ItemFarmacia associado.
        migrations.AlterField(
            model_name='lotemedicamento',
            name='item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='lotes',
                to='api.itemfarmacia',
            ),
        ),
        # PedidoDelivery — marca se a baixa de estoque já foi disparada, para
        # não baixar duas vezes quando o status avança/retransmite.
        migrations.AddField(
            model_name='pedidodelivery',
            name='estoque_baixado',
            field=models.BooleanField(default=False),
        ),
        # ItemPedidoDelivery — itens do pedido de delivery/e-commerce/iFood,
        # vinculados ao catálogo MedicamentoFarmacia para permitir a baixa de
        # estoque na confirmação (mesma baixa usada pelo PDV).
        migrations.CreateModel(
            name='ItemPedidoDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('descricao', models.CharField(blank=True, default='', max_length=200)),
                ('codigo_barras', models.CharField(blank=True, default='', max_length=50)),
                ('quantidade', models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ('preco_unitario', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('total_item', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens_pedido_delivery', to='api.empresa')),
                ('medicamento', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='itens_delivery', to='api.medicamentofarmacia')),
                ('pedido', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens', to='api.pedidodelivery')),
            ],
            options={'ordering': ['id']},
        ),
    ]
