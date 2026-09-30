from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from main.models.unidade_medida import UnidadeMedida
from main.views.serializers.unidade_medida_serializer import UnidadeMedidaSerializer


class UnidadeMedidaViewSet(ModelViewSet):
    queryset = UnidadeMedida.objects.all()
    serializer_class = UnidadeMedidaSerializer
    permission_classes = [IsAuthenticated]
