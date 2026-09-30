from django.db import models


class Categoria(models.Model):
    nome = models.CharField("nome", max_length=100)
    categoria_pai = models.ForeignKey(
        "self",
        verbose_name="categoria pai",
        null=True,
        blank=True,
        related_name="subcategorias",
        on_delete=models.PROTECT,
    )
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]

    def __str__(self):
        if self.categoria_pai:
            return f"{self.categoria_pai} > {self.nome}"
        return self.nome
