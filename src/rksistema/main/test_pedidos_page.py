"""Testes da página de lista de pedidos (aba "Pedidos").

Cobre:
- Exigir login;
- Renderizado com dados agregados (SKUs, quantidade e valor total);
- Filtros por cliente e por status do pedido;
- Presença do botão "Novo pedido".

Rode com:
    python manage.py test main.test_pedidos_page
"""

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
from main.views.services.registrar_saida_service import RegistrarSaidaService


class BasePedidosPageTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="teste", password="senha123"
        )
        cls.categoria = Categoria.objects.create(nome="Embalagens")
        cls.unidade = UnidadeMedida.objects.create(sigla="UN", nome="Unidade")
        cls.deposito = Deposito.objects.create(nome="Depósito Central")
        cls.cliente = Parceiro.objects.create(
            tipo="CLIENTE",
            razao_social="Cliente A LTDA",
            cnpj_cpf="12345678000199",
        )
        cls.cliente2 = Parceiro.objects.create(
            tipo="CLIENTE",
            razao_social="Cliente B LTDA",
            cnpj_cpf="98765432000188",
        )
        cls.produto = Produto.objects.create(
            nome="Caixa de Papelão",
            tipo_produto="PRODUTO_ACABADO",
            categoria=cls.categoria,
        )
        cls.skus = [
            SKU.objects.create(
                produto=cls.produto,
                codigo=f"CX-00{i}",
                unidade_medida=cls.unidade,
                preco_venda=Decimal("10.00"),
                preco_custo=Decimal("4.00"),
            )
            for i in range(1, 4)
        ]
        for sku in cls.skus:
            RegistrarEntradaService.executar(
                sku=sku,
                deposito=cls.deposito,
                quantidade=Decimal("100"),
                origem="COMPRA",
            )

    def _pedido(self, parceiro, quantidade="2", precos=None, **kwargs):
        """Cria um pedido com todos os SKUs e devolve o primeiro movimento."""
        itens = []
        for i, sku in enumerate(self.skus):
            preco = (precos or {}).get(i)
            item = {"sku": sku, "quantidade": Decimal(quantidade)}
            if preco is not None:
                item["preco_unitario"] = preco
            itens.append(item)
        RegistrarSaidaService.executar_varios(
            itens=itens, deposito=self.deposito, origem="VENDA",
            parceiro=parceiro, **kwargs,
        )
        return Movimentacao.objects.filter(tipo="SAIDA").order_by("id").last()


