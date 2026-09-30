from collections import defaultdict
from decimal import Decimal
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DeleteView, FormView, ListView

from main.forms import (
    MovimentacaoEntradaForm,
    MovimentacaoSaidaForm,
    MovimentacaoPrecoStatusForm,
    ProducaoForm,
)
from main.models import (
    Deposito,
    Movimentacao,
    Pedido,
    Parceiro,
    SKU,
    STATUS_PEDIDO_CHOICES,
    FORMA_PAGAMENTO_CHOICES,
)
from main.views.services.estoque_error import EstoqueError
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_saida_service import RegistrarSaidaService
from main.views.services.registrar_producao_service import RegistrarProducaoService
from main.views.services.calcular_saldos_clientes_service import CalcularSaldosClientesService


def _calcular_saldos(deposito_id=None):
    """Retorna {sku_id: saldo} considerando entrada/saída/ajustes."""

    movs = Movimentacao.objects.select_related("sku", "deposito")
    if deposito_id:
        movs = movs.filter(deposito_id=deposito_id)

    saldos = defaultdict(Decimal)
    for m in movs.only("sku_id", "deposito_id", "tipo", "quantidade"):
        saldos[m.sku_id] += m.quantidade if m.eh_entrada else -m.quantidade
    return saldos

def _rotulo_sku(sku):
    """Usa o rótulo canônico do SKU, incluindo medida e cor quando definidos."""
    return str(sku)


class MovimentacaoListView(LoginRequiredMixin, ListView):
    model = Movimentacao
    template_name = "main/movimentacao_list.html"
    context_object_name = "movimentacoes"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            Movimentacao.objects.select_related("sku", "sku__produto", "deposito", "parceiro", "usuario")
            .order_by("-data_movimentacao")
        )
        parceiro_id = self.request.GET.get("parceiro")
        if parceiro_id and parceiro_id.isdigit():
            qs = qs.filter(parceiro_id=parceiro_id)
        status_filtro = self.request.GET.get("status")
        if status_filtro in dict(STATUS_PEDIDO_CHOICES):
            qs = qs.filter(status_pedido=status_filtro)
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
        ctx["status_filtro"] = status_filtro if status_filtro in dict(STATUS_PEDIDO_CHOICES) else ""
        return ctx


class EstoqueListView(LoginRequiredMixin, ListView):
    """Saldos de estoque por SKU, com filtro opcional por depósito."""

    model = SKU
    template_name = "main/estoque.html"
    context_object_name = "skus"

    def get_queryset(self):
        return SKU.objects.select_related("produto", "unidade_medida").order_by("produto__nome", "codigo")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        deposito_filtro = None
        dep_id = self.request.GET.get("deposito")
        if dep_id and dep_id.isdigit():
            deposito_filtro = Deposito.objects.filter(pk=dep_id).first()

        saldos = _calcular_saldos(deposito_filtro.pk if deposito_filtro else None)

        # detalhamento por depósito (sempre calculado para o filtro atual)
        saldos_por_deposito = defaultdict(dict)
        movs = Movimentacao.objects.select_related("deposito").only(
            "sku_id", "deposito_id", "tipo", "quantidade", "deposito__nome"
        )
        if deposito_filtro:
            movs = movs.filter(deposito=deposito_filtro)
        for m in movs:
            delta = m.quantidade if m.eh_entrada else -m.quantidade
            saldos_por_deposito[m.sku_id][m.deposito_id] = (
                saldos_por_deposito[m.sku_id].get(m.deposito_id, Decimal("0")) + delta
            )
        depositos_ativos = list(Deposito.objects.filter(ativo=True).order_by("nome"))

        linhas = []
        for sku in ctx["object_list"]:
            saldo = saldos.get(sku.pk, Decimal("0"))
            linhas.append(
                {
                    "produto": sku.produto.nome,
                    "tipo": {
                        "label": sku.produto.get_tipo_produto_display(),
                        "classe": (
                            "badge-info"
                            if sku.produto.tipo_produto == "MATERIA_PRIMA"
                            else "badge-ok"
                        ),
                    },
                    "codigo": sku.codigo,
                    "descricao": " ".join(filter(None, [sku.tamanho_capacidade, sku.cor])) or "—",
                    "unidade": sku.unidade_medida.sigla,
                    "saldo": saldo,
                    "estoque_minimo": sku.estoque_minimo,
                    "baixo": saldo <= sku.estoque_minimo,
                    "saldos_depositos": [
                        {
                            "nome": d.nome,
                            "saldo": saldos_por_deposito.get(sku.pk, {}).get(d.pk, Decimal("0")),
                        }
                        for d in depositos_ativos
                    ],
                }
            )

        ctx["linhas"] = linhas
        ctx["depositos"] = Deposito.objects.all().order_by("nome")
        ctx["deposito_filtro"] = deposito_filtro
        ctx["saldos_clientes_painel"] = CalcularSaldosClientesService.executar(
            deposito_id=deposito_filtro.pk if deposito_filtro else None
        )
        return ctx


class AtualizarSaldoClienteView(LoginRequiredMixin, View):
    """Define o saldo destinado desejado sem alterar estoque físico."""

    def post(self, request, parceiro_id, sku_id):
        parceiro = Parceiro.objects.filter(
            pk=parceiro_id, tipo__in=("CLIENTE", "AMBOS")
        ).first()
        sku = SKU.objects.filter(pk=sku_id).first()
        if parceiro is None or sku is None:
            messages.error(request, "Cliente ou SKU inválido para ajuste.")
            return redirect("estoque")

        deposito_raw = request.POST.get("deposito", "").strip()
        deposito_id = None
        if deposito_raw:
            if not deposito_raw.isdigit() or not Deposito.objects.filter(pk=deposito_raw).exists():
                messages.error(request, "Depósito inválido para ajuste.")
                return redirect("estoque")
            deposito_id = int(deposito_raw)

        try:
            novo_saldo = forms.DecimalField(
                max_digits=12, decimal_places=2,
            ).clean(request.POST.get("saldo", ""))
        except ValidationError:
            messages.error(request, "Informe um saldo numérico válido com até duas casas decimais.")
            return redirect("estoque")

        saldo_atual = CalcularSaldosClientesService.saldo_atual(
            parceiro_id=parceiro.pk, sku_id=sku.pk, deposito_id=deposito_id,
        )
        if saldo_atual is None:
            messages.error(request, "Não há saldo destinado deste SKU para esse cliente.")
            return redirect("estoque")

        delta = novo_saldo - saldo_atual
        if delta:
            from main.models import AjusteSaldoCliente

            AjusteSaldoCliente.objects.create(
                parceiro=parceiro,
                sku=sku,
                deposito_id=deposito_id,
                delta=delta,
                usuario=request.user,
            )
        messages.success(request, "Saldo destinado atualizado com sucesso.")
        destino = reverse_lazy("estoque")
        if deposito_id:
            destino = f"{destino}?deposito={deposito_id}"
        return redirect(destino)


class BaseRegistrarMovimentacaoView(LoginRequiredMixin, FormView):
    """Compartilhado pelas views de entrada e saída."""

    titulo = ""
    mensagem_sucesso = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        return ctx

    def processar(self, dados):
        raise NotImplementedError

    def form_valid(self, form):
        try:
            self.processar(form.cleaned_data)
        except EstoqueError as erro:
            form.add_error(None, str(erro))
            return self.form_invalid(form)
        messages.success(self.request, self.mensagem_sucesso)
        return super().form_valid(form)


class RegistrarEntradaView(BaseRegistrarMovimentacaoView):
    template_name = "main/registrar_movimentacao.html"
    form_class = MovimentacaoEntradaForm
    success_url = reverse_lazy("movimentacoes")
    titulo = "Registrar entrada de estoque"
    mensagem_sucesso = "Entrada de estoque registrada com sucesso."

    def processar(self, dados):
        RegistrarEntradaService.executar(
            sku=dados["sku"],
            deposito=dados["deposito"],
            quantidade=dados["quantidade"],
            origem=dados["origem"],
            usuario=self.request.user if self.request.user.is_authenticated else None,
            parceiro=dados.get("parceiro"),
            documento=dados.get("documento") or "",
            observacao=dados.get("observacao") or "",
        )


