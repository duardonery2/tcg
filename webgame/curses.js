// Oferece, no momento certo, a decisão de ativar uma Maldição virada para
// baixo em reação a um evento específico — GAME_DESIGN.md: "Revelar/ativar
// uma Maldição já setada: a qualquer momento no turno do OPONENTE." Cada
// Maldição declara (regGatilhoMaldicao, em effects.js) o evento que a torna
// elegível pro modal; isso substitui a lógica antiga (só existia pro ataque,
// e oferecia QUALQUER Maldição virada pra baixo, sem checar se fazia sentido
// pro evento).
var TCG = window.TCG || (window.TCG = {});

// Acha, entre as Maldições viradas pra baixo de quem NÃO está na vez, as que
// têm um gatilho declarado batendo com `evento.tipo`, cuja condição aceita, e
// que o dono ainda tem mana pra pagar (senão a escolha ia estourar ao tentar
// ativar — mesmo cuidado que a IA já tinha antes de oferecer "revelar").
TCG.maldicoesElegiveis = function maldicoesElegiveis(game, evento) {
  const elegiveis = [];
  for (const pid of game.jogadores) {
    if (pid === game.jogadorDaVez) continue; // só quem NÃO está na vez pode reagir
    for (const carta of game.board[pid].magia) {
      if (!carta || !carta.faceDown) continue;
      if (carta.custoMana > game.players[pid].mana) continue;
      const gatilho = TCG.GATILHOS_DE_MALDICAO[carta.nome];
      if (!gatilho || gatilho.eventoTipo !== evento.tipo) continue;
      if (gatilho.condicao(evento, game, pid)) elegiveis.push({ donoId: pid, carta });
    }
  }
  return elegiveis;
};

// Pausa o fluxo — mesmo mecanismo de seleção que já mostra modal pro jogador
// local e resolve sozinho pra IA (ver selection.js e o listener genérico de
// "selecaoPedida" em ui.js) — até que cada dono elegível decida ativar uma
// Maldição (ou nenhuma). `continuar` só roda depois de TODAS as decisões
// resolvidas (na prática, quase sempre um único dono).
TCG.ofertarMaldicoesReativas = function ofertarMaldicoesReativas(game, evento, continuar = () => {}) {
  const elegiveis = TCG.maldicoesElegiveis(game, evento);
  const donos = [...new Set(elegiveis.map((e) => e.donoId))];

  function processar(i) {
    if (i >= donos.length) { continuar(); return; }
    const donoId = donos[i];
    const lado = game.board[donoId];
    const cartas = elegiveis
      .filter((e) => e.donoId === donoId)
      .map((e) => e.carta)
      .filter((c) => lado.magia.includes(c) && c.faceDown); // ainda válidas nesse instante
    if (!cartas.length) { processar(i + 1); return; }
    game.selection.solicitar(
      donoId,
      "Uma Maldição virada para baixo pode ser ativada agora. Ativar uma delas?",
      cartas,
      (escolha) => {
        if (escolha.length) {
          try {
            TCG.acoes.ativarMaldicaoSetada(game, donoId, escolha[0], evento);
          } catch (e) {
            if (!(e instanceof TCG.AcaoInvalida)) throw e; // defensivo: estado pode ter mudado entre a oferta e a escolha
          }
        }
        processar(i + 1);
      },
      0, 1
    );
  }
  processar(0);
};
