// Construção de Baralho: cada seção (Panteão / Baralho Arcano) tem uma busca
// + duas listas roláveis — "Disponíveis" (pool inteiro menos quem já está no
// baralho, filtrado pela busca; clicar ADICIONA) e a lista do baralho atual
// (clicar REMOVE, volta pra "Disponíveis"). Preview ao passar o mouse
// espelha (copia, não importa — ui.js está fortemente acoplado a um `game`
// vivo que não existe nesta página) o par mostrarPreview/comHoverPreview de
// ui.js. Salva/lê pela mesma chave que main.js usa
// (TCG.carregarDeckSalvo/TCG.CHAVE_DECK_LOCAL, engine.js).

const combatentes = CARTAS.filter((c) => c.tipo === "Herói" || c.tipo === "Monstro");
const apoio = CARTAS.filter((c) => c.tipo !== "Herói" && c.tipo !== "Monstro");

const deckSalvo = TCG.carregarDeckSalvo();

const secoes = {
  panteao: {
    pool: combatentes,
    tamanho: TCG.PANTEAO_TAMANHO,
    selecionados: new Set(deckSalvo ? deckSalvo.panteao : []),
    busca: "",
    prefixo: "panteao",
    rotuloDeck: "Panteão",
  },
  arcano: {
    pool: apoio,
    tamanho: TCG.BARALHO_ARCANO_TAMANHO,
    selecionados: new Set(deckSalvo ? deckSalvo.baralhoArcano : []),
    busca: "",
    prefixo: "arcano",
    rotuloDeck: "Baralho Arcano",
  },
};

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

// ---- grids -----------------------------------------------------------

function criarCartaEl(carta, aoClicar) {
  const div = document.createElement("div");
  div.className = "carta-pool";
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
  return div;
}

// Remove acentos antes de comparar (NFD separa a letra da marca diacrítica
// do caractere base; U+0300-036F é o bloco Unicode dessas marcas) —
// "atlantida" acha "Atlântida" na busca, não só correspondência exata.
function normalizar(texto) {
  return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function renderSecao(chave) {
  const secao = secoes[chave];
  const termo = normalizar(secao.busca.trim());

  const disponiveis = secao.pool.filter((c) => !secao.selecionados.has(c.nome) && normalizar(c.nome).includes(termo));
  const gridDisponiveis = el(`grid-${secao.prefixo}-disponiveis`);
  gridDisponiveis.innerHTML = "";
  for (const carta of disponiveis) {
    gridDisponiveis.appendChild(criarCartaEl(carta, () => adicionar(chave, carta)));
  }

  const nomesSelecionados = secao.pool.filter((c) => secao.selecionados.has(c.nome));
  const gridSelecionadas = el(`grid-${secao.prefixo}-selecionadas`);
  gridSelecionadas.innerHTML = "";
  for (const carta of nomesSelecionados) {
    const cartaEl = criarCartaEl(carta, () => remover(chave, carta));
    cartaEl.classList.add("selecionada");
    gridSelecionadas.appendChild(cartaEl);
  }

  const contador = el(`contador-${secao.prefixo}`);
  contador.textContent = `${secao.selecionados.size}/${secao.tamanho} selecionadas`;
  contador.className = "pool-secao__contador " + (secao.selecionados.size === secao.tamanho ? "ok" : "invalido");
}

function adicionar(chave, carta) {
  const secao = secoes[chave];
  el(`aviso-${secao.prefixo}`).textContent = "";
  if (secao.selecionados.size >= secao.tamanho) {
    el(`aviso-${secao.prefixo}`).textContent =
      `${secao.rotuloDeck} já tem ${secao.tamanho} cartas — remova uma antes de adicionar outra.`;
    return;
  }
  secao.selecionados.add(carta.nome);
  renderSecao(chave);
}

function remover(chave, carta) {
  const secao = secoes[chave];
  el(`aviso-${secao.prefixo}`).textContent = "";
  secao.selecionados.delete(carta.nome);
  renderSecao(chave);
}

function renderTudo() {
  renderSecao("panteao");
  renderSecao("arcano");
}

// ---- busca -------------------------------------------------------------

el("busca-panteao").addEventListener("input", (e) => {
  secoes.panteao.busca = e.target.value;
  renderSecao("panteao");
});
el("busca-arcano").addEventListener("input", (e) => {
  secoes.arcano.busca = e.target.value;
  renderSecao("arcano");
});

// ---- botões -----------------------------------------------------------

el("btn-salvar-jogar").addEventListener("click", () => {
  const deck = {
    panteao: Array.from(secoes.panteao.selecionados),
    baralhoArcano: Array.from(secoes.arcano.selecionados),
  };
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
  secoes.panteao.selecionados.clear();
  secoes.arcano.selecionados.clear();
  el("erros-deck").innerHTML = "";
  el("aviso-panteao").textContent = "";
  el("aviso-arcano").textContent = "";
  renderTudo();
});

el("btn-voltar-menu").addEventListener("click", () => {
  location.href = "menu.html"; // sem salvar — seleção não confirmada é descartada
});

renderTudo();
mostrarPreview(null);
