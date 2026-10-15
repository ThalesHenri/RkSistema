from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import SaldoDevedor


class SaldoDevedorViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username="teste", password="senha123"
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_debito_e_pagamento_atualizam_saldo_e_dashboard(self):
        resposta_debito = self.client.post(
            reverse("saldo_devedor_create"),
            {"tipo": "DEBITO", "valor": "100.00", "descricao": "Compra avulsa"},
        )
        self.assertRedirects(resposta_debito, reverse("saldo_devedor_list"))
        self.assertEqual(SaldoDevedor.saldo_atual(), Decimal("100.00"))

        resposta_pagamento = self.client.post(
            reverse("saldo_devedor_create"),
            {"tipo": "PAGAMENTO", "valor": "35.50", "descricao": "Pagamento parcial"},
        )
        self.assertRedirects(resposta_pagamento, reverse("saldo_devedor_list"))
        self.assertEqual(SaldoDevedor.saldo_atual(), Decimal("64.50"))

        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(
            dashboard.context_data["totais"]["saldo_devedor"], Decimal("64.50")
        )
        self.assertEqual(SaldoDevedor.objects.filter(usuario=self.usuario).count(), 2)

    def test_impede_pagamento_maior_que_saldo(self):
        SaldoDevedor.objects.create(
            tipo=SaldoDevedor.Tipo.DEBITO,
            valor=Decimal("25.00"),
            descricao="Débito existente",
        )

        resposta = self.client.post(
            reverse("saldo_devedor_create"),
            {"tipo": "PAGAMENTO", "valor": "25.01", "descricao": "Acima do saldo"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta, "O pagamento não pode ser maior que o saldo devedor atual."
        )
        self.assertEqual(SaldoDevedor.objects.count(), 1)
        self.assertEqual(SaldoDevedor.saldo_atual(), Decimal("25.00"))

    def test_tela_lista_totais_e_historico(self):
        SaldoDevedor.objects.create(
            tipo=SaldoDevedor.Tipo.DEBITO,
            valor=Decimal("80.00"),
            descricao="Conta eventual",
            usuario=self.usuario,
        )
        SaldoDevedor.objects.create(
            tipo=SaldoDevedor.Tipo.PAGAMENTO,
            valor=Decimal("20.00"),
            descricao="Parcela paga",
            usuario=self.usuario,
        )

        resposta = self.client.get(reverse("saldo_devedor_list"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context_data["saldo_atual"], Decimal("60.00"))
        self.assertContains(resposta, "Conta eventual")
        self.assertContains(resposta, "Parcela paga")
        self.assertContains(resposta, "Saldo em aberto")

    def test_telas_exigem_login(self):
        self.client.logout()
        for nome in ("saldo_devedor_list", "saldo_devedor_create"):
            with self.subTest(url=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 302)
                self.assertIn("/login/", resposta.url)
