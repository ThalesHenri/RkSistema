from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from main.models.sku import SKU
from main.models.deposito import Deposito
from main.models.parceiro import Parceiro

TIPO_MOVIMENTACAO_CHOICES = [
    ("ENTRADA", "Entrada"),
    ("SAIDA", "Saída"),
    ("AJUSTE_POSITIVO", "Ajuste (positivo)"),
    ("AJUSTE_NEGATIVO", "Ajuste (negativo)"),
    ("ORCAMENTO", "Orçamento (simulado)"),
]

ORIGEM_MOVIMENTACAO_CHOICES = [
    ("COMPRA", "Compra"),
    ("VENDA", "Venda"),
    ("PRODUCAO", "Produção própria"),
    ("PERDA", "Perda/quebra"),
    ("AJUSTE_INVENTARIO", "Ajuste de inventário"),
    ("DEVOLUCAO_CLIENTE", "Devolução de cliente"),
    ("DEVOLUCAO_FORNECEDOR", "Devolução a fornecedor"),
    ("ORCAMENTO", "Orçamento"),
]

STATUS_PEDIDO_CHOICES = [
    ("PENDENTE", "Pendente"),
    ("FATURADO", "Faturado"),
    ("ENTREGUE", "Entregue"),
    ("CANCELADO", "Cancelado"),
]

FORMA_PAGAMENTO_CHOICES = [
    ("DINHEIRO", "Dinheiro"),
    ("PIX", "Pix"),
    ("BOLETO", "Boleto"),
    ("CARTAO_CREDITO", "Cartão de crédito"),
    ("CARTAO_DEBITO", "Cartão de débito"),
    ("TRANSFERENCIA", "Transferência"),
    ("CREDIARIO", "Crediário"),
    ("OUTRO", "Outro"),
]


class Movimentacao(models.Model):
    """
    Registro imutável de entrada/saída/ajuste de estoque.
    Nunca editar ou deletar uma movimentação confirmada — para corrigir,
    criar uma movimentação de ajuste compensatória (ver views/services).
    """

    sku = models.ForeignKey(
        SKU, verbose_name="SKU", related_name="movimentacoes", on_delete=models.PROTECT,
    )
    pedido = models.ForeignKey(
        "Pedido", verbose_name="pedido", related_name="itens",
        null=True, blank=True, on_delete=models.PROTECT,
    )
    deposito = models.ForeignKey(
        Deposito, verbose_name="depósito", related_name="movimentacoes", on_delete=models.PROTECT,
    )
    tipo = models.CharField("tipo", max_length=20, choices=TIPO_MOVIMENTACAO_CHOICES)
    origem = models.CharField("origem", max_length=25, choices=ORIGEM_MOVIMENTACAO_CHOICES)
    quantidade = models.DecimalField(
        "quantidade", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    parceiro = models.ForeignKey(
        Parceiro, verbose_name="parceiro", related_name="movimentacoes",
        null=True, blank=True, on_delete=models.PROTECT,
    )
    documento = models.CharField(
        "documento", max_length=50, blank=True,
        help_text="Nº de nota fiscal, pedido etc.",
    )
    preco_unitario = models.DecimalField(
        "preço unitário",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Preço negociado nesta movimentação (venda). Se vazio, usa o preço atual do SKU.",
    )
    status_pedido = models.CharField(
        "status do pedido",
        max_length=15,
        choices=STATUS_PEDIDO_CHOICES,
        null=True,
        blank=True,
        help_text="Aplica-se a saídas de venda: pendente, faturado, entregue ou cancelado.",
    )
    forma_pagamento = models.CharField(
        "forma de pagamento",
        max_length=20,
        choices=FORMA_PAGAMENTO_CHOICES,
        null=True,
        blank=True,
        help_text="Forma de pagamento combinada com o cliente para este pedido.",
    )
    prazo_pagamento = models.CharField(
        "prazo de pagamento",
        max_length=50,
        blank=True,
        help_text="Prazo combinado para o pagamento (ex.: 30 dias, à vista).",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuário", related_name="movimentacoes",
        null=True, on_delete=models.SET_NULL,
    )
    data_movimentacao = models.DateTimeField("data da movimentação", auto_now_add=True)
    observacao = models.TextField("observação", blank=True)
    movimentacao_origem = models.ForeignKey(
        "self", verbose_name="movimentação de origem", null=True, blank=True,
        related_name="estornos", on_delete=models.PROTECT,
        help_text="Preenchido quando esta movimentação é um estorno/ajuste de outra.",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"
        ordering = ["-data_movimentacao"]
        indexes = [
            models.Index(fields=["sku", "deposito"]),
            models.Index(fields=["tipo"]),
            models.Index(fields=["data_movimentacao"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.sku} ({self.quantidade})"

    @property
    def eh_entrada(self):
        return self.tipo in ("ENTRADA", "AJUSTE_POSITIVO")

    @property
    def eh_saida(self):
        return self.tipo in ("SAIDA", "AJUSTE_NEGATIVO")

    @property
    def valor_total(self):
        """Total monetário desta movimentação, quando há preço negociado."""
        if self.preco_unitario is None:
            return None
        return self.preco_unitario * self.quantidade
