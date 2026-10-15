from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.core.validators import MinValueValidator


class SaldoDevedor(models.Model):
    class Tipo(models.TextChoices):
        DEBITO = "DEBITO", "Débito"
        PAGAMENTO = "PAGAMENTO", "Pagamento"

    valor = models.DecimalField(
        "valor",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    tipo = models.CharField(
        "tipo", max_length=10, choices=Tipo.choices, default=Tipo.DEBITO
    )
    descricao = models.CharField("descrição", max_length=255, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "saldo devedor"
        verbose_name_plural = "saldos devedores"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.valor}"

    @classmethod
    def saldo_atual(cls):
        totais = cls.objects.aggregate(
            debitos=Sum("valor", filter=Q(tipo=cls.Tipo.DEBITO)),
            pagamentos=Sum("valor", filter=Q(tipo=cls.Tipo.PAGAMENTO)),
        )
        return (totais["debitos"] or Decimal("0.00")) - (
            totais["pagamentos"] or Decimal("0.00")
        )