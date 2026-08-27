// Acoes do Jogador — validam fase/mana/slot antes de mutar, sempre chamadas
// via TCG.acoes.* (nunca mexendo no estado direto). Espelha game/actions.py.
var TCG = window.TCG || (window.TCG = {});

TCG.AcaoInvalida = class AcaoInvalida extends Error {};

function exigirFase(game, playerId, fasesPermitidas) {
  if (game.jogadorDaVez !== playerId) throw new TCG.AcaoInvalida("Não é a vez desse jogador.");
  if (!fasesPermitidas.includes(game.fase)) {
    throw new TCG.AcaoInvalida(`Ação exige a Fase ${fasesPermitidas.join("/")}, mas o jogo está na Fase ${game.fase}.`);
  }
}

function pagarMana(game, playerId, custo) {
  const ps = game.players[playerId];
  if (ps.mana < custo) throw new TCG.AcaoInvalida(`Mana insuficiente: precisa de ${custo}, tem ${ps.mana}.`);
  ps.mana -= custo;
  game.bus.emit("manaAlterada", { playerId, delta: -custo, total: ps.mana });
}

// "Encantamentos Contínuos" (GAME_DESIGN.md) — em vez de resolver e ir pra
// Pilha de Descarte como todo Encantamento normal, ficam em campo (num slot
// de magia, igual Domínio/Maldição) enquanto o efeito passivo de +Mana por
// turno estiver ativo. Custo de Mana 0 de propósito — o "custo" real é o
// sacrifício pago no próprio efeito (descarte, vida, POW/RES). Não usa um
// campo novo no CSV: o tipo continua "Encantamento", só o NOME está nesta
// lista — mesmo padrão de tabela-por-nome já usado por SONS/regGatilhoMaldicao,
// sem mexer no schema do CSV/loader. Espelha game/actions.py.
const ENCANTAMENTOS_CONTINUOS = new Set(["Oásis do Saara", "Geleiras do Ártico", "Selva Amazônica"]);

