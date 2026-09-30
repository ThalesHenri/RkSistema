from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from main.forms import (
    CategoriaForm,
    UnidadeMedidaForm,
    ProdutoForm,
    SKUForm,
    ParceiroForm,
    DepositoForm,
)
from main.models import (
    Categoria,
    UnidadeMedida,
    Produto,
    SKU,
    Parceiro,
    Deposito,
)


# ---------------------------------------------------------------------------
# Classes-base para as páginas de cadastro (CRUD)
# ---------------------------------------------------------------------------


class BaseCadastroListView(LoginRequiredMixin, ListView):
    """Lista genérica: cada subclasse fornece linhas já formatadas."""

    template_name = "main/cadastro_list.html"
    paginate_by = 50
    titulo = ""
    subtitulo = ""
    url_novo = None
    url_editar = None
    url_excluir = None
    cabecalho = []

    def get_linhas(self, objetos):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        ctx["subtitulo"] = self.subtitulo
        ctx["url_novo"] = self.url_novo
        ctx["url_editar"] = self.url_editar
        ctx["url_excluir"] = self.url_excluir
        ctx["cabecalho"] = self.cabecalho
        ctx["linhas"] = self.get_linhas(ctx["object_list"])
        return ctx


class BaseCadastroCreateView(LoginRequiredMixin, CreateView):
    template_name = "main/cadastro_form.html"
    titulo = ""
    url_lista = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        ctx["url_lista"] = self.url_lista
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"{self.titulo}: registro criado com sucesso.")
        return super().form_valid(form)


class BaseCadastroUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "main/cadastro_form.html"
    titulo = ""
    url_lista = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        ctx["url_lista"] = self.url_lista
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"{self.titulo}: registro atualizado com sucesso.")
        return super().form_valid(form)

class BaseCadastroDeleteView(LoginRequiredMixin, DeleteView):
    """DeleteView que trata on_delete=PROTECT e exibe mensagens amigáveis."""

    template_name = "main/cadastro_confirm_delete.html"
    titulo = ""
    url_lista = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = self.titulo
        ctx["url_lista"] = self.url_lista
        return ctx

    def form_valid(self, form):
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                self.request,
                "Exclusão bloqueada: existem registros vinculados a este item. "
                "Remova ou desative os vínculos antes de excluir.",
            )
            return HttpResponseRedirect(self.get_success_url())
        messages.success(self.request, f"{self.titulo}: registro excluído com sucesso.")
        return HttpResponseRedirect(self.get_success_url())


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------


class CategoriaListView(BaseCadastroListView):
    model = Categoria
    titulo = "Categorias"
    subtitulo = "Organize os produtos em categorias e subcategorias."
    url_novo = reverse_lazy("categoria_create")
    url_editar = "categoria_update"
    url_excluir = "categoria_delete"
    cabecalho = ["Nome", "Categoria pai", "Ativo"]

    def get_linhas(self, objetos):
        return [
            {
                "pk": o.pk,
                "colunas": [
                    ("texto", o.nome),
                    ("texto", o.categoria_pai.nome if o.categoria_pai else "—"),
                    ("bool", o.ativo),
                ],
            }
            for o in objetos
        ]


class CategoriaCreateView(BaseCadastroCreateView):
    model = Categoria
    form_class = CategoriaForm
    success_url = reverse_lazy("categoria_list")
    titulo = "Nova categoria"
    url_lista = "categoria_list"


class CategoriaUpdateView(BaseCadastroUpdateView):
    model = Categoria
    form_class = CategoriaForm
    titulo = "Editar categoria"
    url_lista = "categoria_list"

    def get_success_url(self):
        return reverse_lazy("categoria_list")


class CategoriaDeleteView(BaseCadastroDeleteView):
    model = Categoria
    titulo = "Excluir categoria"
    url_lista = "categoria_list"

    def get_success_url(self):
        return reverse_lazy("categoria_list")


# ---------------------------------------------------------------------------
# Unidades de medida
# ---------------------------------------------------------------------------


