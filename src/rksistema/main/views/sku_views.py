from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from main.models.sku import SKU
from main.views.serializers.sku_serializer import SKUSerializer


class SKUViewSet(ModelViewSet):
    queryset = SKU.objects.all()
    serializer_class = SKUSerializer
    permission_classes = [IsAuthenticated]
