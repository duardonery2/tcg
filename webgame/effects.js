// Efeitos de carta: as ~60 cartas cobertas em game/effects.py, traduzidas 1:1,
// como composicao de primitivas. Efeitos com uma parte PASSIVA ("enquanto
// ativo...") ou de GATILHO ("Quando"/"Sempre que"/"No início do turno") usam
// regPassivo/TCG.registrarTrigger (ver triggers.js) em vez de mutar o estado
// direto — mesmas simplificacoes que restam documentadas no topo de
// game/effects.py (Rebote Arcano, Praga da Ferrugem/Equipamento). "Apoio
// Incondicional" fica de fora de proposito — cai no fallback (nenhum efeito
// registrado, no-op).
var TCG = window.TCG || (window.TCG = {});

TCG.EFFECTS = {};
TCG.EFFECTS_ON_DESTROY = {};

// ---- primitivas -----------------------------------------------------

TCG.buff = function buff(game, carta, atributo, magnitude, duracao = "PERMANENTE", origem = "") {
  const campo = atributo === "pow" ? "atualPow" : "atualRes";
  const antes = carta[campo];
  carta.statusEffects.push({ atributo, magnitude, duracao, origem });
  TCG.recalcularStats(carta);
  // "statusAlterado": sinal genérico pra UI animar um alvo específico sem
  // precisar saber qual efeito de carta causou (a maioria buffa um alvo
  // DIFERENTE da carta nomeada no evento que disparou, ex.: Pacto de
  // Sangue nomeia o próprio Encantamento, não o combatente buffado).
  // Suprimido durante TCG.aplicarPassivos (ver triggers.js) — senão TODO
  // Domínio passivo piscaria a cada Fase Tática, mesmo sem nada mudar.
  if (!game._reaplicandoPassivos) {
    const delta = carta[campo] - antes;
    if (delta !== 0) game.bus.emit("statusAlterado", { carta, atributo, delta, origem });
  }
};

TCG.curar = function curar(game, carta, quantidade) {
  if (carta.combate === null) return;
  // Cura nao passa da Resistencia base (nao "sobre-cura" acima do impresso),
  // mas tambem nunca REDUZ o valor atual — se um buff ja tiver deixado a
  // Resistencia acima da base, curar nao pode derrubar isso de volta.
  const antes = carta.atualRes;
  carta.atualRes = Math.max(carta.atualRes, Math.min(carta.atualRes + quantidade, carta.resistencia));
  const delta = carta.atualRes - antes;
  if (delta > 0) game.bus.emit("statusAlterado", { carta, atributo: "res", delta, origem: "cura" });
};

TCG.danoCombatente = function danoCombatente(game, carta, quantidade, origem = "") {
  if (!carta) return;
  // Jardins Suspensos: "todo dano recebido por combatentes de Terra é
  // reduzido em 3" (passivo, ver game.reducaoDanoTerra em effects.js).
  if (game.reducaoDanoTerra && TCG.elementoEfetivo(carta) === "Terra") {
    quantidade = Math.max(quantidade - game.reducaoDanoTerra, 0);
  }
  carta.atualRes = Math.max(carta.atualRes - quantidade, 0);
  game.bus.emit("danoCausado", { alvo: carta, alvoPlayer: null, quantidade, origem });
  if (carta.atualRes <= 0) TCG.destroyCard(game, carta, origem || "destruido por efeito");
};

TCG.danoJogador = function danoJogador(game, playerId, quantidade, origem = "") {
  const ps = game.players[playerId];
  ps.vida = Math.max(ps.vida - quantidade, 0);
  game.bus.emit("vidaAlterada", { playerId, delta: -quantidade, total: ps.vida });
  game.bus.emit("danoCausado", { alvo: null, alvoPlayer: playerId, quantidade, origem });
};

TCG.destruir = function destruir(game, carta, motivo = "") {
  if (!carta) return;
  TCG.destroyCard(game, carta, motivo);
};

TCG.ganharMana = function ganharMana(game, playerId, n) {
  const ps = game.players[playerId];
  ps.mana += n;
  game.bus.emit("manaAlterada", { playerId, delta: n, total: ps.mana });
};

TCG.perderMana = function perderMana(game, playerId, n) {
  const ps = game.players[playerId];
  const roubado = Math.min(n, ps.mana);
  ps.mana -= roubado;
  game.bus.emit("manaAlterada", { playerId, delta: -roubado, total: ps.mana });
  return roubado;
};

TCG.retornarAoPanteao = function retornarAoPanteao(game, playerId, carta) {
  if (!carta) return;
  const lado = game.board[playerId];
  if (lado.monstro === carta) TCG.Board.removerMonstro(lado);
  TCG.Deck.devolver(game.panteoes[playerId], carta);
};

TCG.protegidoContraMaldicao = function protegidoContraMaldicao(game, playerId) {
  if (game._protecaoMaldicao && game._protecaoMaldicao.has(playerId)) {
    game._protecaoMaldicao.delete(playerId);
    return true;
  }
  return false;
};

