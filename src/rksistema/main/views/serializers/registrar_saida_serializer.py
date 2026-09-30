from rest_framework import serializers

from main.models.sku import SKU
from main.models.deposito import Deposito
from main.models.parceiro import Parceiro
from main.models.movimentacao import ORIGEM_MOVIMENTACAO_CHOICES, FORMA_PAGAMENTO_CHOICES


class RegistrarSaidaSerializer(serializers.Serializer):
    sku = serializers.PrimaryKeyRelatedField(queryset=SKU.objects.all(), required=False)
    deposito = serializers.PrimaryKeyRelatedField(queryset=Deposito.objects.all())
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    origem = serializers.ChoiceField(choices=ORIGEM_MOVIMENTACAO_CHOICES)
    parceiro = serializers.PrimaryKeyRelatedField(queryset=Parceiro.objects.all(), required=False, allow_null=True)
    documento = serializers.CharField(required=False, allow_blank=True, default="")
    observacao = serializers.CharField(required=False, allow_blank=True, default="")
    preco_unitario = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0,
    )
    forma_pagamento = serializers.ChoiceField(
        choices=FORMA_PAGAMENTO_CHOICES, required=False, allow_null=True, allow_blank=True,
    )
    prazo_pagamento = serializers.CharField(required=False, allow_blank=True, default="")
    itens = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, attrs):
        if not attrs.get("itens") and not (attrs.get("sku") and attrs.get("quantidade") is not None):
            raise serializers.ValidationError("Informe sku/quantidade ou uma lista de itens.")
        if attrs.get("itens"):
            item_serializer = RegistrarSaidaItemSerializer(data=attrs["itens"], many=True)
            item_serializer.is_valid(raise_exception=True)
            attrs["itens"] = item_serializer.validated_data
        return attrs


class RegistrarSaidaItemSerializer(serializers.Serializer):
    sku = serializers.PrimaryKeyRelatedField(queryset=SKU.objects.all())
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=2)
    preco_unitario = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0,
    )
