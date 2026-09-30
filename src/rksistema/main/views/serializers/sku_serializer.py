from rest_framework import serializers

from main.models.sku import SKU


class SKUSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKU
        fields = [
            "id", "produto", "codigo", "codigo_barras", "tamanho_capacidade",
            "cor", "unidade_medida", "estoque_minimo", "preco_custo",
            "preco_venda", "ativo",
        ]
