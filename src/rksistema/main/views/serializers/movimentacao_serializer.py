from rest_framework import serializers

from main.models.movimentacao import Movimentacao


class MovimentacaoSerializer(serializers.ModelSerializer):
    """Somente leitura via API — a criação passa pelas actions entrada/saida/producao do MovimentacaoViewSet."""

    valor_total = serializers.SerializerMethodField()

    class Meta:
        model = Movimentacao
        fields = [
            "id", "pedido", "sku", "deposito", "tipo", "origem", "quantidade",
            "parceiro", "documento", "usuario", "data_movimentacao",
            "observacao", "preco_unitario", "status_pedido",
            "forma_pagamento", "prazo_pagamento", "valor_total",
        ]
        read_only_fields = fields

    def get_valor_total(self, obj):
        if obj.valor_total is None:
            return None
        return format(obj.valor_total, ".2f")
