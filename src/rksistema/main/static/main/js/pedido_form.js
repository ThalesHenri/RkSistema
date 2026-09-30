/**
 * Formulário dinâmico de pedido / orçamento com suporte a VÁRIOS CLIENTES.
 *
 * Estrutura de nomes dos campos:
 *   - bloco 0 (cliente principal, cabeçalho): `sku`, `sku_2`, ... (criação)
 *     ou `sku_1`, `sku_2`, ... (edição de pedido);
 *   - bloco b (b >= 1, cliente adicional): `cliente_ad_b` + `sku_b_i`,
 *     `quantidade_b_i`, `preco_unitario_b_i`.
 *
 * O padrão do bloco 0 é detectado pela presença do campo `sku` sem sufixo.
 * Todos os blocos são enviados no MESMO formulário — ou seja, formam um
 * único pedido (e um único PDF).
 */
(function () {
  "use strict";

  function iniciar(form) {
    if (!form || form.getAttribute("data-pedido-form") === "pronto") return;
    form.setAttribute("data-pedido-form", "pronto");

    var modeloSku = document.getElementById("modelo-select-sku");
    var modeloCliente = document.getElementById("modelo-select-cliente");
    var areaBlocos = document.getElementById("area-clientes-adicionais");
    var containerBlocos = document.getElementById("blocos-adicionais");
    var chkClientes = document.getElementById("id_tem_clientes_adicionais");
    var btnAddCliente = document.getElementById("btn-adicionar-cliente");
    var btnAddItem0 = document.getElementById("btn-adicionar-item");
    var container0 = document.getElementById("linhas-adicionais");

    if (!modeloSku || !container0) return;

    // Bloco 0: linha 1 sem sufixo no formulário de criação (`sku`).
    var semSufixo = !!form.querySelector('[name="sku"]');
    var tabelaPrincipal = container0.parentNode;

    function nomeCampo(base, bloco, linha) {
      if (!bloco) {
        if (semSufixo && linha === 1) return base;
        return base + "_" + linha;
      }
      return base + "_" + bloco + "_" + linha;
    }

    function proximoIndice(scope) {
      var maximo = 0;
      Array.prototype.forEach.call(
        scope.querySelectorAll(".linha-item[data-indice]"),
        function (el) {
          var n = parseInt(el.getAttribute("data-indice"), 10);
          if (!isNaN(n) && n > maximo) maximo = n;
        }
      );
      return maximo + 1;
    }

    function ancestralComClasse(elemento, classe) {
      while (elemento && elemento !== form) {
        if (elemento.classList && elemento.classList.contains(classe)) return elemento;
        elemento = elemento.parentNode;
      }
      return null;
    }

    function proximoBloco() {
      if (!containerBlocos) return 1;
      var maximo = 0;
      Array.prototype.forEach.call(
        containerBlocos.querySelectorAll(".bloco-cliente-adicional"),
        function (el) {
          var n = parseInt(el.getAttribute("data-bloco"), 10);
          if (!isNaN(n) && n > maximo) maximo = n;
        }
      );
      return maximo + 1;
    }

    function criarLinha(destino, bloco, indice) {
      var linha = document.createElement("div");
      linha.className = "linha-item";
      linha.setAttribute("data-indice", indice);

      var celulaSku = document.createElement("div");
      celulaSku.className = "campo";
      var sel = modeloSku.cloneNode(true);
      sel.removeAttribute("hidden");
      sel.name = nomeCampo("sku", bloco, indice);
      sel.id = "id_" + sel.name;
      sel.value = "";
      celulaSku.appendChild(sel);
      linha.appendChild(celulaSku);

      var celulaQtd = document.createElement("div");
      celulaQtd.className = "campo";
      var qtd = document.createElement("input");
      qtd.type = "number";
      qtd.step = "0.01";
      qtd.min = "0.01";
      qtd.name = nomeCampo("quantidade", bloco, indice);
      qtd.id = "id_" + qtd.name;
      qtd.className = "form-control";
      qtd.placeholder = "Qtd.";
      celulaQtd.appendChild(qtd);
      linha.appendChild(celulaQtd);

      var celulaPreco = document.createElement("div");
      celulaPreco.className = "campo";
      var preco = document.createElement("input");
      preco.type = "number";
      preco.step = "0.01";
      preco.min = "0";
      preco.name = nomeCampo("preco_unitario", bloco, indice);
      preco.id = "id_" + preco.name;
      preco.className = "form-control";
      preco.placeholder = "Preço unit.";
      celulaPreco.appendChild(preco);
      linha.appendChild(celulaPreco);

      var celulaAcao = document.createElement("div");
      celulaAcao.className = "celula-remover";
      var remover = document.createElement("button");
      remover.type = "button";
      remover.className = "btn btn-link btn-link-perigo remover-linha";
      remover.textContent = "Remover";
      celulaAcao.appendChild(remover);
      linha.appendChild(celulaAcao);

      destino.appendChild(linha);
    }

    function criarBloco(bloco) {
      if (!containerBlocos) return null;

      var fs = document.createElement("fieldset");
      fs.className = "grupo-form bloco-cliente-adicional";
      fs.setAttribute("data-bloco", bloco);

      var legenda = document.createElement("legend");
      legenda.textContent = "Cliente adicional " + bloco;
      fs.appendChild(legenda);

      var grid = document.createElement("div");
      grid.className = "grid-campos";
      var campo = document.createElement("div");
      campo.className = "campo";
      var rotulo = document.createElement("label");
      rotulo.setAttribute("for", "id_cliente_ad_" + bloco);
      rotulo.textContent = "Cliente adicional " + bloco;
      campo.appendChild(rotulo);
      if (modeloCliente) {
        var selCliente = modeloCliente.cloneNode(true);
        selCliente.removeAttribute("hidden");
        selCliente.name = "cliente_ad_" + bloco;
        selCliente.id = "id_cliente_ad_" + bloco;
        selCliente.value = "";
        campo.appendChild(selCliente);
      }
      grid.appendChild(campo);
      fs.appendChild(grid);

      var tabela = document.createElement("div");
      tabela.className = "tabela-itens";
      var cabecalho = document.createElement("div");
      cabecalho.className = "linha-item linha-item-cabecalho";
      cabecalho.innerHTML =
        "<span>SKU</span><span>Quantidade</span>" +
        "<span>Preço unitário (R$)</span><span></span>";
      tabela.appendChild(cabecalho);
      var destino = document.createElement("div");
      destino.className = "linhas-adicionais";
      tabela.appendChild(destino);
      fs.appendChild(tabela);

      var ajuda = document.createElement("p");
      ajuda.className = "ajuda";
      ajuda.textContent =
        "Itens deste cliente. Preço vazio = usa o preço cadastrado no SKU.";
      fs.appendChild(ajuda);

      var btnItem = document.createElement("button");
      btnItem.type = "button";
      btnItem.className = "btn btn-secundario btn-adicionar-item-bloco";
      btnItem.textContent = "＋ Adicionar item";
      fs.appendChild(btnItem);

      fs.appendChild(document.createTextNode(" "));

      var btnRemover = document.createElement("button");
      btnRemover.type = "button";
      btnRemover.className = "btn btn-link btn-link-perigo remover-bloco";
      btnRemover.textContent = "Remover este cliente";
      fs.appendChild(btnRemover);

      containerBlocos.appendChild(fs);
      criarLinha(destino, bloco, 1);
      return fs;
    }

    function atualizarArea() {
      if (!areaBlocos) return;
      var temBlocos = !!(containerBlocos && containerBlocos.children.length);
      var marcado = !!(chkClientes && chkClientes.checked);
      areaBlocos.hidden = !(marcado || temBlocos);
    }

    // O botão principal já existe no HTML; ligação direta evita depender de
    // Element.closest e mantém a ação disponível em navegadores móveis antigos.
    if (btnAddItem0) {
      btnAddItem0.addEventListener("click", function (evento) {
        evento.preventDefault();
        criarLinha(container0, 0, proximoIndice(tabelaPrincipal));
      });
    }

    // Delegação para os botões dos blocos criados dinamicamente.
    form.addEventListener("click", function (evento) {
      var alvo = evento.target;
      if (alvo && alvo.nodeType !== 1) alvo = alvo.parentNode;
      if (!alvo) return;

      if (alvo.classList && alvo.classList.contains("btn-adicionar-item-bloco")) {
        var blocoElemento = ancestralComClasse(alvo, "bloco-cliente-adicional");
        var tabelaBloco = blocoElemento && blocoElemento.querySelector(".tabela-itens");
        var destinoBloco = blocoElemento && blocoElemento.querySelector(".linhas-adicionais");
        if (blocoElemento && tabelaBloco && destinoBloco) {
          var indiceBloco = parseInt(blocoElemento.getAttribute("data-bloco"), 10);
          criarLinha(destinoBloco, indiceBloco, proximoIndice(tabelaBloco));
        }
        return;
      }

      if (alvo.classList && alvo.classList.contains("remover-linha")) {
        var linha = ancestralComClasse(alvo, "linha-item");
        if (linha) linha.remove();
        return;
      }

      if (alvo.classList && alvo.classList.contains("remover-bloco")) {
        var bloco = ancestralComClasse(alvo, "bloco-cliente-adicional");
        if (bloco) bloco.remove();
        atualizarArea();
      }
    });

    // ---- opção "Tem clientes adicionais" ----
    if (chkClientes) {
      chkClientes.addEventListener("change", function () {
        if (chkClientes.checked) {
          if (containerBlocos && containerBlocos.children.length === 0) {
            criarBloco(proximoBloco());
          }
        } else if (containerBlocos) {
          // Desmarcar descarta os blocos: a opção é a fonte da verdade.
          containerBlocos.innerHTML = "";
        }
        atualizarArea();
      });
    }

    // ---- botão "＋ Adicionar cliente" ----
    if (btnAddCliente) {
      btnAddCliente.addEventListener("click", function () {
        criarBloco(proximoBloco());
        atualizarArea();
      });
    }

    atualizarArea();
  }

  function aoCarregar() {
    Array.prototype.forEach.call(
      document.querySelectorAll("form[data-pedido-form]"),
      iniciar
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", aoCarregar);
  } else {
    aoCarregar();
  }
})();
