"""Testes da exclusão de movimentações (frontend).

Cobre:
- Exclusão de uma entrada comum reverte o saldo.
- Exclusão de uma produção remove o PAR (saída + entrada vinculada).
- A página de confirmação exige login.

Rode com:
    python manage.py test main.test_movimentacao_delete
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import Categoria, Deposito, Movimentacao, Produto, SKU, UnidadeMedida
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_producao_service import RegistrarProducaoService


class ExcluirMovimentacaoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="teste", password="senha123"
        )
        cls.categoria = Categoria.objects.create(nome="Embalagens")
        cls.unidade = UnidadeMedida.objects.create(sigla="UN", nome="Unidade")
        cls.deposito = Deposito.objects.create(nome="Depósito Central")
        cls.produto_mp = Produto.objects.create(
            nome="Chapa de Papelão", tipo_produto="MATERIA_PRIMA",
            categoria=cls.categoria,
        )
        cls.produto_pa = Produto.objects.create(
            nome="Caixa de Papelão", tipo_produto="PRODUTO_ACABADO",
            categoria=cls.categoria,
        )
        cls.sku_mp = SKU.objects.create(
            produto=cls.produto_mp, codigo="CHAPA-PAP-120X80",
            unidade_medida=cls.unidade,
        )
        cls.sku_pa = SKU.objects.create(
            produto=cls.produto_pa, codigo="CX-302015",
            unidade_medida=cls.unidade,
        )

    def _entrada_mp(self, quantidade="100"):
        return RegistrarEntradaService.executar(
            sku=self.sku_mp,
            deposito=self.deposito,
            quantidade=Decimal(quantidade),
            origem="COMPRA",
            usuario=self.usuario,
        )

    def test_exclusao_entrada_comum_reverte_saldo(self):
        entrada = self._entrada_mp("100")
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_mp, deposito=self.deposito),
            Decimal("100"),
        )

        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_delete", args=[entrada.pk])
        )
        self.assertRedirects(resp, reverse("movimentacoes"))
        self.assertEqual(Movimentacao.objects.count(), 0)
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_mp, deposito=self.deposito),
            Decimal("0"),
        )

    def test_exclusao_producao_remove_o_par(self):
        self._entrada_mp("100")
        resultado = RegistrarProducaoService.executar(
            materia_prima=self.sku_mp,
            quantidade_materia_prima=Decimal("4"),
            produto_acabado=self.sku_pa,
            quantidade_produzida=Decimal("4"),
            deposito=self.deposito,
            usuario=self.usuario,
        )
        saida, entrada = resultado["saida"], resultado["entrada"]
        self.assertEqual(Movimentacao.objects.filter(origem="PRODUCAO").count(), 2)
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("4"),
        )

        self.client.force_login(self.usuario)
        # Excluir pela ENTRADA também remove a SAIDA vinculada
        resp = self.client.post(reverse("movimentacao_delete", args=[entrada.pk]))
        self.assertRedirects(resp, reverse("movimentacoes"))
        self.assertFalse(
            Movimentacao.objects.filter(pk__in=[saida.pk, entrada.pk]).exists()
        )
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("0"),
        )

    def test_pagina_confirmacao_exige_login(self):
        entrada = self._entrada_mp("10")
        resp = self.client.get(reverse("movimentacao_delete", args=[entrada.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_pagina_confirmacao_renderiza_e_post_exclui(self):
        entrada = self._entrada_mp("10")
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacao_delete", args=[entrada.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Excluir movimentação")

        resp = self.client.post(reverse("movimentacao_delete", args=[entrada.pk]))
        self.assertRedirects(resp, reverse("movimentacoes"))
        self.assertEqual(Movimentacao.objects.count(), 0)