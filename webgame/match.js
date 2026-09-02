// Partida (best-of-5, no espírito de jogo de luta): uma sequência de
// duelos independentes (cada um um `game` de engine.js) sobre a MESMA
// conexão de rede. O primeiro a vencer TCG.VITORIAS_PARA_VENCER_PARTIDA
// duelos vence a partida; o vencedor de cada duelo carrega sua vida
// restante (limitada ao máximo) pro próximo, o perdedor recomeça cheio —
// mana/tabuleiro/mão/baralho sempre resetam do zero a cada duelo, porque
// cada um é um `game` novo de TCG.criarJogo.
//
// Dono do ÚNICO listener "message" do WebSocket durante toda a partida
// (rede.js NÃO instala mais o dele sozinho — ver TCG.criarRede) — assim
// dá pra trocar de duelo sem perder/duplicar listener no mesmo `ws`.
var TCG = window.TCG || (window.TCG = {});

TCG.VITORIAS_PARA_VENCER_PARTIDA = 3;

TCG.criarPartida = function criarPartida() {
  return {
    vitoriasDuelo: { 1: 0, 2: 0 },
    vidaCarregada: { 1: null, 2: null }, // null = começa o próximo duelo com vida cheia
    duelo: 1,
    fimDePartida: null, // {vencedor} quando alguém chega a VITORIAS_PARA_VENCER_PARTIDA
    bus: new TCG.EventBus(),
  };
};

// Roda IGUAL no host e no guest: como rede.js já repassa "fimDeJogo" pro
// bus local do guest com o payload de verdade (não é o guest quem decide
// quem venceu), contar vitórias não precisa de mensagem de rede nova —
// os dois lados chegam ao mesmo resultado de forma independente.
function registrarFimDeDuelo(partida, game) {
  game.bus.on("fimDeJogo", (evento) => {
    const perdedor = evento.perdedor;
    const vencedor = TCG.oponenteDe(game, perdedor);
    partida.vitoriasDuelo[vencedor] += 1;
    partida.vidaCarregada[vencedor] = game.players[vencedor].vida;
    partida.vidaCarregada[perdedor] = null;
    if (partida.vitoriasDuelo[vencedor] >= TCG.VITORIAS_PARA_VENCER_PARTIDA) {
      partida.fimDePartida = { vencedor };
    }
    partida.bus.emit("dueloConcluido", {
      placar: { ...partida.vitoriasDuelo },
      vencedorDuelo: vencedor,
      fimDePartida: partida.fimDePartida,
    });
  });
}

function criarJogoDoDuelo(partida, { seed = null, nomes }) {
  const game = TCG.criarJogo({ seed, nomes });
  for (const pid of game.jogadores) {
    const vidaCarregada = partida.vidaCarregada[pid];
    game.players[pid].vida = vidaCarregada != null ? Math.min(vidaCarregada, TCG.VIDA_INICIAL) : TCG.VIDA_INICIAL;
  }
  registrarFimDeDuelo(partida, game);
  return game;
}

function mostrarStatusConexao(texto) {
  const el = document.getElementById("status-multiplayer");
  if (el) { el.textContent = texto; el.style.display = texto ? "block" : "none"; }
}

