from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from decimal import Decimal

from django.db.models import Q, Sum
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from main.forms import SaldoDevedorForm
from main.models import SaldoDevedor


class SaldoDevedorListView(LoginRequiredMixin, ListView):
    model = SaldoDevedor
    template_name = "main/saldo_devedor_list.html"
    context_object_name = "lancamentos"
    paginate_by = 50

    def get_queryset(self):
        return SaldoDevedor.objects.select_related("usuario").order_by(
            "-criado_em", "-pk"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        totais = SaldoDevedor.objects.aggregate(
            debitos=Sum("valor", filter=Q(tipo=SaldoDevedor.Tipo.DEBITO)),
            pagamentos=Sum("valor", filter=Q(tipo=SaldoDevedor.Tipo.PAGAMENTO)),
        )
        ctx["total_debitos"] = totais["debitos"] or Decimal("0.00")
        ctx["total_pagamentos"] = totais["pagamentos"] or Decimal("0.00")
        ctx["saldo_atual"] = SaldoDevedor.saldo_atual()
        return ctx


class SaldoDevedorCreateView(LoginRequiredMixin, CreateView):
    model = SaldoDevedor
    form_class = SaldoDevedorForm
    template_name = "main/cadastro_form.html"
    success_url = reverse_lazy("saldo_devedor_list")
    titulo = "Novo lançamento do saldo devedor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        ctx["url_lista"] = "saldo_devedor_list"
        return ctx

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        messages.success(self.request, "Lançamento registrado com sucesso.")
        return super().form_valid(form)
