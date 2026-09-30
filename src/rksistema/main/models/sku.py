from django.core.validators import MinValueValidator
from django.db import models

from main.models.produto import Produto
from main.models.unidade_medida import UnidadeMedida


class SKU(models.Model):
    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        related_name="skus",
        on_delete=models.PROTECT,
    )
    codigo = models.CharField("código interno", max_length=50, unique=True)
    codigo_barras = models.CharField(
        "código de barras", max_length=50, blank=True, null=True, unique=True
    )
    tamanho_capacidade = models.CharField(
        "tamanho/capacidade", max_length=50, blank=True,
        help_text="Ex: 200ml, 500g, 30x40cm",
    )
    cor = models.CharField("cor", max_length=50, blank=True)
    unidade_medida = models.ForeignKey(
        UnidadeMedida,
        verbose_name="unidade de medida",
        related_name="skus",
        on_delete=models.PROTECT,
    )
    estoque_minimo = models.DecimalField(
        "estoque mínimo",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Usado para disparar alerta de estoque baixo.",
    )
    preco_custo = models.DecimalField(
        "preço de custo", max_digits=12, decimal_places=2, null=True, blank=True,
    )
    preco_venda = models.DecimalField(
        "preço de venda", max_digits=12, decimal_places=2, null=True, blank=True,
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "SKU"
        verbose_name_plural = "SKUs"
        ordering = ["produto__nome", "codigo"]

    def __str__(self):
        descricao = " ".join(filter(None, [self.tamanho_capacidade, self.cor]))
        base = f"{self.produto.nome} — {self.codigo}"
        return f"{base} ({descricao})" if descricao else base