class PedidosPageTestCase(BasePedidosPageTestCase):
    def test_pedidos_requerem_login(self):
        resp = self.client.get(reverse("pedidos"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_pagina_renderiza_pedido_com_totais(self):
        self._pedido(self.cliente, precos={0: Decimal("10.00"), 1: Decimal("12.00"), 2: Decimal("13.00")})
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("pedidos"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Novo pedido")
        pedido = Pedido.objects.get()
        self.assertContains(resp, f"#{pedido.pk}")
        # 3 SKUs, 6 unidades no total e valor 70.00 (10 + 24 + 39)
        self.assertContains(resp, "3 SKUs")
        self.assertContains(resp, "6.00")
        self.assertContains(resp, "70.00")

    def test_valor_total_usa_preco_negociado_ou_preco_do_sku(self):
        # Só o primeiro item com preço negociado; o resto cai no preco_venda (10.00)
        # quantidade=2 por item => (7.50 + 10.00 + 10.00) * 2 = 55.00
        self._pedido(self.cliente, precos={0: Decimal("7.50")})
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("pedidos"))
        self.assertContains(resp, "55.00")

    def test_filtro_por_cliente(self):
        saida_a = self._pedido(self.cliente)
        saida_b = self._pedido(self.cliente2, quantidade="5")
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("pedidos"), {"parceiro": self.cliente.pk})
        self.assertContains(resp, f"#{saida_a.pedido.pk}")
        self.assertNotContains(resp, f"#{saida_b.pedido.pk}")

        resp = self.client.get(reverse("pedidos"), {"parceiro": self.cliente2.pk})
        self.assertContains(resp, f"#{saida_b.pedido.pk}")
        self.assertNotContains(resp, f"#{saida_a.pedido.pk}")

    def test_filtro_por_status(self):
        saida_pendente = self._pedido(self.cliente)  # VENDA => PENDENTE
        saida_faturada = self._pedido(self.cliente2)
        saida_faturada.pedido.itens.update(status_pedido="FATURADO")
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("pedidos"), {"status": "FATURADO"})
        self.assertContains(resp, f"#{saida_faturada.pedido.pk}")
        self.assertNotContains(resp, f"#{saida_pendente.pedido.pk}")

        resp = self.client.get(reverse("pedidos"), {"status": "PENDENTE"})
        self.assertContains(resp, f"#{saida_pendente.pedido.pk}")
        self.assertNotContains(resp, f"#{saida_faturada.pedido.pk}")

    def test_edicao_inline_atualiza_todos_os_itens(self):
        saida = self._pedido(self.cliente)
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("movimentacao_atualizar_preco_status", args=[saida.pk]),
            {
                "status_pedido": "ENTREGUE",
                "forma_pagamento": "PIX",
                "prazo_pagamento": "30 dias",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))

        itens = list(saida.pedido.itens.all())
        self.assertTrue(all(i.status_pedido == "ENTREGUE" for i in itens))
        self.assertTrue(all(i.forma_pagamento == "PIX" for i in itens))
        self.assertTrue(all(i.prazo_pagamento == "30 dias" for i in itens))
        saida.pedido.refresh_from_db()
        self.assertEqual(saida.pedido.status_pedido, "ENTREGUE")

    def test_edicao_individual_faturada_atualiza_lucro_no_dashboard(self):
        saida = self._pedido(self.cliente)
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("movimentacao_atualizar_preco_status", args=[saida.pk]),
            {"status_pedido": "FATURADO"},
        )

        self.assertRedirects(resp, reverse("pedidos"))
        saida.pedido.refresh_from_db()
        self.assertEqual(saida.pedido.status_pedido, "FATURADO")
        dashboard_resp = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_resp.status_code, 200)
        self.assertEqual(
            dashboard_resp.context_data["financeiro"]["lucro_faturado"],
            Decimal("36.00"),
        )

    def test_atualizacao_em_lote_muda_status_de_todos_os_pedidos_selecionados(self):
        pedido_a = self._pedido(self.cliente).pedido
        pedido_b = self._pedido(self.cliente2).pedido
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("pedidos_status_em_lote"),
            {
                "pedido_ids": [pedido_a.pk, pedido_b.pk],
                "status_pedido": "ENTREGUE",
            },
        )

        self.assertRedirects(resp, reverse("pedidos"))
        pedido_a.refresh_from_db()
        pedido_b.refresh_from_db()
        self.assertEqual(pedido_a.status_pedido, "ENTREGUE")
        self.assertEqual(pedido_b.status_pedido, "ENTREGUE")
        self.assertFalse(pedido_a.itens.exclude(status_pedido="ENTREGUE").exists())
        self.assertFalse(pedido_b.itens.exclude(status_pedido="ENTREGUE").exists())

    def test_atualizacao_em_lote_ignora_orcamento_e_rejeita_status_invalido(self):
        pedido = self._pedido(self.cliente).pedido
        from main.views.services.registrar_orcamento_service import RegistrarOrcamentoService

        RegistrarOrcamentoService.executar_varios(
            itens=[{"sku": self.skus[0], "quantidade": Decimal("1")}],
            deposito=self.deposito,
            parceiro=self.cliente,
        )
        orcamento = Pedido.objects.get(origem="ORCAMENTO")
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("pedidos_status_em_lote"),
            {
                "pedido_ids": [pedido.pk, orcamento.pk],
                "status_pedido": "NAO_EXISTE",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))
        pedido.refresh_from_db()
        orcamento.refresh_from_db()
        self.assertEqual(pedido.status_pedido, "PENDENTE")
        self.assertIsNone(orcamento.status_pedido)

        resp = self.client.post(
            reverse("pedidos_status_em_lote"),
            {"pedido_ids": [pedido.pk, orcamento.pk], "status_pedido": "FATURADO"},
        )
        self.assertRedirects(resp, reverse("pedidos"))
        pedido.refresh_from_db()
        orcamento.refresh_from_db()
        self.assertEqual(pedido.status_pedido, "FATURADO")
        self.assertIsNone(orcamento.status_pedido)