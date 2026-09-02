// Ponto de entrada: cria a partida, liga a UI, expoe window.game pra
// depuracao/verificacao (ex.: script de teste em Playwright).
//
// Multiplayer LAN (ver scripts/relay_lan.py, webgame/rede.js): quando a URL
// tem ?servidor=<ip:porta>, em vez do fluxo local de sempre (humano vs bot),
// conecta num relay WebSocket. O relay decide, pela ORDEM de conexão, quem
// é "host" (dono da simulação de verdade) e quem é "guest" (espelho
// sincronizado) — o JS só reage ao que o relay informa, não escolhe sozinho.
const JOGADOR_LOCAL = 1;
const JOGADOR_IA = 2;

function novaPartida(seed) {
  // Baralho customizado (webgame/deckbuilder.html) salvo pro jogador local —
  // TCG.carregarDeckSalvo (engine.js) já valida e volta null se ausente ou
  // inválido, caso em que o comportamento é o de sempre (Panteão sorteado +
  // Baralho Arcano completo), sem diferença nenhuma pra quem nunca abriu o
  // deckbuilder.
  const deckSalvo = TCG.carregarDeckSalvo();
  const decksCustomizados = deckSalvo ? { [JOGADOR_LOCAL]: deckSalvo } : {};
  const game = TCG.criarJogo({ seed, nomes: { 1: "Você", 2: "Oponente" }, decksCustomizados });
  TCG.iniciarJogo(game);
  window.game = game;
  window.ui = TCG.criarUI(game, JOGADOR_LOCAL);
  return game;
}

window.iniciarNovaPartida = function iniciarNovaPartida() {
  const overlayFim = document.getElementById("overlay-fim");
  if (overlayFim) overlayFim.classList.remove("ativo");
  const params = new URLSearchParams(window.location.search);
  const seed = params.has("seed") ? Number(params.get("seed")) : null;
  novaPartida(seed);
};

// ---- multiplayer (LAN e sala por código, via internet) -----------------

function mostrarStatusConexao(texto) {
  const el = document.getElementById("status-multiplayer");
  if (el) { el.textContent = texto; el.style.display = texto ? "block" : "none"; }
}

// Comum aos dois jeitos de entrar em multiplayer (LAN via ?servidor=, ou
// sala por código via internet): uma vez que o relay já disse qual é o
// papel deste navegador, o resto do bootstrap é idêntico — só muda como o
// `ws` foi aberto e como o papel foi descoberto.
function bootstrapMultiplayer(ws, papel) {
  ws.addEventListener("close", () => mostrarStatusConexao("Conexão com o outro jogador caiu. Recarregue a página pra tentar de novo."));

  if (papel === "host") {
    mostrarStatusConexao("Você é o HOST. Aguardando o outro jogador conectar...");
    const params = new URLSearchParams(window.location.search);
    const seed = params.has("seed") ? Number(params.get("seed")) : null;
    const game = TCG.criarJogo({ seed, nomes: { 1: "Você (host)", 2: "Oponente" } });
    window.game = game;
    // a UI só é ligada quando o guest conecta de verdade — antes disso não
    // faz sentido nenhuma ação rodar sem ter quem sincronizar.
    ws.addEventListener("message", function aoConectarGuest(ev) {
      const msg = JSON.parse(ev.data);
      if (msg.type !== "guestConectou") return;
      ws.removeEventListener("message", aoConectarGuest);
      mostrarStatusConexao(null);
      TCG.iniciarJogo(game);
      TCG.criarRede({ role: "host", ws, game, jogadorLocal: 1 });
      window.ui = TCG.criarUI(game, 1, { modoLocal: false });
    });
  } else {
    // guest: NÃO cria uma simulação de verdade — só um objeto com o
    // formato certo pro render()/criarUI rodarem em cima; o RNG dele nunca
    // decide nada (o 1o snapshot do host sobrescreve tudo assim que
    // chegar, ver rede.js aplicarSnapshot).
    mostrarStatusConexao("Conectado. Aguardando o estado inicial do jogo...");
    const game = TCG.criarJogo({ nomes: { 1: "Oponente", 2: "Você" } });
    window.game = game;
    const rede = TCG.criarRede({ role: "guest", ws, game, jogadorLocal: 2 });
    window.ui = TCG.criarUI(game, 2, {
      modoLocal: false,
      acoes: rede.acoes,
      resolverSelecao: (id, escolha) => rede.resolverSelecao(id, escolha),
    });
    mostrarStatusConexao(null);
  }
}

// LAN (scripts/relay_lan.py): o relay decide o papel pela ORDEM de conexão
// — o JS só reage ao que ele informa, não escolhe sozinho.
function iniciarMultiplayerLan(servidor) {
  const ws = new WebSocket(`ws://${servidor}`);
  ws.addEventListener("error", () => mostrarStatusConexao(`Não foi possível conectar em ws://${servidor}.`));
  ws.addEventListener("message", function primeiraMensagem(ev) {
    const msg = JSON.parse(ev.data);
    if (msg.type !== "papel") return; // ignora qualquer coisa antes da atribuição de papel
    ws.removeEventListener("message", primeiraMensagem);
    bootstrapMultiplayer(ws, msg.papel);
  });
}

// Sala por código (scripts/relay_server.py), chegando aqui depois da
// navegação a partir de menu.html — o WebSocket de lá não sobrevive à
// troca de página, então abrimos um NOVO e mandamos "retomarSala" pra
// reocupar o mesmo slot (host/guest) que o menu já tinha conseguido.
async function iniciarMultiplayerPorSala({ relay, sala, papel }) {
  mostrarStatusConexao("Conectando...");
  try {
    const ws = await TCG.conectarRelay(relay);
    ws.addEventListener("error", () => mostrarStatusConexao(`Não foi possível conectar em ${relay}.`));
    await TCG.retomarSalaNoRelay(ws, sala, papel);
    bootstrapMultiplayer(ws, papel);
  } catch (e) {
    mostrarStatusConexao(e.message || "Não foi possível entrar na sala. Volte ao menu e tente de novo.");
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("sala") && params.get("papel")) {
    iniciarMultiplayerPorSala({ relay: params.get("relay") || TCG.RELAY_PADRAO, sala: params.get("sala"), papel: params.get("papel") });
    return;
  }
  const servidor = params.get("servidor");
  if (servidor) {
    iniciarMultiplayerLan(servidor);
    return;
  }
  const seed = params.has("seed") ? Number(params.get("seed")) : null;
  novaPartida(seed);
});