class RegistrarSaidaView(BaseRegistrarMovimentacaoView):
    template_name = "main/saida_movimentacao.html"
    form_class = MovimentacaoSaidaForm
    success_url = reverse_lazy("movimentacoes")
    titulo = "Registrar saída de estoque"
    mensagem_sucesso = "Saída de estoque registrada com sucesso."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["eh_orcamento"] = False
        context["skus_opcoes"] = [
            {"pk": sku.pk, "rotulo": _rotulo_sku(sku)}
            for sku in SKU.objects.select_related("produto").order_by(
                "produto__nome", "codigo"
            )
        ]
        context["clientes_opcoes"] = [
            {"pk": cliente.pk, "rotulo": str(cliente)}
            for cliente in Parceiro.objects.filter(
                tipo__in=("CLIENTE", "AMBOS")
            ).order_by("razao_social")
        ]
        return context

    def processar(self, dados):
        itens = [{"sku": dados["sku"], "quantidade": dados["quantidade"],
                  "preco_unitario": dados.get("preco_unitario") or None,
                  "parceiro": dados.get("parceiro")}]
        indices_principais = sorted({
            int(match.group(1))
            for nome in dados
            if (match := re.fullmatch(r"sku_(\d+)", nome))
        })
        for indice in indices_principais:
            sku = dados.get(f"sku_{indice}")
            quantidade = dados.get(f"quantidade_{indice}")
            if sku and quantidade:
                itens.append({
                    "sku": sku,
                    "quantidade": quantidade,
                    "preco_unitario": dados.get(f"preco_unitario_{indice}"),
                    "parceiro": dados.get("parceiro"),
                })

        if dados.get("tem_clientes_adicionais"):
            indices_blocos = sorted({
                int(match.group(1))
                for nome in dados
                if (match := re.fullmatch(r"cliente_ad_(\d+)", nome))
            })
            for indice_bloco in indices_blocos:
                cliente = dados.get(f"cliente_ad_{indice_bloco}")
                indices_itens = sorted({
                    int(match.group(1))
                    for nome in dados
                    if (match := re.fullmatch(
                        rf"sku_{indice_bloco}_(\d+)", nome
                    ))
                })
                for indice_item in indices_itens:
                    sufixo = f"_{indice_bloco}_{indice_item}"
                    sku = dados.get(f"sku{sufixo}")
                    quantidade = dados.get(f"quantidade{sufixo}")
                    if sku and quantidade:
                        itens.append({
                            "sku": sku,
                            "quantidade": quantidade,
                            "preco_unitario": dados.get(f"preco_unitario{sufixo}"),
                            "parceiro": cliente,
                        })

        RegistrarSaidaService.executar_varios(
            itens=itens, deposito=dados["deposito"], origem=dados["origem"],
            usuario=self.request.user if self.request.user.is_authenticated else None,
            parceiro=dados.get("parceiro"), documento=dados.get("documento") or "",
            observacao=dados.get("observacao") or "",
            forma_pagamento=dados.get("forma_pagamento") or None,
            prazo_pagamento=dados.get("prazo_pagamento") or "",
            reservado=dados.get("reservado", False),
        )


class AtualizarPrecoStatusView(LoginRequiredMixin, View):
    """Edita preço, status, forma de pagamento e/ou prazo de uma saída."""

    def post(self, request, pk):
        movimentacao = get_object_or_404(Movimentacao, pk=pk)
        if not movimentacao.eh_saida:
            messages.error(
                request,
                "Preço, status e pagamento só se aplicam a movimentações de saída.",
            )
            return redirect("movimentacoes")

        form = MovimentacaoPrecoStatusForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            if dados.get("preco_unitario") is not None:
                movimentacao.preco_unitario = dados["preco_unitario"]
            movimentacao.status_pedido = dados.get("status_pedido") or None
            movimentacao.forma_pagamento = dados.get("forma_pagamento") or None
            movimentacao.prazo_pagamento = dados.get("prazo_pagamento") or ""
            atualizacoes = {
                "status_pedido": movimentacao.status_pedido,
                "forma_pagamento": movimentacao.forma_pagamento,
                "prazo_pagamento": movimentacao.prazo_pagamento,
            }
            with transaction.atomic():
                if movimentacao.pedido_id:
                    pedido = movimentacao.pedido
                    pedido.status_pedido = atualizacoes["status_pedido"]
                    pedido.forma_pagamento = atualizacoes["forma_pagamento"]
                    pedido.prazo_pagamento = atualizacoes["prazo_pagamento"]
                    pedido.save(
                        update_fields=[
                            "status_pedido", "forma_pagamento", "prazo_pagamento",
                        ]
                    )
                    pedido.itens.update(**atualizacoes)
                movimentacao.save(
                    update_fields=[
                        "preco_unitario", "status_pedido",
                        "forma_pagamento", "prazo_pagamento", "atualizado_em",
                    ]
                )
            messages.success(
                request, "Preço/status/pagamento atualizados com sucesso."
            )
        else:
            messages.error(request, "Valores inválidos para preço/status/pagamento.")

        return redirect("pedidos")


