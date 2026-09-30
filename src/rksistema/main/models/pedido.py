from django.conf import settings
from django.db import models

from main.models.deposito import Deposito
from main.models.movimentacao import (
    FORMA_PAGAMENTO_CHOICES,
    ORIGEM_MOVIMENTACAO_CHOICES,
    STATUS_PEDIDO_CHOICES,
)
from main.models.parceiro import Parceiro


class Pedido(models.Model):
    """Agrupa os itens de uma saída de venda ou de outro pedido."""

    deposito = models.ForeignKey(Deposito, on_delete=models.PROTECT)
    origem = models.CharField(max_length=25, choices=ORIGEM_MOVIMENTACAO_CHOICES)
    parceiro = models.ForeignKey(
        Parceiro, null=True, blank=True, on_delete=models.PROTECT,
    )
    documento = models.CharField(max_length=50, blank=True)
    observacao = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
    )
    status_pedido = models.CharField(
        max_length=15, choices=STATUS_PEDIDO_CHOICES, null=True, blank=True,
    )
    forma_pagamento = models.CharField(
        max_length=20, choices=FORMA_PAGAMENTO_CHOICES, null=True, blank=True,
    )
    prazo_pagamento = models.CharField(max_length=50, blank=True)
    reservado = models.BooleanField(
        "reserva explícita para cliente",
        default=False,
        help_text=(
            "Indica se os itens deste pedido foram reservados do saldo "
            "destinado ao cliente."
        ),
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.documento or f"Pedido #{self.pk}"

    @property
    def eh_orcamento(self):
        return self.origem == "ORCAMENTO"