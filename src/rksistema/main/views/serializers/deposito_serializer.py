from rest_framework import serializers

from main.models.deposito import Deposito


class DepositoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deposito
        fields = ["id", "nome", "endereco", "ativo"]
