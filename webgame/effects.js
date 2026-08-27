// Efeitos de carta: as ~70 cartas cobertas em game/effects.py, traduzidas 1:1,
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
  // Domínio passivo piscaria a cada Fase Principal, mesmo sem nada mudar.
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
  const alvoRes = Math.max(carta.atualRes, Math.min(carta.atualRes + quantidade, carta.resistencia));
  // traduz em reduzir danoAcumulado (não mutar atualRes direto) — é o que
  // sobrevive a um recálculo futuro por outro motivo (ver TCG.recalcularStats).
  carta.danoAcumulado = Math.max(carta.danoAcumulado - (alvoRes - antes), 0);
  TCG.recalcularStats(carta);
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
  // danoAcumulado (não mutar atualRes direto): sobrevive a qualquer
  // recálculo futuro por outro motivo — bug real que isso corrige: um buff
  // não relacionado nessa mesma carta, depois, silenciosamente "curava"
  // esse dano (ver TCG.recalcularStats).
  carta.danoAcumulado += quantidade;
  TCG.recalcularStats(carta);
  game.bus.emit("danoCausado", { alvo: carta, alvoPlayer: null, quantidade, origem });
  if (carta.atualRes <= 0) TCG.destroyCard(game, carta, origem || "destruido por efeito");
};

