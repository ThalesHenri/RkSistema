"""Vistas que emitem PDFs de pedidos de clientes (frontend server-rendered).

- MovimentacaoPedidoPdfView  → PDF individual de uma movimentação SAIDA/VENDA.
- RelatorioPedidosPdfView    → listado filtrável de pedidos (parceiro/status).

Exigem login (LoginRequiredMixin), igual às demais páginas.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from main.models import Movimentacao, Parceiro, STATUS_PEDIDO_CHOICES
from main.views.services.pedido_pdf_service import (
    gerar_pdf_pedido,
    gerar_pdf_relatorio_pedidos,
)


class MovimentacaoPedidoPdfView(LoginRequiredMixin, View):
    """Emite o PDF de um pedido de cliente (SAIDA/VENDA) ou de um orçamento."""

    def get(self, request, pk):
        movimentacao = get_object_or_404(Movimentacao, pk=pk)
        eh_orcamento = movimentacao.tipo == "ORCAMENTO"
        eh_pedido = movimentacao.eh_saida and movimentacao.origem == "VENDA"
        if not (eh_pedido or eh_orcamento):
            messages.error(
                request,
                "Só é possível emitir PDF para pedidos de clientes "
                "(saídas com origem Venda) ou para orçamentos.",
            )
            return redirect("movimentacoes")

        pdf = gerar_pdf_pedido(
            movimentacao,
            usuario=request.user,
            tipo_documento="ORCAMENTO" if eh_orcamento else "PEDIDO",
        )
        numero = movimentacao.pedido_id or movimentacao.pk
        resposta = HttpResponse(pdf, content_type="application/pdf")
        prefixo = "orcamento" if eh_orcamento else "pedido"
        resposta["Content-Disposition"] = (
            f'attachment; filename="{prefixo}-{numero}.pdf"'
        )
        return resposta


class RelatorioPedidosPdfView(LoginRequiredMixin, View):
    """Listado de pedidos de clientes filtrável (mesmos filtros da página)."""

    def get(self, request):
        qs = (
            Movimentacao.objects.select_related(
                "sku", "sku__produto", "deposito", "parceiro", "usuario"
            )
            .filter(tipo="SAIDA", origem="VENDA")
            .order_by("-data_movimentacao")
        )

        filtros = {}
        parceiro_id = request.GET.get("parceiro")
        parceiro_filtro = None
        if parceiro_id and parceiro_id.isdigit():
            parceiro_filtro = Parceiro.objects.filter(pk=parceiro_id).first()
        if parceiro_filtro:
            qs = qs.filter(parceiro=parceiro_filtro)
            filtros["parceiro"] = parceiro_filtro.razao_social

        status_filtro = request.GET.get("status")
        if status_filtro in dict(STATUS_PEDIDO_CHOICES):
            qs = qs.filter(status_pedido=status_filtro)
            filtros["status"] = dict(STATUS_PEDIDO_CHOICES)[status_filtro]

        pdf = gerar_pdf_relatorio_pedidos(
            qs, filtros=filtros, usuario=request.user
        )
        resposta = HttpResponse(pdf, content_type="application/pdf")
        resposta["Content-Disposition"] = 'attachment; filename="pedidos-clientes.pdf"'
        return resposta