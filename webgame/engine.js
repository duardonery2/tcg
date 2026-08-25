// Estado do jogo + regras gerais (recurso, combate, destruicao, fase).
// Espelha game/components.py + game/systems.py + game/phases.py + game/loader.py,
// sem ECS generico (objetos simples bastam para uma unica partida numa pagina).
var TCG = window.TCG || (window.TCG = {});

TCG.VANTAGEM_ELEMENTAL = { Água: "Fogo", Fogo: "Vento", Vento: "Terra", Terra: "Água" };
TCG.MANA_INICIAL = 5;
TCG.VIDA_INICIAL = 20;
TCG.MAO_INICIAL = 4;
TCG.MANA_POR_TURNO = 2;
TCG.LIMITE_MAO = 6;
TCG.PANTEAO_TAMANHO = 5;

let _proximoInstanceId = 1;

TCG.criarCardInstance = function criarCardInstance(template) {
  return {
    ...template,
    atualPow: template.combate,
    atualRes: template.resistencia,
    statusEffects: [],
    habilidadeUsadaNesteTurno: false,
    atacouNesteTurno: false,
    faceDown: false,
    elementoOverride: null,
    attackNegated: false,
    damageReflected: false,
    ignoraFraquezaElemental: false,
    danoDobradoContraMonstro: false, // Sigurd (Matador de Feras), NESTE_TURNO
    // dano de combate/efeito já sofrido, que NÃO é um statusEffect (sem
    // duração própria) — ver comentário completo em TCG.recalcularStats.
    danoAcumulado: 0,
    instanceId: _proximoInstanceId++,
  };
};

TCG.recalcularStats = function recalcularStats(carta) {
  if (carta.combate === null) return; // nao-combatente, nada a recalcular
  // SEMPRE a partir da base impressa (carta.combate/resistencia) + soma dos
  // statusEffects ATUAIS — nunca incremental em cima do atualPow/atualRes
  // anterior. Incremental faria qualquer recalculo repetido (2a Habilidade
  // no mesmo combatente, limpar-e-reaplicar de passivo, expirar buff de fim
  // de turno) somar de novo efeitos que já estavam dentro do valor atual,
  // inflando POW/RES a cada chamada e nunca voltando à base quando um
  // StatusEffect é removido. Espelha game/phases.py `_recalcular_stats`.
  let pow = carta.combate;
  let res = carta.resistencia;
  for (const st of carta.statusEffects) {
    if (st.atributo === "pow") pow += st.magnitude;
    else if (st.atributo === "res") res += st.magnitude;
  }
  // O limite de 20 (TETO_ATRIBUTO) e so pro valor BASE impresso na carta —
  // toda alteração de POW/RES no jogo vem de Habilidade, Encantamento ou
  // Maldição, e "só pode ser quebrado por feitiços" (GAME_DESIGN.md) quer
  // dizer exatamente isso: nao ha teto pra valor JA alterado por efeito, so
  // um piso em 0 (nao da pra ficar negativo).
  // danoAcumulado (combate/efeito, NÃO statusEffect) desconta aqui — é o que
  // garante que dano sobrevive a este recálculo sendo repetido por outro
  // motivo (ex.: um buff não relacionado nessa mesma carta) sem "curar"
  // sozinho o dano já sofrido; ver campo no comentário de criarCardInstance.
  carta.atualPow = Math.max(pow, 0);
  carta.atualRes = Math.max(res - carta.danoAcumulado, 0);
};

TCG.elementoEfetivo = function elementoEfetivo(carta) {
  if (carta.elementoOverride) return carta.elementoOverride.elemento;
  return carta.elemento;
};

TCG.combatenteAtivo = function combatenteAtivo(game, playerId) {
  return game.board[playerId].monstro;
};

TCG.dominioAtivo = function dominioAtivo(game, playerId) {
  return TCG.Board.dominioAtivo(game.board[playerId]);
};

