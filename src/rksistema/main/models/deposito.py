from django.db import models


class Deposito(models.Model):
    nome = models.CharField("nome", max_length=100)
    endereco = models.CharField("endereço", max_length=255, blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "depósito"
        verbose_name_plural = "depósitos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome
