import re

from django import forms

from main.models import (
    Categoria,
    UnidadeMedida,
    Produto,
    SKU,
    Parceiro,
    Deposito,
)
from main.models.movimentacao import (
    ORIGEM_MOVIMENTACAO_CHOICES,
    STATUS_PEDIDO_CHOICES,
    FORMA_PAGAMENTO_CHOICES,
)


class BaseModelForm(forms.ModelForm):
    """Aplica a classe .form-control a todos os campos automaticamente."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            else:
                campo.widget.attrs.setdefault("class", "form-control")


class CategoriaForm(BaseModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["categoria_pai"].queryset = Categoria.objects.exclude(pk=self.instance.pk)
        else:
            self.fields["categoria_pai"].queryset = Categoria.objects.all()

    class Meta:
        model = Categoria
        fields = ["nome", "categoria_pai", "ativo"]


class UnidadeMedidaForm(BaseModelForm):
    class Meta:
        model = UnidadeMedida
        fields = ["sigla", "nome"]


class ProdutoForm(BaseModelForm):
    class Meta:
        model = Produto
        fields = ["tipo_produto", "nome", "categoria", "descricao", "ativo"]


class SKUForm(BaseModelForm):
    class Meta:
        model = SKU
        fields = [
            "produto",
            "codigo",
            "codigo_barras",
            "tamanho_capacidade",
            "cor",
            "unidade_medida",
            "estoque_minimo",
            "preco_custo",
            "preco_venda",
            "ativo",
        ]


class ParceiroForm(BaseModelForm):
    class Meta:
        model = Parceiro
        fields = [
            "tipo",
            "razao_social",
            "nome_fantasia",
            "cnpj_cpf",
            "telefone",
            "email",
            "endereco",
            "ativo",
        ]


class DepositoForm(BaseModelForm):
    class Meta:
        model = Deposito
        fields = ["nome", "endereco", "ativo"]


class _MovimentacaoForm(forms.Form):
    """Campos comuns de entrada/saída de estoque."""

    sku = forms.ModelChoiceField(
        queryset=SKU.objects.select_related("produto").order_by("produto__nome", "codigo"),
        label="SKU",
        help_text="Produto com suas variações (tamanho, cor etc.).",
    )
    deposito = forms.ModelChoiceField(queryset=Deposito.objects.all(), label="Depósito")
    quantidade = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0.01, label="Quantidade"
    )
    origem = forms.ChoiceField(choices=ORIGEM_MOVIMENTACAO_CHOICES, label="Origem")
    parceiro = forms.ModelChoiceField(
        queryset=Parceiro.objects.all(), required=False, label="Cliente (opcional)"
    )
    documento = forms.CharField(required=False, label="Documento (opcional)", help_text="Nº de nota fiscal, pedido etc.")
    observacao = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Observação (opcional)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            else:
                campo.widget.attrs.setdefault("class", "form-control")


class MovimentacaoEntradaForm(_MovimentacaoForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origem"].initial = "COMPRA"
        self.fields["parceiro"].label = "Fornecedor (opcional)"


class MovimentacaoSaidaForm(_MovimentacaoForm):
    preco_unitario = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False,
        label="Preço unitário (opcional)",
        help_text="Preço negociado nesta venda. Vazio = usa o preço cadastrado no SKU.",
    )
    forma_pagamento = forms.ChoiceField(
        required=False,
        choices=[("", "Sem forma definida")] + list(FORMA_PAGAMENTO_CHOICES),
        label="Forma de pagamento (opcional)",
    )
    prazo_pagamento = forms.CharField(
        required=False,
        label="Prazo de pagamento (opcional)",
        help_text="Ex.: 30 dias, à vista, 2x sem juros...",
    )
    reservado = forms.BooleanField(
        required=False,
        label="Reservar do saldo destinado ao cliente",
        help_text="Quando marcado, os itens são abatidos do saldo destinado ao cliente.",
    )
    tem_clientes_adicionais = forms.BooleanField(
        required=False,
        label="Tem clientes adicionais",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origem"].initial = "VENDA"
        self.fields["parceiro"].label = "Cliente (opcional)"
        self.itens_adicionais = []
        self.blocos = []
        self._linhas_dinamicas = []

        data = self.data
        campos = set(data.keys()) if data is not None else set()
        principais = sorted({
            int(match.group(1))
            for nome in campos
            if (match := re.fullmatch(r"(?:sku|quantidade|preco_unitario)_(\d+)", nome))
        })
        if "sku" in campos:
            principais = [indice for indice in principais if indice >= 2]
        for indice in principais:
            sufixo = f"_{indice}"
            nomes = (
                f"sku{sufixo}",
                f"quantidade{sufixo}",
                f"preco_unitario{sufixo}",
            )
            self._adicionar_linha_dinamica(*nomes)
            self.itens_adicionais.append(tuple(self[nome] for nome in nomes))

        indices_blocos = sorted({
            int(match.group(1))
            for nome in campos
            if (match := re.fullmatch(r"cliente_ad_(\d+)", nome))
        })
        for indice_bloco in indices_blocos:
            cliente_nome = f"cliente_ad_{indice_bloco}"
            self.fields[cliente_nome] = forms.ModelChoiceField(
                queryset=Parceiro.objects.filter(
                    tipo__in=("CLIENTE", "AMBOS")
                ).order_by("razao_social"),
                required=False,
                label=f"Cliente adicional {indice_bloco}",
            )
            sufixos_linhas = sorted({
                int(match.group(1))
                for nome in campos
                if (match := re.fullmatch(
                    rf"(?:sku|quantidade|preco_unitario)_{indice_bloco}_(\d+)",
                    nome,
                ))
            }) or [1]
            linhas = []
            for indice_linha in sufixos_linhas:
                prefixo = f"_{indice_bloco}_{indice_linha}"
                nomes = (
                    f"sku{prefixo}",
                    f"quantidade{prefixo}",
                    f"preco_unitario{prefixo}",
                )
                self._adicionar_linha_dinamica(*nomes)
                linhas.append({
                    "indice": indice_linha,
                    "sku": self[nomes[0]],
                    "quantidade": self[nomes[1]],
                    "preco_unitario": self[nomes[2]],
                })
            self.blocos.append({
                "indice": indice_bloco,
                "cliente": self[cliente_nome],
                "linhas": linhas,
            })

    def _adicionar_linha_dinamica(self, nome_sku, nome_quantidade, nome_preco):
        queryset_skus = SKU.objects.select_related("produto").order_by("produto__nome", "codigo")
        self.fields.setdefault(nome_sku, forms.ModelChoiceField(
            queryset=queryset_skus, required=False, label="SKU",
        ))
        self.fields.setdefault(nome_quantidade, forms.DecimalField(
            max_digits=12, decimal_places=2, min_value=0.01,
            required=False, label="Quantidade",
        ))
        self.fields.setdefault(nome_preco, forms.DecimalField(
            max_digits=12, decimal_places=2, min_value=0,
            required=False, label="Preço unitário",
        ))
        self._linhas_dinamicas.append((nome_sku, nome_quantidade, nome_preco))

    def clean(self):
        dados = super().clean()
        tem_clientes_adicionais = dados.get("tem_clientes_adicionais", False)
        for nome_sku, nome_quantidade, _nome_preco in self._linhas_dinamicas:
            if re.fullmatch(r"sku_\d+_\d+", nome_sku) and not tem_clientes_adicionais:
                continue
            sku = dados.get(nome_sku)
            quantidade = dados.get(nome_quantidade)
            if bool(sku) != bool(quantidade):
                if sku and not quantidade:
                    self.add_error(
                        nome_quantidade, "Informe a quantidade deste item."
                    )
                else:
                    self.add_error(nome_sku, "Informe o SKU deste item.")

        if tem_clientes_adicionais:
            if not self.blocos:
                self.add_error(
                    "tem_clientes_adicionais",
                    "Adicione ao menos um cliente adicional ou desmarque a opção.",
                )
            for bloco in self.blocos:
                if not bloco["cliente"].value():
                    self.add_error(
                        f"cliente_ad_{bloco['indice']}",
                        "Escolha o cliente deste bloco.",
                    )
                if not any(
                    linha["sku"].value() and linha["quantidade"].value()
                    for linha in bloco["linhas"]
                ):
                    self.add_error(
                        None,
                        "Informe pelo menos um item para este cliente adicional.",
                    )
        return dados


class MovimentacaoPrecoStatusForm(forms.Form):
    """Edição rápida de preço, status, forma de pagamento e prazo de uma saída."""

    preco_unitario = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False,
        label="Preço unitário",
    )
    status_pedido = forms.ChoiceField(
        required=False,
        choices=[("", "Sem status")] + list(STATUS_PEDIDO_CHOICES),
        label="Status do pedido",
    )
    forma_pagamento = forms.ChoiceField(
        required=False,
        choices=[("", "Sem forma definida")] + list(FORMA_PAGAMENTO_CHOICES),
        label="Forma de pagamento",
    )
    prazo_pagamento = forms.CharField(
        required=False,
        label="Prazo de pagamento",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            else:
                campo.widget.attrs.setdefault("class", "form-control")


class ProducaoForm(forms.Form):
    """Formulário de produção: matéria-prima (consumida) → produto em estoque (produzido)."""

    materia_prima = forms.ModelChoiceField(
        queryset=(
            SKU.objects.select_related("produto", "unidade_medida")
            .filter(produto__tipo_produto="MATERIA_PRIMA")
            .order_by("produto__nome", "codigo")
        ),
        label="Matéria-prima (consumida)",
        help_text="SKU que será baixado do estoque.",
    )
    quantidade_materia_prima = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0.01,
        label="Quantidade consumida",
    )
    produto_acabado = forms.ModelChoiceField(
        queryset=(
            SKU.objects.select_related("produto", "unidade_medida")
            .filter(produto__tipo_produto="PRODUTO_ACABADO")
            .order_by("produto__nome", "codigo")
        ),
        label="Produto em estoque (produzido)",
        help_text="SKU que receberá a entrada no estoque.",
    )
    quantidade_produzida = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0.01,
        label="Quantidade produzida",
    )
    deposito = forms.ModelChoiceField(queryset=Deposito.objects.all(), label="Depósito")
    parceiro = forms.ModelChoiceField(
        queryset=Parceiro.objects.filter(tipo__in=("CLIENTE", "AMBOS")).order_by("razao_social"),
        required=False,
        label="Cliente destino (opcional)",
    )
    documento = forms.CharField(
        required=False,
        label="Documento (opcional)",
        help_text="Nº de ordem de produção, nota fiscal etc.",
    )
    observacao = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Observação (opcional)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "form-check-input")
            else:
                campo.widget.attrs.setdefault("class", "form-control")


class PedidoEdicaoForm(forms.Form):
    deposito = forms.ModelChoiceField(queryset=Deposito.objects.all(), label="Depósito")
    parceiro = forms.ModelChoiceField(
        queryset=Parceiro.objects.filter(tipo__in=("CLIENTE", "AMBOS")).order_by("razao_social"),
        required=False,
        label="Cliente",
    )
    documento = forms.CharField(required=False, label="Documento")
    status_pedido = forms.ChoiceField(
        required=False,
        choices=[("", "Sem status")] + list(STATUS_PEDIDO_CHOICES),
        label="Status do pedido",
    )
    forma_pagamento = forms.ChoiceField(
        required=False,
        choices=[("", "Sem forma definida")] + list(FORMA_PAGAMENTO_CHOICES),
        label="Forma de pagamento",
    )
    prazo_pagamento = forms.CharField(required=False, label="Prazo de pagamento")
    observacao = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Observação",
    )
    reservado = forms.BooleanField(
        required=False,
        label="Reservar do saldo destinado ao cliente",
        help_text="Esta saída será abatida do saldo destinado ao cliente.",
    )
    tem_clientes_adicionais = forms.BooleanField(
        required=False, label="Tem clientes adicionais",
    )

    def __init__(self, *args, pedido, **kwargs):
        super().__init__(*args, **kwargs)
        itens = list(pedido.itens.select_related("sku", "parceiro").all())
        cliente_principal_id = pedido.parceiro_id
        adicionais = []
        vistos = {cliente_principal_id} if cliente_principal_id else set()
        for item in itens:
            if item.parceiro_id and item.parceiro_id not in vistos:
                vistos.add(item.parceiro_id)
                adicionais.append(item.parceiro)

        valores_iniciais = {
            "deposito": pedido.deposito_id,
            "parceiro": pedido.parceiro_id,
            "documento": pedido.documento,
            "observacao": pedido.observacao,
            "status_pedido": pedido.status_pedido or "",
            "forma_pagamento": pedido.forma_pagamento or "",
            "prazo_pagamento": pedido.prazo_pagamento,
            "reservado": pedido.reservado,
            "tem_clientes_adicionais": bool(adicionais),
        }
        for nome, valor in valores_iniciais.items():
            self.fields[nome].initial = valor

        principal = [item for item in itens if not item.parceiro_id or item.parceiro_id == cliente_principal_id]
        self.linhas_itens = []
        for indice, item in enumerate(principal or [None], start=1):
            self._adicionar_linha(indice, item)
            self.linhas_itens.append(self._linha_campos(indice))

        self.blocos = []
        for bloco_indice, cliente in enumerate(adicionais, start=1):
            nome_cliente = f"cliente_ad_{bloco_indice}"
            self.fields[nome_cliente] = forms.ModelChoiceField(
                queryset=Parceiro.objects.filter(tipo__in=("CLIENTE", "AMBOS")),
                required=False,
                label=f"Cliente adicional {bloco_indice}",
            )
            self.fields[nome_cliente].initial = cliente.pk
            linhas = []
            itens_cliente = [item for item in itens if item.parceiro_id == cliente.pk]
            for linha_indice, item in enumerate(itens_cliente or [None], start=1):
                self._adicionar_linha(linha_indice, item, bloco_indice)
                linhas.append(self._linha_campos(linha_indice, bloco_indice))
            self.blocos.append({
                "indice": bloco_indice,
                "cliente": self[nome_cliente],
                "linhas": linhas,
            })

        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-check-input" if isinstance(campo.widget, forms.CheckboxInput) else "form-control")

    def _adicionar_linha(self, indice, item, bloco=0):
        sufixo = f"_{indice}" if not bloco else f"_{bloco}_{indice}"
        self.fields[f"sku{sufixo}"] = forms.ModelChoiceField(
            queryset=SKU.objects.select_related("produto").order_by("produto__nome", "codigo"),
            required=False,
            label="SKU",
        )
        self.fields[f"quantidade{sufixo}"] = forms.DecimalField(
            max_digits=12, decimal_places=2, min_value=0.01, required=False,
            label="Quantidade",
        )
        self.fields[f"preco_unitario{sufixo}"] = forms.DecimalField(
            max_digits=12, decimal_places=2, min_value=0, required=False,
            label="Preço unitário",
        )
        if item:
            self.fields[f"sku{sufixo}"].initial = item.sku_id
            self.fields[f"quantidade{sufixo}"].initial = item.quantidade
            self.fields[f"preco_unitario{sufixo}"].initial = item.preco_unitario

    def _linha_campos(self, indice, bloco=0):
        sufixo = f"_{indice}" if not bloco else f"_{bloco}_{indice}"
        return {
            "indice": indice,
            "sku": self[f"sku{sufixo}"],
            "quantidade": self[f"quantidade{sufixo}"],
            "preco_unitario": self[f"preco_unitario{sufixo}"],
        }