"""Regra de negócio para registrar **orçamentos** (pedidos simulados).

Um orçamento é um `Pedido` com `origem="ORCAMENTO"` cujos itens são
`Movimentacao` com `tipo="ORCAMENTO"`. Esses itens **não movimentam estoque**
(são ignorados por `CalcularSaldoService` e por `_calcular_saldos`) e servem
apenas para compor o documento de orçamento.

A efetivação (transformar o orçamento em pedido real) fica em
`efetivar_orcamento_service.py`.

Rode os testes com:
    python manage.py test main.test_orcamento
"""

from django.db import transaction

from main.models.movimentacao import Movimentacao
from main.models.pedido import Pedido
from main.views.services.estoque_error import EstoqueError


class RegistrarOrcamentoService:
    """Cria um orçamento sem validar saldo (pode superar o estoque atual)."""

    @staticmethod
    @transaction.atomic
    def executar_varios(*, itens, deposito, usuario=None, parceiro=None,
                        documento="", observacao="", forma_pagamento=None,
                        prazo_pagamento=""):
        if not itens:
            raise EstoqueError("Informe pelo menos um item para o orçamento.")
        for item in itens:
            if item["quantidade"] <= 0:
                raise EstoqueError("A quantidade deve ser maior que zero.")

        pedido = Pedido.objects.create(
            deposito=deposito,
            origem="ORCAMENTO",
            usuario=usuario,
            parceiro=parceiro,
            documento=documento,
            observacao=observacao,
            status_pedido=None,
            forma_pagamento=forma_pagamento or None,
            prazo_pagamento=prazo_pagamento or "",
        )
        return [
            Movimentacao.objects.create(
                sku=item["sku"],
                deposito=deposito,
                pedido=pedido,
                tipo="ORCAMENTO",
                origem="ORCAMENTO",
                quantidade=item["quantidade"],
                usuario=usuario,
                parceiro=item.get("parceiro") or parceiro,
                documento=documento,
                observacao=observacao,
                preco_unitario=item.get("preco_unitario"),
                forma_pagamento=forma_pagamento or None,
                prazo_pagamento=prazo_pagamento or "",
            )
            for item in itens
        ]
