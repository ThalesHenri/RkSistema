from rest_framework import serializers

from main.models.movimentacao import ORIGEM_MOVIMENTACAO_CHOICES
from main.views.serializers.registrar_saida_serializer import RegistrarSaidaSerializer


class RegistrarOrcamentoSerializer(RegistrarSaidaSerializer):
    """Payload de orçamento: mesmos campos da saída, mas origem fixa.

    O orçamento NÃO movimenta estoque (ver RegistrarOrcamentoService).
    """

    origem = serializers.ChoiceField(
        choices=ORIGEM_MOVIMENTACAO_CHOICES, required=False, default="ORCAMENTO",
    )
