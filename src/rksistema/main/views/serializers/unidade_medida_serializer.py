from rest_framework import serializers

from main.models.unidade_medida import UnidadeMedida


class UnidadeMedidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadeMedida
        fields = ["id", "sigla", "nome"]
