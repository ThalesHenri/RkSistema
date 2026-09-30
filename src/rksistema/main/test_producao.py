"""
Testes automatizados do fluxo de produção (matéria-prima → produto acabado).

O Produto agora possui `tipo_produto` (MATERIA_PRIMA / PRODUTO_ACABADO), e o
RegistrarProducaoService cria, em transação atômica, uma SAIDA da matéria-prima
+ uma ENTRADA do produto acabado, ambas com origem PRODUCAO.

Rode com:
    python manage.py test main.test_producao
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from main.models import Categoria, Deposito, Movimentacao, Produto, SKU, UnidadeMedida
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.estoque_error import EstoqueError
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_producao_service import RegistrarProducaoService


class FluxoProducaoTestCase(TestCase):
    """Cenário real: chapa de papelão (matéria-prima) vira caixa (produto acabado)."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="teste", password="senha123"
        )
        cls.categoria = Categoria.objects.create(nome="Embalagens")
        cls.unidade = UnidadeMedida.objects.create(sigla="UN", nome="Unidade")
        cls.deposito = Deposito.objects.create(nome="Depósito Central")

        cls.produto_mp = Produto.objects.create(
            nome="Chapa de Papelão",
            tipo_produto="MATERIA_PRIMA",
            categoria=cls.categoria,
        )
        cls.produto_pa = Produto.objects.create(
            nome="Caixa de Papelão",
            tipo_produto="PRODUTO_ACABADO",
            categoria=cls.categoria,
        )

        cls.sku_mp = SKU.objects.create(
            produto=cls.produto_mp,
            codigo="CHAPA-PAP-120X80",
            unidade_medida=cls.unidade,
            estoque_minimo=Decimal("10"),
        )
        cls.sku_pa = SKU.objects.create(
            produto=cls.produto_pa,
            codigo="CX-302015",
            unidade_medida=cls.unidade,
            estoque_minimo=Decimal("5"),
        )

    def _entrada_mp(self, quantidade="100"):
        RegistrarEntradaService.executar(
            sku=self.sku_mp,
            deposito=self.deposito,
            quantidade=Decimal(quantidade),
            origem="COMPRA",
            usuario=self.usuario,
        )

    def test_producao_baixa_mp_e_soma_pa(self):
        self._entrada_mp("100")

        resultado = RegistrarProducaoService.executar(
            materia_prima=self.sku_mp,
            quantidade_materia_prima=Decimal("4"),
            produto_acabado=self.sku_pa,
            quantidade_produzida=Decimal("4"),
            deposito=self.deposito,
            usuario=self.usuario,
            documento="OP-0001",
            observacao="Produção de teste",
        )

        self.assertEqual(resultado["saida"].tipo, "SAIDA")
        self.assertEqual(resultado["entrada"].tipo, "ENTRADA")
        self.assertEqual(resultado["saida"].origem, "PRODUCAO")
        self.assertEqual(resultado["entrada"].origem, "PRODUCAO")
        self.assertEqual(resultado["saida"].documento, "OP-0001")
        self.assertEqual(resultado["entrada"].documento, "OP-0001")
        # A entrada fica vinculada à saída (usado na exclusão do par)
        self.assertEqual(resultado["entrada"].movimentacao_origem, resultado["saida"])

        # Saldo: MP 100 − 4 = 96; PA 0 + 4 = 4
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_mp, deposito=self.deposito),
            Decimal("96"),
        )
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("4"),
        )
        self.assertEqual(Movimentacao.objects.filter(origem="PRODUCAO").count(), 2)

    def test_producao_sem_saldo_mp_eh_bloqueada(self):
        self._entrada_mp("10")

        with self.assertRaises(EstoqueError):
            RegistrarProducaoService.executar(
                materia_prima=self.sku_mp,
                quantidade_materia_prima=Decimal("11"),
                produto_acabado=self.sku_pa,
                quantidade_produzida=Decimal("11"),
                deposito=self.deposito,
                usuario=self.usuario,
            )

        # Nada foi criado (transação atômica)
        self.assertEqual(Movimentacao.objects.filter(origem="PRODUCAO").count(), 0)
        self.assertEqual(Movimentacao.objects.count(), 1)  # só a entrada de compra

    def test_producao_valida_tipos_de_produto(self):
        self._entrada_mp("100")

        # Produto acabado passado como matéria-prima deve ser rejeitado
        with self.assertRaises(EstoqueError):
            RegistrarProducaoService.executar(
                materia_prima=self.sku_pa,
                quantidade_materia_prima=Decimal("1"),
                produto_acabado=self.sku_pa,
                quantidade_produzida=Decimal("1"),
                deposito=self.deposito,
                usuario=self.usuario,
            )

    def test_api_producao_registra_duas_movimentacoes(self):
        self._entrada_mp("50")
        api = APIClient()
        api.force_authenticate(user=self.usuario)

        resp = api.post(
            "/api/movimentacoes/producao/",
            {
                "materia_prima": self.sku_mp.id,
                "quantidade_materia_prima": "10",
                "produto_acabado": self.sku_pa.id,
                "quantidade_produzida": "10",
                "deposito": self.deposito.id,
                "documento": "OP-0001",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.json()), 2)
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_mp, deposito=self.deposito),
            Decimal("40"),
        )
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("10"),
        )

    def test_api_producao_sem_saldo_retorna_400(self):
        self._entrada_mp("2")
        api = APIClient()
        api.force_authenticate(user=self.usuario)

        resp = api.post(
            "/api/movimentacoes/producao/",
            {
                "materia_prima": self.sku_mp.id,
                "quantidade_materia_prima": "99",
                "produto_acabado": self.sku_pa.id,
                "quantidade_produzida": "99",
                "deposito": self.deposito.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("insuficiente", resp.json()["detail"])

    def test_pagina_producao_post_valida(self):
        self._entrada_mp("30")
        self.client.force_login(self.usuario)

        # GET renderiza o formulário
        resp = self.client.get(reverse("movimentacao_producao"))
        self.assertEqual(resp.status_code, 200)

        # POST válido redireciona para a listagem de movimentações
        resp = self.client.post(
            reverse("movimentacao_producao"),
            {
                "materia_prima": self.sku_mp.id,
                "quantidade_materia_prima": "6",
                "produto_acabado": self.sku_pa.id,
                "quantidade_produzida": "6",
                "deposito": self.deposito.id,
                "documento": "OP-0002",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("movimentacoes"))
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_mp, deposito=self.deposito),
            Decimal("24"),
        )
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("6"),
        )

    def test_paginas_listagem_renderizam_tipo(self):
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("estoque"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Matéria-prima")

        resp = self.client.get(reverse("produto_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "badge-info")

        resp = self.client.get(reverse("sku_list"))
        self.assertEqual(resp.status_code, 200)