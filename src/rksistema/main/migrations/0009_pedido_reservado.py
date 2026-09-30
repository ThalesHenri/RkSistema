from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0008_backfill_movimentacao_parceiro"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="reservado",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Indica se os itens deste pedido foram reservados do saldo "
                    "destinado ao cliente."
                ),
                verbose_name="reserva explícita para cliente",
            ),
        ),
    ]