TCG.negarProximoAtaque = function negarProximoAtaque(game, carta) {
  carta.attackNegated = true;
};

TCG.refletirDano = function refletirDano(game, carta) {
  carta.damageReflected = true;
};

// ---- registro -----------------------------------------------------

// `evento` (opcional): o evento que motivou essa ativação, pra Maldições
// reativas (ver TCG.ofertarMaldicoesReativas) lerem o alvo certo direto dele
// (ex.: "o combatente INVOCADO") em vez de adivinhar pelo estado atual.
TCG.executarEfeito = function executarEfeito(game, nome, playerId, carta, evento = null) {
  const fn = TCG.EFFECTS[nome];
  if (!fn) {
    console.warn(`[effects] nenhum efeito implementado para '${nome}', ignorando.`);
    return;
  }
  fn(game, playerId, carta, evento);
};

function reg(nome, fn) { TCG.EFFECTS[nome] = fn; }
function regDestroy(nome, fn) { TCG.EFFECTS_ON_DESTROY[nome] = fn; }

// Efeito PASSIVO ("enquanto ativo..."): `aplicarFn` roda já na ativação e de
// novo a cada Fase Tática (limpa-e-reaplica, ver TCG.aplicarPassivos), até a
// carta-fonte sair de campo. `limparFn` (opcional) desfaz o que `aplicarFn`
// fez — o padrão remove os StatusEffects com origem = nome da carta, o que
// cobre a maioria dos casos (buff de atributo); passe um `limparFn` próprio
// quando o passivo mexe em outra coisa (uma flag em `game`, por exemplo).
function regPassivo(nome, aplicarFn, limparFn = null) {
  TCG.EFFECTS[nome] = (game, playerId, carta) => {
    TCG.registrarPassivo(game, playerId, carta, aplicarFn, limparFn);
    aplicarFn(game, playerId, carta);
  };
}

// Tabela declarativa: qual evento torna uma Maldição virada pra baixo
// ELEGÍVEL pro modal de "ativar agora?" (ver TCG.ofertarMaldicoesReativas,
// curses.js). Sem entrada aqui = a Maldição nunca aparece nesse modal (ex.:
// Praga da Ferrugem, que depende de um subtipo "Equipamento" inexistente
// nos dados desta versão).
TCG.GATILHOS_DE_MALDICAO = {};
function regGatilhoMaldicao(nome, eventoTipo, condicao = () => true) {
  TCG.GATILHOS_DE_MALDICAO[nome] = { eventoTipo, condicao };
}

// ---- Heróis -----------------------------------------------------------

reg("Rei Arthur", (game, playerId, carta) => TCG.buff(game, carta, "pow", 4, "NESTE_TURNO", "Excalibur"));

reg("Beowulf", (game, playerId, carta) => TCG.curar(game, carta, 4));

reg("Odisseu", (game, playerId, carta) => {
  game._protecaoMaldicao = game._protecaoMaldicao || new Set();
  game._protecaoMaldicao.add(playerId);
});

reg("Sigurd", (game, playerId, carta) => {
  const oponente = TCG.oponenteDe(game, playerId);
  const alvo = TCG.combatenteAtivo(game, oponente);
  if (alvo && alvo.tipo === "Monstro") TCG.danoCombatente(game, alvo, carta.atualPow, "Matador de Feras");
});

reg("Joana d'Arc", (game, playerId, carta) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  // mesmo cuidado de TCG.curar: nunca reduz um atualRes ja acima da base
  // por causa de buff permanente.
  if (alvo) alvo.atualRes = Math.max(alvo.atualRes, alvo.resistencia);
});

reg("Gilgamesh", (game, playerId) => TCG.comprar(game, playerId, 1)); // simplificado: sem subtipo "Equipamento" nos dados

reg("Aquiles", (game, playerId, carta) => {
  const oponente = TCG.oponenteDe(game, playerId);
  const meio = Math.floor(carta.atualPow / 2);
  for (let i = 0; i < 2; i++) {
    const defensor = TCG.combatenteAtivo(game, oponente);
    if (defensor) TCG.danoCombatente(game, defensor, meio, "Rapidez");
    else TCG.danoJogador(game, oponente, meio, "Rapidez");
  }
});

reg("Atalanta", (game, playerId) => TCG.danoJogador(game, TCG.oponenteDe(game, playerId), 5, "Flecha Veloz"));