// Só pode haver 1 Domínio ativo NO JOGO INTEIRO — "só pode haver um ativo na
// mesa" (GAME_DESIGN.md) é a mesa compartilhada dos dois jogadores, não uma
// por lado; jogar um novo (de qualquer um dos dois) destrói o que já estava
// ativo, seja de quem for (TCG.acoes.jogarCartaDeCampo). A arte dele vira o
// fundo do campo INTEIRO, dos DOIS lados do tabuleiro, porque representa o
// cenário onde a partida acontece, não um efeito pessoal de quem jogou. Os
// dois lados nunca deveriam ter um Domínio próprio ativo ao mesmo tempo por
// causa disso — o fallback abaixo é só uma defesa contra estado inconsistente.
TCG.dominioParaFundo = function dominioParaFundo(game) {
  const d1 = TCG.dominioAtivo(game, 1);
  const d2 = TCG.dominioAtivo(game, 2);
  if (d1 && d2) return game.ultimoDominioAtivadoPor === 2 ? { dono: 2, carta: d2 } : { dono: 1, carta: d1 };
  if (d1) return { dono: 1, carta: d1 };
  if (d2) return { dono: 2, carta: d2 };
  return null;
};

TCG.oponenteDe = function oponenteDe(game, playerId) {
  return game.jogadores.find((p) => p !== playerId);
};

TCG.nomeOuId = function nomeOuId(carta) {
  return carta ? carta.nome : null;
};

// ---- criacao da partida ---------------------------------------------------

function montarJogadorDados(playerId, rng) {
  const combatentesTemplates = CARTAS.filter((c) => c.tipo === "Herói" || c.tipo === "Monstro");
  const apoioTemplates = CARTAS.filter((c) => c.tipo !== "Herói" && c.tipo !== "Monstro");

  const sorteados = rng.sample(combatentesTemplates, TCG.PANTEAO_TAMANHO);
  const panteaoInstancias = sorteados.map(TCG.criarCardInstance);
  const baralhoInstancias = apoioTemplates.map(TCG.criarCardInstance);

  return { panteaoInstancias, baralhoInstancias };
}

TCG.criarJogo = function criarJogo({ seed = null, nomes = { 1: "Você", 2: "Oponente" } } = {}) {
  const rng = TCG.criarRng(seed);
  const bus = new TCG.EventBus();
  const jogadores = [1, 2];

  const game = {
    seed: rng.seed,
    rng,
    bus,
    selection: TCG.criarSelectionManager(bus),
    jogadores,
    turno: 1,
    jogadorDaVez: 1,
    fase: "SAQUE",
    players: {},
    panteoes: {},
    baralhos: {},
    board: {},
    descarte: { 1: [], 2: [] },
    fimDeJogo: null,
    _iniciado: false,
    _habilidadeUsadaPendenteReset: true,
    // qual jogador ativou por último um Domínio — usado só pra desempate
    // visual quando os DOIS lados têm Domínio ativo ao mesmo tempo (raro);
    // ver TCG.dominioParaFundo.
    ultimoDominioAtivadoPor: null,
    triggers: [],  // ver triggers.js
    passivos: [],  // ver triggers.js
  };

  for (const pid of jogadores) {
    game.players[pid] = { playerId: pid, nome: nomes[pid], mana: TCG.MANA_INICIAL, vida: TCG.VIDA_INICIAL, mao: [] };
    game.board[pid] = TCG.criarLadoTabuleiro(pid);

    const { panteaoInstancias, baralhoInstancias } = montarJogadorDados(pid, rng);
    game.panteoes[pid] = TCG.criarDeck(`Panteão de ${nomes[pid]}`, panteaoInstancias);
    game.baralhos[pid] = TCG.criarDeck(`Baralho Arcano de ${nomes[pid]}`, baralhoInstancias);
  }

  bus.jogo = game; // ver EventBus.emit (events.js) — dispara os gatilhos registrados a cada evento

  return game;
};