class RegistrarProducaoView(BaseRegistrarMovimentacaoView):
    template_name = "main/registrar_movimentacao.html"
    form_class = ProducaoForm
    success_url = reverse_lazy("movimentacoes")
    titulo = "Registrar produção (matéria-prima → produto em estoque)"
    mensagem_sucesso = (
        "Produção registrada com sucesso: saída da matéria-prima e "
        "entrada do produto em estoque."
    )

    def processar(self, dados):
        RegistrarProducaoService.executar(
            materia_prima=dados["materia_prima"],
            quantidade_materia_prima=dados["quantidade_materia_prima"],
            produto_acabado=dados["produto_acabado"],
            quantidade_produzida=dados["quantidade_produzida"],
            deposito=dados["deposito"],
            usuario=self.request.user if self.request.user.is_authenticated else None,
            documento=dados.get("documento") or "",
            observacao=dados.get("observacao") or "",
            parceiro=dados.get("parceiro"),
        )


class MovimentacaoDeleteView(LoginRequiredMixin, DeleteView):
    """Exclui uma movimentação (com página de confirmação).

    No caso de uma produção, a entrada fica vinculada à saída
    (movimentacao_origem); excluímos o PAR junto para o saldo continuar
    consistente. Em qualquer outro caso, apenas a movimentação escolhida é
    removida — o saldo é sempre recalculado a partir do histórico restante.
    """

    model = Movimentacao
    template_name = "main/cadastro_confirm_delete.html"
    titulo = "Excluir movimentação"
    url_lista = "movimentacoes"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        ctx["url_lista"] = self.url_lista
        return ctx

    def get_success_url(self):
        return reverse_lazy("movimentacoes")

    def form_valid(self, form):
        with transaction.atomic():
            alvo = self.get_object()
            pedido = alvo.pedido if alvo.pedido_id else None
            ids = {alvo.pk}
            if alvo.movimentacao_origem_id:
                ids.add(alvo.movimentacao_origem_id)
            # Estornos/vinculados apontam para esta movimentação
            ids.update(alvo.estornos.values_list("id", flat=True))
            if alvo.pedido_id:
                ids.update(alvo.pedido.itens.values_list("id", flat=True))
            # Desfaz o vínculo (movimentacao_origem) antes de apagar, pois o
            # campo é on_delete=PROTECT — evita ProtectedError ao excluir o par.
            Movimentacao.objects.filter(id__in=ids).update(movimentacao_origem=None)
            Movimentacao.objects.filter(id__in=ids).delete()
            if pedido:
                pedido.delete()
        messages.success(self.request, "Movimentação excluída com sucesso.")
        return redirect(self.get_success_url())


class RegistrarOrcamentoView(LoginRequiredMixin, View):
    """Cria orçamento sem baixar estoque; a efetivação valida o saldo."""

    template_name = "main/registrar_movimentacao.html"

    def get(self, request):
        from main.forms import MovimentacaoSaidaForm

        return self._render(request, MovimentacaoSaidaForm())

    def post(self, request):
        from main.forms import MovimentacaoSaidaForm
        from main.views.services.registrar_orcamento_service import RegistrarOrcamentoService

        dados_post = request.POST.copy()
        dados_post["origem"] = "ORCAMENTO"
        form = MovimentacaoSaidaForm(dados_post)
        if not form.is_valid():
            return self._render(request, form)
        dados = form.cleaned_data
        try:
            RegistrarOrcamentoService.executar_varios(
                itens=[{
                    "sku": dados["sku"],
                    "quantidade": dados["quantidade"],
                    "preco_unitario": dados.get("preco_unitario"),
                }],
                deposito=dados["deposito"],
                usuario=request.user,
                parceiro=dados.get("parceiro"),
                documento=dados.get("documento") or "",
                observacao=dados.get("observacao") or "",
                forma_pagamento=dados.get("forma_pagamento"),
                prazo_pagamento=dados.get("prazo_pagamento") or "",
            )
        except EstoqueError as erro:
            form.add_error(None, str(erro))
            return self._render(request, form)
        messages.success(request, "Orçamento criado sem movimentar o estoque.")
        return redirect("pedidos")

    def _render(self, request, form):
        return render(request, self.template_name, {
            "form": form,
            "titulo": "Novo orçamento",
        })


