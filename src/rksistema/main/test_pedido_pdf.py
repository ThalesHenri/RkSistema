"""Testes da emissão de PDF de pedidos de clientes.

Cobre:
- Serviço: gerar_pdf_pedido e gerar_pdf_relatorio_pedidos geram PDFs válidos;
  o campo Total usa o preço efetivo (negociado OU preço atual do SKU).
- Views: exigem login, emitem application/pdf e respeitam filtros.

Rode com:
    python manage.py test main.test_pedido_pdf
"""

import base64
import re
import zlib
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import (
    Categoria,
    Deposito,
    Movimentacao,
    Parceiro,
    Produto,
    SKU,
    UnidadeMedida,
)
from main.views.services.pedido_pdf_service import (
    gerar_pdf_pedido,
    gerar_pdf_relatorio_pedidos,
    _estilos,
    _total,
)
from main.views.services.registrar_entrada_service import RegistrarEntradaService
from main.views.services.registrar_saida_service import RegistrarSaidaService


def _texto_pdf(pdf_bytes):
    """Extrai o conteúdo (descomprimido) dos streams de um PDF do ReportLab.

    O ReportLab codifica o stream com ASCII85 + FlateDecode; aqui invertemos
    essa codificação para poder inspecionar o texto realmente desenhado.
    Caracteres não-ASCII das fontes padrão vêm como escapes octais (ex.:
    \252 = "ª"); decodificamos para comparar com bytes legíveis.
    """
    conteudos = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        dados = m.group(1)
        if dados.endswith(b"~>"):
            dados = base64.a85decode(dados, adobe=True)
        for _ in range(3):
            try:
                dados = zlib.decompress(dados)
                break
            except zlib.error:
                break
        # Decodifica escapes octais (\ooo) usados pelo ReportLab
        dados = re.sub(rb"\\([0-7]{3})", lambda e: bytes([int(e.group(1), 8)]), dados)
        conteudos.append(dados)
    return b"\n".join(conteudos)


class BasePedidoPdfTestCase(TestCase):
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

    def _saida(self, quantidade="10", origem="VENDA", preco=None, parceiro=None):
        return RegistrarSaidaService.executar(
            sku=self.sku,
            deposito=self.deposito,
            quantidade=Decimal(quantidade),
            origem=origem,
            usuario=self.usuario,
            parceiro=parceiro or self.cliente,
            preco_unitario=preco,
        )


