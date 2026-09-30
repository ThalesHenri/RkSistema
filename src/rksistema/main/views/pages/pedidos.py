"""Página de lista de pedidos (frontend server-rendered).

Cada "pedido" é o grupo de movimentações (itens) de uma mesma saída
criada com RegistrarSaidaService.executar_varios — ou seja, um pedido pode
ter 1..N SKUs. Esta página mostra um resumo por pedido com a quantidade e
o valor agregados, além de permitir editar status/pagamento/prazo do
pedido completo (a edição se aplica a todos os seus itens).
"""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from main.models import (
    Parceiro,
    Pedido,
    STATUS_PEDIDO_CHOICES,
    FORMA_PAGAMENTO_CHOICES,
)


class PedidoListView(LoginRequiredMixin, ListView):
    model = Pedido
    template_name = "main/pedido_list.html"
    context_object_name = "pedidos"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            Pedido.objects.select_related("parceiro", "deposito", "usuario")
            .order_by("-criado_em")
        )
        parceiro_id = self.request.GET.get("parceiro")
        if parceiro_id and parceiro_id.isdigit():
            # Um pedido pode reunir vários clientes: o do cabeçalho (principal)
            # ou qualquer cliente atribuído aos seus itens.
            qs = qs.filter(
                Q(parceiro_id=parceiro_id) | Q(itens__parceiro_id=parceiro_id)
            ).distinct()
        # Filtro por tipo: pedidos "de verdade" x orçamentos (pedidos simulados).
        tipo_filtro = self.request.GET.get("tipo")
        if tipo_filtro == "orcamento":
            qs = qs.filter(origem="ORCAMENTO")
        elif tipo_filtro == "pedido":
            qs = qs.exclude(origem="ORCAMENTO")
        status_filtro = self.request.GET.get("status")
        if status_filtro in dict(STATUS_PEDIDO_CHOICES):
            # O status de um pedido vive em seus itens (movimentações);
            # os itens do mesmo pedido mantêm-se sincronizados.
            qs = qs.filter(itens__status_pedido=status_filtro).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["parceiros"] = Parceiro.objects.all().order_by("razao_social")
        ctx["status_choices"] = STATUS_PEDIDO_CHOICES
        ctx["formas_pagamento"] = FORMA_PAGAMENTO_CHOICES

        parceiro_filtro = None
        parceiro_id = self.request.GET.get("parceiro")
        if parceiro_id and parceiro_id.isdigit():
            parceiro_filtro = Parceiro.objects.filter(pk=parceiro_id).first()
        ctx["parceiro_filtro"] = parceiro_filtro

        status_filtro = self.request.GET.get("status")
        ctx["status_filtro"] = (
            status_filtro if status_filtro in dict(STATUS_PEDIDO_CHOICES) else ""
        )

        tipo_filtro = self.request.GET.get("tipo")
        ctx["tipo_filtro"] = tipo_filtro if tipo_filtro in ("orcamento", "pedido") else ""
        ctx["num_orcamentos"] = Pedido.objects.filter(origem="ORCAMENTO").count()

        ctx["linhas"] = [self._linha(pedido) for pedido in ctx["object_list"]]
        return ctx

    def _linha(self, pedido):
        """Agrega os dados de UM pedido (itens = movimentações do pedido)."""
        itens = list(pedido.itens.select_related("sku", "parceiro").all())
        primeiro = itens[0] if itens else None

        # Clientes do pedido: primeiro o principal (cabeçalho) e depois os
        # demais na ordem em que aparecem nos itens (pedido multi-cliente).
        clientes = []
        vistos = set()
        if pedido.parceiro_id:
            clientes.append(pedido.parceiro)
            vistos.add(pedido.parceiro_id)
        for item in itens:
            if item.parceiro_id and item.parceiro_id not in vistos:
                vistos.add(item.parceiro_id)
                clientes.append(item.parceiro)

        total_qtd = sum((i.quantidade for i in itens), Decimal("0"))

        # Valor total usando o preço negociado (preco_unitario) ou, se faltar,
        # o preço de venda atual do SKU (mesma regra do PDF do pedido).
        total_valor = Decimal("0")
        tem_valor = True
        for item in itens:
            preco = (
                item.preco_unitario
                if item.preco_unitario is not None
                else item.sku.preco_venda
            )
            if preco is None:
                tem_valor = False
            else:
                total_valor += preco * item.quantidade

        return {
            "pedido": pedido,
            "num_skus": len(itens),
            "quantidade_total": total_qtd,
            "valor_total": total_valor if tem_valor else None,
            "primeiro_item": primeiro,
            "eh_orcamento": pedido.eh_orcamento,
            "clientes": clientes,
            "num_clientes": len(clientes),
            # Campos do primeiro item: representam ao pedido completo porque
            # os itens do mesmo pedido são editados sempre em conjunto.
            "status_pedido": getattr(primeiro, "status_pedido", None) if primeiro else None,
            "forma_pagamento": getattr(primeiro, "forma_pagamento", None) if primeiro else None,
            "prazo_pagamento": (primeiro.prazo_pagamento or "") if primeiro else "",
        }


class PedidosStatusEmLoteView(LoginRequiredMixin, View):
    """Atualiza o status dos pedidos reais selecionados na listagem."""

    def post(self, request):
        ids = {
            valor for valor in request.POST.getlist("pedido_ids")
            if valor.isdigit()
        }
        novo_status = request.POST.get("status_pedido", "")

        if not ids:
            messages.error(request, "Selecione pelo menos um pedido.")
            return redirect("pedidos")
        if novo_status not in dict(STATUS_PEDIDO_CHOICES):
            messages.error(request, "Selecione um status válido.")
            return redirect("pedidos")

        pedidos = Pedido.objects.filter(pk__in=ids).exclude(origem="ORCAMENTO")
        pedido_ids = list(pedidos.values_list("pk", flat=True))
        if not pedido_ids:
            messages.error(request, "Nenhum pedido real válido foi selecionado.")
            return redirect("pedidos")

        from main.models import Movimentacao

        with transaction.atomic():
            atualizados = pedidos.update(status_pedido=novo_status)
            Movimentacao.objects.filter(pedido_id__in=pedido_ids).update(
                status_pedido=novo_status
            )
        rotulo = dict(STATUS_PEDIDO_CHOICES)[novo_status]
        messages.success(
            request,
            f"Status de {atualizados} pedido(s) atualizado para {rotulo}.",
        )
        return redirect("pedidos")
    
    