// "Se for derrotado NO ATAQUE, o alvo também é" — não é um efeito pra
// disparar na hora que a Habilidade é ativada, e sim um gatilho de morte:
// registra um trigger em `cartaDestruida` que só faz alguma coisa se a carta
// destruída for o PRÓPRIO Cu Chulainn E se isso aconteceu por dano refletido
// durante o ataque dele mesmo (único jeito, nesta versão, de um atacante
// "ser derrotado no ataque" — não há contra-ataque comum modelado).
reg("Cu Chulainn", (game, playerId, carta) => {
  TCG.removerTriggersDe(game, carta); // evita empilhar de novo se a Habilidade for ativada mais de 1 vez
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    ownerPlayerId: playerId,
    eventoTipo: "cartaDestruida",
    // "derrotado em combate" cobre tanto morrer atacando (dano refletido)
    // quanto defendendo — o que distingue os dois é de QUEM é a vez: Fase de
    // Combate só acontece no turno de quem ataca, então se ainda é a vez do
    // dono de Cu Chulainn, foi ELE quem atacou (e morreu por reflexão).
    condicao: (evento) => evento.carta === carta && evento.motivo === "derrotado em combate" && game.jogadorDaVez === playerId,
    efeito: () => {
      const oponente = TCG.oponenteDe(game, playerId);
      TCG.destruir(game, TCG.combatenteAtivo(game, oponente), "Fúria Final");
    },
  });
});

reg("Merlin", (game, playerId) => {
  const topo = TCG.Deck.topo(game.baralhos[playerId], 3);
  game.bus.emit("topoRevelado", { playerId, cartas: topo });
});

// ---- Monstros -----------------------------------------------------------

reg("Cthulhu", (game, playerId) => TCG.descartarAleatorias(game, TCG.oponenteDe(game, playerId), 2));

reg("Fenrir", (game, playerId) => TCG.destruir(game, TCG.dominioAtivo(game, TCG.oponenteDe(game, playerId)), "Devorar"));

// "Causa 3 de dano POR TURNO ao alvo atingido" — não é um dano único; morde
// logo na ativação e registra um gatilho no PRÓPRIO alvo (não em Jörmungandr)
// que continua mordendo a cada início de turno do controlador do alvo, até
// o alvo morrer (o destroyCard dele mesmo limpa o gatilho — a sobrevida de
// Jörmungandr não importa pro veneno continuar).
reg("Jörmungandr", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, TCG.oponenteDe(game, playerId));
  if (!alvo) return;
  TCG.danoCombatente(game, alvo, 3, "Veneno");
  if (alvo.atualRes <= 0) return; // ja morreu com a mordida inicial, sem gatilho pra registrar
  const donoDoAlvo = TCG.dono(game, alvo);
  TCG.registrarTrigger(game, {
    origemCarta: alvo,
    ownerPlayerId: playerId,
    eventoTipo: "turnoIniciado",
    condicao: (evento) => evento.playerId === donoDoAlvo,
    efeito: () => TCG.danoCombatente(game, alvo, 3, "Veneno"),
  });
});

reg("Tífon", (game, playerId) => {
  const oponente = TCG.oponenteDe(game, playerId);
  TCG.retornarAoPanteao(game, oponente, TCG.combatenteAtivo(game, oponente));
});

reg("Shoggoth", (game, playerId, carta) => { carta.ignoraFraquezaElemental = true; });

reg("Surtur", (game) => {
  for (const pid of game.jogadores) TCG.danoCombatente(game, TCG.combatenteAtivo(game, pid), 10, "Ragnarok");
});

reg("Wendigo", (game, playerId) => {
  const oponente = TCG.oponenteDe(game, playerId);
  TCG.ganharMana(game, playerId, TCG.perderMana(game, oponente, 2));
});

reg("Nyarlathotep", (game, playerId) => {
  // "Olhe... e desarme uma" — quem ativa a habilidade ve as Maldições
  // reveladas e ESCOLHE qual desarmar, isso e uma decisao de verdade.
  const oponente = TCG.oponenteDe(game, playerId);
  const setadas = game.board[oponente].magia.filter((c) => c && c.faceDown);
  if (!setadas.length) return;
  game.bus.emit("topoRevelado", { playerId, cartas: setadas });
  game.selection.solicitar(
    playerId, "Caos: escolha 1 Maldição virada para baixo do oponente para desarmar",
    setadas,
    (escolha) => TCG.destruir(game, escolha[0], "Caos")
  );
});

reg("Minotauro", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, TCG.oponenteDe(game, playerId));
  if (alvo) alvo.habilidadeUsadaNesteTurno = true; // simplificado: bloqueia so o turno corrente
});

reg("Quimera", (game, playerId, carta) => {
  const alvo = TCG.combatenteAtivo(game, TCG.oponenteDe(game, playerId));
  if (alvo && TCG.elementoEfetivo(alvo) === "Terra") TCG.buff(game, carta, "pow", 2, "NESTE_TURNO", "Três Cabeças");
});

// ---- Domínios ----------------------------------------------------------
//
// Todos os 10 Domínios têm efeito PASSIVO ("enquanto ativo...") e/ou um
// GATILHO ("Quando"/"Sempre que"/"No início do turno") — ver triggers.js.
// Passivos são reaplicados do zero a cada Fase Tática (regPassivo) e somem
// quando o Domínio é destruído; gatilhos ficam registrados esperando o
// evento certo, e também são removidos automaticamente na destruição
// (TCG.destroyCard chama TCG.removerPassivosDe/removerTriggersDe).

