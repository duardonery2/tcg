// Deck: sorteia aleatoriamente 1 carta ainda nao comprada da sua lista.
// Espelha game/deck.py. O Panteao usa a MESMA estrutura (ver engine.js) — a
// escolha de qual Combatente invocar passa pela selecao do jogador, nao por
// sorteio; sortear e so o mecanismo de COMPRA automatica do Baralho Arcano.
var TCG = window.TCG || (window.TCG = {});

// PRNG determinístico (mulberry32) — permite reproduzir uma partida inteira
// por seed, tanto pra depuração quanto pra verificação automatizada.
TCG.criarRng = function criarRng(seed) {
  let a = (seed == null ? Math.floor(Math.random() * 2 ** 32) : seed) >>> 0;
  function proximo() {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  return {
    seed,
    random: proximo,
    choice(arr) {
      return arr[Math.floor(proximo() * arr.length)];
    },
    sample(arr, n) {
      const copia = arr.slice();
      const resultado = [];
      for (let i = 0; i < n && copia.length > 0; i++) {
        const idx = Math.floor(proximo() * copia.length);
        resultado.push(copia.splice(idx, 1)[0]);
      }
      return resultado;
    },
    shuffle(arr) {
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(proximo() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
      return arr;
    },
  };
};

TCG.criarDeck = function criarDeck(nome, cartas) {
  return { nome, cartas: cartas.slice(), compradas: new Set() };
};

TCG.Deck = {
  restantes(deck) {
    return deck.cartas.filter((c) => !deck.compradas.has(c));
  },

  estaVazio(deck) {
    return TCG.Deck.restantes(deck).length === 0;
  },

  drawRandom(deck, rng) {
    const opcoes = TCG.Deck.restantes(deck);
    if (opcoes.length === 0) throw new Error(`O deck '${deck.nome}' esta vazio.`);
    const carta = rng.choice(opcoes);
    deck.compradas.add(carta);
    return carta;
  },

  tirarEspecifica(deck, carta) {
    if (!deck.cartas.includes(carta)) throw new Error(`${carta.nome} nao pertence ao deck '${deck.nome}'.`);
    if (deck.compradas.has(carta)) throw new Error(`${carta.nome} ja foi retirada de '${deck.nome}'.`);
    deck.compradas.add(carta);
    return carta;
  },

  devolver(deck, carta) {
    deck.compradas.delete(carta);
  },

  adicionar(deck, carta) {
    if (!deck.cartas.includes(carta)) deck.cartas.push(carta);
    deck.compradas.delete(carta);
  },

  embaralhar(deck, rng) {
    const restantes = rng.shuffle(TCG.Deck.restantes(deck));
    const compradasOrdem = deck.cartas.filter((c) => deck.compradas.has(c));
    deck.cartas = compradasOrdem.concat(restantes);
  },

  topo(deck, n = 1) {
    return TCG.Deck.restantes(deck).slice(0, n);
  },
};
