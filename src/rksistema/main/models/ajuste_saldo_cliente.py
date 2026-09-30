from django.conf import settings
from django.db import models

from main.models.deposito import Deposito
from main.models.parceiro import Parceiro
from main.models.sku import SKU


class AjusteSaldoCliente(models.Model):
    """Ajuste auditável do saldo destinado sem alterar o estoque físico."""

    parceiro = models.ForeignKey(
        Parceiro, related_name="ajustes_saldo_cliente", on_delete=models.PROTECT,
    )
    sku = models.ForeignKey(
        SKU, related_name="ajustes_saldo_cliente", on_delete=models.PROTECT,
    )
    deposito = models.ForeignKey(
        Deposito, related_name="ajustes_saldo_cliente", null=True, blank=True,
        on_delete=models.PROTECT,
    )
    delta = models.DecimalField(max_digits=12, decimal_places=2)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]

    def __str__(self):
        return f"Ajuste de saldo {self.parceiro} / {self.sku}: {self.delta}"