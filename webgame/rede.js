// Multiplayer sobre rede local (LAN). O relay (scripts/relay_lan.py) só
// repassa mensagens entre host e guest sem entender nada de jogo — toda a
// lógica de sincronização e filtragem de informação oculta mora aqui.
//
// Modelo: o HOST roda a simulação de verdade (só ele chama TCG.acoes.*, só
// ele consome game.rng — dois clientes independentes consumindo RNG em
// ordens diferentes dessincronizariam sem chance de detecção, ver
// GAME_ENGINE.md). O GUEST nunca chama TCG.acoes.* sozinho: manda
// "intents" pro host e aplica de volta os eventos + snapshots de estado
// que ele manda (ver TCG.estadoCompletoPara, engine.js).
var TCG = window.TCG || (window.TCG = {});

// `tipoSincronizacao` (default "sincronizacaoInicial"): tipo do PRIMEIRO
// evento mandado pro guest na construção (ver final da seção HOST). Além
// do início normal de duelo, TCG.iniciarPartidaMultiplayer (match.js)
// também chama criarRede de novo quando um guest RECONECTA no meio de um
// duelo já em andamento — nesse caso passa "resincronizacao" pra não ser
// confundido com "começou um duelo novo" (ver dispatch do guest,
// match.js), mesmo repassando o mesmo snapshot completo de sempre.
TCG.criarRede = function criarRede({ role, ws, game, jogadorLocal, tipoSincronizacao = "sincronizacaoInicial" }) {
  const oponenteId = TCG.oponenteDe(game, jogadorLocal);

  // `wsAtual` (não `ws` direto): TCG.substituirWsDaRede permite trocar o
  // WebSocket por baixo depois de uma reconexão (ver match.js
  // tentarReconectar) sem precisar reconstruir toda a rede/UI do zero —
  // só o transporte muda, o `game`/estado de sincronização continuam os
  // mesmos.
  let wsAtual = ws;
  function enviar(msg) {
    if (wsAtual.readyState === WebSocket.OPEN) wsAtual.send(JSON.stringify(msg));
  }
  function substituirWs(novoWs) {
    wsAtual = novoWs;
  }

  // ---- cache de identidade por instanceId (só usada pelo GUEST) --------
  // Cada snapshot chega como JSON recém-desserializado — objetos NOVOS
  // mesmo quando é "a mesma carta de antes". Isso quebraria elCartaAtual
  // (WeakMap por IDENTIDADE de objeto, ver ui.js) em toda animação "em
  // lugar" (pulso/shake/flip): a mesma instanceId precisa sempre resolver
  // pro MESMO objeto JS, mutado em cima — igual o motor de verdade já faz
  // com atualPow/statusEffects/etc — nunca substituído por um objeto novo.
  const cacheCartas = new Map();
  function resolverCartaRecebida(dados) {
    if (!dados) return null;
    let carta = cacheCartas.get(dados.instanceId);
    if (!carta) {
      carta = {};
      cacheCartas.set(dados.instanceId, carta);
    }
    Object.assign(carta, dados);
    return carta;
  }
  function resolverPayloadRecebido(payload) {
    const resolvido = {};
    for (const [chave, valor] of Object.entries(payload || {})) {
      resolvido[chave] = (valor && typeof valor === "object" && "instanceId" in valor)
        ? resolverCartaRecebida(valor)
        : valor;
    }
    return resolvido;
  }
  // Baralho: só a CONTAGEM existe do lado de cá (ver estadoCompletoPara) —
  // nenhum código de render lê o conteúdo, só TCG.Deck.restantes(...).length.
  function baralhoFalso(contagem) {
    return { cartas: new Array(contagem).fill({}), compradas: new Set() };
  }
  // Panteão: o HOST manda a lista de verdade quando é o Panteão do PRÓPRIO
  // destinatário (precisa pra solicitarInvocacao escolher quem invocar) e
  // só a contagem quando é o do oponente — os dois formatos chegam aqui.
  function panteaoRecebido(valor) {
    if (Array.isArray(valor)) return { cartas: valor.map(resolverCartaRecebida), compradas: new Set() };
    return baralhoFalso(valor);
  }

  function aplicarSnapshot(estado) {
    game.turno = estado.turno;
    game.jogadorDaVez = estado.jogadorDaVez;
    game.fase = estado.fase;
    game.ultimoDominioAtivadoPor = estado.ultimoDominioAtivadoPor;
    game.fimDeJogo = estado.fimDeJogo;
    for (const pid of game.jogadores) {
      const p = estado.players[pid];
      // NÃO sincroniza `nome`: é só um rótulo local ("Você"/"Oponente",
      // ver TCG.criarJogo/match.js), não estado de jogo de verdade — cada
      // lado já criou o SEU `game` com o nome certo do PRÓPRIO ponto de
      // vista; copiar o nome do host por cima faria os dois lados
      // mostrarem os mesmos rótulos (do ponto de vista do host).
      game.players[pid].mana = p.mana;
      game.players[pid].vida = p.vida;
      game.players[pid].mao = p.mao.map(resolverCartaRecebida);
      const b = estado.board[pid];
      game.board[pid].monstro = resolverCartaRecebida(b.monstro);
      game.board[pid].magia = b.magia.map(resolverCartaRecebida);
      game.panteoes[pid] = panteaoRecebido(estado.panteoes[pid]);
      game.baralhos[pid] = baralhoFalso(estado.baralhos[pid]);
      game.descarte[pid] = estado.descarte[pid].map(resolverCartaRecebida);
    }
  }

  // ---- papel: HOST -------------------------------------------------------
  if (role === "host") {
    function localizaLado(carta) {
      for (const pid of game.jogadores) {
        if (game.players[pid].mao.includes(carta)) return { pid, zona: "mao" };
        if (game.board[pid].magia.includes(carta)) return { pid, zona: "magia" };
      }
      return null;
    }
    function deveOcultarPara(valor, destinatarioId) {
      if (!valor || typeof valor !== "object" || !("instanceId" in valor)) return false;
      const onde = localizaLado(valor);
      if (!onde) return false;
      if (onde.zona === "mao") return onde.pid !== destinatarioId;
      if (onde.zona === "magia") return valor.faceDown && onde.pid !== destinatarioId;
      return false;
    }
    function filtrarPayload(payload, destinatarioId) {
      const copia = {};
      for (const [chave, valor] of Object.entries(payload)) {
        copia[chave] = deveOcultarPara(valor, destinatarioId)
          ? { oculto: true, instanceId: valor.instanceId }
          : valor;
      }
      return copia;
    }
    function porInstanceId(id) {
      if (id == null) return null;
      for (const pid of game.jogadores) {
        const naMao = game.players[pid].mao.find((c) => c.instanceId === id);
        if (naMao) return naMao;
        if (game.board[pid].monstro && game.board[pid].monstro.instanceId === id) return game.board[pid].monstro;
        const naMagia = game.board[pid].magia.find((c) => c && c.instanceId === id);
        if (naMagia) return naMagia;
        const noPanteao = TCG.Deck.restantes(game.panteoes[pid]).find((c) => c.instanceId === id);
        if (noPanteao) return noPanteao;
      }
      return null;
    }

    // Repassa TODO evento emitido no bus pro guest, junto com um snapshot
    // fresco do estado (filtrado do ponto de vista dele) — mais simples e
    // mais robusto que tentar detectar "quando a ação terminou de vez" (ver
    // plano): substituição integral nunca "dessincroniza", e o volume de
    // dados de um jogo de cartas é trivial numa LAN.
    game.bus.onQualquer((evento) => {
      const { tipo, ...payload } = evento;
      enviar({
        type: "evento", tipo,
        payload: filtrarPayload(payload, oponenteId),
        estado: TCG.estadoCompletoPara(game, oponenteId),
      });
    });

    // Decisão pedida pro GUEST (ex.: Maldição reativa, escolha de
    // Combatente): não resolve sozinho (ver ui.js "selecaoPedida" local),
    // encaminha pro guest e fica esperando a resposta chegar pela rede —
    // game.selection já foi desenhado pra isso (resolver() pode ser chamado
    // de qualquer lugar, a qualquer momento depois).
    const pedidosPendentes = new Map(); // requestId -> opcoes (cartas reais)
    game.bus.on("selecaoPedida", (evento) => {
      if (evento.playerId !== oponenteId) return; // decisão do próprio host: UI local já mostra o modal
      pedidosPendentes.set(evento.requestId, evento.opcoes);
      enviar({
        type: "selecaoPedida",
        requestId: evento.requestId, prompt: evento.prompt, minimo: evento.minimo, maximo: evento.maximo,
        opcoes: evento.opcoes.map((c) => (deveOcultarPara(c, oponenteId) ? { oculto: true, instanceId: c.instanceId } : c)),
      });
    });

    function tratarIntent(msg) {
      const carta = porInstanceId(msg.cartaInstanceId);
      try {
        // TCG.acoes.avancarFase/terminarTurno NÃO recebem playerId nem
        // validam de quem é a vez (são só "avança o relógio", confiança de
        // quem chama) — ao contrário de invocar/ativarHabilidade/atacar,
        // que já validam via exigirFase(game, playerId, ...). Sem essa
        // checagem aqui, o guest poderia avançar a fase durante o turno do
        // HOST só mandando o intent certo.
        if ((msg.fn === "avancarFase" || msg.fn === "terminarTurno") && game.jogadorDaVez !== oponenteId) {
          throw new TCG.AcaoInvalida("Não é a vez desse jogador.");
        }
        if (msg.fn === "invocar") TCG.acoes.invocar(game, oponenteId, carta);
        else if (msg.fn === "ativarHabilidade") TCG.acoes.ativarHabilidade(game, oponenteId, carta);
        else if (msg.fn === "jogarCartaDeCampo") TCG.acoes.jogarCartaDeCampo(game, oponenteId, carta, msg.slot ?? null);
        else if (msg.fn === "ativarMaldicaoSetada") TCG.acoes.ativarMaldicaoSetada(game, oponenteId, carta);
        else if (msg.fn === "atacar") TCG.acoes.atacar(game, oponenteId, jogadorLocal);
        else if (msg.fn === "avancarFase") TCG.acoes.avancarFase(game);
        else if (msg.fn === "terminarTurno") TCG.acoes.terminarTurno(game);
      } catch (e) {
        if (!(e instanceof TCG.AcaoInvalida)) throw e;
        enviar({ type: "erro", mensagem: e.message });
      }
    }

    function tratarMensagem(msg) {
      if (msg.type === "intent") tratarIntent(msg);
      else if (msg.type === "selecaoResposta") {
        const opcoesReais = pedidosPendentes.get(msg.requestId) || [];
        pedidosPendentes.delete(msg.requestId);
        const escolha = (msg.escolha || [])
          .map((id) => opcoesReais.find((c) => c.instanceId === id))
          .filter(Boolean);
        game.selection.resolver(msg.requestId, escolha);
      }
    }

    // Manda um snapshot completo avulso — usada tanto pro bootstrap inicial
    // (abaixo) quanto por match.js quando o GUEST reconecta no meio de um
    // duelo já em andamento (tipoSincronizacao: "resincronizacao"). NUNCA
    // chame TCG.criarRede de novo sobre o MESMO `game` só pra reenviar um
    // snapshot: os `game.bus.onQualquer`/`game.bus.on("selecaoPedida")`
    // acima ficam registrados pra sempre (não há "off" correspondente aqui)
    // — uma segunda chamada duplicaria PERMANENTEMENTE todo broadcast dali
    // pra frente (2x, depois 3x a cada reconexão adicional), causando
    // exatamente o sintoma que já apareceu: logs duplicados no guest e o
    // jogo travando por aplicar o mesmo evento múltiplas vezes.
    function enviarSincronizacaoCompleta(tipo) {
      enviar({ type: "evento", tipo, payload: {}, estado: TCG.estadoCompletoPara(game, oponenteId) });
    }

    // primeiro snapshot: o guest ainda não tem NADA desenhado certo até
    // aqui, não dá pra esperar o primeiro evento de jogo pra sincronizar.
    enviarSincronizacaoCompleta(tipoSincronizacao);

    // o host age sempre por TCG.acoes.* direto, não precisa de wrapper de
    // ações — só de receber intents/respostas de seleção do guest. Quem
    // chama (webgame/match.js) é dono do único listener "message" do `ws`
    // ao longo de toda a partida (várias trocas de duelo incluídas) e
    // repassa cada mensagem recebida pra cá.
    return { tratarMensagem, substituirWs, enviarSincronizacaoCompleta };
  }

  // ---- papel: GUEST --------------------------------------------------
  // requestId de uma seleção vinda do HOST (contador dele) e requestId de
  // uma seleção puramente LOCAL (ex.: solicitarInvocacao, contador do
  // SelectionManager do próprio guest) são DOIS contadores independentes,
  // cada um começando em 1 — colidiriam sem aviso nenhum. Namespacing
  // ("rede:N") faz o requestId de rede nunca ser confundido com um local.
  const opcoesPendentesLocais = new Map(); // "rede:N" -> cartas (já resolvidas/cacheadas)
  const prefixoRede = (id) => `rede:${id}`;

  // Quem chama (webgame/match.js) é dono do único listener "message" do
  // `ws` ao longo de toda a partida e repassa cada mensagem recebida pra
  // cá — necessário pra poder trocar de duelo (nova instância de rede,
  // sem perder/duplicar listeners no mesmo WebSocket).
  function tratarMensagem(msg) {
    if (msg.type === "evento") {
      aplicarSnapshot(msg.estado);
      if (msg.tipo !== "sincronizacaoInicial") game.bus.emit(msg.tipo, resolverPayloadRecebido(msg.payload));
    } else if (msg.type === "selecaoPedida") {
      const opcoes = msg.opcoes.map(resolverCartaRecebida);
      const requestId = prefixoRede(msg.requestId);
      opcoesPendentesLocais.set(requestId, opcoes);
      game.bus.emit("selecaoPedida", {
        requestId, playerId: jogadorLocal, prompt: msg.prompt,
        opcoes, minimo: msg.minimo, maximo: msg.maximo,
      });
    } else if (msg.type === "erro") {
      console.warn("[rede] o host recusou uma ação:", msg.mensagem);
    }
  }

  // Substitui TCG.acoes pro lado do guest: em vez de mutar o jogo direto
  // (que só o host pode fazer de verdade), manda a intenção pela rede e
  // chama `continuar` na hora — o resultado de verdade chega depois, de
  // forma assíncrona, via evento+snapshot, e o próprio game.bus/fila de FX
  // cuidam de mostrar quando estiver pronto.
  const acoesDoGuest = {
    invocar(g, pid, carta, continuar = () => {}) { enviar({ type: "intent", fn: "invocar", cartaInstanceId: carta.instanceId }); continuar(); },
    ativarHabilidade(g, pid, carta, continuar = () => {}) { enviar({ type: "intent", fn: "ativarHabilidade", cartaInstanceId: carta.instanceId }); continuar(); },
    jogarCartaDeCampo(g, pid, carta, slot = null) { enviar({ type: "intent", fn: "jogarCartaDeCampo", cartaInstanceId: carta.instanceId, slot }); },
    ativarMaldicaoSetada(g, pid, carta) { enviar({ type: "intent", fn: "ativarMaldicaoSetada", cartaInstanceId: carta.instanceId }); },
    atacar(g, pid, oponente, continuar = () => {}) { enviar({ type: "intent", fn: "atacar" }); continuar(); },
    avancarFase(g) { enviar({ type: "intent", fn: "avancarFase" }); },
    terminarTurno(g) { enviar({ type: "intent", fn: "terminarTurno" }); },
  };

  return {
    tratarMensagem,
    substituirWs,
    acoes: acoesDoGuest,
    // Nem toda "selecaoPedida" que o guest vê veio da rede: algumas são só
    // UI local (ex.: solicitarInvocacao em ui.js chama game.selection.
    // solicitar() direto, sem passar pelo host — é só um jeito de mostrar
    // um modal e coletar a escolha antes de mandar a AÇÃO de verdade,
    // ex.: acoesDoGuest.invocar). Só as que estão em opcoesPendentesLocais
    // (registradas quando uma mensagem "selecaoPedida" chega DO host, ver
    // acima) precisam de resposta pela rede; qualquer outra é resolvida na
    // hora, local, exatamente como no modo single-player.
    resolverSelecao(requestId, escolha) {
      if (opcoesPendentesLocais.has(requestId)) {
        const idOriginal = Number(String(requestId).slice("rede:".length));
        enviar({ type: "selecaoResposta", requestId: idOriginal, escolha: escolha.map((c) => c.instanceId) });
        opcoesPendentesLocais.delete(requestId);
      } else {
        game.selection.resolver(requestId, escolha);
      }
    },
  };
};
