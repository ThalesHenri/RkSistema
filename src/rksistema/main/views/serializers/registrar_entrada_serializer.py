from rest_framework import serializers

from main.models.sku import SKU
from main.models.deposito import Deposito
from main.models.parceiro import Parceiro
from main.models.movimentacao import ORIGEM_MOVIMENTACAO_CHOICES


class RegistrarEntradaSerializer(serializers.Serializer):
    sku = serializers.PrimaryKeyRelatedField(queryset=SKU.objects.all())
    deposito = serializers.PrimaryKeyRelatedField(queryset=Deposito.objects.all())
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=2)
    origem = serializers.ChoiceField(choices=ORIGEM_MOVIMENTACAO_CHOICES)
    parceiro = serializers.PrimaryKeyRelatedField(queryset=Parceiro.objects.all(), required=False, allow_null=True)
    documento = serializers.CharField(required=False, allow_blank=True, default="")
    observacao = serializers.CharField(required=False, allow_blank=True, default="")
