"""Geração de PDFs de pedidos de clientes (ReportLab).

O "pedido de cliente" é uma movimentação de SAIDA com origem VENDA (ver
registrar_saida_service.py). Este serviço produz dois documentos:

- gerar_pdf_pedido(...)          → PDF individual por pedido com DUAS VIAS na
                                   mesma página (1ª via fica com a empresa;
                                   2ª via para o cliente, destacada e com recibo).
- gerar_pdf_relatorio_pedidos()  → listado filtrável de vários pedidos.

Rode os testes com:
    python manage.py test main.test_pedido_pdf
"""

from datetime import datetime
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Paleta do frontend — RK Embalagens (ver main/static/main/css/style.css)
COR_PRIMARIA = colors.black
COR_PRIMARIA_ESCURA = colors.black
COR_DOURADO = colors.black
COR_TEXTO = colors.black
COR_TEXTO_SUAVE = colors.HexColor("#444444")
COR_BORDA = colors.HexColor("#777777")
COR_STRIPE = colors.HexColor("#eeeeee")


def _estilos(*, ampliado=False):
    """Estilos do PDF; `ampliado` prioriza legibilidade no pedido individual."""
    base = getSampleStyleSheet()
    escala = 1.2 if ampliado else 1
    return {
        "marca": ParagraphStyle(
            "marca", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=10 * escala, leading=12 * escala, textColor=COR_PRIMARIA,
        ),
        "titulo": ParagraphStyle(
            "titulo", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18 * escala, leading=22 * escala, textColor=COR_PRIMARIA_ESCURA,
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo", parent=base["Normal"], fontName="Helvetica",
            fontSize=10 * escala, leading=12 * escala, textColor=COR_TEXTO_SUAVE,
        ),
        "rotulo": ParagraphStyle(
            "rotulo", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9 * escala, leading=11 * escala, textColor=COR_TEXTO_SUAVE,
        ),
        "valor": ParagraphStyle(
            "valor", parent=base["Normal"], fontName="Helvetica",
            fontSize=10 * escala, leading=12 * escala, textColor=COR_TEXTO,
        ),
        "celula": ParagraphStyle(
            "celula", parent=base["Normal"], fontName="Helvetica",
            fontSize=9 * escala, leading=11 * escala,
        ),
        "celula_bold": ParagraphStyle(
            "celula_bold", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9 * escala, leading=11 * escala,
        ),
        "celula_direita": ParagraphStyle(
            "celula_direita", parent=base["Normal"], fontName="Helvetica",
            fontSize=9 * escala, leading=11 * escala, alignment=TA_RIGHT,
        ),
        "celula_bold_direita": ParagraphStyle(
            "celula_bold_direita", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9 * escala, leading=11 * escala, alignment=TA_RIGHT,
        ),
    }


def _nome_usuario(usuario):
    if not usuario:
        return "—"
    return (usuario.get_full_name() or usuario.username).strip() or usuario.username


def _descricao_sku(sku):
    detalhe = " ".join(filter(None, [sku.tamanho_capacidade, sku.cor]))
    base = f"{sku.produto.nome} — {sku.codigo}"
    return f"{base} ({detalhe})" if detalhe else base


def _preco_unitario(movimentacao):
    """Preço unitário negociado na movimentação; senão, preço atual do SKU."""
    if movimentacao.preco_unitario is not None:
        return movimentacao.preco_unitario
    return movimentacao.sku.preco_venda


def _total(movimentacao):
    """Total monetário usando o preço efetivo (negociado ou preço atual do SKU).

    NOTE: a prop `Movimentacao.valor_total` do modelo só considera o preço
    negociado (`preco_unitario`) e retorna None quando ele está vazio — por isso
    aqui recalculamos com _preco_unitario() para o PDF nunca mostrar preço
    unitário sem total correspondente.
    """
    preco = _preco_unitario(movimentacao)
    if preco is None:
        return None
    return preco * movimentacao.quantidade


def _itens_pedido(movimentacao):
    if movimentacao.pedido_id:
        return list(movimentacao.pedido.itens.select_related(
            "sku", "sku__produto", "sku__unidade_medida"
        ).all())
    return [movimentacao]


def _total_pedido(movimentacao):
    totais = [_total(item) for item in _itens_pedido(movimentacao)]
    if any(total is None for total in totais):
        return None
    return sum(totais, Decimal("0"))


def _moeda(valor):
    if valor is None:
        return "—"
    return f"R$ {Decimal(valor):.2f}"