// Ponto de entrada único pro multiplayer (chamado por main.js tanto pro
// relay LAN quanto pro relay com código de sala — os dois já entregam
// `{ws, role, jogadorLocal}` no mesmo formato depois do handshake).
TCG.iniciarPartidaMultiplayer = function iniciarPartidaMultiplayer({ ws, role, jogadorLocal }) {
  const partida = TCG.criarPartida();
  window.partida = partida; // depuração/verificação, mesmo espírito de window.game/window.ui (main.js)
  let redeAtual = null;
  let primeiraSincronizacaoRecebida = false; // só relevante pro guest, ver dispatch abaixo

  function nomesParaDuelo() {
    return role === "host" ? { 1: "Você (host)", 2: "Oponente" } : { 1: "Oponente", 2: "Você" };
  }

  function ligarUIDoDuelo(game, { seedInicial } = {}) {
    const rede = TCG.criarRede({ role, ws, game, jogadorLocal });
    redeAtual = rede;
    window.game = game;
    const opcoesComuns = { modoLocal: false, partida, role };
    window.ui = role === "host"
      ? TCG.criarUI(game, jogadorLocal, opcoesComuns)
      : TCG.criarUI(game, jogadorLocal, {
          ...opcoesComuns,
          acoes: rede.acoes,
          resolverSelecao: (id, escolha) => rede.resolverSelecao(id, escolha),
        });
  }

  // Host-only: acionado pelo botão "Próximo Duelo" (ver ui.js renderFim) —
  // constrói o próximo `game` já com a vida carregada e liga rede/UI novas;
  // TCG.criarRede manda o snapshot inicial pro guest de graça, na
  // construção (ver rede.js), então não precisa de mensagem extra aqui.
  partida.iniciarProximoDuelo = function iniciarProximoDuelo() {
    if (role !== "host" || partida.fimDePartida) return;
    partida.duelo += 1;
    const game = criarJogoDoDuelo(partida, { nomes: nomesParaDuelo() });
    TCG.iniciarJogo(game);
    ligarUIDoDuelo(game);
  };

  ws.addEventListener("close", () => mostrarStatusConexao("Conexão com o outro jogador caiu. Recarregue a página pra tentar de novo."));

  if (role === "host") {
    mostrarStatusConexao("Você é o HOST. Aguardando o outro jogador conectar...");
    ws.addEventListener("message", function dispatch(ev) {
      const msg = JSON.parse(ev.data);
      if (msg.type === "guestConectou") {
        mostrarStatusConexao(null);
        const params = new URLSearchParams(window.location.search);
        const seed = params.has("seed") ? Number(params.get("seed")) : null;
        const game = criarJogoDoDuelo(partida, { seed, nomes: nomesParaDuelo() });
        TCG.iniciarJogo(game);
        ligarUIDoDuelo(game);
      } else if (msg.type === "oponenteDesconectou") {
        mostrarStatusConexao("O oponente caiu. Aguardando reconexão...");
      } else if (redeAtual) {
        redeAtual.tratarMensagem(msg);
      }
    });
  } else {
    // guest: NÃO cria uma simulação de verdade — só um objeto com o
    // formato certo pro render()/criarUI rodarem em cima; o RNG dele nunca
    // decide nada (o snapshot do host sobrescreve tudo assim que chega,
    // ver rede.js aplicarSnapshot). O mesmo vale pra vida carregada: é só
    // um placeholder até o snapshot de verdade chegar.
    mostrarStatusConexao("Conectado. Aguardando o estado inicial do jogo...");
    const game = criarJogoDoDuelo(partida, { nomes: nomesParaDuelo() });
    ligarUIDoDuelo(game);
    mostrarStatusConexao(null);

    ws.addEventListener("message", function dispatch(ev) {
      const msg = JSON.parse(ev.data);
      if (msg.type === "oponenteDesconectou") {
        mostrarStatusConexao("O oponente caiu. Aguardando reconexão...");
        return;
      }
      // Uma SEGUNDA (ou posterior) "sincronizacaoInicial" só pode
      // significar que o host começou um duelo novo (dentro de UM duelo
      // ela é mandada exatamente uma vez, na construção de TCG.criarRede)
      // — o `game` antigo é jogado fora (não só re-sincronizado por cima:
      // triggers/passivos registrados pelas cartas do duelo anterior não
      // fariam sentido no tabuleiro novo) e um novo é criado por baixo do
      // snapshot que está chegando.
      if (msg.type === "evento" && msg.tipo === "sincronizacaoInicial") {
        if (primeiraSincronizacaoRecebida) {
          partida.duelo += 1;
          const novoGame = criarJogoDoDuelo(partida, { nomes: nomesParaDuelo() });
          ligarUIDoDuelo(novoGame);
        } else {
          primeiraSincronizacaoRecebida = true;
        }
      }
      if (redeAtual) redeAtual.tratarMensagem(msg);
    });
  }
};
