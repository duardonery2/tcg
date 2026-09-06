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
// dá pra trocar de duelo sem perder/duplicar listener no mesmo `ws`. Além
// disso, é quem cuida de reconectar quando a conexão cai (ver
// tentarReconectar abaixo) — heartbeat (webgame/sala.js) tenta evitar a
// queda; isto aqui é a rede de segurança pra quando ela acontece mesmo
// assim.
var TCG = window.TCG || (window.TCG = {});

TCG.VITORIAS_PARA_VENCER_PARTIDA = 3;

// Janela total pra reconectar depois de uma queda, contada a partir do
// PRIMEIRO close de cada episódio de queda (não reinicia a cada tentativa
// falha dentro do mesmo episódio) — pedido explícito do usuário: tempo
// suficiente pra sobreviver uma queda de wifi ou o navegador suspender a
// aba, sem tentar pra sempre num link morto de vez.
TCG.JANELA_RECONEXAO_MS = 300000;
const INTERVALO_ENTRE_TENTATIVAS_MS = 2000;

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
//
// `reconectar` (opcional): função assíncrona que abre e retoma uma NOVA
// conexão pro MESMO papel (fornecida por main.js — difiere entre o
// caminho LAN e o de sala por código, ver lá) — sem ela, uma queda de
// conexão volta a mostrar só "recarregue a página" (comportamento de
// antes desta rede de segurança existir).
TCG.iniciarPartidaMultiplayer = function iniciarPartidaMultiplayer({ ws, role, jogadorLocal, reconectar = null }) {
  const partida = TCG.criarPartida();
  window.partida = partida; // depuração/verificação, mesmo espírito de window.game/window.ui (main.js)
  let redeAtual = null;
  let primeiraSincronizacaoRecebida = false; // só relevante pro guest, ver dispatch abaixo
  let primeiroGuestJaConectou = false; // só relevante pro host, ver dispatch abaixo
  let pararHeartbeat = null;
  let reconectando = false;
  let fimDaJanelaDeReconexao = null; // timestamp; null = não estamos numa queda agora

  function nomesParaDuelo() {
    return role === "host" ? { 1: "Você (host)", 2: "Oponente" } : { 1: "Oponente", 2: "Você" };
  }

  // Só a camada de rede (sem mexer em window.ui) — chamada de dentro de
  // ligarUIDoDuelo, sempre sobre um `game` NOVO (início de duelo). NUNCA
  // chame isto de novo sobre um `game` já em uso (ex.: pra reenviar um
  // snapshot depois que o outro lado reconecta) — o branch HOST de
  // TCG.criarRede registra listeners em game.bus sem jeito de tirá-los
  // depois; uma segunda chamada sobre o MESMO bus duplicaria pra sempre
  // todo broadcast dali pra frente. Pra isso existe
  // redeAtual.enviarSincronizacaoCompleta (ver dispatch do host abaixo).
  function religarRede(game) {
    const rede = TCG.criarRede({ role, ws, game, jogadorLocal });
    redeAtual = rede;
    return rede;
  }

  function ligarUIDoDuelo(game) {
    const rede = religarRede(game);
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

  function religarHeartbeat(wsAlvo) {
    if (pararHeartbeat) pararHeartbeat();
    pararHeartbeat = TCG.iniciarHeartbeat(wsAlvo);
  }

  // Redundância pedida: quando a conexão cai (queda real de rede, proxy
  // fechando por ociosidade, etc.), tenta reabrir e retomar o MESMO papel
  // repetidamente por até TCG.JANELA_RECONEXAO_MS (5 min) antes de desistir
  // e voltar à mensagem antiga de "recarregue a página". Só troca o
  // TRANSPORTE (substituirWs) — o `game`/`partida` locais continuam os
  // mesmos, nada é perdido do lado de quem reconecta; o OUTRO lado, se for
  // o host, também manda um resync completo assim que percebe (ver
  // dispatch do host, "guestConectou" chegando pela segunda vez).
  async function tentarReconectar() {
    if (reconectando || !reconectar || partida.fimDePartida) return;
    reconectando = true;
    if (!fimDaJanelaDeReconexao) fimDaJanelaDeReconexao = Date.now() + TCG.JANELA_RECONEXAO_MS;

    let tentativa = 0;
    while (Date.now() < fimDaJanelaDeReconexao) {
      tentativa += 1;
      mostrarStatusConexao(`Conexão caiu. Tentando reconectar (tentativa ${tentativa})...`);
      try {
        const novoWs = await reconectar();
        ws = novoWs;
        if (redeAtual) redeAtual.substituirWs(novoWs);
        anexarListeners(novoWs);
        mostrarStatusConexao(null);
        fimDaJanelaDeReconexao = null;
        reconectando = false;
        return;
      } catch (e) {
        await new Promise((resolve) => setTimeout(resolve, INTERVALO_ENTRE_TENTATIVAS_MS));
      }
    }
    mostrarStatusConexao("Não foi possível reconectar. Recarregue a página pra tentar de novo.");
    reconectando = false;
  }

  let dispatch;
  function anexarListeners(wsAlvo) {
    wsAlvo.addEventListener("close", tentarReconectar, { once: true });
    wsAlvo.addEventListener("message", dispatch);
    religarHeartbeat(wsAlvo);
    window.__tcgWs = wsAlvo; // depuração/verificação, ver scripts/testar_webgame_reconexao_playwright.py
  }

  if (role === "host") {
    mostrarStatusConexao("Você é o HOST. Aguardando o outro jogador conectar...");
    dispatch = function dispatch(ev) {
      const msg = JSON.parse(ev.data);
      if (msg.type === "pong") return;
      if (msg.type === "guestConectou") {
        mostrarStatusConexao(null);
        if (!primeiroGuestJaConectou) {
          primeiroGuestJaConectou = true;
          const params = new URLSearchParams(window.location.search);
          const seed = params.has("seed") ? Number(params.get("seed")) : null;
          const game = criarJogoDoDuelo(partida, { seed, nomes: nomesParaDuelo() });
          TCG.iniciarJogo(game);
          ligarUIDoDuelo(game);
        } else if (redeAtual) {
          // "guestConectou" de novo, no meio de um duelo já em andamento,
          // só pode significar que o guest CAIU E RECONECTOU (ver regra
          // unificada em scripts/relay_server.py _parear: qualquer vez que
          // a sala volta a ficar completa, o host é avisado) — NÃO é uma
          // primeira conexão, então NÃO cria um duelo novo (isso jogaria
          // fora o duelo em andamento!). NÃO chama religarRede/TCG.criarRede
          // aqui: isso reconstruiria a rede sobre o MESMO `game.bus`, que já
          // tem os listeners onQualquer/selecaoPedida da rede ATUAL
          // registrados (sem "off" correspondente) — duplicaria pra sempre
          // todo broadcast dali pra frente. Só reenvia um snapshot completo
          // fresco pela rede que já existe (ver rede.js enviarSincronizacaoCompleta)
          // — exatamente o que o guest precisa pra recuperar o que perdeu.
          redeAtual.enviarSincronizacaoCompleta("resincronizacao");
        }
      } else if (msg.type === "oponenteDesconectou") {
        mostrarStatusConexao("O oponente caiu. Aguardando reconexão...");
      } else if (redeAtual) {
        redeAtual.tratarMensagem(msg);
      }
    };
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

    dispatch = function dispatch(ev) {
      const msg = JSON.parse(ev.data);
      if (msg.type === "pong") return;
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
      // snapshot que está chegando. Uma "resincronizacao" (host recuperando
      // ESTE guest depois de uma reconexão, ver dispatch do host) NÃO cai
      // aqui — o `if` só compara com "sincronizacaoInicial" — e por isso
      // segue direto pro tratarMensagem genérico logo abaixo, que já
      // aplica o snapshot recebido sem mexer no `game`/`ui` atuais.
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
      // Rede de segurança: nem todo "evento" tem um handler em ui.js que
      // enfileira uma animação (e portanto acaba chamando render() quando
      // ela termina) — "faseAlterada" sozinho (ex.: PRINCIPAL -> BATALHA,
      // sem compra/mana envolvida) é um caso real disso. Sem isto, o
      // `game` do guest já estava correto (aplicarSnapshot já rodou, ver
      // rede.js) mas a TELA ficava presa no estado anterior — o botão de
      // Atacar simplesmente nunca aparecia pro guest ao entrar na Fase de
      // Batalha. filaFxVazia() evita brigar com uma animação já em
      // andamento (ela mesma chama render() quando terminar).
      if (msg.type === "evento" && window.ui && window.ui.filaFxVazia()) window.ui.render();
    };
  }

  anexarListeners(ws);
};
