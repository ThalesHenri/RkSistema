from django.db import models

from main.models.categoria import Categoria

TIPO_PRODUTO_CHOICES = [
    ("MATERIA_PRIMA", "Matéria-prima"),
    ("PRODUTO_ACABADO", "Produto em estoque"),
]


class Produto(models.Model):
    tipo_produto = models.CharField(
        "tipo de produto",
        max_length=15,
        choices=TIPO_PRODUTO_CHOICES,
        default="PRODUTO_ACABADO",
        help_text="Matéria-prima é consumida na produção; produto em estoque é o resultado final.",
    )
    nome = models.CharField("nome", max_length=150)
    categoria = models.ForeignKey(
        Categoria,
        verbose_name="categoria",
        related_name="produtos",
        on_delete=models.PROTECT,
    )
    descricao = models.TextField("descrição", blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome
