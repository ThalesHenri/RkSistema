from rest_framework import serializers

from main.models.produto import Produto


class ProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = ["id", "tipo_produto", "nome", "categoria", "descricao", "ativo", "criado_em", "atualizado_em"]
