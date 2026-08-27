// Construção de Baralho: clique numa carta do pool alterna se ela está no
// baralho ou não — sem lista espelhada separada, o próprio pool É a lista
// (mesmo padrão de "clique pra agir" de ui.js, nunca drag-and-drop). Preview
// ao passar o mouse espelha (copia, não importa — ui.js está fortemente
// acoplado a um `game` vivo que não existe nesta página) o par
// mostrarPreview/comHoverPreview de ui.js. Salva/lê pela mesma chave que
// main.js usa (TCG.carregarDeckSalvo/TCG.CHAVE_DECK_LOCAL, engine.js).
const combatentes = CARTAS.filter((c) => c.tipo === "Herói" || c.tipo === "Monstro");
const apoio = CARTAS.filter((c) => c.tipo !== "Herói" && c.tipo !== "Monstro");

const deckSalvo = TCG.carregarDeckSalvo();
const selecionadosPanteao = new Set(deckSalvo ? deckSalvo.panteao : []);
const selecionadosArcano = new Set(deckSalvo ? deckSalvo.baralhoArcano : []);

function el(id) { return document.getElementById(id); }

// ---- preview (espelha ui.js: só a imagem, sem legenda de texto — o nome/
// tipo/custo já estão impressos na própria arte da carta) ----
const previewImg = el("preview-img");
const previewVazio = el("preview-vazio");
const previewLegenda = el("preview-legenda");

function mostrarPreview(carta) {
  if (!carta) {
    previewImg.style.display = "none";
    previewLegenda.style.display = "none";
    previewVazio.style.display = "block";
    return;
  }
  previewVazio.style.display = "none";
  previewLegenda.style.display = "none";
  previewImg.style.display = "block";
  previewImg.src = carta.arquivo;
  previewImg.alt = carta.nome;
}

function comHoverPreview(elemento, carta) {
  elemento.addEventListener("mouseenter", () => mostrarPreview(carta));
  elemento.addEventListener("focus", () => mostrarPreview(carta));
}

// ---- grids de seleção -----------------------------------------------------

function renderGrid(container, cartas, selecionados, aoClicar) {
  container.innerHTML = "";
  for (const carta of cartas) {
    const div = document.createElement("div");
    div.className = "carta-pool" + (selecionados.has(carta.nome) ? " selecionada" : "");
    div.tabIndex = 0;

    const img = document.createElement("img");
    img.src = carta.arquivo;
    img.alt = carta.nome;
    div.appendChild(img);

    const nome = document.createElement("div");
    nome.className = "carta-pool__nome";
    nome.textContent = carta.nome;
    div.appendChild(nome);

    comHoverPreview(div, carta);
    div.addEventListener("click", () => aoClicar(carta));
    container.appendChild(div);
  }
}

function alternarPanteao(carta) {
  el("aviso-panteao").textContent = "";
  if (selecionadosPanteao.has(carta.nome)) {
    selecionadosPanteao.delete(carta.nome);
  } else if (selecionadosPanteao.size >= TCG.PANTEAO_TAMANHO) {
    el("aviso-panteao").textContent =
      `O Panteão já tem ${TCG.PANTEAO_TAMANHO} combatentes — remova um antes de adicionar outro.`;
    return;
  } else {
    selecionadosPanteao.add(carta.nome);
  }
  renderTudo();
}

function alternarArcano(carta) {
  if (selecionadosArcano.has(carta.nome)) selecionadosArcano.delete(carta.nome);
  else selecionadosArcano.add(carta.nome);
  renderTudo();
}

function renderContadores() {
  const cPanteao = el("contador-panteao");
  cPanteao.textContent = `${selecionadosPanteao.size}/${TCG.PANTEAO_TAMANHO} selecionados`;
  cPanteao.className = "pool-secao__contador " + (selecionadosPanteao.size === TCG.PANTEAO_TAMANHO ? "ok" : "invalido");

  const cArcano = el("contador-arcano");
  cArcano.textContent = `${selecionadosArcano.size} selecionadas (mínimo ${TCG.BARALHO_ARCANO_MINIMO})`;
  cArcano.className = "pool-secao__contador " + (selecionadosArcano.size >= TCG.BARALHO_ARCANO_MINIMO ? "ok" : "invalido");
}

function renderTudo() {
  renderContadores();
  renderGrid(el("grid-panteao"), combatentes, selecionadosPanteao, alternarPanteao);
  renderGrid(el("grid-arcano"), apoio, selecionadosArcano, alternarArcano);
}

// ---- botões -----------------------------------------------------------

el("btn-salvar-jogar").addEventListener("click", () => {
  const deck = { panteao: Array.from(selecionadosPanteao), baralhoArcano: Array.from(selecionadosArcano) };
  const { valido, erros } = TCG.validarDeckCustomizado(deck);
  if (!valido) {
    el("erros-deck").innerHTML = "<ul>" + erros.map((e) => `<li>${e}</li>`).join("") + "</ul>";
    return;
  }
  el("erros-deck").innerHTML = "";
  localStorage.setItem(TCG.CHAVE_DECK_LOCAL, JSON.stringify(deck));
  location.href = "index.html";
});

el("btn-restaurar").addEventListener("click", () => {
  localStorage.removeItem(TCG.CHAVE_DECK_LOCAL);
  selecionadosPanteao.clear();
  selecionadosArcano.clear();
  el("erros-deck").innerHTML = "";
  el("aviso-panteao").textContent = "";
  renderTudo();
});

el("btn-voltar-menu").addEventListener("click", () => {
  location.href = "menu.html"; // sem salvar — toggles não confirmados são descartados
});

renderTudo();
mostrarPreview(null);
