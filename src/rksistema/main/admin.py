from django.contrib import admin
from .models import *


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ["nome", "tipo_produto", "categoria", "ativo"]
    list_filter = ["tipo_produto", "ativo", "categoria"]


@admin.register(Movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = [
        "data_movimentacao", "tipo", "origem", "sku", "quantidade",
        "preco_unitario", "valor_total", "status_pedido", "parceiro",
    ]
    list_filter = ["tipo", "origem", "status_pedido", "deposito"]


# Register your models here.
admin.site.register(Categoria)
admin.site.register(UnidadeMedida)
admin.site.register(SKU)
admin.site.register(Parceiro)
admin.site.register(Deposito)