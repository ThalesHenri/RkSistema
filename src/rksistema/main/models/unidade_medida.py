from django.db import models


class UnidadeMedida(models.Model):
    sigla = models.CharField("sigla", max_length=10, unique=True)
    nome = models.CharField("nome", max_length=50)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "unidade de medida"
        verbose_name_plural = "unidades de medida"
        ordering = ["sigla"]

    def __str__(self):
        return self.sigla