TCG.acoes = {
  // Fase de Invocação: traz um Combatente do Panteão pro slot de Monstro.
  // `continuar` (opcional): chamada quando a ação (incluindo qualquer
  // decisão de Maldição reativa que "invocar" torne elegível) está
  // totalmente resolvida — usado pelo turno automático da IA (ai.js) pra
  // só seguir pro próximo passo depois de uma decisão do jogador humano em
  // resposta, em vez de continuar o turno inteiro por cima dela.
  invocar(game, playerId, carta, continuar = () => {}) {
    exigirFase(game, playerId, ["INVOCACAO"]);
    const lado = game.board[playerId];
    if (lado.monstro !== null) throw new TCG.AcaoInvalida("Já há um combatente ativo neste lado do tabuleiro.");
    pagarMana(game, playerId, carta.custoMana);
    TCG.Deck.tirarEspecifica(game.panteoes[playerId], carta);
    // zera flags de "já usado neste turno" ao ENTRAR em campo — sem isso,
    // um combatente que atacou, voltou ao Panteão no mesmo turno (Cânion dos
    // Ventos) e foi invocado de novo depois ficaria com atacouNesteTurno
    // travado em true pra sempre (upkeep só reresta quem já está em campo).
    carta.atacouNesteTurno = false;
    carta.habilidadeUsadaNesteTurno = false;
    TCG.Board.colocarMonstro(lado, carta);
    game.bus.emit("combatenteInvocado", { playerId, carta });
    TCG.checarFimDeJogo(game);
    TCG.ofertarMaldicoesReativas(game, { tipo: "combatenteInvocado", playerId, carta }, continuar);
  },

  // Fase Principal ou de Batalha, 1x por turno: paga o Custo de Habilidade e
  // dispara o efeito da carta. A decisão de Maldição reativa (ex.: Roubo de
  // Essência) acontece ANTES do efeito da própria Habilidade resolver.
  ativarHabilidade(game, playerId, carta, continuar = () => {}) {
    exigirFase(game, playerId, ["PRINCIPAL", "BATALHA"]);
    if (game.board[playerId].monstro !== carta) throw new TCG.AcaoInvalida("Essa carta não é o combatente ativo desse jogador.");
    if (carta.custoHabilidade == null) throw new TCG.AcaoInvalida("Essa carta não tem Habilidade ativável.");
    if (carta.habilidadeUsadaNesteTurno) throw new TCG.AcaoInvalida("Habilidade já usada neste turno.");
    pagarMana(game, playerId, carta.custoHabilidade);
    carta.habilidadeUsadaNesteTurno = true;
    game.bus.emit("habilidadeAtivada", { playerId, carta });
    TCG.ofertarMaldicoesReativas(game, { tipo: "habilidadeAtivada", playerId, carta }, () => {
      TCG.executarEfeito(game, carta.nome, playerId, carta);
      continuar();
    });
  },

  // Fase Principal: joga uma carta de campo da mão — Domínio, Encantamento ou
  // Maldição, unificados no mesmo passo (ver plano). Maldição e a excecao:
  // setar (colocar virada pra baixo) e de graca — o Custo de Mana da carta
  // so e cobrado depois, na hora de revelar/ativar (ver ativarMaldicaoSetada).
  jogarCartaDeCampo(game, playerId, carta, slot = null) {
    exigirFase(game, playerId, ["PRINCIPAL"]);
    const ps = game.players[playerId];
    if (!ps.mao.includes(carta)) throw new TCG.AcaoInvalida("Essa carta não está na mão desse jogador.");

    const lado = game.board[playerId];
    if (carta.tipo === "Domínio") {
      // Só pode haver 1 Domínio ativo NO JOGO INTEIRO — "só pode haver um
      // ativo na mesa" (GAME_DESIGN.md) é a mesa compartilhada dos dois
      // jogadores, não uma por lado. Jogar um novo destrói QUALQUER um já
      // ativo, seja de quem for (o do próprio jogador OU o do oponente).
      const anteriorProprio = TCG.Board.dominioAtivo(lado);
      if (anteriorProprio) TCG.destroyCard(game, anteriorProprio, "substituído por novo Domínio");
      const anteriorOponente = TCG.dominioAtivo(game, TCG.oponenteDe(game, playerId));
      if (anteriorOponente) TCG.destroyCard(game, anteriorOponente, "substituído por novo Domínio");
      // checa DEPOIS de liberar o próprio slot (se havia um Domínio antes) e
      // ANTES de pagar mana/tirar da mão — senão, sem slot livre, a mana
      // seria cobrada e a carta perdida da mão sem ir pra lugar nenhum.
      if (slot === null && TCG.Board.slotsLivres(lado).length === 0) {
        throw new TCG.AcaoInvalida("Não há slot de magia livre (limite de 5) pra ativar o Domínio.");
      }
      // destruir o Domínio anterior pode disparar gatilhos de terceiros
      // (ex.: Caixa de Pandora força um descarte aleatório) que, em tese,
      // poderiam pegar justo ESTA carta ainda na mão antes dela ser
      // colocada em campo — confere de novo em vez de deixar indexOf(-1)
      // corromper silenciosamente outra carta da mão via splice(-1, 1).
      if (!ps.mao.includes(carta)) {
        throw new TCG.AcaoInvalida("Essa carta foi descartada por um efeito antes de poder ser ativada.");
      }
      pagarMana(game, playerId, carta.custoMana);
      ps.mao.splice(ps.mao.indexOf(carta), 1);
      const s = TCG.Board.colocarMagia(lado, carta, slot);
      game.ultimoDominioAtivadoPor = playerId; // ver TCG.dominioParaFundo
      game.bus.emit("dominioAtivado", { playerId, carta, slot: s });
      TCG.executarEfeito(game, carta.nome, playerId, carta);
    } else if (carta.tipo === "Encantamento") {
      const continuo = ENCANTAMENTOS_CONTINUOS.has(carta.nome);
      if (continuo && slot === null && TCG.Board.slotsLivres(lado).length === 0) {
        throw new TCG.AcaoInvalida("Não há slot de magia livre (limite de 5) pra jogar este Encantamento Contínuo.");
      }
      pagarMana(game, playerId, carta.custoMana);
      ps.mao.splice(ps.mao.indexOf(carta), 1);
      game.bus.emit("encantamentoJogado", { playerId, carta });
      TCG.executarEfeito(game, carta.nome, playerId, carta);
      if (continuo) {
        TCG.Board.colocarMagia(lado, carta, slot);
      } else {
        game.descarte[playerId].push(carta);
      }
    } else if (carta.tipo === "Maldição") {
      // mesmo cuidado do Domínio: checa slot livre ANTES de tirar da mão
      // (setar é grátis, mas a carta não pode simplesmente sumir).
      if (slot === null && TCG.Board.slotsLivres(lado).length === 0) {
        throw new TCG.AcaoInvalida("Não há slot de magia livre (limite de 5) pra setar a Maldição.");
      }
      ps.mao.splice(ps.mao.indexOf(carta), 1);
      carta.faceDown = true;
      const s = TCG.Board.colocarMagia(lado, carta, slot);
      game.bus.emit("maldicaoColocada", { playerId, carta, slot: s });
    } else {
      throw new TCG.AcaoInvalida(`"${carta.nome}" não é uma carta de campo (Domínio/Encantamento/Maldição).`);
    }
  },

  // Revela e resolve uma Maldição já setada — chamada pela decisão do dono
  // dentro de TCG.ofertarMaldicoesReativas (curses.js), nunca solta. E aqui,
  // na ativação, que o Custo de Mana da carta é cobrado (setar foi de
  // graça). `evento` (opcional): o evento que motivou a oferta, repassado
  // pro efeito da carta (ver comentário no topo da seção Maldições de
  // effects.js) — fica `null` se revelada manualmente (clique direto no
  // próprio verso em campo), sem um evento associado.
  ativarMaldicaoSetada(game, playerId, carta, evento = null) {
    const lado = game.board[playerId];
    if (!lado.magia.includes(carta)) throw new TCG.AcaoInvalida("Essa Maldição não está setada nesse lado do tabuleiro.");
    pagarMana(game, playerId, carta.custoMana);
    carta.faceDown = false;
    game.bus.emit("maldicaoAtivada", { playerId, carta });
    TCG.executarEfeito(game, carta.nome, playerId, carta, evento);
    TCG.destroyCard(game, carta, "Maldição ativada");
  },

  // Fase de Batalha: confronta o combatente ativo contra o do oponente (ou
  // os Pontos de Vida dele, se o campo estiver vazio). Só uma vez por turno
  // por combatente — um segundo ataque só acontece via efeito de carta
  // (ex.: Aquiles), que causa o dano direto sem passar por esta ação.
  atacar(game, playerId, oponenteId, continuar = () => {}) {
    exigirFase(game, playerId, ["BATALHA"]);
    if (game.turno === 1) throw new TCG.AcaoInvalida("Não é possível atacar no primeiro turno.");
    const atacante = game.board[playerId].monstro;
    if (!atacante) throw new TCG.AcaoInvalida("Não há combatente ativo pra atacar.");
    if (atacante.atacouNesteTurno) throw new TCG.AcaoInvalida("Esse combatente já atacou neste turno.");
    atacante.atacouNesteTurno = true;

    // Maldições reativas elegíveis pro ataque (Escudo de Gelo Absoluto,
    // Espelho das Ilusões, Barreira de Vento Cortante, Retribuição Kármica,
    // Vínculo Sombrio) precisam decidir ANTES do dano ser calculado — pro
    // jogador local isso aparece como modal; pra IA resolve sozinho (ver o
    // listener de "selecaoPedida" pro lado não-local, em ui.js).
    const evento = { tipo: "ataqueDeclarado", atacantePlayer: playerId, atacante, defensorPlayer: oponenteId, defensor: game.board[oponenteId].monstro };
    TCG.ofertarMaldicoesReativas(game, evento, () => {
      TCG.resolverAtaque(game, playerId, atacante, oponenteId, game.board[oponenteId].monstro);
      continuar();
    });
  },

  avancarFase(game) {
    return TCG.avancarFase(game);
  },

  terminarTurno(game) {
    const inicial = game.jogadorDaVez;
    do { TCG.avancarFase(game); } while (game.jogadorDaVez === inicial && !game.fimDeJogo);
  },
};
