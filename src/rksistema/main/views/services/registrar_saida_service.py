from django.db import transaction

from main.models.movimentacao import Movimentacao
from main.models.pedido import Pedido
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.estoque_error import EstoqueError


class RegistrarSaidaService:
    """Regra de negócio para registrar uma saída de estoque, validando saldo."""

    @staticmethod
    @transaction.atomic
    def executar(*, sku, deposito, quantidade, origem, usuario=None,
                 parceiro=None, documento="", observacao="",
                 preco_unitario=None, forma_pagamento=None, prazo_pagamento=""):
        if quantidade <= 0:
            raise EstoqueError("A quantidade deve ser maior que zero.")

        saldo_atual = CalcularSaldoService.executar(sku=sku, deposito=deposito)
        if saldo_atual < quantidade:
            raise EstoqueError(
                f"Saldo insuficiente: disponível {saldo_atual}, solicitado {quantidade}."
            )

        # Vendas viram "pedido" com status inicial Pendente, editável depois.
        status_inicial = "PENDENTE" if origem == "VENDA" else None

        return Movimentacao.objects.create(
            sku=sku,
            deposito=deposito,
            tipo="SAIDA",
            origem=origem,
            quantidade=quantidade,
            usuario=usuario,
            parceiro=parceiro,
            documento=documento,
            observacao=observacao,
            preco_unitario=preco_unitario,
            status_pedido=status_inicial,
            forma_pagamento=forma_pagamento or None,
            prazo_pagamento=prazo_pagamento or "",
        )

    @staticmethod
    @transaction.atomic
    def executar_varios(*, itens, deposito, origem, usuario=None,
                        parceiro=None, documento="", observacao="",
                        forma_pagamento=None, prazo_pagamento="", reservado=False):
        """Registra uma saída contendo vários SKUs como um único pedido."""
        if not itens:
            raise EstoqueError("Informe pelo menos um item para a saída.")

        quantidades = {}
        for item in itens:
            sku = item["sku"]
            quantidade = item["quantidade"]
            if quantidade <= 0:
                raise EstoqueError("A quantidade deve ser maior que zero.")
            quantidades[sku.pk] = quantidades.get(sku.pk, 0) + quantidade

        for item in itens:
            sku = item["sku"]
            if sku.pk not in quantidades:
                continue
            saldo_atual = CalcularSaldoService.executar(sku=sku, deposito=deposito)
            if saldo_atual < quantidades[sku.pk]:
                raise EstoqueError(
                    f"Saldo insuficiente para {sku}: disponível {saldo_atual}, "
                    f"solicitado {quantidades[sku.pk]}."
                )
            quantidades.pop(sku.pk)

        status_inicial = "PENDENTE" if origem == "VENDA" else None
        pedido = Pedido.objects.create(
            deposito=deposito, origem=origem, usuario=usuario, parceiro=parceiro,
            documento=documento, observacao=observacao,
            status_pedido=status_inicial, forma_pagamento=forma_pagamento or None,
            prazo_pagamento=prazo_pagamento or "",
            reservado=bool(reservado and origem == "VENDA"),
        )
        return [
            Movimentacao.objects.create(
                sku=item["sku"], deposito=deposito, pedido=pedido, tipo="SAIDA",
                origem=origem, quantidade=item["quantidade"], usuario=usuario,
                parceiro=item.get("parceiro") or parceiro,
                documento=documento, observacao=observacao,
                preco_unitario=item.get("preco_unitario"),
                status_pedido=status_inicial,
                forma_pagamento=forma_pagamento or None,
                prazo_pagamento=prazo_pagamento or "",
            )
            for item in itens
        ]
