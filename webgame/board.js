// Tabuleiro: 1 slot de Monstro + 5 slots de Magia por jogador. Espelha game/board.py.
var TCG = window.TCG || (window.TCG = {});

TCG.N_SLOTS_MAGIA = 5;

TCG.criarLadoTabuleiro = function criarLadoTabuleiro(playerId) {
  return { playerId, monstro: null, magia: new Array(TCG.N_SLOTS_MAGIA).fill(null) };
};

TCG.Board = {
  slotsLivres(lado) {
    const livres = [];
    lado.magia.forEach((v, i) => { if (v === null) livres.push(i); });
    return livres;
  },

  // Próximo slot a ser ocupado quando ninguém pede um índice específico:
  // sempre o mais à DIREITA ainda livre — mesma convenção da mão (ver
  // rectProximoSlotDeMao em ui.js), pra a animação de voo (rectSlotDeMagia)
  // ter garantia de mirar o mesmo lugar onde a carta realmente vai cair.
  proximoSlotLivre(lado) {
    const livres = TCG.Board.slotsLivres(lado);
    return livres.length ? livres[livres.length - 1] : null;
  },

  colocarMonstro(lado, carta) {
    if (lado.monstro !== null) throw new Error("Ja existe um combatente ativo neste lado do tabuleiro.");
    lado.monstro = carta;
  },

  removerMonstro(lado) {
    const carta = lado.monstro;
    lado.monstro = null;
    return carta;
  },

  colocarMagia(lado, carta, slot = null) {
    if (slot === null) {
      slot = TCG.Board.proximoSlotLivre(lado);
      if (slot === null) throw new Error("Nao ha slot de magia livre (limite de 5).");
    } else if (lado.magia[slot] !== null) {
      throw new Error(`Slot de magia ${slot} ja ocupado.`);
    }
    lado.magia[slot] = carta;
    return slot;
  },

  removerMagia(lado, carta) {
    const i = lado.magia.indexOf(carta);
    if (i === -1) throw new Error(`${carta.nome} nao esta em nenhum slot de magia deste lado.`);
    lado.magia[i] = null;
    return i;
  },

  dominioAtivo(lado) {
    return lado.magia.find((c) => c !== null && c.tipo === "Domínio") || null;
  },
};