class NumeroDoPedidoNoPdfTestCase(BasePedidoPdfTestCase):
    """O PDF (título, filename) usa o nº do PEDIDO, não o da movimentação."""

    def setUp(self):
        self._entrada("100")
        produto2 = Produto.objects.create(
            nome="Saco Plástico",
            tipo_produto="PRODUTO_ACABADO",
            categoria=self.categoria,
        )
        self.sku2 = SKU.objects.create(
            produto=produto2,
            codigo="SP-001",
            unidade_medida=self.unidade,
            preco_venda=Decimal("5.00"),
            preco_custo=Decimal("2.00"),
        )
        RegistrarEntradaService.executar(
            sku=self.sku2,
            deposito=self.deposito,
            quantidade=Decimal("50"),
            origem="COMPRA",
            usuario=self.usuario,
        )
        self.movimentacoes = RegistrarSaidaService.executar_varios(
            itens=[
                {"sku": self.sku, "quantidade": Decimal("2"),
                 "preco_unitario": Decimal("8.50")},
                {"sku": self.sku2, "quantidade": Decimal("3"),
                 "preco_unitario": Decimal("5.00")},
            ],
            deposito=self.deposito,
            origem="VENDA",
            usuario=self.usuario,
            parceiro=self.cliente,
        )
        self.pedido = self.movimentacoes[0].pedido

    def test_pdf_mostra_numero_do_pedido_nao_da_movimentacao(self):
        item = self.movimentacoes[0]
        pdf = gerar_pdf_pedido(item, usuario=self.usuario)
        texto = _texto_pdf(pdf).decode("latin-1")
        self.assertIn(f"#{self.pedido.pk}", texto)
        # O nº das movimentações (de outras tabelas) não aparece no lugar —
        # salvo colisão de auto-increment entre as tabelas Pedido/Movimentacao.
        for mov in self.movimentacoes:
            if mov.pk != self.pedido.pk:
                self.assertNotIn(f"#{mov.pk}", texto)

    def test_view_filename_usa_numero_do_pedido(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(
            reverse("movimentacao_pdf", args=[self.movimentacoes[1].pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            f'filename="pedido-{self.pedido.pk}.pdf"',
            resp["Content-Disposition"],
        )


class ServicoPedidoPdfTestCase(BasePedidoPdfTestCase):
    def setUp(self):
        self._entrada()
        self.saida = self._saida(
            quantidade="5", preco=Decimal("8.50"), origem="VENDA"
        )

    def test_pdf_pedido_valido(self):
        pdf = gerar_pdf_pedido(self.saida, usuario=self.usuario)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertGreater(len(pdf), 500)

    def test_pdf_pedido_usa_fontes_ampliadas(self):
        estilos_normais = _estilos()
        estilos_pedido = _estilos(ampliado=True)
        self.assertGreater(
            estilos_pedido["celula"].fontSize,
            estilos_normais["celula"].fontSize,
        )
        self.assertGreater(
            estilos_pedido["valor"].fontSize,
            estilos_normais["valor"].fontSize,
        )

    def test_pdf_pedido_tem_separador_de_tesoura_monocromatico(self):
        conteudo = _texto_pdf(gerar_pdf_pedido(self.saida, usuario=self.usuario))
        self.assertIn(b"[3 2] 0 d", conteudo)
        self.assertIn(b"0 0 0 RG", conteudo)
        self.assertNotIn(b".831373 .686275 .215686", conteudo)

    def test_total_usa_preco_fallback_do_sku(self):
        # Sem preço negociado na venda, a prop `valor_total` do modelo volta None
        # (por isso o PDF usava "—" na coluna Total). O total deve ser recalculado
        # com o preço atual do SKU: 5 x R$ 10,00 = R$ 50,00.
        saida_sem_preco = self._saida(quantidade="5", preco=None)
        self.assertIsNone(saida_sem_preco.preco_unitario)
        self.assertIsNone(saida_sem_preco.valor_total)
        self.assertEqual(_total(saida_sem_preco), Decimal("50.00"))

        pdf = gerar_pdf_pedido(saida_sem_preco, usuario=self.usuario)
        conteudo = _texto_pdf(pdf)
        self.assertIn(b"50.00", conteudo)  # total = 5 x R$ 10,00 (preço do SKU)
        self.assertIn(b"10.00", conteudo)  # preço unitário = preco_venda do SKU

    def test_pdf_pedido_tem_duas_vias_e_dados_de_pagamento(self):
        self.saida.forma_pagamento = "PIX"
        self.saida.prazo_pagamento = "30 dias"
        self.saida.save(update_fields=["forma_pagamento", "prazo_pagamento"])

        pdf = gerar_pdf_pedido(self.saida, usuario=self.usuario)
        conteudo = _texto_pdf(pdf)

        # Duas vias na mesma página
        self.assertIn("1ª VIA".encode("latin-1"), conteudo)
        self.assertIn("2ª VIA".encode("latin-1"), conteudo)
        self.assertIn(b"RECIBO DE ENTREGA", conteudo)  # 2ª via destacada
        self.assertIn("PREÇO TOTAL DO PEDIDO".encode("latin-1"), conteudo)
        self.assertEqual(conteudo.count(b"Assinatura:"), 2)  # uma assinatura por via

        # Forma de pagamento e prazo presentes
        self.assertIn(b"Forma de pagamento", conteudo)
        self.assertIn(b"Prazo de pagamento", conteudo)
        self.assertIn(b"Pix", conteudo)
        self.assertIn(b"30 dias", conteudo)

        # Removidos do PDF do pedido: status, depósito e lote
        self.assertNotIn(b"Status do pedido", conteudo)
        self.assertNotIn("Depósito".encode("latin-1"), conteudo)
        self.assertNotIn(b"Lote", conteudo)

    # --- faixas vazadas (economia de tinta) + resumo nas duas vias ----------

    def test_pdf_pedido_vazado_sem_retangulos_pretos(self):
        # As faixas pretas (1ª via, RECIBO DE ENTREGA, cabeçalho da tabela de
        # itens) viraram vazadas: o PDF não pode conter NENHUM retângulo
        # preenchido (operador "re f"). O destaque agora é por contorno.
        conteudo = _texto_pdf(gerar_pdf_pedido(self.saida, usuario=self.usuario))
        self.assertNotIn(b"re f", conteudo)
        # os textos dos antigos banners seguem presentes (agora pretos)
        self.assertIn("1ª VIA".encode("latin-1"), conteudo)
        self.assertIn("2ª VIA".encode("latin-1"), conteudo)
        self.assertIn(b"RECIBO DE ENTREGA", conteudo)

    def test_total_do_pedido_aparece_nas_duas_vias(self):
        # Antes só a 1ª via trazia a linha de total; agora as duas mostram.
        conteudo = _texto_pdf(gerar_pdf_pedido(self.saida, usuario=self.usuario))
        self.assertEqual(
            conteudo.count("PREÇO TOTAL DO PEDIDO".encode("latin-1")), 2
        )
        # 5 x R$ 8,50 = R$ 42,50 (preço negociado)
        self.assertIn(b"42.50", conteudo)

    def test_relatorio_vazado_sem_faixa_preta_e_usa_qtd(self):
        conteudo = _texto_pdf(
            gerar_pdf_relatorio_pedidos(
                Movimentacao.objects.filter(pk=self.saida.pk),
                usuario=self.usuario,
            )
        )
        # Listras/cabeçalho/TOTAL sem preenchimento preto (só listra cinza-clara
        # e texto; preto aparece apenas como cor de TEXTO, nunca de retângulo).
        self.assertIsNone(re.search(rb"0 0 0 rg\s*[0-9.\- ]+re f", conteudo))
        # Cabeçalho em português: Qtd. (não mais a abreviação "Cant.")
        self.assertIn(b"Qtd.", conteudo)
        self.assertNotIn(b"Cant.", conteudo)

class ViewPedidoPdfTestCase(BasePedidoPdfTestCase):
    def setUp(self):
        self._entrada()
        self.saida = self._saida(
            quantidade="5", preco=Decimal("8.50"), origem="VENDA"
        )

    def test_pdf_pedido_exige_login(self):
        resp = self.client.get(reverse("movimentacao_pdf", args=[self.saida.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_pdf_pedido_emitido_para_venda(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacao_pdf", args=[self.saida.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        # Venda avulsa (sem Pedido): fallback usa o próprio nº da movimentação.
        self.assertIn(
            f'attachment; filename="pedido-{self.saida.pk}.pdf"',
            resp["Content-Disposition"],
        )
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_pedido_oculta_preco_unitario_quando_solicitado(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(
            reverse("movimentacao_pdf", args=[self.saida.pk]),
            {"ocultar_valor_unitario": "1"},
        )

        self.assertEqual(resp.status_code, 200)
        conteudo = _texto_pdf(resp.content)
        self.assertNotIn(b"Pre\xe7o unit.", conteudo)
        self.assertNotIn(b"8.50", conteudo)
        self.assertIn(b"42.50", conteudo)

    def test_pdf_pedido_movimento_nao_venda_redireciona(self):
        perda = self._saida(origem="PERDA")
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacao_pdf", args=[perda.pk]))
        self.assertRedirects(resp, reverse("movimentacoes"))

    def test_pdf_relatorio_exige_login(self):
        resp = self.client.get(reverse("movimentacoes_relatorio_pdf"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_pdf_relatorio_emitido(self):
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("movimentacoes_relatorio_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(
            'attachment; filename="pedidos-clientes.pdf"',
            resp["Content-Disposition"],
        )
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_relatorio_filtra_por_status(self):
        faturada = self._saida(quantidade="2", preco=Decimal("5.00"))
        faturada.status_pedido = "FATURADO"
        faturada.save(update_fields=["status_pedido"])
        self.client.force_login(self.usuario)

        capturado = {}

        def fake_gerar(movimentacoes, filtros=None, usuario=None):
            capturado["ids"] = set(movimentacoes.values_list("id", flat=True))
            capturado["filtros"] = filtros
            return b"%PDF-1.4 teste"

        with patch(
            "main.views.pages.pedidos_pdf.gerar_pdf_relatorio_pedidos",
            side_effect=fake_gerar,
        ):
            resp = self.client.get(
                reverse("movimentacoes_relatorio_pdf"), {"status": "FATURADO"}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(capturado["ids"], {faturada.pk})
        self.assertEqual(capturado["filtros"]["status"], "Faturado")

    def test_pdf_relatorio_filtra_por_parceiro(self):
        saida_b = self._saida(parceiro=self.cliente2)
        self.client.force_login(self.usuario)

        capturado = {}

        def fake_gerar(movimentacoes, filtros=None, usuario=None):
            capturado["ids"] = set(movimentacoes.values_list("id", flat=True))
            capturado["filtros"] = filtros
            return b"%PDF-1.4 teste"

        with patch(
            "main.views.pages.pedidos_pdf.gerar_pdf_relatorio_pedidos",
            side_effect=fake_gerar,
        ):
            resp = self.client.get(
                reverse("movimentacoes_relatorio_pdf"),
                {"parceiro": self.cliente2.pk},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(capturado["ids"], {saida_b.pk})
        self.assertEqual(capturado["filtros"]["parceiro"], "Cliente B LTDA")
    def test_pdf_relatorio_valido(self):
        pdf = gerar_pdf_relatorio_pedidos(
            Movimentacao.objects.filter(pk=self.saida.pk),
            filtros={"status": "Pendente"},
            usuario=self.usuario,
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_pdf_relatorio_vazio_nao_quebra(self):
        pdf = gerar_pdf_relatorio_pedidos(
            Movimentacao.objects.none(), usuario=self.usuario
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))