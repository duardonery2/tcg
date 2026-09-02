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

// mostrarStatusConexao(texto) vem de match.js (carregado antes deste
// script), reaproveitada aqui só pra feedback de conexão/erro ANTES do
// handshake terminar — dali em diante quem cuida do status é match.js.

// LAN (scripts/relay_lan.py): o relay decide o papel pela ORDEM de conexão
// — o JS só reage ao que ele informa, não escolhe sozinho. Uma vez que o
// papel chega, o resto (criar duelos, trocar de duelo, contar vitórias) é
// idêntico ao caminho por código de sala — TCG.iniciarPartidaMultiplayer
// (match.js) cuida de tudo daqui pra frente.
function iniciarMultiplayerLan(servidor) {
  const ws = new WebSocket(`ws://${servidor}`);
  ws.addEventListener("error", () => mostrarStatusConexao(`Não foi possível conectar em ws://${servidor}.`));
  ws.addEventListener("message", function primeiraMensagem(ev) {
    const msg = JSON.parse(ev.data);
    if (msg.type !== "papel") return; // ignora qualquer coisa antes da atribuição de papel
    ws.removeEventListener("message", primeiraMensagem);
    TCG.iniciarPartidaMultiplayer({ ws, role: msg.papel, jogadorLocal: msg.papel === "host" ? 1 : 2 });
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
    TCG.iniciarPartidaMultiplayer({ ws, role: papel, jogadorLocal: papel === "host" ? 1 : 2 });
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
