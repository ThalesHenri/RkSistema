from django.db import models

TIPO_PARCEIRO_CHOICES = [
    ("FORNECEDOR", "Fornecedor"),
    ("CLIENTE", "Cliente"),
    ("AMBOS", "Fornecedor e Cliente"),
]


class Parceiro(models.Model):
    tipo = models.CharField("tipo", max_length=12, choices=TIPO_PARCEIRO_CHOICES)
    razao_social = models.CharField("razão social/nome", max_length=150)
    nome_fantasia = models.CharField("nome fantasia", max_length=150, blank=True)
    cnpj_cpf = models.CharField("CNPJ/CPF", max_length=18, unique=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    endereco = models.CharField("endereço", max_length=255, blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["razao_social"]

    def __str__(self):
        return self.nome_fantasia or self.razao_social

    def pode_fornecer(self):
        return self.tipo in ("FORNECEDOR", "AMBOS")

    def pode_comprar(self):
        return self.tipo in ("CLIENTE", "AMBOS")