class UnidadeMedidaListView(BaseCadastroListView):
    model = UnidadeMedida
    titulo = "Unidades de medida"
    subtitulo = "Unidades usadas pelos SKUs (UN, KG, CX, L...)."
    url_novo = reverse_lazy("unidade_create")
    url_editar = "unidade_update"
    url_excluir = "unidade_delete"
    cabecalho = ["Sigla", "Nome"]

    def get_linhas(self, objetos):
        return [
            {"pk": o.pk, "colunas": [("texto", o.sigla), ("texto", o.nome)]}
            for o in objetos
        ]


class UnidadeMedidaCreateView(BaseCadastroCreateView):
    model = UnidadeMedida
    form_class = UnidadeMedidaForm
    success_url = reverse_lazy("unidade_list")
    titulo = "Nova unidade de medida"
    url_lista = "unidade_list"


class UnidadeMedidaUpdateView(BaseCadastroUpdateView):
    model = UnidadeMedida
    form_class = UnidadeMedidaForm
    titulo = "Editar unidade de medida"
    url_lista = "unidade_list"

    def get_success_url(self):
        return reverse_lazy("unidade_list")


class UnidadeMedidaDeleteView(BaseCadastroDeleteView):
    model = UnidadeMedida
    titulo = "Excluir unidade de medida"
    url_lista = "unidade_list"

    def get_success_url(self):
        return reverse_lazy("unidade_list")

# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------


class ProdutoListView(BaseCadastroListView):
    model = Produto
    titulo = "Produtos"
    subtitulo = "Produtos fabricados ou comercializados."
    url_novo = reverse_lazy("produto_create")
    url_editar = "produto_update"
    url_excluir = "produto_delete"
    cabecalho = ["Tipo", "Nome", "Categoria", "Ativo"]

    def get_linhas(self, objetos):
        return [
            {
                "pk": o.pk,
                "colunas": [
                    (
                        "badge",
                        {
                            "texto": o.get_tipo_produto_display(),
                            "classe": (
                                "badge-info"
                                if o.tipo_produto == "MATERIA_PRIMA"
                                else "badge-ok"
                            ),
                        },
                    ),
                    ("texto", o.nome),
                    ("texto", o.categoria.nome),
                    ("bool", o.ativo),
                ],
            }
            for o in objetos
        ]


class ProdutoCreateView(BaseCadastroCreateView):
    model = Produto
    form_class = ProdutoForm
    success_url = reverse_lazy("produto_list")
    titulo = "Novo produto"
    url_lista = "produto_list"


class ProdutoUpdateView(BaseCadastroUpdateView):
    model = Produto
    form_class = ProdutoForm
    titulo = "Editar produto"
    url_lista = "produto_list"

    def get_success_url(self):
        return reverse_lazy("produto_list")


class ProdutoDeleteView(BaseCadastroDeleteView):
    model = Produto
    titulo = "Excluir produto"
    url_lista = "produto_list"

    def get_success_url(self):
        return reverse_lazy("produto_list")


# ---------------------------------------------------------------------------
# SKUs
# ---------------------------------------------------------------------------


class SKUListView(BaseCadastroListView):
    model = SKU
    titulo = "SKUs"
    subtitulo = "Variações de cada produto (tamanho, cor, embalagem...)."
    url_novo = reverse_lazy("sku_create")
    url_editar = "sku_update"
    url_excluir = "sku_delete"
    cabecalho = ["Produto", "Tipo", "Código", "Tamanho/capacidade", "Cor", "Un.", "Est. mínimo", "Preço venda", "Ativo"]

    def get_linhas(self, objetos):
        return [
            {
                "pk": o.pk,
                "colunas": [
                    ("texto", o.produto.nome),
                    (
                        "badge",
                        {
                            "texto": o.produto.get_tipo_produto_display(),
                            "classe": (
                                "badge-info"
                                if o.produto.tipo_produto == "MATERIA_PRIMA"
                                else "badge-ok"
                            ),
                        },
                    ),
                    ("texto", o.codigo),
                    ("texto", o.tamanho_capacidade or "—"),
                    ("texto", o.cor or "—"),
                    ("texto", o.unidade_medida.sigla),
                    ("numero", o.estoque_minimo),
                    ("moeda", o.preco_venda),
                    ("bool", o.ativo),
                ],
            }
            for o in objetos
        ]