TCG.dono = function dono(game, carta) {
  for (const pid of game.jogadores) {
    if (game.players[pid].mao.includes(carta)) return pid;
    if (game.board[pid].monstro === carta || game.board[pid].magia.includes(carta)) return pid;
    if (game.panteoes[pid].cartas.includes(carta)) return pid;
    if (game.baralhos[pid].cartas.includes(carta)) return pid;
    if (game.descarte[pid].includes(carta)) return pid;
  }
  return null;
};

// ---- comprar / destruir (pontos unicos) -----------------------------------

// `origem` identifica DE ONDE veio a compra ("turno" = compra automática da
// Fase de Saque, "efeito" = Encantamento/Habilidade tipo Tomo do Oráculo)
// — alguns gatilhos (Nevoeiro do Pânico, Mente Fraturada) só disparam pra um
// dos dois casos, e sem essa tag não daria pra diferenciar no evento.
TCG.comprar = function comprar(game, playerId, n, origem = "efeito") {
  const ps = game.players[playerId];
  const baralho = game.baralhos[playerId];
  const compradas = [];
  for (let i = 0; i < n; i++) {
    if (TCG.Deck.estaVazio(baralho)) break;
    const carta = TCG.Deck.drawRandom(baralho, game.rng);
    if (ps.mao.length >= TCG.LIMITE_MAO) {
      game.descarte[playerId].push(carta);
      game.bus.emit("cartaDescartada", { playerId, carta });
      continue;
    }
    ps.mao.push(carta);
    compradas.push(carta);
    game.bus.emit("cartaComprada", { playerId, carta, origem });
    // Nevoeiro do Pânico/Mente Fraturada: oferece a decisão reativa aqui
    // mesmo (best-effort — TCG.comprar é chamado de muitos lugares aninhados
    // dentro de efeitos de carta, então isso não encadeia uma continuação
    // até o topo da ação que disparou a compra, diferente de invocar/
    // ativarHabilidade/atacar; a decisão em si sempre resolve certo, só o
    // "resto do turno esperar" não é garantido nesse caso específico).
    TCG.ofertarMaldicoesReativas(game, { tipo: "cartaComprada", playerId, carta, origem });
  }
  return compradas;
};

TCG.descartarAleatorias = function descartarAleatorias(game, playerId, n) {
  const ps = game.players[playerId];
  const alvo = game.rng.sample(ps.mao, Math.min(n, ps.mao.length));
  for (const carta of alvo) {
    ps.mao.splice(ps.mao.indexOf(carta), 1);
    game.descarte[playerId].push(carta);
    game.bus.emit("cartaDescartada", { playerId, carta });
  }
  return alvo;
};