regPassivo("Trono de Camelot", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (alvo && alvo.tipo === "Herói") TCG.buff(game, alvo, "pow", 3, "PERMANENTE", "Trono de Camelot");
});
regDestroy("Trono de Camelot", (game, playerId) => TCG.comprar(game, playerId, 1));

reg("Fenda de R'lyeh", (game, playerId, carta) => {
  const aplicar = (g, pid) => {
    const alvo = TCG.combatenteAtivo(g, pid);
    if (alvo && alvo.tipo === "Monstro") TCG.buff(g, alvo, "res", 4, "PERMANENTE", "Fenda de R'lyeh");
  };
  TCG.registrarPassivo(game, playerId, carta, aplicar);
  aplicar(game, playerId);
  // "No início do turno, ambos descartam 1 carta" — os dois jogadores, todo turno.
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "turnoIniciado",
    efeito: () => { for (const pid of game.jogadores) TCG.descartarAleatorias(game, pid, 1); },
  });
});

regPassivo("Vulcão Primordial", (game) => {
  for (const pid of game.jogadores) {
    const alvo = TCG.combatenteAtivo(game, pid);
    if (!alvo) continue;
    const elem = TCG.elementoEfetivo(alvo);
    if (elem === "Fogo") TCG.buff(game, alvo, "pow", 3, "PERMANENTE", "Vulcão Primordial");
    else if (elem === "Vento") TCG.buff(game, alvo, "res", -2, "PERMANENTE", "Vulcão Primordial");
  }
});

// "Sempre que um combatente de Água usar uma Habilidade de Mana, o
// feiticeiro recupera 1 de Mana" — gatilho puro, sem parte passiva.
reg("Templo de Atlântida", (game, playerId, carta) => {
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "habilidadeAtivada",
    condicao: (evento) => TCG.elementoEfetivo(evento.carta) === "Água",
    efeito: (evento) => TCG.ganharMana(game, evento.playerId, 1),
  });
});

// "Combatentes de Vento podem retornar ao Panteão logo após atacar,
// evitando contra-ataques" — sem contra-ataque modelado, vira determinístico:
// todo combatente de Vento que sobrevive ao próprio ataque volta sozinho.
reg("Cânion dos Ventos", (game, playerId, carta) => {
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "ataqueResolvido",
    condicao: (evento) => TCG.elementoEfetivo(evento.atacante) === "Vento"
      && game.board[evento.atacantePlayer].monstro === evento.atacante,
    efeito: (evento) => TCG.retornarAoPanteao(game, evento.atacantePlayer, evento.atacante),
  });
});

// "Todo dano recebido por combatentes de Terra é reduzido em 3" (passivo,
// checado dentro de TCG.danoCombatente) + "Se um for derrotado, o feiticeiro
// [dono do Domínio] ganha 4 de Mana" (gatilho).
reg("Jardins Suspensos", (game, playerId, carta) => {
  const aplicar = (g) => { g.reducaoDanoTerra = 3; };
  const limpar = (g) => { delete g.reducaoDanoTerra; };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar(game);
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "cartaDestruida",
    condicao: (evento) => evento.carta.combate !== null && TCG.elementoEfetivo(evento.carta) === "Terra",
    efeito: () => TCG.ganharMana(game, playerId, 4),
  });
});

// "Quando um Espírito Heróico for derrotado, em vez de ir para a Pilha de
// Descarte, ele retorna para o Panteão" — intercepta o destino no evento
// PRÉ-destruição (ver TCG.destroyCard), sem precisar de caso especial lá.
reg("Valhalla", (game, playerId, carta) => {
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "cartaSeraDestruida",
    condicao: (evento) => evento.carta.tipo === "Herói",
    efeito: (evento) => { evento.contexto.destino = "panteao"; },
  });
});

// "Todo Monstro em campo ganha +3 de Combate" (passivo) + "Nenhuma carta
// pode ser retirada ou revivida da Pilha de Descarte" (flag global, checada
// em Ressurreição Arcana e Chamado do Além — os únicos 2 efeitos que
// tiram carta do descarte).
reg("Fosso de Tártaro", (game, playerId, carta) => {
  const aplicar = (g, pid) => {
    const alvo = TCG.combatenteAtivo(g, pid);
    if (alvo && alvo.tipo === "Monstro") TCG.buff(g, alvo, "pow", 3, "PERMANENTE", "Fosso de Tártaro");
    g.bloqueiaRessureicao = true;
  };
  const limpar = (g, c) => { TCG.limparStatusPorOrigem(g, c.nome); delete g.bloqueiaRessureicao; };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar(game, playerId);
});

