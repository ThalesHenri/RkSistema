from rest_framework import serializers

from main.models.movimentacao import STATUS_PEDIDO_CHOICES, FORMA_PAGAMENTO_CHOICES


class AtualizarPrecoStatusSerializer(serializers.Serializer):
    """Atualização parcial de preço, status, forma/prazo de pagamento de uma saída."""

    preco_unitario = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0,
    )
    status_pedido = serializers.ChoiceField(
        choices=STATUS_PEDIDO_CHOICES, required=False, allow_null=True,
    )
    forma_pagamento = serializers.ChoiceField(
        choices=FORMA_PAGAMENTO_CHOICES, required=False, allow_null=True, allow_blank=True,
    )
    prazo_pagamento = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        enviados = list(self.initial_data.keys())
        if not any(
            k in enviados
            for k in (
                "preco_unitario",
                "status_pedido",
                "forma_pagamento",
                "prazo_pagamento",
            )
        ):
            raise serializers.ValidationError(
                "Informe ao menos um dos campos: 'preco_unitario', 'status_pedido', "
                "'forma_pagamento' ou 'prazo_pagamento'."
            )
        return attrs