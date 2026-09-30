"""
Testes da produção com cliente destino e do painel "Saldos por cliente".

A produção pode informar um cliente (parceiro); o cliente é gravado na ENTRADA
do produto acabado. Em /estoque/, o saldo por cliente de um SKU é:

    entradas de PRODUCAO destinadas − saídas de pedidos explicitamente reservados

apenas para parceiros tipo CLIENTE/AMBOS. Itens de orçamento (delta 0) nunca
entram nessa conta.

Rode com:
    python manage.py test main.test_producao_cliente
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import (
    AjusteSaldoCliente,
    Categoria,
    Deposito,
    Movimentacao,
    Parceiro,
    Produto,
    SKU,
    UnidadeMedida,
)
from main.views.services.calcular_saldo_service import CalcularSaldoService
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_producao_service import RegistrarProducaoService
from main.views.services.registrar_saida_service import RegistrarSaidaService


class ProducaoClienteTestCase(TestCase):
    """Chapa vira caixa destinada a um cliente; vendas abatem o saldo do cliente."""

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

        cls.cliente = Parceiro.objects.create(
            tipo="CLIENTE", razao_social="Cliente Alpha Ltda", cnpj_cpf="11111111000111"
        )
        cls.outro_cliente = Parceiro.objects.create(
            tipo="CLIENTE", razao_social="Cliente Beta Ltda", cnpj_cpf="22222222000122"
        )
        cls.fornecedor = Parceiro.objects.create(
            tipo="FORNECEDOR", razao_social="Fornecedor Gama", cnpj_cpf="33333333000133"
        )

        # Estoque de matéria-prima para as produções
        RegistrarEntradaService.executar(
            sku=cls.sku_mp,
            deposito=cls.deposito,
            quantidade=Decimal("100"),
            origem="COMPRA",
            usuario=cls.usuario,
        )

    def _produzir(self, quantidade, cliente=None):
        return RegistrarProducaoService.executar(
            materia_prima=self.sku_mp,
            quantidade_materia_prima=Decimal("10"),
            produto_acabado=self.sku_pa,
            quantidade_produzida=Decimal(quantidade),
            deposito=self.deposito,
            usuario=self.usuario,
            parceiro=cliente,
        )

    def _painel(self, deposito_id=None):
        self.client.force_login(self.usuario)
        url = reverse("estoque")
        if deposito_id:
            url = f"{url}?deposito={deposito_id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        return resp.context["saldos_clientes_painel"]

    def _saldo_no_painel(self, painel, cliente, sku):
        for grupo in painel:
            if grupo["cliente"] != str(cliente):
                continue
            for item in grupo["itens"]:
                if item["sku"].pk == sku.pk:
                    return item
        return None

    # --- serviço -----------------------------------------------------------

    def test_producao_carimba_cliente_apenas_na_entrada(self):
        resultado = self._produzir("5", cliente=self.cliente)

        self.assertEqual(resultado["entrada"].parceiro, self.cliente)
        # A baixa da matéria-prima não pertence ao cliente
        self.assertIsNone(resultado["saida"].parceiro)


    # --- painel em /estoque/ -----------------------------------------------

    def test_painel_mostra_saldo_destinado_ao_cliente(self):
        self._produzir("5", cliente=self.cliente)

        item = self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa)
        self.assertIsNotNone(item, "cliente deveria aparecer no painel")
        self.assertEqual(item["saldo"], Decimal("5"))
        self.assertFalse(item["negativo"])

    def test_producao_sem_cliente_nao_aparece_no_painel(self):
        self._produzir("5")
        self.assertEqual(self._painel(), [])

    def test_fornecedor_nao_aparece_no_painel(self):
        self._produzir("5", cliente=self.fornecedor)
        self.assertEqual(self._painel(), [])

    def test_venda_comum_para_o_mesmo_cliente_nao_abate_saldo_destinado(self):
        self._produzir("5", cliente=self.cliente)
        # A venda comum reduz o estoque geral, mas não toca o saldo destinado.
        RegistrarSaidaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("2"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )

        item = self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa)
        self.assertEqual(item["saldo"], Decimal("5"))
        # O estoque geral foi abatido (2 caixas saíram).
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("3"),
        )

    def test_pedido_reservado_abate_o_saldo_do_cliente(self):
        self._produzir("5", cliente=self.cliente)
        saidas = RegistrarSaidaService.executar_varios(
            itens=[{
                "sku": self.sku_pa,
                "quantidade": Decimal("2"),
                "parceiro": self.cliente,
            }],
            deposito=self.deposito,
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
            reservado=True,
        )

        item = self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa)
        self.assertEqual(item["saldo"], Decimal("3"))
        self.assertTrue(saidas[0].pedido.reservado)

    def test_venda_para_outro_ou_sem_cliente_nao_abate(self):
        self._produzir("5", cliente=self.cliente)
        RegistrarSaidaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("2"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.outro_cliente,
        )
        RegistrarSaidaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("1"),
            origem="VENDA",
            usuario=self.usuario,
        )

        item = self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa)
        self.assertEqual(item["saldo"], Decimal("5"))

    def test_entrega_alem_do_destinado_fica_negativa(self):
        # 5 destinados ao cliente + 10 entram sem destino
        self._produzir("5", cliente=self.cliente)
        RegistrarEntradaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("10"),
            origem="OUTRA",
            usuario=self.usuario,
        )
        # Reserva 8 ao cliente: 5 destinados − 8 = −3.
        RegistrarSaidaService.executar_varios(
            itens=[{"sku": self.sku_pa, "quantidade": Decimal("8"), "parceiro": self.cliente}],
            deposito=self.deposito,
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
            reservado=True,
        )

        item = self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa)
        self.assertEqual(item["saldo"], Decimal("-3"))
        self.assertTrue(item["negativo"])
        # global: 5 + 10 − 8 = 7
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            Decimal("7"),
        )

    def test_venda_de_sku_nunca_destinado_nao_gera_negativo(self):
        # Estoque geral entra SEM cliente e é vendido AO cliente: nunca houve
        # estoque destinado a ele, entao o par (SKU x cliente) nao pode aparecer
        # no painel nem acusar "entregue alem do destinado".
        RegistrarEntradaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("20"),
            origem="OUTRA",
            usuario=self.usuario,
        )
        RegistrarSaidaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("8"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )

        self.assertIsNone(
            self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa),
            "venda de estoque nunca destinado nao deve gerar linha no painel",
        )

    def test_entrada_com_cliente_que_nao_veio_de_producao_nao_e_destinada(self):
        RegistrarEntradaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("10"),
            origem="COMPRA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )

        self.assertIsNone(self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa))

    # --- limpeza / desvincular entrada individual ---------------------------

    def test_painel_mostra_botao_limpar_e_expansao_de_entradas(self):
        self._produzir("5", cliente=self.cliente)
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("estoque"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("saldos_clientes_limpar"))
        self.assertContains(resp, "Limpar saldos por cliente")
        self.assertContains(resp, "ver entradas (1)")
        self.assertContains(resp, reverse("movimentacao_desvincular_cliente", args=[
            Movimentacao.objects.filter(origem="PRODUCAO", tipo="ENTRADA")[0].pk
        ]))

    def test_edicao_inline_atualiza_saldo_sem_alterar_estoque_fisico(self):
        self._produzir("5", cliente=self.cliente)
        estoque_antes = CalcularSaldoService.executar(
            sku=self.sku_pa, deposito=self.deposito
        )
        self.client.force_login(self.usuario)
        resposta = self.client.post(
            reverse(
                "saldo_cliente_atualizar",
                args=[self.cliente.pk, self.sku_pa.pk],
            ),
            {"saldo": "3.25", "deposito": ""},
        )

        self.assertRedirects(resposta, reverse("estoque"))
        item = self._saldo_no_painel(
            self._painel(), self.cliente, self.sku_pa
        )
        self.assertEqual(item["saldo"], Decimal("3.25"))
        self.assertEqual(AjusteSaldoCliente.objects.count(), 1)
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            estoque_antes,
        )
        page = self.client.get(reverse("estoque"))
        self.assertContains(
            page,
            reverse("saldo_cliente_atualizar", args=[self.cliente.pk, self.sku_pa.pk]),
        )

    def test_painel_tem_regiao_rolavel_e_exibe_cliente_em_cada_item(self):
        self._produzir("5", cliente=self.cliente)
        self._produzir("3", cliente=self.outro_cliente)
        self.client.force_login(self.usuario)

        resp = self.client.get(reverse("estoque"))

        self.assertContains(resp, 'class="cartao-tabela tabela-rolagem-clientes"')
        self.assertContains(resp, "dica-rolagem-clientes")
        self.assertContains(resp, str(self.cliente))
        self.assertContains(resp, str(self.outro_cliente))

    def test_limpar_saldos_exige_login(self):
        resp = self.client.get(reverse("saldos_clientes_limpar"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_limpar_saldos_mostra_confirmacao_com_contagem(self):
        self._produzir("5", cliente=self.cliente)
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("saldos_clientes_limpar"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1 entrada(s) de produção")
        self.assertContains(resp, "Desvincular cliente das produções")

    def test_limpar_saldos_zera_painel_e_so_mexe_em_entradas(self):
        self._produzir("5", cliente=self.cliente)
        saida = RegistrarSaidaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("2"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )
        saldo_antes = CalcularSaldoService.executar(
            sku=self.sku_pa, deposito=self.deposito
        )

        self.client.force_login(self.usuario)
        resp = self.client.post(reverse("saldos_clientes_limpar"))
        self.assertRedirects(resp, reverse("estoque"))

        # painel zerado: entradas sem cliente => par descartado
        self.assertEqual(self._painel(), [])
        self.assertFalse(
            Movimentacao.objects.filter(tipo="ENTRADA", parceiro__isnull=False).exists()
        )
        # a venda mantém o vínculo com o cliente (filtros/relatórios)
        saida.refresh_from_db()
        self.assertEqual(saida.parceiro, self.cliente)
        # saldo global de estoque inalterado
        self.assertEqual(
            CalcularSaldoService.executar(sku=self.sku_pa, deposito=self.deposito),
            saldo_antes,
        )

    def test_desvincular_entrada_individual(self):
        primeira = self._produzir("5", cliente=self.cliente)["entrada"]
        outra = self._produzir("3", cliente=self.outro_cliente)["entrada"]

        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_desvincular_cliente", args=[primeira.pk])
        )
        self.assertRedirects(resp, reverse("estoque"))

        primeira.refresh_from_db()
        self.assertIsNone(primeira.parceiro)
        outra.refresh_from_db()
        self.assertEqual(outra.parceiro, self.outro_cliente)
        # o par (cliente, sku) some do painel; o outro cliente permanece
        self.assertIsNone(self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa))
        self.assertIsNotNone(self._saldo_no_painel(self._painel(), self.outro_cliente, self.sku_pa))
        # a movimentação continua existindo (estoque não muda)
        self.assertTrue(Movimentacao.objects.filter(pk=primeira.pk).exists())

    def test_desvincular_rejeita_saida(self):
        RegistrarEntradaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("10"),
            origem="OUTRA",
            usuario=self.usuario,
        )
        saida = RegistrarSaidaService.executar(
            sku=self.sku_pa,
            deposito=self.deposito,
            quantidade=Decimal("2"),
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_desvincular_cliente", args=[saida.pk]), follow=True,
        )
        self.assertRedirects(resp, reverse("estoque"))
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("Só é possível desvincular" in m for m in msgs), msgs)
        saida.refresh_from_db()
        self.assertEqual(saida.parceiro, self.cliente)

    def test_desvincular_exige_login(self):
        entrada = self._produzir("5", cliente=self.cliente)["entrada"]
        resp = self.client.post(
            reverse("movimentacao_desvincular_cliente", args=[entrada.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)
        entrada.refresh_from_db()
        self.assertEqual(entrada.parceiro, self.cliente)

    # --- formulário da página de produção -----------------------------------

    def test_pagina_producao_com_cliente_destino(self):
        self.client.force_login(self.usuario)
        resp = self.client.post(
            reverse("movimentacao_producao"),
            {
                "materia_prima": self.sku_mp.id,
                "quantidade_materia_prima": "10",
                "produto_acabado": self.sku_pa.id,
                "quantidade_produzida": "4",
                "deposito": self.deposito.id,
                "parceiro": self.cliente.id,
                "documento": "OP-CLI-01",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Movimentacao.objects.filter(
                origem="PRODUCAO", tipo="ENTRADA", parceiro=self.cliente
            ).exists(),
            "entrada da produção deveria ficar vinculada ao cliente",
        )
        item = self._saldo_no_painel(self._painel(), self.cliente, self.sku_pa)
        self.assertIsNotNone(item, "a produção recém-registrada deve aparecer no saldo do cliente")
        self.assertEqual(item["saldo"], Decimal("4"))

    def test_formulario_producao_oferece_apenas_clientes(self):
        from main.forms import ProducaoForm

        form = ProducaoForm()
        opcoes = {opcao.pk for opcao in form.fields["parceiro"].queryset}
        self.assertEqual(opcoes, {self.cliente.pk, self.outro_cliente.pk})

    def test_producao_sem_cliente_fica_com_parceiro_nulo(self):
        resultado = self._produzir("5")
        self.assertIsNone(resultado["entrada"].parceiro)
