from django.db import transaction

from main.models.movimentacao import Movimentacao
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.estoque_error import EstoqueError


class RegistrarProducaoService:
    """Regra de negócio para registrar produção (matéria-prima → produto em estoque).

    Em uma única transação: dá baixa no estoque da matéria-prima (SAIDA,
    origem PRODUCAO) e soma no estoque do produto em estoque (ENTRADA, origem
    PRODUCAO). A entrada fica vinculada à saída (movimentacao_origem) para que
    a exclusão de uma produção remova o par juntos. Valida o saldo da
    matéria-prima antes de movimentar.
    """

    @staticmethod
    @transaction.atomic
    def executar(*, materia_prima, quantidade_materia_prima,
                 produto_acabado, quantidade_produzida, deposito,
                 usuario=None, documento="", observacao="", parceiro=None):
        if quantidade_materia_prima <= 0 or quantidade_produzida <= 0:
            raise EstoqueError("As quantidades devem ser maiores que zero.")

        if materia_prima.produto.tipo_produto != "MATERIA_PRIMA":
            raise EstoqueError(
                f'O SKU "{materia_prima}" não é uma matéria-prima.'
            )
        if produto_acabado.produto.tipo_produto != "PRODUTO_ACABADO":
            raise EstoqueError(
                f'O SKU "{produto_acabado}" não é um produto em estoque.'
            )
        if materia_prima.pk == produto_acabado.pk:
            raise EstoqueError(
                "A matéria-prima e o produto em estoque devem ser SKUs diferentes."
            )

        saldo_mp = CalcularSaldoService.executar(
            sku=materia_prima, deposito=deposito
        )
        if saldo_mp < quantidade_materia_prima:
            raise EstoqueError(
                f"Saldo insuficiente de matéria-prima: disponível {saldo_mp}, "
                f"consumo solicitado {quantidade_materia_prima}."
            )

        saida = Movimentacao.objects.create(
            sku=materia_prima,
            deposito=deposito,
            tipo="SAIDA",
            origem="PRODUCAO",
            quantidade=quantidade_materia_prima,
            usuario=usuario,
            documento=documento,
            observacao=observacao,
        )
        entrada = Movimentacao.objects.create(
            sku=produto_acabado,
            deposito=deposito,
            tipo="ENTRADA",
            origem="PRODUCAO",
            quantidade=quantidade_produzida,
            usuario=usuario,
            documento=documento,
            observacao=observacao,
            movimentacao_origem=saida,
            # Cliente ao qual este produto em estoque está destinado. Fica
            # gravado só na ENTRADA do produto (não na baixa da matéria-prima),
            # pois é o produto acabado que "pertence" ao cliente.
            parceiro=parceiro,
        )
        return {"saida": saida, "entrada": entrada}