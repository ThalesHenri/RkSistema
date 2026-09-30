from django.db import transaction

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from main.models.movimentacao import Movimentacao
from main.views.serializers.movimentacao_serializer import MovimentacaoSerializer
from main.views.serializers.registrar_entrada_serializer import RegistrarEntradaSerializer
from main.views.serializers.registrar_saida_serializer import RegistrarSaidaSerializer
from main.views.serializers.registrar_producao_serializer import RegistrarProducaoSerializer
from main.views.serializers.atualizar_preco_status_serializer import AtualizarPrecoStatusSerializer
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_saida_service import RegistrarSaidaService
from main.views.services.registrar_producao_service import RegistrarProducaoService
from main.views.services.estoque_error import EstoqueError


class MovimentacaoViewSet(ReadOnlyModelViewSet):
    """
    Listagem/detalhe padrão (herdados do ReadOnlyModelViewSet) + actions
    customizadas registradas automaticamente pelo DefaultRouter:
      POST /movimentacoes/entrada/
      POST /movimentacoes/saida/
      POST /movimentacoes/producao/
    A criação em si nunca é genérica — sempre passa por um dos services.
    """

    queryset = Movimentacao.objects.all()
    serializer_class = MovimentacaoSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def entrada(self, request):
        entrada = RegistrarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        usuario = request.user if request.user.is_authenticated else None

        try:
            movimentacao = RegistrarEntradaService.executar(
                sku=dados["sku"],
                deposito=dados["deposito"],
                quantidade=dados["quantidade"],
                origem=dados["origem"],
                usuario=usuario,
                parceiro=dados.get("parceiro"),
                documento=dados.get("documento", ""),
                observacao=dados.get("observacao", ""),
            )
        except EstoqueError as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MovimentacaoSerializer(movimentacao).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def saida(self, request):
        saida = RegistrarSaidaSerializer(data=request.data)
        saida.is_valid(raise_exception=True)
        dados = saida.validated_data
        usuario = request.user if request.user.is_authenticated else None

        try:
            if dados.get("itens"):
                movimentacoes = RegistrarSaidaService.executar_varios(
                    itens=dados["itens"], deposito=dados["deposito"],
                    origem=dados["origem"], usuario=usuario,
                    parceiro=dados.get("parceiro"), documento=dados.get("documento", ""),
                    observacao=dados.get("observacao", ""),
                    forma_pagamento=dados.get("forma_pagamento"),
                    prazo_pagamento=dados.get("prazo_pagamento", ""),
                )
            else:
                movimentacoes = [RegistrarSaidaService.executar(
                    sku=dados["sku"], deposito=dados["deposito"],
                    quantidade=dados["quantidade"], origem=dados["origem"],
                    usuario=usuario, parceiro=dados.get("parceiro"),
                    documento=dados.get("documento", ""), observacao=dados.get("observacao", ""),
                    preco_unitario=dados.get("preco_unitario"),
                    forma_pagamento=dados.get("forma_pagamento"),
                    prazo_pagamento=dados.get("prazo_pagamento", ""),
                )]
        except EstoqueError as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_400_BAD_REQUEST)

        if dados.get("itens"):
            resposta = MovimentacaoSerializer(movimentacoes, many=True).data
        else:
            resposta = MovimentacaoSerializer(movimentacoes[0]).data
        return Response(resposta, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="preco-status")
    def preco_status(self, request, pk=None):
        """Edita preço, status, forma de pagamento e/ou prazo de uma saída."""
        movimentacao = self.get_object()
        if not movimentacao.eh_saida:
            return Response(
                {"detail": "Preço, status e pagamento só se aplicam a saídas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        atualizacao = AtualizarPrecoStatusSerializer(data=request.data)
        atualizacao.is_valid(raise_exception=True)
        dados = atualizacao.validated_data

        if "preco_unitario" in dados:
            movimentacao.preco_unitario = dados["preco_unitario"]
        if "status_pedido" in dados:
            movimentacao.status_pedido = dados["status_pedido"]
        if "forma_pagamento" in dados:
            movimentacao.forma_pagamento = dados["forma_pagamento"] or None
        if "prazo_pagamento" in dados:
            movimentacao.prazo_pagamento = dados["prazo_pagamento"] or ""
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
            movimentacao.save(update_fields=[
                "preco_unitario", "status_pedido", "forma_pagamento",
                "prazo_pagamento", "atualizado_em",
            ])

        return Response(MovimentacaoSerializer(movimentacao).data)

    @action(detail=False, methods=["post"])
    def producao(self, request):
        """Registra produção: saída da matéria-prima + entrada do produto acabado."""
        producao = RegistrarProducaoSerializer(data=request.data)
        producao.is_valid(raise_exception=True)
        dados = producao.validated_data
        usuario = request.user if request.user.is_authenticated else None

        try:
            resultado = RegistrarProducaoService.executar(
                materia_prima=dados["materia_prima"],
                quantidade_materia_prima=dados["quantidade_materia_prima"],
                produto_acabado=dados["produto_acabado"],
                quantidade_produzida=dados["quantidade_produzida"],
                deposito=dados["deposito"],
                usuario=usuario,
                documento=dados.get("documento", ""),
                observacao=dados.get("observacao", ""),
            )
        except EstoqueError as erro:
            return Response({"detail": str(erro)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            [
                MovimentacaoSerializer(resultado["saida"]).data,
                MovimentacaoSerializer(resultado["entrada"]).data,
            ],
            status=status.HTTP_201_CREATED,
        )
