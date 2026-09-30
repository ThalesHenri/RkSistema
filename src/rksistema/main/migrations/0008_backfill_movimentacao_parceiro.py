"""Copia o cliente do cabeçalho do pedido para os itens que não têm cliente.

Antes do suporte a VÁRIOS CLIENTES por pedido, só ``Pedido.parceiro`` guardava
o cliente — o ``parceiro`` dos itens (``Movimentacao``) ficava nulo nas saídas
de pedido. Como agora o cliente de cada item é o que os filtros de faturamento
(página de pedidos e dashboard) usam para contabilizar por cliente, os itens
antigos passam a receber o cliente do pedido a que pertencem.

Itens com cliente próprio são preservados; pedidos sem cliente no cabeçalho
permanecem com os itens sem cliente.
"""

from django.db import migrations


def copiar_cliente_do_pedido(apps, schema_editor):
    Movimentacao = apps.get_model("main", "Movimentacao")
    Pedido = apps.get_model("main", "Pedido")

    pedidos = Pedido.objects.exclude(parceiro__isnull=True).only("id", "parceiro_id")
    for pedido in pedidos.iterator():
        Movimentacao.objects.filter(
            pedido_id=pedido.pk, parceiro__isnull=True
        ).update(parceiro_id=pedido.parceiro_id)


class Migration(migrations.Migration):

    dependencies = [
        (
            "main",
            "0007_alter_movimentacao_origem_alter_movimentacao_tipo_and_more",
        ),
    ]

    operations = [
        # Sem volta: desfazer apagaria clientes legítimos. A migração apenas
        # preenche o que estava vazio.
        migrations.RunPython(copiar_cliente_do_pedido, migrations.RunPython.noop),
    ]
