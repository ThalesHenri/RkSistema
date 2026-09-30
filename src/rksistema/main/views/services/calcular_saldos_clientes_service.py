from collections import defaultdict
from decimal import Decimal

from main.models import AjusteSaldoCliente, Movimentacao


class CalcularSaldosClientesService:
    """Calcula os saldos destinados, incluindo ajustes manuais auditados."""

    @staticmethod
    def executar(*, deposito_id=None):
        grupos = {}
        entradas = Movimentacao.objects.filter(
            tipo="ENTRADA",
            origem="PRODUCAO",
            parceiro__tipo__in=("CLIENTE", "AMBOS"),
        ).select_related("parceiro", "sku", "sku__produto")
        if deposito_id:
            entradas = entradas.filter(deposito_id=deposito_id)

        for entrada in entradas.order_by("data_movimentacao", "pk"):
            chave = (entrada.parceiro_id, entrada.sku_id)
            if chave not in grupos:
                grupos[chave] = {
                    "cliente_obj": entrada.parceiro,
                    "sku": entrada.sku,
                    "saldo": Decimal("0"),
                    "entradas": [],
                }
            grupos[chave]["saldo"] += entrada.quantidade
            grupos[chave]["entradas"].append(entrada)

        reservas = Movimentacao.objects.filter(
            tipo="SAIDA",
            origem="VENDA",
            pedido__reservado=True,
            parceiro__tipo__in=("CLIENTE", "AMBOS"),
        ).values_list("parceiro_id", "sku_id", "quantidade")
        if deposito_id:
            reservas = reservas.filter(deposito_id=deposito_id)

        for parceiro_id, sku_id, quantidade in reservas:
            item = grupos.get((parceiro_id, sku_id))
            if item:
                item["saldo"] -= quantidade

        ajustes = AjusteSaldoCliente.objects.select_related("parceiro", "sku", "sku__produto")
        if deposito_id:
            ajustes = ajustes.filter(deposito_id=deposito_id)
        for ajuste in ajustes:
            item = grupos.get((ajuste.parceiro_id, ajuste.sku_id))
            if item:
                item["saldo"] += ajuste.delta

        por_cliente = defaultdict(list)
        for item in grupos.values():
            por_cliente[item["cliente_obj"]].append(
                {
                    "sku": item["sku"],
                    "saldo": item["saldo"],
                    "negativo": item["saldo"] < 0,
                    "entradas": item["entradas"],
                }
            )

        return [
            {
                "cliente": str(cliente),
                "cliente_obj": cliente,
                "itens": sorted(
                    itens,
                    key=lambda item: (
                        item["sku"].produto.nome.lower(), item["sku"].codigo.lower()
                    ),
                ),
            }
            for cliente, itens in sorted(
                por_cliente.items(), key=lambda par: str(par[0]).lower()
            )
        ]

    @staticmethod
    def saldo_atual(*, parceiro_id, sku_id, deposito_id=None):
        for grupo in CalcularSaldosClientesService.executar(deposito_id=deposito_id):
            if grupo["cliente_obj"].pk != parceiro_id:
                continue
            for item in grupo["itens"]:
                if item["sku"].pk == sku_id:
                    return item["saldo"]
        return None