class SKUCreateView(BaseCadastroCreateView):
    model = SKU
    form_class = SKUForm
    success_url = reverse_lazy("sku_list")
    titulo = "Novo SKU"
    url_lista = "sku_list"


class SKUUpdateView(BaseCadastroUpdateView):
    model = SKU
    form_class = SKUForm
    titulo = "Editar SKU"
    url_lista = "sku_list"

    def get_success_url(self):
        return reverse_lazy("sku_list")


class SKUDeleteView(BaseCadastroDeleteView):
    model = SKU
    titulo = "Excluir SKU"
    url_lista = "sku_list"

    def get_success_url(self):
        return reverse_lazy("sku_list")
# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


class ParceiroListView(BaseCadastroListView):
    model = Parceiro
    titulo = "Clientes"
    subtitulo = "Clientes e fornecedores."
    url_novo = reverse_lazy("parceiro_create")
    url_editar = "parceiro_update"
    url_excluir = "parceiro_delete"
    cabecalho = ["Tipo", "Nome fantasia", "Razão social", "CNPJ/CPF", "Telefone", "Ativo"]

    def get_linhas(self, objetos):
        return [
            {
                "pk": o.pk,
                "colunas": [
                    ("texto", o.get_tipo_display()),
                    ("texto", o.nome_fantasia or "—"),
                    ("texto", o.razao_social),
                    ("texto", o.cnpj_cpf),
                    ("texto", o.telefone or "—"),
                    ("bool", o.ativo),
                ],
            }
            for o in objetos
        ]


class ParceiroCreateView(BaseCadastroCreateView):
    model = Parceiro
    form_class = ParceiroForm
    success_url = reverse_lazy("parceiro_list")
    titulo = "Novo cliente"
    url_lista = "parceiro_list"


class ParceiroUpdateView(BaseCadastroUpdateView):
    model = Parceiro
    form_class = ParceiroForm
    titulo = "Editar cliente"
    url_lista = "parceiro_list"

    def get_success_url(self):
        return reverse_lazy("parceiro_list")


class ParceiroDeleteView(BaseCadastroDeleteView):
    model = Parceiro
    titulo = "Excluir cliente"
    url_lista = "parceiro_list"

    def get_success_url(self):
        return reverse_lazy("parceiro_list")


# ---------------------------------------------------------------------------
# Depósitos
# ---------------------------------------------------------------------------


class DepositoListView(BaseCadastroListView):
    model = Deposito
    titulo = "Depósitos"
    subtitulo = "Locais físicos onde o estoque é armazenado."
    url_novo = reverse_lazy("deposito_create")
    url_editar = "deposito_update"
    url_excluir = "deposito_delete"
    cabecalho = ["Nome", "Endereço", "Ativo"]

    def get_linhas(self, objetos):
        return [
            {
                "pk": o.pk,
                "colunas": [
                    ("texto", o.nome),
                    ("texto", o.endereco or "—"),
                    ("bool", o.ativo),
                ],
            }
            for o in objetos
        ]


class DepositoCreateView(BaseCadastroCreateView):
    model = Deposito
    form_class = DepositoForm
    success_url = reverse_lazy("deposito_list")
    titulo = "Novo depósito"
    url_lista = "deposito_list"


class DepositoUpdateView(BaseCadastroUpdateView):
    model = Deposito
    form_class = DepositoForm
    titulo = "Editar depósito"
    url_lista = "deposito_list"

    def get_success_url(self):
        return reverse_lazy("deposito_list")


class DepositoDeleteView(BaseCadastroDeleteView):
    model = Deposito
    titulo = "Excluir depósito"
    url_lista = "deposito_list"

    def get_success_url(self):
        return reverse_lazy("deposito_list")