// destroyCard: PONTO UNICO onde uma carta morre. Limpa o slot do tabuleiro
// (monstro OU magia) antes de mais nada, move pro descarte, dispara os
// gatilhos "ao destruir". Nenhum outro codigo deve tocar board.monstro /
// board.magia[i] diretamente — foi exatamente essa duplicacao que causou um
// bug real na versao Python (game/systems.py, docstring de DestructionSystem):
// um combatente destruido em combate continuava marcado como monstro ativo e
// seguia atacando, porque a limpeza de slot estava espalhada em varios lugares.
TCG.destroyCard = function destroyCard(game, carta, motivo = "") {
  const playerId = TCG.dono(game, carta);
  if (playerId !== null) {
    const lado = game.board[playerId];
    if (lado.monstro === carta) TCG.Board.removerMonstro(lado);
    else if (lado.magia.includes(carta)) TCG.Board.removerMagia(lado, carta);

    // evento PRE-destruicao: da pra um gatilho (ex.: Valhalla) sobrescrever
    // contexto.destino ANTES de decidir pra onde a carta vai, sem precisar
    // de um caso especial aqui dentro so pra essa carta. Ainda NAO limpamos
    // os gatilhos desta carta aqui de proposito — uma carta pode ter um
    // gatilho que reage à PRÓPRIA destruição (ex.: Cu Chulainn), que só
    // dispara mais abaixo, no evento "cartaDestruida".
    const contexto = { destino: "descarte" };
    game.bus.emit("cartaSeraDestruida", { carta, motivo, playerId, contexto });

    if (contexto.destino === "panteao") {
      // a remocao do slot (monstro/magia) ja aconteceu acima; so falta
      // devolver a carta pro Panteão em vez de empilhar no descarte.
      TCG.Deck.devolver(game.panteoes[playerId], carta);
    } else {
      game.descarte[playerId].push(carta);
    }
  }
  game.bus.emit("cartaDestruida", { carta, motivo, playerId });
  const gatilho = TCG.EFFECTS_ON_DESTROY[carta.nome];
  if (gatilho) gatilho(game, playerId, carta);

  // Caixa de Pandora: oferece a decisão reativa aqui (best-effort — mesma
  // ressalva de TCG.comprar acima, destroyCard é chamado de muitos lugares
  // aninhados pro "resto do turno esperar" não ser garantido em todo caso).
  TCG.ofertarMaldicoesReativas(game, { tipo: "cartaDestruida", carta, motivo, playerId });

  // só agora, depois que a própria carta teve a chance de reagir à sua
  // destruição (ex.: Cu Chulainn), limpa qualquer passivo/gatilho cuja
  // FONTE é ela — o buff "enquanto ativo" de um Domínio some quando ele morre.
  TCG.removerPassivosDe(game, carta);
  TCG.removerTriggersDe(game, carta);
};

// ---- fase / turno -----------------------------------------------------

const ORDEM_FASES = ["SAQUE", "INVOCACAO", "PRINCIPAL", "BATALHA", "FINAL"];

TCG.iniciarJogo = function iniciarJogo(game) {
  if (game._iniciado) return;
  for (const pid of game.jogadores) TCG.comprar(game, pid, TCG.MAO_INICIAL);
  game.bus.emit("turnoIniciado", { playerId: game.jogadorDaVez, numeroTurno: game.turno });
  game._iniciado = true;
};

// Reseta "Habilidade usada neste turno" — turno novo, direito renovado.
function zerarFlagsDeTurno(game) {
  for (const pid of game.jogadores) {
    const lado = game.board[pid];
    if (lado.monstro) {
      lado.monstro.habilidadeUsadaNesteTurno = false;
      lado.monstro.atacouNesteTurno = false;
    }
    for (const c of lado.magia) if (c) c.habilidadeUsadaNesteTurno = false;
  }
}

// Expira StatusEffects "neste turno"/"ate fim de turno" dos DOIS lados, na
// Fase Final de quem quer que esteja jogando — "neste turno" significa até
// o fim do turno ATUAL, não importa em qual combatente o efeito está (ex.:
// Vínculo Sombrio, que a dona da Maldição aplica no combatente do
// OPONENTE). Espelha UpkeepSystem em game/phases.py.
function expirarBuffsDeFimDeTurno(game) {
  for (const pid of game.jogadores) {
    const lado = game.board[pid];
    const alvos = [lado.monstro, ...lado.magia].filter(Boolean);
    for (const carta of alvos) {
      const antes = carta.statusEffects.length;
      carta.statusEffects = carta.statusEffects.filter(
        (st) => st.duracao !== "NESTE_TURNO" && st.duracao !== "ATE_FIM_DE_TURNO"
      );
      if (carta.statusEffects.length !== antes) TCG.recalcularStats(carta);
      // danoDobradoContraMonstro (Sigurd) e ignoraFraquezaElemental
      // (Shoggoth: "Disforme... até o fim do turno") são sempre NESTE_TURNO/
      // ATE_FIM_DE_TURNO por natureza — a mera flag ligada já significa
      // "ainda não expirou"; não precisam de campo de duração próprio,
      // sempre desligam incondicionalmente aqui. (Céus de Valíria também
      // usa ignoraFraquezaElemental, mas via passivo limpa-e-reaplica a
      // cada Fase Principal — desligar aqui não atrapalha, só cria uma
      // janela inofensiva até a próxima Principal reaplicar.)
      carta.danoDobradoContraMonstro = false;
      carta.ignoraFraquezaElemental = false;
    }
  }
}

