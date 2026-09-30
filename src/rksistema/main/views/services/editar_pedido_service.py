"""Edição completa de um pedido: cabeçalho + itens (SKU, quantidade e preço).

O saldo é derivado do histórico de movimentações, então na edição os itens do
pedido são **substituídos**: apagamos os itens atuais e criamos os novos. Para
validar corretamente a disponibilidade, somamos de volta ao saldo a quantidade
que o próprio pedido já reservava no depósito de destino (essas saídas deixam
de existir e são recriadas).

Orçamentos podem ser editados sem validação de saldo.

Rode os testes com:
    python manage.py test main.test_pedido_edicao
"""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from main.models.movimentacao import Movimentacao
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.estoque_error import EstoqueError


class EditarPedidoService:
    """Substitui os itens e o cabeçalho de um pedido existente."""

    @staticmethod
    @transaction.atomic
    def executar(*, pedido, dados, itens, usuario=None):
        if not itens:
            raise EstoqueError("O pedido deve ter pelo menos um item.")

        eh_orcamento = pedido.eh_orcamento
        deposito = dados["deposito"]

        # Quantidade que o pedido atual já reservava (por SKU/depósito).
        atuais = defaultdict(Decimal)
        for item in pedido.itens.select_related("sku").all():
            atuais[(item.sku_id, item.deposito_id)] += item.quantidade

        skus = {}
        novos = defaultdict(Decimal)
        for item in itens:
            if item["quantidade"] is None or item["quantidade"] <= 0:
                raise EstoqueError("A quantidade deve ser maior que zero.")
            skus[item["sku"].pk] = item["sku"]
            novos[item["sku"].pk] += item["quantidade"]

        if not eh_orcamento:
            for sku_id, quantidade in novos.items():
                devolvido = atuais.get((sku_id, deposito.pk), Decimal("0"))
                disponivel = (
                    CalcularSaldoService.executar(sku=skus[sku_id], deposito=deposito)
                    + devolvido
                )
                if disponivel < quantidade:
                    raise EstoqueError(
                        f"Saldo insuficiente para {skus[sku_id]}: "
                        f"disponível {disponivel}, solicitado {quantidade}."
                    )

        # Cabeçalho
        pedido.deposito = deposito
        pedido.parceiro = dados.get("parceiro")
        pedido.documento = dados.get("documento") or ""
        pedido.observacao = dados.get("observacao") or ""
        pedido.forma_pagamento = dados.get("forma_pagamento") or None
        pedido.prazo_pagamento = dados.get("prazo_pagamento") or ""
        pedido.reservado = bool(
            dados.get("reservado") and not eh_orcamento and pedido.origem == "VENDA"
        )
        if not eh_orcamento:
            pedido.status_pedido = dados.get("status_pedido") or None
        pedido.save(
            update_fields=[
                "deposito", "parceiro", "documento", "observacao",
                "forma_pagamento", "prazo_pagamento", "status_pedido", "reservado",
            ]
        )

        # Substitui os itens (o saldo é recalculado a partir do histórico).
        ids = set(pedido.itens.values_list("id", flat=True))
        if ids:
            Movimentacao.objects.filter(id__in=ids).update(movimentacao_origem=None)
            Movimentacao.objects.filter(id__in=ids).delete()

        tipo = "ORCAMENTO" if eh_orcamento else "SAIDA"
        return [
            Movimentacao.objects.create(
                sku=item["sku"], deposito=deposito, pedido=pedido,
                tipo=tipo, origem=pedido.origem,
                quantidade=item["quantidade"], usuario=usuario,
                # Item a item: um pedido pode ter vários clientes; o do
                # cabeçalho (pedido.parceiro) é o principal e serve de padrão.
                parceiro=item.get("parceiro") or pedido.parceiro,
                documento=pedido.documento,
                observacao=pedido.observacao,
                preco_unitario=item.get("preco_unitario"),
                status_pedido=pedido.status_pedido,
                forma_pagamento=pedido.forma_pagamento,
                prazo_pagamento=pedido.prazo_pagamento,
            )
            for item in itens
        ]