// "No início do turno, revela a carta do topo do Baralho. Se for de Água ou
// Encantamento, compra de graça." — gatilho recorrente, sem parte passiva.
reg("Oceano Primordial", (game, playerId, carta) => {
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "turnoIniciado",
    efeito: (evento) => {
      const pid = evento.playerId;
      const baralho = game.baralhos[pid];
      const topo = TCG.Deck.topo(baralho, 1)[0];
      if (!topo) return;
      game.bus.emit("topoRevelado", { playerId: pid, cartas: [topo] });
      if ((topo.elemento === "Água" || topo.tipo === "Encantamento") && game.players[pid].mao.length < TCG.LIMITE_MAO) {
        TCG.Deck.tirarEspecifica(baralho, topo);
        game.players[pid].mao.push(topo);
        game.bus.emit("cartaComprada", { playerId: pid, carta: topo, origem: "efeito" });
      }
    },
  });
});

// "Heróis de Fogo/Vento ignoram desvantagem elemental" (passivo, reaproveita
// a flag `ignoraFraquezaElemental` que Shoggoth já usa) + "Sempre que
// atacam, oponente descarta o topo do baralho" (gatilho — mill, não compra).
reg("Céus de Valíria", (game, playerId, carta) => {
  const elegivel = (c) => c && c.tipo === "Herói" && ["Fogo", "Vento"].includes(TCG.elementoEfetivo(c));
  const aplicar = (g) => {
    for (const pid of g.jogadores) {
      const alvo = TCG.combatenteAtivo(g, pid);
      if (elegivel(alvo)) alvo.ignoraFraquezaElemental = true;
    }
  };
  const limpar = (g) => {
    for (const pid of g.jogadores) {
      const alvo = TCG.combatenteAtivo(g, pid);
      if (alvo) alvo.ignoraFraquezaElemental = false;
    }
  };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar(game);
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    eventoTipo: "ataqueDeclarado",
    condicao: (evento) => elegivel(evento.atacante),
    efeito: (evento) => {
      const oponente = TCG.oponenteDe(game, evento.atacantePlayer);
      const baralho = game.baralhos[oponente];
      const topo = TCG.Deck.topo(baralho, 1)[0];
      if (!topo) return;
      TCG.Deck.tirarEspecifica(baralho, topo);
      game.descarte[oponente].push(topo);
      game.bus.emit("cartaDescartada", { playerId: oponente, carta: topo });
    },
  });
});

// ---- Encantamentos -----------------------------------------------------------

reg("Tomo do Oráculo", (game, playerId) => TCG.comprar(game, playerId, 2));

reg("Pacto de Sangue", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (!alvo) return;
  alvo.atualRes = Math.max(alvo.atualRes - 5, 0);
  TCG.buff(game, alvo, "pow", 6, "ATE_FIM_DE_TURNO", "Pacto de Sangue");
});

reg("Visão do Olho Que Tudo Vê", (game, playerId) => {
  // "O oponente deve revelar sua mão. Escolha uma carta..." — quem ativa
  // a habilidade e que escolhe, depois de ver a mao revelada.
  const oponente = TCG.oponenteDe(game, playerId);
  const ps = game.players[oponente];
  const candidatas = ps.mao.filter((c) => c.tipo === "Maldição" || c.tipo === "Encantamento");
  if (!candidatas.length) return;
  game.selection.solicitar(
    playerId, "Visão do Olho Que Tudo Vê: escolha 1 carta da mão revelada do oponente para descartar",
    candidatas,
    (escolha) => {
      const escolhida = escolha[0];
      ps.mao.splice(ps.mao.indexOf(escolhida), 1);
      game.descarte[oponente].push(escolhida);
      game.bus.emit("cartaDescartada", { playerId: oponente, carta: escolhida });
    }
  );
});

reg("Ressurreição Arcana", (game, playerId) => {
  if (game.bloqueiaRessureicao) return; // Fosso de Tártaro: nada sai do descarte enquanto ativo
  // "Escolha qualquer carta..." e uma escolha de verdade -> mecanismo de selecao.
  const descarte = game.descarte[playerId];
  if (!descarte.length) return;
  game.selection.solicitar(
    playerId, "Ressurreição Arcana: escolha 1 carta da Pilha de Descarte para sua mão",
    descarte.slice(),
    (escolha) => {
      const escolhida = escolha[0];
      descarte.splice(descarte.indexOf(escolhida), 1);
      game.players[playerId].mao.push(escolhida);
    }
  );
});

reg("Transmutação Elemental", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (!alvo) return;
  const elementos = ["Fogo", "Água", "Terra", "Vento"];
  alvo.elementoOverride = { elemento: game.rng.choice(elementos), duracao: "ATE_PROXIMO_TURNO_PROPRIO" };
});

reg("Desintegração de Realidade", (game, playerId) => {
  TCG.destruir(game, TCG.dominioAtivo(game, TCG.oponenteDe(game, playerId)), "Desintegração de Realidade");
});

reg("Vórtice Dimensional", (game, playerId) => {
  const oponente = TCG.oponenteDe(game, playerId);
  TCG.retornarAoPanteao(game, oponente, TCG.combatenteAtivo(game, oponente));
});