TCG.avancarFase = function avancarFase(game) {
  const idx = ORDEM_FASES.indexOf(game.fase);
  const anterior = game.fase;
  let jogadorDoTurnoQueEntra = game.jogadorDaVez;

  let novaFase;
  if (idx < ORDEM_FASES.length - 1) {
    novaFase = ORDEM_FASES[idx + 1];
  } else {
    const i = game.jogadores.indexOf(game.jogadorDaVez);
    game.jogadorDaVez = game.jogadores[(i + 1) % game.jogadores.length];
    game.turno += 1;
    novaFase = "SAQUE";
    jogadorDoTurnoQueEntra = game.jogadorDaVez;
  }
  game.fase = novaFase;
  // snapshot do turno DESTA transição — só importa pra saber se é o
  // primeiro turno de quem está entrando em SAQUE (ver abaixo); congelado
  // aqui pelo mesmo motivo de `novaFase" (comentário logo abaixo).
  const turnoDestaTransicao = game.turno;

  game.bus.emit("faseAlterada", { playerId: game.jogadorDaVez, faseAnterior: anterior, faseNova: novaFase });

  // A PARTIR DAQUI usa `novaFase` (o valor que ESTA chamada produziu), não
  // `game.fase` de novo — um listener de "faseAlterada" pode ter chamado
  // avancarFase RECURSIVAMENTE de dentro do emit acima (ex.: o auto-skip da
  // Fase de Saque em ui.js, quando o turno do bot termina e cai direto na
  // Saque do jogador local, que se auto-pula na hora). Se essa chamada
  // aninhada já tiver avançado `game.fase` de novo antes do emit acima
  // retornar, reler `game.fase` aqui faria a lógica de "quem acabou de
  // entrar nesta fase" (mana, compra, passivos, expirar buffs) ser
  // silenciosamente pulada — foi exatamente isso que aconteceu até esta
  // correção: o jogador local perdia a compra E a mana do turno toda vez
  // que o turno anterior era do bot.
  if (novaFase === "SAQUE") {
    zerarFlagsDeTurno(game);
    // +2 de Mana por turno, exceto no PRIMEIRO turno de cada jogador (eles
    // já começam com MANA_INICIAL, sem bônus adicional nessa primeira vez).
    // Com N jogadores em rodízio, os primeiros N números de turno
    // correspondem exatamente ao primeiro turno de cada um. Espelha
    // ResourceSystem em game/systems.py.
    if (turnoDestaTransicao > game.jogadores.length) {
      const ps = game.players[jogadorDoTurnoQueEntra];
      ps.mana += TCG.MANA_POR_TURNO;
      game.bus.emit("manaAlterada", { playerId: jogadorDoTurnoQueEntra, delta: TCG.MANA_POR_TURNO, total: ps.mana });
    }
    TCG.comprar(game, jogadorDoTurnoQueEntra, 1, "turno");
    if (anterior === "FINAL") game.bus.emit("turnoIniciado", { playerId: jogadorDoTurnoQueEntra, numeroTurno: turnoDestaTransicao });
  }

  if (novaFase === "PRINCIPAL") TCG.aplicarPassivos(game);
  if (novaFase === "FINAL") expirarBuffsDeFimDeTurno(game);

  TCG.checarFimDeJogo(game);
  return game.fase;
};

// ---- combate -----------------------------------------------------

