"""Testes da edição completa de pedidos (e orçamentos).

Cobre:
- Editar cabeçalho (cliente, documento, status...) e itens (SKU/quantidade/preço);
- Adicionar e remover itens com recálculo do saldo;
- Bloqueio quando faltar saldo;
- Orçamento pode ser editado sem validar saldo.

Rode com:
    python manage.py test main.test_pedido_edicao
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import (
    Categoria,
    Deposito,
    Parceiro,
    Pedido,
    Produto,
    SKU,
    UnidadeMedida,
)
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_orcamento_service import RegistrarOrcamentoService
from main.views.services.registrar_saida_service import RegistrarSaidaService


class BasePedidoEdicaoTestCase(TestCase):
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
        cls.cliente2 = Parceiro.objects.create(
            tipo="CLIENTE", razao_social="Cliente B LTDA", cnpj_cpf="98765432000188"
        )
        cls.produto = Produto.objects.create(
            nome="Caixa de Papelão",
            tipo_produto="PRODUTO_ACABADO",
            categoria=cls.categoria,
        )
        cls.skus = [
            SKU.objects.create(
                produto=cls.produto, codigo=f"CX-00{i}", unidade_medida=cls.unidade,
                preco_venda=Decimal("10.00"), preco_custo=Decimal("4.00"),
            )
            for i in range(1, 4)
        ]

    def _entrada(self, sku, quantidade="100"):
        return RegistrarEntradaService.executar(
            sku=sku, deposito=self.deposito,
            quantidade=Decimal(quantidade), origem="COMPRA",
        )

    def _entradas(self):
        for sku in self.skus:
            self._entrada(sku)

    def _pedido(self, itens):
        """itens: lista de (sku, quantidade[, preco])."""
        dados = []
        for item in itens:
            dados.append({
                "sku": item[0],
                "quantidade": Decimal(str(item[1])),
                "preco_unitario": item[2] if len(item) > 2 else None,
            })
        RegistrarSaidaService.executar_varios(
            itens=dados, deposito=self.deposito, origem="VENDA",
            parceiro=self.cliente, usuario=self.usuario,
        )
        return Pedido.objects.latest("id")

    def _saldo(self, sku):
        return CalcularSaldoService.executar(sku=sku, deposito=self.deposito)


class PedidoEdicaoTestCase(BasePedidoEdicaoTestCase):
    def test_pagina_editar_exige_login(self):
        self._entradas()
        pedido = self._pedido([(self.skus[0], 2)])
        resp = self.client.get(reverse("pedido_editar", args=[pedido.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_editar_cabecalho_e_itens_recalcula_saldo(self):
        self._entradas()
        pedido = self._pedido([(self.skus[0], 2), (self.skus[1], 2)])
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("pedido_editar", args=[pedido.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Salvar alterações")

        resp = self.client.post(
            reverse("pedido_editar", args=[pedido.pk]),
            {
                "deposito": self.deposito.pk,
                "parceiro": self.cliente2.pk,
                "documento": "PED-99",
                "status_pedido": "FATURADO",
                "forma_pagamento": "PIX",
                "prazo_pagamento": "15 dias",
                "observacao": "Alterado",
                "reservado": "on",
                "sku_1": self.skus[0].pk,
                "quantidade_1": "3",
                "preco_unitario_1": "20.00",
                "sku_2": self.skus[2].pk,
                "quantidade_2": "1",
                "preco_unitario_2": "",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))

        pedido.refresh_from_db()
        self.assertEqual(pedido.parceiro, self.cliente2)
        self.assertEqual(pedido.documento, "PED-99")
        self.assertEqual(pedido.status_pedido, "FATURADO")
        self.assertEqual(pedido.forma_pagamento, "PIX")
        self.assertEqual(pedido.prazo_pagamento, "15 dias")
        self.assertTrue(pedido.reservado)

        itens = {i.sku_id: i for i in pedido.itens.all()}
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[self.skus[0].pk].quantidade, Decimal("3"))
        self.assertEqual(itens[self.skus[0].pk].preco_unitario, Decimal("20.00"))
        self.assertEqual(itens[self.skus[2].pk].quantidade, Decimal("1"))
        # sku1: 100 - 3; sku2 voltou a 100 (saiu do pedido); sku3: 100 - 1.
        self.assertEqual(self._saldo(self.skus[0]), Decimal("97"))
        self.assertEqual(self._saldo(self.skus[1]), Decimal("100"))
        self.assertEqual(self._saldo(self.skus[2]), Decimal("99"))