reg("Clarividência Divina", (game, playerId) => {
  // "Descarte 1 e devolva as outras 2" — quem olha e que escolhe qual das
  // 3 descarta.
  const oponente = TCG.oponenteDe(game, playerId);
  const topo = TCG.Deck.topo(game.baralhos[oponente], 3);
  if (!topo.length) return;
  game.bus.emit("topoRevelado", { playerId, cartas: topo });
  game.selection.solicitar(
    playerId, "Clarividência Divina: escolha 1 das 3 cartas do topo do baralho inimigo para descartar",
    topo,
    (escolha) => {
      const escolhida = escolha[0];
      TCG.Deck.tirarEspecifica(game.baralhos[oponente], escolhida);
      game.descarte[oponente].push(escolhida);
      game.bus.emit("cartaDescartada", { playerId: oponente, carta: escolhida });
    }
  );
});

reg("Bênção de Yggdrasil", (game, playerId) => {
  TCG.comprar(game, playerId, 2);
  if (game.players[playerId].mao.length <= 1) TCG.comprar(game, playerId, 1);
});

reg("Fúria Titânica", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (!alvo) return;
  TCG.buff(game, alvo, "pow", 8, "NESTE_TURNO", "Fúria Titânica");
  TCG.buff(game, alvo, "res", -4, "PERMANENTE", "Fúria Titânica");
});

reg("Troca Equivalente", (game, playerId) => {
  const ps = game.players[playerId];
  const devolver = game.rng.sample(ps.mao, Math.min(3, ps.mao.length));
  for (const c of devolver) ps.mao.splice(ps.mao.indexOf(c), 1);
  const baralho = game.baralhos[playerId];
  for (const c of devolver) TCG.Deck.adicionar(baralho, c);
  TCG.Deck.embaralhar(baralho, game.rng);
  game.bus.emit("deckEmbaralhado", { deckNome: baralho.nome });
  TCG.comprar(game, playerId, devolver.length);
});

reg("Exílio Dimensional", (game, playerId) => {
  const oponente = TCG.oponenteDe(game, playerId);
  TCG.destruir(game, TCG.combatenteAtivo(game, oponente), "Exílio Dimensional");
  // "invoca outro de graça" exige escolha do oponente -> fica pra IA/UI decidir summon gratis em seguida (nao automatizado aqui).
});

reg("Chamado do Além", (game, playerId) => {
  if (game.bloqueiaRessureicao) return; // Fosso de Tártaro: nada sai do descarte enquanto ativo
  // "Escolha uma carta de Maldição/Equipamento da Pilha de Descarte" — escolha
  // de verdade. Simplificado (como ja era): volta pra mao em vez de campo
  // direto, mas agora setar uma Maldição já é grátis, então o efeito prático
  // é quase o mesmo.
  const descarte = game.descarte[playerId];
  const candidatas = descarte.filter((c) => c.tipo === "Maldição");
  if (!candidatas.length) return;
  game.selection.solicitar(
    playerId, "Chamado do Além: escolha 1 Maldição da Pilha de Descarte para sua mão",
    candidatas,
    (escolha) => {
      const escolhida = escolha[0];
      descarte.splice(descarte.indexOf(escolhida), 1);
      game.players[playerId].mao.push(escolhida);
    }
  );
});

reg("Purificação Arcana", (game, playerId) => {
  // "Destrua duas delas" — duas escolhas de verdade, uma de cada vez (assim
  // reaproveita o mesmo modal de selecao unica, sem precisar de UI de
  // multi-selecao: escolhe uma, ve destruida, escolhe a proxima).
  const oponente = TCG.oponenteDe(game, playerId);
  function pedirUma(restantes) {
    if (restantes <= 0) return;
    const maldicoes = game.board[oponente].magia.filter((c) => c && c.faceDown);
    if (!maldicoes.length) return;
    game.selection.solicitar(
      playerId, `Purificação Arcana: escolha uma Maldição do oponente para destruir (restam ${restantes})`,
      maldicoes,
      (escolha) => {
        TCG.destruir(game, escolha[0], "Purificação Arcana");
        pedirUma(restantes - 1);
      }
    );
  }
  pedirUma(2);
});

reg("Manto da Natureza", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (alvo) TCG.buff(game, alvo, "res", 5, "PERMANENTE", "Manto da Natureza");
});

// ---- Maldições -----------------------------------------------------------
//
// GAME_DESIGN.md: "Revelar/ativar uma Maldição já setada: a qualquer momento
// no turno do OPONENTE." O jogo nunca revela uma Maldição sozinho: sempre que
// um evento bate com o gatilho declarado (regGatilhoMaldicao) de alguma
// Maldição virada pra baixo de quem NÃO está na vez, um modal pergunta pro
// dono se quer ativá-la agora (TCG.ofertarMaldicoesReativas, curses.js) — o
// jogo PARA até essa decisão (mesmo mecanismo de seleção que já existia só
// pro ataque). O efeito roda na hora da decisão, com o `evento` que motivou
// a oferta ainda disponível como 4º argumento — por isso lê o alvo direto
// dele quando o texto pede algo específico (ex.: "o combatente INVOCADO"),
// com fallback pro combatente ativo/mão atual pra continuar funcionando se
// a carta for revelada manualmente (clique direto no próprio verso em campo,
// fora de um evento — ver ui.js) sem um evento associado.

