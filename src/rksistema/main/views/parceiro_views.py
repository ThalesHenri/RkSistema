from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from main.models.parceiro import Parceiro
from main.views.serializers.parceiro_serializer import ParceiroSerializer


class ParceiroViewSet(ModelViewSet):
    queryset = Parceiro.objects.all()
    serializer_class = ParceiroSerializer
    permission_classes = [IsAuthenticated]
