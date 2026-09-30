"""Testes do nº de PEDIDOS exibido no dashboard (card de Faturamento).

O card conta registros da tabela `Pedido` (um pedido com N SKUs conta UMA vez);
saídas avulsas sem pedido e orçamentos NÃO contam — mas avulsas continuam
somando no faturamento.

Rode com:
    python manage.py test main.test_dashboard
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import (
    Categoria,
    Deposito,
    Movimentacao,
    Parceiro,
    Pedido,
    Produto,
    SKU,
    UnidadeMedida,
)
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_orcamento_service import RegistrarOrcamentoService
from main.views.services.registrar_saida_service import RegistrarSaidaService


class DashboardNumPedidosTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="teste", password="senha123"
        )
        cls.categoria = Categoria.objects.create(nome="Embalagens")
        cls.unidade = UnidadeMedida.objects.create(sigla="UN", nome="Unidade")
        cls.deposito = Deposito.objects.create(nome="Depósito Central")
        cls.cliente = Parceiro.objects.create(
            tipo="CLIENTE", razao_social="Cliente A LTDA", cnpj_cpf="12345678000199"
        )
        cls.produto = Produto.objects.create(
            nome="Caixa de Papelão",
            tipo_produto="PRODUTO_ACABADO",
            categoria=cls.categoria,
        )
        cls.sku = SKU.objects.create(
            produto=cls.produto,
            codigo="CX-302015",
            unidade_medida=cls.unidade,
            preco_venda=Decimal("10.00"),
            preco_custo=Decimal("4.00"),
        )
        cls.produto2 = Produto.objects.create(
            nome="Saco Plástico",
            tipo_produto="PRODUTO_ACABADO",
            categoria=cls.categoria,
        )
        cls.sku2 = SKU.objects.create(
            produto=cls.produto2,
            codigo="SP-001",
            unidade_medida=cls.unidade,
            preco_venda=Decimal("5.00"),
            preco_custo=Decimal("2.00"),
        )

    def setUp(self):
        for sku in (self.sku, self.sku2):
            RegistrarEntradaService.executar(
                sku=sku,
                deposito=self.deposito,
                quantidade=Decimal("100"),
                origem="COMPRA",
                usuario=self.usuario,
            )
        self.client.force_login(self.usuario)

    def _pedido(self, itens):
        """Cria um Pedido real (saída com N SKUs)."""
        movimentacoes = RegistrarSaidaService.executar_varios(
            itens=itens,
            deposito=self.deposito,
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )
        return movimentacoes[0].pedido

    def test_pedido_com_dois_skus_conta_apenas_um(self):
        self._pedido(
            [
                {"sku": self.sku, "quantidade": Decimal("2")},
                {"sku": self.sku2, "quantidade": Decimal("3")},
            ]
        )
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 2)
        self.assertEqual(self._financeiro()["num_pedidos"], 1)

    def test_dois_pedidos_contam_dois(self):
        self._pedido([{"sku": self.sku, "quantidade": Decimal("2")}])
        self._pedido([{"sku": self.sku2, "quantidade": Decimal("1")}])
        self.assertEqual(self._financeiro()["num_pedidos"], 2)

    def test_saida_avulsa_sem_pedido_nao_conta_mas_entra_no_faturamento(self):
        RegistrarSaidaService.executar(
            sku=self.sku,
            deposito=self.deposito,
            quantidade=Decimal("5"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
            preco_unitario=Decimal("8.00"),
        )
        financeiro = self._financeiro()
        self.assertEqual(financeiro["num_pedidos"], 0)
        # A venda avulsa continua valendo como dinheiro recebido.
        self.assertEqual(financeiro["faturamento"], Decimal("40.00"))

    def test_orcamento_nao_conta_como_pedido(self):
        RegistrarOrcamentoService.executar_varios(
            itens=[{"sku": self.sku, "quantidade": Decimal("10")}],
            deposito=self.deposito,
            usuario=self.usuario,
            parceiro=self.cliente,
        )
        self.assertEqual(Pedido.objects.count(), 1)  # só o orçamento
        self.assertEqual(self._financeiro()["num_pedidos"], 0)

    def test_filtro_por_produto_e_sku(self):
        self._pedido(
            [
                {"sku": self.sku, "quantidade": Decimal("2")},
                {"sku": self.sku2, "quantidade": Decimal("3")},
            ]
        )
        # O pedido contém os dois SKUs: ambos os filtros devem encontrá-lo.
        self.assertEqual(self._financeiro(produto=self.produto.pk)["num_pedidos"], 1)
        self.assertEqual(self._financeiro(produto=self.produto2.pk)["num_pedidos"], 1)
        self.assertEqual(self._financeiro(sku=self.sku.pk)["num_pedidos"], 1)
        self.assertEqual(self._financeiro(sku=self.sku2.pk)["num_pedidos"], 1)
        # SKU/produto que não estão em nenhum pedido → 0.
        produto3 = Produto.objects.create(
            nome="Rolo de Fita",
            tipo_produto="PRODUTO_ACABADO",
            categoria=self.categoria,
        )
        sku3 = SKU.objects.create(
            produto=produto3,
            codigo="RF-001",
            unidade_medida=self.unidade,
            preco_venda=Decimal("3.00"),
        )
        self.assertEqual(self._financeiro(produto=produto3.pk)["num_pedidos"], 0)
        self.assertEqual(self._financeiro(sku=sku3.pk)["num_pedidos"], 0)

    def test_filtro_por_parceiro(self):
        self._pedido([{"sku": self.sku, "quantidade": Decimal("2")}])
        outro = Parceiro.objects.create(
            tipo="CLIENTE", razao_social="Cliente B LTDA", cnpj_cpf="98765432000188"
        )
        self.assertEqual(self._financeiro(parceiro=self.cliente.pk)["num_pedidos"], 1)
        self.assertEqual(self._financeiro(parceiro=outro.pk)["num_pedidos"], 0)

    def test_filtro_por_periodo(self):
        pedido = self._pedido([{"sku": self.sku, "quantidade": Decimal("2")}])
        # criado_em é auto_now_add; deslocamos via update para sair dos 7 dias.
        Pedido.objects.filter(pk=pedido.pk).update(
            criado_em=pedido.criado_em - timedelta(days=30)
        )
        self.assertEqual(self._financeiro(periodo="7")["num_pedidos"], 0)
        self.assertEqual(self._financeiro(periodo="all")["num_pedidos"], 1)

    def test_exige_login(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)


    def _financeiro(self, **params):
        resp = self.client.get(reverse("dashboard"), params)
        self.assertEqual(resp.status_code, 200)
        return resp.context_data["financeiro"]
