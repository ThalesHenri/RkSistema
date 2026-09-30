"""Efetivação de orçamento: cria o pedido real e exclui o orçamento.

Para não duplicar registros no banco, o orçamento **não** é convertido
in-place: um novo pedido de venda é criado via `RegistrarSaidaService`
(que valida o saldo) e, em seguida, o orçamento (itens + `Pedido`) é apagado.
Uma nota na observação do novo pedido preserva a rastreabilidade
("Efetivado a partir do orçamento #N").

Rode os testes com:
    python manage.py test main.test_orcamento
"""

from django.db import transaction

from main.views.services.estoque_error import EstoqueError
from main.views.services.excluir_pedido_service import ExcluirPedidoService
from main.views.services.registrar_saida_service import RegistrarSaidaService

NOTA_ORIGEM = "Efetivado a partir do orçamento #{pk} (orçamento excluído)."


class EfetivarOrcamentoService:
    """Transforma um orçamento em pedido real (e remove o orçamento)."""

    @staticmethod
    @transaction.atomic
    def executar(pedido, usuario=None):
        if not pedido.eh_orcamento:
            raise EstoqueError("Este registro não é um orçamento.")

        itens = list(pedido.itens.select_related("sku", "parceiro").all())
        if not itens:
            raise EstoqueError("O orçamento não possui itens.")

        itens_dados = [
            {
                "sku": item.sku,
                "quantidade": item.quantidade,
                "preco_unitario": item.preco_unitario,
                # Preserva o cliente de cada item (pedido com vários clientes).
                "parceiro": item.parceiro,
            }
            for item in itens
        ]

        observacao = (pedido.observacao or "").strip()
        nota = NOTA_ORIGEM.format(pk=pedido.pk)
        observacao = f"{observacao}\n{nota}" if observacao else nota

        # Cria o pedido real: valida saldo e grava SAIDA/VENDA/PENDENTE.
        novos_itens = RegistrarSaidaService.executar_varios(
            itens=itens_dados,
            deposito=pedido.deposito,
            origem="VENDA",
            usuario=usuario,
            parceiro=pedido.parceiro,
            documento=pedido.documento,
            observacao=observacao,
            forma_pagamento=pedido.forma_pagamento,
            prazo_pagamento=pedido.prazo_pagamento,
        )

        # O orçamento deixa de existir (não ocupa espaço no banco).
        ExcluirPedidoService.executar(pedido)

        return novos_itens[0].pedido