TCG.danoJogador = function danoJogador(game, playerId, quantidade, origem = "") {
  const ps = game.players[playerId];
  ps.vida = Math.max(ps.vida - quantidade, 0);
  // danoCausado ANTES de vidaAlterada — mesma razao do TCG.resolverAtaque em
  // engine.js: e o que deixa o listener de FX (ui.js) deduplicar o numero
  // flutuante em vez de mostrar os dois.
  game.bus.emit("danoCausado", { alvo: null, alvoPlayer: playerId, quantidade, origem });
  game.bus.emit("vidaAlterada", { playerId, delta: -quantidade, total: ps.vida });
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
  // Volta como copia "intocada": sem dano/buffs acumulados nem gatilhos
  // pendurados na carta — igual a qualquer outro Combatente esperando no
  // Panteão pra ser invocado (convenção padrão de TCG: sair de campo
  // "reseta" o objeto; sem isso, ex.: o gatilho de Veneno de Jörmungandr
  // continuava mordendo um alvo que nem estava mais em jogo, e uma carta
  // podia voltar pro Panteão carregando dano/buff da vida anterior).
  TCG.removerPassivosDe(game, carta);
  TCG.removerTriggersDe(game, carta);
  carta.statusEffects = [];
  carta.danoAcumulado = 0;
  TCG.recalcularStats(carta);
  carta.attackNegated = false;
  carta.damageReflected = false;
  carta.ignoraFraquezaElemental = false;
  carta.danoDobradoContraMonstro = false;
  carta.imuneAHabilidadesInimigas = false;
  carta.habilidadeUsadaNesteTurno = false;
  carta.atacouNesteTurno = false;
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
// novo a cada Fase Principal (limpa-e-reaplica, ver TCG.aplicarPassivos), até a
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

// "Matador de Feras: Dano em dobro contra Monstros" — a Habilidade só
// PREPARA o buff (NESTE_TURNO); o dano dobrado só sai de verdade se Sigurd
// de fato ATACAR um Monstro antes do fim do turno (TCG.resolverAtaque, em
// engine.js, dobra o dano de combate nessa condição). Sem isso, "Dano em
// dobro" virava um nuke avulso que não exigia ataque nenhum — não bate com
// o texto nem com o resto do vocabulário do jogo (GAME_DESIGN.md separa
// Habilidade de Ataque).
reg("Sigurd", (game, playerId, carta) => {
  carta.danoDobradoContraMonstro = true;
});

reg("Joana d'Arc", (game, playerId, carta) => {
  // "Cura totalmente" = TCG.curar com uma quantidade grande o bastante pra
  // sempre bater no teto (resistencia impressa) — reaproveita a mesma
  // proteção de TCG.curar (nunca reduz um atualRes já acima da base por
  // causa de buff permanente) em vez de duplicar a lógica.
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (alvo) TCG.curar(game, alvo, alvo.resistencia);
});

reg("Gilgamesh", (game, playerId) => TCG.comprar(game, playerId, 1)); // simplificado: sem subtipo "Equipamento" nos dados

// "Ataca duas vezes, mas o dano é reduzido à metade" — dispara DOIS ataques
// DE VERDADE (passam pela fórmula normal de combate em TCG.resolverAtaque:
// diferença de Combate, bônus elemental, Sigurd, Jardins Suspensos,
// reflexão), cada um com o dano final dividido por 2 — não um nuke avulso
// de "metade do Combate atual" direto no alvo, fora da fórmula (mesmo
// raciocínio da correção de Sigurd). Conta como o ataque do turno: depois
// de ativar, não dá pra declarar um ataque normal de novo. Não passa por
// TCG.ofertarMaldicoesReativas (as Maldições reativas a "ataque declarado",
// tipo Escudo de Gelo Absoluto, não são oferecidas aqui) — escopo
// deliberadamente menor que um ataque declarado de verdade.
reg("Aquiles", (game, playerId, carta) => {
  const oponente = TCG.oponenteDe(game, playerId);
  for (let i = 0; i < 2; i++) {
    const defensor = TCG.combatenteAtivo(game, oponente);
    TCG.resolverAtaque(game, playerId, carta, oponente, defensor, 0.5);
  }
  carta.atacouNesteTurno = true;
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
  // A vingança só protege ATÉ O FIM DO TURNO em que a Habilidade foi
  // ativada — mesmo padrão de duração das outras Habilidades de combatente
  // (Rei Arthur, Sigurd, Quimera: todas NESTE_TURNO). Sem isso, o gatilho
  // ficava armado PRA SEMPRE (só sumia se Cu Chulainn morresse) — pagar o
  // custo de Habilidade de novo em turnos seguintes nunca fazia diferença
  // nenhuma, já que a vingança já estava permanentemente armada.
  TCG.registrarTrigger(game, {
    origemCarta: carta,
    ownerPlayerId: playerId,
    eventoTipo: "faseAlterada",
    persistente: false,
    condicao: (evento) => evento.faseNova === "FINAL" && evento.playerId === playerId,
    efeito: () => TCG.removerTriggersDe(game, carta),
  });
});

reg("Merlin", (game, playerId) => {
  const topo = TCG.Deck.topo(game.baralhos[playerId], 3);
  game.bus.emit("topoRevelado", { playerId, cartas: topo });
});

// ---- Monstros -----------------------------------------------------------

reg("Cthulhu", (game, playerId) => TCG.descartarAleatorias(game, TCG.oponenteDe(game, playerId), 2));

// "Destrói a carta de Domínio ativa no campo" — sem qualificar dono. Como só
// existe 1 Domínio ativo NO JOGO INTEIRO (compartilhado, fica no slot de
// magia de quem o jogou por último — ver TCG.dominioParaFundo), mira esse
// Domínio único, mesmo que tenha sido o próprio controlador de Fenrir quem
// o ativou — checar só o lado do oponente deixava a Habilidade sem alvo
// válido nesse caso, apesar de haver um Domínio bem "ativo no campo".
reg("Fenrir", (game) => {
  const fundo = TCG.dominioParaFundo(game);
  if (fundo) TCG.destruir(game, fundo.carta, "Devorar");
});

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
  if (alvo && alvo.imuneAHabilidadesInimigas) return; // Manto da Natureza
  if (alvo) alvo.habilidadeUsadaNesteTurno = true; // simplificado: bloqueia so o turno corrente
});

