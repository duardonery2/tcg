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

// A IA de teste "pensa" por um tempo fixo antes de CADA decisão (não antes de
// cada avanço de fase automático) — dá tempo do jogador humano acompanhar o
// que está acontecendo na tela em vez do turno inteiro resolver num piscar.
TCG.IA_ATRASO_MS = 3000;

function decidir(fn) {
  setTimeout(fn, TCG.IA_ATRASO_MS);
}

function opcoesInvocar(game, aiId) {
  const ps = game.players[aiId];
  return TCG.Deck.restantes(game.panteoes[aiId]).filter((c) => c.custoMana <= ps.mana);
}

function decidirInvocar(game, aiId, continuar = () => {}) {
  decidir(() => {
    if (game.board[aiId].monstro !== null) { continuar(); return; }
    const opcoes = opcoesInvocar(game, aiId);
    if (!opcoes.length) { continuar(); return; }
    TCG.acoes.invocar(game, aiId, game.rng.choice(opcoes), continuar);
  });
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

function decidirFasePrincipal(game, aiId, continuar = () => {}) {
  // loop: sorteia entre as opcoes legais + "parar", ate parar ou esgotar —
  // permite de 0 a N acoes no turno, de verdade aleatorio. Cada iteracao e
  // uma decisao nova, com seu proprio atraso.
  function iteracao(i) {
    if (i >= 20 || game.fimDeJogo) { continuar(); return; } // limite de seguranca, nao deveria nunca chegar perto
    decidir(() => {
      const opcoes = opcoesFaseTatica(game, aiId);
      const escolha = game.rng.choice([...opcoes, { tipo: "parar" }]);
      if (escolha.tipo === "parar") { continuar(); return; }
      if (escolha.tipo === "jogar") {
        TCG.acoes.jogarCartaDeCampo(game, aiId, escolha.carta); // Domínio/Encantamento/Maldição setada não são eventos monitorados por Maldição reativa
        iteracao(i + 1);
      } else if (escolha.tipo === "habilidade") {
        TCG.acoes.ativarHabilidade(game, aiId, game.board[aiId].monstro, () => iteracao(i + 1));
      }
    });
  }
  iteracao(0);
}

function decidirBatalha(game, aiId, oponenteId, continuar = () => {}) {
  if (game.fimDeJogo) { continuar(); return; }
  const lado = game.board[aiId];
  function depoisDaHabilidade() {
    if (game.fimDeJogo) { continuar(); return; }
    decidir(() => {
      if (lado.monstro) TCG.acoes.atacar(game, aiId, oponenteId, continuar);
      else continuar();
    });
  }
  decidir(() => {
    if (lado.monstro && lado.monstro.custoHabilidade != null && !lado.monstro.habilidadeUsadaNesteTurno
        && lado.monstro.custoHabilidade <= game.players[aiId].mana && game.rng.random() < 0.5) {
      TCG.acoes.ativarHabilidade(game, aiId, lado.monstro, depoisDaHabilidade);
    } else {
      depoisDaHabilidade();
    }
  });
}

TCG.executarTurnoIA = function executarTurnoIA(game, aiId) {
  const oponenteId = TCG.oponenteDe(game, aiId);

  function depoisDeInvocar() {
    TCG.acoes.avancarFase(game); // INVOCACAO -> PRINCIPAL
    if (!game.fimDeJogo) decidirFasePrincipal(game, aiId, depoisDePrincipal);
    else depoisDePrincipal();
  }
  function depoisDePrincipal() {
    TCG.acoes.avancarFase(game); // PRINCIPAL -> BATALHA
    if (!game.fimDeJogo) decidirBatalha(game, aiId, oponenteId, depoisDeBatalha);
    else depoisDeBatalha();
  }
  function depoisDeBatalha() {
    if (!game.fimDeJogo) TCG.acoes.terminarTurno(game); // BATALHA -> FINAL -> SAQUE do proximo jogador
  }

  TCG.acoes.avancarFase(game); // SAQUE -> INVOCACAO
  if (!game.fimDeJogo) decidirInvocar(game, aiId, depoisDeInvocar);
  else depoisDeInvocar();
};
