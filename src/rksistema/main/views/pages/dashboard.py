from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView

from main.models import (
    Categoria,
    UnidadeMedida,
    Produto,
    SKU,
    Parceiro,
    Deposito,
    Movimentacao,
    Pedido,
    SaldoDevedor,
)
from main.views.pages.estoque import _calcular_saldos


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "main/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Filtros opcionais: cliente, produto e SKU (faturamento e movimentações)
        parceiro_filtro = None
        produto_filtro = None
        sku_filtro = None

        parceiro_id = self.request.GET.get("parceiro")
        if parceiro_id and parceiro_id.isdigit():
            parceiro_filtro = Parceiro.objects.filter(pk=parceiro_id).first()

        produto_id = self.request.GET.get("produto")
        if produto_id and produto_id.isdigit():
            produto_filtro = Produto.objects.filter(pk=produto_id).first()

        sku_id = self.request.GET.get("sku")
        if sku_id and sku_id.isdigit():
            sku_filtro = SKU.objects.select_related("produto").filter(pk=sku_id).first()

        ctx["parceiros"] = Parceiro.objects.all().order_by("razao_social")
        ctx["parceiro_filtro"] = parceiro_filtro
        ctx["produtos"] = Produto.objects.all().order_by("nome")
        ctx["produto_filtro"] = produto_filtro
        # SKUs inteligentes: se um produto foi escolhido, lista só os dele
        skus_qs = SKU.objects.select_related("produto").order_by("produto__nome", "codigo")
        if produto_filtro:
            skus_qs = skus_qs.filter(produto=produto_filtro)
        ctx["skus"] = skus_qs
        ctx["sku_filtro"] = sku_filtro

        # Um pedido com MÚLTIPLOS SKUs conta como uma única movimentação de
        # estoque no dashboard (agrupa e não polui as métricas). Orçamentos
        # (tipo ORCAMENTO) não movimentam estoque e ficam de fora.
        total_movimentacoes = Movimentacao.objects.exclude(tipo="ORCAMENTO").count()
        excedentes = sum(
            (num_itens - 1)
            for num_itens in Pedido.objects.exclude(origem="ORCAMENTO")
            .annotate(num_itens=Count("itens"))
            .filter(num_itens__gte=2)
            .values_list("num_itens", flat=True)
        )

        ctx["totais"] = {
            "categorias": Categoria.objects.count(),
            "unidades": UnidadeMedida.objects.count(),
            "produtos": Produto.objects.count(),
            "skus": SKU.objects.count(),
            "parceiros": Parceiro.objects.count(),
            "depositos": Deposito.objects.count(),
            "movimentacoes": total_movimentacoes - excedentes,
            "saldo_devedor": SaldoDevedor.saldo_atual(),
        }

        movs = (
            Movimentacao.objects.select_related("sku", "sku__produto", "deposito", "parceiro", "usuario")
            .exclude(tipo="ORCAMENTO")
        )
        if parceiro_filtro:
            movs = movs.filter(parceiro=parceiro_filtro)
        if produto_filtro:
            movs = movs.filter(sku__produto=produto_filtro)
        if sku_filtro:
            movs = movs.filter(sku=sku_filtro)
        # Pedidos com múltiplos SKUs viram uma única linha consolidada em
        # "Últimas movimentações" (não poluem o dashboard).
        recentes = list(movs.order_by("-data_movimentacao")[:80])
        pedidos_multi = set(
            Pedido.objects.annotate(num_itens=Count("itens"))
            .filter(
                num_itens__gte=2,
                id__in=[m.pedido_id for m in recentes if m.pedido_id],
            )
            .values_list("id", flat=True)
        )

        agrupados = defaultdict(list)
        for m in recentes:
            if m.pedido_id and m.pedido_id in pedidos_multi:
                agrupados[m.pedido_id].append(m)

        linhas = [
            {"eh_grupo": False, "movimentacao": m, "data": m.data_movimentacao}
            for m in recentes
            if m.pedido_id not in agrupados
        ]
        for pedido_id, itens in agrupados.items():
            primeiro = itens[0]
            # Todos os clientes do pedido (um mesmo pedido pode reunir
            # vários clientes), na ordem em que aparecem nos itens.
            clientes_grupo = list(
                dict.fromkeys(i.parceiro for i in itens if i.parceiro_id)
            )
            linhas.append(
                {
                    "eh_grupo": True,
                    "pedido_id": pedido_id,
                    "num_skus": len(itens),
                    "data": primeiro.data_movimentacao,
                    "deposito": primeiro.deposito,
                    "parceiro": primeiro.parceiro,
                    "clientes": clientes_grupo,
                    "quantidade_total": sum(
                        (i.quantidade for i in itens), Decimal("0")
                    ),
                    "origem_display": primeiro.get_origem_display(),
                    "item_pdf": primeiro,
                }
            )

        linhas.sort(key=lambda linha: linha["data"], reverse=True)
        ctx["movimentacoes_recentes"] = linhas[:8]

        ctx["estoque_baixo"], ctx["valor_custo"], ctx["valor_venda"] = self._resumo_estoque()
        ctx["financeiro"], ctx["periodo_dias"] = self._resumo_financeiro(
            parceiro=parceiro_filtro,
            produto=produto_filtro,
            sku=sku_filtro,
        )
        return ctx

    # ------------------------------------------------------------------
    # Métricas financeiras: faturamento, lucro bruto e margem
    #
    # O faturamento de cada saída usa o preço NEGOCIADO na movimentação
    # (preco_unitario) quando informado; senão, cai para o preco_venda
    # ATUAL do SKU. O custo usa o preco_custo atual do SKU.
    # ------------------------------------------------------------------
    def _resumo_financeiro(self, parceiro=None, produto=None, sku=None):
        periodo_raw = self.request.GET.get("periodo", "all")
        if periodo_raw == "all":
            dias = 0
        else:
            try:
                dias = int(periodo_raw)
            except (TypeError, ValueError):
                dias = 0

        qs = Movimentacao.objects.filter(tipo="SAIDA", origem="VENDA")
        if parceiro:
            qs = qs.filter(parceiro=parceiro)
        if produto:
            qs = qs.filter(sku__produto=produto)
        if sku:
            qs = qs.filter(sku=sku)
        if dias:
            qs = qs.filter(
                data_movimentacao__gte=timezone.now() - timedelta(days=dias)
            )

        qs = qs.annotate(
            valor_venda=ExpressionWrapper(
                Coalesce(F("preco_unitario"), F("sku__preco_venda"), Value(0)) * F("quantidade"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            custo_venda=ExpressionWrapper(
                Coalesce(F("sku__preco_custo"), Value(0)) * F("quantidade"),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
        )
        agregado = qs.aggregate(
            faturamento=Sum("valor_venda"),
            custo=Sum("custo_venda"),
        )

        # Nº de PEDIDOS (tabela Pedido), não de movimentações: cada pedido
        # conta UMA vez, mesmo com vários SKUs. Saídas avulsas sem pedido não
        # contam (continuam valendo no faturamento). Orçamentos ficam de fora.
        pedidos_qs = Pedido.objects.exclude(origem="ORCAMENTO")
        if parceiro:
            # Pedido multi-cliente: conta pelo cliente principal OU por
            # qualquer cliente atribuído aos seus itens.
            pedidos_qs = pedidos_qs.filter(
                Q(parceiro=parceiro) | Q(itens__parceiro=parceiro)
            )
        if produto:
            pedidos_qs = pedidos_qs.filter(itens__sku__produto=produto)
        if sku:
            pedidos_qs = pedidos_qs.filter(itens__sku=sku)
        if dias:
            pedidos_qs = pedidos_qs.filter(
                criado_em__gte=timezone.now() - timedelta(days=dias)
            )
        num_pedidos = pedidos_qs.distinct().count()
        pedidos_faturados = pedidos_qs.filter(status_pedido__iexact="FATURADO").distinct()
        
        pedidos_faturados_soma = (
            Movimentacao.objects.filter(tipo="SAIDA", pedido__in=pedidos_faturados)
            .annotate(
                valor_venda=ExpressionWrapper(
                    Coalesce(F("preco_unitario"), F("sku__preco_venda"), Value(0)) * F("quantidade"),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
                custo_venda=ExpressionWrapper(
                    Coalesce(F("sku__preco_custo"), Value(0)) * F("quantidade"),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
            )
            .aggregate(
                faturamento=Sum("valor_venda"),
                custo=Sum("custo_venda"),
            )
        )
      
        faturamento = agregado["faturamento"] or Decimal("0")
        custo = agregado["custo"] or Decimal("0")
        lucro = faturamento - custo
        
        # Ajuste para calcular o lucro real dos pedidos faturados
        faturamento_fat = pedidos_faturados_soma["faturamento"] or Decimal("0")
        custo_fat = pedidos_faturados_soma["custo"] or Decimal("0")
        lucro_faturado = faturamento_fat - custo_fat
        
        margem = (lucro * Decimal("100") / faturamento) if faturamento else Decimal("0")
    
        return (
            {
                "faturamento": faturamento,
                "lucro": lucro,
                "lucro_faturado": lucro_faturado,
                "margem": margem,
                "num_pedidos": num_pedidos,
                # Compatibilidade: o card usa num_pedidos.
                "num_vendas": num_pedidos,
            },
            dias,
        )

    def _resumo_estoque(self):
        saldos = _calcular_saldos()
        skus_ativos = {
            sku.pk: sku
            for sku in SKU.objects.select_related("produto").filter(ativo=True)
        }

        estoque_baixo = []
        valor_custo = Decimal("0")
        valor_venda = Decimal("0")

        for sku_id, sku in skus_ativos.items():
            saldo = saldos.get(sku_id, Decimal("0"))
            if saldo <= sku.estoque_minimo:
                estoque_baixo.append(
                    {
                        "produto": sku.produto.nome,
                        "tipo": sku.produto.get_tipo_produto_display(),
                        "codigo": sku.codigo,
                        "saldo": saldo,
                        "estoque_minimo": sku.estoque_minimo,
                    }
                )
            if sku.preco_custo is not None:
                valor_custo += saldo * sku.preco_custo
            if sku.preco_venda is not None:
                valor_venda += saldo * sku.preco_venda

        return estoque_baixo, valor_custo, valor_venda