reg("Quimera", (game, playerId, carta) => {
  const alvo = TCG.combatenteAtivo(game, TCG.oponenteDe(game, playerId));
  if (alvo && TCG.elementoEfetivo(alvo) === "Terra") TCG.buff(game, carta, "pow", 2, "NESTE_TURNO", "Três Cabeças");
});

// ---- Combatentes de Suporte (GAME_DESIGN.md, "Diretrizes de Design de
// Combatentes") ----------------------------------------------------------
//
// Faixa de POW até 14: baratos, focados em busca de carta e farm de Mana
// pra abrir caminho pro combatente Poderoso — não em brigar (por isso a
// Habilidade de cada um é só um dos dois primitivos de sempre, comprar/
// ganharMana, sem nenhum efeito de combate). As 3 Habilidades de +Mana
// (Gnomos das Minas, Soldados de Camelot, Zumbis Errantes) têm um
// drawback além do Custo de Habilidade — ver drawbackCartaOuMaldicao.

// Drawback de mana: o jogador ESCOLHE entre descartar 1 carta da mão ou
// destruir 1 Maldição virada para baixo sua (nunca do oponente — preço
// pago com o próprio recurso, mesmo espírito do sacrifício dos
// Encantamentos Contínuos). As duas opções entram no mesmo pedido de
// seleção — mão + Maldições setadas do próprio jogador — porque ambas são
// só "escolha 1 carta", diferindo apenas em pra onde ela vai depois. Sem
// opção nenhuma disponível (mão vazia e nenhuma Maldição setada), a
// Habilidade segue sem custo — mesma leniência de Pacto de Sangue/Selva
// Amazônica quando falta o alvo do sacrifício.
function drawbackCartaOuMaldicao(game, playerId, nomeCarta) {
  const ps = game.players[playerId];
  const lado = game.board[playerId];
  const maldicoesProprias = lado.magia.filter((c) => c && c.faceDown);
  const opcoes = ps.mao.concat(maldicoesProprias);
  if (!opcoes.length) return;
  game.selection.solicitar(
    playerId, `${nomeCarta}: descarte 1 carta da mão ou destrua 1 Maldição virada para baixo sua`,
    opcoes,
    (escolha) => {
      const escolhida = escolha[0];
      if (ps.mao.includes(escolhida)) {
        ps.mao.splice(ps.mao.indexOf(escolhida), 1);
        game.descarte[playerId].push(escolhida);
        game.bus.emit("cartaDescartada", { playerId, carta: escolhida });
      } else {
        TCG.destruir(game, escolhida, nomeCarta);
      }
    }
  );
}

// ganha 2, Custo de Habilidade é 1 -> +1 de Mana líquido por ativação,
// senão a Habilidade só pagaria a si mesma (sem farm de verdade).
reg("Gnomos das Minas", (game, playerId) => {
  TCG.ganharMana(game, playerId, 2);
  drawbackCartaOuMaldicao(game, playerId, "Gnomos das Minas");
});

reg("Soldados de Camelot", (game, playerId) => { // mesma lógica de Gnomos das Minas acima
  TCG.ganharMana(game, playerId, 2);
  drawbackCartaOuMaldicao(game, playerId, "Soldados de Camelot");
});

reg("Zumbis Errantes", (game, playerId) => { // Custo de Habilidade 2 -> +1 líquido
  TCG.ganharMana(game, playerId, 3);
  drawbackCartaOuMaldicao(game, playerId, "Zumbis Errantes");
});

reg("Fadas do Bosque", (game, playerId) => TCG.comprar(game, playerId, 1));

reg("Sombras Noturnas", (game, playerId) => TCG.comprar(game, playerId, 1));

reg("Cultistas do Abismo", (game, playerId) => {
  TCG.comprar(game, playerId, 1);
  TCG.danoJogador(game, playerId, 1, "Cultistas do Abismo");
});

