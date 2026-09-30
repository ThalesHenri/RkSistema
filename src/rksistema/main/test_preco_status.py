"""
Testes automatizados de preço negociado e status do pedido nas movimentações
de saída.

Recursos testados:
- Saída com origem VENDA nasce com status PENDENTE.
- preco_unitario é gravado no registro da saída (service e API).
- Dashboard prioriza o preço negociado na movimentação (fallback p/ SKU).
- Atualização de preço/status via API (`POST /api/movimentacoes/{id}/preco-status/`)
  e via página (AtualizarPrecoStatusView).
- Filtro por status na listagem de movimentações.

Rode com:
    python manage.py test main.test_preco_status
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from main.models import (
    Categoria,
    Deposito,
    Movimentacao,
    Parceiro,
    Produto,
    SKU,
    UnidadeMedida,
)
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_saida_service import RegistrarSaidaService


class BaseMovimentacaoTestCase(TestCase):
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

    def _entrada(self, quantidade="100"):
        RegistrarEntradaService.executar(
            sku=self.sku,
            deposito=self.deposito,
            quantidade=Decimal(quantidade),
            origem="COMPRA",
            usuario=self.usuario,
        )

    def _saida(self, quantidade="10", origem="VENDA", preco=None):
        return RegistrarSaidaService.executar(
            sku=self.sku,
            deposito=self.deposito,
            quantidade=Decimal(quantidade),
            origem=origem,
            usuario=self.usuario,
            parceiro=self.cliente,
            preco_unitario=preco,
        )
class StatusPedidoTestCase(BaseMovimentacaoTestCase):
    def test_saida_pode_conter_varios_skus_e_e_atomica(self):
        segundo_sku = SKU.objects.create(
            produto=self.produto, codigo="CX-403020", unidade_medida=self.unidade,
        )
        self._entrada("10")
        RegistrarEntradaService.executar(
            sku=segundo_sku, deposito=self.deposito, quantidade=Decimal("3"),
            origem="COMPRA", usuario=self.usuario,
        )
        api = APIClient()
        api.force_authenticate(user=self.usuario)
        resposta = api.post(
            "/api/movimentacoes/saida/",
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "itens": [
                    {"sku": self.sku.pk, "quantidade": "2"},
                    {"sku": segundo_sku.pk, "quantidade": "1"},
                ],
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(len(resposta.json()), 2)
        self.assertEqual(
            Movimentacao.objects.filter(pedido__isnull=False).count(), 2
        )
        self.assertEqual(
            Movimentacao.objects.filter(pedido__isnull=False).values_list(
                "pedido_id", flat=True
            ).distinct().count(), 1
        )

    def test_saida_varios_skus_nao_grava_parte_sem_saldo(self):
        segundo_sku = SKU.objects.create(
            produto=self.produto, codigo="CX-403020", unidade_medida=self.unidade,
        )
        self._entrada("10")
        api = APIClient()
        api.force_authenticate(user=self.usuario)
        resposta = api.post(
            "/api/movimentacoes/saida/",
            {
                "deposito": self.deposito.pk,
                "origem": "VENDA",
                "itens": [
                    {"sku": self.sku.pk, "quantidade": "2"},
                    {"sku": segundo_sku.pk, "quantidade": "1"},
                ],
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_saida_venda_nasce_pendente(self):
        self._entrada()
        saida = self._saida(origem="VENDA")
        saida.refresh_from_db()
        self.assertEqual(saida.status_pedido, "PENDENTE")

    def test_saida_sem_origem_venda_nao_ganha_status(self):
        self._entrada()
        saida = self._saida(origem="PERDA")
        saida.refresh_from_db()
        self.assertIsNone(saida.status_pedido)

    def test_saida_grava_preco_unitario_negociado(self):
        self._entrada()
        saida = self._saida(quantidade="5", preco=Decimal("8.50"))
        saida.refresh_from_db()
        self.assertEqual(saida.preco_unitario, Decimal("8.50"))
        self.assertEqual(saida.valor_total, Decimal("42.50"))

    def test_saida_sem_preco_fica_nulo(self):
        self._entrada()
        saida = self._saida()
        saida.refresh_from_db()
        self.assertIsNone(saida.preco_unitario)
        self.assertIsNone(saida.valor_total)


class AtualizarPrecoStatusAPITestCase(BaseMovimentacaoTestCase):
    def setUp(self):
        self._entrada()
        self.saida = self._saida(quantidade="10", preco=Decimal("9.00"))
        self.api = APIClient()
        self.api.force_authenticate(user=self.usuario)

    def test_atualiza_preco_e_status(self):
        resp = self.api.post(
            f"/api/movimentacoes/{self.saida.id}/preco-status/",
            {"preco_unitario": "7.75", "status_pedido": "FATURADO"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.saida.refresh_from_db()
        self.assertEqual(self.saida.preco_unitario, Decimal("7.75"))
        self.assertEqual(self.saida.status_pedido, "FATURADO")
        self.assertEqual(self.saida.valor_total, Decimal("77.50"))
        self.assertEqual(resp.json()["valor_total"], "77.50")

    def test_status_faturado_sincroniza_pedido_e_calcula_lucro_no_dashboard(self):
        segundo_sku = SKU.objects.create(
            produto=self.produto,
            codigo="CX-403020",
            unidade_medida=self.unidade,
            preco_venda=Decimal("20.00"),
            preco_custo=Decimal("5.00"),
        )
        RegistrarEntradaService.executar(
            sku=segundo_sku,
            deposito=self.deposito,
            quantidade=Decimal("100"),
            origem="COMPRA",
            usuario=self.usuario,
        )
        movimentacoes = RegistrarSaidaService.executar_varios(
            itens=[
                {
                    "sku": self.sku,
                    "quantidade": Decimal("10"),
                    "preco_unitario": Decimal("9.00"),
                },
                {
                    "sku": segundo_sku,
                    "quantidade": Decimal("2"),
                    "preco_unitario": Decimal("20.00"),
                },
            ],
            deposito=self.deposito,
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )

        resp = self.api.post(
            f"/api/movimentacoes/{movimentacoes[0].pk}/preco-status/",
            {"status_pedido": "FATURADO"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pedido = movimentacoes[0].pedido
        pedido.refresh_from_db()
        self.assertEqual(pedido.status_pedido, "FATURADO")
        self.assertFalse(pedido.itens.exclude(status_pedido="FATURADO").exists())

        dashboard_client = Client()
        dashboard_client.force_login(self.usuario)
        dashboard_resp = dashboard_client.get(reverse("dashboard"))
        self.assertEqual(dashboard_resp.status_code, 200)
        self.assertEqual(
            dashboard_resp.context_data["financeiro"]["lucro_faturado"],
            Decimal("80.00"),
        )

    def test_atualiza_apenas_status(self):
        resp = self.api.post(
            f"/api/movimentacoes/{self.saida.id}/preco-status/",
            {"status_pedido": "ENTREGUE"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.saida.refresh_from_db()
        self.assertEqual(self.saida.status_pedido, "ENTREGUE")
        self.assertEqual(self.saida.preco_unitario, Decimal("9.00"))

    def test_recusa_atualizar_preco_em_entrada(self):
        entrada = Movimentacao.objects.get(tipo="ENTRADA")
        resp = self.api.post(
            f"/api/movimentacoes/{entrada.id}/preco-status/",
            {"preco_unitario": "5.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requer_ao_menos_um_campo(self):
        resp = self.api.post(
            f"/api/movimentacoes/{self.saida.id}/preco-status/",
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_saida_aceita_preco_negociado(self):
        resp = self.api.post(
            "/api/movimentacoes/saida/",
            {
                "sku": self.sku.id,
                "deposito": self.deposito.id,
                "quantidade": "5",
                "origem": "VENDA",
                "parceiro": self.cliente.id,
                "preco_unitario": "12.30",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["status_pedido"], "PENDENTE")
        self.assertEqual(Decimal(resp.json()["preco_unitario"]), Decimal("12.30"))

    def test_atualiza_forma_pagamento_e_prazo(self):
        resp = self.api.post(
            f"/api/movimentacoes/{self.saida.id}/preco-status/",
            {"forma_pagamento": "BOLETO", "prazo_pagamento": "30 dias"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.saida.refresh_from_db()
        self.assertEqual(self.saida.forma_pagamento, "BOLETO")
        self.assertEqual(self.saida.prazo_pagamento, "30 dias")

    def test_api_saida_aceita_forma_e_prazo(self):
        resp = self.api.post(
            "/api/movimentacoes/saida/",
            {
                "sku": self.sku.id,
                "deposito": self.deposito.id,
                "quantidade": "5",
                "origem": "VENDA",
                "parceiro": self.cliente.id,
                "forma_pagamento": "PIX",
                "prazo_pagamento": "à vista",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["forma_pagamento"], "PIX")
        self.assertEqual(resp.json()["prazo_pagamento"], "à vista")

    def test_serializer_nao_inclui_mais_lote(self):
        resp = self.api.get(f"/api/movimentacoes/{self.saida.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("lote", resp.json())
        self.assertIn("forma_pagamento", resp.json())
        self.assertIn("prazo_pagamento", resp.json())


class PaginaPrecoStatusTestCase(BaseMovimentacaoTestCase):
    def setUp(self):
        self._entrada()
        self.saida = self._saida(quantidade="10", preco=Decimal("9.00"))
        self.client.force_login(self.usuario)

    def test_post_atualiza_preco_e_status(self):
        resp = self.client.post(
            reverse("movimentacao_atualizar_preco_status", args=[self.saida.id]),
            {"preco_unitario": "6.60", "status_pedido": "ENTREGUE"},
        )
        self.assertEqual(resp.status_code, 302)
        self.saida.refresh_from_db()
        self.assertEqual(self.saida.preco_unitario, Decimal("6.60"))
        self.assertEqual(self.saida.status_pedido, "ENTREGUE")
        self.assertRedirects(resp, reverse("pedidos"))

    def test_post_atualiza_forma_e_prazo(self):
        resp = self.client.post(
            reverse("movimentacao_atualizar_preco_status", args=[self.saida.id]),
            {"forma_pagamento": "PIX", "prazo_pagamento": "30 dias"},
        )
        self.assertEqual(resp.status_code, 302)
        self.saida.refresh_from_db()
        self.assertEqual(self.saida.forma_pagamento, "PIX")
        self.assertEqual(self.saida.prazo_pagamento, "30 dias")
        self.assertRedirects(resp, reverse("pedidos"))

    def test_registrar_saida_form_exibe_campo_preco(self):
        # o form de saída deve conter preco_unitario na renderização
        self._entrada()
        resp = self.client.get(reverse("movimentacao_saida"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "preco_unitario")
        self.assertContains(resp, "forma_pagamento")
        self.assertContains(resp, "prazo_pagamento")

    def test_listagem_filtra_por_status(self):
        out = self._saida(quantidade="2", preco=Decimal("5.00"))
        out.status_pedido = "FATURADO"
        out.save(update_fields=["status_pedido"])

        resp = self.client.get(reverse("movimentacoes"), {"status": "FATURADO"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.sku.codigo)

        resp = self.client.get(reverse("movimentacoes"), {"status": "ENTREGUE"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, self.sku.codigo)

    def test_pagina_renderiza_edicao_inline_preco_status(self):
        resp = self.client.get(reverse("movimentacoes"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"form-mov-{self.saida.id}")
        self.assertContains(resp, 'name="preco_unitario"')
        self.assertContains(resp, 'name="status_pedido"')


class DashboardFinanceiroTestCase(BaseMovimentacaoTestCase):
    def test_faturamento_usa_preco_negociado_da_movimentacao(self):
        self._entrada()
        saida = self._saida(quantidade="10", preco=Decimal("3.00"))

        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)  # sem login -> redireciona

        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        # 10 unidades x preco negociado 3.00 = 30.00 (e não 10 x 10.00 do SKU)
        self.assertContains(resp, "30.00")

    def test_dashboard_filtra_por_produto_e_sku(self):
        self._entrada()
        self._saida(quantidade="10", preco=Decimal("3.00"))
        self.client.force_login(self.usuario)

        # Filtro por produto inclui a venda
        resp = self.client.get(
            reverse("dashboard"), {"produto": self.produto.pk}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "30.00")

        # Filtro por SKU sem vendas zera o faturamento
        outro_produto = Produto.objects.create(
            nome="Sacola", tipo_produto="PRODUTO_ACABADO",
            categoria=self.categoria,
        )
        outro_sku = SKU.objects.create(
            produto=outro_produto, codigo="SAC-01",
            unidade_medida=self.unidade, preco_venda=Decimal("2.00"),
        )
        resp = self.client.get(reverse("dashboard"), {"sku": outro_sku.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "0.00")