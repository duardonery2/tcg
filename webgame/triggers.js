// Pilha de gatilhos + efeitos passivos.
//
// Gatilhos: uma carta em campo (Domínio, Maldição revelada) pode registrar um
// gatilho que fica esperando um EVENTO futuro em vez de mudar o estado na
// hora (TCG.registrarTrigger). Toda vez que QUALQUER evento é publicado no
// EventBus (ver events.js — o bus chama TCG.dispararTriggers logo depois de
// empilhar no historico), roda a lista de gatilhos pra ver se algum bate com
// o tipo do evento e, se a condição aceitar, dispara o efeito. É o único
// lugar onde "Quando X"/"Sempre que X" são resolvidos — nada bespoke espalhado.
//
// Passivos: um Domínio "enquanto ativo" registra um efeito PASSIVO
// (TCG.registrarPassivo), reaplicado do zero — limpa e reaplica — a cada
// Fase Principal de QUALQUER jogador (TCG.aplicarPassivos, chamado por
// TCG.avancarFase), e removido (com limpeza) assim que a carta-fonte sai de
// campo, pelo único ponto de destruição (TCG.destroyCard).
var TCG = window.TCG || (window.TCG = {});

TCG.registrarTrigger = function registrarTrigger(game, {
  ownerPlayerId = null, origemCarta, eventoTipo, condicao = () => true, efeito, persistente = true,
}) {
  const t = { ownerPlayerId, origemCarta, eventoTipo, condicao, efeito, persistente };
  game.triggers.push(t);
  return t;
};

TCG.removerTriggersDe = function removerTriggersDe(game, origemCarta) {
  game.triggers = game.triggers.filter((t) => t.origemCarta !== origemCarta);
};

TCG.dispararTriggers = function dispararTriggers(game, evento) {
  const candidatos = game.triggers.filter((t) => t.eventoTipo === evento.tipo);
  for (const t of candidatos) {
    if (!game.triggers.includes(t)) continue; // pode ter sido removido por um trigger anterior neste mesmo lote
    if (t.condicao(evento, game)) {
      t.efeito(evento, game);
      if (!t.persistente) game.triggers = game.triggers.filter((x) => x !== t);
    }
  }
};

// Percorre os dois lados e remove todo StatusEffect com essa `origem`
// (nome da carta-fonte), recalculando stats de quem foi afetado — usado
// tanto pra limpar um passivo removido quanto como o "limpar" padrão antes
// de reaplicar (ver TCG.aplicarPassivos).
TCG.limparStatusPorOrigem = function limparStatusPorOrigem(game, origem) {
  for (const pid of game.jogadores) {
    const carta = game.board[pid].monstro;
    if (!carta) continue;
    const antes = carta.statusEffects.length;
    carta.statusEffects = carta.statusEffects.filter((st) => st.origem !== origem);
    if (carta.statusEffects.length !== antes) TCG.recalcularStats(carta);
  }
};

TCG.registrarPassivo = function registrarPassivo(game, playerId, carta, aplicarFn, limparFn = null) {
  const limpar = limparFn || ((g, c) => TCG.limparStatusPorOrigem(g, c.nome));
  game.passivos.push({ playerId, carta, aplicar: aplicarFn, limpar });
};

TCG.removerPassivosDe = function removerPassivosDe(game, carta) {
  const restantes = [];
  for (const p of game.passivos) {
    if (p.carta === carta) p.limpar(game, carta);
    else restantes.push(p);
  }
  game.passivos = restantes;
};

TCG.aplicarPassivos = function aplicarPassivos(game) {
  // limpa-e-reaplica roda em TODA Fase Principal, mesmo quando nada mudou —
  // suprime o evento "statusAlterado" (ver TCG.buff, effects.js) durante
  // esse ciclo pra não piscar um flash de UI toda vez sem nenhuma mudança
  // visível de verdade.
  game._reaplicandoPassivos = true;
  for (const p of game.passivos) {
    p.limpar(game, p.carta);
    p.aplicar(game, p.playerId, p.carta);
  }
  game._reaplicandoPassivos = false;
};