// ---- Domínios ----------------------------------------------------------
//
// Todos os 10 Domínios têm efeito PASSIVO ("enquanto ativo...") e/ou um
// GATILHO ("Quando"/"Sempre que"/"No início do turno") — ver triggers.js.
// Passivos são reaplicados do zero a cada Fase Principal (regPassivo) e somem
// quando o Domínio é destruído; gatilhos ficam registrados esperando o
// evento certo, e também são removidos automaticamente na destruição
// (TCG.destroyCard chama TCG.removerPassivosDe/removerTriggersDe).

// "todos os Espíritos Heróicos" — sem qualificar dono, vale pros DOIS
// lados (mesmo padrão de Vulcão Primordial), não só o combatente do
// controlador do Domínio.
regPassivo("Trono de Camelot", (game) => {
  for (const pid of game.jogadores) {
    const alvo = TCG.combatenteAtivo(game, pid);
    if (alvo && alvo.tipo === "Herói") TCG.buff(game, alvo, "pow", 3, "PERMANENTE", "Trono de Camelot");
  }
});
regDestroy("Trono de Camelot", (game, playerId) => TCG.comprar(game, playerId, 1));

reg("Fenda de R'lyeh", (game, playerId, carta) => {
  // "Monstros Primordiais ganham +4 de Resistência" — sem qualificar dono,
  // vale pros DOIS lados, não só o combatente do controlador do Domínio.
  const aplicar = (g) => {
    for (const pid of g.jogadores) {
      const alvo = TCG.combatenteAtivo(g, pid);
      if (alvo && alvo.tipo === "Monstro") TCG.buff(g, alvo, "res", 4, "PERMANENTE", "Fenda de R'lyeh");
    }
  };
  TCG.registrarPassivo(game, playerId, carta, aplicar);
  aplicar(game);
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
  // "Todo Monstro em campo ganha +3 de Combate" — sem qualificar dono, vale
  // pros DOIS lados, não só o combatente do controlador do Domínio.
  const aplicar = (g) => {
    for (const pid of g.jogadores) {
      const alvo = TCG.combatenteAtivo(g, pid);
      if (alvo && alvo.tipo === "Monstro") TCG.buff(g, alvo, "pow", 3, "PERMANENTE", "Fosso de Tártaro");
    }
    g.bloqueiaRessureicao = true;
  };
  const limpar = (g, c) => { TCG.limparStatusPorOrigem(g, c.nome); delete g.bloqueiaRessureicao; };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar(game);
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
  // danoAcumulado (não mutar atualRes direto): sobrevive a qualquer
  // recálculo futuro por outro motivo (ver TCG.recalcularStats).
  alvo.danoAcumulado += 5;
  TCG.recalcularStats(alvo);
  // Resistência chegando a 0 destrói o combatente, igual a QUALQUER outra
  // fonte de dano (TCG.resolverAtaque, danoCombatente) — o sacrifício não é
  // isento dessa regra só por vir de um custo pago pelo próprio dono.
  if (alvo.atualRes <= 0) {
    TCG.destroyCard(game, alvo, "sacrificado por Pacto de Sangue");
    return;
  }
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

// "Mude... para QUALQUER OUTRA" — decisão real do jogador (mirar a
// vantagem elemental certa), não sorteio; exclui o elemento atual (não
// seria "outra"). Sem carta pra mostrar nesta escolha — usa a variante de
// "rótulo" de renderOverlaySelecao (ver ui.js).
reg("Transmutação Elemental", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (!alvo) return;
  const atual = TCG.elementoEfetivo(alvo);
  const opcoes = ["Fogo", "Água", "Terra", "Vento"]
    .filter((e) => e !== atual)
    .map((e) => ({ rotulo: e, elemento: e }));
  game.selection.solicitar(
    playerId, "Transmutação Elemental: escolha o novo elemento do seu combatente ativo",
    opcoes,
    (escolha) => {
      alvo.elementoOverride = { elemento: escolha[0].elemento, duracao: "ATE_PROXIMO_TURNO_PROPRIO" };
    }
  );
});

// "a carta de Domínio ativa NA MESA" — sem qualificar dono. Mesmo caso de
// Fenrir: só existe 1 Domínio ativo NO JOGO INTEIRO (compartilhado), então
// mira esse Domínio único, mesmo que esteja do lado do próprio ativador
// (checar só o lado do oponente deixava a carta sem alvo válido nesse
// caso). "...ou um Equipamento ligado a um combatente inimigo" não é
// modelado (sem subtipo Equipamento nos dados).
reg("Desintegração de Realidade", (game) => {
  const fundo = TCG.dominioParaFundo(game);
  if (fundo) TCG.destruir(game, fundo.carta, "Desintegração de Realidade");
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

// "Fim do turno sofre debuff permanente de -4 de Resistência" — o texto
// separa os dois momentos ("neste turno" vs. "fim do turno"): o debuff só
// bate na Fase Final DAQUELE turno, não na hora de jogar a carta (o
// combatente aproveita o ataque forte sem pagar o preço imediatamente).
// Gatilho amarrado ao próprio alvo: se ele morrer/sair de campo antes da
// Fase Final, o gatilho é removido junto (removerTriggersDe), sem debuff
// pendurado num combatente que já não existe mais.
reg("Fúria Titânica", (game, playerId) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (!alvo) return;
  TCG.buff(game, alvo, "pow", 8, "NESTE_TURNO", "Fúria Titânica");
  TCG.registrarTrigger(game, {
    origemCarta: alvo,
    ownerPlayerId: playerId,
    eventoTipo: "faseAlterada",
    persistente: false,
    condicao: (evento) => evento.faseNova === "FINAL" && evento.playerId === playerId,
    efeito: () => TCG.buff(game, alvo, "res", -4, "PERMANENTE", "Fúria Titânica"),
  });
});

// "Embaralhe ATÉ 3 cartas da mão" — escolha real do jogador (mulligan
// seletivo, pra se livrar de cartas específicas), não sorteio; até 3
// escolhas de 1 em 1 (mesmo padrão de Purificação Arcana), com opção de
// parar antes via "Pular" (minimo=0).
reg("Troca Equivalente", (game, playerId) => {
  const ps = game.players[playerId];
  const escolhidas = [];

  function finalizar() {
    if (!escolhidas.length) return;
    const baralho = game.baralhos[playerId];
    for (const c of escolhidas) TCG.Deck.adicionar(baralho, c);
    TCG.Deck.embaralhar(baralho, game.rng);
    game.bus.emit("deckEmbaralhado", { deckNome: baralho.nome });
    TCG.comprar(game, playerId, escolhidas.length);
  }

  function pedirUma(restantes) {
    if (restantes <= 0 || !ps.mao.length) { finalizar(); return; }
    game.selection.solicitar(
      playerId, `Troca Equivalente: escolha uma carta da mão pra embaralhar de volta (restam até ${restantes}, ou pule)`,
      ps.mao.slice(),
      (escolha) => {
        if (!escolha.length) { finalizar(); return; }
        const escolhida = escolha[0];
        ps.mao.splice(ps.mao.indexOf(escolhida), 1);
        escolhidas.push(escolhida);
        pedirUma(restantes - 1);
      },
      0, 1
    );
  }

  pedirUma(3);
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

// Tipo de Encantamento EQUIPAMENTO (GAME_DESIGN.md): fica em campo
// "vestido" num combatente específico até ELE ser destruído (o branch de
// Encantamento em jogarCartaDeCampo cuida disso, registrando um trigger
// genérico de "cartaDestruida" pro alvo — ver actions.js) ou até o
// próprio Equipamento ser destruído. TCG.registrarPassivo dá o segundo
// caso de graça: seu `limpar` já roda automaticamente quando `carta`
// morre (ver TCG.destroyCard -> TCG.removerPassivosDe). O `aplicar` mira
// sempre NESTE alvo fixo (capturado agora), não "quem estiver ativo" —
// diferente do TCG.limparStatusPorOrigem padrão (que olha só o
// combatente ativo de cada lado), pra sobreviver mesmo que o alvo volte
// ao Panteão sem ser destruído.
reg("Manto da Natureza", (game, playerId, carta) => {
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (!alvo) return;

  const aplicar = () => {
    TCG.buff(game, alvo, "res", 5, "PERMANENTE", "Manto da Natureza");
    // "imunidade a Habilidades de Mana inimigas" — checado por Minotauro,
    // Amnésia Mágica e Roubo de Essência antes de agir.
    alvo.imuneAHabilidadesInimigas = true;
  };
  const limpar = () => {
    const antes = alvo.statusEffects.length;
    alvo.statusEffects = alvo.statusEffects.filter((st) => st.origem !== "Manto da Natureza");
    if (alvo.statusEffects.length !== antes) TCG.recalcularStats(alvo);
    alvo.imuneAHabilidadesInimigas = false;
  };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar();
});

// ---- Encantamentos Contínuos (GAME_DESIGN.md) ----------------------------
//
// Custo de Mana 0 de propósito — o "custo" real é o sacrifício pago no
// próprio efeito (descarte, vida, POW/RES). Diferente de um Encantamento
// Simples/Equipamento, ficam em campo (TCG.acoes.jogarCartaDeCampo checa
// carta.tipoEncantamento === "Contínuo", em actions.js) enquanto o bônus de
// +Mana por turno estiver ativo — mesmo padrão de
// registrarPassivo/limpa-e-reaplica já usado pelos Domínios (Vulcão
// Primordial, Jardins Suspensos...), só que somando num contador por
// JOGADOR (game.bonusManaPorTurno) em vez de um statusEffect por carta.

reg("Oásis do Saara", (game, playerId, carta) => {
  TCG.descartarAleatorias(game, playerId, 1); // sacrifício: descarte 1 carta da mão (se houver)
  const aplicar = () => { game.bonusManaPorTurno[playerId] = (game.bonusManaPorTurno[playerId] || 0) + 1; };
  const limpar = () => { game.bonusManaPorTurno[playerId] = (game.bonusManaPorTurno[playerId] || 0) - 1; };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar();
});

reg("Geleiras do Ártico", (game, playerId, carta) => {
  TCG.danoJogador(game, playerId, 3, "Geleiras do Ártico"); // sacrifício: 3 de vida do próprio dono
  const aplicar = () => { game.bonusManaPorTurno[playerId] = (game.bonusManaPorTurno[playerId] || 0) + 1; };
  const limpar = () => { game.bonusManaPorTurno[playerId] = (game.bonusManaPorTurno[playerId] || 0) - 1; };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar();
});

reg("Selva Amazônica", (game, playerId, carta) => {
  // sacrifício: o próprio combatente em campo perde 2/2 permanentemente
  // (se não houver combatente, o sacrifício simplesmente não se aplica —
  // mesma leniência de Pacto de Sangue).
  const alvo = TCG.combatenteAtivo(game, playerId);
  if (alvo) {
    TCG.buff(game, alvo, "pow", -2, "PERMANENTE", "Selva Amazônica");
    TCG.buff(game, alvo, "res", -2, "PERMANENTE", "Selva Amazônica");
  }
  const aplicar = () => { game.bonusManaPorTurno[playerId] = (game.bonusManaPorTurno[playerId] || 0) + 2; };
  const limpar = () => { game.bonusManaPorTurno[playerId] = (game.bonusManaPorTurno[playerId] || 0) - 2; };
  TCG.registrarPassivo(game, playerId, carta, aplicar, limpar);
  aplicar();
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
  if (evento && evento.carta && evento.carta.imuneAHabilidadesInimigas) return; // Manto da Natureza
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
// "a carta recém comprada NO TURNO" = a compra automática da Fase de Saque
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
  if (alvo && alvo.imuneAHabilidadesInimigas) return; // Manto da Natureza
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