// `multiplicador` (default 1): escala o dano final do ataque, sem mexer no
// resto da fórmula (vantagem elemental, Sigurd, redução de Jardins
// Suspensos, reflexão) — usado por Aquiles ("Rapidez: ataca duas vezes, mas
// o dano é reduzido à metade"), que chama isto DUAS vezes com 0.5 em vez de
// causar dano avulso fora da fórmula de combate normal.
TCG.resolverAtaque = function resolverAtaque(game, atacantePlayer, atacante, defensorPlayer, defensor, multiplicador = 1) {
  game.bus.emit("ataqueDeclarado", { atacantePlayer, atacante, defensorPlayer, defensor });
  let dano = Math.floor(atacante.atualPow * multiplicador);

  if (defensor === null) {
    const ps = game.players[defensorPlayer];
    ps.vida = Math.max(ps.vida - dano, 0);
    // danoCausado ANTES de vidaAlterada: o listener de FX (ui.js) so consegue
    // deduplicar o numero flutuante ("gemeo direto") se ja souber do
    // danoCausado quando vidaAlterada chegar — na ordem trocada os dois
    // emitem animacao, dobrando o numero na tela.
    game.bus.emit("danoCausado", { alvo: null, alvoPlayer: defensorPlayer, quantidade: dano, origem: "ataque" });
    game.bus.emit("vidaAlterada", { playerId: defensorPlayer, delta: -dano, total: ps.vida });
    game.bus.emit("ataqueResolvido", { atacantePlayer, atacante, defensorPlayer, defensor });
    TCG.checarFimDeJogo(game);
    return;
  }

  if (defensor.attackNegated) {
    defensor.attackNegated = false;
    game.bus.emit("ataqueResolvido", { atacantePlayer, atacante, defensorPlayer, defensor });
    return; // ataque completamente anulado
  }

  // A diferença de Combate entre os dois combatentes acerta quem tiver o
  // POW MENOR — não sempre o defensor: atacar um combatente mais forte
  // agora machuca o próprio ATACANTE (contra-ataque). Combatentes parelhos
  // não se machucam (diferença 0).
  dano = Math.abs(atacante.atualPow - defensor.atualPow);

  // Vantagem elemental/Sigurd continuam bonificando o dano com base no
  // ATACANTE (elemento dele vs. o do defensor; "Dano em dobro contra
  // Monstros" checando o TIPO do defensor) exatamente como antes — mesmo
  // que esse dano acabe voltando pro próprio atacante no cenário de
  // contra-ataque acima.
  const elemA = TCG.elementoEfetivo(atacante);
  const elemD = TCG.elementoEfetivo(defensor);
  if (TCG.VANTAGEM_ELEMENTAL[elemA] === elemD && !defensor.ignoraFraquezaElemental) dano = Math.floor(dano * 1.5);

  // Sigurd ("Matador de Feras"): a Habilidade dele so prepara o buff
  // (danoDobradoContraMonstro, NESTE_TURNO); o dano so dobra de verdade se
  // ele ATACAR um Monstro antes do buff expirar na Fase Final.
  if (atacante.danoDobradoContraMonstro && defensor.tipo === "Monstro") dano *= 2;

  dano = Math.floor(dano * multiplicador);

  // Quem leva o dano: quem tiver o POW ATUAL menor (empate cai pro
  // atacante, mas dano já é 0 nesse caso — tanto faz).
  let alvoDano, alvoDanoPlayer;
  if (atacante.atualPow <= defensor.atualPow) { alvoDano = atacante; alvoDanoPlayer = atacantePlayer; }
  else { alvoDano = defensor; alvoDanoPlayer = defensorPlayer; }

  // Reflexão: se quem IA levar o dano tem o escudo, ele volta pro OUTRO
  // participante do combate (Espelho das Ilusões, Retribuição Kármica).
  if (alvoDano.damageReflected) {
    if (alvoDano === atacante) { alvoDano = defensor; alvoDanoPlayer = defensorPlayer; }
    else { alvoDano = atacante; alvoDanoPlayer = atacantePlayer; }
  }

  // Jardins Suspensos: "todo dano recebido por combatentes de Terra é
  // reduzido em 3" (passivo) — vale pra quem quer que esteja levando o
  // dano agora, não só o defensor de costume.
  if (game.reducaoDanoTerra && TCG.elementoEfetivo(alvoDano) === "Terra") {
    dano = Math.max(dano - game.reducaoDanoTerra, 0);
  }

  // O dano que passar da Resistência da criatura vaza pra vida do PRÓPRIO
  // dono dela — antes esse excedente era simplesmente descartado.
  const resAntes = alvoDano.atualRes;
  const danoNaCriatura = Math.min(dano, resAntes);
  const excedente = dano - danoNaCriatura;
  // danoAcumulado (não mutar atualRes direto): sobrevive a qualquer
  // recálculo futuro por outro motivo — bug real que isso corrige: um buff
  // não relacionado nessa mesma carta, depois, silenciosamente "curava"
  // esse dano de combate (ver TCG.recalcularStats).
  alvoDano.danoAcumulado += danoNaCriatura;
  TCG.recalcularStats(alvoDano);
  game.bus.emit("danoCausado", { alvo: alvoDano, alvoPlayer: alvoDanoPlayer, quantidade: danoNaCriatura, origem: "ataque" });
  if (excedente > 0) {
    const psAlvo = game.players[alvoDanoPlayer];
    psAlvo.vida = Math.max(psAlvo.vida - excedente, 0);
    // mesma ordem danoCausado-antes-de-vidaAlterada do dano direto (dedup de FX).
    game.bus.emit("danoCausado", { alvo: null, alvoPlayer: alvoDanoPlayer, quantidade: excedente, origem: "ataque" });
    game.bus.emit("vidaAlterada", { playerId: alvoDanoPlayer, delta: -excedente, total: psAlvo.vida });
  }

  if (alvoDano.atualRes <= 0) {
    TCG.destroyCard(game, alvoDano, "derrotado em combate");
    // quem CAUSOU o dano ganha +1 de mana — vale pro atacante de costume,
    // pro defensor quando o dano volta por reflexão (Espelho das Ilusões,
    // Retribuição Kármica), e agora também pro defensor quando o próprio
    // atacante morre de contra-ataque por atacar algo mais forte.
    const beneficiario = alvoDanoPlayer === atacantePlayer ? defensorPlayer : atacantePlayer;
    const ps = game.players[beneficiario];
    ps.mana += 1;
    game.bus.emit("manaAlterada", { playerId: beneficiario, delta: 1, total: ps.mana });
  }
  // "logo após atacar" (Cânion dos Ventos) — dispara sempre que o ataque
  // termina de resolver, com ou sem dano/destruição (os outros 2 desfechos
  // possíveis, sem defensor e ataque anulado, já emitem isso mais acima).
  game.bus.emit("ataqueResolvido", { atacantePlayer, atacante, defensorPlayer, defensor });
  TCG.checarFimDeJogo(game);
};