class EfetivarOrcamentoView(LoginRequiredMixin, View):
    template_name = "main/orcamento_efetivar.html"

    def get_pedido(self, pk):
        return get_object_or_404(Pedido, pk=pk)

    def get_context(self, pedido):
        from main.views.services.calcular_saldo_service import CalcularSaldoService

        itens = list(pedido.itens.select_related("sku", "sku__produto", "parceiro"))
        linhas = [
            {
                "item": item,
                "saldo": CalcularSaldoService.executar(
                    sku=item.sku, deposito=pedido.deposito,
                ),
            }
            for item in itens
        ]
        clientes = list(dict.fromkeys(
            item.parceiro for item in itens if item.parceiro_id
        ))
        return {
            "pedido": pedido,
            "linhas": linhas,
            "clientes_do_pedido": clientes,
            "insuficiente": any(
                linha["saldo"] < linha["item"].quantidade for linha in linhas
            ),
        }

    def get(self, request, pk):
        pedido = self.get_pedido(pk)
        if not pedido.eh_orcamento:
            messages.info(request, "Este registro já não é um orçamento.")
            return redirect("pedidos")
        return render(request, self.template_name, self.get_context(pedido))

    def post(self, request, pk):
        from main.views.services.efetivar_orcamento_service import EfetivarOrcamentoService

        pedido = self.get_pedido(pk)
        if not pedido.eh_orcamento:
            messages.info(request, "Este registro já não é um orçamento.")
            return redirect("pedidos")
        try:
            EfetivarOrcamentoService.executar(pedido, usuario=request.user)
        except EstoqueError as erro:
            messages.error(request, str(erro))
            return redirect("orcamento_efetivar", pk=pedido.pk)
        messages.success(request, "Orçamento efetivado como pedido.")
        return redirect("pedidos")


class PedidoDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from main.models import Pedido
        from main.views.services.excluir_pedido_service import ExcluirPedidoService

        pedido = get_object_or_404(Pedido, pk=pk)
        ExcluirPedidoService.executar(pedido)
        messages.success(request, "Pedido excluído com sucesso.")
        return redirect("pedidos")


class OrcamentosDeleteView(LoginRequiredMixin, View):
    template_name = "main/cadastro_confirm_delete.html"

    def get(self, request):
        quantidade = Pedido.objects.filter(origem="ORCAMENTO").count()
        return render(request, self.template_name, {
            "titulo": "Excluir todos os orçamentos",
            "url_lista": "pedidos",
            "texto_confirmacao": f"Excluir {quantidade} orçamento(s)? Os pedidos reais serão preservados.",
            "rotulo_acao": "Excluir orçamentos",
        })

    def post(self, request):
        from main.views.services.excluir_pedido_service import ExcluirPedidoService

        with transaction.atomic():
            orcamentos = list(Pedido.objects.filter(origem="ORCAMENTO"))
            for pedido in orcamentos:
                ExcluirPedidoService.executar(pedido)
        messages.success(request, f"{len(orcamentos)} orçamento(s) excluído(s).")
        return redirect("pedidos")


