"""Testes das mudanças 1, 3 e 4:

- Pedido com N SKUs (sem limite fixo) e PREÇO UNITÁRIO INDIVIDUAL por item
  (RegistrarSaidaView / MovimentacaoSaidaForm);
- Código interno do SKU visível nos selects do formulário de saída;
- Dashboard agrupa pedido com múltiplos SKUs em uma única movimentação.

Rode com:
    python manage.py test main.test_pedido_dinamico
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


class BasePedidoDinamicoTestCase(TestCase):
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
                tamanho_capacidade=f"{20 + i}cm",
                cor="Azul" if i == 1 else "",
            )
            for i in range(1, 6)
        ]

    def _entrar(self, sku, quantidade="100"):
        RegistrarEntradaService.executar(
            sku=sku,
            deposito=self.deposito,
            quantidade=Decimal(quantidade),
            origem="COMPRA",
        )

    def _entradas_para_todos(self):
        for sku in self.skus:
            self._entrar(sku)


class RegistrarSaidaMultiplosItensTestCase(BasePedidoDinamicoTestCase):
    def test_saida_via_form_com_n_itens_e_precos_individuais(self):
        """Um pedido pode ter N SKUs, cada um com o seu preço unitário."""
        self._entradas_para_todos()
        self.client.force_login(self.usuario)

        dados = {
            "deposito": self.deposito.pk,
            "origem": "VENDA",
            "parceiro": self.cliente.pk,
            "sku": self.skus[0].pk,
            "quantidade": "1",
            "preco_unitario": "10.00",
        }
        # 4 linhas adicionais (5 SKUs no total), cada uma com preço próprio
        for i, sku in enumerate(self.skus[1:], start=2):
            dados[f"sku_{i}"] = sku.pk
            dados[f"quantidade_{i}"] = str(i)
            dados[f"preco_unitario_{i}"] = f"{10 + i}.50"

        resp = self.client.post(reverse("movimentacao_saida"), dados)
        self.assertRedirects(resp, reverse("movimentacoes"))

        saidas = Movimentacao.objects.filter(tipo="SAIDA").order_by("id")
        self.assertEqual(saidas.count(), 5)
        self.assertFalse(saidas.first().pedido.reservado)
        # todos os itens pertencem ao MESMO pedido
        pedidos = set(saidas.values_list("pedido_id", flat=True))
        self.assertEqual(len(pedidos), 1)

        precos = dict(saidas.values_list("sku_id", "preco_unitario"))
        self.assertEqual(precos[self.skus[0].pk], Decimal("10.00"))
        self.assertEqual(precos[self.skus[1].pk], Decimal("12.50"))
        self.assertEqual(precos[self.skus[2].pk], Decimal("13.50"))
        self.assertEqual(precos[self.skus[3].pk], Decimal("14.50"))
        self.assertEqual(precos[self.skus[4].pk], Decimal("15.50"))

    def test_saida_exibe_codigo_interno_nos_selects(self):
        """O código interno aparece nas opções de SKU (diferencia variações)."""
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacao_saida"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.skus[0].codigo)
        self.assertContains(resp, f"{self.produto.nome} — {self.skus[0].codigo}")
        self.assertContains(resp, str(self.skus[0]))
        self.assertIn(
            {"pk": self.skus[0].pk, "rotulo": str(self.skus[0])},
            resp.context_data["skus_opcoes"],
        )
        self.assertContains(resp, "pedido_form.js?v=20260928-2")

    def test_saida_com_reserva_explicita_grava_reserva_no_pedido(self):
        self._entradas_para_todos()
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "reservado": "on",
                "sku": self.skus[0].pk,
                "quantidade": "2",
            },
        )

        self.assertRedirects(resp, reverse("movimentacoes"))
        pedido = Pedido.objects.get()
        self.assertTrue(pedido.reservado)

    def test_saida_ignora_linhas_totalmente_vazias(self):
        """Linhas extras em branco não atrapalham o registro."""
        self._entradas_para_todos()
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "sku": self.skus[0].pk,
                "quantidade": "3",
                "preco_unitario": "",
                "sku_2": "",
                "quantidade_2": "",
                "preco_unitario_2": "",
            },
        )
        self.assertRedirects(resp, reverse("movimentacoes"))
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 1)

    def test_saida_rejeita_linha_parcialmente_preenchida(self):
        """SKU preenchido sem quantidade (ou vice-versa) gera erro."""
        self._entradas_para_todos()
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "sku": self.skus[0].pk,
                "quantidade": "3",
                "sku_2": self.skus[1].pk,
                "quantidade_2": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Informe a quantidade deste item")
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_pagina_saida_exibe_codigo_interno_nos_selects(self):
        """O código interno aparece nas opções de SKU (diferencia variações)."""
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacao_saida"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.skus[0].codigo)
        self.assertContains(resp, f"{self.produto.nome} — {self.skus[0].codigo}")
        self.assertContains(resp, "pedido_form.js?v=20260928-2")


class DashboardAgrupamentoTestCase(BasePedidoDinamicoTestCase):
    def test_dashboard_agrupa_pedido_com_multiplos_skus(self):
        """Pedido com vários SKUs conta como uma movimentação no dashboard."""
        for sku in self.skus[:3]:
            self._entrar(sku)
        RegistrarSaidaService.executar_varios(
            itens=[
                {"sku": self.skus[0], "quantidade": Decimal("1"), "preco_unitario": Decimal("10.00")},
                {"sku": self.skus[1], "quantidade": Decimal("2"), "preco_unitario": Decimal("12.00")},
                {"sku": self.skus[2], "quantidade": Decimal("3"), "preco_unitario": Decimal("13.00")},
            ],
            deposito=self.deposito,
            origem="VENDA",
            parceiro=self.cliente,
        )
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

        context = resp.context_data
        # 3 entradas (individuais) + 1 pedido consolidado => 4 linhas
        recentes = context["movimentacoes_recentes"]
        self.assertEqual(len(recentes), 4)
        grupos = [linha for linha in recentes if linha["eh_grupo"]]
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]["num_skus"], 3)
        self.assertEqual(grupos[0]["quantidade_total"], Decimal("6"))

        # 6 registros no total, mas o pedido multi-SKU conta como 1
        self.assertEqual(Movimentacao.objects.count(), 6)
        self.assertEqual(context["totais"]["movimentacoes"], 4)

    def test_dashboard_nao_agrupa_pedido_de_um_item(self):
        """Pedido com apenas um SKU continua aparecendo normalmente."""
        self._entrar(self.skus[0])
        RegistrarSaidaService.executar_varios(
            itens=[{"sku": self.skus[0], "quantidade": Decimal("2")}],
            deposito=self.deposito,
            origem="VENDA",
        )
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

        context = resp.context_data
        recentes = context["movimentacoes_recentes"]
        self.assertFalse(any(linha["eh_grupo"] for linha in recentes))
        # 1 entrada + 1 saída => 2 movimentações individuais
        self.assertEqual(context["totais"]["movimentacoes"], 2)