"""Testes do orçamento (pedido simulado) e da sua efetivação.

Cobre:
- Criar orçamento pelo formulário (não movimenta estoque, aceita quantidade
  acima do saldo disponível);
- Orçamento aparece em /pedidos/ (badge, filtro por tipo) e some das
  movimentações/métricas de estoque;
- PDF do orçamento é válido e traz o aviso "sem valor fiscal";
- Efetivar cria um PEDIDO NOVO e EXCLUI o orçamento (valida o saldo);
- Excluir orçamento individual e excluir todos de uma vez;
- API: POST /api/movimentacoes/orcamento/ e .../{id}/efetivar/.

Rode com:
    python manage.py test main.test_orcamento
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

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
from main.views.services.registrar_orcamento_service import RegistrarOrcamentoService
from main.views.services.registrar_saida_service import RegistrarSaidaService


class BaseOrcamentoTestCase(TestCase):
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
            produto=cls.produto, codigo="CX-302015", unidade_medida=cls.unidade,
            preco_venda=Decimal("10.00"), preco_custo=Decimal("4.00"),
        )

    def _entrada(self, quantidade="100"):
        return RegistrarEntradaService.executar(
            sku=self.sku, deposito=self.deposito,
            quantidade=Decimal(quantidade), origem="COMPRA",
        )

    def _orcamento(self, quantidade="5", preco=Decimal("12.50")):
        itens = RegistrarOrcamentoService.executar_varios(
            itens=[{
                "sku": self.sku,
                "quantidade": Decimal(quantidade),
                "preco_unitario": preco,
            }],
            deposito=self.deposito,
            parceiro=self.cliente,
            usuario=self.usuario,
        )
        return itens[0].pedido


class RegistrarOrcamentoTestCase(BaseOrcamentoTestCase):
    def test_orcamento_requer_login(self):
        resp = self.client.get(reverse("orcamento_novo"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_criar_orcamento_nao_movimenta_estoque(self):
        self._entrada("100")
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("orcamento_novo"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Novo orçamento")

        # 500 > saldo disponível: orçamento NÃO valida saldo.
        resp = self.client.post(
            reverse("orcamento_novo"),
            {
                "deposito": self.deposito.pk,
                "parceiro": self.cliente.pk,
                "sku": self.sku.pk,
                "quantidade": "500",
                "preco_unitario": "12.50",
            },
        )
        self.assertRedirects(resp, reverse("pedidos"))

        pedido = Pedido.objects.get()
        self.assertTrue(pedido.eh_orcamento)
        item = Movimentacao.objects.get(tipo="ORCAMENTO")
        self.assertEqual(item.tipo, "ORCAMENTO")
        self.assertEqual(item.pedido, pedido)
        # Estoque intocado.
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku, deposito=self.deposito),
            Decimal("100"),
        )
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_orcamento_aparece_em_pedidos_com_filtro_de_tipo(self):
        self._entrada("100")
        orcamento = self._orcamento(quantidade="2")
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("pedidos"))
        self.assertContains(resp, f"#{orcamento.pk}")
        self.assertContains(resp, "Orçamento")
        self.assertContains(resp, "PDF orçamento")
        self.assertContains(resp, "Efetivar")

        resp = self.client.get(reverse("pedidos"), {"tipo": "orcamento"})
        self.assertContains(resp, f"#{orcamento.pk}")

        resp = self.client.get(reverse("pedidos"), {"tipo": "pedido"})
        self.assertNotContains(resp, f"#{orcamento.pk}")

    def test_orcamento_nao_polui_dashboard(self):
        self._entrada("100")
        self._orcamento(quantidade="3")
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Só a entrada de compra conta como movimentação de estoque.
        self.assertEqual(resp.context_data["totais"]["movimentacoes"], 1)
        self.assertEqual(resp.context_data["financeiro"]["num_pedidos"], 0)

    def test_pdf_do_orcamento_destaca_que_nao_tem_valor_fiscal(self):
        self._entrada("100")
        orcamento = self._orcamento(quantidade="2")
        item = orcamento.itens.first()

        pdf = gerar_pdf_pedido(item, usuario=self.usuario, tipo_documento="ORCAMENTO")
        self.assertTrue(pdf.startswith(b"%PDF"))
        texto = _texto_pdf(pdf).decode("latin-1")
        self.assertIn("ORÇAMENTO", texto)
        self.assertIn("SEM VALOR FISCAL", texto)
        self.assertIn("SUJEITO A APROVAÇÃO", texto)
        self.assertIn("APROVAÇÃO DO ORÇAMENTO", texto)

    def test_view_pdf_do_orcamento(self):
        self._entrada("100")
        orcamento = self._orcamento()
        item = orcamento.itens.first()
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("movimentacao_pdf", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(
            f'filename="orcamento-{orcamento.pk}.pdf"',
            resp["Content-Disposition"],
        )


class EfetivarOrcamentoTestCase(BaseOrcamentoTestCase):
    def test_pagina_efetivar_exige_login(self):
        self._entrada("100")
        orcamento = self._orcamento()
        resp = self.client.get(reverse("orcamento_efetivar", args=[orcamento.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_efetivar_cria_pedido_e_exclui_orcamento(self):
        self._entrada("100")
        orcamento = self._orcamento(quantidade="5", preco=Decimal("12.50"))
        numero_orcamento = orcamento.pk
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("orcamento_efetivar", args=[numero_orcamento]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Efetivar")

        resp = self.client.post(reverse("orcamento_efetivar", args=[numero_orcamento]))
        self.assertRedirects(resp, reverse("pedidos"))

        # O orçamento foi excluído...
        self.assertFalse(Pedido.objects.filter(pk=numero_orcamento).exists())
        # ...e existe um pedido real com os mesmos itens.
        novo = Pedido.objects.get()
        self.assertEqual(novo.origem, "VENDA")
        self.assertEqual(novo.parceiro, self.cliente)
        item = novo.itens.get()
        self.assertEqual(item.tipo, "SAIDA")
        self.assertEqual(item.status_pedido, "PENDENTE")
        self.assertEqual(item.quantidade, Decimal("5"))
        self.assertEqual(item.preco_unitario, Decimal("12.50"))
        self.assertIn(f"orçamento #{numero_orcamento}", item.observacao)
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku, deposito=self.deposito),
            Decimal("95"),
        )

    def test_efetivar_sem_saldo_nao_altera_nada(self):
        self._entrada("10")
        orcamento = self._orcamento(quantidade="500")
        self.client.force_login(self.usuario)

        resp = self.client.post(reverse("orcamento_efetivar", args=[orcamento.pk]))
        self.assertRedirects(
            resp, reverse("orcamento_efetivar", args=[orcamento.pk])
        )

        orcamento.refresh_from_db()
        self.assertTrue(orcamento.eh_orcamento)
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku, deposito=self.deposito),
            Decimal("10"),
        )

    def test_efetivar_em_pedido_comum_redireciona(self):
        self._entrada("100")
        self._orcamento(quantidade="1")
        self.client.force_login(self.usuario)
        # Efetiva e tenta efetivar de novo (agora é um pedido comum).
        orcamento = Pedido.objects.get()
        self.client.post(reverse("orcamento_efetivar", args=[orcamento.pk]))
        novo = Pedido.objects.get()
        resp = self.client.get(reverse("orcamento_efetivar", args=[novo.pk]))
        self.assertRedirects(resp, reverse("pedidos"))


class ExcluirOrcamentoTestCase(BaseOrcamentoTestCase):
    def test_excluir_orcamento_individual(self):
        self._entrada("100")
        orcamento = self._orcamento()
        self.client.force_login(self.usuario)

        resp = self.client.post(reverse("pedido_excluir", args=[orcamento.pk]))
        self.assertRedirects(resp, reverse("pedidos"))
        self.assertFalse(Pedido.objects.exists())
        self.assertFalse(Movimentacao.objects.filter(tipo="ORCAMENTO").exists())

    def test_excluir_todos_os_orcamentos_preserva_pedidos(self):
        self._entrada("100")
        RegistrarSaidaService.executar_varios(
            itens=[{"sku": self.sku, "quantidade": Decimal("2")}],
            deposito=self.deposito, origem="VENDA", parceiro=self.cliente,
        )
        pedido_real = Pedido.objects.get()
        self._orcamento(quantidade="3")
        self._orcamento(quantidade="4")
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("orcamentos_excluir_todos"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse("orcamentos_excluir_todos"))
        self.assertRedirects(resp, reverse("pedidos"))

        self.assertEqual(Pedido.objects.count(), 1)
        self.assertTrue(Pedido.objects.filter(pk=pedido_real.pk).exists())
        self.assertEqual(Movimentacao.objects.filter(tipo="ORCAMENTO").count(), 0)


class OrcamentoApiTestCase(BaseOrcamentoTestCase):
    def test_api_criar_e_efetivar_orcamento(self):
        self._entrada("100")
        api = APIClient()
        api.force_authenticate(user=self.usuario)

        resp = api.post(
            "/api/movimentacoes/orcamento/",
            {
                "sku": self.sku.pk,
                "deposito": self.deposito.pk,
                "quantidade": "4",
                "parceiro": self.cliente.pk,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        item_id = resp.json()[0]["id"]
        self.assertEqual(resp.json()[0]["tipo"], "ORCAMENTO")

        # Itens de orçamento não aparecem na listagem da API.
        resp_lista = api.get("/api/movimentacoes/")
        ids = [item["id"] for item in resp_lista.json()]
        self.assertNotIn(item_id, ids)

        resp = api.post(f"/api/movimentacoes/{item_id}/efetivar/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["tipo"], "SAIDA")
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku, deposito=self.deposito),
            Decimal("96"),
        )
        self.assertFalse(Pedido.objects.filter(origem="ORCAMENTO").exists())


