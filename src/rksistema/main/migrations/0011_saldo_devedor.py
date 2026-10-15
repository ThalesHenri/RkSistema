import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0010_ajuste_saldo_cliente"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SaldoDevedor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "valor",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                        verbose_name="valor",
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[("DEBITO", "Débito"), ("PAGAMENTO", "Pagamento")],
                        default="DEBITO",
                        max_length=10,
                        verbose_name="tipo",
                    ),
                ),
                (
                    "descricao",
                    models.CharField(blank=True, max_length=255, verbose_name="descrição"),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="usuário",
                    ),
                ),
            ],
            options={
                "verbose_name": "saldo devedor",
                "verbose_name_plural": "saldos devedores",
                "ordering": ["-criado_em"],
            },
        ),
    ]