// ---- fim de jogo -----------------------------------------------------

TCG.checarFimDeJogo = function checarFimDeJogo(game) {
  if (game.fimDeJogo) return game.fimDeJogo;
  for (const pid of game.jogadores) {
    const ps = game.players[pid];
    if (ps.vida <= 0) {
      game.fimDeJogo = { perdedor: pid, motivo: "Pontos de Vida chegaram a 0" };
      game.bus.emit("fimDeJogo", game.fimDeJogo);
      return game.fimDeJogo;
    }
    const semCombatentes = game.board[pid].monstro === null && TCG.Deck.estaVazio(game.panteoes[pid]);
    if (semCombatentes && game.jogadorDaVez === pid && game.fase === "INVOCACAO") {
      game.fimDeJogo = { perdedor: pid, motivo: "sem combatentes para invocar" };
      game.bus.emit("fimDeJogo", game.fimDeJogo);
      return game.fimDeJogo;
    }
  }
  return null;
};

TCG.estado = function estado(game) {
  const nomeDe = (c) => (c ? c.nome : null);
  return {
    turno: game.turno,
    jogadorDaVez: game.jogadorDaVez,
    fase: game.fase,
    jogadores: Object.fromEntries(
      game.jogadores.map((pid) => [pid, {
        nome: game.players[pid].nome, mana: game.players[pid].mana, vida: game.players[pid].vida,
        mao: game.players[pid].mao.map(nomeDe),
      }])
    ),
    tabuleiro: Object.fromEntries(
      game.jogadores.map((pid) => [pid, {
        monstro: nomeDe(game.board[pid].monstro), magia: game.board[pid].magia.map(nomeDe),
      }])
    ),
    fimDeJogo: game.fimDeJogo ? game.fimDeJogo.motivo : null,
  };
};

