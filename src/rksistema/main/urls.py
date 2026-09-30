from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from main.views import (
    CategoriaViewSet,
    UnidadeMedidaViewSet,
    ProdutoViewSet,
    SKUViewSet,
    ParceiroViewSet,
    DepositoViewSet,
    MovimentacaoViewSet,
)

router = DefaultRouter()
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("unidades-medida", UnidadeMedidaViewSet, basename="unidademedida")
router.register("produtos", ProdutoViewSet, basename="produto")
router.register("skus", SKUViewSet, basename="sku")
router.register("parceiros", ParceiroViewSet, basename="parceiro")
router.register("depositos", DepositoViewSet, basename="deposito")
router.register("movimentacoes", MovimentacaoViewSet, basename="movimentacao")

urlpatterns = [
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
] + router.urls
