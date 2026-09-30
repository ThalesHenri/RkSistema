from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from main.models.deposito import Deposito
from main.views.serializers.deposito_serializer import DepositoSerializer


class DepositoViewSet(ModelViewSet):
    queryset = Deposito.objects.all()
    serializer_class = DepositoSerializer
    permission_classes = [IsAuthenticated]
