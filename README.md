# StockPlastic

Sistema de **gestão de estoque para indústria de plásticos — RK Embalagens**: cadastro de produtos, SKUs, clientes/fornecedores, depósitos e controle de entradas/saídas com cálculo automático de saldo.

Frontend com identidade visual da **RK Embalagens** ("Embalando Sonhos", desde 2020): paleta de cores Azul Marinho (#1B2A4A), Vermelho Vivo (#B91C1C) e Dourado Premium (#D4AF37). Logo da marca no cabeçalho e tela de login.

Backend em **Django REST Framework** (API JWT) + **Frontend server-rendered com Django Templates** (CSS próprio em `static/main/css/style.css`, sem dependência de CDN — modo noturno incluído).

---

## Sumário

- [Tecnologias](#tecnologias)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Como rodar](#como-rodar)
- [Frontend (páginas)](#frontend-páginas)
- [API REST](#api-rest)
- [Domínio — as entidades](#domínio--as-entidades)
- [Preços: onde aparecem?](#preços-onde-aparecem)
- [Regras de negócio](#regras-de-negócio)
- [Testes](#testes)

---

## Tecnologias

| Ferramenta | Versão |
|---|---|
| Python | 3.10 |
| Django | 5.2.17 |
| Django REST Framework | 3.18.0 |
| djangorestframework-simplejwt | 5.3.1 |
| Banco de dados | SQLite (`db.sqlite3`) |

---

## Estrutura do projeto

```
StockPlastic/
└── src/back-end/
    ├── manage.py
    ├── requirements.txt
    ├── db.sqlite3
    ├── restApi/                    # projeto Django
    │   ├── settings.py             # conf. apps, banco, JWT, login
    │   ├── urls.py                 # rotas raiz (admin, api, frontend)
    │   ├── wsgi.py / asgi.py
    └── main/                       # app principal
        ├── models/                 # domínio
        │   ├── categoria.py
        │   ├── unidade_medida.py
        │   ├── produto.py
        │   ├── sku.py
        │   ├── parceiro.py
        │   ├── deposito.py
        │   └── movimentacao.py
        ├── views/
        │   ├── *_views.py          # ViewSets da API
        │   ├── serializers/        # serializers da API
        │   ├── services/           # regras de negócio (entrada, saída, saldo)
        │   └── pages/              # views do frontend (dashboard, cadastros, estoque)
        ├── forms.py                # forms do frontend
        ├── urls.py                 # rotas da API (/api/)
        ├── frontend_urls.py        # rotas do frontend (/)
        ├── templates/
        │   ├── registration/login.html
        │   └── main/                # base, dashboard, listas, forms, estoque...
        ├── static/main/css/style.css
        └── migrations/
```

---

## Como rodar

```bash
cd src/back-end

# 1. Criar e ativar o ambiente virtual (se ainda não existir)
python -m venv .venv
source .venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Aplicar migrações e criar usuário admin
python manage.py migrate
python manage.py createsuperuser

# 4. Subir o servidor
python manage.py runserver
```

- **Frontend:** http://127.0.0.1:8000/ (faça login com o superusuário)
- **Admin Django:** http://127.0.0.1:8000/admin/
- **API:** http://127.0.0.1:8000/api/
---

## Frontend (páginas)

O frontend é **server-rendered** (Django Templates + CSS próprio em `static/main/css/style.css`), sem dependência de CDN. Todas as páginas exigem login.

| Rota | Página |
|---|---|
| `/login/` | Login |
| `/` | Dashboard — **faturamento, lucro bruto, margem** (com filtro de período), **nº de pedidos** (pedidos distintos, não movimentações de estoque), valor do estoque, alertas de estoque baixo, últimas movimentações |
| `/categorias/` + novo/editar/excluir | Cadastro de Categorias |
| `/unidades/` + novo/editar/excluir | Cadastro de Unidades de Medida |
| `/produtos/` + novo/editar/excluir | Cadastro de Produtos |
| `/skus/` + novo/editar/excluir | Cadastro de SKUs |
| `/parceiros/` + novo/editar/excluir | Cadastro de Clientes (na tela; internamente Parceiro — clientes e fornecedores) |
| `/depositos/` + novo/editar/excluir | Cadastro de Depósitos |
| `/estoque/` | Saldos por SKU (filtro por depósito, detalhe "por depósito" e painel **"Saldos por cliente"**) |
| `/estoque/entrada/` | Registrar entrada |
| `/estoque/saida/` | Registrar saída (bloqueia saldo insuficiente) |
| `/estoque/producao/` | Registrar produção (matéria-prima → produto acabado), com **cliente destino** opcional |
| `/estoque/orcamento/` | **Novo orçamento** (pedido simulado — não movimenta estoque) |
| `/movimentacoes/` | Histórico de entradas/saídas |
| `/pedidos/` | Pedidos e orçamentos: editar, **efetivar orçamento**, excluir (individual ou **todos os orçamentos**) e PDF |
| `/pedidos/<pk>/editar/` | Editar pedido/orçamento (cabeçalho + itens: SKU, quantidade e preço) |
| `/pedidos/<pk>/efetivar/` | Efetivar orçamento → gera o pedido real e **exclui o orçamento** |
| `/pedidos/<pk>/excluir/` | Excluir pedido/orçamento (com confirmação) |
| `/orcamentos/excluir-todos/` | Excluir todos os orçamentos de uma vez |

---

## API REST

Base: `http://127.0.0.1:8000/api/` — todas as rotas exigem **JWT Bearer**.

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/token/` | Login (retorna `access` + `refresh`) |
| POST | `/api/token/refresh/` | Renovar token |
| GET/POST | `/api/categorias/` | Listar/criar categorias |
| GET/PUT/DELETE | `/api/categorias/{id}/` | Detalhar/editar/excluir |
| GET/POST | `/api/unidades-medida/` | Unidades de medida |
| GET/POST | `/api/produtos/` | Produtos |
| GET/POST | `/api/skus/` | SKUs |
| GET/POST | `/api/parceiros/` | Parceiros (internamente; a interface chama de Clientes) |
| GET/POST | `/api/depositos/` | Depósitos |
| GET | `/api/movimentacoes/` | Listar movimentações (somente leitura) |
| POST | `/api/movimentacoes/entrada/` | Registrar entrada |
| POST | `/api/movimentacoes/saida/` | Registrar saída (aceita `preco_unitario`) |
| POST | `/api/movimentacoes/{id}/preco-status/` | Atualizar preço unitário e/ou status do pedido de uma saída |
| POST | `/api/movimentacoes/producao/` | Registrar produção (saída MP + entrada PA; aceita `parceiro` = **cliente destino**) |
| POST | `/api/movimentacoes/orcamento/` | Criar orçamento (pedido simulado — não movimenta estoque) |
| POST | `/api/movimentacoes/{id}/efetivar/` | Efetivar orçamento: cria o pedido real e **exclui o orçamento** |

Exemplo de login e chamada:

```bash
# Login
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"sua-senha"}'

# Usar o token
curl http://127.0.0.1:8000/api/produtos/ \
  -H "Authorization: Bearer SEU_TOKEN"
```
---

## Domínio — as entidades

| Modelo | Campos principais |
|---|---|
| **Categoria** | nome, categoria_pai (subcategorias), ativo |
| **UnidadeMedida** | sigla (UN, KG, CX...), nome |
| **Produto** | **tipo_produto** (MATERIA_PRIMA / PRODUTO_ACABADO — exibido como "Produto em estoque"), nome, categoria, descrição, ativo |
| **SKU** | produto, código, código de barras, tamanho/capacidade, cor, unidade_medida, estoque_minimo, **preco_custo**, **preco_venda**, ativo |
| **Parceiro** | tipo (FORNECEDOR / CLIENTE / AMBOS), razão social, nome fantasia, CNPJ/CPF, contato |
| **Deposito** | nome, endereço, ativo |
| **Movimentacao** | sku, depósito, tipo (ENTRADA/SAIDA/AJUSTES/**ORCAMENTO** — orçamentos **não** movimentam estoque), origem, quantidade, parceiro, documento, usuário, data, observação, **preco_unitario** (negociado na venda), **status_pedido** (PENDENTE/FATURADO/ENTREGUE/CANCELADO), **forma_pagamento**, **prazo_pagamento** |
| **Pedido** | depósito, origem (ex.: `VENDA`, `ORCAMENTO`), cliente (parceiro), documento, observação, status, forma/prazo — os **itens** são movimentações vinculadas; um orçamento efetivado **gera um novo pedido e o orçamento é excluído** |

---

## Preços: onde aparecem?

**Preço negociado na venda:** a `Movimentacao` **agora grava `preco_unitario`** nas saídas
(principalmente VENDA). Ele permite vender o mesmo SKU por **preços diferentes por cliente**:
no registro da saída (ou depois, na listagem de movimentações), informe o preço negociado.

- Se `preco_unitario` **estiver preenchido**, o faturamento do Dashboard usa **ele** (custo continua pelo `preco_custo` do SKU).
- Se estiver **vazio**, o sistema usa o **`preco_venda` atual do SKU** (comportamento anterior).

Os preços de referência continuam no **SKU**:
- `SKU.preco_custo` — preço de custo unitário atual
- `SKU.preco_venda` — preço de venda unitário padrão (usado quando a venda não negocia outro)

Edição rápida: na página **Movimentações** (`/movimentacoes/`), cada linha de **saída** tem campos
para editar **preço unitário** e **status do pedido**; via API, use
`POST /api/movimentacoes/{id}/preco-status/` com `{"preco_unitario": "7.50", "status_pedido": "FATURADO"}`.

**Custo histórico:** a movimentação grava apenas o preço de **venda**; o custo unitário continua
vindo do `SKU.preco_custo` atual — portanto **não** há custo médio/lote histórico ainda.

---

## Regras de negócio

- **Orçamentos (pedido simulado)** — botão **"＋ Novo orçamento"** (dashboard e `/pedidos/`, rota `/estoque/orcamento/`) cria um pedido simulado com `origem/tipo = ORCAMENTO`: **não movimenta estoque**, não entra no histórico, no Dashboard nem nos saldos. Cada orçamento tem **PDF próprio** (duas vias, nos moldes do pedido) com destaque **"ORÇAMENTO — SEM VALOR FISCAL · SUJEITO A APROVAÇÃO"**.
- **Efetivar orçamento** — `/pedidos/<pk>/efetivar/` mostra o saldo disponível de cada item e, no POST, **gera um pedido real** (mesmos itens, preços, cliente e depósito, com nota rastreando o orçamento de origem) e **exclui o orçamento** do banco. Saldo insuficiente bloqueia a efetivação com mensagem amigável.
- **Exclusão fácil de orçamentos** — botão **Excluir** em cada linha de `/pedidos/` + botão **"Excluir todos os orçamentos"** (com confirmação e contagem).
- **Edição de pedidos** — `/pedidos/<pk>/editar/` edita o **cabeçalho e os itens** (SKU, quantidade e preço unitário, com linhas adicionais/removíveis) de qualquer pedido **ou** orçamento; ao salvar, o saldo é validado **devolvendo as quantidades atuais do próprio pedido** antes de recalcular.
- **Dashboard: nº de pedidos** — o card de Faturamento mostra o **número de pedidos** (registros da tabela Pedido: um pedido com N SKUs conta **uma única vez**), e **não** o nº de movimentações de estoque; **saídas avulsas sem pedido não contam** (mas continuam valendo no faturamento) e orçamentos também não. Respeita os filtros de parceiro/produto/SKU e o período (por `criado_em`).
- **Produção com cliente destino** — o formulário de produção aceita **"Cliente (destino)"** opcional; o cliente fica gravado na **entrada** do produto acabado. Em `/estoque/`, o painel **"Saldos por cliente"** mostra, por cliente e SKU, o saldo destinado = **entradas produzidas para o cliente − saídas de venda para esse mesmo cliente** (valor negativo = entregue além do destinado), respeitando o filtro de depósito.
- **Movimentações podem ser excluídas** (com página de confirmação, botão na listagem `/movimentacoes/`). O saldo é sempre recalculado do histórico restante; **produções** (`origem PRODUCAO`) têm a entrada vinculada à saída (`movimentacao_origem`) e são sempre excluídas em **par**. Edição continua proibida — correções de valor/quantidade devem ser feitas com exclusão + nova movimentação ou ajustes compensatórios.
- **Saldo = entradas + ajustes positivos − saídas − ajustes negativos** (calculado por `CalcularSaldoService`).
- **Saída bloqueada** quando o saldo é insuficiente → erro `EstoqueError` (400 na API / mensagem amigável no frontend).
- **Quantidade deve ser > 0** para qualquer movimentação.
- **`on_delete=PROTECT`** — não permite excluir registros que tenham vínculos (ex.: excluir categoria que possui produto). O frontend exibe mensagem de bloqueio.
- **Estoque mínimo** — SKUs com saldo `≤ estoque_minimo` geram alerta de reposição no Dashboard e na tela de Estoque.
- **Usuário registrador** — a movimentação grava quem a fez (`usuario`).
- **Matéria-prima vs produto em estoque** — `Produto.tipo_produto` classifica o item: `MATERIA_PRIMA` (ex.: chapa de papelão) é consumido na fabricação; `PRODUTO_ACABADO` (exibido como "Produto em estoque"; ex.: caixa) é o resultado final.
- **Produção** — `RegistrarProducaoService` registra, em **uma transação atômica**, a **SAIDA** da matéria-prima e a **ENTRADA** do produto em estoque (ambas com origem `PRODUCAO`, entrada vinculada à saída), validando o saldo da MP. Disponível em `/estoque/producao/` (frontend) e `POST /api/movimentacoes/producao/` (API).
- **Preço negociado por cliente** — cada saída pode ter `preco_unitario` diferente (mesmo SKU, clientes diferentes). O **Dashboard** prioriza o preço gravado na movimentação e só usa o `preco_venda` do SKU como fallback.
- **Status do pedido** — saídas com origem `VENDA` nascem como `PENDENTE` e podem ser marcadas como `FATURADO`, `ENTREGUE` ou `CANCELADO` na própria linha da listagem `/movimentacoes/` (filtro por status incluído). Via API: `POST /api/movimentacoes/{id}/preco-status/`.
- **Forma de pagamento e prazo** — cada saída/venda pode registrar `forma_pagamento` (Dinheiro, Pix, Boleto, Cartão, Transferência, Crediário, Outro) e `prazo_pagamento` (texto livre, ex.: "30 dias"), preenchíveis no registro da saída ou na edição inline da listagem. Esses dados aparecem no **PDF do pedido**.
- **PDF do pedido em DUAS VIAS** — o PDF individual de um pedido (`/movimentacoes/<pk>/pdf/`) traz as duas vias na **mesma página**: 1ª via (fica com a empresa) e 2ª via (cliente) **destacada** e com **recibo de entrega/assinatura**. O PDF **não** exibe lote, depósito nem status do pedido. O **nº do documento** (título, metadados, coluna do relatório e nome do arquivo) é o **nº real do Pedido**, não o da movimentação (venda avulsa sem pedido usa o nº da própria movimentação).
- **Cadastro "Clientes"** — a interface usa "Clientes"; internamente o modelo continua `Parceiro` (com tipos Fornecedor / Cliente / Ambos), mantendo URLs `/parceiros/` e API `/api/parceiros/` inalteradas.
- **Faturamento filtrável** — o Dashboard filtra Faturamento/Lucro/Margem por **cliente**, **produto**, **SKU** e **período**.
- **Modo noturno** — alternável pelo botão 🌙/☀️ no topo (e na tela de login); o tema é salvo no navegador (`localStorage`) e segue a preferência do sistema por padrão.

---

## Testes

- **`main/tests.py`** — script manual (CLI interativo) que testa a API via `requests`: login JWT, criação de cadastros, entrada/saída (com preço negociado), produção, atualização de preço/status/pagamento e bloqueio de saldo insuficiente.
- **`main/test_producao.py`** — testes automatizados (Django `TestCase`) do fluxo de produção: baixa de matéria-prima, entrada do produto em estoque, vínculo entre o par, bloqueio por saldo insuficiente e endpoint da API. Rode com `python manage.py test main.test_producao`.
- **`main/test_preco_status.py`** — testes automatizados de preço negociado, status do pedido, forma de pagamento/prazo e filtros do Dashboard (cliente/produto/SKU). Rode com `python manage.py test main.test_preco_status`.
- **`main/test_pedido_pdf.py`** — testes da emissão de PDF: duas vias na mesma página, forma de pagamento/prazo, ausência de lote/depósito/status e total usando preço negociado ou fallback do SKU. Rode com `python manage.py test main.test_pedido_pdf`.
- **`main/test_dashboard.py`** — testes do nº de pedidos do dashboard: pedido com N SKUs conta 1, avulsas/orçamentos não contam, filtros (produto/SKU/parceiro/período) e faturamento incluindo avulsa. Rode com `python manage.py test main.test_dashboard`.
- **`main/test_movimentacao_delete.py`** — testes de exclusão de movimentações (comum e par de produção) com revérsão do saldo. Rode com `python manage.py test main.test_movimentacao_delete`.
- **`main/test_orcamento.py`** — testes dos orçamentos: criação sem movimentar estoque, exclusão (individual e em lote), efetivação (gera pedido novo e apaga o orçamento, inclusive via página e API) e destaque no PDF. Rode com `python manage.py test main.test_orcamento`.
- **`main/test_pedido_edicao.py`** — testes da edição completa de pedidos (cabeçalho + itens, recálculo e validação de saldo). Rode com `python manage.py test main.test_pedido_edicao`.
- **`main/test_producao_cliente.py`** — testes da produção com cliente destino: carimbo do cliente na entrada, painel "Saldos por cliente" (venda abate, saldo negativo, fornecedor fora do painel). Rode com `python manage.py test main.test_producao_cliente`.
- Smoke test do frontend (todas as páginas + fluxos de formulário) validado com o test client do Django.
- `python manage.py check` — sem erros no momento da última validação.