from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from main.models.produto import Produto
from main.views.serializers.produto_serializer import ProdutoSerializer


class ProdutoViewSet(ModelViewSet):
    queryset = Produto.objects.all()
    serializer_class = ProdutoSerializer
    permission_classes = [IsAuthenticated]
