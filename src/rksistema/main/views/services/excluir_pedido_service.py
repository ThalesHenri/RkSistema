"""Exclusão de um pedido e de todos os seus itens (movimentações).

O saldo é sempre **derivado** do histórico de movimentações, então apagar os
itens já devolve corretamente as quantidades ao estoque. Antes de apagar,
desfazemos os vínculos `movimentacao_origem` (campo `on_delete=PROTECT`) para
evitar `ProtectedError` ao remover pares/estornos.

Rode os testes com:
    python manage.py test main.test_orcamento main.test_pedido_edicao
"""

from django.db import transaction

from main.models.movimentacao import Movimentacao


class ExcluirPedidoService:
    """Remove o pedido e todos os seus itens em uma única transação."""

    @staticmethod
    @transaction.atomic
    def executar(pedido):
        ids = set(pedido.itens.values_list("id", flat=True))

        if ids:
            # Estornos/vinculados apontam para estas movimentações (PROTECT).
            vinculados = Movimentacao.objects.filter(
                movimentacao_origem_id__in=ids
            ).values_list("id", flat=True)
            ids.update(vinculados)
            Movimentacao.objects.filter(id__in=ids).update(movimentacao_origem=None)
            Movimentacao.objects.filter(id__in=ids).delete()

        pedido.delete()
        return ids