reg("Escudo de Gelo Absoluto", (game, playerId, carta, evento) => {
  // "O ataque e negado" protege quem ATIVOU a Maldição (é quem está sendo
  // atacado quando isso dispara) — negarProximoAtaque tem que ir no PRÓPRIO
  // combatente do ativador, não no do oponente. "o combatente inimigo perde
  // seu elemento" é que mira o oponente.
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const proprio = (evento && evento.defensor) || TCG.combatenteAtivo(game, playerId);
  if (proprio) TCG.negarProximoAtaque(game, proprio);
  const inimigo = (evento && evento.atacante) || TCG.combatenteAtivo(game, oponente);
  if (inimigo) inimigo.elementoOverride = { elemento: null, duracao: "ATE_FIM_DE_TURNO" };
});
regGatilhoMaldicao("Escudo de Gelo Absoluto", "ataqueDeclarado", (evento, game, donoId) => evento.defensorPlayer === donoId);

reg("Espelho das Ilusões", (game, playerId, carta, evento) => {
  if (TCG.protegidoContraMaldicao(game, TCG.oponenteDe(game, playerId))) return;
  const alvo = (evento && evento.defensor) || TCG.combatenteAtivo(game, playerId);
  if (alvo) TCG.refletirDano(game, alvo);
});
regGatilhoMaldicao("Espelho das Ilusões", "ataqueDeclarado", (evento, game, donoId) => evento.defensorPlayer === donoId);

reg("Areias Movediças", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const alvo = (evento && evento.carta) || TCG.combatenteAtivo(game, oponente);
  if (alvo) TCG.buff(game, alvo, "res", -5, "PERMANENTE", "Areias Movediças");
});
regGatilhoMaldicao("Areias Movediças", "combatenteInvocado", (evento, game, donoId) => evento.playerId !== donoId);

reg("Roubo de Essência", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  // simplificado (como já era): não cancela de fato o efeito da Habilidade
  // ativada (não há uma noção separada de "Habilidade de Mana" nos dados),
  // só rouba a Mana que ela custou.
  const custo = evento && evento.carta ? evento.carta.custoHabilidade : 99;
  TCG.ganharMana(game, playerId, TCG.perderMana(game, oponente, custo));
});
regGatilhoMaldicao("Roubo de Essência", "habilidadeAtivada", (evento, game, donoId) => evento.playerId !== donoId);

reg("Praga da Ferrugem", (game, playerId) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  TCG.perderMana(game, oponente, 1);
});
// sem gatilho declarado: depende de "Equipamento", que não existe nos dados
// desta versão — não é oferecida no modal reativo, só pode ser descartada
// por outro efeito (ex.: Purificação Arcana) nesta versão.

reg("Vínculo Sombrio", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const alvo = (evento && evento.atacante) || TCG.combatenteAtivo(game, oponente);
  if (alvo) TCG.buff(game, alvo, "pow", 10 - alvo.atualPow, "ATE_FIM_DE_TURNO", "Vínculo Sombrio");
});
regGatilhoMaldicao("Vínculo Sombrio", "ataqueDeclarado", (evento, game, donoId) => evento.defensorPlayer === donoId);

reg("Nevoeiro do Pânico", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const ps = game.players[oponente];
  const cartaComprada = evento && evento.carta;
  if (cartaComprada && ps.mao.includes(cartaComprada)) {
    ps.mao.splice(ps.mao.indexOf(cartaComprada), 1);
    game.descarte[oponente].push(cartaComprada);
    game.bus.emit("cartaDescartada", { playerId: oponente, carta: cartaComprada });
  } else {
    TCG.descartarAleatorias(game, oponente, 1); // fallback p/ revelação manual sem evento associado
  }
  const baralho = game.baralhos[oponente];
  const restantes = TCG.Deck.restantes(baralho);
  if (!restantes.length) return;
  const doFundo = restantes[restantes.length - 1];
  TCG.Deck.tirarEspecifica(baralho, doFundo);
  ps.mao.push(doFundo);
  game.bus.emit("cartaComprada", { playerId: oponente, carta: doFundo, origem: "efeito" });
});
// "a carta recém comprada NO TURNO" = a compra automática da Fase de Recurso
// (origem "turno" — ver TCG.comprar), não uma compra de efeito.
regGatilhoMaldicao("Nevoeiro do Pânico", "cartaComprada", (evento, game, donoId) => evento.playerId !== donoId && evento.origem === "turno");

