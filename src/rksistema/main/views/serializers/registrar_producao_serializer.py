from rest_framework import serializers

from main.models.sku import SKU
from main.models.deposito import Deposito
from main.models.parceiro import Parceiro


class RegistrarProducaoSerializer(serializers.Serializer):
    """Payload de produção: matéria-prima consumida + produto em estoque produzido."""

    materia_prima = serializers.PrimaryKeyRelatedField(
        queryset=SKU.objects.filter(produto__tipo_produto="MATERIA_PRIMA")
    )
    quantidade_materia_prima = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    produto_acabado = serializers.PrimaryKeyRelatedField(
        queryset=SKU.objects.filter(produto__tipo_produto="PRODUTO_ACABADO")
    )
    quantidade_produzida = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    deposito = serializers.PrimaryKeyRelatedField(queryset=Deposito.objects.all())
    parceiro = serializers.PrimaryKeyRelatedField(
        queryset=Parceiro.objects.all(), required=False, allow_null=True
    )
    documento = serializers.CharField(required=False, allow_blank=True, default="")
    observacao = serializers.CharField(required=False, allow_blank=True, default="")