from rest_framework import serializers

from main.models.parceiro import Parceiro


class ParceiroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parceiro
        fields = [
            "id", "tipo", "razao_social", "nome_fantasia", "cnpj_cpf",
            "telefone", "email", "endereco", "ativo",
        ]