// Snapshot COMPLETO do estado (cartas de verdade, não só nomes — instância
// inteira, com arquivo/custoMana/atualPow/etc, tudo que renderLado/renderMao
// precisam pra desenhar a tela) FILTRADO do ponto de vista de
// `destinatarioId` — usado pelo host em multiplayer (webgame/rede.js) pra
// sincronizar o guest sem NUNCA revelar informação oculta: a mão do
// jogador que não é `destinatarioId`, e qualquer Maldição virada pra baixo
// (faceDown) cujo dono não é `destinatarioId` — nem o dono de uma
// Maldição ALHEIA setada vê a identidade dela. Isso não é só uma UI que
// escolhe não desenhar (como TCG.estado/ui.js fazem hoje) — o dado em si
// não existe no lado de quem não deveria ver, então nem abrindo o
// devtools dá pra trapacear.
function cartaOuOculta(carta, podeVer) {
  if (!carta) return null;
  if (podeVer) return carta;
  return { oculto: true, instanceId: carta.instanceId };
}

TCG.estadoCompletoPara = function estadoCompletoPara(game, destinatarioId) {
  function maoFiltrada(playerId) {
    return game.players[playerId].mao.map((c) => cartaOuOculta(c, playerId === destinatarioId));
  }
  function magiaFiltrada(lado) {
    return lado.magia.map((c) => cartaOuOculta(c, !c || !c.faceDown || lado.playerId === destinatarioId));
  }
  return {
    turno: game.turno,
    jogadorDaVez: game.jogadorDaVez,
    fase: game.fase,
    ultimoDominioAtivadoPor: game.ultimoDominioAtivadoPor,
    fimDeJogo: game.fimDeJogo,
    players: Object.fromEntries(game.jogadores.map((pid) => [pid, {
      nome: game.players[pid].nome, mana: game.players[pid].mana, vida: game.players[pid].vida,
      mao: maoFiltrada(pid),
    }])),
    board: Object.fromEntries(game.jogadores.map((pid) => [pid, {
      playerId: pid, monstro: game.board[pid].monstro, magia: magiaFiltrada(game.board[pid]),
    }])),
    // Baralho: nunca é lido além da CONTAGEM em nenhum lugar da UI, nem pelo
    // próprio dono (a compra é aleatória/oculta até sair — ver TCG.comprar)
    // — manda só o número, nunca a lista, mesmo pro dono.
    baralhos: Object.fromEntries(game.jogadores.map((pid) => [pid, TCG.Deck.restantes(game.baralhos[pid]).length])),
    // Panteão é DIFERENTE: é a lista de Combatentes que o PRÓPRIO dono
    // escolhe pra invocar (solicitarInvocacao, ui.js) — ele precisa ver a
    // lista inteira pra decidir. Só o OPONENTE não pode ver (mesma regra
    // de sempre: contagem, não identidade).
    panteoes: Object.fromEntries(game.jogadores.map((pid) => [
      pid,
      pid === destinatarioId
        ? TCG.Deck.restantes(game.panteoes[pid])
        : TCG.Deck.restantes(game.panteoes[pid]).length,
    ])),
    // descarte é informação pública (ver ui.js mostrarDescarte) — sem filtro.
    descarte: Object.fromEntries(game.jogadores.map((pid) => [pid, game.descarte[pid]])),
  };
};