def _cabecalho(titulo, subtitulo):
    """Bloque de cabeçalho comum: marca + título (lista plana de Flowables)."""
    return [
        Paragraph("RK Embalagens — Gestão de estoque", _estilos()["marca"]),
        Paragraph(
            f"Emitido: {datetime.now():%d/%m/%Y %H:%M}",
            _estilos()["subtitulo"],
        ),
        Spacer(1, 2 * mm),
        Paragraph(titulo, _estilos()["titulo"]),
        Paragraph(subtitulo, _estilos()["subtitulo"]),
        Spacer(1, 4 * mm),
    ]


def _fila_rotulo_valor(rotulo, valor, estilos=None):
    estilos = estilos or _estilos()
    return [
        Paragraph(rotulo, estilos["rotulo"]),
        Paragraph(valor, estilos["valor"]),
    ]


def _datos_pedido(movimentacao, estilos=None):
    estilos = estilos or _estilos()
    return [
        _fila_rotulo_valor("Documento", movimentacao.documento or "—", estilos),
        _fila_rotulo_valor(
            "Forma de pagamento",
            movimentacao.get_forma_pagamento_display() or "—",
            estilos,
        ),
        _fila_rotulo_valor(
            "Prazo de pagamento", movimentacao.prazo_pagamento or "—", estilos
        ),
        _fila_rotulo_valor(
            "Data da movimentação",
            f"{movimentacao.data_movimentacao:%d/%m/%Y %H:%M}",
            estilos,
        ),
    ]


def _datos_cliente(parceiro, estilos=None):
    estilos = estilos or _estilos()
    if parceiro is None:
        return [_fila_rotulo_valor("Cliente", "—", estilos)]
    linhas = [_fila_rotulo_valor("Cliente", parceiro.razao_social, estilos)]
    if parceiro.nome_fantasia:
        linhas.append(_fila_rotulo_valor("Nome fantasia", parceiro.nome_fantasia, estilos))
    linhas.append(_fila_rotulo_valor("CNPJ/CPF", parceiro.cnpj_cpf, estilos))
    if parceiro.endereco:
        linhas.append(_fila_rotulo_valor("Endereço", parceiro.endereco, estilos))
    if parceiro.telefone:
        linhas.append(_fila_rotulo_valor("Telefone", parceiro.telefone, estilos))
    if parceiro.email:
        linhas.append(_fila_rotulo_valor("E-mail", parceiro.email, estilos))
    return linhas


def _tabla_rotulo_valor(datos, col1, col2):
    tabla = Table(datos, colWidths=[col1, col2])
    tabla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return tabla