class PedidoUpdateView(LoginRequiredMixin, View):
    """Endpoint de edição básica, com itens enviados em campos numerados."""

    template_name = "main/pedido_editar.html"

    def get_pedido(self, pk):
        return get_object_or_404(Pedido, pk=pk)

    def get(self, request, pk):
        pedido = self.get_pedido(pk)
        return redirect("pedidos") if not pedido.itens.exists() else self._render(request, pedido)

    def post(self, request, pk):
        from main.views.services.editar_pedido_service import EditarPedidoService

        pedido = self.get_pedido(pk)
        deposito = Deposito.objects.filter(pk=request.POST.get("deposito")).first()
        if deposito is None:
            messages.error(request, "Selecione um depósito válido.")
            return self._render(request, pedido)
        dados_post = request.POST.copy()
        dados_post["origem"] = "ORCAMENTO"
        itens = _itens_pedido_post(dados_post, pedido=pedido)
        if not itens:
            messages.error(request, "O pedido deve ter pelo menos um item válido.")
            return self._render(request, pedido)
        dados = {
            "deposito": deposito,
            "parceiro": Parceiro.objects.filter(pk=request.POST.get("parceiro")).first(),
            "documento": request.POST.get("documento", ""),
            "observacao": request.POST.get("observacao", ""),
            "forma_pagamento": request.POST.get("forma_pagamento") or None,
            "prazo_pagamento": request.POST.get("prazo_pagamento", ""),
            "status_pedido": request.POST.get("status_pedido") or None,
            "reservado": request.POST.get("reservado") == "on",
        }
        try:
            EditarPedidoService.executar(
                pedido=pedido, dados=dados, itens=itens, usuario=request.user,
            )
        except EstoqueError as erro:
            messages.error(request, str(erro))
            return self._render(request, pedido)
        messages.success(request, "Pedido atualizado com sucesso.")
        return redirect("pedidos")

    def _render(self, request, pedido):
        from main.forms import PedidoEdicaoForm

        form = PedidoEdicaoForm(pedido=pedido)
        return render(request, self.template_name, {
            "pedido": pedido,
            "form": form,
            "eh_orcamento": pedido.eh_orcamento,
            "pode_reservar": not pedido.eh_orcamento and pedido.origem == "VENDA",
            "clientes_opcoes": [
                {"pk": cliente.pk, "rotulo": str(cliente)}
                for cliente in Parceiro.objects.filter(
                    tipo__in=("CLIENTE", "AMBOS")
                ).order_by("razao_social")
            ],
            "skus_opcoes": [
                {"pk": sku.pk, "rotulo": _rotulo_sku(sku)}
                for sku in SKU.objects.select_related("produto").order_by(
                    "produto__nome", "codigo"
                )
            ],
        })


class LimparSaldosClientesView(LoginRequiredMixin, View):
    template_name = "main/cadastro_confirm_delete.html"

    def get_queryset(self):
        return Movimentacao.objects.filter(
            tipo="ENTRADA", origem="PRODUCAO", parceiro__isnull=False,
        )

    def get(self, request):
        quantidade = self.get_queryset().count()
        return render(request, self.template_name, {
            "titulo": "Desvincular cliente das produções",
            "url_lista": "estoque",
            "texto_confirmacao": f"Desvincular cliente de {quantidade} entrada(s) de produção? O estoque não será alterado.",
            "rotulo_acao": "Desvincular clientes",
        })

    def post(self, request):
        with transaction.atomic():
            atualizadas = self.get_queryset().update(parceiro=None)
        messages.success(request, f"Cliente desvinculado de {atualizadas} entrada(s) de produção.")
        return redirect("estoque")


class DesvincularClienteEntradaView(LoginRequiredMixin, View):
    def post(self, request, pk):
        movimentacao = get_object_or_404(Movimentacao, pk=pk)
        if movimentacao.tipo != "ENTRADA" or movimentacao.origem != "PRODUCAO":
            messages.error(request, "Só é possível desvincular o cliente de uma entrada de produção.")
            return redirect("estoque")
        if movimentacao.parceiro_id:
            movimentacao.parceiro = None
            movimentacao.save(update_fields=["parceiro", "atualizado_em"])
            messages.success(request, "Cliente desvinculado da entrada. O estoque não foi alterado.")
        return redirect("estoque")


def _itens_pedido_post(dados, pedido=None):
    """Extrai linhas tradicionais ou dinamicamente numeradas do POST."""
    import re

    itens = []
    campos = set(dados.keys())
    if "sku" in campos:
        indices = [None]
        indices += sorted(
            int(match.group(1)) for nome in campos
            if (match := re.fullmatch(r"sku_(\d+)", nome))
        )
    else:
        indices = sorted(
            int(match.group(1)) for nome in campos
            if (match := re.fullmatch(r"sku_(\d+)", nome))
        )

    for indice in indices:
        sufixo = "" if indice is None else f"_{indice}"
        sku_id = dados.get(f"sku{sufixo}")
        quantidade_raw = dados.get(f"quantidade{sufixo}")
        if not sku_id and not quantidade_raw:
            continue
        sku = SKU.objects.filter(pk=sku_id).first()
        if sku is None or not quantidade_raw:
            raise EstoqueError("Informe um SKU e a quantidade para cada item.")
        try:
            quantidade = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01")).clean(quantidade_raw)
            preco_raw = dados.get(f"preco_unitario{sufixo}")
            preco = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False).clean(preco_raw) if preco_raw else None
        except ValidationError as erro:
            raise EstoqueError("Quantidade ou preço inválido.") from erro
        itens.append({"sku": sku, "quantidade": quantidade, "preco_unitario": preco})
    return itens