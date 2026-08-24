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
  const game = TCG.criarJogo({ seed, nomes: { 1: "Você", 2: "Oponente" } });
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

// ---- multiplayer LAN --------------------------------------------------

function mostrarStatusConexao(texto) {
  const el = document.getElementById("status-multiplayer");
  if (el) { el.textContent = texto; el.style.display = texto ? "block" : "none"; }
}

function iniciarMultiplayer(servidor) {
  const ws = new WebSocket(`ws://${servidor}`);
  ws.addEventListener("error", () => mostrarStatusConexao(`Não foi possível conectar em ws://${servidor}.`));
  ws.addEventListener("close", () => mostrarStatusConexao("Conexão com o outro jogador caiu. Recarregue a página pra tentar de novo."));

  ws.addEventListener("message", function primeiraMensagem(ev) {
    const msg = JSON.parse(ev.data);
    if (msg.type !== "papel") return; // ignora qualquer coisa antes da atribuição de papel
    ws.removeEventListener("message", primeiraMensagem);

    if (msg.papel === "host") {
      mostrarStatusConexao("Você é o HOST. Aguardando o outro jogador conectar...");
      const params = new URLSearchParams(window.location.search);
      const seed = params.has("seed") ? Number(params.get("seed")) : null;
      const game = TCG.criarJogo({ seed, nomes: { 1: "Você (host)", 2: "Oponente" } });
      window.game = game;
      // a UI só é ligada quando o guest conecta de verdade — antes disso
      // não faz sentido nenhuma ação rodar sem ter quem sincronizar.
      ws.addEventListener("message", function aoConectarGuest(ev2) {
        const msg2 = JSON.parse(ev2.data);
        if (msg2.type !== "guestConectou") return;
        ws.removeEventListener("message", aoConectarGuest);
        mostrarStatusConexao(null);
        TCG.iniciarJogo(game);
        TCG.criarRede({ role: "host", ws, game, jogadorLocal: 1 });
        window.ui = TCG.criarUI(game, 1, { modoLocal: false });
      });
    } else {
      // guest: NÃO cria uma simulação de verdade — só um objeto com o
      // formato certo pro render()/criarUI rodarem em cima; o RNG dele
      // nunca decide nada (o 1o snapshot do host sobrescreve tudo assim
      // que chegar, ver rede.js aplicarSnapshot).
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
  });
}

window.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const servidor = params.get("servidor");
  if (servidor) {
    iniciarMultiplayer(servidor);
    return;
  }
  const seed = params.has("seed") ? Number(params.get("seed")) : null;
  novaPartida(seed);
});
