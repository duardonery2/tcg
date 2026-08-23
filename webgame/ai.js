// Bot de escolha aleatória: usa os MESMOS validadores/ações de actions.js
// (nunca faz nada que a UI bloquearia de um humano) e o RNG do próprio jogo,
// nunca Math.random() direto — permite reproduzir uma partida inteira por seed.
//
// GAME_DESIGN.md: Maldição só pode ser revelada/ativada "a qualquer momento
// no turno do OPONENTE" — a IA nunca revela a PRÓPRIA Maldição no próprio
// turno (removido de opcoesFaseTatica); ela só ativa Maldições reativamente,
// pelo mesmo TCG.ofertarMaldicoesReativas que o jogador humano usa (curses.js
// resolve sozinho pra quem não é o jogador local, via o listener genérico de
// "selecaoPedida" em ui.js).
//
// Todo o turno é escrito em estilo de continuação (cada `decidirX` recebe um
// `continuar` e só o chama quando termina) porque `invocar`/`ativarHabilidade`/
// `atacar` podem abrir uma decisão de Maldição reativa pro jogador HUMANO no
// meio do turno da IA — sem isso, o resto do turno (e até turnos seguintes)
// rodaria por cima do modal antes do jogador responder.
var TCG = window.TCG || (window.TCG = {});

function opcoesInvocar(game, aiId) {
  const ps = game.players[aiId];
  return TCG.Deck.restantes(game.panteoes[aiId]).filter((c) => c.custoMana <= ps.mana);
}

function decidirInvocar(game, aiId, continuar = () => {}) {
  if (game.board[aiId].monstro !== null) { continuar(); return; }
  const opcoes = opcoesInvocar(game, aiId);
  if (!opcoes.length) { continuar(); return; }
  TCG.acoes.invocar(game, aiId, game.rng.choice(opcoes), continuar);
}

function opcoesFaseTatica(game, aiId) {
  const ps = game.players[aiId];
  const lado = game.board[aiId];
  const opcoes = [];

  for (const carta of ps.mao) {
    if (!["Domínio", "Encantamento", "Maldição"].includes(carta.tipo)) continue;
    // Setar uma Maldição e de graca (o custo so e cobrado na ativação) —
    // só Domínio/Encantamento exigem mana pra jogar.
    if (carta.tipo !== "Maldição" && carta.custoMana > ps.mana) continue;
    if ((carta.tipo === "Domínio" || carta.tipo === "Maldição") && TCG.Board.slotsLivres(lado).length === 0) continue;
    opcoes.push({ tipo: "jogar", carta });
  }

  if (lado.monstro && lado.monstro.custoHabilidade != null && !lado.monstro.habilidadeUsadaNesteTurno
      && lado.monstro.custoHabilidade <= ps.mana) {
    opcoes.push({ tipo: "habilidade" });
  }

  return opcoes;
}

function decidirFaseTatica(game, aiId, continuar = () => {}) {
  // loop: sorteia entre as opcoes legais + "parar", ate parar ou esgotar —
  // permite de 0 a N acoes no turno, de verdade aleatorio.
  function iteracao(i) {
    if (i >= 20 || game.fimDeJogo) { continuar(); return; } // limite de seguranca, nao deveria nunca chegar perto
    const opcoes = opcoesFaseTatica(game, aiId);
    const escolha = game.rng.choice([...opcoes, { tipo: "parar" }]);
    if (escolha.tipo === "parar") { continuar(); return; }
    if (escolha.tipo === "jogar") {
      TCG.acoes.jogarCartaDeCampo(game, aiId, escolha.carta); // Domínio/Encantamento/Maldição setada não são eventos monitorados por Maldição reativa
      iteracao(i + 1);
    } else if (escolha.tipo === "habilidade") {
      TCG.acoes.ativarHabilidade(game, aiId, game.board[aiId].monstro, () => iteracao(i + 1));
    }
  }
  iteracao(0);
}

function decidirCombate(game, aiId, oponenteId, continuar = () => {}) {
  if (game.fimDeJogo) { continuar(); return; }
  const lado = game.board[aiId];
  function depoisDaHabilidade() {
    if (game.fimDeJogo) { continuar(); return; }
    if (lado.monstro) TCG.acoes.atacar(game, aiId, oponenteId, continuar);
    else continuar();
  }
  if (lado.monstro && lado.monstro.custoHabilidade != null && !lado.monstro.habilidadeUsadaNesteTurno
      && lado.monstro.custoHabilidade <= game.players[aiId].mana && game.rng.random() < 0.5) {
    TCG.acoes.ativarHabilidade(game, aiId, lado.monstro, depoisDaHabilidade);
  } else {
    depoisDaHabilidade();
  }
}

TCG.executarTurnoIA = function executarTurnoIA(game, aiId) {
  const oponenteId = TCG.oponenteDe(game, aiId);

  function depoisDeInvocar() {
    TCG.acoes.avancarFase(game); // INVOCACAO -> TATICA
    if (!game.fimDeJogo) decidirFaseTatica(game, aiId, depoisDeTatica);
    else depoisDeTatica();
  }
  function depoisDeTatica() {
    TCG.acoes.avancarFase(game); // TATICA -> COMBATE
    if (!game.fimDeJogo) decidirCombate(game, aiId, oponenteId, depoisDeCombate);
    else depoisDeCombate();
  }
  function depoisDeCombate() {
    if (!game.fimDeJogo) TCG.acoes.terminarTurno(game); // COMBATE -> RECURSO do proximo jogador
  }

  TCG.acoes.avancarFase(game); // RECURSO -> INVOCACAO
  if (!game.fimDeJogo) decidirInvocar(game, aiId, depoisDeInvocar);
  else depoisDeInvocar();
};