reg("Barreira de Vento Cortante", (game, playerId, carta, evento) => {
  // "O ataque e negado" protege o PRÓPRIO combatente de quem ativou a
  // Maldição; "o atacante retorna ao Panteão" manda o combatente do
  // OPONENTE de volta.
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const proprio = (evento && evento.defensor) || TCG.combatenteAtivo(game, playerId);
  if (proprio) TCG.negarProximoAtaque(game, proprio);
  const inimigo = (evento && evento.atacante) || TCG.combatenteAtivo(game, oponente);
  TCG.retornarAoPanteao(game, oponente, inimigo);
});
regGatilhoMaldicao("Barreira de Vento Cortante", "ataqueDeclarado", (evento, game, donoId) => evento.defensorPlayer === donoId);

reg("Retribuição Kármica", (game, playerId, carta, evento) => {
  if (TCG.protegidoContraMaldicao(game, TCG.oponenteDe(game, playerId))) return;
  const alvo = (evento && evento.defensor) || TCG.combatenteAtivo(game, playerId);
  if (alvo) TCG.refletirDano(game, alvo);
});
regGatilhoMaldicao("Retribuição Kármica", "ataqueDeclarado", (evento, game, donoId) => evento.defensorPlayer === donoId);

reg("Aperto da Múmia", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const alvo = (evento && evento.carta) || TCG.combatenteAtivo(game, oponente);
  if (alvo) {
    TCG.buff(game, alvo, "res", -5, "PERMANENTE", "Aperto da Múmia");
    TCG.buff(game, alvo, "pow", -3, "PERMANENTE", "Aperto da Múmia");
  }
});
regGatilhoMaldicao("Aperto da Múmia", "combatenteInvocado", (evento, game, donoId) => evento.playerId !== donoId);

reg("Mente Fraturada", (game, playerId) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const ps = game.players[oponente];
  if (!ps.mao.length) return;
  const pior = ps.mao.reduce((a, b) => (b.custoMana > a.custoMana ? b : a));
  ps.mao.splice(ps.mao.indexOf(pior), 1);
  game.descarte[oponente].push(pior);
  game.bus.emit("cartaDescartada", { playerId: oponente, carta: pior });
});
// "ao tentar comprar cartas EXTRAS" = origem "efeito" (Tomo do Oráculo,
// Bênção de Yggdrasil...), não a compra normal de início de turno.
regGatilhoMaldicao("Mente Fraturada", "cartaComprada", (evento, game, donoId) => evento.playerId !== donoId && evento.origem === "efeito");

reg("Amnésia Mágica", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  // "a Habilidade de Mana falha e o combatente perde o direito de usar
  // habilidades" — simplificado (como já era) pra "essa ativação já era" +
  // bloqueia o resto do turno.
  const alvo = (evento && evento.carta) || TCG.combatenteAtivo(game, oponente);
  if (alvo) alvo.habilidadeUsadaNesteTurno = true;
});
regGatilhoMaldicao("Amnésia Mágica", "habilidadeAtivada", (evento, game, donoId) => evento.playerId !== donoId);

reg("Fio do Destino Cortado", (game, playerId, carta, evento) => {
  const oponente = TCG.oponenteDe(game, playerId);
  if (TCG.protegidoContraMaldicao(game, oponente)) return;
  const alvo = (evento && evento.carta) || TCG.combatenteAtivo(game, oponente);
  if (alvo) {
    for (const st of alvo.statusEffects) st.magnitude = -st.magnitude;
    TCG.recalcularStats(alvo);
  }
});
// aproximação de "buff ativado": a maioria dos buffs vem de Habilidade.
regGatilhoMaldicao("Fio do Destino Cortado", "habilidadeAtivada", (evento, game, donoId) => evento.playerId !== donoId);

reg("Rebote Arcano", () => {}); // exige rastrear "o proximo feitico inimigo" — nao modelado nesta versao

reg("Caixa de Pandora", (game, playerId, carta, evento) => {
  // diferente das outras Maldições reativas, não faz sentido nenhum "efeito
  // de fallback" pra Caixa de Pandora sem o evento de destruição que a
  // motivou — sem ele, revelar a carta (fora do modal reativo) não faz nada.
  if (!evento) return;
  TCG.descartarAleatorias(game, TCG.oponenteDe(game, playerId), 3);
});
// "Ao ter Domínio/Combatente destruído" = quando uma carta DO DONO da Caixa
// de Pandora (não ela mesma) morre — fix de um gatilho errado que existia
// antes desta refatoração (disparava quando a PRÓPRIA Caixa de Pandora era
// destruída, condição diferente da do texto).
regGatilhoMaldicao("Caixa de Pandora", "cartaDestruida", (evento, game, donoId) =>
  evento.playerId === donoId && (evento.carta.tipo === "Domínio" || evento.carta.combate !== null));

// "Apoio Incondicional" fica sem entrada de proposito — cai no fallback de executarEfeito.
