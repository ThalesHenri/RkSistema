from django.db import transaction

from main.models.movimentacao import Movimentacao
from main.views.services.estoque_error import EstoqueError


class RegistrarEntradaService:
    """Regra de negócio para registrar uma entrada de estoque."""

    @staticmethod
    @transaction.atomic
    def executar(*, sku, deposito, quantidade, origem, usuario=None,
                 parceiro=None, documento="", observacao=""):
        if quantidade <= 0:
            raise EstoqueError("A quantidade deve ser maior que zero.")

        return Movimentacao.objects.create(
            sku=sku,
            deposito=deposito,
            tipo="ENTRADA",
            origem=origem,
            quantidade=quantidade,
            usuario=usuario,
            parceiro=parceiro,
            documento=documento,
            observacao=observacao,
        )
