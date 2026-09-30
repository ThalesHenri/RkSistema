"""Testes do pedido com VÁRIOS CLIENTES (um pedido, vários clientes).

Cobre:
- Página de saída: a opção "Tem clientes adicionais" e o modelo de select de
  cliente usado pelo JS para montar os blocos;
- Criação: cada bloco tem seu cliente e seus itens, e o cliente fica gravado em
  ``Movimentacao.parceiro`` (é o que os filtros de faturamento usam);
- A opção é a fonte da verdade: desmarcada ignora os blocos enviados; marcada
  exige cliente e ao menos um item em cada bloco;
- Orçamento multi-cliente (não movimenta estoque) e efetivação preservando o
  cliente de cada item;
- Edição do pedido por blocos (PedidoEditForm / página de edição);
- PDF único com os dois clientes (cabeçalho + itens agrupados por cliente);
- Faturamento: o filtro pelo cliente secundário encontra o pedido (página de
  pedidos e dashboard).

Rode com:
    python manage.py test main.test_pedido_multi_cliente
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
from main.test_pedido_pdf import _texto_pdf
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.pedido_pdf_service import gerar_pdf_pedido
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_saida_service import RegistrarSaidaService


class BaseMultiClienteTestCase(TestCase):
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
        cls.cliente3 = Parceiro.objects.create(
            tipo="CLIENTE", razao_social="Cliente C LTDA", cnpj_cpf="11122233000144"
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

    def setUp(self):
        # Saldo novo a cada teste (as saídas consomem o estoque).
        for sku in self.skus:
            RegistrarEntradaService.executar(
                sku=sku, deposito=self.deposito,
                quantidade=Decimal("100"), origem="COMPRA",
            )

    def _saldo(self, sku):
        return CalcularSaldoService.executar(sku=sku, deposito=self.deposito)

    def _pedido_multi(self, itens, parceiro=None):
        """Cria um pedido multi-cliente. itens: [(sku, quantidade, cliente)]."""
        RegistrarSaidaService.executar_varios(
            itens=[
                {
                    "sku": sku,
                    "quantidade": Decimal(str(quantidade)),
                    "parceiro": cliente,
                }
                for sku, quantidade, cliente in itens
            ],
            deposito=self.deposito,
            origem="VENDA",
            usuario=self.usuario,
            parceiro=parceiro or self.cliente,
        )
        return Pedido.objects.latest("id")


class SaidaMultiClienteTestCase(BaseMultiClienteTestCase):
    def test_pagina_de_saida_oferece_opcao_e_clientes(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacao_saida"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tem clientes adicionais")
        # Modelo de select que o JS clona para montar os blocos.
        self.assertContains(resp, "modelo-select-cliente")
        self.assertEqual(
            {opcao["pk"] for opcao in resp.context_data["clientes_opcoes"]},
            {self.cliente.pk, self.cliente2.pk, self.cliente3.pk},
        )

    def test_saida_com_dois_clientes_grava_cliente_por_item(self):
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "documento": "PED-MULTI",
                "forma_pagamento": "PIX",
                "sku": self.skus[0].pk,
                "quantidade": "2",
                "preco_unitario": "10.00",
                "tem_clientes_adicionais": "on",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "3",
                "preco_unitario_1_1": "12.50",
            },
        )
        self.assertRedirects(resp, reverse("movimentacoes"))

        pedido = Pedido.objects.get()
        itens = list(pedido.itens.order_by("id"))
        # Um único pedido com os dois clientes.
        self.assertEqual(len(itens), 2)
        self.assertEqual(pedido.parceiro, self.cliente)
        self.assertEqual(itens[0].parceiro, self.cliente)
        self.assertEqual(itens[1].parceiro, self.cliente2)
        # Preço negociado continua sendo do item.
        self.assertEqual(itens[1].preco_unitario, Decimal("12.50"))
        # Estoque baixado só pelos itens informados.
        self.assertEqual(self._saldo(self.skus[0]), Decimal("98"))
        self.assertEqual(self._saldo(self.skus[1]), Decimal("97"))
        self.assertEqual(self._saldo(self.skus[2]), Decimal("100"))

    def test_saida_aceita_tres_clientes_no_mesmo_pedido(self):
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": "1",
                "tem_clientes_adicionais": "on",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "1",
                "cliente_ad_2": self.cliente3.pk,
                "sku_2_1": self.skus[2].pk,
                "quantidade_2_1": "1",
            },
        )
        self.assertRedirects(resp, reverse("movimentacoes"))

        pedido = Pedido.objects.get()
        clientes = [item.parceiro for item in pedido.itens.order_by("id")]
        self.assertEqual(clientes, [self.cliente, self.cliente2, self.cliente3])


    def test_saida_sem_marcar_opcao_ignora_os_blocos(self):
        """Sem a opção marcada os blocos enviados não entram no pedido."""
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": "2",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "3",
            },
        )
        self.assertRedirects(resp, reverse("movimentacoes"))

        itens = list(Movimentacao.objects.filter(tipo="SAIDA"))
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0].parceiro, self.cliente)
        self.assertEqual(self._saldo(self.skus[1]), Decimal("100"))

    def test_saida_com_opcao_marcada_exige_cliente_no_bloco(self):
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": "1",
                "tem_clientes_adicionais": "on",
                "cliente_ad_1": "",
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Escolha o cliente deste bloco.")
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_saida_com_opcao_marcada_exige_item_no_bloco(self):
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": "1",
                "tem_clientes_adicionais": "on",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": "",
                "quantidade_1_1": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp, "Informe pelo menos um item para este cliente adicional"
        )
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_saida_com_opcao_marcada_sem_blocos_gera_erro(self):
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": "1",
                "tem_clientes_adicionais": "on",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp, "Adicione ao menos um cliente adicional ou desmarque a opção."
        )
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_erro_de_validacao_rerenderiza_os_blocos_enviados(self):
        """Após um erro, os blocos voltam preenchidos na página."""
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_saida"),
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": "1",
                "tem_clientes_adicionais": "on",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "",  # falta a quantidade → erro
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Informe a quantidade deste item")
        blocos = resp.context["form"].blocos
        self.assertEqual(len(blocos), 1)
        self.assertEqual(blocos[0]["cliente"].value(), str(self.cliente2.pk))
        self.assertEqual(
            blocos[0]["linhas"][0]["sku"].value(), str(self.skus[1].pk)
        )



class OrcamentoMultiClienteTestCase(BaseMultiClienteTestCase):
    def _criar_orcamento_multi(self, quantidade="10", quantidade_extra="5"):
        """Cria um orçamento com Cliente A + Cliente B pela própria página."""
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("orcamento_novo"),
            {
                "deposito": self.deposito.pk,
                "parceiro": self.cliente.pk,
                "sku": self.skus[0].pk,
                "quantidade": quantidade,
                "preco_unitario": "9.00",
                "tem_clientes_adicionais": "on",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": quantidade_extra,
                "preco_unitario_1_1": "11.00",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))
        return Pedido.objects.get()

    def test_orcamento_multi_cliente_nao_movimenta_estoque(self):
        # 200 > saldo disponível: o orçamento NÃO valida saldo.
        orcamento = self._criar_orcamento_multi(quantidade="200")

        self.assertTrue(orcamento.eh_orcamento)
        # A ordem dos itens não é garantida (ordenados por data de criação);
        # aqui o que importa é o cliente de CADA item.
        por_sku = {item.sku_id: item for item in orcamento.itens.all()}
        self.assertEqual(len(por_sku), 2)
        self.assertEqual(
            {item.tipo for item in por_sku.values()}, {"ORCAMENTO"}
        )
        self.assertEqual(por_sku[self.skus[0].pk].parceiro, self.cliente)
        self.assertEqual(por_sku[self.skus[1].pk].parceiro, self.cliente2)
        # Nenhum item de estoque criado/baixado.
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)
        self.assertEqual(self._saldo(self.skus[0]), Decimal("100"))
        self.assertEqual(self._saldo(self.skus[1]), Decimal("100"))

    def test_efetivar_orcamento_preserva_o_cliente_de_cada_item(self):
        orcamento = self._criar_orcamento_multi()
        numero_orcamento = orcamento.pk

        resp = self.client.get(reverse("orcamento_efetivar", args=[numero_orcamento]))
        self.assertEqual(resp.status_code, 200)
        # O resumo mostra os dois clientes do orçamento.
        self.assertContains(resp, "Cliente A LTDA")
        self.assertContains(resp, "Cliente B LTDA")

        resp = self.client.post(reverse("orcamento_efetivar", args=[numero_orcamento]))
        self.assertRedirects(resp, reverse("pedidos"))

        self.assertEqual(Pedido.objects.count(), 1)
        pedido = Pedido.objects.get()
        self.assertFalse(pedido.eh_orcamento)
        por_sku = {item.sku_id: item for item in pedido.itens.all()}
        self.assertEqual(len(por_sku), 2)
        self.assertEqual(pedido.parceiro, self.cliente)
        self.assertEqual(por_sku[self.skus[0].pk].parceiro, self.cliente)
        self.assertEqual(por_sku[self.skus[1].pk].parceiro, self.cliente2)
        self.assertEqual(por_sku[self.skus[1].pk].preco_unitario, Decimal("11.00"))
        self.assertEqual(self._saldo(self.skus[0]), Decimal("90"))
        self.assertEqual(self._saldo(self.skus[1]), Decimal("95"))


class EdicaoMultiClienteTestCase(BaseMultiClienteTestCase):
    def _pedido(self):
        return self._pedido_multi(
            [(self.skus[0], 2, self.cliente), (self.skus[1], 3, self.cliente2)]
        )

    def test_pagina_de_edicao_renderiza_os_blocos_do_pedido(self):
        pedido = self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("pedido_editar", args=[pedido.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cliente adicional 1")
        self.assertContains(resp, "Cliente B LTDA")
        # A opção vem marcada porque o pedido já tem clientes adicionais.
        form = resp.context["form"]
        self.assertTrue(form.fields["tem_clientes_adicionais"].initial)
        self.assertEqual(len(form.blocos), 1)
        self.assertEqual(form.blocos[0]["cliente"].value(), self.cliente2.pk)

    def test_edicao_confirma_o_cliente_de_cada_item(self):
        pedido = self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("pedido_editar", args=[pedido.pk]),
            {
                "deposito": self.deposito.pk,
                "parceiro": self.cliente.pk,
                "documento": "PED-EDIT",
                "status_pedido": "FATURADO",
                "tem_clientes_adicionais": "on",
                "sku_1": self.skus[0].pk,
                "quantidade_1": "4",
                "preco_unitario_1": "10.00",
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "5",
                "preco_unitario_1_1": "20.00",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))

        pedido.refresh_from_db()
        self.assertEqual(pedido.documento, "PED-EDIT")
        itens = {item.sku_id: item for item in pedido.itens.all()}
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[self.skus[0].pk].parceiro, self.cliente)
        self.assertEqual(itens[self.skus[1].pk].parceiro, self.cliente2)
        self.assertEqual(itens[self.skus[0].pk].quantidade, Decimal("4"))
        self.assertEqual(itens[self.skus[1].pk].quantidade, Decimal("5"))
        self.assertEqual(itens[self.skus[1].pk].status_pedido, "FATURADO")

    def test_edicao_troca_o_cliente_do_bloco(self):
        pedido = self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("pedido_editar", args=[pedido.pk]),
            {
                "deposito": self.deposito.pk,
                "parceiro": self.cliente.pk,
                "tem_clientes_adicionais": "on",
                "sku_1": self.skus[0].pk,
                "quantidade_1": "2",
                "cliente_ad_1": self.cliente3.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "3",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))

        itens = {item.sku_id: item for item in pedido.itens.all()}
        self.assertEqual(itens[self.skus[1].pk].parceiro, self.cliente3)

    def test_edicao_sem_a_opcao_remove_os_itens_dos_blocos(self):
        """Desmarcar a opção deixa apenas os itens do cliente principal."""
        pedido = self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.post(
            reverse("pedido_editar", args=[pedido.pk]),
            {
                "deposito": self.deposito.pk,
                "parceiro": self.cliente.pk,
                "sku_1": self.skus[0].pk,
                "quantidade_1": "2",
                # Bloco do cliente adicional enviado, mas a opção está fora.
                "cliente_ad_1": self.cliente2.pk,
                "sku_1_1": self.skus[1].pk,
                "quantidade_1_1": "3",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))

        itens = list(pedido.itens.all())
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0].sku, self.skus[0])
        self.assertEqual(itens[0].parceiro, self.cliente)
        self.assertEqual(self._saldo(self.skus[1]), Decimal("100"))




class PdfMultiClienteTestCase(BaseMultiClienteTestCase):
    def test_pdf_unico_traz_os_dois_clientes(self):
        pedido = self._pedido_multi(
            [(self.skus[0], 2, self.cliente), (self.skus[1], 3, self.cliente2)]
        )
        item = pedido.itens.order_by("id").first()

        pdf = gerar_pdf_pedido(item, usuario=self.usuario)
        texto = _texto_pdf(pdf).decode("latin-1")

        # Um único documento: cabeçalho com os dois clientes...
        self.assertIn("Dados dos clientes", texto)
        self.assertIn("Clientes", texto)
        self.assertIn("Cliente A LTDA", texto)
        self.assertIn("Cliente B LTDA", texto)
        # ...e os itens agrupados/identificados por cliente.
        self.assertIn("Cliente: Cliente A LTDA", texto)
        self.assertIn("Cliente: Cliente B LTDA", texto)
        self.assertIn("Subtotal do cliente", texto)

    def test_pdf_de_pedido_com_um_cliente_nao_mostra_grupos(self):
        pedido = self._pedido_multi(
            [(self.skus[0], 2, self.cliente), (self.skus[1], 1, self.cliente)]
        )
        item = pedido.itens.order_by("id").first()

        pdf = gerar_pdf_pedido(item, usuario=self.usuario)
        texto = _texto_pdf(pdf).decode("latin-1")

        self.assertIn("Dados do cliente", texto)
        self.assertIn("Cliente A LTDA", texto)
        self.assertNotIn("Subtotal do cliente", texto)
        self.assertNotIn("Dados dos clientes", texto)


class FaturamentoMultiClienteTestCase(BaseMultiClienteTestCase):
    def _pedido(self):
        return self._pedido_multi(
            [(self.skus[0], 2, self.cliente), (self.skus[1], 3, self.cliente2)]
        )

    def test_pedidos_filtro_por_cliente_secundario(self):
        pedido = self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("pedidos"), {"parceiro": self.cliente2.pk})
        self.assertEqual(resp.status_code, 200)
        # O pedido aparece no filtro do cliente que está apenas nos itens.
        self.assertContains(resp, f"#{pedido.pk}")
        linha = resp.context_data["linhas"][0]
        self.assertEqual(linha["num_clientes"], 2)
        self.assertEqual(
            [cliente.pk for cliente in linha["clientes"]],
            [self.cliente.pk, self.cliente2.pk],
        )

    def test_dashboard_mostra_os_clientes_do_pedido_agrupado(self):
        self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        grupos = [
            linha
            for linha in resp.context_data["movimentacoes_recentes"]
            if linha["eh_grupo"]
        ]
        self.assertEqual(len(grupos), 1)
        self.assertEqual(
            {cliente.pk for cliente in grupos[0]["clientes"]},
            {self.cliente.pk, self.cliente2.pk},
        )

    def test_dashboard_filtro_por_cliente_secundario_conta_o_pedido(self):
        self._pedido()
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("dashboard"), {"parceiro": self.cliente2.pk})
        financeiro = resp.context_data["financeiro"]
        # Faturamento dos itens do cliente secundário: 3 x R$ 10,00.
        self.assertEqual(financeiro["faturamento"], Decimal("30.00"))
        # O pedido (um só) conta pelo cliente que está nos itens.
        self.assertEqual(financeiro["num_pedidos"], 1)