def _tabla_item(movimentacao, estilos=None):
    s = estilos or _estilos()
    cabeceras = [
        Paragraph("Produto / SKU", s["celula_bold"]),
        Paragraph("Unidade", s["celula_bold"]),
        Paragraph("Quantidade", s["celula_bold_direita"]),
        Paragraph("Preço unit.", s["celula_bold_direita"]),
        Paragraph("Total", s["celula_bold_direita"]),
    ]
    filas = [cabeceras]
    for item in _itens_pedido(movimentacao):
        filas.append([
            Paragraph(_descricao_sku(item.sku), s["celula"]),
            Paragraph(item.sku.unidade_medida.sigla, s["celula"]),
            Paragraph(f"{item.quantidade:.2f}", s["celula_direita"]),
            Paragraph(_moeda(_preco_unitario(item)), s["celula_direita"]),
            Paragraph(_moeda(_total(item)), s["celula_bold_direita"]),
        ])
    tabla = Table(
        filas,
        colWidths=[86 * mm, 20 * mm, 22 * mm, 26 * mm, 26 * mm],
    )
    tabla.setStyle(
        TableStyle(
            [
                # Cabeçalho vazado (sem faixa preta) para economizar tinta:
                # o destaque vem do GRID + linha própria abaixo do cabeçalho.
                ("GRID", (0, 0), (-1, -1), 0.4, COR_BORDA),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return tabla


def _pie_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(COR_TEXTO_SUAVE)
    canvas.drawCentredString(
        A4[0] / 2,
        9 * mm,
        f"RK Embalagens · Página {doc.page} · Emitido {datetime.now():%d/%m/%Y %H:%M}",
    )
    canvas.restoreState()


class _LinhaTesoura(Flowable):
    """Separador tracejado com tesoura vetorial entre as duas vias."""

    def __init__(self, largura, altura=10 * mm):
        super().__init__()
        self.width = largura
        self.height = altura

    def draw(self):
        canvas = self.canv
        centro_x = self.width / 2
        centro_y = self.height / 2

        canvas.saveState()
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(0.8)
        canvas.setDash(3, 2)
        canvas.line(0, centro_y, centro_x - 8, centro_y)
        canvas.line(centro_x + 8, centro_y, self.width, centro_y)
        canvas.setDash()

        # Anéis à esquerda, articulação no centro e lâminas apontadas à direita.
        canvas.setLineWidth(1.2)
        canvas.circle(centro_x - 4, centro_y + 2.8, 2.1, stroke=1, fill=0)
        canvas.circle(centro_x - 4, centro_y - 2.8, 2.1, stroke=1, fill=0)
        canvas.line(centro_x - 2.2, centro_y + 1.7, centro_x + 1.2, centro_y)
        canvas.line(centro_x - 2.2, centro_y - 1.7, centro_x + 1.2, centro_y)
        canvas.circle(centro_x + 1.2, centro_y, 0.8, stroke=1, fill=0)
        canvas.line(centro_x + 1.2, centro_y, centro_x + 6, centro_y + 3.4)
        canvas.line(centro_x + 1.2, centro_y, centro_x + 6, centro_y - 3.4)
        canvas.restoreState()


def _banner_via(rotulo, largura, cor_fundo=None, segunda_via=False):
    """Faixa vazada que destaca qual via do pedido é esta.

    As duas vias são preto sobre branco SEM preenchimento (economia de tinta);
    o contorno (BOX) dá o destaque que a faixa cheia dava antes.
    `cor_fundo`/`segunda_via` são mantidos na assinatura por compatibilidade,
    mas não alteram mais as cores.
    """
    s = _estilos()
    estilo_banner = ParagraphStyle(
        "banner", parent=s["titulo"], fontSize=16, leading=19,
        textColor=colors.black,
    )
    banner = Table([[Paragraph(rotulo, estilo_banner)]], colWidths=[largura])
    banner.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return banner


def _recibo_entrega(movimentacao, largura, estilos=None):
    """Bloco de recibo/assinatura da 2ª via — para destacar na entrega."""
    s = estilos or _estilos()
    total = _moeda(_total_pedido(movimentacao))
    estilo_valor = ParagraphStyle(
        "recibo-valor", parent=s["celula_bold"], fontSize=11,
    )
    titulo = Table(
        [[Paragraph("RECIBO DE ENTREGA", estilo_valor)]],
        colWidths=[largura],
    )
    titulo.setStyle(
        TableStyle(
            [
                # Faixa vazada: contorno no lugar do preenchimento preto.
                ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    linhas = [
        [
            Paragraph("Recebido por:", s["celula"]),
            Paragraph("Data: ____/____/____", s["celula"]),
        ],
        [
            Paragraph("Assinatura:", s["celula"]),
            Paragraph("", s["celula"]),
        ],
        [
            Paragraph(f"Valor total: {total}", s["celula"]),
            Paragraph("", s["celula"]),
        ],
    ]
    corpo = Table(linhas, colWidths=[largura * 0.55, largura * 0.45])
    corpo.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, COR_BORDA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWHEIGHTS", (1, 0), (1, -1), 14),
            ]
        )
    )
    return [titulo, corpo]


def _conteudo_via(
    movimentacao, usuario, rotulo, largura, segunda_via=False,
    tipo_documento="PEDIDO",
):
    """Flowables de uma via (1ª ou 2ª) do pedido."""
    s = _estilos(ampliado=True)
    conteudo = []

    # Cabeçalho da via: faixa destacada + título + dados em duas colunas
    col = (largura - 4 * mm) / 2
    pedido_col = 42 * mm
    valor_col = col - pedido_col
    esq = _tabla_rotulo_valor(_datos_pedido(movimentacao, s), pedido_col, valor_col)
    dir_ = _tabla_rotulo_valor(
        _datos_cliente(movimentacao.parceiro, s), pedido_col, valor_col
    )
    celula_esq = [
        Paragraph("Dados do pedido", s["celula_bold"]),
        Spacer(1, 1 * mm),
        esq,
    ]
    celula_dir = [
        Paragraph("Dados do cliente", s["celula_bold"]),
        Spacer(1, 1 * mm),
        dir_,
    ]
    dupla = Table([[celula_esq, celula_dir]], colWidths=[col, col])
    dupla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, -1), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    titulo_via = ParagraphStyle(
        "titulo-via", parent=s["titulo"], fontSize=16, leading=19,
        spaceBefore=3 * mm, spaceAfter=1 * mm,
    )

    titulo_documento = "ORÇAMENTO" if tipo_documento == "ORCAMENTO" else "Pedido de cliente"
    conteudo.append(_banner_via(rotulo, largura, segunda_via=segunda_via))
    conteudo.append(Paragraph(f"{titulo_documento} — Nº #{movimentacao.pedido_id or movimentacao.pk}", titulo_via))
    if tipo_documento == "ORCAMENTO":
        conteudo.append(
            Paragraph("SEM VALOR FISCAL — SUJEITO A APROVAÇÃO", s["celula_bold"])
        )
    conteudo.append(
        Paragraph(f"Emitido: {datetime.now():%d/%m/%Y %H:%M}", s["subtitulo"])
    )
    conteudo.append(Spacer(1, 1 * mm))
    conteudo.append(dupla)
    conteudo.append(Spacer(1, 2 * mm))
    conteudo.append(Paragraph(
        "Itens do orçamento" if tipo_documento == "ORCAMENTO" else "Detalhes do pedido",
        s["subtitulo"],
    ))
    conteudo.append(Spacer(1, 1 * mm))
    conteudo.append(_tabla_item(movimentacao, s))
    # Linha de resumo (qtd./preço unit. por item na tabela acima) + total
    # aparece nas DUAS vias — a 2ª via não dependia do recibo para o valor.
    rotulo_total = (
        "VALOR TOTAL DO ORÇAMENTO"
        if tipo_documento == "ORCAMENTO"
        else "PREÇO TOTAL DO PEDIDO"
    )
    conteudo.append(Spacer(1, 1 * mm))
    conteudo.append(
        Paragraph(
            f"{rotulo_total}: {_moeda(_total_pedido(movimentacao))}",
            s["celula_bold_direita"],
        )
    )

    if movimentacao.observacao:
        conteudo.append(Spacer(1, 1 * mm))
        conteudo.append(Paragraph("Observações", s["subtitulo"]))
        conteudo.append(Spacer(1, 1 * mm))
        conteudo.append(Paragraph(movimentacao.observacao, s["valor"]))

    conteudo.append(Spacer(1, 2 * mm))
    conteudo.append(
        Paragraph(f"Gerado por: {_nome_usuario(usuario)}", s["subtitulo"])
    )

    if tipo_documento == "ORCAMENTO":
        conteudo.append(Spacer(1, 2 * mm))
        conteudo.append(Paragraph("APROVAÇÃO DO ORÇAMENTO", s["celula_bold"]))
        conteudo.append(Spacer(1, 2 * mm))
        conteudo.append(Paragraph("Aprovado por: ____________________________________", s["celula"]))
        conteudo.append(Paragraph("Data: ____/____/________    Assinatura: __________________________", s["celula"]))
    elif segunda_via:
        conteudo.append(Spacer(1, 2 * mm))
        conteudo.extend(_recibo_entrega(movimentacao, largura, s))
    else:
        # 1ª via do pedido: linha de assinatura da empresa — uma por via.
        conteudo.append(Spacer(1, 2 * mm))
        conteudo.append(
            Paragraph("Assinatura: ____________________________________", s["celula"])
        )

    return conteudo


def gerar_pdf_pedido(movimentacao, usuario=None, tipo_documento=None):
    """Gera o PDF individual de um pedido ou orçamento.

    Produz o pedido em UMA ÚNICA PÁGINA:
      - 1ª VIA — fica com a empresa;
      - 2ª VIA — para o cliente, destacada com recibo de entrega/assinatura.
    """

    if tipo_documento is None:
        tipo_documento = "ORCAMENTO" if movimentacao.tipo == "ORCAMENTO" else "PEDIDO"
    if tipo_documento not in {"PEDIDO", "ORCAMENTO"}:
        raise ValueError("tipo_documento deve ser 'PEDIDO' ou 'ORCAMENTO'.")

    numero_documento = movimentacao.pedido_id or movimentacao.pk
    rotulo_via_1 = (
        "ORÇAMENTO — 1ª VIA" if tipo_documento == "ORCAMENTO"
        else "1ª VIA — Fica com a empresa"
    )
    rotulo_via_2 = (
        "ORÇAMENTO — 2ª VIA" if tipo_documento == "ORCAMENTO"
        else "2ª VIA — Cliente"
    )
    margem = 12 * mm
    largura = A4[0] - 2 * margem

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margem,
        rightMargin=margem,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{'Orçamento' if tipo_documento == 'ORCAMENTO' else 'Pedido'} #{numero_documento}",
        author="RK Embalagens",
        onFirstPage=_pie_pagina,
    )

    historia = []
    historia.extend(
        _conteudo_via(
            movimentacao, usuario, rotulo_via_1, largura,
            tipo_documento=tipo_documento,
        )
    )
    historia.append(_LinhaTesoura(largura))
    historia.extend(
        _conteudo_via(
            movimentacao, usuario, rotulo_via_2, largura,
            segunda_via=True, tipo_documento=tipo_documento,
        )
    )

    doc.build(historia, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return buffer.getvalue()


def gerar_pdf_relatorio_pedidos(movimentacoes, filtros=None, usuario=None):
    """Gera o listado de pedidos de clientes filtrável.

    `movimentacoes` é um iterable de Movimentacao (saídas com origem VENDA).
    `filtros` é um dict opcional com chaves: parceiro, status.
    """
    s = _estilos()

    partes_filtro = []
    if filtros and filtros.get("parceiro"):
        partes_filtro.append(f"Cliente: {filtros['parceiro']}")
    if filtros and filtros.get("status"):
        partes_filtro.append(f"Status: {filtros['status']}")
    texto_filtro = " · ".join(partes_filtro) or "Todos os pedidos"

    historia = []
    historia.extend(_cabecalho("Relatório de pedidos de clientes", texto_filtro))
    historia.append(
        Paragraph(
            f"Gerado por: {_nome_usuario(usuario)}",
            s["subtitulo"],
        )
    )
    historia.append(Spacer(1, 4 * mm))

    cabeceras = [
        Paragraph("Data", s["celula_bold"]),
        Paragraph("Nº pedido", s["celula_bold"]),
        Paragraph("Cliente", s["celula_bold"]),
        Paragraph("SKU / Produto", s["celula_bold"]),
        Paragraph("Qtd.", s["celula_bold_direita"]),
        Paragraph("Preço unit.", s["celula_bold_direita"]),
        Paragraph("Total", s["celula_bold_direita"]),
        Paragraph("Status", s["celula_bold"]),
    ]
    filas = [cabeceras]

    total_quantidade = Decimal("0")
    total_valor = Decimal("0")
    for m in movimentacoes:
        quantidade_linha = m.quantidade
        total_quantidade += quantidade_linha
        total_linha = _total(m) or Decimal("0")
        total_valor += total_linha
        filas.append(
            [
                Paragraph(f"{m.data_movimentacao:%d/%m/%Y %H:%M}", s["celula"]),
                Paragraph(f"#{m.pk}", s["celula"]),
                Paragraph(m.parceiro.razao_social if m.parceiro else "—", s["celula"]),
                Paragraph(_descricao_sku(m.sku), s["celula"]),
                Paragraph(f"{quantidade_linha:.2f}", s["celula_direita"]),
                Paragraph(_moeda(_preco_unitario(m)), s["celula_direita"]),
                Paragraph(_moeda(total_linha), s["celula_direita"]),
                Paragraph(m.get_status_pedido_display() or "—", s["celula"]),
            ]
        )

    if len(filas) > 1:
        filas.append(
            [
                Paragraph("TOTAL", s["celula_bold"]),
                "",
                "",
                "",
                Paragraph(f"{total_quantidade:.2f}", s["celula_bold_direita"]),
                "",
                Paragraph(_moeda(total_valor), s["celula_bold_direita"]),
                "",
            ]
        )

    tabla = Table(
        filas,
        colWidths=[26 * mm, 16 * mm, 30 * mm, 42 * mm, 14 * mm, 20 * mm, 20 * mm, 16 * mm],
    )
    # Cabeçalho e TOTAL vazados (sem faixas pretas) — destaque por linhas.
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, COR_BORDA),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if len(filas) > 1:
        estilo.append(
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, COR_STRIPE])
        )
        estilo.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black))
    tabla.setStyle(TableStyle(estilo))
    historia.append(tabla)

    if len(filas) == 1:
        historia.append(Spacer(1, 4 * mm))
        historia.append(
            Paragraph("Nenhum pedido coincide com o filtro.", s["subtitulo"])
        )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Relatório de pedidos",
        author="RK Embalagens",
        onFirstPage=_pie_pagina,
        onLaterPages=_pie_pagina,
    )
    doc.build(historia, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
    return buffer.getvalue()