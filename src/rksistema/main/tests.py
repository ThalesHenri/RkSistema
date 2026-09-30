#!/usr/bin/env python3
"""
Script de teste manual dos fluxos da API do RK Embalagens.

Uso:
    pip install requests
    python testar_api.py

Ajuste BASE_URL abaixo se o servidor não estiver em localhost:8000.
Nenhuma autenticação é usada por enquanto (JWT ainda não implementado).
"""

import sys
import requests

BASE_URL = "http://127.0.0.1:8000/api"

# Token de acesso JWT obtido no login — preenchido em fazer_login()
ACCESS_TOKEN = None


def headers_autenticados():
    if ACCESS_TOKEN:
        return {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    return {}


def fazer_login():
    global ACCESS_TOKEN
    print("\n=== Login (JWT) ===")
    username = input("  usuário: ").strip()
    password = input("  senha: ").strip()
    resp = requests.post(f"{BASE_URL}/token/", json={"username": username, "password": password})
    imprimir_resposta(resp)
    if resp.ok:
        ACCESS_TOKEN = resp.json().get("access")
        print("Login OK — token salvo para as próximas requisições.")
    else:
        print("Login falhou — as próximas chamadas continuarão sem autenticação (vão dar 401).")

# ---------------------------------------------------------------------------
# Dados mockados — usados como sugestão/padrão em cada fluxo, pra não
# precisar redigitar tudo a cada teste. Sempre editáveis na hora.
# ---------------------------------------------------------------------------

MOCK_CATEGORIA = {"nome": "Descartáveis", "ativo": True}

MOCK_UNIDADE_MEDIDA = {"sigla": "UN", "nome": "Unidade"}

MOCK_PRODUTO = {"tipo_produto": "PRODUTO_ACABADO", "nome": "Copo Descartável", "descricao": "Copo plástico descartável", "ativo": True}

MOCK_SKU = {
    "codigo": "COPO-200-TRANS",
    "codigo_barras": "7890000000010",
    "tamanho_capacidade": "200ml",
    "cor": "Transparente",
    "estoque_minimo": "50",
    "preco_custo": "0.10",
    "preco_venda": "0.25",
    "ativo": True,
}

MOCK_PARCEIRO = {
    "tipo": "FORNECEDOR",
    "razao_social": "Plásticos Nordeste LTDA",
    "nome_fantasia": "Plásticos Nordeste",
    "cnpj_cpf": "12345678000199",
    "telefone": "(83) 99999-0000",
    "email": "contato@plasticosnordeste.com.br",
    "endereco": "Rua das Embalagens, 100",
    "ativo": True,
}

MOCK_DEPOSITO = {"nome": "Depósito Central", "endereco": "Galpão 1", "ativo": True}


# ---------------------------------------------------------------------------
# Dados para mockagem em massa — CADA CAMPO possui pelo menos 2 exemplos.
# Usado pela opção "Mockar todos os campos (2+ exemplos por campo)".
# Os FKs (categoria_pai, categoria, produto, unidade_medida, sku, deposito)
# são preenchidos dinamicamente dentro da função mockar_todos_os_campos().
# ---------------------------------------------------------------------------

EXEMPLOS_CATEGORIA = [
    {"nome": "Descartáveis", "ativo": True},
    {"nome": "Higiene e Limpeza", "ativo": False},
]

EXEMPLOS_UNIDADE = [
    {"sigla": "UN", "nome": "Unidade"},
    {"sigla": "CX", "nome": "Caixa"},
]

EXEMPLOS_PRODUTO = [
    {"tipo_produto": "PRODUTO_ACABADO", "nome": "Copo Descartável", "descricao": "Copo plástico de 200ml", "ativo": True},
    {"tipo_produto": "MATERIA_PRIMA", "nome": "Chapa de Papelão", "descricao": "Chapa de papelão para fabricação de caixas", "ativo": True},
]

EXEMPLOS_SKU = [
    {
        "codigo": "COPO-200-TRANS",
        "codigo_barras": "7890000000010",
        "tamanho_capacidade": "200ml",
        "cor": "Transparente",
        "estoque_minimo": "50",
        "preco_custo": "0.10",
        "preco_venda": "0.25",
        "ativo": True,
    },
    {
        "codigo": "CHAPA-PAP-120X80",
        "codigo_barras": "7890000000027",
        "tamanho_capacidade": "120x80cm",
        "cor": "Kraft",
        "estoque_minimo": "20",
        "preco_custo": "1.50",
        "preco_venda": "2.00",
        "ativo": True,
    },
]

EXEMPLOS_PARCEIRO = [
    {
        "tipo": "FORNECEDOR",
        "razao_social": "Plásticos Nordeste LTDA",
        "nome_fantasia": "Plásticos Nordeste",
        "cnpj_cpf": "12345678000199",
        "telefone": "(83) 99999-0000",
        "email": "contato@plasticosnordeste.com.br",
        "endereco": "Rua das Embalagens, 100",
        "ativo": True,
    },
    {
        "tipo": "CLIENTE",
        "razao_social": "Atacadão de Utilidades SA",
        "nome_fantasia": "Atacadão",
        "cnpj_cpf": "98765432000188",
        "telefone": "(11) 98888-0000",
        "email": "compras@atacadao.com.br",
        "endereco": "Av. dos Plásticos, 500",
        "ativo": False,
    },
]

EXEMPLOS_DEPOSITO = [
    {"nome": "Depósito Central", "endereco": "Galpão 1", "ativo": True},
    {"nome": "Depósito Filial", "endereco": "Galpão 2", "ativo": True},
]


# ---------------------------------------------------------------------------
# Helpers de request/print
# ---------------------------------------------------------------------------

def imprimir_resposta(resp):
    cor_ok = "\033[92m"
    cor_erro = "\033[91m"
    reset = "\033[0m"
    cor = cor_ok if resp.ok else cor_erro
    print(f"{cor}Status: {resp.status_code}{reset}")
    try:
        print(resp.json())
    except ValueError:
        print(resp.text)
    print("-" * 60)


def perguntar(campo, padrao):
    valor = input(f"  {campo} [{padrao}]: ").strip()
    return valor if valor else padrao


def montar_payload(mock: dict) -> dict:
    """Pergunta cada campo do mock, um a um, permitindo aceitar o padrão com Enter."""
    payload = {}
    for campo, padrao in mock.items():
        resposta = perguntar(campo, padrao)
        if isinstance(padrao, bool):
            payload[campo] = str(resposta).strip().lower() in ("1", "true", "sim", "s", "yes", "y") if isinstance(resposta, str) else bool(resposta)
        else:
            payload[campo] = resposta
    return payload


def escolher_id(lista_url, rotulo):
    """Lista os registros de um endpoint e pede pra escolher um ID."""
    resp = requests.get(f"{BASE_URL}{lista_url}", headers=headers_autenticados())
    imprimir_resposta(resp)
    if not resp.ok:
        return None
    dados = resp.json()
    itens = dados.get("results", dados) if isinstance(dados, dict) else dados
    if not itens:
        print(f"Nenhum(a) {rotulo} cadastrado(a) ainda.")
        return None
    for item in itens:
        print(f"  id={item.get('id')} -> {item}")
    escolha = input(f"ID d{'o' if rotulo[-1] != 'a' else 'a'} {rotulo}: ").strip()
    return escolha


# ---------------------------------------------------------------------------
# Fluxos individuais
# ---------------------------------------------------------------------------

def criar_categoria():
    print("\n=== Criar Categoria ===")
    payload = montar_payload(MOCK_CATEGORIA)
    resp = requests.post(f"{BASE_URL}/categorias/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def criar_unidade_medida():
    print("\n=== Criar Unidade de Medida ===")
    payload = montar_payload(MOCK_UNIDADE_MEDIDA)
    resp = requests.post(f"{BASE_URL}/unidades-medida/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def criar_produto():
    print("\n=== Criar Produto ===")
    print("Selecione a categoria:")
    categoria_id = escolher_id("/categorias/", "categoria")
    if not categoria_id:
        return
    payload = montar_payload(MOCK_PRODUTO)
    payload["categoria"] = categoria_id
    resp = requests.post(f"{BASE_URL}/produtos/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def criar_sku():
    print("\n=== Criar SKU ===")
    print("Selecione o produto:")
    produto_id = escolher_id("/produtos/", "produto")
    if not produto_id:
        return
    print("Selecione a unidade de medida:")
    unidade_id = escolher_id("/unidades-medida/", "unidade de medida")
    if not unidade_id:
        return
    payload = montar_payload(MOCK_SKU)
    payload["produto"] = produto_id
    payload["unidade_medida"] = unidade_id
    resp = requests.post(f"{BASE_URL}/skus/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def criar_parceiro():
    print("\n=== Criar Cliente ===")
    payload = montar_payload(MOCK_PARCEIRO)
    resp = requests.post(f"{BASE_URL}/parceiros/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def criar_deposito():
    print("\n=== Criar Depósito ===")
    payload = montar_payload(MOCK_DEPOSITO)
    resp = requests.post(f"{BASE_URL}/depositos/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def _montar_payload_movimentacao(origens_sugeridas):
    print("Selecione o SKU:")
    sku_id = escolher_id("/skus/", "SKU")
    if not sku_id:
        return None
    print("Selecione o depósito:")
    deposito_id = escolher_id("/depositos/", "depósito")
    if not deposito_id:
        return None

    quantidade = perguntar("Quantidade", "10")
    origem = perguntar("Origem" + f" (sugestões: {', '.join(origens_sugeridas)})", origens_sugeridas[0])
    documento = perguntar("Documento (NF/pedido, opcional)", "")
    observacao = perguntar("Observação (opcional)", "")

    payload = {
        "sku": sku_id,
        "deposito": deposito_id,
        "quantidade": quantidade,
        "origem": origem,
        "documento": documento,
        "observacao": observacao,
    }

    usar_parceiro = perguntar("Vincular cliente? (s/n) (entrada: fornecedor)", "n").lower() in ("s", "sim", "y", "yes")
    if usar_parceiro:
        print("Selecione o cliente:")
        parceiro_id = escolher_id("/parceiros/", "cliente")
        if parceiro_id:
            payload["parceiro"] = parceiro_id

    return payload


def registrar_entrada():
    print("\n=== Registrar Entrada de Estoque ===")
    payload = _montar_payload_movimentacao(["COMPRA", "PRODUCAO", "DEVOLUCAO_CLIENTE", "AJUSTE_INVENTARIO"])
    if payload is None:
        return
    resp = requests.post(f"{BASE_URL}/movimentacoes/entrada/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def registrar_saida():
    print("\n=== Registrar Saída de Estoque ===")
    payload = _montar_payload_movimentacao(["VENDA", "PERDA", "DEVOLUCAO_FORNECEDOR", "AJUSTE_INVENTARIO"])
    if payload is None:
        return
    preco = perguntar("Preço unitário (opcional; vazio = usa preço do SKU)", "")
    if preco:
        payload["preco_unitario"] = preco
    resp = requests.post(f"{BASE_URL}/movimentacoes/saida/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def atualizar_preco_status():
    print("\n=== Atualizar preço/status do pedido de uma saída ===")
    print("Selecione a movimentação de saída:")
    mov_id = escolher_id("/movimentacoes/", "movimentação")
    if not mov_id:
        return
    preco = perguntar("Preço unitário (vazio = manter atual)", "")
    status_pedido = perguntar("Status [PENDENTE/FATURADO/ENTREGUE/CANCELADO] (vazio = manter)", "")
    payload = {}
    if preco:
        payload["preco_unitario"] = preco
    if status_pedido:
        payload["status_pedido"] = status_pedido.upper()
    if not payload:
        print("Nada para atualizar — informe preço e/ou status.")
        return
    resp = requests.post(
        f"{BASE_URL}/movimentacoes/{mov_id}/preco-status/",
        json=payload,
        headers=headers_autenticados(),
    )
    imprimir_resposta(resp)


def registrar_producao():
    print("\n=== Registrar Produção (matéria-prima → produto em estoque) ===")
    print("Selecione a matéria-prima (SKU consumida):")
    mp_id = escolher_id("/skus/", "matéria-prima")
    if not mp_id:
        return
    print("Selecione o produto em estoque (SKU produzido):")
    pa_id = escolher_id("/skus/", "produto em estoque")
    if not pa_id:
        return
    print("Selecione o depósito:")
    deposito_id = escolher_id("/depositos/", "depósito")
    if not deposito_id:
        return

    quantidade_mp = perguntar("Quantidade de matéria-prima consumida", "5")
    quantidade_pa = perguntar("Quantidade produzida (produto em estoque)", "5")
    documento = perguntar("Documento (opcional)", "")
    observacao = perguntar("Observação (opcional)", "")

    payload = {
        "materia_prima": mp_id,
        "produto_acabado": pa_id,
        "deposito": deposito_id,
        "quantidade_materia_prima": quantidade_mp,
        "quantidade_produzida": quantidade_pa,
        "documento": documento,
        "observacao": observacao,
    }
    resp = requests.post(f"{BASE_URL}/movimentacoes/producao/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)


def listar(endpoint, nome):
    print(f"\n=== Listar {nome} ===")
    resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers_autenticados())
    imprimir_resposta(resp)


def fluxo_completo_mock():
    """
    Cria uma cadeia inteira (categoria -> produto -> sku -> depósito -> parceiro
    -> entrada -> saída) usando só os dados mockados, sem perguntar nada.
    Útil pra um smoke test rápido do zero.
    """
    print("\n=== Fluxo completo com dados mockados ===")

    print("\n[1/7] Categoria")
    resp = requests.post(f"{BASE_URL}/categorias/", json=MOCK_CATEGORIA, headers=headers_autenticados())
    imprimir_resposta(resp)
    if not resp.ok:
        return
    categoria_id = resp.json()["id"]

    print("[2/7] Unidade de medida")
    resp = requests.post(f"{BASE_URL}/unidades-medida/", json=MOCK_UNIDADE_MEDIDA, headers=headers_autenticados())
    imprimir_resposta(resp)
    if not resp.ok:
        return
    unidade_id = resp.json()["id"]

    print("[3/7] Produto")
    produto = {**MOCK_PRODUTO, "categoria": categoria_id}
    resp = requests.post(f"{BASE_URL}/produtos/", json=produto, headers=headers_autenticados())
    imprimir_resposta(resp)
    if not resp.ok:
        return
    produto_id = resp.json()["id"]

    print("[4/7] SKU")
    sku = {**MOCK_SKU, "produto": produto_id, "unidade_medida": unidade_id}
    resp = requests.post(f"{BASE_URL}/skus/", json=sku, headers=headers_autenticados())
    imprimir_resposta(resp)
    if not resp.ok:
        return
    sku_id = resp.json()["id"]

    print("[5/7] Depósito")
    resp = requests.post(f"{BASE_URL}/depositos/", json=MOCK_DEPOSITO, headers=headers_autenticados())
    imprimir_resposta(resp)
    if not resp.ok:
        return
    deposito_id = resp.json()["id"]

    print("[6/7] Entrada de 100 unidades (COMPRA)")
    entrada = {
        "sku": sku_id, "deposito": deposito_id, "quantidade": "100",
        "origem": "COMPRA", "documento": "NF-0001",
    }
    resp = requests.post(f"{BASE_URL}/movimentacoes/entrada/", json=entrada, headers=headers_autenticados())
    imprimir_resposta(resp)

    print("[7/7] Saída de 30 unidades (VENDA)")
    saida = {
        "sku": sku_id, "deposito": deposito_id, "quantidade": "30",
        "origem": "VENDA", "documento": "PED-0001",
    }
    resp = requests.post(f"{BASE_URL}/movimentacoes/saida/", json=saida, headers=headers_autenticados())
    imprimir_resposta(resp)

    print("\nFluxo completo executado. Confira /movimentacoes/ pra ver o histórico.")


def mockar_todos_os_campos():
    """
    Cria em um único fluxo pelo menos 2 exemplos de valor para cada campo
    das entidades, fechando a cadeia completa (cadastros + movimentações).
    Nada é perguntado — os payloads já vêm prontos nas constantes EXEMPLOS_*.
    Campos com restrição de unicidade (sigla, codigo, codigo_barras, cnpj_cpf)
    recebem um sufixo numérico se já existirem no banco, permitindo rodar
    várias vezes sem parar.
    """

    # Endpoint -> campos únicos (usados no retry com sufixo)
    campos_unicos = {
        "unidades-medida/": ["sigla"],
        "skus/": ["codigo", "codigo_barras"],
        "parceiros/": ["cnpj_cpf"],
    }

    def criar(endpoint, payload):
        resp = requests.post(f"{BASE_URL}/{endpoint}", json=payload, headers=headers_autenticados())
        tentativa = 0
        while tentativa < 5 and not resp.ok:
            tentativa += 1
            adaptado = dict(payload)
            for campo in campos_unicos.get(endpoint, []):
                if campo in adaptado and adaptado[campo]:
                    adaptado[campo] = f"{adaptado[campo]}-{tentativa}"
            resp = requests.post(f"{BASE_URL}/{endpoint}", json=adaptado, headers=headers_autenticados())
            if resp.ok:
                payload = adaptado
        imprimir_resposta(resp)
        if not resp.ok:
            print("Fluxo interrompido — verifique se fez login (opção L) e se o servidor está no ar.")
        return resp.json() if resp.ok else {}

    print("\n=== Mockar todos os campos (2+ exemplos por campo) ===\n")
    ids = {}

    print("Categorias — 'nome', 'ativo' e 'categoria_pai' (None → id da 1ª) com 2 exemplos")
    cat_1 = criar("categorias/", {**EXEMPLOS_CATEGORIA[0], "categoria_pai": None})
    cat_2 = criar("categorias/", {**EXEMPLOS_CATEGORIA[1], "categoria_pai": cat_1.get("id")})
    ids["categorias"] = [cat_1.get("id"), cat_2.get("id")]

    print("\nUnidades de medida — 'sigla' e 'nome' com 2 exemplos")
    un_1 = criar("unidades-medida/", EXEMPLOS_UNIDADE[0])
    un_2 = criar("unidades-medida/", EXEMPLOS_UNIDADE[1])
    ids["unidades"] = [un_1.get("id"), un_2.get("id")]

    print("\nProdutos — 'nome', 'descricao', 'ativo' e 'categoria' (cat_1/cat_2) com 2 exemplos")
    pr_1 = criar("produtos/", {**EXEMPLOS_PRODUTO[0], "categoria": cat_1.get("id")})
    pr_2 = criar("produtos/", {**EXEMPLOS_PRODUTO[1], "categoria": cat_2.get("id")})
    ids["produtos"] = [pr_1.get("id"), pr_2.get("id")]

    print("\nSKUs — 'produto', 'unidade_medida' e todos os campos com 2 exemplos")
    sk_1 = criar("skus/", {**EXEMPLOS_SKU[0], "produto": pr_1.get("id"), "unidade_medida": un_1.get("id")})
    sk_2 = criar("skus/", {**EXEMPLOS_SKU[1], "produto": pr_2.get("id"), "unidade_medida": un_2.get("id")})
    ids["skus"] = [sk_1.get("id"), sk_2.get("id")]

    print("\nClientes — todos os campos (tipo, razão social, CNPJ etc.) com 2 exemplos")
    for ex in EXEMPLOS_PARCEIRO:
        criar("parceiros/", ex)

    print("\nDepósitos — 'nome', 'endereco' e 'ativo' com 2 exemplos")
    dp_1 = criar("depositos/", EXEMPLOS_DEPOSITO[0])
    dp_2 = criar("depositos/", EXEMPLOS_DEPOSITO[1])
    ids["depositos"] = [dp_1.get("id"), dp_2.get("id")]

    print("\nMovimentações — 'origem', 'documento', 'quantidade' e 'observacao' com 2 exemplos")
    sk = sk_1.get("id") or sk_2.get("id")
    dp = dp_1.get("id") or dp_2.get("id")
    if not sk or not dp:
        print("Sem SKU/depósito válidos — pulando movimentações.")
    else:
        movimentacoes = [
            ("movimentacoes/entrada/", "COMPRA", "100", "NF-0001", "Entrada de teste 1"),
            ("movimentacoes/entrada/", "PRODUCAO", "50", "NF-0002", "Entrada de teste 2"),
            ("movimentacoes/saida/", "VENDA", "30", "PED-0001", "Saída de teste 1"),
            ("movimentacoes/saida/", "DEVOLUCAO_FORNECEDOR", "10", "RV-0001", "Saída de teste 2"),
        ]
        for endpoint, origem, quantidade, documento, observacao in movimentacoes:
            criar(endpoint, {
                "sku": sk, "deposito": dp,
                "origem": origem, "quantidade": quantidade,
                "documento": documento, "observacao": observacao,
            })

    print("\nProdução — matéria-prima (chapa) → produto em estoque (copo)")
    if sk_2.get("id") and sk_1.get("id") and dp:
        criar("movimentacoes/producao/", {
            "materia_prima": sk_2.get("id"),
            "produto_acabado": sk_1.get("id"),
            "deposito": dp,
            "quantidade_materia_prima": "5",
            "quantidade_produzida": "5",
            "documento": "OP-MOCK-1",
            "observacao": "Produção de teste",
        })
    else:
        print("Sem SKUs/depósito válidos — pulando produção.")

    print("\nMockagem concluída. IDs criados:")
    for entidade, lista_ids in ids.items():
        print(f"  {entidade}: {lista_ids}")
def testar_saida_sem_saldo():
    """Tenta uma saída absurdamente grande pra provar que o EstoqueError bloqueia."""
    print("\n=== Testar bloqueio de saldo insuficiente ===")
    print("Selecione o SKU:")
    sku_id = escolher_id("/skus/", "SKU")
    if not sku_id:
        return
    print("Selecione o depósito:")
    deposito_id = escolher_id("/depositos/", "depósito")
    if not deposito_id:
        return

    payload = {
        "sku": sku_id, "deposito": deposito_id,
        "quantidade": "999999999", "origem": "VENDA",
    }
    resp = requests.post(f"{BASE_URL}/movimentacoes/saida/", json=payload, headers=headers_autenticados())
    imprimir_resposta(resp)
    if resp.status_code == 400:
        print("OK — a API bloqueou corretamente por saldo insuficiente.")
    else:
        print("Atenção — esperava 400 (saldo insuficiente) e não veio isso.")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

MENU_TEMPLATE = """
==============================================
  RK Embalagens — Teste manual da API
  BASE_URL = {base_url}
==============================================
  Autenticação
  L  - Fazer login (JWT)

  Cadastros
  1  - Criar categoria
  2  - Criar unidade de medida
  3  - Criar produto
  4  - Criar SKU
  5  - Criar cliente
  6  - Criar depósito

  Estoque
  7  - Registrar entrada
  8  - Registrar saída
  9  - Registrar produção
  10 - Testar bloqueio de saldo insuficiente
  17 - Atualizar preço/status de uma saída

  Consultas
  11 - Listar categorias
  12 - Listar produtos
  13 - Listar SKUs
  14 - Listar clientes
  15 - Listar depósitos
  16 - Listar movimentações

  Atalhos
  20 - Rodar fluxo completo com dados mockados
  21 - Mockar todos os campos (2+ exemplos por campo)

  0  - Sair
==============================================
"""


def montar_menu():
    return MENU_TEMPLATE.format(base_url=BASE_URL)

ACOES = {
    "L": fazer_login,
    "1": criar_categoria,
    "2": criar_unidade_medida,
    "3": criar_produto,
    "4": criar_sku,
    "5": criar_parceiro,
    "6": criar_deposito,
    "7": registrar_entrada,
    "8": registrar_saida,
    "9": registrar_producao,
    "10": testar_saida_sem_saldo,
    "17": atualizar_preco_status,
    "11": lambda: listar("/categorias/", "Categorias"),
    "12": lambda: listar("/produtos/", "Produtos"),
    "13": lambda: listar("/skus/", "SKUs"),
    "14": lambda: listar("/parceiros/", "Clientes"),
    "15": lambda: listar("/depositos/", "Depósitos"),
    "16": lambda: listar("/movimentacoes/", "Movimentações"),
    "20": fluxo_completo_mock,
    "21": mockar_todos_os_campos,
}


def main():
    global BASE_URL
    url_customizada = input(f"BASE_URL [{BASE_URL}]: ").strip()
    if url_customizada:
        BASE_URL = url_customizada.rstrip("/")

    print("\nFaça login antes de usar os outros endpoints (opção L).")

    while True:
        print(montar_menu())
        opcao = input("Escolha uma opção: ").strip()

        if opcao == "0":
            print("Até mais!")
            sys.exit(0)

        acao = ACOES.get(opcao) or ACOES.get(opcao.upper())
        if not acao:
            print("Opção inválida.")
            continue

        try:
            acao()
        except requests.exceptions.ConnectionError:
            print(f"\nNão consegui conectar em {BASE_URL}. O servidor Django está rodando?")
        except Exception as erro:
            print(f"\nErro inesperado: {erro}")

        input("\nPressione Enter para continuar...")


if __name__ == "__main__":
    main()