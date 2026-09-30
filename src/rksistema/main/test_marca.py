"""Testes da marca exibida no sistema: RK Embalagens.

O nome antigo ("StockPlastic") foi substituído em títulos de página, no app
Django e nos PDFs emitidos. Estes testes evitam que ele reapareça.

Rode com:
    python manage.py test main.test_marca
"""

from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import (
    Categoria,
    Deposito,
    Parceiro,
    Produto,
    SKU,
    UnidadeMedida,
)
from main.test_pedido_pdf import _texto_pdf
from main.views.services.pedido_pdf_service import (
    gerar_pdf_pedido,
    gerar_pdf_relatorio_pedidos,
)
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_saida_service import RegistrarSaidaService

MARCA = "RK Embalagens"
MARCA_ANTIGA = "StockPlastic"


class MarcaNasPaginasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="teste", password="senha123"
        )
        cls.deposito = Deposito.objects.create(nome="Depósito Central")
        cls.categoria = Categoria.objects.create(nome="Embalagens")
        cls.unidade = UnidadeMedida.objects.create(sigla="UN", nome="Unidade")

    def test_verbose_name_do_app(self):
        self.assertEqual(apps.get_app_config("main").verbose_name, MARCA)

    def test_login_usa_a_marca_nova(self):
        resposta = self.client.get(reverse("login"))
        self.assertContains(resposta, f"<title>Entrar — {MARCA}</title>")
        self.assertNotContains(resposta, MARCA_ANTIGA)

    def test_dashboard_usa_a_marca_nova(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("dashboard"))
        self.assertContains(resposta, f"<title>Dashboard — {MARCA}</title>")
        self.assertContains(resposta, MARCA)  # logo/nome na sidebar
        self.assertNotContains(resposta, MARCA_ANTIGA)

    def test_paginas_sem_titulo_proprio_usam_a_marca_nova(self):
        self.client.force_login(self.usuario)
        for nome in ("estoque", "pedidos", "parceiro_list"):
            with self.subTest(url=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, f"<title>{MARCA}</title>")
                self.assertNotContains(resposta, MARCA_ANTIGA)


class MarcaNoPdfTestCase(TestCase):
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
        cls.sku = SKU.objects.create(
            produto=cls.produto,
            codigo="CX-302015",
            unidade_medida=cls.unidade,
            preco_venda=Decimal("10.00"),
            preco_custo=Decimal("4.00"),
        )

    def _movimentacao(self):
        """Cria uma saída de venda com cliente (matéria-prima dos PDFs)."""
        RegistrarEntradaService.executar(
            sku=self.sku,
            deposito=self.deposito,
            quantidade=Decimal("100"),
            origem="COMPRA",
            usuario=self.usuario,
        )
        return RegistrarSaidaService.executar(
            sku=self.sku,
            deposito=self.deposito,
            quantidade=Decimal("10"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )

    def test_pedido_usa_a_marca_nova_no_rodape(self):
        pdf = gerar_pdf_pedido(self._movimentacao())

        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(MARCA.encode(), pdf)  # metadados (author)
        self.assertNotIn(MARCA_ANTIGA.encode(), pdf)

        texto = _texto_pdf(pdf)
        # Rodapé realmente desenhado: o ReportLab 4 só executa o callback quando
        # ele é passado ao build() (no construtor é silenciosamente ignorado).
        self.assertIn(f"{MARCA} · Página 1".encode("cp1252"), texto)
        self.assertNotIn(MARCA_ANTIGA.encode(), texto)

    def test_relatorio_usa_a_marca_nova_no_cabecalho_e_rodape(self):
        pdf = gerar_pdf_relatorio_pedidos([self._movimentacao()])

        texto = _texto_pdf(pdf)
        self.assertIn(f"{MARCA} — Gestão de estoque".encode("cp1252"), texto)
        self.assertIn(f"{MARCA} · Página 1".encode("cp1252"), texto)
        self.assertNotIn(MARCA_ANTIGA.encode(), texto)
