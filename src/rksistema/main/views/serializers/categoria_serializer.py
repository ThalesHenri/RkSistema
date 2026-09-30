from rest_framework import serializers

from main.models.categoria import Categoria


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nome", "categoria_pai", "ativo", "criado_em", "atualizado_em"]
